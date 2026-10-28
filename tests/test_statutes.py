"""Statute parsing and 'as on date' lookups, on HTML shaped like India Code's records."""
from datetime import date

import pytest

from docketpilot.knowledge.statutes import as_on, html_to_text, parse_footnotes, parse_section

S138_HTML = ('<span style="margin-left: 15px;"></span><sup>1</sup>[Where any cheque drawn ... imprisonment for '
             '<sup>2</sup>[a term which may be extended to two years] ...<br/><hr/> (b) ... within '
             '<sup>3</sup>[thirty days] of the receipt of information')
S138_NOTES = ('<sup>1</sup>. Ins. by Act 66 of 1988, s, 4 (w.e.f. 1-4-1989).<br/><hr/> '
              '<sup>2</sup>. Subs. by Act 55 of 2002, s.7, for certain words (w.e.f. 6-2-2003).<br/><hr/> '
              '<sup>3</sup>. Subs. by s. 7, ibid., for within fifteen days (w.e.f. 6-2-2003).<br/><hr/>')


def item(number: str, text_html: str, notes_html: str, collection: str = "SECTION") -> dict:
    return {"uuid": "u", "handle": "123/456", "metadata": {
        "dc.identifier.collection": [collection], "dc.identifier.section_number": [number],
        "dc.title": [f"Heading {number}."], "dc.identifier.section_page_note": [text_html],
        "dc.identifier.section_footnote": [notes_html]}}


@pytest.fixture
def s138():
    sec = parse_section(item("138", S138_HTML, S138_NOTES))
    assert sec is not None
    return sec


def test_footnotes_parsed_with_ibid(s138):
    assert [(f.action, f.amending_act, f.effective) for f in s138.footnotes] == [
        ("ins", "Act 66 of 1988", date(1989, 4, 1)),
        ("subs", "Act 55 of 2002", date(2003, 2, 6)),
        ("subs", "Act 55 of 2002", date(2003, 2, 6)),  # 'ibid.' carries the previous Act
    ]


def test_text_has_no_markup_or_footnote_numbers(s138):
    assert "<" not in s138.text and "sup" not in s138.text
    assert "[a term which may be extended to two years]" in s138.text
    assert "\n" in s138.text  # <br/> becomes a line break


def test_whole_section_insertion_detected(s138):
    assert s138.inserted_on == date(1989, 4, 1)
    assert s138.valid_from == date(2003, 2, 6)


@pytest.mark.parametrize(
    ("on", "status"),
    [
        (date(1989, 3, 31), "not_yet_in_force"),          # day before insertion
        (date(1989, 4, 1), "earlier_version_not_stored"),  # inserted, but old wording
        (date(2003, 2, 5), "earlier_version_not_stored"),  # day before 2002 Act took effect
        (date(2003, 2, 6), "in_force"),                    # amendment day
        (date(2024, 7, 1), "in_force"),
    ],
)
def test_as_on_amendment_boundaries(s138, on, status):
    assert as_on(s138, on).status == status


def test_in_force_returns_text_and_older_does_not(s138):
    assert as_on(s138, date(2010, 1, 1)).text == s138.text
    old = as_on(s138, date(1995, 1, 1))
    assert old.text is None
    assert "Act 55 of 2002" in old.message


def test_section_without_footnotes_always_in_force():
    sec = parse_section(item("139", "It shall be presumed ...", ""))
    assert sec is not None and sec.valid_from is None and sec.inserted_on is None
    assert as_on(sec, date(1950, 1, 1)).status == "in_force"


def test_partial_insertion_is_not_whole_section():
    sec = parse_section(item("142", "Notwithstanding ... <sup>1</sup>[(c) ...]",
                             "<sup>1</sup>. Ins. by Act 55 of 2002, s. 9 (w.e.f. 6-2-2003)."))
    assert sec is not None and sec.inserted_on is None
    assert as_on(sec, date(2000, 1, 1)).status == "earlier_version_not_stored"


def test_missing_section_and_non_section_items():
    assert as_on(None, date(2020, 1, 1)).status == "not_found"
    assert parse_section(item("1", "x", "", collection="SCHEDULE")) is None


def test_bad_date_in_footnote_is_ignored():
    notes = parse_footnotes("<sup>1</sup>. Ins. by Act 1 of 2000 (w.e.f. 31-2-2000).")
    assert notes[0].effective is None and notes[0].action == "ins"


def test_html_to_text_unescapes():
    assert html_to_text("a&amp;b&nbsp;c<br/>d") == "a&b c\nd"
