from docketpilot.retrieval.search import Filters, _where, rrf, ts_text


def test_short_query_kept_as_is():
    assert ts_text("dishonour of cheque") == "dishonour of cheque"


def test_long_query_becomes_or_of_words():
    q = "the presumption under section 139 is rebuttable by the accused on preponderance"
    assert ts_text(q) == " or ".join(q.split())


def test_punctuation_dropped_from_long_query():
    assert ts_text('a "b" (c) d, e; f: g.') == "a or b or c or d or e or f or g"


def test_rrf_rewards_agreement():
    fused = rrf([(1, 0.9), (2, 0.8)], [(2, 0.7), (3, 0.6)])
    assert fused[0][0] == 2


def test_where_excludes_headnotes_by_default():
    sql, args = _where(Filters(court_level="SC", year_from=2020, s138_only=True))
    assert "role <> 'headnote'" in sql and "is_s138" in sql and args == ["SC", 2020]
    sql2, _ = _where(Filters(include_headnotes=True))
    assert "headnote" not in sql2
