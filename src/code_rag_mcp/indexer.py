"""File scanning, chunking, and ChromaDB upsert with incremental support."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# --- exclusion rules ---
EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", "__pycache__",
    ".venv", "venv", ".tox", ".mypy_cache", ".ruff_cache",
    "target", "vendor", ".gradle", "Pods",
}
EXCLUDE_PATTERNS = [
    re.compile(r".*\.min\.(js|css)$"),
    re.compile(r".*\.(lock|sum)$"),
    re.compile(r".*\.(png|jpg|jpeg|gif|bmp|ico|svg|pdf|zip|tar|gz|bin|exe|so|dylib|whl|egg)$"),
]
TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
    ".java", ".kt", ".swift", ".rb", ".php", ".cs", ".lua", ".sh", ".bash",
    ".zsh", ".fish", ".vim", ".el", ".clj", ".hs", ".ml", ".ex", ".exs",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".html", ".css", ".scss", ".sass",
    ".md", ".txt", ".rst",
    ".sql",
}

CHUNK_LINES = 128
CHUNK_OVERLAP = 32


def _is_excluded(path: Path, extra_exclude_dirs: set[str] | None = None) -> bool:
    exclude = EXCLUDE_DIRS | extra_exclude_dirs if extra_exclude_dirs else EXCLUDE_DIRS
    for part in path.parts:
        if part in exclude:
            return True
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return True
    for pat in EXCLUDE_PATTERNS:
        if pat.match(path.name):
            return True
    return False


def _file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _sliding_window_chunks(lines: list[str], file_path: str) -> list[dict]:
    """Split into overlapping windows of CHUNK_LINES with CHUNK_OVERLAP."""
    chunks = []
    total = len(lines)
    step = CHUNK_LINES - CHUNK_OVERLAP
    start = 0
    while start < total:
        end = min(start + CHUNK_LINES, total)
        chunk_lines = lines[start:end]
        text = "".join(chunk_lines).strip()
        if text:
            chunks.append(
                {
                    "text": text,
                    "file": file_path,
                    "line_start": start + 1,
                    "line_end": end,
                }
            )
        if end >= total:
            break
        start += step
    return chunks


# Mapping from lang name to the installable Python module name.
# Only languages with an installed package will be available at runtime.
_LANG_MODULE_MAP: dict[str, str] = {
    "c": "tree_sitter_c",
    "cpp": "tree_sitter_cpp",
}


def _get_ts_language(lang: str):
    """Return a tree-sitter Language object for *lang*, or None if unavailable."""
    module_name = _LANG_MODULE_MAP.get(lang)
    if module_name is None:
        return None
    try:
        import importlib
        from tree_sitter import Language
        mod = importlib.import_module(module_name)
        return Language(mod.language())
    except Exception:
        return None


def _treesitter_chunks(content: str, file_path: str, lang: str) -> list[dict] | None:
    """Try tree-sitter chunking; returns None if unavailable or no nodes found."""
    language = _get_ts_language(lang)
    if language is None:
        return None
    try:
        from tree_sitter import Parser

        parser = Parser(language)
        tree = parser.parse(content.encode())

        NODE_TYPES = {
            "function_definition", "class_definition", "method_definition",
            "function_declaration", "class_declaration", "method_declaration",
            "impl_item", "fn_item",
        }

        chunks: list[dict] = []
        lines = content.splitlines(keepends=True)

        def visit(node):
            if node.type in NODE_TYPES:
                start_line = node.start_point[0]
                end_line = node.end_point[0] + 1
                text = "".join(lines[start_line:end_line]).strip()
                if text:
                    chunks.append(
                        {
                            "text": text,
                            "file": file_path,
                            "line_start": start_line + 1,
                            "line_end": end_line,
                        }
                    )
            else:
                for child in node.children:
                    visit(child)

        visit(tree.root_node)
        return chunks if chunks else None
    except Exception:
        return None


_EXT_TO_LANG = {
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hxx": "cpp",
}


def _chunk_file(file_path: str, content: str) -> list[dict]:
    ext = Path(file_path).suffix.lower()
    lang = _EXT_TO_LANG.get(ext)
    if lang:
        chunks = _treesitter_chunks(content, file_path, lang)
        if chunks:
            return chunks
    lines = content.splitlines(keepends=True)
    return _sliding_window_chunks(lines, file_path)


def _chunk_id(file_path: str, line_start: int, line_end: int, file_hash: str) -> str:
    raw = f"{file_path}:{line_start}:{line_end}:{file_hash}"
    return hashlib.sha1(raw.encode()).hexdigest()


def index_repo(
    repo_path: str,
    incremental: bool = True,
    file_glob: str | None = None,
    exclude_dirs: list[str] | None = None,
) -> dict:
    """Scan repo_path, chunk files, embed and upsert into ChromaDB."""
    from . import embedder, store

    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        return {"error": f"Not a directory: {repo_path}"}

    collection = store.get_collection(str(repo))

    # build map of existing doc ids -> metadata for incremental check
    existing: dict[str, str] = {}  # chunk_id -> file_hash stored in metadata
    if incremental:
        try:
            results = collection.get(include=["metadatas"])
            for doc_id, meta in zip(results["ids"], results["metadatas"]):
                existing[doc_id] = meta.get("file_hash", "")
        except Exception:
            pass

    # scan files
    all_files: list[Path] = []
    for f in repo.rglob("*"):
        if f.is_file() and not _is_excluded(f.relative_to(repo), set(exclude_dirs) if exclude_dirs else None):
            if file_glob:
                import fnmatch
                if not fnmatch.fnmatch(f.name, file_glob):
                    continue
            all_files.append(f)

    chunks_to_add: list[dict] = []
    ids_seen: set[str] = set()

    for file_path in all_files:
        try:
            raw = file_path.read_bytes()
            content = raw.decode("utf-8", errors="replace")
        except Exception:
            continue

        fhash = _file_hash(raw)
        rel_path = str(file_path.relative_to(repo))
        chunks = _chunk_file(rel_path, content)

        for chunk in chunks:
            cid = _chunk_id(chunk["file"], chunk["line_start"], chunk["line_end"], fhash)
            ids_seen.add(cid)
            if incremental and cid in existing:
                continue  # unchanged
            chunk["_id"] = cid
            chunk["_file_hash"] = fhash
            chunks_to_add.append(chunk)

    # delete stale ids (files removed or chunks shifted)
    stale_ids = set(existing.keys()) - ids_seen
    if stale_ids:
        collection.delete(ids=list(stale_ids))

    # embed and upsert in batches
    BATCH = 64
    added = 0
    for i in range(0, len(chunks_to_add), BATCH):
        batch = chunks_to_add[i : i + BATCH]
        texts = [c["text"] for c in batch]
        embeddings = embedder.embed_texts(texts)
        collection.upsert(
            ids=[c["_id"] for c in batch],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "file": c["file"],
                    "line_start": c["line_start"],
                    "line_end": c["line_end"],
                    "file_hash": c["_file_hash"],
                    "repo_path": str(repo),
                }
                for c in batch
            ],
        )
        added += len(batch)

    return {
        "repo_path": str(repo),
        "files_scanned": len(all_files),
        "chunks_added": added,
        "chunks_deleted": len(stale_ids),
        "total_chunks": collection.count(),
    }


def search_code(
    query: str,
    repo_path: str | None = None,
    top_k: int = 10,
    file_glob: str | None = None,
) -> list[dict]:
    """Semantic search across indexed repos."""
    from . import embedder, store

    query_vec = embedder.embed_query(query)

    where: dict | None = None
    if file_glob:
        import fnmatch

        # ChromaDB where filter is limited; we post-filter instead
        pass

    collections_to_search = []
    if repo_path:
        rp = str(Path(repo_path).expanduser().resolve())
        collections_to_search.append(store.get_collection(rp))
    else:
        for info in store.list_collections():
            col = store._get_client().get_collection(info["collection"])
            collections_to_search.append(col)

    results = []
    for col in collections_to_search:
        if col.count() == 0:
            continue
        qr = col.query(
            query_embeddings=[query_vec],
            n_results=min(top_k, col.count()),
            include=["documents", "metadatas", "distances"],
        )
        for doc, meta, dist in zip(
            qr["documents"][0], qr["metadatas"][0], qr["distances"][0]
        ):
            if file_glob:
                import fnmatch
                if not fnmatch.fnmatch(Path(meta["file"]).name, file_glob):
                    continue
            results.append(
                {
                    "file": meta["file"],
                    "line_start": meta["line_start"],
                    "line_end": meta["line_end"],
                    "repo_path": meta.get("repo_path", ""),
                    "score": round(1 - dist, 4),  # cosine similarity
                    "snippet": doc[:500],
                }
            )

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k]
