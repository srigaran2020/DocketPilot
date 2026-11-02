"""Weekly law update: changed text keeps the old version, removed sections are closed, broken downloads are refused."""
import uuid
from datetime import date

import pytest

from docketpilot.ingestion import update_laws
from docketpilot.knowledge import statutes
from docketpilot.knowledge.statutes import ParsedSection


def _sec(number: str, text: str) -> ParsedSection:
    import hashlib
    return ParsedSection(number, "h", text, "", [], None, None, "u", hashlib.sha256(text.encode()).hexdigest())


def test_compare_finds_added_changed_removed():
    stored = {"1": [_sec("1", "same").sha256], "2": [_sec("2", "old").sha256], "3": [_sec("3", "gone").sha256]}
    fresh = {"1": [_sec("1", "same")], "2": [_sec("2", "new")], "4": [_sec("4", "brand new")]}
    assert update_laws.compare(stored, fresh) == {"added": ["4"], "changed": ["2"], "removed": ["3"]}


def _item(number: str, text: str, footnote: str = "") -> dict:
    return {"uuid": uuid.uuid4().hex, "handle": f"123/{number}", "metadata": {
        "dc.identifier.collection": ["SECTION"], "dc.identifier.section_number": [number], "dc.title": [f"Heading {number}"],
        "dc.identifier.section_page_note": [f"<p>{text}</p>"], "dc.identifier.section_footnote": [footnote]}}


@pytest.mark.integration
@pytest.mark.usefixtures("migrated_db")
def test_update_act_keeps_history(monkeypatch):
    from docketpilot.ingestion.load import connect
    from docketpilot.retrieval.search import statute_as_on

    code, short = f"TEST_{uuid.uuid4().hex[:8]}", f"T{uuid.uuid4().hex[:6]}"
    with connect() as conn:
        aid = conn.execute("INSERT INTO acts (india_code_act_id, short_name, title) VALUES (%s,%s,%s) RETURNING id",
                           (code, short, f"The {short} Act, 2020")).fetchone()[0]  # type: ignore[index]
        for n, t in (("1", "Short title and extent of this Act."), ("2", "Old wording of the penalty section."),
                     ("3", "A section that will be omitted.")):
            sec = statutes.parse_section(_item(n, t))
            assert sec is not None
            update_laws._insert(conn.cursor(), aid, sec)
        conn.commit()

        footnote = "1. Subs. by Act 5 of 2026, s. 2 (w.e.f. 1-6-2026)."
        monkeypatch.setattr(statutes, "fetch_act", lambda *_a, **_k: [
            _item("1", "Short title and extent of this Act."),
            _item("2", "<sup>1</sup>[New wording of the penalty section.]", footnote),
            _item("4", "A section inserted by the amendment."),
        ])
        r = update_laws.update_act(conn, short, code, date(2026, 11, 2))
        kinds = {(c["section"], c["kind"]) for c in r["changes"]}
        assert kinds == {("2", "changed"), ("3", "removed"), ("4", "added")}

        rows = conn.execute("SELECT section_number, text, valid_from, valid_to FROM section_versions WHERE act_id=%s "
                            "ORDER BY section_number, valid_to NULLS LAST", (aid,)).fetchall()
        s2 = [x for x in rows if x[0] == "2"]
        assert len(s2) == 2 and "Old wording" in s2[0][1] and s2[0][3] == date(2026, 6, 1)  # old kept, closed
        assert "New wording" in s2[1][1] and s2[1][3] is None and s2[1][2] == date(2026, 6, 1)
        assert [x[3] for x in rows if x[0] == "3"] == [date(2026, 11, 2)]  # removed: closed, not deleted

        # "as on" a date before the amendment now finds the stored old wording
        before = statute_as_on(conn, short, "2", date(2026, 1, 1))
        after = statute_as_on(conn, short, "2", date(2026, 7, 1))
        assert "Old wording" in str(before) and "New wording" in str(after)

        # running again with the same text changes nothing
        assert update_laws.update_act(conn, short, code, date(2026, 11, 9))["changes"] == []

        # a download with far fewer sections than stored is refused, nothing is changed
        monkeypatch.setattr(statutes, "fetch_act", lambda *_a, **_k: [_item("1", "Short title and extent of this Act.")])
        with pytest.raises(RuntimeError, match="incomplete"):
            update_laws.update_act(conn, short, code, date(2026, 11, 16))
        conn.rollback()
        conn.execute("DELETE FROM acts WHERE id=%s", (aid,))
        conn.commit()
