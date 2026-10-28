"""General-purpose pieces without the database: Act names, section references, routing, size budgets."""
import pytest

from docketpilot import chat
from docketpilot.api.assistant import doc_type_of, route
from docketpilot.knowledge.statutes import ACTS, act_short_name
from docketpilot.llm import head_tail
from docketpilot.verification.extract import extract


@pytest.mark.parametrize(("raw", "short"), [
    ("Hindu Marriage Act, 1955", "Hindu Marriage Act"), ("the BNS", "BNS"), ("B.N.S.S.", "BNSS"), ("CPC", "CPC"),
    ("N.I. Act", "NI Act"), ("Indian Contract Act", "Contract Act"), ("Arbitration and Conciliation Act, 1996", "Arbitration Act"),
    ("POCSO", "POCSO Act"), ("Domestic Violence Act", "DV Act"), ("IPC", None), ("Foo Act", None),
])
def test_act_names(raw, short):
    assert act_short_name(raw) == short


def test_every_alias_points_to_a_stored_act():
    from docketpilot.knowledge.statutes import ACT_ALIASES

    assert {short for _, short in ACT_ALIASES} <= set(ACTS)


def test_section_references_across_acts():
    text = ("Under Section 13(1)(ia) of the Hindu Marriage Act, 1955 cruelty is a ground. u/s 302 IPC. "
            "Section 483 BNSS gives bail. Section 9, CPC. Section 10 of the Indian Contract Act. Section 3 of the Foo Act.")
    refs = [(r.section, r.act) for r in extract(text)[1]]
    assert refs == [("13", "Hindu Marriage Act"), ("302", "IPC"), ("483", "BNSS"), ("9", "CPC"), ("10", "Contract Act")]


@pytest.mark.parametrize(("text", "kind"), [
    ("Draft a bail application for my client arrested under Section 303 BNS", "Bail application"),
    ("Please draft divorce petition under section 13 of the Hindu Marriage Act", "Divorce petition"),
    ("prepare a reply to the legal notice dated 5 May", "Reply"),
    ("write a written statement in the suit", "Written statement"),
])
def test_any_document_routes_to_drafting(text, kind):
    assert route(text) == "draft"
    assert doc_type_of(text) == kind


def test_questions_are_not_drafts():
    assert route("What must be proved for divorce on the ground of cruelty?") == "answer"


def test_sources_fit_the_groq_request_limit():
    passages = [{"tag": f"P{i}", "text": "x" * 1400} for i in range(6)]
    statutes = [{"tag": f"S{i}", "text": "y" * 6000} for i in range(7)]
    p, s = chat.fit_sources(passages, statutes, 16_000)
    assert sum(len(x["text"]) for x in p + s) <= 16_000
    assert len(s) == 5 and p  # statutes are trimmed before passages are dropped
    assert statutes[0]["text"] == "y" * 6000  # inputs are not modified


def test_long_paper_keeps_head_and_tail():
    text = "HEAD " + "m" * 50_000 + " TAIL"
    out = head_tail(text, 18_000)
    assert out.startswith("HEAD") and out.endswith("TAIL") and len(out) < 18_100


def test_statute_label():
    assert chat.statute_label({"section": "13", "act_title": "The Hindu Marriage Act, 1955"}) == "Section 13, Hindu Marriage Act, 1955"
