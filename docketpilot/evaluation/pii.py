"""Synthetic Indian-PII test set and leakage measurement (spec 10.1, 16.4). All values are generated.

Leakage rate = share of sensitive values that still appear in the redacted text (i.e. would reach the LLM).
Precision is measured on masked spans: a mask is a false hit if it covers no planted value.

    python -m docketpilot.evaluation.pii [--n 200]
"""
import argparse
import json
import random
import re
import string
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from docketpilot.privacy.redact import redact, verhoeff_digit

REPORTS = Path(__file__).resolve().parents[2] / "reports"
FIRST = ["Ramesh", "Kavitha", "Arjun", "Meenakshi", "Suresh", "Lakshmi", "Vikram", "Anitha", "Karthik", "Priya",
         "Senthil", "Deepa", "Rahul", "Fathima", "Joseph", "Gurpreet", "Venkatesh", "Shalini", "Imran", "Divya"]
LAST = ["Kumar", "Natarajan", "Reddy", "Iyer", "Sharma", "Menon", "Pillai", "Gowda", "Singh", "Rao", "Thomas"]
FIRMS = ["Sri Balaji Traders", "Kaveri Textiles Pvt. Ltd.", "Annapurna Agencies", "Coastal Exports",
         "Lakshmi Hardware Stores", "Nilgiri Tea Company"]
STREETS = ["Gandhi Road", "Anna Nagar 2nd Street", "MG Road", "Temple Street", "Lake View Colony"]
CITIES = ["Coimbatore", "Madurai", "Kochi", "Mysuru", "Warangal", "Salem", "Thrissur"]
BANKS = ["HDFC", "ICIC", "SBIN", "CNRB", "IOBA", "KVBL"]


def aadhaar(rng: random.Random) -> str:
    base = str(rng.randint(2, 9)) + "".join(rng.choice(string.digits) for _ in range(10))
    n = base + verhoeff_digit(base)
    return f"{n[:4]} {n[4:8]} {n[8:]}"


def pan(rng: random.Random) -> str:
    return ("".join(rng.choice(string.ascii_uppercase) for _ in range(3)) + "P" + rng.choice(string.ascii_uppercase)
            + "".join(rng.choice(string.digits) for _ in range(4)) + rng.choice(string.ascii_uppercase))


def make_doc(rng: random.Random) -> tuple[str, list[tuple[str, str]]]:
    p1 = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    p2 = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    father = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    firm = rng.choice(FIRMS)
    phone = f"{rng.choice('6789')}{rng.randint(100000000, 999999999)}"
    email = f"{p1.split()[0].lower()}.{rng.randint(10, 99)}@example.com"
    acct = "".join(rng.choice(string.digits) for _ in range(rng.choice([11, 12, 14])))
    ifsc = f"{rng.choice(BANKS)}0{rng.randint(100000, 999999)}"
    addr = f"No. {rng.randint(1, 300)}, {rng.choice(STREETS)}, {rng.choice(CITIES)} - {rng.randint(600001, 699999)}"
    veh = f"TN {rng.randint(1, 99):02d} {rng.choice(['AB', 'C', 'BX'])} {rng.randint(1000, 9999)}"
    aad, pn = aadhaar(rng), pan(rng)
    planted = [("PERSON", p1), ("PERSON", p2), ("PERSON", father), ("ORG", firm), ("PHONE", phone), ("EMAIL", email),
               ("BANK_ACCOUNT", acct), ("IFSC", ifsc), ("ADDRESS", addr), ("VEHICLE", veh), ("AADHAAR", aad),
               ("PAN", pn)]
    doc = rng.choice([
        f"LEGAL NOTICE under Section 138 of the Negotiable Instruments Act, 1881.\nTo: Mr. {p2}, S/o {father}, "
        f"residing at {addr}.\nMy client Mr. {p1}, proprietor of {firm}, states that you issued cheque No. "
        f"{rng.randint(100000, 999999)} drawn on A/c No. {acct} (IFSC {ifsc}) for Rs. 2,50,000 which was returned "
        f"unpaid with the memo 'Funds Insufficient'. You may contact my client on {phone} or {email}. "
        f"Your Aadhaar {aad} and PAN {pn} were furnished in the loan application. Vehicle {veh} was pledged.",
        f"COMPLAINT. The complainant {p1} ({firm}) knows the accused {p2}, son of {father}, of {addr}. "
        f"The accused gave his PAN {pn} and Aadhaar No. {aad}. The cheque was drawn on account no. {acct}, "
        f"IFSC {ifsc}. Phone: +91 {phone[:5]} {phone[5:]}. Email: {email}. The accused owns vehicle {veh}.",
    ])
    if "+91" in doc:
        planted = [(t, f"+91 {phone[:5]} {phone[5:]}" if t == "PHONE" else v) for t, v in planted]
    return doc, planted


