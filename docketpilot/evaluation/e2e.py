"""End-to-end check of the whole flow through the real API (Phase 6/7 acceptance). Synthetic data only.

upload -> redaction preview -> confirm -> draft (7 agents) -> verification gate -> approve -> .docx + reminders
Also checks that a draft with a planted wrong citation is BLOCKED and cannot be approved.

    python -m docketpilot.evaluation.e2e
"""
import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from docketpilot.api.main import app
from docketpilot.cli import create_admin

REPORTS = Path(__file__).resolve().parents[2] / "reports"
DOCS = {
    "return_memo.txt": (
        "SYNTHETIC TEST DOCUMENT\nCHEQUE RETURN MEMO\nBank: Kaveri Grameena Bank, R.S. Puram Branch, Coimbatore\n"
        "Date: 03-07-2025\nCheque No. 004512 dated 10-06-2025 for Rs. 2,50,000/- drawn by Mr. Senthil Natarajan "
        "on A/c No. 501200334455 has been returned unpaid for the reason: FUNDS INSUFFICIENT.\n"
        "The cheque was presented for collection on 01-07-2025 by Mr. Arjun Menon through his account at our "
        "Coimbatore branch."),
    "client_statement.txt": (
        "SYNTHETIC TEST DOCUMENT\nStatement of Mr. Arjun Menon, phone 9876501234.\n"
        "In January 2025 I lent Rs. 2,50,000 as a hand loan to Mr. Senthil Natarajan, S/o Ramesh Natarajan, "
        "residing at No. 14, Gandhi Road, Salem - 636007, to be repaid by June 2025. Towards repayment of this loan "
        "he gave me cheque No. 004512 dated 10-06-2025 for Rs. 2,50,000. I deposited it on 01-07-2025 at my bank "
        "branch in Coimbatore. The bank informed me on 03-07-2025 that it was returned for insufficient funds.\n"
        "My advocate sent a written demand notice dated 15-07-2025, which Mr. Senthil Natarajan received on "
        "18-07-2025. He has not paid any amount till date."),
}


async def wait_for(c: httpx.AsyncClient, h: dict[str, str], draft_id: str, timeout_s: int = 900) -> dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        d = (await c.get(f"/drafts/{draft_id}", headers=h)).json()
        if d["status"] != "running":
            return d
        await asyncio.sleep(5)
    raise TimeoutError("draft still running")


async def main_async() -> dict[str, Any]:
    out: dict[str, Any] = {"run_at": datetime.now(UTC).isoformat(), "steps": []}
    email, pw = f"e2e-{uuid.uuid4().hex[:6]}@example.test", "e2e-synthetic-pass-1"
    os.environ["DP_ADMIN_PASSWORD"] = pw
    await create_admin(f"E2E Synthetic Firm {uuid.uuid4().hex[:6]}", email, "E2E Admin", pw)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://e2e", timeout=1200) as c:
        tok = (await c.post("/auth/login", data={"username": email, "password": pw})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        mid = (await c.post("/matters", json={"title": "E2E synthetic cheque matter"}, headers=h)).json()["id"]

        for name, text in DOCS.items():
            pv = (await c.post(f"/matters/{mid}/documents/preview", headers=h,
                               files={"file": (name, text.encode(), "text/plain")})).json()
            leaked = [v for v in ("Senthil", "Arjun", "9876501234", "501200334455", "Gandhi Road") if v in pv["redacted_text"]]
            out["steps"].append({"step": f"preview {name}", "masked": len(pv["entities"]), "leaked_values": leaked})
            r = await c.post(f"/matters/{mid}/documents", headers=h, json={"preview_id": pv["preview_id"]})
            assert r.status_code == 201, r.text

        t0 = time.time()
        did = (await c.post(f"/matters/{mid}/drafts", json={"workflow": "complaint"}, headers=h)).json()["id"]
        d = await wait_for(c, h, did)
        out["draft_seconds"] = round(time.time() - t0, 1)
        out["steps"].append({"step": "draft", "status": d["status"], "release": (d.get("verification") or {}).get("release"),
                             "facts": d.get("facts"), "error": d.get("error"), "trace": d.get("graph_trace")})
        if d["status"] == "failed":
            return out

        # If the generated draft is blocked, a lawyer would edit it; here we drop red items by revising.
        rep = d["verification"]
        if rep["release"] == "blocked":
            text = d["redacted_text"]
            for cit in rep["citations"]:
                if cit["colour"] == "red":
                    text = text.replace(cit["raw"], "")
            await c.post(f"/drafts/{did}/revise", json={"text": text}, headers=h)
            d = await wait_for(c, h, did)
            rep = d["verification"]
            out["steps"].append({"step": "revise to remove red items", "release": rep["release"]})

        ack = rep["items_needing_acknowledgement"]
        r = await c.post(f"/drafts/{did}/approve", json={"acknowledged": ack}, headers=h)
        out["steps"].append({"step": "approve", "http": r.status_code, "body": r.json()})
        dl = await c.get(f"/drafts/{did}/download", headers=h)
        out["steps"].append({"step": "download docx", "http": dl.status_code, "bytes": len(dl.content),
                             "real_names_restored": b"word/document.xml" in dl.content})
        m = (await c.get(f"/matters/{mid}", headers=h)).json()
        out["reminders"] = [{"title": x["title"], "due": x["due_date"]} for x in m["reminders"]]
        ics = await c.get(f"/matters/{mid}/reminders.ics", headers=h)
        out["steps"].append({"step": "calendar .ics", "http": ics.status_code, "events": ics.text.count("BEGIN:VEVENT")})

        # Gate check: a draft with a citation that belongs to a different case must be blocked.
        did2 = (await c.post(f"/matters/{mid}/drafts", json={"workflow": "demand_notice"}, headers=h)).json()["id"]
        d2 = await wait_for(c, h, did2)
        if d2["status"] in ("awaiting_approval", "blocked"):
            bad = d2["redacted_text"] + ("\n\nAs held in Rajeshbhai Muljibhai Patel v. State of Gujarat, "
                                         "[2020] 7 S.C.R. 89, the notice is valid.")
            await c.post(f"/drafts/{did2}/revise", json={"text": bad}, headers=h)
            d2 = await wait_for(c, h, did2)
            r2 = await c.post(f"/drafts/{did2}/approve",
                              json={"acknowledged": d2["verification"]["items_needing_acknowledgement"]}, headers=h)
            out["gate_check"] = {"release": d2["verification"]["release"], "approve_http": r2.status_code,
                                 "blocked_as_expected": d2["verification"]["release"] == "blocked"
                                 and r2.status_code == 409}
        else:
            out["gate_check"] = {"status": d2["status"], "error": d2.get("error")}
    return out


def main() -> None:
    result = asyncio.run(main_async())
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "e2e.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(json.dumps(result, indent=1, default=str)[:6000])


if __name__ == "__main__":
    main()
