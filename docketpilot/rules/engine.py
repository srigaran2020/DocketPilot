"""Deadline computation and the Section 138 element checklist, driven by data/rules/*.json."""
import calendar
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parents[2] / "data" / "rules"


@lru_cache
def load(name: str) -> dict[str, Any]:
    return json.loads((RULES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


@dataclass
class Deadline:
    id: str
    title: str
    due: date | None
    warn_on: date | None
    anchor: str
    note: str
    source: dict[str, str]
    holiday_shift: bool = False


def _parse(v: Any) -> date | None:
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def next_working_day(d: date, holidays: set[date]) -> date:
    while d.weekday() == 6 or d in holidays:  # Sundays and recorded court holidays
        d += timedelta(days=1)
    return d


def deadlines(facts: dict[str, Any], holidays: set[date] | None = None,
              overrides: dict[str, date] | None = None) -> list[Deadline]:
    """overrides: the lawyer's own dates per rule id (spec 9: 'the lawyer's own override')."""
    holidays = holidays or set()
    out: dict[str, Deadline] = {}
    for r in load("s138_deadlines")["rules"]:
        if "anchor_fact" in r:
            base, anchor = _parse(facts.get(r["anchor_fact"])), r["anchor_fact"]
        else:
            prev = out.get(r["anchor_rule"])
            base = prev.due + timedelta(days=r.get("anchor_offset_days", 0)) if prev and prev.due else None
            anchor = f"{r['anchor_rule']} deadline + {r.get('anchor_offset_days', 0)} day(s)"
        due = None
        shifted = False
        if overrides and r["id"] in overrides:
            due = overrides[r["id"]]
        elif base:
            raw_due = add_months(base, r["months"]) + timedelta(days=r["days"])
            due = next_working_day(raw_due, holidays)
            shifted = due != raw_due
        warn = due - timedelta(days=r["warn_days_before"]) if due else None
        out[r["id"]] = Deadline(r["id"], r["title"], due, warn, anchor, r["note"], r["source"], shifted)
    return list(out.values())


@dataclass
class ElementResult:
    id: str
    title: str
    status: str  # satisfied | unclear | missing
    evidence: str
    source: dict[str, str]


def checklist(facts: dict[str, Any], today: date | None = None) -> list[ElementResult]:
    today = today or date.today()
    dl = {d.id: d for d in deadlines(facts)}
    out = []
    for el in load("s138_elements")["elements"]:
        status, evidence = "unclear", ""
        if el["check"] == "fact_present":
            vals = [facts.get(f) for f in el["facts"]]
            if all(vals):
                status, evidence = "satisfied", "; ".join(f"{f}: {v}" for f, v in zip(el["facts"], vals, strict=True))
            else:
                status, evidence = "missing", f"Not found in the documents: {', '.join(el['facts'])}"
        elif el["check"] == "within_deadline":
            d, fact_val = dl.get(el["deadline"]), _parse(facts.get(el["fact"]))
            if d is None or d.due is None:
                evidence = f"Cannot compute the '{el['deadline']}' deadline: a date it depends on is missing."
            elif fact_val is None:
                evidence = f"Deadline is {d.due:%d-%m-%Y}; '{el['fact']}' not found in documents."
                status = "missing" if today > d.due else "unclear"
            else:
                ok = fact_val <= d.due
                status = "satisfied" if ok else "missing"
                when = "is on or before" if ok else "is AFTER"
                evidence = f"{el['fact']} {fact_val:%d-%m-%Y} {when} deadline {d.due:%d-%m-%Y}."
        elif el["check"] == "pattern":
            v = facts.get(el["fact"])
            if not v:
                status, evidence = "missing", f"'{el['fact']}' not found in documents."
            elif re.search(el["pattern"], str(v), re.I):
                status, evidence = "satisfied", f"Return reason: {v}"
            else:
                evidence = f"Return reason '{v}' may not be one covered by s.138; needs review."
        elif el["check"] == "payment_not_made":
            d = dl.get(el["deadline"])
            paid = facts.get(el["fact"])
            if paid is True:
                status, evidence = "missing", "Documents say payment was received."
            elif d and d.due and today > d.due and paid is False:
                status, evidence = "satisfied", f"No payment by {d.due:%d-%m-%Y}."
            elif d and d.due and today <= d.due:
                evidence = f"Payment window still open until {d.due:%d-%m-%Y}."
            else:
                evidence = "Payment status not stated in the documents."
        out.append(ElementResult(el["id"], el["title"], status, evidence, el["source"]))
    return out


def as_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in asdict(i).items()} for i in items]
