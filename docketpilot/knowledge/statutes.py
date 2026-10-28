"""Statutes from India Code (indiacode.gov.in REST API) with date validity (spec 5.5).

India Code holds only the *current* text of each section plus amendment footnotes. So:
  * a section whose whole text was inserted on date D did not exist before D;
  * the current text is valid from the latest amendment date in its footnotes;
  * any earlier wording is NOT stored, and lookups say so instead of guessing.
Everything here is status 'unverified' (decision 11).
"""
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BASE = "https://indiacode.gov.in/server/api"
UA = {"User-Agent": "DocketPilot-research/0.1 (student project)", "Accept": "application/json"}
RAW = Path(__file__).resolve().parents[2] / "data" / "raw" / "india_code"

ACTS = {  # short name -> (India Code act id, title, act number, year)
    "NI Act": ("AC_CEN_2_33_00042_00042_1523271998701", "The Negotiable Instruments Act, 1881", "26", 1881),
    "BNS": ("AC_CEN_5_23_00048_2023-45_1719292564123", "The Bharatiya Nyaya Sanhita, 2023", "45", 2023),
    "BNSS": ("AC_CEN_5_23_00049_202346_1719552320687", "The Bharatiya Nagarik Suraksha Sanhita, 2023", "46", 2023),
    "BSA": ("AC_CEN_5_23_00049_2023-47_1719292804654", "The Bharatiya Sakshya Adhiniyam, 2023", "47", 2023),
    "CPC": ("AC_CEN_3_20_00051_190805_1523340333624", "The Code of Civil Procedure, 1908", "5", 1908),
    "Contract Act": ("AC_CEN_3_20_00035_187209_1523268996428", "The Indian Contract Act, 1872", "9", 1872),
    "Specific Relief Act": ("AC_CEN_3_20_00009_196347_1517807320084", "The Specific Relief Act, 1963", "47", 1963),
    "Limitation Act": ("AC_CEN_3_20_00005_196336_1517807319297", "The Limitation Act, 1963", "36", 1963),
    "Hindu Marriage Act": ("AC_CEN_3_20_00004_195525_1517807318992", "The Hindu Marriage Act, 1955", "25", 1955),
    "Hindu Succession Act": ("AC_CEN_3_20_00027_195630_1517807324239", "The Hindu Succession Act, 1956", "30", 1956),
    "Special Marriage Act": ("AC_CEN_3_20_00019_195443_1517807321908", "The Special Marriage Act, 1954", "43", 1954),
    "DV Act": ("AC_CEN_13_14_00008_200543_1517807325788",
               "The Protection of Women from Domestic Violence Act, 2005", "43", 2005),
    "Consumer Protection Act": ("AC_CEN_21_44_00007_201935_1596441164903", "The Consumer Protection Act, 2019", "35", 2019),
    "Transfer of Property Act": ("AC_CEN_3_20_00042_188204_1523272233671", "The Transfer of Property Act, 1882", "4", 1882),
    "Arbitration Act": ("AC_CEN_3_46_00004_199626_1517807323919", "The Arbitration and Conciliation Act, 1996", "26", 1996),
    "IT Act": ("AC_CEN_45_76_00001_200021_1517807324077", "The Information Technology Act, 2000", "21", 2000),
    "Dowry Prohibition Act": ("AC_CEN_13_14_00003_196128_1517807322681", "The Dowry Prohibition Act, 1961", "28", 1961),
    "Motor Vehicles Act": ("AC_CEN_30_42_00009_198859_1517807326286", "The Motor Vehicles Act, 1988", "59", 1988),
    "Registration Act": ("AC_CEN_18_43_00004_190816_1523340837338", "The Registration Act, 1908", "16", 1908),
    "HAMA": ("AC_CEN_3_20_00015_195678_1517807320925", "The Hindu Adoptions and Maintenance Act, 1956", "78", 1956),
    "Guardians and Wards Act": ("AC_CEN_3_20_00047_189008_1523274313365", "The Guardians and Wards Act, 1890", "8", 1890),
    "Indian Succession Act": ("AC_CEN_3_20_00058_192539_1523349789879", "The Indian Succession Act, 1925", "39", 1925),
    "Companies Act": ("AC_CEN_22_29_00008_201318_1517807327856", "The Companies Act, 2013", "18", 2013),
    "IBC": ("AC_CEN_2_11_00055_201631_1517807328273", "The Insolvency and Bankruptcy Code, 2016", "31", 2016),
    "RTI Act": ("AC_CEN_26_36_00004_200522_1517807322955", "The Right to Information Act, 2005", "22", 2005),
    "POCSO Act": ("AC_CEN_13_14_00005_201232_1517807323686",
                  "The Protection of Children from Sexual Offences Act, 2012", "32", 2012),
    "NDPS Act": ("AC_CEN_2_2_00029_198561_1517807326222",
                 "The Narcotic Drugs and Psychotropic Substances Act, 1985", "61", 1985),
    "Family Courts Act": ("AC_CEN_3_3_00019_198466_1517807326692", "The Family Courts Act, 1984", "66", 1984),
    "Partnership Act": ("AC_CEN_22_0_00012_193209_1523350631460", "The Indian Partnership Act, 1932", "9", 1932),
    "Sale of Goods Act": ("AC_CEN_3_20_00059_193003_1523350185738", "The Sale of Goods Act, 1930", "3", 1930),
    "Copyright Act": ("AC_CEN_9_30_00006_195714_1517807321712", "The Copyright Act, 1957", "14", 1957),
    "Trade Marks Act": ("AC_CEN_11_60_00004_199947_1517807323972", "The Trade Marks Act, 1999", "47", 1999),
    "RERA": ("AC_CEN_17_19_00033_201616_1517807328405",
             "The Real Estate (Regulation and Development) Act, 2016", "16", 2016),
    "Commercial Courts Act": ("AC_CEN_3_46_00008_201604_1517807328347", "The Commercial Courts Act, 2015", "4", 2016),
    "PC Act": ("AC_CEN_26_36_00001_198849_1517807318890", "The Prevention of Corruption Act, 1988", "49", 1988),
}

