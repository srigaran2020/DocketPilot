import pytest

from docketpilot.api.assistant import route


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("Remind me about the hearing on 5 November", "schedule"),
        ("Schedule cross-examination for next Monday", "schedule"),
        ("Add a hearing on 2026-11-12", "schedule"),
        ("Draft a legal notice for this matter", "draft"),
        ("Please prepare the complaint", "draft"),
        ("Verify this: As held in A v. B, (2019) 4 SCC 197 ...", "verify"),
        ("Is this a real judgment? 2023 INSC 123", "verify"),
        ("Show me similar cases", "similar"),
        ("Any previous judgments on security cheques?", "similar"),
        ("What are the strengths and weaknesses of my case?", "risk"),
        ("What strategy should I use to win?", "risk"),
        ("When is the next hearing?", "dates"),
        ("What are my hearings this week?", "dates"),
        ("Show me the calendar", "dates"),
        ("When is the next hearing in HMOP 123/2025?", "dates"),
        ("Schedule the hearing date", "schedule"),
        ("Can a director be held liable for a company cheque?", "answer"),
        ("Explain Section 138 simply", "answer"),
    ],
)
def test_routes(text, intent):
    assert route(text) == intent


def test_long_pasted_text_with_citations_is_verified():
    text = ("The law is settled. " * 20) + "See (2019) 4 SCC 197 and 2023 INSC 123."
    assert route(text) == "verify"
