"""How well Ask DocketPilot handles everyday Indian-law questions -> reports/chat_eval.json.

    python -m docketpilot.evaluation.chat_eval              # retrieval only: no AI, no Groq tokens
    python -m docketpilot.evaluation.chat_eval --llm 12     # also answer the first 12 questions end to end (Groq)

Part 1 (no AI): for each question, do the statutes the chat would send to the model include an Act that governs
the topic? Questions are written the way users type them (casual, "top 10", typos), across 20 areas of law.
Part 2 (AI): the full chat (masking, retrieval, answer, verification, auto-correction) and automatic checks on the
answer the user sees: not a refusal, names an expected Act, no leaked source tags or raw asterisks, does not call
the library "your material", list questions give a list. A two-turn follow-up ("why only a few? give 10") is
included. The expected Acts are test expectations for retrieval, not legal content shown to anyone.
"""
import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from docketpilot import chat
from docketpilot.knowledge.pool import kb_conn

OUT = Path("reports/chat_eval.json")

# (question, Acts any one of which should be among the statute sources, is it a "list the laws" question)
CASES: list[tuple[str, set[str], bool]] = [
    ("talk about the top 10 best women empowerment laws", {"DV Act", "POSH Act", "Dowry Prohibition Act"}, True),
    ("which laws protect children in india", {"POCSO Act", "JJ Act", "PCMA"}, True),
    ("list the main labour laws", {"Code on Wages", "Industrial Relations Code", "Social Security Code", "OSH Code"}, True),
    ("what are the environmental protection laws", {"Environment Act", "Water Act", "Air Act"}, True),
    ("laws on cyber crime", {"IT Act"}, True),
    ("what is the punishment for murder", {"BNS"}, False),
    ("punishment for theft under new criminal law", {"BNS"}, False),
    ("how to get anticipatory bail", {"BNSS"}, False),
    ("what is the time limit to file a cheque bounce complaint", {"NI Act"}, False),
    ("can a wife claim maintenance from her husband", {"BNSS", "HAMA", "Hindu Marriage Act"}, False),
    ("grounds for divorce for hindus", {"Hindu Marriage Act"}, False),
    ("how can a muslim woman get divorce", {"DMMA", "Muslim Women Act 2019"}, False),
    ("is triple talaq illegal", {"Muslim Women Act 2019"}, False),
    ("what is domestic violence", {"DV Act"}, False),
    ("sexual harassment complaint at office internal committee", {"POSH Act"}, False),
    ("is giving dowry a crime", {"Dowry Prohibition Act", "BNS"}, False),
    ("minimum age of marriage for girls", {"PCMA", "Hindu Marriage Act", "Special Marriage Act"}, False),
    ("how to file a consumer complaint for defective product", {"Consumer Protection Act"}, False),
    ("limitation period for filing a civil suit for money", {"Limitation Act"}, False),
    ("what makes a contract void", {"Contract Act"}, False),
    ("specific performance of agreement to sell", {"Specific Relief Act"}, False),
    ("is registration of sale deed compulsory", {"Registration Act", "Transfer of Property Act"}, False),
    ("daughter's share in father's property", {"Hindu Succession Act"}, False),
    ("how to appoint an arbitrator", {"Arbitration Act"}, False),
    ("what is an RTI application and time limit for reply", {"RTI Act"}, False),
    ("punishment for drunk driving", {"Motor Vehicles Act"}, False),
    ("compensation for road accident death", {"Motor Vehicles Act"}, False),
    ("possession of drugs punishment ndps", {"NDPS Act"}, False),
    ("bribery by public servant punishment", {"PC Act", "BNS"}, False),
    ("money laundering offence", {"PMLA"}, False),
    ("insolvency of a company who can file", {"IBC"}, False),
    ("what is a confession to police admissible", {"BSA"}, False),
    ("how to get bail in a non bailable offence", {"BNSS"}, False),
    ("maintenance of senior citizen parents by children", {"Senior Citizens Act"}, False),
    ("custody of child after divorce", {"Guardians and Wards Act", "HMGA", "Hindu Marriage Act"}, False),
    ("atrocity against scheduled caste person punishment", {"SC/ST Act"}, False),
    ("copyright infringement remedy", {"Copyright Act"}, False),
    ("trademark registration", {"Trade Marks Act"}, False),
    ("builder delayed flat possession", {"RERA", "Consumer Protection Act"}, False),
    ("free legal aid who is entitled", {"Legal Services Act"}, False),
    ("defamation punishment", {"BNS"}, False),
    ("rights of persons with disabilities", {"RPwD Act"}, False),
    # added after the first round, to check the fixes generalise
    ("punishment for stalking a woman", {"BNS"}, False),
    ("can police arrest without warrant", {"BNSS"}, False),
    ("how to make a valid will", {"Indian Succession Act"}, False),
    ("what is adverse possession period", {"Limitation Act"}, False),
    ("penalty for not filing GST return", {"CGST Act"}, False),
    ("can an employer deduct salary", {"Code on Wages"}, False),
    ("maternity leave how many weeks", {"Social Security Code"}, False),
    ("gratuity eligibility", {"Social Security Code"}, False),
    ("what is a power of attorney and stamp duty", {"Stamp Act"}, False),
    ("bank recovering loan by seizing house", {"SARFAESI", "RDB Act"}, False),
    ("can a minor enter a contract", {"Contract Act"}, False),
    ("right to education of children with disability", {"RPwD Act"}, False),
    ("acid attack punishment", {"BNS"}, False),
    ("food adulteration penalty", {"FSS Act"}, False),
    ("consumer protection laws in india", {"Consumer Protection Act"}, True),
]
FOLLOW_UP = [("talk about the top 10 best women empowerment laws", "i asked for top 10, why you provided few")]

