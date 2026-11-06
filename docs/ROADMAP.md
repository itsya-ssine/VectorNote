# VectorNote Roadmap

Offline, privacy-first RAG study assistant: FastAPI backend, React + TypeScript (Vite) frontend, ChromaDB, local LLMs via Ollama.

Each task is one branch and one pull request, with a "done when" check. Tick the boxes as you go.

## Overview

| Phase | Goal | Estimate |
|---|---|---|
| 0 | Skeleton, tooling, CI | done |
| 1 | Ingestion pipeline | 3-4 days |
| 2 | Retrieval | 2-3 days |
| 3 | Generation with citations | 2-3 days |
| 4 | Evaluation | 2 days |
| 5 | Live UI | 3-4 days |
| 6 | Vercel demo | 1 day |
| 7 | Packaging and showcase | 2-3 days |

Phases 1 to 3 give you a working terminal tool, which is the core of the project. Phase 4 is what makes it stand out. Phases 5 to 7 are packaging.

## Phase 0: Skeleton (done)

- [x] **Task 1:** repo, `uv`, flake8, mypy, pytest, pre-commit, CI, FastAPI skeleton, React + Vite skeleton

## Phase 1: Ingestion

- [x] **Task 2: Loaders and cleaning** (`feat/loaders`)
  - Implement `load_document` for PDF (`pymupdf`), Markdown and TXT, returning one `Document` with a list of pages.
  - Implement `clean_text`: remove repeated headers and footers, fix hyphenated line breaks, collapse whitespace, drop empty pages.
  - Tests use small fixture files (a generated PDF, a `.md`, a `.txt`).
  - **Done when:** a real lecture PDF loads with correct page numbers and clean text.

- [x] **Task 3: Chunking** (`feat/chunking`)
  - Recursive splitter that respects paragraphs and sentences. Defaults: about 800 characters with about 100 overlap, read from `Settings`.
  - Every `Chunk` carries `chunk_id` (stable hash of source, page and position), `source`, `page` and `text`.
  - Tests cover overlap, no empty chunks, and stable IDs across runs.
  - **Done when:** chunking a 50-page PDF gives sane chunk counts and every chunk maps back to a page.

- [x] **Task 4: Embeddings and vector store** (`feat/embeddings-store`)
  - `Encoder` wraps `all-MiniLM-L6-v2` (sentence-transformers) with batching and lazy model loading.
  - `ChromaStore`: persistent client with `add`, `query`, `delete_by_source` and `list_sources`.
  - **Done when:** you can add chunks, restart the process, and still query them.

- [x] **Task 5: Ingestion service and CLI** (`feat/ingest-pipeline`)
  - `RagService.ingest` runs load, clean, chunk, embed and store.
  - Store a content hash per file so unchanged files are skipped and edited files are re-indexed (delete old chunks first).
  - Wire `vectornote ingest` and `POST /ingest`, and report chunks added.
  - **Done when:** running `ingest` twice processes each file once, and uploading from the UI works.

## Phase 2: Retrieval

- [x] **Task 6: Vector search** (`feat/vector-retrieval`)
  - `Retriever.search` returns `SearchResult` objects with scores, supports `top_k` and a filter by source.

- [x] **Task 7: BM25 and hybrid** (`feat/hybrid-retrieval`)
  - Add BM25 over the stored chunks and fuse it with vector results using Reciprocal Rank Fusion (RRF).
  - Make the mode switchable (`vector`, `bm25`, `hybrid`) so you can compare them in Phase 4.

- [ ] **Task 8: Reranking, optional** (`feat/rerank`)
  - A small cross-encoder reranks the top 20 down to the top 5. Keep it behind a setting.
  - **Done when (Phase 2):** `vectornote search "<query>"` returns the right pages for ten test questions whose answers you know.

## Phase 3: Generation

- [x] **Task 9: Prompt and answer with citations** (`feat/generation`)
  - `RagService.ask`: retrieve, build the prompt (`SYSTEM_PROMPT` plus numbered context blocks), call Ollama, return the answer plus source chunks.
  - The model must cite as `[file, page]` and say "I don't know" when the context lacks the answer. Handle empty retrieval without calling the LLM.
  - Wire `vectornote ask` and `POST /ask`.

- [x] **Task 10: Streaming** (`feat/streaming`)
  - Stream tokens from Ollama through FastAPI (Server-Sent Events) and send the sources at the end.

- [x] **Task 11: Conversation memory** (`feat/chat-memory`)
  - Rewrite follow-up questions ("explain that more") into standalone queries using recent history before retrieval.
  - **Done when (Phase 3):** answers are grounded, cited and streamed, and the assistant refuses when the notes don't cover the question.

## Phase 4: Evaluation

- [x] **Task 12: Evaluation set** (`feat/eval-dataset`)
  - Write 30-50 questions from your own course material, each with the expected source and page and a reference answer. Keep them in `eval/questions.jsonl`.
  - Done: 46 questions on a public Python textbook, validated with `vectornote eval check`.

