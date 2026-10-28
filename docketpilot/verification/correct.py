"""Auto-correction after verification: the user should not have to deal with bad citations.

  * wrong citation for a case that exists   -> replaced with the correct citation of that case
  * case not found / does not support the point / quote not in the judgment -> citation removed, and a
    sentence left with no remaining authority is removed too (an unsupported legal claim is not kept)
  * everything else stays as it is

Returns the corrected text, a short list of what changed, and a report that matches the corrected text.
"""
import re
from typing import Any

import psycopg

from docketpilot.knowledge.citations import find_citations
from docketpilot.verification.engine import resolve
from docketpilot.verification.extract import CASE_NAME, CitedItem, _clean_name, _sentence_bounds

BAD_PROPOSITION = {"contradicts", "does_not_support", "unsupported"}
BAD_QUOTE = {"not_found", "only_in_headnote"}


def _display_citation(conn: psycopg.Connection, case_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT raw FROM case_citations WHERE case_id=%s
                       ORDER BY CASE kind WHEN 'neutral' THEN 0 WHEN 'scr' THEN 1 WHEN 'hc_neutral' THEN 2 ELSE 3 END,
                                confidence DESC LIMIT 1""", (case_id,))
        r = cur.fetchone()
    return r[0] if r else None


def _short_name(title: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    m = re.search(r"\bof\s+(.*?)\s+Vs\.?\s+(.*)$", title, re.I) or re.search(r"^(.*?)\s+versus\s+(.*)$", title, re.I)
    name = f"{m.group(1).strip().title()} v. {m.group(2).strip().title()}" if m else title.title()
    return re.sub(r"\s+(And|&)\s+(Another|Others|Ors\.?|Anr\.?)\b.*$", "", name, flags=re.I)


def _fix_for(conn: psycopg.Connection, c: dict[str, Any]) -> tuple[str, str | None, str]:
    """(action, replacement, reason) for one citation result. action: keep | replace | remove."""
    prop = (c.get("proposition") or {}).get("label")
    if any(q["status"] in BAD_QUOTE for q in c.get("quotes", [])):
        return "remove", None, "the quoted words are not in that judgment"
    if prop in BAD_PROPOSITION:
        return "remove", None, "that judgment does not support the point"
    if c["verdict"] == "NOT_FOUND":
        return "remove", None, "the case could not be found"
    if c["verdict"] == "CONFLICT":
        if c.get("case_name"):  # the named case may exist under its correct citation
            cands = resolve(conn, CitedItem("x", c["case_name"], c["case_name"], None, c.get("year"), 0, 0, ""))
            if cands:
                cit = _display_citation(conn, cands[0].case_id)
                if cit:
                    return "replace", f"{c['case_name']}, {cit}", "the citation pointed to a different case"
        return "remove", None, "the citation pointed to a different case"
    if c["verdict"] == "PARTIAL" and c.get("candidates"):
        best = c["candidates"][0]
        if best.get("via") == "name_year":  # names match a real case, citation string wrong
            cit = _display_citation(conn, best["case_id"])
            if cit:
                name = c.get("case_name") or _short_name(best["title"])
                return "replace", f"{name}, {cit}", "wrong year or page in the citation"
    return "keep", None, ""


def _cleanup(text: str) -> str:
    text = re.sub(r"\(\s*[;,]?\s*\)", "", text)          # empty brackets
    text = re.sub(r"\(\s*[;,]\s*", "(", text)
    text = re.sub(r"\s*[;,]\s*\)", ")", text)
    text = re.sub(r";\s*;", ";", text)
    text = re.sub(r"[ \t]+([.,;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"^[ \t]*[-•*][ \t]*$\n?", "", text, flags=re.M)  # bullets left empty
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def autocorrect(conn: psycopg.Connection, text: str, report: dict[str, Any]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    cits = report.get("citations", [])
    plans = [(c, *_fix_for(conn, c)) for c in cits]
    removed = [c for c, a, _, _ in plans if a == "remove"]
    kept_spans = [(c["start"], c["end"]) for c, a, _, _ in plans if a != "remove"]

    # Sentences whose every citation is removed lose their claim too.
    drop: list[tuple[int, int]] = []
    for c in removed:
        s, e = _sentence_bounds(text, c["start"], c["end"])
        if not any(s <= ks < e for ks, _ in kept_spans) and (s, e) not in drop:
            drop.append((s, e))

    edits: list[tuple[int, int, str]] = [(s, e, "") for s, e in drop]
    for c, action, repl, _ in plans:
        inside_dropped = any(s <= c["start"] < e for s, e in drop)
        if action == "remove" and not inside_dropped:
            edits.append((c["start"], c["end"], ""))
        elif action == "replace" and not inside_dropped:
            edits.append((c["start"], c["end"], repl or ""))
    # apply from the end so earlier offsets stay valid; skip overlaps
    out, last_start = text, len(text) + 1
    for s, e, new in sorted(edits, key=lambda x: x[0], reverse=True):
        if e > last_start:
            continue
        out = out[:s] + new + out[e:]
        last_start = s
    out = _cleanup(out)

    changes = [{"action": a, "original": c["raw"], "replacement": r, "reason": why}
               for c, a, r, why in plans if a != "keep"]
    # Names of cases the model mentioned without any citation could not be checked: take them out too.
    kept_raws = [r if a == "replace" else c["raw"] for c, a, r, _ in plans if a != "remove"]
    out, name_changes = strip_unchecked_names(out, [x for x in kept_raws if x])
    changes += name_changes
    # Report that matches the corrected text: kept citations stay, replacements become verified entries.
    new_cits = []
    for c, a, r, why in plans:
        if a == "keep":
            new_cits.append(c)
        elif a == "replace" and r and r in out:
            new_cits.append({**c, "raw": r, "verdict": "VERIFIED", "colour": "green", "reason": f"Corrected: {why}.",
                             "proposition": c.get("proposition") if (c.get("proposition") or {}).get("label") not in BAD_PROPOSITION else None})
    statutes = report.get("statutes", [])
    red = [x for x in new_cits if x["colour"] == "red"] + [s for s in statutes if s["colour"] == "red"]
    amber = [x for x in new_cits if x["colour"] == "amber"] + [s for s in statutes if s["colour"] == "amber"]
    fixed = {**report, "citations": new_cits,
             "release": "blocked" if red else ("needs_acknowledgement" if amber else "clear"),
             "blocking_items": [x["id"] for x in red], "items_needing_acknowledgement": [x["id"] for x in amber],
             "corrections": changes, "checked": len(cits) + len(statutes)}
    return out, changes, fixed


def strip_unchecked_names(text: str, checked: list[str]) -> tuple[str, list[dict[str, Any]]]:
    """Case names written without a citation (e.g. "see *A v. B* or similar") could not be checked, so they are
    taken out: a bracketed mention is removed with its brackets; otherwise the name becomes 'a relevant judgment'."""
    changes: list[dict[str, Any]] = []
    keep = [c for c in checked if c]

    def is_checked(name: str) -> bool:
        return any(name.split(" v. ")[0].strip(" *_") in c for c in keep)

    out = text
    for m in reversed(list(CASE_NAME.finditer(text))):
        lead = len(m.group(1)) - len(_clean_name(m.group(1)))  # "See A v. B" -> the name starts at "A"
        name = m.group(0)[lead:]
        if is_checked(name):
            continue
        s, e = m.start() + lead, m.end()
        while s > 0 and text[s - 1] in "*_":  # markdown emphasis around the name
            s -= 1
        while e < len(text) and text[e] in "*_":
            e += 1
        open_ = text.rfind("(", 0, s)
        close = text.find(")", e)
        if open_ != -1 and close != -1 and text.rfind(")", open_, s) == -1 and close - open_ < 160:
            out = out[:open_] + out[close + 1:]
        else:
            out = out[:s] + "a relevant judgment" + out[e:]
        changes.append({"action": "remove", "original": name, "replacement": None,
                        "reason": "case named without a citation, so it could not be checked"})
    return _cleanup(out), changes


def has_citations(text: str) -> bool:
    return bool(find_citations(text))
