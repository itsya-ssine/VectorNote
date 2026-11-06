# Changelog

All notable changes to VectorNote. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-05

First release: an offline, privacy-first RAG study assistant. Ask questions about your own PDFs, slides and notes and get answers that cite the file and page they came from, with everything running on your machine.

### Added

- **Ingestion:** PDF, Markdown and text files, with cleaning (running headers and footers, page numbers, ligatures, hyphenated line breaks), sentence-aware chunking that never crosses a page, stable chunk IDs, and incremental indexing by content hash.
- **Search:** vector search (`all-MiniLM-L6-v2`), BM25 keyword search and hybrid search with Reciprocal Rank Fusion, which is the default. On the 35 answerable evaluation questions it finds the right page in the top 3 every time (hit@3 100%, hit@1 77%), with a search latency of about 20 ms.
- **Answers:** grounded in the retrieved passages through a local LLM (Ollama, `llama3.2:3b` by default), with `[1]` `[2]` citations mapped back to file and page, and an "I couldn't find it in your documents" answer (also in French) when nothing relevant is found. On the evaluation set it refused all 7 unanswerable questions.
- **Streaming answers** word by word (Server-Sent Events), which stop generating when the client disconnects.
- **Conversation memory:** follow-ups such as "explain that more" are rewritten into standalone questions before searching. The server stores nothing; clients send the history.
- **HTTP API** (FastAPI): `/health`, `/documents` (list and delete), `/ingest`, `/ask` and `/ask/stream`.
- **Web UI** (React and TypeScript): streaming chat with a Stop button, clickable citations that open and highlight the source passage, copy buttons, upload with progress, per-document search filter, keyboard shortcuts, empty and error states, and a layout for phones.
- **Command line:** `ingest`, `search`, `ask`, `chat`, `inspect`, `serve` and `eval`.
- **Evaluation:** a harness (`vectornote eval run`), a 46-question evaluation set with expected pages, and benchmarks for retrieval modes, chunk sizes, the relevance threshold and answer quality, with the raw results in `eval/results/`.
- **Static demo** on Vercel, with canned answers and no backend: <https://vector-note.vercel.app/>.
- **Docker:** `docker compose up --build` starts the API, the web UI and Ollama. Images use the CPU build of PyTorch and include the embedding model, so they run offline. Images for each release are published to `ghcr.io/itsya-ssine/vectornote-api` and `vectornote-web`, and `docker-compose.prebuilt.yml` runs them without cloning the repository.
- `make dev` runs the API and the web UI together.

### Security

- Uploads are limited to `.pdf`, `.md` and `.txt` files of at most `VECTORNOTE_MAX_UPLOAD_MB` (50 by default); an oversized upload is refused with 413 before it is stored.
- File names are reduced to a plain name inside the data directory (no folders, no `..`, no hidden files, at most 200 bytes). Errors name the file and never a path on the server.
- The API has no login and listens on `127.0.0.1` by default; the Docker setup publishes its ports on `127.0.0.1` only.

### Known limitations

See [Limitations](https://github.com/itsya-ssine/VectorNote#limitations) in the README: scanned PDFs need OCR, which is not included; retrieval was measured on English text only; and the 3B model cites the expected page in about 79% of answers.

[1.0.0]: https://github.com/itsya-ssine/VectorNote/releases/tag/v1.0.0