- [x] **Task 13: Metrics and benchmarks** (`feat/eval-harness`)
  - Done: retrieval, chunk sizes (400, 800, 1200) and answers are benchmarked and the tables are in the README. Defaults: hybrid search, 800-character chunks, `VECTORNOTE_MIN_RELEVANCE` 0.35. Open question: whether 400-character chunks improve the answers (see the README).
  - Retrieval: hit rate@k and MRR.
  - Generation: faithfulness and citation correctness, by manual check or an LLM judge.
  - Latency: measure query time so any speed claim in the README is backed by numbers.
  - Compare chunk size, vector vs BM25 vs hybrid, and with vs without reranking. Choose the defaults from the results.
  - Put the results table in the README.

## Phase 5: Live UI

- [x] **Task 14: Connect the React UI** (`feat/web-live`)
  - Streaming answers in the chat, upload progress and errors, document list with delete, source filter.
  - Done: `/ask/stream` is consumed with `fetch` (stop button, follow-ups send the last 10 messages, the rewritten question is shown), uploads report progress and then "indexing", each file succeeds or fails on its own, `DELETE /documents/{name}` removes a file and its chunks, and unticking a document leaves it out of the search (`sources`).

- [ ] **Task 15: Citation experience** (`feat/web-citations`)
  - Clickable citations that highlight the matching source card, a copy-answer button, empty and error states.

- [ ] **Task 16: Polish** (`feat/web-polish`)
  - Mobile layout, keyboard shortcuts, loading skeletons, dark and light mode check.

## Phase 6: Vercel demo

- [x] **Task 17: Static demo deployment** (`feat/vercel-demo`)
  - [x] More canned Q&A: seven topics over three demo documents, follow-ups understood from the history, refusal for anything else, document filter respected.
  - [x] "Run it locally" link in the demo banner, `web/vercel.json` (build settings, caching, security headers), Open Graph tags.
  - [x] `npm run check:demo` in CI and `make check`: the production bundle has no backend code and the deployment config is valid.
  - [x] Imported on Vercel with Root Directory `web`; live at https://vector-note.vercel.app/ and linked from the README.

## Phase 7: Packaging and showcase

- [x] **Task 18: Docker** (`feat/docker`)
  - `Dockerfile` for the API (CPU-only PyTorch from the lock file, embedding model baked in, runs offline, non-root), `web/Dockerfile` (Vite build in live mode, served by nginx, `/api` forwarded to the API with streaming), and `docker-compose.yml` with Ollama and a one-shot model pull.
  - An allow-list `.dockerignore` keeps documents and the index out of the images; `make docker-up`; a CI job builds both images, checks for CUDA libraries, starts the API and loads the embedding model with the network off.
  - **Done when:** one command starts everything.

- [x] **Task 19: Quality hardening** (`chore/hardening`)
  - Coverage was already 99%, and `/ask` is tested with a mocked Ollama (`tests/test_ask.py`); CI runs the same checks as `make check`. So the work went into probing the API with hostile input (`tests/test_hardening.py`, 33 tests) and fixing what that found.
  - Fixed: a 300-character file name returned a 500; there was no upload size limit; unreadable-PDF errors exposed the server's temporary path.
  - Upload limit `VECTORNOTE_MAX_UPLOAD_MB` (default 50), checked from Content-Length before the body is stored and again after reading, with a 413 that still carries CORS headers; names are cut to 200 bytes keeping the extension; `make dev` starts the API and the UI together.

- [ ] **Task 20: Docs and demo** (`docs/showcase`)
  - [x] README with architecture diagrams (Mermaid, checked with the Mermaid parser), results at a glance, the benchmark tables, setup steps, limitations and the roadmap; the same diagrams in `docs/architecture.md`.
  - [x] Version 1.0.0 (three files kept in step by a test), `CHANGELOG.md`, social preview card (`docs/assets/`, `web/public/og.png` with Open Graph tags).
  - [x] Release workflow: a `v*` tag checks the version, publishes `vectornote-api` and `vectornote-web` to ghcr.io and creates the GitHub release from the changelog. `docker-compose.prebuilt.yml` runs those images and is generated from `docker-compose.yml` (a test keeps them in step).
  - [ ] Record a 60-90 second demo (ingest, ask, citations) and embed the GIF: shot list and commands in `docs/DEMO.md`.
  - [ ] Push the `v1.0.0` tag, make the packages public, fill in the repository About box (checklist in `docs/DEMO.md`).

- [ ] **Task 21: Resume and portfolio**
  - Write the resume bullets with your real numbers (hit rate, latency, chunk counts) and add the project to your portfolio.

## Git workflow for every task

```bash
git switch main && git pull
git switch -c feat/<name>
# commit small, using Conventional Commits: feat(ingest): ..., test(chunking): ...
make check
git push -u origin feat/<name>
gh pr create --fill
gh pr merge --squash --delete-branch
```

| Commit type | Use for |
|---|---|
| `feat` | new functionality |
| `fix` | bug fix |
| `docs` | README, docstrings |
| `test` | adding or fixing tests |
| `refactor` | no behavior change |
| `perf` | performance work |
| `chore` | tooling, config, dependencies |

## Pitfalls to watch

- PDF extraction quality dominates retrieval quality. Test it early on your real lecture slides.
- Small local models hallucinate easily, so strict prompting and a refusal path matter more than model choice.
- Any performance claim ("sub-second search") needs a measured benchmark behind it.
- Never commit course material or the vector store: `data/` and `chroma_db/` stay out of git.