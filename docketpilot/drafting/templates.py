"""Fill a template: {{field}} from facts, [[LLM:section]] from model output. Missing facts stay visible."""
import re
from datetime import date
from pathlib import Path
from typing import Any

TEMPLATES = Path(__file__).resolve().parents[2] / "data" / "templates"
NAMES = {"demand_notice": "demand_notice_v1", "complaint": "complaint_v1"}
MISSING = "[NOT IN DOCUMENTS: {}]"


def load(kind: str) -> str:
    text = (TEMPLATES / f"{NAMES[kind]}.txt").read_text(encoding="utf-8")
    return "\n".join(ln for ln in text.splitlines() if not ln.startswith("#")).strip() + "\n"


def llm_sections(template: str) -> list[str]:
    return re.findall(r"\[\[LLM:(\w+)\]\]", template)


def _display(facts: dict[str, Any]) -> dict[str, Any]:
    out = dict(facts)
    for k, v in facts.items():
        if k.endswith("_date") and v:
            try:
                out[f"{k}_display"] = date.fromisoformat(str(v)[:10]).strftime("%d-%m-%Y")
            except ValueError:
                out[f"{k}_display"] = v
    if facts.get("amount") is not None:
        try:
            out["amount_display"] = indian_amount(float(facts["amount"]))
        except (TypeError, ValueError):
            out["amount_display"] = facts["amount"]
    return out


def indian_amount(x: float) -> str:
    """2,50,000 style grouping (lakh/crore), with paise only when present."""
    rupees, paise = divmod(round(x * 100), 100)
    s = str(rupees)
    head, tail = s[:-3], s[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    out = ",".join([*groups, tail]) if groups else tail
    return f"{out}.{paise:02d}" if paise else out


def fill(kind: str, facts: dict[str, Any], sections: dict[str, str]) -> str:
    vals = _display(facts)
    text = load(kind)
    text = re.sub(r"\{\{(\w+)\}\}", lambda m: str(vals.get(m.group(1)) or MISSING.format(m.group(1))), text)
    return re.sub(r"\[\[LLM:(\w+)\]\]", lambda m: sections.get(m.group(1), MISSING.format(m.group(1))).strip(), text)
