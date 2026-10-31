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

- [ ] **Task 7: BM25 and hybrid** (`feat/hybrid-retrieval`)
  - Add BM25 over the stored chunks and fuse it with vector results using Reciprocal Rank Fusion (RRF).
  - Make the mode switchable (`vector`, `bm25`, `hybrid`) so you can compare them in Phase 4.

- [ ] **Task 8: Reranking, optional** (`feat/rerank`)
  - A small cross-encoder reranks the top 20 down to the top 5. Keep it behind a setting.
  - **Done when (Phase 2):** `vectornote search "<query>"` returns the right pages for ten test questions whose answers you know.

## Phase 3: Generation

- [ ] **Task 9: Prompt and answer with citations** (`feat/generation`)
  - `RagService.ask`: retrieve, build the prompt (`SYSTEM_PROMPT` plus numbered context blocks), call Ollama, return the answer plus source chunks.
  - The model must cite as `[file, page]` and say "I don't know" when the context lacks the answer. Handle empty retrieval without calling the LLM.
  - Wire `vectornote ask` and `POST /ask`.

- [ ] **Task 10: Streaming** (`feat/streaming`)
  - Stream tokens from Ollama through FastAPI (Server-Sent Events) and send the sources at the end.

- [ ] **Task 11: Conversation memory** (`feat/chat-memory`)
  - Rewrite follow-up questions ("explain that more") into standalone queries using recent history before retrieval.
  - **Done when (Phase 3):** answers are grounded, cited and streamed, and the assistant refuses when the notes don't cover the question.

## Phase 4: Evaluation

- [ ] **Task 12: Evaluation set** (`feat/eval-dataset`)
  - Write 30-50 questions from your own course material, each with the expected source and page and a reference answer. Keep them in `eval/questions.jsonl`.

- [ ] **Task 13: Metrics and benchmarks** (`feat/eval-harness`)
  - Retrieval: hit rate@k and MRR.
  - Generation: faithfulness and citation correctness, by manual check or an LLM judge.
  - Latency: measure query time so any speed claim in the README is backed by numbers.
  - Compare chunk size, vector vs BM25 vs hybrid, and with vs without reranking. Choose the defaults from the results.
  - Put the results table in the README.

## Phase 5: Live UI

- [ ] **Task 14: Connect the React UI** (`feat/web-live`)
  - Streaming answers in the chat, upload progress and errors, document list with delete, source filter.

- [ ] **Task 15: Citation experience** (`feat/web-citations`)
  - Clickable citations that highlight the matching source card, a copy-answer button, empty and error states.

- [ ] **Task 16: Polish** (`feat/web-polish`)
  - Mobile layout, keyboard shortcuts, loading skeletons, dark and light mode check.

## Phase 6: Vercel demo

- [ ] **Task 17: Static demo deployment** (`feat/demo`)
  - Import the repo on Vercel with Root Directory `web`. The production build already runs in demo mode.
  - Add more canned Q&A, a "run it locally" link to the README, and put the live URL in the README.

## Phase 7: Packaging and showcase

- [ ] **Task 18: Docker** (`feat/docker`)
  - A `Dockerfile` for the API, one for the web build (served by nginx), and a `docker-compose.yml` with the app and Ollama.
  - **Done when:** one command starts everything.

- [ ] **Task 19: Quality hardening** (`chore/hardening`)
  - Raise test coverage on ingestion and retrieval, add an API test with a mocked Ollama, run `make check` in CI.
  - Add file-size and file-type limits on uploads and sanitize filenames.

- [ ] **Task 20: Docs and demo** (`docs/showcase`)
  - README with an architecture diagram, the benchmark table, setup steps, limitations and the roadmap.
  - Record a 60-90 second demo (ingest, ask, citations) and embed the GIF.
  - Tag `v1.0.0` and create a GitHub release.

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