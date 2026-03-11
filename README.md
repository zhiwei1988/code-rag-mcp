# code-rag-mcp

A Model Context Protocol (MCP) server that indexes code repositories and exposes semantic search as tools for AI assistants like Claude.

## How it works

```
Source Files
    │
    ▼
File Scanner (indexer.py)
    │  filter by extension / exclusion rules / file size limit (2 MB)
    ▼
Chunker
    │  tree-sitter (function/class level, supported languages only)
    ▼
Embedder (fastembed + BAAI/bge-small-en-v1.5, local ONNX)
    │  batch embed + upsert with retry (3 attempts)
    ▼
ChromaDB (persistent, one collection per repo)
    │
    ▼
MCP Tools (stdio or HTTP transport)
```

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

**Option 1 — run directly with `uvx` (no install, recommended once published to PyPI):**

```bash
uvx code-rag-mcp
```

**Option 2 — local development install:**

```bash
git clone https://github.com/yourname/code-rag-mcp.git
cd code-rag-mcp
uv sync
uv run code-rag-mcp
```

## MCP Client Configuration

### stdio (Claude Desktop / Cursor)

Add to your MCP config (`claude_desktop_config.json` or `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "code-rag": {
      "command": "uvx",
      "args": ["code-rag-mcp"]
    }
  }
}
```

For a local install, replace `"uvx"` with the full path to the installed `code-rag-mcp` binary, or use `uv run`:

```json
{
  "mcpServers": {
    "code-rag": {
      "command": "uv",
      "args": ["--directory", "/path/to/code-rag-mcp", "run", "code-rag-mcp"]
    }
  }
}
```

### HTTP (avante / other HTTP clients)

```bash
code-rag-mcp --http --port 8765
```

```json
{
  "mcpServers": {
    "code-rag": {
      "url": "http://localhost:8765/mcp"
    }
  }
}
```

## Available Tools

| Tool | Description |
|---|---|
| `index_repo` | Index or incrementally update a repository. |
| `search_code` | Semantic search across indexed repositories. |
| `list_indexed_repos` | List all indexed repositories with chunk counts. |
| `get_file_context` | Fetch raw lines from a file by line range. |
| `delete_repo_index` | Remove the index for a repository. |

### `index_repo`

```
repo_path    (str)              Absolute or ~ path to the repository root.
incremental  (bool)             Only reindex changed files. Default: true.
exclude_dirs (list[str] | null) Additional directory names to exclude from indexing (e.g. ["docs", "examples"]).
```

### `search_code`

```
query      (str)        Natural language or code description.
repo_path  (str | null) Restrict search to one repo. Default: search all.
top_k      (int)        Number of results. Default: 10.
file_glob  (str | null) Filter by filename pattern, e.g. "*.py".
```

### `get_file_context`

```
file_path  (str)  Absolute path to the file.
line_start (int)  1-based start line.
line_end   (int)  1-based end line (inclusive).
```

### `delete_repo_index`

```
repo_path  (str)  Path to the repository root.
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `CODE_RAG_CHROMA_DIR` | `~/.local/share/code-rag/chroma` | ChromaDB persistent storage directory. |
| `CODE_RAG_EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | fastembed model name. |
| `CODE_RAG_EMBED_BACKEND` | `fastembed` | Embedding backend (only `fastembed` is supported). |

## Chunking Strategy

The indexer uses tree-sitter to extract top-level functions, classes, and methods as individual chunks. This preserves semantic boundaries and keeps each chunk self-contained. Files in unsupported languages are skipped.

Supported languages and extensions:

| Language | Extensions |
|---|---|
| Python | `.py` |
| C | `.c` `.h` |
| C++ | `.cpp` `.cc` `.cxx` `.hpp` `.hxx` |
| JavaScript | `.js` `.jsx` `.mjs` |
| Bash | `.sh` `.bash` `.zsh` |

## Stability for Large Repos

The indexer is designed to handle repositories with 30,000+ files reliably:

- **File size limit** — Files larger than 2 MB are skipped automatically to avoid memory spikes or parser hangs.
- **Streaming batch processing** — Chunks are embedded and upserted as soon as a batch (64 chunks) is ready, instead of accumulating all chunks in memory first.
- **Retry on failure** — Each embed + upsert batch is retried up to 3 times before being skipped, preventing transient errors from aborting the entire indexing run.
- **Structured logging** — All errors and progress are logged via Python's `logging` module under the `code_rag_mcp` logger. Progress is reported every 1,000 files.

## License

MIT
