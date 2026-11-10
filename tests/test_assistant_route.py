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


@pytest.mark.parametrize("text", [
    "hearing date is on 15th december 2026 for this case. add it to calender",
    "add hearing date of 15th december 2026 on calender",
    "hearing on 15th december 2026",
    "next hearing 20.12.2026",
    "case is posted to 3rd Jan",
    "matter adjourned to 12/01/2027",
    "add it to my calendar",
    "put this in the diary",
    "mark 15 dec in calander",
    "note the hearing in my calendar",
    "save this date to calendar please",
    "arguments on 5th Feb 2027",
    "filing deadline is next friday",
    "client meeting tomorrow at 4",
    "hearing shifted to Dec 18",
    "the matter is listed on 2027-01-04",
])
def test_calendar_requests_however_typed(text):
    assert route(text) == "schedule"


@pytest.mark.parametrize("text", [
    "What happens if I miss the hearing on 15 December?",
    "Can the court adjourn a hearing more than 3 times?",
    "Explain the limitation period for filing a cheque bounce complaint",
    "is the accused required to appear on every date?",
    "Draft an application for adjournment of the hearing on 15 December 2026",
])
def test_questions_and_drafts_with_dates_are_not_calendar(text):
    assert route(text) != "schedule"


def test_long_pasted_text_with_citations_is_verified():
    text = ("The law is settled. " * 20) + "See (2019) 4 SCC 197 and 2023 INSC 123."
    assert route(text) == "verify"
