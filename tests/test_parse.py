from docketpilot.knowledge.parse import chunk, clean, is_s138, outcome, split_headnote

SCR_SAMPLE = """A
B
557
SYNTHETIC PETITIONER
v.
SYNTHETIC RESPONDENT
Negotiable Instruments Act, 1881: s.138 - Dishonour of cheque - held: ...
C
HELD: 1.1 The complaint was within time.
558 SUPREME COURT REPORTS [2022] 7 S.C.R.
CRIMINAL APPELLATE JURISDICTION: Criminal Appeal No. 1 of 2022.
The Judgment of the Court was delivered by
SYNTHETIC JUDGE, J.
1. The appellant issued a cheque which was dishonoured. The appeal is allowed."""


def test_clean_removes_margin_letters_page_numbers_and_headers():
    out = clean(SCR_SAMPLE)
    lines = out.splitlines()
    assert "A" not in lines and "B" not in lines and "C" not in lines
    assert "557" not in lines
    assert "SUPREME COURT REPORTS" not in out
    assert "SYNTHETIC PETITIONER" in out


def test_clean_joins_hyphenated_line_breaks_and_keeps_pages():
    out = clean("the com-\nplaint was filed\fsecond page")
    assert "complaint" in out
    assert out.count("\f") == 1


def test_headnote_split_at_delivered_by():
    text = clean(SCR_SAMPLE)
    segs = split_headnote(text, is_scr=True)
    assert [s.role for s in segs] == ["headnote", "body"]
    assert "HELD" in segs[0].text
    assert "HELD" not in segs[1].text
    assert segs[1].text.lstrip().startswith("SYNTHETIC JUDGE")


def test_no_headnote_split_for_high_court_text():
    segs = split_headnote("IN THE HIGH COURT ... The petition is dismissed.", is_scr=False)
    assert [s.role for s in segs] == ["body"]


def test_no_marker_means_all_body():
    segs = split_headnote("Old judgment with no marker at all.", is_scr=True)
    assert [s.role for s in segs] == ["body"]


def test_chunks_respect_segments_and_track_pages():
    text = ("Headnote words. " * 30) + "\f" + ("Body sentence here. " * 200)
    segs = split_headnote(text, is_scr=False)
    chunks = chunk(text, segs, size=500, overlap=50)
    assert all(c.role == "body" for c in chunks)
    assert chunks[0].page == 1 and chunks[-1].page == 2
    assert all(len(c.text) <= 500 for c in chunks)
    covered = set()
    for c in chunks:
        covered.update(range(c.start, c.end))
    assert len(covered) >= len(text) - 60


def test_is_s138():
    assert is_s138("complaint under Section 138 of the Negotiable Instruments Act ... offence u/s 138")
    assert not is_s138("Section 138 of the Electricity Act")  # one mention, no cheque/NI wording
    assert not is_s138("The cheque was lost.")


def test_outcome_prefers_metadata():
    assert outcome("whatever", "Appeal(s) allowed") == ("allowed", 0.95)


def test_outcome_rules_and_unknown():
    assert outcome("... For the reasons stated, the revision petition is dismissed.") == ("dismissed", 0.7)
    assert outcome("... The accused is acquitted of the charge.")[0] == "acquitted"
    assert outcome("Heard. List after two weeks.") == ("unknown", 0.0)


def test_conflicting_outcome_has_low_confidence():
    label, conf = outcome("The appeal is allowed. The complaint is dismissed.")
    assert conf < 0.5
