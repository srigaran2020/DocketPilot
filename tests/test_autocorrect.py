"""Auto-correction on synthetic verification reports (no database: resolve/display lookups are patched)."""
import pytest

from docketpilot.verification import correct
from docketpilot.verification.engine import Candidate


def cite(text, raw, verdict="VERIFIED", colour="green", prop=None, quotes=(), name=None, cands=()):
    s = text.index(raw)
    return {"id": "C", "raw": raw, "case_name": name, "verdict": verdict, "colour": colour, "start": s, "end": s + len(raw),
            "proposition": {"label": prop} if prop else None, "quotes": list(quotes), "candidates": list(cands), "year": None}


@pytest.fixture(autouse=True)
def no_db(monkeypatch):
    monkeypatch.setattr(correct, "_display_citation", lambda conn, cid: "2010 INSC 99")
    monkeypatch.setattr(correct, "resolve", lambda conn, item: [Candidate("real", "REAL versus CASE", "SC", 2010, None, True, 0.9, "name_year")])


def test_unsupported_citation_removed_with_its_sentence():
    text = "The presumption is rebuttable (Good v. Case, 2020 INSC 1). Divorce needs cruelty (Wrong v. Case, 2019 INSC 5). End."
    rep = {"citations": [cite(text, "Good v. Case, 2020 INSC 1"),
                         cite(text, "Wrong v. Case, 2019 INSC 5", colour="red", prop="does_not_support")], "statutes": []}
    out, changes, fixed = correct.autocorrect(None, text, rep)
    assert "Divorce needs cruelty" not in out and "Wrong v. Case" not in out
    assert "The presumption is rebuttable (Good v. Case, 2020 INSC 1)." in out
    assert changes[0]["action"] == "remove" and fixed["release"] == "clear"


def test_grouped_citation_only_bad_one_removed():
    text = "Notice must be in writing (Good v. Case, 2020 INSC 1; Bad v. Case, 2019 INSC 5)."
    rep = {"citations": [cite(text, "Good v. Case, 2020 INSC 1"),
                         cite(text, "Bad v. Case, 2019 INSC 5", verdict="NOT_FOUND", colour="amber")], "statutes": []}
    out, _, _ = correct.autocorrect(None, text, rep)
    assert out == "Notice must be in writing (Good v. Case, 2020 INSC 1)."


def test_wrong_citation_for_real_case_is_replaced():
    text = "As held in Real v. Case, [2015] 3 S.C.R. 1, notice is needed."
    c = cite(text, "Real v. Case, [2015] 3 S.C.R. 1", verdict="PARTIAL", colour="amber", name="Real v. Case",
             cands=[{"case_id": "real", "title": "REAL versus CASE", "via": "name_year"}])
    out, changes, fixed = correct.autocorrect(None, text, {"citations": [c], "statutes": []})
    assert out == "As held in Real v. Case, 2010 INSC 99, notice is needed."
    assert changes[0]["action"] == "replace" and fixed["citations"][0]["colour"] == "green"


def test_conflict_replaced_when_named_case_exists():
    text = "See Real v. Case, [2020] 7 S.C.R. 89 on this."
    c = cite(text, "Real v. Case, [2020] 7 S.C.R. 89", verdict="CONFLICT", colour="red", name="Real v. Case")
    out, _, fixed = correct.autocorrect(None, text, {"citations": [c], "statutes": []})
    assert "Real v. Case, 2010 INSC 99" in out and fixed["release"] == "clear"


def test_bullet_with_bad_citation_disappears():
    text = "**Strengths**\n- Debt is proved (Good v. Case, 2020 INSC 1).\n- Cruelty shown (Bad v. Case, 2019 INSC 5).\n- Notice served."
    rep = {"citations": [cite(text, "Good v. Case, 2020 INSC 1"),
                         cite(text, "Bad v. Case, 2019 INSC 5", colour="red", prop="unsupported")], "statutes": []}
    out, _, _ = correct.autocorrect(None, text, rep)
    assert "Cruelty shown" not in out and "- Notice served." in out and "- Debt is proved" in out


def test_case_named_from_memory_is_removed():
    text = ("Cruelty must be proved (Good v. Case, 2020 INSC 1).\n\n**What to do next**\n"
            "- Look up precedent on cruelty (e.g., *V. Muthulakshmi v. M. Raghunathan* or similar).\n"
            "- Read Ravi Kumar v. State Of Kerala for the standard.")
    rep = {"citations": [cite(text, "Good v. Case, 2020 INSC 1")], "statutes": []}
    out, changes, _ = correct.autocorrect(None, text, rep)
    assert "Muthulakshmi" not in out and "Ravi Kumar" not in out
    assert "Good v. Case, 2020 INSC 1" in out  # the checked citation stays
    assert "- Look up precedent on cruelty." in out and "a relevant judgment" in out
    assert {c["original"] for c in changes} == {"V. Muthulakshmi v. M. Raghunathan", "Ravi Kumar v. State Of Kerala"}


def test_clean_answer_untouched():
    text = "The presumption is rebuttable (Good v. Case, 2020 INSC 1)."
    out, changes, _ = correct.autocorrect(None, text, {"citations": [cite(text, "Good v. Case, 2020 INSC 1")], "statutes": []})
    assert out == text and changes == []
