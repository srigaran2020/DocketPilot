from datetime import date

import pytest

from docketpilot.rules.engine import add_months, checklist, deadlines, load, next_working_day

FACTS = {
    "cheque_date": "2025-01-10", "presentation_date": "2025-03-01", "return_reason": "Funds Insufficient",
    "return_information_date": "2025-03-05", "notice_date": "2025-03-20", "notice_received_date": "2025-03-25",
    "payment_received": False, "debt_description": "hand loan", "payee_bank_branch_city": "Coimbatore",
}


def test_add_months_clamps_month_end():
    assert add_months(date(2025, 8, 31), 6) == date(2026, 2, 28)
    assert add_months(date(2024, 8, 31), 6) == date(2025, 2, 28)
    assert add_months(date(2023, 8, 31), 6) == date(2024, 2, 29)  # leap year


def test_deadlines_chain():
    d = {x.id: x for x in deadlines(FACTS)}
    assert d["presentation"].due == date(2025, 7, 10)
    assert d["demand_notice"].due == date(2025, 4, 4)
    assert d["payment_window"].due == date(2025, 4, 9)
    # complaint: one month from the day after the payment window ends
    assert d["complaint"].due == date(2025, 5, 10)  # 10-04 + 1 month; a Saturday, so no shift
    assert d["complaint"].warn_on is not None


def test_sunday_and_holiday_shift():
    assert next_working_day(date(2025, 5, 11), set()) == date(2025, 5, 12)  # Sunday -> Monday
    assert next_working_day(date(2025, 5, 12), {date(2025, 5, 12)}) == date(2025, 5, 13)


def test_missing_anchor_gives_no_due_date():
    d = {x.id: x for x in deadlines({"cheque_date": "2025-01-10"})}
    assert d["presentation"].due is not None
    assert d["demand_notice"].due is None and d["complaint"].due is None


def test_lawyer_override_wins():
    d = {x.id: x for x in deadlines(FACTS, overrides={"complaint": date(2025, 6, 1)})}
    assert d["complaint"].due == date(2025, 6, 1)


def test_checklist_all_satisfied():
    res = {r.id: r.status for r in checklist(FACTS, today=date(2025, 4, 20))}
    assert res == {"debt": "satisfied", "presented_in_time": "satisfied", "returned_unpaid": "satisfied",
                   "notice_in_time": "satisfied", "no_payment": "satisfied", "complaint_in_time": "unclear",
                   "jurisdiction": "satisfied"}


def test_checklist_flags_late_notice_and_odd_reason():
    facts = {**FACTS, "notice_date": "2025-04-30", "return_reason": "Signature mismatch"}
    res = {r.id: r for r in checklist(facts, today=date(2025, 6, 1))}
    assert res["notice_in_time"].status == "missing" and "AFTER" in res["notice_in_time"].evidence
    assert res["returned_unpaid"].status == "unclear"


def test_checklist_payment_received():
    res = {r.id: r.status for r in checklist({**FACTS, "payment_received": True})}
    assert res["no_payment"] == "missing"


def test_every_rule_has_a_statute_quote():
    for name in ("s138_deadlines", "s138_elements"):
        data = load(name)
        items = data.get("rules") or data["elements"]
        for item in items:
            assert item["source"]["quote"] and item["source"]["section"]


@pytest.mark.integration
def test_rule_quotes_exist_in_stored_statute_text():
    """Rules must not drift from the law: every quote has to be in the India Code text we store."""
    from docketpilot.ingestion.load import connect
    from docketpilot.verification.quotes import norm

    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT section_number, text FROM section_versions")
        texts = {s: norm(t) for s, t in cur.fetchall()}
    if not texts:
        pytest.skip("statutes not loaded")
    for name in ("s138_deadlines", "s138_elements"):
        data = load(name)
        for item in data.get("rules") or data["elements"]:
            src = item["source"]
            assert norm(src["quote"]) in texts[src["section"]], (name, item["id"])
