"""Smart filing and the calendar.

Upload a paper from anywhere (chat or case page): the case number is read locally, the paper is filed under
the matching case (or a new case file), names are masked, and every date in the paper goes on the calendar.
Real names are shown on screen from the encrypted vault; the database only holds placeholders.
"""
import asyncio
import json
import re
import time
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from docketpilot import audit, casefile
from docketpilot.api.deps import CurrentUser, Session
from docketpilot.api.matters import _extract_text
from docketpilot.knowledge.pool import kb_conn
from docketpilot.privacy import redact as pii
from docketpilot.privacy import vault

router = APIRouter(tags=["cases"])
_PENDING: dict[str, dict[str, Any]] = {}  # preview id -> raw text etc. (memory only, never stored)
TTL_S = 900

KIND_LABEL = {"hearing": "Hearing", "filing": "Filing", "notice": "Notice", "order": "Order", "deadline": "Deadline",
              "other": "Date", "user": "Reminder", "rule": "Statutory deadline"}


def _kind(rule_id: str | None) -> str:
    if not rule_id:
        return "other"
    if rule_id.startswith("doc-"):
        return rule_id.split("-")[1]
    if rule_id.startswith("user-"):
        return "user"
    return "rule"


def case_card(conn: Any, matter_id: str) -> dict[str, Any]:
    """Case details for the screen, with real names from the vault."""
    with conn.cursor() as cur:
        cur.execute("""SELECT m.id::text, m.title, m.case_number, m.court, m.facts, m.created_at,
                              (SELECT count(*) FROM matter_documents d WHERE d.matter_id=m.id),
                              (SELECT min(due_date) FROM reminders r WHERE r.matter_id=m.id AND r.status='open'
                                 AND r.due_date >= current_date AND r.rule_id LIKE 'doc-hearing%%'),
                              (SELECT min(due_date) FROM reminders r WHERE r.matter_id=m.id AND r.status='open'
                                 AND r.due_date >= current_date),
                              (SELECT status FROM drafts d WHERE d.matter_id=m.id ORDER BY version DESC LIMIT 1)
                       FROM matters m WHERE m.id=%s""", (matter_id,))
        r = cur.fetchone()
    facts = r[4] or {}
    names = casefile.names(r[0])
    pet = casefile.show(facts.get("petitioner"), names)
    res = casefile.show(facts.get("respondent"), names)
    return {"id": r[0], "title": r[1], "case_number": r[2], "court": casefile.show(r[3], names), "case_type": facts.get("case_type"),
            "petitioner": pet, "respondent": res, "created_at": r[5], "documents": r[6],
            "next_hearing": r[7], "next_date": r[8], "latest_draft_status": r[9],
            "label": " · ".join(x for x in (r[2] or r[1], pet and f"{pet}" + (f" v. {res}" if res else "")) if x)}


# ---------------- upload: preview, then confirm ----------------

@router.post("/papers/preview")
async def paper_preview(user: CurrentUser, file: Annotated[UploadFile, File()],
                        matter_id: Annotated[str | None, Form()] = None) -> dict[str, Any]:
    data = await file.read()
    if len(data) > 15_000_000:
        raise HTTPException(413, "File too large (15 MB max)")
    name = Path(file.filename or "upload").name

    def run() -> dict[str, Any]:
        text, pages, src = _extract_text(name, data)
        with kb_conn() as conn:
            target = casefile.choose_matter(conn, user.firm_id, text, matter_id or None)
            label = case_card(conn, target["id"])["label"] if target["id"] else (target["case_number"] or "a new case file")
        mapping = casefile.names(target["id"]) if target["id"] else {}
        red = pii.redact(text, mapping=mapping)
        pid = uuid.uuid4().hex
        now = time.time()
        for k in [k for k, v in _PENDING.items() if now - v["ts"] > TTL_S]:
            _PENDING.pop(k, None)
        _PENDING[pid] = {"ts": now, "firm": str(user.firm_id), "text": text, "pages": pages, "src": src, "name": name,
                         "target": target}
        return {"preview_id": pid, "filename": name, "pages": pages, "redacted_text": red.text,
                "entities": [{"type": e.type, "placeholder": e.placeholder, "value": e.value} for e in red.entities],
                "target": {"matter_id": target["id"], "new": target["new"], "case_number": target["case_number"],
                           "label": label}}

    return await asyncio.to_thread(run)


class PaperConfirm(BaseModel):
    preview_id: str
    extra: list[tuple[str, str]] = []
    unmask: list[str] = []


@router.post("/papers/confirm", status_code=201)
async def paper_confirm(body: PaperConfirm, user: CurrentUser, session: Session) -> dict[str, Any]:
    p = _PENDING.pop(body.preview_id, None)
    if p is None or p["firm"] != str(user.firm_id):
        raise HTTPException(404, "Preview expired; attach the file again")

    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            t = p["target"]
            mid = t["id"] or casefile.create_matter(conn, user.firm_id, user.id, t["case_number"], t["case_number"],
                                                    t["case_key"])
            red = pii.redact(p["text"], mapping=casefile.names(mid), extra=body.extra, unmask=set(body.unmask))
            vault.save(mid, red.mapping)
            masks = [{"type": e.type, "placeholder": e.placeholder, "start": e.start, "end": e.end} for e in red.entities]
            did = uuid.uuid4()
            conn.execute("INSERT INTO matter_documents (id, matter_id, filename, pages, text_source, redacted_text, masks) "
                         "VALUES (%s,%s,%s,%s,%s,%s,%s)", (did, mid, p["name"], p["pages"], p["src"], red.text, json.dumps(masks)))
            conn.commit()
            result = casefile.analyze(conn, mid, red.text, p["name"])
            card = case_card(conn, mid)
            names = casefile.names(mid)
            events = [{**e, "title": casefile.show(e["title"], names)} for e in result["events"]]
            return {"matter": card, "new_case": t["id"] is None, "document_id": str(did), "masked": len(masks),
                    "events": events, "warning": result.get("error")}

    out = await asyncio.to_thread(run)
    audit.record(session, "document.upload", actor_user_id=user.id, firm_id=user.firm_id, target_type="matter",
                 target_id=out["matter"]["id"], details={"masked": out["masked"], "events": len(out["events"]),
                                                        "new_case": out["new_case"]})
    await session.commit()
    return out


