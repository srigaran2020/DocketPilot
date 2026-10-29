"""Chat pipeline without the database or the real LLM: masking of every turn, tag replacement, name restore."""
import asyncio
from typing import Any

import pytest

from docketpilot import chat
from docketpilot.llm import LLMResult

PASSAGE = {"chunk_id": 7, "case_id": "c1", "title": "ALPHA TRADERS versus BETA MILLS", "court": "Supreme Court of India",
           "year": 2019, "role": "body", "page": 3, "text": "The presumption is rebuttable.", "citations": ["2019INSC1"]}


class FakeLLM:
    name, model = "fake", "fake-model"

    def __init__(self) -> None:
        self.seen: list[dict[str, str]] = []

    async def complete(self, messages: list[dict[str, str]], **_: Any) -> LLMResult:
        self.seen = messages
        return LLMResult("PERSON_1 can rely on this: the presumption is rebuttable [P1][P9].", "fake-model", 1, 1, 1)


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(chat.rs, "search", lambda *a, **k: {"hits": [PASSAGE], "mode": "lexical", "notice": None})
    monkeypatch.setattr(chat.rs, "statute_as_on", lambda *a, **k: {"status": "not_found"})
    monkeypatch.setattr(chat.rs, "statute_search", lambda *a, **k: [])

    async def fake_verify(conn, text, llm, relevant_date=None):
        fake_verify.text = text
        raw = "Alpha Traders v. Beta Mills, 2019INSC1"
        cits = [{"id": "C1", "raw": raw, "case_name": "Alpha Traders v. Beta Mills", "verdict": "VERIFIED", "colour": "green",
                 "start": text.index(raw), "end": text.index(raw) + len(raw), "quotes": [], "proposition": None,
                 "candidates": [], "year": 2019}] if raw in text else []
        return {"release": "clear", "citations": cits, "statutes": []}

    monkeypatch.setattr(chat, "verify", fake_verify)
    return fake_verify


def test_every_turn_masked_and_names_restored(patched):
    llm = FakeLLM()
    msgs = [{"role": "user", "content": "Mr. Ramesh Kumar lent money."},
            {"role": "assistant", "content": "Noted, Mr. Ramesh Kumar's loan."},
            {"role": "user", "content": "Can Mr. Ramesh Kumar rely on section 139?"}]
    out = asyncio.run(chat.answer(None, llm, msgs))  # type: ignore[arg-type]
    sent = " ".join(m["content"] for m in llm.seen)
    assert "Ramesh" not in sent  # nothing identifying reaches the model, including earlier answers
    assert "PERSON_1" in sent
    assert out["answer"].startswith("Ramesh Kumar can rely")  # restored for the user
    assert "Alpha Traders v. Beta Mills, 2019INSC1" in out["answer"]  # tag replaced by a real citation
    assert "[P9]" not in out["answer"]  # unknown tag dropped
    assert "Ramesh" not in patched.text  # verification ran on the masked text
    assert [s["tag"] for s in out["sources"]] == ["P1"]


def test_swap_tags_grouping_and_odd_brackets():
    labels = {"P1": "A v. B, 2020 INSC 1", "P2": "C v. D, 2021 INSC 2"}
    out, used = chat.swap_tags("Rebuttable [P1][P2]. Also true【P1】. Unknown [P9]. Section 13(1)(ia) stays.", labels)
    assert out == ("Rebuttable (A v. B, 2020 INSC 1; C v. D, 2021 INSC 2). Also true (A v. B, 2020 INSC 1). "
                   "Unknown. Section 13(1)(ia) stays.")
    assert used == ["P1", "P2", "P1"]


def test_swap_tags_accepts_asterisk_and_paren_forms():
    labels = {"P1": "A v. B, 2020 INSC 1", "P2": "C v. D, 2021 INSC 2"}
    out, used = chat.swap_tags("In *P1* the Court held X. Also **P2** and (P1).", labels)
    assert "*P1*" not in out and "P2" not in out.replace("2021", "")
    assert "A v. B, 2020 INSC 1" in out and "C v. D, 2021 INSC 2" in out and used == ["P1", "P2", "P1"]


def test_swap_tags_accepts_spaces_inside_brackets():
    labels = {"P1": "A v. B, 2020 INSC 1", "S3": "Section 13, Hindu Marriage Act, 1955"}
    out, used = chat.swap_tags("Cruelty is a ground [ S3 ]. The court agreed [ P1 ].", labels)
    assert "[ S3 ]" not in out and "P1" not in out
    assert "Section 13, Hindu Marriage Act, 1955" in out and "A v. B, 2020 INSC 1" in out and used == ["S3", "P1"]


def test_last_message_must_be_user(patched):
    with pytest.raises(ValueError):
        asyncio.run(chat.answer(None, FakeLLM(), [{"role": "assistant", "content": "hi"}]))  # type: ignore[arg-type]
