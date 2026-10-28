"""Embedding and reranking models (fastembed / ONNX, CPU; no PyTorch download needed).

Prototype choice (docs/DECISIONS.md #12): bge-small-en-v1.5 instead of BGE-M3, and a MiniLM
cross-encoder instead of the BGE reranker -- both small enough for this laptop and link.
"""
from functools import lru_cache
from typing import Any

from docketpilot.config import get_settings

EMBED_DIM = 384
BATCH_SIZE = 32


@lru_cache
def embedder() -> Any:
    from fastembed import TextEmbedding

    return TextEmbedding(get_settings().embed_model, threads=2)


@lru_cache
def reranker() -> Any:
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(get_settings().rerank_model, threads=2)


def embed(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in embedder().embed(texts, batch_size=BATCH_SIZE)]


def embed_query(text: str) -> list[float]:
    # bge models expect this instruction prefix on queries (not on passages)
    return [float(x) for x in next(iter(embedder().query_embed([text])))]


def rerank_scores(query: str, docs: list[str]) -> list[float]:
    return [float(s) for s in reranker().rerank(query, docs, batch_size=16)]
