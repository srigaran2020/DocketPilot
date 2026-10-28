r"""Build the dense vector index in Qdrant from the chunks table. Resumable: only new chunks are embedded.

    python -m docketpilot.retrieval.index                       # CPU, Section 138 judgments only (decision 13)
    .venv-gpu\Scripts\python -m docketpilot.retrieval.index --gpu --scope all --collection chunks_all
                                                                # GPU: every judgment passage (decision 28)

The GPU run uses the same ONNX model as the CPU, so vectors match (cosine 0.99999994 in a spot check); the API
keeps embedding queries on the CPU.
"""
import argparse
import time

import psycopg
from qdrant_client import QdrantClient, models

from docketpilot.config import get_settings
from docketpilot.retrieval import models as emb
from docketpilot.retrieval.models import EMBED_DIM

BATCH = 256
SCOPES = {"s138": "c.is_s138 AND ch.role = 'body'", "all": "ch.role = 'body'"}


def client() -> QdrantClient:
    return QdrantClient(url=get_settings().qdrant_url, timeout=60)


def ensure_collection(qc: QdrantClient, name: str) -> None:
    if qc.collection_exists(name):
        return
    qc.create_collection(
        name,
        vectors_config=models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE, on_disk=True),
        # int8 quantisation cuts memory ~4x (spec 6.3)
        quantization_config=models.ScalarQuantization(
            scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)),
    )
    # Filters are applied inside the vector search, not after (spec 6.3)
    for field, schema in [("court_level", models.PayloadSchemaType.KEYWORD), ("role", models.PayloadSchemaType.KEYWORD),
                          ("year", models.PayloadSchemaType.INTEGER), ("is_s138", models.PayloadSchemaType.BOOL),
                          ("outcome", models.PayloadSchemaType.KEYWORD), ("chunk_id", models.PayloadSchemaType.INTEGER)]:
        qc.create_payload_index(name, field, schema)


def max_indexed_id(qc: QdrantClient, name: str) -> int:
    pts, _ = qc.scroll(name, limit=1, order_by=models.OrderBy(key="chunk_id", direction=models.Direction.DESC),
                       with_payload=["chunk_id"])
    return int(pts[0].payload["chunk_id"]) if pts and pts[0].payload else 0


def build(conn: psycopg.Connection, name: str | None = None, scope: str = "s138") -> None:
    name = name or get_settings().qdrant_collection
    where = SCOPES[scope]
    qc = client()
    ensure_collection(qc, name)
    if "chunk_id" not in (qc.get_collection(name).payload_schema or {}):
        qc.create_payload_index(name, "chunk_id", models.PayloadSchemaType.INTEGER)
    start_after = max_indexed_id(qc, name)
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM chunks ch JOIN cases c ON c.id = ch.case_id "  # noqa: S608
                    f"WHERE ch.id > %s AND {where}", (start_after,))
        todo = cur.fetchone()[0]  # type: ignore[index]
    print(f"embedding {todo} chunks into '{name}' (after id {start_after})", flush=True)
    done, t0, last = 0, time.time(), start_after
    while True:
        with conn.cursor() as cur:
            cur.execute("""SELECT ch.id, ch.text, ch.role, ch.case_id, c.court_level, c.year, c.is_s138, c.outcome
                           FROM chunks ch JOIN cases c ON c.id = ch.case_id
                           WHERE ch.id > %s AND """ + where + " ORDER BY ch.id LIMIT %s",  # noqa: S608 (constant scope)
                        (last, BATCH))
            rows = cur.fetchall()
        if not rows:
            break
        vectors = emb.embed([r[1] for r in rows])
        qc.upsert(name, points=[
            models.PointStruct(id=r[0], vector=v, payload={
                "chunk_id": r[0], "role": r[2], "case_id": str(r[3]), "court_level": r[4], "year": r[5],
                "is_s138": r[6], "outcome": r[7]})
            for r, v in zip(rows, vectors, strict=True)])
        last = rows[-1][0]
        done += len(rows)
        if done % (BATCH * 20) == 0 or done == todo:
            rate = done / (time.time() - t0)
            print(f"  {done}/{todo} ({rate:.0f}/s, ~{(todo - done) / max(rate, 1) / 60:.0f} min left)", flush=True)
    print("index: done", flush=True)


def use_gpu() -> None:
    """Swap the embedder for the CUDA build of the same model (needs the .venv-gpu environment)."""
    import onnxruntime as ort
    from fastembed import TextEmbedding

    ort.preload_dlls()
    gpu = TextEmbedding(get_settings().embed_model, cuda=True)
    emb.embedder.cache_clear()
    emb.embedder = lambda: gpu  # type: ignore[assignment]
    emb.BATCH_SIZE = 128


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--scope", choices=list(SCOPES), default="s138")
    ap.add_argument("--collection")
    args = ap.parse_args()
    if args.gpu:
        use_gpu()
    url = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(url) as conn:
        build(conn, args.collection, args.scope)


if __name__ == "__main__":
    main()
