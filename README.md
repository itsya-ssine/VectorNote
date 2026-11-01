# VectorNote

Offline, privacy-first RAG study assistant. Ingest your semester PDFs, slides and notes, then search them locally, with every result tied to the file and page it came from. No cloud API, no cost, and your documents never leave your machine.

**Stack:** Python 3.11+, FastAPI, ChromaDB, sentence-transformers (`all-MiniLM-L6-v2`), Ollama, React + TypeScript (Vite). A static demo of the same UI deploys to Vercel.

## Status

Work in progress. The full question-answering pipeline works from the command line and the API: ingest, hybrid search, and cited answers from a local LLM through Ollama. Evaluation and the live chat UI are next. See the [roadmap](#roadmap).

| Works today | Coming next |
|---|---|
| PDF / Markdown / text ingestion with cleaning | Evaluation harness and benchmarks |
| Sentence-aware chunking with page-level citations | Cited answers from a local LLM, streaming |
| Incremental indexing (unchanged files are skipped) | Live chat UI, Docker, Vercel demo |
| Vector, BM25 keyword and hybrid (RRF) search from the CLI | Reranking (optional) |
| Cited answers from a local LLM (`ask`, `POST /ask`), with an "I couldn't find it" path | |
| Streaming answers word by word (CLI and Server-Sent Events) | |
| Conversation memory: follow-ups like "explain that more" are rewritten before searching (`chat`) | |
| FastAPI endpoints for upload, listing, health and questions | |

## How it works

```
PDFs / notes -> load -> clean -> chunk -> embed -> ChromaDB
                                                      |
              question -> vector search  --+
                       -> BM25 keywords --+-> Reciprocal Rank Fusion -> ranked passages (file, page)
                                                      |
                                      prompt (numbered passages) -> Ollama -> answer with [1] [2] citations
```

- **Cleaning** removes running headers, footers and page numbers, fixes ligatures and hyphenated line breaks, and keeps the original page numbers.
- **Chunking** never crosses a page, so every chunk maps to one `[file, page]` citation. Chunk IDs are stable, and files are tracked by content hash.
- **Answers are grounded:** the model only sees the numbered passages that passed a relevance check (`VECTORNOTE_MIN_RELEVANCE`, a minimum cosine similarity). It must cite them as `[1]`, `[2]`, and the citations are mapped back to file and page. If nothing relevant is found, or the model says the passages do not contain the answer, you get "I couldn't find it in your documents" (in French if you asked in French) and no answer is made up.
- **Conversations work:** a follow-up like "explain that more" is first rewritten by the model into a standalone question using the latest messages (citations stripped, long messages cut), and that is what gets searched and answered. If the rewrite looks wrong (empty, too long, an answer instead of a question) the original question is used. The server stores nothing; clients send the history with each request.
- **Search has three modes:** `vector` (embeddings, understands paraphrases), `bm25` (exact words, acronyms, identifiers) and `hybrid` (default: both, merged with Reciprocal Rank Fusion, so a passage that ranks well in both lists wins). The keyword index is rebuilt automatically when the index changes, even if another process (such as the CLI) changed it.
- **Indexing is incremental:** re-running `ingest` skips unchanged files and re-indexes edited ones. An edit replaces the old chunks only after the new ones were embedded successfully.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.11+, and (for the UI) Node 20+. Ollama is only needed for `ask`.

```bash
git clone https://github.com/<your-username>/VectorNote.git
cd VectorNote
uv sync

# 1. Put your files in data/ (PDF, .md, .txt) and index them
cp ~/lectures/*.pdf data/
uv run vectornote ingest

# 2. Search them
uv run vectornote search "what are the four conditions for deadlock?"

# 3. Ask questions (needs Ollama: https://ollama.com)
ollama pull llama3.2:3b
uv run vectornote ask "What are the four conditions for deadlock?"

# 4. Or have a conversation: follow-up questions work
uv run vectornote chat
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
| `vectornote search "<question>" [-k N] [--mode vector\|bm25\|hybrid] [--source FILE] [--min-score X] [--full]` | Show the most relevant passages with score, file and page. `--source` can be repeated. `--min-score` is a minimum cosine similarity (vector and hybrid modes). In hybrid mode each result also shows its cosine and BM25 scores. |
| `vectornote chat [-k N] [--mode ...] [--source FILE]` | Interactive conversation with your documents. Follow-ups such as "explain that more" are rewritten into standalone questions first, and the rewrite is shown as `(searching for: ...)`. `/reset` forgets the conversation, `/exit` quits. Needs Ollama. |
| `vectornote inspect <file> [--chunks]` | Show how a file is loaded, cleaned and chunked. Use it to debug a bad PDF. |
| `vectornote serve [--host] [--port] [--reload]` | Run the HTTP API. |
| `vectornote ask "<question>" [-k N] [--mode ...] [--source FILE] [--no-stream]` | Answer from your documents with numbered citations, printed word by word as the model writes it, followed by the list of sources (`[1] file, p. N`). `--no-stream` waits for the whole answer. Needs Ollama. |

## HTTP API

| Method | Path | Status |
|---|---|---|
| `GET` | `/health` | done |
| `GET` | `/documents` | done: files in `data/` |
| `POST` | `/ingest` | done: upload a file and index it (415 for unsupported types, 422 for unreadable files) |
| `POST` | `/ask/stream` | done: same request as `/ask`, answered as Server-Sent Events: a `query` event (`{"question"}`) when a follow-up was rewritten, many `token` events (`{"text"}`), then `done` (same JSON as `/ask`), or `error` (`{"detail"}`) if the model fails midway. Closing the connection stops the model. |
| `POST` | `/ask` | done: `{question, top_k?, sources?, mode?, history?}` where `history` is the earlier messages `[{role: "user"|"assistant", content}]` (the server keeps no conversation state; the client sends it each time) returns `{answer, answered, standalone_question, cited, sources[]}`; 503 if Ollama is down or the model is missing |

## Configuration

Set these as environment variables. A `.env` file is not loaded automatically yet.

| Variable | Default | Meaning |
|---|---|---|
| `VECTORNOTE_DATA_DIR` | `data` | Folder with your documents |
| `VECTORNOTE_CHROMA_DIR` | `chroma_db` | Where the index is stored |
| `VECTORNOTE_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model. `hashing` selects a tiny dependency-free embedder for tests and offline smoke runs (word matching only, no semantics). |
| `VECTORNOTE_RETRIEVAL_MODE` | `hybrid` | Default search mode: `vector`, `bm25` or `hybrid` |
| `VECTORNOTE_MIN_RELEVANCE` | `0.25` | Minimum cosine similarity for a passage to be used in an answer (tune it in Phase 4) |
| `VECTORNOTE_LLM_MODEL` | `llama3.2:3b` | Ollama model used for answers |
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
  retrieval/      vector search, BM25, rank fusion (hybrid)
  generation/     Ollama client, prompts, citation parsing
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
  - [x] BM25 and hybrid search
  - [ ] Reranking (optional)
- [x] **Phase 3:** generation
  - [x] Cited answers, refusal path, `ask` command and `/ask` endpoint
  - [x] Streaming
  - [x] Conversation memory
- [ ] **Phase 4:** evaluation (hit rate, MRR, faithfulness, latency)
- [ ] **Phase 5:** live chat UI
- [ ] **Phase 6:** Vercel demo
- [ ] **Phase 7:** Docker, demo video, v1.0.0

## License

MIT
