"""Verification steps that need no database: extraction, quote matching, verdict rules."""
import pytest

from docketpilot.knowledge.citations import normalise
from docketpilot.verification.engine import Candidate, verdict
from docketpilot.verification.extract import CitedItem, extract
from docketpilot.verification.quotes import find_quote

JUDGMENT = ("The drawer of the cheque shall be presumed to have issued it for the discharge of a debt. "
            "This presumption is rebuttable, and the accused may rely on the materials submitted by the complainant.")


# ---------- Step 1: extraction ----------

def test_extracts_name_citation_quote_and_proposition():
    draft = ('In Alpha Traders v. Beta Mills, (2019) 4 SCC 197, it was held that "the presumption under this '
             'provision is rebuttable by the accused". Further text.')
    items, refs = extract(draft)
    assert len(items) == 1
    it = items[0]
    assert it.case_name == "Alpha Traders v. Beta Mills"
    assert it.citation is not None and it.citation.canonical == "2019 4 SCC 197"
    assert it.quotes == ["the presumption under this provision is rebuttable by the accused"]
    assert "it was held that" in it.proposition and "SCC" not in it.proposition
    assert refs == []


def test_proposition_spans_wrapped_lines():
    draft = ("In Alpha Traders v. Beta Mills, (2019) 4 SCC 197, the Court held that the presumption\n"
             "under Section 139 can be rebutted on a preponderance of probabilities.\n\nNext paragraph.")
    items, _ = extract(draft)
    assert "preponderance of probabilities" in items[0].proposition
    assert "Next paragraph" not in items[0].proposition


def test_grouped_citations_share_a_clean_proposition():
    draft = ("The standard is a preponderance of probabilities (Alpha Traders v. Beta Mills, 2023 INSC 51; "
             "Gamma Ltd. v. Delta Bank, (2019) 4 SCC 197).")
    items, _ = extract(draft)
    assert len(items) == 2
    for it in items:
        assert it.proposition == "The standard is a preponderance of probabilities"


def test_name_only_citation_with_year():
    items, _ = extract("As held in Gamma Ltd. v. Delta Bank (2015), the notice must be in writing.")
    assert len(items) == 1
    assert items[0].citation is None and items[0].year == 2015 and items[0].case_name == "Gamma Ltd. v. Delta Bank"


def test_citation_without_name():
    items, _ = extract("This is settled law, see 2023 INSC 123.")
    assert items[0].case_name is None and items[0].citation.kind == "neutral"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("text", "act", "section"),
    [
        ("under Section 138 of the Negotiable Instruments Act, 1881", "NI Act", "138"),
        ("u/s 138 N.I. Act", "NI Act", "138"),
        ("Section 143A of the NI Act", "NI Act", "143A"),
        ("Section 420 IPC", "IPC", "420"),
        ("Section 200 of the Code of Criminal Procedure", "Code of Criminal Procedure", "200"),
    ],
)
def test_statute_references(text, act, section):
    _, refs = extract(text)
    assert [(r.act, r.section) for r in refs] == [(act, section)]


def test_statute_quote_attached():
    _, refs = extract('Section 139 of the NI Act says: "It shall be presumed, unless the contrary is proved, that '
                      'the holder of a cheque received the cheque"')
    assert refs[0].quoted_text and refs[0].quoted_text.startswith("It shall be presumed")


# ---------- Step 5: quotes ----------

def test_quote_exact_ignoring_case_and_punctuation():
    assert find_quote("THIS presumption is rebuttable; and the accused", JUDGMENT).status == "exact"


def test_quote_exact_despite_split_words_in_pdf():
    assert find_quote("presumed to have issued it", "shall be pre sumed to have iss ued it").status == "exact"


def test_quote_near_exact_shows_diff():
    m = find_quote("This presumption is rebutable, and the accused may rely on the material submitted by the "
                   "complainant", JUDGMENT)
    assert m.status == "near_exact"
    assert m.diff


def test_quote_not_found():
    assert find_quote("the complaint must always be dismissed if notice is late", JUDGMENT).status == "not_found"


# ---------- Step 4: verdicts ----------

def item(raw: str, name: str | None) -> CitedItem:
    c = normalise(raw)
    return CitedItem("C1", raw, name, c, c.year if c else None, 0, len(raw), "proposition")


def cand(title: str, via: str = "exact", sim: float | None = 0.8, year: int = 2019) -> Candidate:
    return Candidate("id", title, "Supreme Court of India", year, None, True, sim, via)


def test_verdict_not_found():
    assert verdict(item("(2019) 4 SCC 197", "A v. B"), [])[0] == "NOT_FOUND"


def test_verdict_verified():
    assert verdict(item("[2020] 1 S.C.R. 395", "A v. B"), [cand("A versus B")])[0] == "VERIFIED"


def test_verdict_conflict_when_citation_belongs_to_other_case():
    v, reason = verdict(item("[2020] 7 S.C.R. 89", "Rajesh v. State"), [cand("Shailendra versus ED", sim=0.05)])
    assert v == "CONFLICT" and "Shailendra" in reason


def test_verdict_partial_when_matched_by_name_only():
    v, _ = verdict(item("(2019) 4 SCC 197", "A v. B"), [cand("A versus B", via="name_year", sim=0.7)])
    assert v == "PARTIAL"


def test_verdict_partial_wrong_year():
    v, reason = verdict(item("(2015) 4 SCC 197", "A v. B"), [cand("A versus B", via="name_year", year=2019)])
    assert v == "PARTIAL" and "2015" in reason


def test_verdict_alias_is_partial():
    assert verdict(item("(2019) 4 SCC 197", None), [cand("A versus B", via="alias", sim=None)])[0] == "PARTIAL"
