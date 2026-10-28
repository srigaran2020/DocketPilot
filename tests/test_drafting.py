import pytest

from docketpilot.drafting.templates import MISSING, fill, indian_amount, llm_sections, load


@pytest.mark.parametrize(("x", "s"), [(250000, "2,50,000"), (999, "999"), (1000, "1,000"), (12345678, "1,23,45,678"),
                                      (1500.5, "1,500.50")])
def test_indian_amount(x, s):
    assert indian_amount(x) == s


def test_templates_have_llm_sections():
    assert llm_sections(load("demand_notice")) == ["facts", "grounds"]
    assert llm_sections(load("complaint")) == ["facts", "grounds", "prayer"]


def test_fill_uses_facts_and_marks_missing():
    text = fill("demand_notice", {"drawer": "PERSON_1", "payee": "PERSON_2", "amount": 250000,
                                  "notice_date": "2025-07-15"}, {"facts": "F", "grounds": "G"})
    assert "PERSON_1" in text and "2,50,000" in text and "15-07-2025" in text
    assert MISSING.format("drawer_address") in text  # missing facts stay visible, never invented
    assert "[[LLM" not in text and "{{" not in text
