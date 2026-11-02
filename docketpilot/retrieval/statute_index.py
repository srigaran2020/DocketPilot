r"""Dense (meaning-based) index of the current Act sections, so "how to make a valid will" finds the Indian
Succession Act although it never says "valid will" in those words. Qdrant collection `statutes`, one point per
current section version (point id = section_versions.id). No AI model is called; the same small embedding model
as the judgment index runs on the laptop.

    python -m docketpilot.retrieval.statute_index            # sync: add new/changed sections, drop old versions
    python -m docketpilot.retrieval.statute_index --rebuild  # from scratch
    .venv-gpu\Scripts\python -m docketpilot.retrieval.statute_index --gpu   # much faster with an NVIDIA GPU

The weekly law update calls sync() after it changes sections.
"""
import argparse
import time
from typing import Any

import psycopg
from qdrant_client import models

from docketpilot.retrieval import models as emb
from docketpilot.retrieval.index import client

COLLECTION = "statutes"
BATCH = 64


def passage(title: str, number: str, heading: str, text: str) -> str:
    """What is embedded: the Act's name and the section heading carry most of the meaning."""
    return f"{title}. Section {number}: {heading}. {text[:1200]}"


def sync(conn: psycopg.Connection, rebuild: bool = False) -> dict[str, int]:
    qc = client()
    if rebuild and qc.collection_exists(COLLECTION):
        qc.delete_collection(COLLECTION)
    if not qc.collection_exists(COLLECTION):
        qc.create_collection(COLLECTION, vectors_config=models.VectorParams(size=emb.EMBED_DIM,
                                                                            distance=models.Distance.COSINE))
        qc.create_payload_index(COLLECTION, "act", models.PayloadSchemaType.KEYWORD)
    have: set[int] = set()
    offset = None
    while True:
        pts, offset = qc.scroll(COLLECTION, limit=2000, offset=offset, with_payload=False, with_vectors=False)
        have |= {int(p.id) for p in pts}
        if offset is None:
            break
    with conn.cursor() as cur:
        cur.execute("""SELECT sv.id, a.short_name, a.title, sv.section_number, sv.heading, sv.text
                       FROM section_versions sv JOIN acts a ON a.id = sv.act_id
                       WHERE sv.valid_to IS NULL AND length(sv.text) > 40""")
        rows = cur.fetchall()
    current = {r[0] for r in rows}
    stale: list[int | str] = sorted(have - current)
    if stale:
        qc.delete(COLLECTION, points_selector=models.PointIdsList(points=stale))
    todo = [r for r in rows if r[0] not in have]
    t0 = time.time()
    for i in range(0, len(todo), BATCH):
        part = todo[i:i + BATCH]
        vectors = emb.embed([passage(r[2], r[3], r[4], r[5]) for r in part])
        qc.upsert(COLLECTION, points=[models.PointStruct(id=r[0], vector=v, payload={"act": r[1], "section": r[3]})
                                      for r, v in zip(part, vectors, strict=True)])
        if (i // BATCH) % 20 == 0:
            print(f"  statutes: {i + len(part)}/{len(todo)} embedded ({time.time() - t0:.0f} s)", flush=True)
    return {"added": len(todo), "removed": len(stale), "total": len(current)}


def dense(query: str, k: int = 40, acts: list[str] | None = None) -> list[int]:
    """section_versions ids closest in meaning to the question (empty if the index is not built)."""
    flt = models.Filter(must=[models.FieldCondition(key="act", match=models.MatchAny(any=acts))]) if acts else None
    try:
        res = client().query_points(COLLECTION, query=emb.embed_query(query), limit=k, query_filter=flt)
    except Exception:  # index missing or Qdrant down: keyword search still works
        return []
    return [int(p.id) for p in res.points]


def main() -> None:
    from docketpilot.config import get_settings

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--gpu", action="store_true", help="embed on the GPU (needs .venv-gpu)")
    args = ap.parse_args()
    if args.gpu:
        from docketpilot.retrieval.index import use_gpu

        use_gpu()
    with psycopg.connect(get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")) as conn:
        result: dict[str, Any] = sync(conn, args.rebuild)
    print(result)


if __name__ == "__main__":
    main()