# How each Act is written in drafts and questions -> short name. Longer names come first.
_Y = r"(?:,?\s*\d{4})?"
ACT_ALIASES: list[tuple[str, str]] = [
    (rf"Negotiable\s+Instruments\s+Act{_Y}|N\.?\s?I\.?\s?Act", "NI Act"),
    (rf"Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita{_Y}|B\.?N\.?S\.?S\.?", "BNSS"),
    (rf"Bharatiya\s+Nyaya\s+Sanhita{_Y}|B\.?N\.?S\.?", "BNS"),
    (rf"Bharatiya\s+Sakshya\s+Adhiniyam{_Y}|B\.?S\.?A\.?", "BSA"),
    (rf"Code\s+of\s+Civil\s+Procedure{_Y}|C\.?\s?P\.?\s?C\.?", "CPC"),
    (rf"(?:Indian\s+)?Contract\s+Act{_Y}", "Contract Act"),
    (rf"Specific\s+Relief\s+Act{_Y}", "Specific Relief Act"),
    (rf"Limitation\s+Act{_Y}", "Limitation Act"),
    (rf"Hindu\s+Marriage\s+Act{_Y}|H\.?\s?M\.?\s?Act", "Hindu Marriage Act"),
    (rf"Hindu\s+Succession\s+Act{_Y}", "Hindu Succession Act"),
    (rf"Special\s+Marriage\s+Act{_Y}", "Special Marriage Act"),
    (rf"(?:Protection\s+of\s+Women\s+from\s+)?Domestic\s+Violence\s+Act{_Y}|D\.?\s?V\.?\s?Act|PWDV\s+Act", "DV Act"),
    (rf"Consumer\s+Protection\s+Act{_Y}", "Consumer Protection Act"),
    (rf"Transfer\s+of\s+Property\s+Act{_Y}|T\.?\s?P\.?\s?Act", "Transfer of Property Act"),
    (rf"Arbitration\s+(?:and|&)\s+Conciliation\s+Act{_Y}|Arbitration\s+Act", "Arbitration Act"),
    (rf"Information\s+Technology\s+Act{_Y}|I\.?\s?T\.?\s?Act", "IT Act"),
    (rf"Dowry\s+Prohibition\s+Act{_Y}", "Dowry Prohibition Act"),
    (rf"Motor\s+Vehicles\s+Act{_Y}|M\.?\s?V\.?\s?Act", "Motor Vehicles Act"),
    (rf"Registration\s+Act{_Y}", "Registration Act"),
    (rf"Hindu\s+Adoptions?\s+and\s+Maintenance\s+Act{_Y}|HAMA", "HAMA"),
    (rf"Guardians?\s+and\s+Wards\s+Act{_Y}", "Guardians and Wards Act"),
    (rf"Indian\s+Succession\s+Act{_Y}", "Indian Succession Act"),
    (rf"Companies\s+Act{_Y}", "Companies Act"),
    (rf"Insolvency\s+and\s+Bankruptcy\s+Code{_Y}|I\.?B\.?C\.?", "IBC"),
    (rf"Right\s+to\s+Information\s+Act{_Y}|RTI\s+Act", "RTI Act"),
    (rf"Protection\s+of\s+Children\s+from\s+Sexual\s+Offences\s+Act{_Y}|POCSO(?:\s+Act)?", "POCSO Act"),
    (rf"Narcotic\s+Drugs\s+and\s+Psychotropic\s+Substances\s+Act{_Y}|NDPS(?:\s+Act)?", "NDPS Act"),
    (rf"Family\s+Courts\s+Act{_Y}", "Family Courts Act"),
    (rf"(?:Indian\s+)?Partnership\s+Act{_Y}", "Partnership Act"),
    (rf"Sale\s+of\s+Goods\s+Act{_Y}", "Sale of Goods Act"),
    (rf"Copyright\s+Act{_Y}", "Copyright Act"),
    (rf"Trade\s*Marks\s+Act{_Y}", "Trade Marks Act"),
    (rf"Real\s+Estate\s+\(Regulation\s+and\s+Development\)\s+Act{_Y}|RERA", "RERA"),
    (rf"Commercial\s+Courts\s+Act{_Y}", "Commercial Courts Act"),
    (rf"Prevention\s+of\s+Corruption\s+Act{_Y}|P\.?\s?C\.?\s?Act", "PC Act"),
]
_ALIAS_RES = [(re.compile(rf"\s*(?:the\s+)?(?:{p})\s*", re.I), short) for p, short in ACT_ALIASES]


