"""Check AIBE practice questions against the statute store: every right answer must trace back to its section.

    python -m docketpilot.evaluation.exam_check            -> reports/exam_check.json

Uses no AI. For each generated question it re-reads the section from the database and checks that
the right option is what the section says, the wrong options are not, and options are distinct.
"""
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from docketpilot import exam
from docketpilot.knowledge.pool import kb_conn

OUT = Path("reports/exam_check.json")


def check(q: dict[str, Any], cur: Any) -> str | None:
    """None if the question is sound, else the reason it is not."""
    opts, right = q["options"], q["options"][q["answer"]]
    if len(set(opts)) != len(opts) or len(opts) != 4:
        return "options not 4 distinct"
    cur.execute("""SELECT sv.heading, sv.text, a.title FROM section_versions sv JOIN acts a ON a.id = sv.act_id
                   WHERE a.short_name = %s AND sv.section_number = %s AND sv.valid_to IS NULL""", (q["act"], q["section"]))
    rows = cur.fetchall()
    if len(rows) != 1:
        return "section not unique in store"
    heading, text, title = rows[0]
    clean = exam._clean(heading)
    if q["kind"] == "which_section":
        if right != f"Section {q['section']}" or clean not in q["question"]:
            return "answer is not the section"
        cur.execute("""SELECT count(*) FROM section_versions sv JOIN acts a ON a.id = sv.act_id WHERE sv.valid_to IS NULL
                       AND lower(trim(trailing '.' from trim(sv.heading))) = lower(%s)""", (clean,))
        if cur.fetchone()[0] != 1:
            return "heading not unique"
    elif q["kind"] == "which_heading":
        if right != clean:
            return "answer is not the heading"
    elif q["kind"] == "which_act":
        if right != title:
            return "answer is not the Act"
    elif q["kind"] == "period":
        blanked = q["question"].split("“", 1)[1].rstrip("”")
        if blanked.replace("_____", right, 1).lower() not in " ".join(text.split()).lower() and \
                blanked.replace("_____", right, 1).lower() not in text.lower():
            return "filled sentence not in section text"
        if any(blanked.replace("_____", o, 1).lower() in text.lower() for o in opts if o != right):
            return "a wrong option also fits"
    return None


def main() -> None:
    t0 = time.time()
    with kb_conn() as conn, conn.cursor() as cur:
        subjects = exam.subjects(conn)
        questions: list[dict[str, Any]] = []
        for seed in range(10):  # ten 100-question mock tests
            questions += exam.build_quiz(conn, None, 100, seed=seed)
        for kind in exam.KINDS:  # plus 200 of each kind
            questions += exam.build_quiz(conn, None, 200, kinds=[kind], seed=99)
        problems = Counter[str]()
        examples: list[dict[str, Any]] = []
        for q in questions:
            why = check(q, cur)
            if why:
                problems[why] += 1
                if len(examples) < 10:
                    examples.append({"why": why, "question": q["question"], "options": q["options"], "answer": q["answer"]})
    report = {
        "questions_checked": len(questions),
        "by_kind": dict(Counter(q["kind"] for q in questions)),
        "sound": len(questions) - sum(problems.values()),
        "problems": dict(problems), "examples": examples,
        "subjects_covered": sum(1 for s in subjects if s["sections"]), "subjects_total": len(subjects),
        "usable_sections": sum(s["sections"] for s in subjects),
        "llm_tokens_used": 0, "seconds": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "examples"}, indent=1))
    for e in examples:
        print(e)


if __name__ == "__main__":
    main()
