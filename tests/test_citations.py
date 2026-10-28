import pytest

from docketpilot.knowledge.citations import find_citations, normalise, sentence_around, signal_for


@pytest.mark.parametrize(
    ("raw", "kind", "canonical"),
    [
        ("2023 INSC 123", "neutral", "2023 INSC 123"),
        ("2011INSC759", "neutral", "2011 INSC 759"),
        ("2023 insc 0045", "neutral", "2023 INSC 45"),
        ("2023:DHC:2651-DB", "hc_neutral", "2023:DHC:2651-DB"),
        ("2024:KER:12345", "hc_neutral", "2024:KER:12345"),
        ("[2022] 7 S.C.R. 557", "scr", "2022 7 SCR 557"),
        ("[1963] SUPP. 1 S.C.R. 539", "scr", "1963 SUPP 1 SCR 539"),
        ("(2022) 7 SCR 557", "scr", "2022 7 SCR 557"),
        ("(2019) 4 SCC 197", "scc", "2019 4 SCC 197"),
        ("(2019) 4 S.C.C. 197", "scc", "2019 4 SCC 197"),
        ("2019 SCC OnLine SC 123", "scc_online", "2019 SCC ONLINE SC 123"),
        ("2021 SCC Online Ker 456", "scc_online", "2021 SCC ONLINE KER 456"),
        ("AIR 1999 SC 1234", "air", "AIR 1999 SC 1234"),
        ("A.I.R. 1999 S.C. 1234", "air", "AIR 1999 SC 1234"),
        ("AIR 2005 Mad 77", "air", "AIR 2005 MAD 77"),
        ("2005 Cri LJ 123", "crlj", "2005 CRLJ 123"),
        ("2005 Cr.L.J. 123", "crlj", "2005 CRLJ 123"),
        ("(2005) CrLJ 123", "crlj", "2005 CRLJ 123"),
    ],
)
def test_normalise_formats(raw, kind, canonical):
    c = normalise(raw)
    assert c is not None
    assert (c.kind, c.canonical) == (kind, canonical)
    assert c.raw.strip() == raw.strip() or raw in c.raw or c.raw in raw


@pytest.mark.parametrize("raw", ["Section 138", "Rs. 2,50,000", "1881", "page 197", "SCC", "2023 INSC"])
def test_non_citations_rejected(raw):
    assert normalise(raw) is None


def test_finds_parallel_citations_in_order():
    text = ("In Dashrath Rupsingh Rathod v. State of Maharashtra, (2014) 9 SCC 129 : 2014 INSC 520, "
            "this Court held ... see also AIR 1999 SC 1234.")
    found = find_citations(text)
    assert [c.kind for c in found] == ["scc", "neutral", "air"]
    assert text[found[0].start:found[0].end] == found[0].raw


def test_scc_online_not_also_matched_as_other_kinds():
    found = find_citations("2019 SCC OnLine SC 123")
    assert len(found) == 1 and found[0].kind == "scc_online"


def test_years_carry_through():
    assert normalise("(2019) 4 SCC 197").year == 2019  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("sentence", "signal"),
    [
        ("The decision in X was overruled by a larger Bench.", "overruled"),
        ("We are unable to follow it as it was rendered per incuriam.", "per_incuriam"),
        ("The facts are clearly distinguishable.", "distinguished"),
        ("We have relied upon the judgment in X.", "relied"),
        ("This view was followed in Y.", "followed"),
        ("See X.", "cited"),
    ],
)
def test_signals(sentence, signal):
    assert signal_for(sentence) == signal


def test_sentence_around_returns_containing_sentence():
    text = "First sentence here. The ratio in (2019) 4 SCC 197 was followed. Last one."
    c = find_citations(text)[0]
    assert sentence_around(text, c.start, c.end) == "The ratio in (2019) 4 SCC 197 was followed."
