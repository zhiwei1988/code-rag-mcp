"""FastMCP server - stdio (Claude Code) or HTTP (avante) transport."""

from __future__ import annotations

import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("code-rag")


@mcp.tool()
def index_repo(repo_path: str, incremental: bool = True) -> dict:
    """Index or update a code repository for semantic search.

    Args:
        repo_path: Absolute or ~ path to the repository root.
        incremental: Only reindex changed files (default True).
    """
    from .indexer import index_repo as _index

    return _index(repo_path, incremental=incremental)


@mcp.tool()
def search_code(
    query: str,
    repo_path: str | None = None,
    top_k: int = 10,
    file_glob: str | None = None,
) -> list[dict]:
    """Semantic search across indexed code repositories.

    Args:
        query: Natural language or code description.
        repo_path: Restrict search to this repo (optional).
        top_k: Number of results (default 10).
        file_glob: Filter results by filename pattern e.g. '*.py'.
    """
    from .indexer import search_code as _search

    return _search(query, repo_path=repo_path, top_k=top_k, file_glob=file_glob)


@mcp.tool()
def list_indexed_repos() -> list[dict]:
    """List all indexed repositories with chunk counts."""
    from .store import list_collections

    return list_collections()


@mcp.tool()
def get_file_context(file_path: str, line_start: int, line_end: int) -> dict:
    """Return raw lines from a file (for expanding search result context).

    Args:
        file_path: Absolute path to the file.
        line_start: 1-based start line.
        line_end: 1-based end line (inclusive).
    """
    p = Path(file_path).expanduser()
    if not p.is_file():
        return {"error": f"File not found: {file_path}"}
    lines = p.read_text(errors="replace").splitlines()
    selected = lines[line_start - 1 : line_end]
    return {
        "file": str(p),
        "line_start": line_start,
        "line_end": line_end,
        "content": "\n".join(selected),
    }


@mcp.tool()
def delete_repo_index(repo_path: str) -> dict:
    """Delete the index for a repository.

    Args:
        repo_path: Path to the repository root.
    """
    from .store import delete_collection

    rp = str(Path(repo_path).expanduser().resolve())
    ok = delete_collection(rp)
    return {"deleted": ok, "repo_path": rp}


def main():
    http_mode = "--http" in sys.argv
    if http_mode:
        port = 8765
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