REFUSAL = re.compile(r"library has nothing|don't cover|do not cover|does not contain|do not contain|cannot (?:produce|provide|answer)|"
                     r"not (?:able|possible) to", re.I)
LEAK = re.compile(r"\b[PS]\d+\s*[-–]\s*[PS]?\d+\b|\[[PS]\d+\]|material (?:you|supplied)|you (?:supplied|provided)|your sources", re.I)
RAW_STAR = re.compile(r"(?<![*\w])\*(?!\s)[^*\n]+?\*(?![*\w])")


def retrieval() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with kb_conn() as conn:
        for q, want, listing in CASES:
            st = chat.statute_sources(conn, q, q)
            acts = [s["act"] for s in st]
            out.append({"question": q, "expected_any": sorted(want), "statutes": [f"{s['act']} s.{s['section']}" for s in st],
                        "hit": bool(want & set(acts)), "distinct_acts": len(set(acts)), "listing": listing,
                        "expected_found": sorted(want & set(acts))})
    return out


async def _ask(messages: list[dict[str, str]]) -> dict[str, Any]:
    from docketpilot.llm import get_llm

    with kb_conn() as conn:
        return await chat.answer(conn, get_llm(), messages)


def check(answer: str, want: set[str], listing: bool) -> dict[str, Any]:
    from docketpilot.knowledge.statutes import ACTS

    titles = {k: re.sub(r"^The\s+|,\s*\d{4}$", "", v[1]) for k, v in ACTS.items()}
    named = [k for k in want if titles[k].lower() in answer.lower() or k.lower() in answer.lower()]
    bullets = len(re.findall(r"^\s*[-•]\s+", answer, re.M))
    checks = {"not_refusal": not REFUSAL.search(answer[:400]), "names_expected_act": bool(named),
              "no_leaked_tags": not LEAK.search(answer), "no_raw_asterisks": not RAW_STAR.search(answer)}
    if listing:
        acts_named = sum(1 for t in titles.values() if t.lower() in answer.lower())
        checks["list_of_4_plus_acts"] = acts_named >= 4
    return {"checks": checks, "ok": all(checks.values()), "bullets": bullets, "named": named}


def answers(n: int, pick: list[int] | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for q, want, listing in ([CASES[i] for i in pick] if pick else CASES[:n]):
        t0 = time.time()
        try:
            r = asyncio.run(_ask([{"role": "user", "content": q}]))
        except Exception as e:  # rate limit or network: record and go on
            out.append({"question": q, "error": str(e)[:200]})
            continue
        out.append({"question": q, "answer": r["answer"], "seconds": round(time.time() - t0, 1),
                    "citations_checked": len(r["verification"].get("citations", [])) + len(r["verification"].get("statutes", [])),
                    **check(r["answer"], want, listing)})
        print(f"{'OK ' if out[-1]['ok'] else 'BAD'} {q}  {out[-1]['checks']}", flush=True)
    for first, second in FOLLOW_UP:
        r1 = asyncio.run(_ask([{"role": "user", "content": first}]))
        r2 = asyncio.run(_ask([{"role": "user", "content": first}, {"role": "assistant", "content": r1["answer"]},
                               {"role": "user", "content": second}]))
        c = check(r2["answer"], CASES[0][1], True)
        out.append({"question": f"{first} -> {second}", "answer": r2["answer"], **c})
        print(f"{'OK ' if c['ok'] else 'BAD'} follow-up  {c['checks']}", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", type=int, default=0, help="also answer the first N questions with the model")
    ap.add_argument("--pick", help="comma list of question numbers to answer instead of the first N")
    args = ap.parse_args()
    ret = retrieval()
    hits = sum(r["hit"] for r in ret)
    lists = [r for r in ret if r["listing"]]
    for r in ret:
        if not r["hit"]:
            print("MISS", r["question"], "->", r["statutes"])
    report: dict[str, Any] = {
        "questions": len(ret), "statute_hit": hits, "statute_hit_pct": round(100 * hits / len(ret), 1),
        "list_questions_distinct_acts_avg": round(sum(r["distinct_acts"] for r in lists) / max(len(lists), 1), 1),
        "retrieval": ret}
    if args.llm:
        a = answers(args.llm, [int(x) for x in args.pick.split(",")] if args.pick else None)
        good = [x for x in a if x.get("ok")]
        report |= {"answered": len(a), "answers_ok": len(good), "answers": a}
    OUT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("retrieval", "answers")}, indent=1))


if __name__ == "__main__":
    main()
