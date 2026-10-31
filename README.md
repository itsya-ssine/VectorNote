# VectorNote

Offline, privacy-first RAG study assistant. Ingest your semester PDFs, slides and notes, then search them locally, with every result tied to the file and page it came from. No cloud API, no cost, and your documents never leave your machine.

**Stack:** Python 3.11+, FastAPI, ChromaDB, sentence-transformers (`all-MiniLM-L6-v2`), Ollama, React + TypeScript (Vite). A static demo of the same UI deploys to Vercel.

## Status

Work in progress. The ingestion and search pipeline works end to end from the command line and the API. Answer generation with a local LLM (Ollama), hybrid search, evaluation and the live chat UI are next. See the [roadmap](#roadmap).

| Works today | Coming next |
|---|---|
| PDF / Markdown / text ingestion with cleaning | BM25 + hybrid search, reranking |
| Sentence-aware chunking with page-level citations | Cited answers from a local LLM, streaming |
| Incremental indexing (unchanged files are skipped) | Evaluation harness and benchmarks |
| Semantic search from the CLI | Live chat UI, Docker, Vercel demo |
| FastAPI endpoints for upload, listing and health | |

## How it works

```
PDFs / notes -> load -> clean -> chunk -> embed -> ChromaDB
                                                      |
              question -> embed -> vector search -> ranked passages (file, page, score)
                                                      |
                                    (next) prompt -> Ollama -> cited answer
```

- **Cleaning** removes running headers, footers and page numbers, fixes ligatures and hyphenated line breaks, and keeps the original page numbers.
- **Chunking** never crosses a page, so every chunk maps to one `[file, page]` citation. Chunk IDs are stable, and files are tracked by content hash.
- **Indexing is incremental:** re-running `ingest` skips unchanged files and re-indexes edited ones. An edit replaces the old chunks only after the new ones were embedded successfully.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.11+, and (for the UI) Node 20+. Ollama is only needed once answer generation lands.

```bash
git clone https://github.com/<your-username>/VectorNote.git
cd VectorNote
uv sync

# 1. Put your files in data/ (PDF, .md, .txt) and index them
cp ~/lectures/*.pdf data/
uv run vectornote ingest

# 2. Search them
uv run vectornote search "what are the four conditions for deadlock?"
```

The first `ingest` downloads the embedding model once (about 90 MB) into the Hugging Face cache. After that you can set `HF_HUB_OFFLINE=1` to guarantee nothing touches the network.

### Run the API and the web UI

```bash
uv run vectornote serve --reload            # API on http://localhost:8000 (docs at /docs)

cd web
cp .env.local.example .env.local
npm install
npm run dev                                 # UI on http://localhost:3000
```

## Command line

| Command | What it does |
|---|---|
| `vectornote ingest [paths...] [--force] [--prune]` | Index files or folders (default: `data/`). `--force` re-indexes unchanged files. `--prune` removes files that left `data/` from the index. |
| `vectornote search "<question>" [-k N] [--source FILE] [--min-score X] [--full]` | Show the most relevant passages with score, file and page. `--source` can be repeated. |
| `vectornote inspect <file> [--chunks]` | Show how a file is loaded, cleaned and chunked. Use it to debug a bad PDF. |
| `vectornote serve [--host] [--port] [--reload]` | Run the HTTP API. |
| `vectornote ask "<question>"` | Not implemented yet (Phase 3). |

## HTTP API

| Method | Path | Status |
|---|---|---|
| `GET` | `/health` | done |
| `GET` | `/documents` | done: files in `data/` |
| `POST` | `/ingest` | done: upload a file and index it (415 for unsupported types, 422 for unreadable files) |
| `POST` | `/ask` | not implemented yet (returns 501) |

## Configuration

Set these as environment variables. A `.env` file is not loaded automatically yet.

| Variable | Default | Meaning |
|---|---|---|
| `VECTORNOTE_DATA_DIR` | `data` | Folder with your documents |
| `VECTORNOTE_CHROMA_DIR` | `chroma_db` | Where the index is stored |
| `VECTORNOTE_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model. `hashing` selects a tiny dependency-free embedder for tests and offline smoke runs (word matching only, no semantics). |
| `VECTORNOTE_LLM_MODEL` | `llama3.2:3b` | Ollama model for answers (Phase 3) |
| `VECTORNOTE_OLLAMA_URL` | `http://localhost:11434` | Ollama server |
| `VECTORNOTE_CORS_ORIGINS` | `http://localhost:3000` | Allowed browser origins, comma separated |

The index remembers which embedding model built it. If you change the model, VectorNote refuses to mix vectors and asks you to delete `chroma_db/` and ingest again.

## Privacy

- Documents, embeddings and the index stay on your machine. `data/` and `chroma_db/` are git-ignored.
- ChromaDB telemetry is switched off.
- The only network access is the one-time model download.

## Development

```bash
make check                     # flake8, mypy --strict, pytest, web build
uv run pre-commit install      # run flake8 and mypy on every commit
```

Work happens on short-lived branches with Conventional Commits (`feat(ingest): ...`), and CI runs the backend and web jobs on every pull request. Details in [docs/architecture.md](docs/architecture.md).

## Project layout

```
src/vectornote/
  config.py       settings (environment variables)
  models.py       Page, Document, Chunk, SearchResult
  service.py      RagService: the only entry point the API and CLI use
  cli.py          command-line interface
  api/            FastAPI app, routes, schemas
  ingestion/      loaders, cleaning, chunking
  embeddings/     sentence-transformers encoder, hashing embedder, factory
  store/          ChromaDB persistence
  retrieval/      vector search
  generation/     Ollama client and prompts (wired up in Phase 3)
web/              React + TypeScript UI (live mode and static demo mode)
scripts/          smoke tests for Ollama and the vector store
tests/            pytest suite
docs/             architecture notes
```

## Roadmap

- [x] **Phase 0:** repo, tooling, CI, API and UI skeleton
- [x] **Phase 1:** ingestion (loaders and cleaning, chunking, embeddings and vector store, incremental ingest)
- [ ] **Phase 2:** retrieval
  - [x] Vector search
  - [ ] BM25 and hybrid search
  - [ ] Reranking (optional)
- [ ] **Phase 3:** generation with citations, streaming, conversation memory
- [ ] **Phase 4:** evaluation (hit rate, MRR, faithfulness, latency)
- [ ] **Phase 5:** live chat UI
- [ ] **Phase 6:** Vercel demo
- [ ] **Phase 7:** Docker, demo video, v1.0.0

## License

MIT