# ---------------- cases list ----------------

@router.get("/cases")
async def cases(user: CurrentUser) -> list[dict[str, Any]]:
    def run() -> list[dict[str, Any]]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT id::text FROM matters WHERE firm_id=%s ORDER BY created_at DESC", (user.firm_id,))
            ids = [r[0] for r in cur.fetchall()]
            return [case_card(conn, i) for i in ids]

    return await asyncio.to_thread(run)


@router.post("/cases/{matter_id}/reread")
async def reread(matter_id: str, user: CurrentUser) -> dict[str, Any]:
    """Read dates again from every paper in the case (e.g. after the AI was busy at upload time)."""
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM matters WHERE id=%s AND firm_id=%s", (matter_id, user.firm_id))
                if cur.fetchone() is None:
                    raise HTTPException(404, "Case not found")
                cur.execute("SELECT filename, redacted_text FROM matter_documents WHERE matter_id=%s", (matter_id,))
                docs = cur.fetchall()
            events, warn = [], None
            for name, text in docs:
                r = casefile.analyze(conn, matter_id, text, name)
                events += r["events"]
                warn = warn or r.get("error")
            return {"events": events, "warning": warn, "matter": case_card(conn, matter_id)}

    return await asyncio.to_thread(run)


# ---------------- calendar & reminders ----------------

@router.get("/calendar")
async def calendar(user: CurrentUser, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    start = start or (date.today().replace(day=1) - timedelta(days=7))
    end = end or (start + timedelta(days=75))

    def run() -> dict[str, Any]:
        with kb_conn() as conn, conn.cursor() as cur:
            cur.execute("""SELECT r.id::text, r.title, r.due_date, r.warn_on, r.status, r.rule_id, r.source,
                                  m.id::text, m.title, m.case_number, m.facts
                           FROM reminders r JOIN matters m ON m.id = r.matter_id
                           WHERE m.firm_id=%s AND r.due_date BETWEEN %s AND %s ORDER BY r.due_date""",
                        (user.firm_id, start, end))
            rows = cur.fetchall()
        cache: dict[str, dict[str, str]] = {}
        events = []
        for rid, title, due, warn, status, rule, source, mid, mtitle, cno, facts in rows:
            names = cache.setdefault(mid, casefile.names(mid))
            facts = facts or {}
            pet = casefile.show(facts.get("petitioner"), names)
            kind = _kind(rule)
            events.append({"id": rid, "title": casefile.show(title, names), "date": due.isoformat(),
                           "warn_on": warn.isoformat() if warn else None, "status": status, "kind": kind,
                           "kind_label": KIND_LABEL.get(kind, "Date"), "source": casefile.show(source, names),
                           "matter_id": mid, "case_number": cno, "petitioner": pet, "case": cno or mtitle})
        today = date.today()
        soon = [e for e in events if e["status"] == "open" and today <= date.fromisoformat(e["date"]) <= today + timedelta(days=7)]
        return {"start": start.isoformat(), "end": end.isoformat(), "events": events, "due_this_week": soon}

    return await asyncio.to_thread(run)


class ReminderIn(BaseModel):
    matter_id: str
    title: str = Field(min_length=2, max_length=200)
    date: date


@router.post("/reminders", status_code=201)
async def add_reminder(body: ReminderIn, user: CurrentUser) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        with kb_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM matters WHERE id=%s AND firm_id=%s", (body.matter_id, user.firm_id))
                if cur.fetchone() is None:
                    raise HTTPException(404, "Case not found")
            rid = uuid.uuid4()
            kind = "hearing" if re.search(r"hearing|posting|next date", body.title, re.I) else "user"
            rule = f"doc-hearing-u{rid.hex[:8]}" if kind == "hearing" else f"user-{rid.hex[:8]}"
            conn.execute("""INSERT INTO reminders (id, matter_id, rule_id, title, due_date, warn_on, source)
                            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                         (rid, body.matter_id, rule, body.title, body.date, body.date - timedelta(days=2), "Added by you"))
            conn.commit()
            return {"id": str(rid)}

    return await asyncio.to_thread(run)


class ReminderPatch(BaseModel):
    status: str = Field(pattern="^(open|done)$")


@router.patch("/reminders/{rid}")
async def patch_reminder(rid: str, body: ReminderPatch, user: CurrentUser) -> dict[str, str]:
    def run() -> None:
        with kb_conn() as conn:
            cur = conn.execute("""UPDATE reminders r SET status=%s FROM matters m
                                  WHERE r.id=%s AND m.id=r.matter_id AND m.firm_id=%s""", (body.status, rid, user.firm_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "Reminder not found")
            conn.commit()

    await asyncio.to_thread(run)
    return {"status": body.status}


@router.delete("/reminders/{rid}", status_code=204)
async def delete_reminder(rid: str, user: CurrentUser) -> None:
    def run() -> None:
        with kb_conn() as conn:
            cur = conn.execute("DELETE FROM reminders r USING matters m WHERE r.id=%s AND m.id=r.matter_id AND m.firm_id=%s",
                               (rid, user.firm_id))
            if cur.rowcount == 0:
                raise HTTPException(404, "Reminder not found")
            conn.commit()

    await asyncio.to_thread(run)
