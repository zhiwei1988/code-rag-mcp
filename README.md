# code-rag-mcp

A Model Context Protocol (MCP) server that indexes code repositories and exposes semantic search as tools for AI assistants like Claude.

## How it works

```
Source Files
    │
    ▼
File Scanner (indexer.py)
    │  filter by extension / exclusion rules
    ▼
Chunker
    │  tree-sitter (function/class level)  ──fallback──▶  sliding window (128 lines, 32 overlap)
    ▼
Embedder (fastembed + BAAI/bge-small-en-v1.5, local ONNX)
    │
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

For languages with tree-sitter support (Python, JS/TS, Go, Rust, C/C++, Java, Ruby, Lua, C#), the indexer extracts top-level functions, classes, and methods as individual chunks. This preserves semantic boundaries and keeps each chunk self-contained.

For all other file types, or when tree-sitter is unavailable, the indexer falls back to a **sliding window** of 128 lines with a 32-line overlap between adjacent chunks, ensuring no context is lost at chunk boundaries.

Supported languages for tree-sitter chunking:

`.py` `.js` `.ts` `.jsx` `.tsx` `.go` `.rs` `.c` `.cpp` `.h` `.hpp` `.java` `.rb` `.lua` `.cs`

## License

MIT
