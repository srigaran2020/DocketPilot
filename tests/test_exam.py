"""AIBE practice questions: built from section text only, one right answer, no AI."""
import random

from docketpilot import exam
from docketpilot.exam import Sec, find_period, make_question

TITLES = {"BNS": "The Bharatiya Nyaya Sanhita, 2023", "BNSS": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
          "BSA": "The Bharatiya Sakshya Adhiniyam, 2023", "CPC": "The Code of Civil Procedure, 1908"}
POOL = [Sec("BNS", TITLES["BNS"], str(n), h, i) for i, (n, h) in enumerate(
    [(100, "Culpable homicide."), (101, "Murder."), (102, "Culpable homicide by causing death of person other than person whose death was intended."),
     (103, "Punishment for murder."), (104, "Punishment for murder by life-convict."),
     (105, "Punishment for culpable homicide not amounting to murder.")])]
MURDER = POOL[3]


def _ask(kind: str, text: str = "", seed: int = 0) -> dict:
    q = make_question(kind, MURDER, POOL, TITLES, ["BNS"], text, "https://indiacode.nic.in/x", random.Random(seed))  # noqa: S311
    assert q is not None
    return q


def test_which_section_answer_is_the_section_itself():
    for seed in range(20):
        q = _ask("which_section", seed=seed)
        assert q["options"][q["answer"]] == "Section 103"
        assert len(set(q["options"])) == 4 and "Punishment for murder" in q["question"]
        assert "the Bharatiya Nyaya Sanhita" in q["question"] and "the The" not in q["question"]


def test_which_heading_and_which_act():
    q = _ask("which_heading")
    assert q["options"][q["answer"]] == "Punishment for murder" and len(set(q["options"])) == 4
    q = _ask("which_act")
    assert q["options"][q["answer"]] == TITLES["BNS"] and len(set(q["options"])) == 4


def test_period_blank_keeps_the_written_form():
    text = ("(1) Whoever commits murder shall be punished with death or imprisonment for life. (2) Whoever ... shall be punished "
            "with imprisonment for a term which may extend to ten years, and shall also be liable to fine.")
    blanked, number, unit = find_period(text)
    assert (number, unit) == ("ten", "years") and "_____ years" in blanked and "ten years" not in blanked
    q = _ask("period", text)
    assert q["options"][q["answer"]] == "ten"
    assert all(not o.isdigit() for o in q["options"]) and len(set(q["options"])) == 4


def test_period_needs_a_period():
    assert find_period("Nothing is an offence which is done by a child under seven.") is None
    q = make_question("period", MURDER, POOL, TITLES, ["BNS"], "no time limit here at all, none whatsoever in the text",
                      "", random.Random(1))  # noqa: S311
    assert q is None


def test_every_subject_is_listed_and_acts_belong_to_one_subject():
    assert len(exam.SUBJECTS) == 19
    acts = [a for _, al, _ in exam.SUBJECTS for a in al]
    assert len(acts) == len(set(acts))
    assert "Income-tax Act" not in acts  # replaced by the Income-tax Act, 2025, which is not loaded
