"""Knowledge-base composition from the live stores -> reports/kb_composition.json (for the paper and its figure).

    python -m docketpilot.evaluation.kb_stats
"""
import json
import urllib.request
from pathlib import Path

from docketpilot.config import get_settings
from docketpilot.ingestion.load import connect

OUT = Path(__file__).resolve().parents[2] / "reports" / "kb_composition.json"
BENCH = {"hc_cis_mas": "Madras", "mdubench": "Madras\n(Madurai)", "highcourtofkerala": "Kerala", "karnataka_bng_old": "Karnataka",
         "taphc": "Telangana"}


def main() -> None:
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*), count(*) FILTER (WHERE has_text) FROM cases")
        cases, with_text = cur.fetchone()  # type: ignore[misc]
        cur.execute("SELECT court_level, bench, count(*) FROM cases WHERE has_text GROUP BY 1, 2")
        by: dict[str, int] = {}
        for level, bench, n in cur.fetchall():
            label = "Supreme\nCourt" if level == "SC" else BENCH.get(bench or "", bench or "Other HC")
            by[label] = by.get(label, 0) + n
        cur.execute("SELECT count(*) FROM chunks")
        chunks = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("SELECT count(*) FROM acts")
        acts = cur.fetchone()[0]  # type: ignore[index]
        cur.execute("SELECT count(*) FROM section_versions")
        sections = cur.fetchone()[0]  # type: ignore[index]
    s = get_settings()
    vectors = json.loads(urllib.request.urlopen(f"{s.qdrant_url}/collections/{s.qdrant_collection}").read())["result"]["points_count"]  # noqa: S310
    order = ["Supreme\nCourt"] + sorted((k for k in by if k != "Supreme\nCourt"), key=lambda k: -by[k])
    out = {"cases_total": cases, "judgments_total": with_text, "judgments_by_court": {k: by[k] for k in order},
           "chunks": chunks, "vectors": vectors, "acts": acts, "sections": sections}
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out))


if __name__ == "__main__":
    main()
