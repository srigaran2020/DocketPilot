"""LIME explanations of evidence selection (Ribeiro, Singh & Guestrin, KDD 2016).

DocketPilot's cross-encoder re-ranker decides which judgment passage is the best evidence for a question. LIME
explains one such decision locally: words of the chosen passage are randomly removed many times, the re-ranker scores
each perturbed passage, and a weighted linear model (samples weighted by closeness to the original) is fitted to the
scores. Its coefficients say how much each word pushed the passage up or down. Runs locally, no LLM.

    python -m docketpilot.evaluation.lime_explain          -> reports/lime.json
"""
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from docketpilot.ingestion.load import connect
from docketpilot.retrieval import search as rs
from docketpilot.retrieval.models import rerank_scores

OUT = Path(__file__).resolve().parents[2] / "reports" / "lime.json"
QUERIES = [
    "Is the presumption under Section 139 of the Negotiable Instruments Act rebuttable, and what must the accused show?",
    "Can a wife claim maintenance from her husband under more than one law at the same time?",
]
STOP = {"the", "of", "a", "an", "and", "or", "to", "in", "on", "is", "be", "by", "for", "that", "this", "it", "as", "at",
        "with", "was", "are", "has", "have", "which", "from", "its", "not", "but", "his", "her", "their", "been"}


def explain(query: str, passage: str, n_samples: int = 400, max_words: int = 90, seed: int = 7) -> dict[str, Any]:
    words = re.findall(r"\S+", passage)[:max_words]
    d = len(words)
    rng = np.random.default_rng(seed)
    masks = rng.random((n_samples, d)) > 0.3          # keep ~70% of words per sample
    masks[0] = True                                    # the original passage
    texts = [" ".join(w for w, keep in zip(words, m, strict=True) if keep) for m in masks]
    y = np.array(rerank_scores(query, texts), dtype=float)
    # LIME kernel: cosine distance to the all-ones vector, exponential kernel of width 0.25
    cos = masks.sum(1) / (np.sqrt(masks.sum(1)) * np.sqrt(d) + 1e-9)
    w = np.exp(-((1 - cos) ** 2) / 0.25 ** 2)
    x = masks.astype(float)
    xw = np.hstack([x, np.ones((n_samples, 1))]) * np.sqrt(w)[:, None]
    yw = y * np.sqrt(w)
    lam = 1.0                                          # ridge, as in LIME's default surrogate
    a = xw.T @ xw + lam * np.eye(d + 1)
    coef = np.linalg.solve(a, xw.T @ yw)
    pred = np.hstack([x, np.ones((n_samples, 1))]) @ coef
    r2 = 1 - np.sum(w * (y - pred) ** 2) / np.sum(w * (y - np.average(y, weights=w)) ** 2)
    contrib: dict[str, float] = {}
    for word, c in zip(words, coef[:d], strict=True):
        key = re.sub(r"[^\w.]", "", word).strip(".").lower()
        if key and key not in STOP:
            contrib[key] = contrib.get(key, 0.0) + float(c)
    top = sorted(contrib.items(), key=lambda kv: -abs(kv[1]))[:12]
    return {"query": query, "passage": " ".join(words), "original_score": float(y[0]), "surrogate_r2": float(r2),
            "n_samples": n_samples, "top_words": top}


def main() -> None:
    results = []
    with connect() as conn:
        for q in QUERIES:
            hit = next(h for h in rs.search(conn, q, rs.Filters(), mode="hybrid_rerank", k=5)["hits"] if h["role"] == "body")
            res = explain(q, hit["text"])
            res.update(case=hit["title"], court=hit["court"], year=hit["year"])
            results.append(res)
            print(json.dumps({"query": q[:60], "case": hit["title"][:60], "r2": round(res["surrogate_r2"], 3),
                              "top": res["top_words"][:6]}), flush=True)
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