def act_short_name(raw: str) -> str | None:
    """'the Hindu Marriage Act, 1955' -> 'Hindu Marriage Act'; an Act not in the store -> None."""
    for rx, short in _ALIAS_RES:
        if rx.fullmatch(raw):
            return short
    return None


def act_title(short: str) -> str:
    return ACTS[short][1] if short in ACTS else short


# ---------- fetching ----------

def _get(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:  # noqa: S310
        return json.loads(r.read())


def fetch_act(act_id: str, page_size: int = 50) -> list[dict]:
    """All items of one act, saved to data/raw/india_code/<act_id>.json (re-used if present)."""
    out_file = RAW / f"{act_id}.json"
    if out_file.exists():
        return json.loads(out_file.read_text(encoding="utf-8"))
    query = urllib.parse.quote(f'dc.identifier.act_id:"{act_id}"')
    items, page = [], 0
    while True:
        j = _get(f"{BASE}/discover/search/objects?query={query}&size={page_size}&page={page}&dsoType=ITEM")
        sr = j["_embedded"]["searchResult"]
        for o in sr["_embedded"]["objects"]:
            it = o["_embedded"]["indexableObject"]
            items.append({"uuid": it["uuid"], "handle": it.get("handle"),
                          "metadata": {k: [v["value"] for v in vs] for k, vs in it["metadata"].items()}})
        page += 1
        if page >= sr["page"]["totalPages"]:
            break
        time.sleep(1.0)  # be polite to the government server
    RAW.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return items


# ---------- parsing ----------

def html_to_text(s: str) -> str:
    s = re.sub(r"<sup>\s*\d+\s*</sup>", "", s)  # footnote markers
    s = re.sub(r"<br\s*/?>|<hr[^>]*>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()


@dataclass(frozen=True)
class Footnote:
    note: str
    action: str | None
    amending_act: str | None
    effective: date | None


_ACTION = re.compile(r"^\s*(Ins|Subs|Omitted|Added|Rep|Renumbered|Inserted|Substituted)\b", re.I)
_ACT_REF = re.compile(r"\b(Act\s+\d+\s+of\s+\d{4}|Ord\.?\s*\d+\s+of\s+\d{4})", re.I)
_WEF = re.compile(r"w\.\s*e\.\s*f\.?\s*(\d{1,2})[-./](\d{1,2})[-./](\d{4})", re.I)
_ACTION_NAMES = {"ins": "ins", "inserted": "ins", "subs": "subs", "substituted": "subs", "omitted": "omitted",
                 "added": "added", "rep": "repealed", "renumbered": "renumbered"}


def parse_footnotes(raw_html: str) -> list[Footnote]:
    notes = [html_to_text(p) for p in re.split(r"<hr[^>]*>", raw_html) if html_to_text(p)]
    out: list[Footnote] = []
    last_act: str | None = None
    for n in notes:
        n = re.sub(r"^[\d\s.]+", "", n)  # leftover footnote number and dot
        a = _ACTION.search(n)
        act_m = _ACT_REF.search(n)
        act = re.sub(r"\s+", " ", act_m.group(1)) if act_m else (last_act if "ibid" in n.lower() else None)
        last_act = act or last_act
        w = _WEF.search(n)
        eff = None
        if w:
            d, m, y = (int(x) for x in w.groups())
            try:
                eff = date(y, m, d)
            except ValueError:
                eff = None
        out.append(Footnote(n, _ACTION_NAMES.get(a.group(1).lower()) if a else None, act, eff))
    return out


@dataclass(frozen=True)
class ParsedSection:
    number: str
    heading: str
    text: str
    footnotes_raw: str
    footnotes: list[Footnote]
    inserted_on: date | None  # whole section inserted by amendment on this date
    valid_from: date | None   # current wording in force since
    source_url: str
    sha256: str


def parse_section(item: dict) -> ParsedSection | None:
    md = item["metadata"]
    if md.get("dc.identifier.collection", [""])[0] != "SECTION":
        return None
    raw_html = md.get("dc.identifier.section_page_note", [""])[0]
    foot_html = md.get("dc.identifier.section_footnote", [""])[0]
    notes = parse_footnotes(foot_html)
    # Text that opens with marker 1 + '[' means the whole section came in with footnote 1.
    whole_inserted = re.match(r"^\s*(?:<span[^>]*>\s*</span>\s*)*<sup>\s*1\s*</sup>\s*\[", raw_html) is not None
    first = notes[0] if notes else None
    inserted_on = first.effective if (whole_inserted and first and first.action in ("ins", "added")) else None
    dates = [n.effective for n in notes if n.effective]
    text = html_to_text(raw_html)
    return ParsedSection(
        number=md.get("dc.identifier.section_number", [""])[0].strip(),
        heading=md.get("dc.title", [""])[0].strip(),
        text=text,
        footnotes_raw="\n".join(n.note for n in notes),
        footnotes=notes,
        inserted_on=inserted_on,
        valid_from=max(dates) if dates else None,
        source_url=f"https://indiacode.gov.in/handle/{item.get('handle')}",
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


# ---------- "as on date" ----------

@dataclass(frozen=True)
class AsOn:
    status: str  # in_force | not_yet_in_force | earlier_version_not_stored | not_found
    message: str
    text: str | None = None


def as_on(sec: ParsedSection | None, on: date) -> AsOn:
    if sec is None:
        return AsOn("not_found", "Section not found in the statute store.")
    if sec.inserted_on and on < sec.inserted_on:
        return AsOn("not_yet_in_force",
                    f"Section {sec.number} was inserted with effect from {sec.inserted_on:%d-%m-%Y}; "
                    f"it did not exist on {on:%d-%m-%Y}.")
    if sec.valid_from is None or on >= sec.valid_from:
        return AsOn("in_force", "Current text, in force on that date (unverified).", sec.text)
    later = [f.note for f in sec.footnotes if f.effective and f.effective > on]
    return AsOn("earlier_version_not_stored",
                f"The wording on {on:%d-%m-%Y} differs from today's text; that older version is not stored. "
                f"Amendments after that date: " + " | ".join(later), None)
