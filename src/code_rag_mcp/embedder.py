"""Embedding abstraction layer - fastembed backend with ONNX local inference."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

_EMBED_MODEL = os.environ.get("CODE_RAG_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
_BACKEND = os.environ.get("CODE_RAG_EMBED_BACKEND", "fastembed")

_fastembed_model = None


def _get_fastembed_model():
    global _fastembed_model
    if _fastembed_model is None:
        from fastembed import TextEmbedding

        _fastembed_model = TextEmbedding(model_name=_EMBED_MODEL)
    return _fastembed_model


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed a batch of texts, returns list of float vectors."""
    if _BACKEND == "fastembed":
        model = _get_fastembed_model()
        return [vec.tolist() for vec in model.embed(texts)]
    raise ValueError(f"Unknown embed backend: {_BACKEND}")


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    if _BACKEND == "fastembed":
        model = _get_fastembed_model()
        return next(model.query_embed(query)).tolist()
    raise ValueError(f"Unknown embed backend: {_BACKEND}")
