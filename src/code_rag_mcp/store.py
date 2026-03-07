"""ChromaDB persistent store management."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import chromadb

_CHROMA_DIR = Path(
    os.environ.get(
        "CODE_RAG_CHROMA_DIR",
        Path.home() / ".local/share/code-rag/chroma",
    )
)

_client: chromadb.PersistentClient | None = None


def _get_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
    return _client


def _repo_collection_name(repo_path: str) -> str:
    """Stable short collection name derived from repo path."""
    digest = hashlib.sha1(repo_path.encode()).hexdigest()[:8]
    # ChromaDB requires [a-z0-9_-], max 63 chars
    safe = Path(repo_path).name.lower().replace(" ", "_")[:40]
    return f"repo_{safe}_{digest}"


def get_collection(repo_path: str) -> chromadb.Collection:
    client = _get_client()
    name = _repo_collection_name(repo_path)
    return client.get_or_create_collection(
        name=name,
        metadata={"repo_path": repo_path, "hnsw:space": "cosine"},
    )


def delete_collection(repo_path: str) -> bool:
    client = _get_client()
    name = _repo_collection_name(repo_path)
    try:
        client.delete_collection(name)
        return True
    except Exception:
        return False


def list_collections() -> list[dict]:
    """Return metadata for all indexed repos."""
    client = _get_client()
    result = []
    for col in client.list_collections():
        meta = col.metadata or {}
        count = col.count()
        result.append(
            {
                "collection": col.name,
                "repo_path": meta.get("repo_path", "unknown"),
                "chunk_count": count,
            }
        )
    return result
