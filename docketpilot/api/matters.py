"""Matters, document upload with redaction preview, drafts with approval, reminders, dashboard.

Every matter query is limited to the user's firm. Original (unredacted) uploads are never stored: the
preview keeps the text in memory for a few minutes; only redacted text goes to the database, and the
placeholder map goes to the encrypted local vault.
"""
import asyncio
import io
import json
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from docketpilot import audit
from docketpilot.api.deps import CurrentUser, Session, require_role
from docketpilot.knowledge.pool import kb_conn
from docketpilot.models import Role, User
from docketpilot.privacy import redact as pii
from docketpilot.privacy import vault

router = APIRouter(tags=["matters"])
Approver = Annotated[User, Depends(require_role(Role.advocate, Role.admin))]

_PREVIEWS: dict[str, tuple[float, str, str, str, int, str]] = {}  # id -> (ts, firm, matter, text, pages, filename+src)
PREVIEW_TTL_S = 900


def _rows(cur: Any) -> list[dict[str, Any]]:
    cols = [d.name for d in cur.description or []]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def _own_matter(conn: Any, matter_id: str, firm_id: uuid.UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM matters WHERE id = %s AND firm_id = %s", (matter_id, firm_id))
        rows = _rows(cur)
    if not rows:
        raise HTTPException(404, "Matter not found")
    return rows[0]


# ---------------- matters ----------------

class MatterIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    court: str | None = None
    case_number: str | None = None


@router.post("/matters", status_code=201)
async def create_matter(body: MatterIn, user: CurrentUser, session: Session) -> dict[str, Any]:
    mid = uuid.uuid4()

    def run() -> None:
        with kb_conn() as conn:
            conn.execute("INSERT INTO matters (id, firm_id, title, court, case_number, created_by) "
                         "VALUES (%s,%s,%s,%s,%s,%s)", (mid, user.firm_id, body.title, body.court, body.case_number,
                                                        user.id))
            conn.commit()

    await asyncio.to_thread(run)
    audit.record(session, "matter.create", actor_user_id=user.id, firm_id=user.firm_id, target_type="matter",
                 target_id=str(mid))
    await session.commit()
    return {"id": str(mid)}


@router.get("/matters")
async def list_matters(user: CurrentUser) -> list[dict[str, Any]]:
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT m.id, m.title, m.court, m.case_number, m.stage, m.created_at,
                                  (SELECT count(*) FROM matter_documents d WHERE d.matter_id = m.id) AS documents,
                                  (SELECT status FROM drafts d WHERE d.matter_id = m.id ORDER BY version DESC LIMIT 1)
                                    AS latest_draft_status,
                                  (SELECT min(due_date) FROM reminders r WHERE r.matter_id = m.id AND r.status='open'
                                     AND r.due_date >= current_date) AS next_deadline
                           FROM matters m WHERE m.firm_id = %s ORDER BY m.created_at DESC""", (user.firm_id,))
            return _rows(cur)

    return await asyncio.to_thread(run)


@router.get("/matters/{matter_id}")
async def get_matter(matter_id: str, user: CurrentUser, session: Session) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            m = _own_matter(conn, matter_id, user.firm_id)
            with conn.cursor() as cur:
                cur.execute("SELECT id, filename, pages, text_source, masks, created_at FROM matter_documents "
                            "WHERE matter_id=%s ORDER BY created_at", (matter_id,))
                m["documents"] = _rows(cur)
                cur.execute("SELECT id, version, template, doc_type, status, created_at, approved_at FROM drafts "
                            "WHERE matter_id=%s ORDER BY version DESC", (matter_id,))
                m["drafts"] = _rows(cur)
                cur.execute("SELECT id, rule_id, title, due_date, warn_on, source, status FROM reminders "
                            "WHERE matter_id=%s ORDER BY due_date", (matter_id,))
                m["reminders"] = _rows(cur)
            return m

    m = await asyncio.to_thread(run)
    audit.record(session, "matter.view", actor_user_id=user.id, firm_id=user.firm_id, target_type="matter",
                 target_id=matter_id)
    await session.commit()
    return m


# ---------------- documents: preview, then confirm ----------------

def _extract_text(name: str, data: bytes) -> tuple[str, int, str]:
    lower = name.lower()
    if lower.endswith(".pdf"):
        from pypdf import PdfReader

        pages = [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]
        if sum(len(p.strip()) for p in pages) < 50:
            raise HTTPException(422, "This PDF has no text layer (probably a scan). OCR is not available in the "
                                     "prototype; upload a text PDF, .docx or .txt.")
        return "\f".join(pages), len(pages), "text_layer"
    if lower.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs), 1, "docx"
    if lower.endswith(".txt"):
        return data.decode("utf-8", errors="replace"), 1, "plain_text"
    raise HTTPException(415, "Supported files: .pdf (with text), .docx, .txt")


@router.post("/matters/{matter_id}/documents/preview")
async def preview_document(matter_id: str, user: CurrentUser, file: Annotated[UploadFile, File()]) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "File too large (15 MB max)")
    name = Path(file.filename or "upload").name

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            _own_matter(conn, matter_id, user.firm_id)
        text, pages, src = _extract_text(name, data)
        red = pii.redact(text, mapping=vault.load(matter_id))
        pid = uuid.uuid4().hex
        now = time.time()
        for k in [k for k, v in _PREVIEWS.items() if now - v[0] > PREVIEW_TTL_S]:
            _PREVIEWS.pop(k, None)
        _PREVIEWS[pid] = (now, str(user.firm_id), matter_id, text, pages, f"{name}|{src}")
        return {"preview_id": pid, "filename": name, "pages": pages, "text_source": src,
                "redacted_text": red.text,
                "entities": [{"type": e.type, "placeholder": e.placeholder, "value": e.value, "source": e.source}
                             for e in red.entities],
                "note": "Shown only to you, on this machine. Add anything missed, or un-mask false hits, then confirm."}

    return await asyncio.to_thread(run)


class ConfirmIn(BaseModel):
    preview_id: str
    extra: list[tuple[str, str]] = []  # (type, value) the lawyer wants masked too
    unmask: list[str] = []  # values that are not personal data


@router.post("/matters/{matter_id}/documents", status_code=201)
async def confirm_document(matter_id: str, body: ConfirmIn, user: CurrentUser, session: Session) -> dict[str, Any]:
    pv = _PREVIEWS.pop(body.preview_id, None)
    if pv is None or pv[1] != str(user.firm_id) or pv[2] != matter_id:
        raise HTTPException(404, "Preview expired; upload the file again")
    _, _, _, text, pages, name_src = pv
    name, src = name_src.rsplit("|", 1)
    did = uuid.uuid4()

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            _own_matter(conn, matter_id, user.firm_id)
            red = pii.redact(text, mapping=vault.load(matter_id), extra=body.extra, unmask=set(body.unmask))
            vault.save(matter_id, red.mapping)
            masks = [{"type": e.type, "placeholder": e.placeholder, "start": e.start, "end": e.end}
                     for e in red.entities]
            conn.execute("INSERT INTO matter_documents (id, matter_id, filename, pages, text_source, redacted_text, "
                         "masks) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                         (did, matter_id, name, pages, src, red.text, json.dumps(masks)))
            conn.commit()
            from docketpilot import casefile  # case number, parties and dates -> case details + calendar

            cn = casefile.find_case_number(text)
            if cn:
                conn.execute("""UPDATE matters SET case_number=coalesce(case_number, %s),
                                facts = facts || jsonb_build_object('case_key', coalesce(facts->>'case_key', %s))
                                WHERE id=%s""", (cn.display, cn.key, matter_id))
                conn.commit()
            result = casefile.analyze(conn, matter_id, red.text, name)
            return {"id": str(did), "masked": len(masks), "events": result["events"], "warning": result.get("error")}

    out = await asyncio.to_thread(run)
    audit.record(session, "document.upload", actor_user_id=user.id, firm_id=user.firm_id, target_type="document",
                 target_id=str(did), details={"matter": matter_id, "masked": out["masked"], "pages": pages,
                                              "added_by_lawyer": len(body.extra), "unmasked": len(body.unmask)})
    await session.commit()
    return out


# ---------------- drafts ----------------

class DraftIn(BaseModel):
    workflow: str = Field(default="general", pattern="^(demand_notice|complaint|general)$")
    doc_type: str | None = Field(default=None, max_length=200)  # general: "Bail application", "Written statement"...
    instructions: str | None = Field(default=None, max_length=20_000)  # general: what to draft, in the lawyer's words


def launch_draft(conn: Any, user: Any, matter_id: str, workflow: str, background: BackgroundTasks,
                 doc_type: str | None = None, instructions: str | None = None) -> dict[str, Any]:
    """Create the draft row and run the agents in the background. Instructions are masked with the case file's
    own placeholder map, so PERSON_1 in the instructions is the same person as PERSON_1 in the papers."""
    from docketpilot.agents import graph

    with conn.cursor() as cur:
        cur.execute("SELECT id::text, filename, redacted_text FROM matter_documents WHERE matter_id=%s ORDER BY created_at",
                    (matter_id,))
        docs = _rows(cur)
        cur.execute("SELECT coalesce(max(version), 0) + 1 FROM drafts WHERE matter_id=%s", (matter_id,))
        version = cur.fetchone()[0]
    if workflow != "general" and not docs:
        raise HTTPException(422, "Upload at least one document first")
    red_instructions = None
    if instructions:
        red = pii.redact(instructions, mapping=vault.load(matter_id))
        vault.save(matter_id, red.mapping)
        red_instructions = red.text
    if workflow == "general" and not (docs or red_instructions):
        raise HTTPException(422, "Say what to draft, or upload the case papers first")
    did = uuid.uuid4()
    conn.execute("INSERT INTO drafts (id, matter_id, version, template, doc_type, instructions, status, thread_id, created_by) "
                 "VALUES (%s,%s,%s,%s,%s,%s,'running',%s,%s)",
                 (did, matter_id, version, workflow, doc_type, red_instructions, str(did), user.id))
    conn.commit()
    background.add_task(asyncio.to_thread, _run_graph, graph.start, str(did), matter_id, workflow, docs, doc_type,
                        red_instructions)
    return {"id": str(did), "status": "running", "documents": len(docs)}


def _run_graph(fn: Any, *args: Any) -> None:
    from docketpilot.agents.nodes import save_draft

    try:
        fn(*args)
    except Exception as e:  # never leave a draft stuck in 'running'
        save_draft(args[0], status="failed", trace=[{"node": "graph", "error": f"{type(e).__name__}: {e}"}])


@router.post("/matters/{matter_id}/drafts", status_code=202)
async def start_draft(matter_id: str, body: DraftIn, user: CurrentUser, session: Session,
                      background: BackgroundTasks) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            _own_matter(conn, matter_id, user.firm_id)
            return launch_draft(conn, user, matter_id, body.workflow, background, body.doc_type, body.instructions)

    out = await asyncio.to_thread(run)
    audit.record(session, "draft.start", actor_user_id=user.id, firm_id=user.firm_id, target_type="draft",
                 target_id=out["id"], details={"workflow": body.workflow, "model": "groq (redacted text only)"})
    await session.commit()
    return {"id": out["id"], "status": "running"}


def _own_draft(conn: Any, draft_id: str, firm_id: uuid.UUID) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("""SELECT d.* FROM drafts d JOIN matters m ON m.id = d.matter_id
                       WHERE d.id = %s AND m.firm_id = %s""", (draft_id, firm_id))
        rows = _rows(cur)
    if not rows:
        raise HTTPException(404, "Draft not found")
    return rows[0]


@router.get("/drafts/{draft_id}")
async def get_draft(draft_id: str, user: CurrentUser) -> dict[str, Any]:
    from docketpilot.agents import graph

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            d = _own_draft(conn, draft_id, user.firm_id)
        if d["status"] not in ("running",):
            try:
                st = graph.current(draft_id)
                d["facts"] = st["values"].get("facts")
                d["fact_sources"] = st["values"].get("fact_sources")
                d["graph_trace"] = st["values"].get("trace")
                d["error"] = st["values"].get("error")
                d["approval"] = st["values"].get("approval")
                d["waiting_for"] = st["next"]
            except Exception:  # noqa: S110 (graph state is optional detail)
                pass
            if d["status"] == "failed" and not d.get("error"):  # e.g. cut off by a server restart
                d["error"] = next((t.get("error") for t in reversed(d.get("trace") or []) if t.get("error")), None)
        return d

    return await asyncio.to_thread(run)


class ApproveIn(BaseModel):
    acknowledged: list[str] = []


class ReviseIn(BaseModel):
    text: str = Field(min_length=20, max_length=200_000)


@router.post("/drafts/{draft_id}/approve")
async def approve(draft_id: str, body: ApproveIn, user: Approver, session: Session) -> dict[str, Any]:
    from docketpilot.agents import graph

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            d = _own_draft(conn, draft_id, user.firm_id)
        if d["status"] not in ("awaiting_approval", "blocked"):
            raise HTTPException(409, f"Draft is {d['status']}")
        out = graph.resume(draft_id, {"action": "approve", "user_id": str(user.id),
                                      "acknowledged": body.acknowledged})
        return {"status": out.get("status"), "approval": out.get("approval")}

    res = await asyncio.to_thread(run)
    ok = res["status"] == "approved"
    audit.record(session, "draft.approve" if ok else "draft.approve_refused", actor_user_id=user.id,
                 firm_id=user.firm_id, target_type="draft", target_id=draft_id,
                 details={"acknowledged": body.acknowledged})
    await session.commit()
    if not ok:
        raise HTTPException(409, (res.get("approval") or {}).get("reason", "Not approved"))
    return res


@router.post("/drafts/{draft_id}/revise", status_code=202)
async def revise(draft_id: str, body: ReviseIn, user: CurrentUser, session: Session,
                 background: BackgroundTasks) -> dict[str, Any]:
    """The lawyer's edited text (still with placeholders) is re-verified before it can be approved."""
    from docketpilot.agents import graph
    from docketpilot.agents.nodes import save_draft

    def run() -> None:
        with kb_conn() as conn:
            d = _own_draft(conn, draft_id, user.firm_id)
        if d["status"] not in ("awaiting_approval", "blocked"):
            raise HTTPException(409, f"Draft is {d['status']}")
        save_draft(draft_id, status="running")

    await asyncio.to_thread(run)
    background.add_task(asyncio.to_thread, _run_graph, graph.resume, draft_id, {"action": "revise", "text": body.text})
    audit.record(session, "draft.revise", actor_user_id=user.id, firm_id=user.firm_id, target_type="draft",
                 target_id=draft_id)
    await session.commit()
    return {"status": "running"}


@router.get("/drafts/{draft_id}/download")
async def download(draft_id: str, user: CurrentUser, session: Session) -> FileResponse:
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            return _own_draft(conn, draft_id, user.firm_id)

    d = await asyncio.to_thread(run)
    if d["status"] != "approved" or not d.get("output_file"):
        raise HTTPException(409, "Only approved drafts can be downloaded")
    audit.record(session, "draft.export", actor_user_id=user.id, firm_id=user.firm_id, target_type="draft",
                 target_id=draft_id)
    await session.commit()
    return FileResponse(d["output_file"], filename=f"draft-v{d['version']}-{d['template']}.docx")


# ---------------- reminders and dashboard ----------------

@router.get("/matters/{matter_id}/reminders.ics")
async def reminders_ics(matter_id: str, user: CurrentUser) -> Response:
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn:
            m = _own_matter(conn, matter_id, user.firm_id)
            with conn.cursor() as cur:
                cur.execute("SELECT id, title, due_date, source FROM reminders WHERE matter_id=%s", (matter_id,))
                rows = _rows(cur)
            for r in rows:
                r["matter"] = m["title"]
            return rows

    rows = await asyncio.to_thread(run)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//DocketPilot//EN"]
    for r in rows:
        d: date = r["due_date"]
        desc = f"{r['source']} (computed by DocketPilot; not checked by a lawyer)".replace(",", "\\,").replace(";", "\\;")
        lines += ["BEGIN:VEVENT", f"UID:{r['id']}@docketpilot", f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
                  f"DTEND;VALUE=DATE:{d + timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{r['matter']}: {r['title']}".replace(",", "\\,"), f"DESCRIPTION:{desc}",
                  "BEGIN:VALARM", "TRIGGER:-P3D", "ACTION:DISPLAY", "DESCRIPTION:Deadline in 3 days", "END:VALARM",
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return Response("\r\n".join(lines), media_type="text/calendar",
                    headers={"Content-Disposition": f'attachment; filename="matter-{matter_id[:8]}.ics"'})


@router.get("/dashboard")
async def dashboard(user: CurrentUser) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT r.title, r.due_date, r.warn_on, m.title AS matter, m.id AS matter_id
                           FROM reminders r JOIN matters m ON m.id = r.matter_id
                           WHERE m.firm_id = %s AND r.status = 'open' AND r.due_date >= current_date - 7
                           ORDER BY r.due_date LIMIT 20""", (user.firm_id,))
            upcoming = _rows(cur)
            cur.execute("""SELECT d.id, d.version, d.template, d.doc_type, d.status, m.title AS matter, m.id AS matter_id,
                                  d.created_at FROM drafts d JOIN matters m ON m.id = d.matter_id
                           WHERE m.firm_id = %s AND d.status IN ('awaiting_approval','blocked','running','failed')
                           ORDER BY d.created_at DESC LIMIT 20""", (user.firm_id,))
            drafts = _rows(cur)
            cur.execute("SELECT count(*) FROM matters WHERE firm_id = %s", (user.firm_id,))
            n = cur.fetchone()[0]  # type: ignore[index]
        return {"matters": n, "upcoming_deadlines": upcoming, "drafts_needing_action": drafts,
                "notice": "Deadlines are computed from unverified rules. Not legal advice; not reviewed by a lawyer."}

    return await asyncio.to_thread(run)
