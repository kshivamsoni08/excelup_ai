"""Embedding engine.

Primary: sentence-transformers `all-MiniLM-L6-v2` (384-dim), loaded locally at
startup, CPU-only. Embeddings for seed skills/postings are precomputed at seed
time; runtime embedding is only needed for live strings (resume snippets, new
postings).

Fallback: if sentence-transformers (or the model download) is unavailable, a
deterministic feature-hashing embedder is used instead. It is stable for the
same input text, needs no network, and keeps every downstream flow - matching,
retrieval, resume scanning - fully functional. All 384-dim vectors, either way,
so pgvector columns stay compatible.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Optional

logger = logging.getLogger(__name__)

DIM = 384
MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_model_failed = False
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _try_load_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(MODEL_NAME, device="cpu")
        logger.info("Loaded sentence-transformers model %s", MODEL_NAME)
    except Exception as exc:  # not installed, no weights, no net, etc.
        logger.warning(
            "sentence-transformers unavailable (%s); using deterministic "
            "hashing embedder (384-dim, stable per text).",
            exc,
        )
        _model_failed = True
        _model = None
    return _model


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder (fallback).

    Same text -> same 384-dim vector, always. Similar texts land closer together
    than dissimilar ones (shared token buckets), which is all the retrieval
    stage needs to remain sensible without the neural model.
    """

    def encode(self, text: str) -> list[float]:
        vec = [0.0] * DIM
        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vec
        for tok in tokens:
            h = int.from_bytes(hashlib.md5(tok.encode()).digest()[:8], "big")
            idx = h % DIM
            sign = 1.0 if (h >> 63) & 1 else -1.0
            # sub-buckets soften collisions
            vec[idx] += sign * 1.0
            vec[(h // DIM) % DIM] += sign * 0.5
        n = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / n for x in vec]


_hasher = HashingEmbedder()


def embed(text: str) -> list[float]:
    """Embed a single string into a 384-dim vector (model or deterministic fallback)."""
    text = (text or "").strip()
    if not text:
        return [0.0] * DIM
    model = _try_load_model()
    if model is not None:
        try:
            return [float(x) for x in model.encode(text, normalize_embeddings=True)]
        except Exception as exc:
            logger.warning("Model encode failed (%s); using hashing embedder.", exc)
    return _hasher.encode(text)


def embed_many(texts: list[str]) -> list[list[float]]:
    """Batch embed; uses the model in one batch when available."""
    cleaned = [(t or "").strip() for t in texts]
    model = _try_load_model()
    if model is not None:
        try:
            arr = model.encode(cleaned, normalize_embeddings=True, show_progress_bar=False)
            return [[float(x) for x in row] for row in arr]
        except Exception as exc:
            logger.warning("Batch encode failed (%s); falling back.", exc)
    return [_hasher.encode(t) for t in cleaned]


def embedder_status() -> dict:
    model = _try_load_model()
    return {
        "provider": "minilm" if model is not None else "hashing-fallback",
        "dim": DIM,
        "model": MODEL_NAME if model is not None else "deterministic-hashing",
    }