H_FIRST = ["Balamurugan", "Revathi", "Sathish", "Nandini", "Abdul", "Gayathri", "Muthu", "Harini", "Prakash"]
H_LAST = ["Subramanian", "Krishnan", "Varghese", "Hegde", "Naidu", "Chettiar", "Bhat", "Sundaram"]
H_FIRMS = ["Ganesh Steels", "Sundaram Brothers", "Velan Cotton House", "Royal Furnishings", "Green Valley Farms"]


def make_heldout_doc(rng: random.Random) -> tuple[str, list[tuple[str, str]]]:
    """Different wording, no honorifics, names and business types the rules were NOT written for."""
    p1 = f"{rng.choice(H_FIRST)} {rng.choice(H_LAST)}"
    p2 = f"{rng.choice(H_FIRST)} {rng.choice(H_LAST)}"
    firm = rng.choice(H_FIRMS)
    phone = f"{rng.choice('6789')}{rng.randint(100000000, 999999999)}"
    acct = "".join(rng.choice(string.digits) for _ in range(12))
    aad = aadhaar(rng)
    planted = [("PERSON", p1), ("PERSON", p2), ("ORG", firm), ("PHONE", phone), ("BANK_ACCOUNT", acct),
               ("AADHAAR", aad)]
    doc = (f"{p1} runs {firm} in {rng.choice(CITIES)}. In March he lent money to {p2}, who later handed over a "
           f"cheque from his savings account {acct}. When it bounced, {p1} called {p2} at {phone} several times. "
           f"{p2}'s Aadhaar ({aad}) is on the loan papers.")
    return doc, planted


def _present(value: str, text: str) -> bool:
    return re.sub(r"\s+", "", value).lower() in re.sub(r"\s+", "", text).lower()


def evaluate(n: int, seed: int, use_ner: bool = True, heldout: bool = False) -> dict[str, Any]:
    rng = random.Random(seed)
    per_type: dict[str, list[bool]] = defaultdict(list)
    masked = false_hits = 0
    examples = []
    for i in range(n):
        doc, planted = make_heldout_doc(rng) if heldout else make_doc(rng)
        red = redact(doc, use_ner=use_ner)
        for typ, value in planted:
            per_type[typ].append(not _present(value, red.text))
        for e in red.entities:
            masked += 1
            if not any(_present(e.value, v) or _present(v, e.value) for _, v in planted):
                false_hits += 1
        if i < 2:
            examples.append({"original": doc, "redacted": red.text})
    total = sum(len(v) for v in per_type.values())
    caught = sum(sum(v) for v in per_type.values())
    return {
        "per_type_recall": {t: round(sum(v) / len(v), 3) for t, v in sorted(per_type.items())},
        "recall": round(caught / total, 4), "leakage_rate": round(1 - caught / total, 4),
        "precision": round((masked - false_hits) / masked, 4) if masked else 0.0,
        "planted_values": total, "masks": masked, "false_masks": false_hits, "examples": examples,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    result = {"benchmark": "synthetic_indian_pii_v1", "run_at": datetime.now(UTC).isoformat(), "seed": args.seed,
              "docs": args.n, "with_ner": evaluate(args.n, args.seed, True),
              "rules_only": evaluate(args.n, args.seed, False),
              "heldout_with_ner": evaluate(args.n, args.seed + 1, True, heldout=True),
              "note": "with_ner/rules_only use templates the rules were tuned on (optimistic). "
                      "heldout_with_ner uses unseen wording and names: report this as the realistic figure."}
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "pii.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    for k in ("with_ner", "rules_only", "heldout_with_ner"):
        r = result[k]
        print(k, "| recall", r["recall"], "| leakage", r["leakage_rate"], "| precision", r["precision"])
        print("   ", r["per_type_recall"])


if __name__ == "__main__":
    main()
