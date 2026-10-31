# Architecture

```
PDFs / notes -> loaders -> cleaning -> chunking -> embeddings -> ChromaDB
                                                                   |
question -> RagService.search -> Retriever (vector search) -> ranked chunks
                  |
                  +-- (Phase 3) prompt -> Ollama -> cited answer, streamed
                  ^
                  |
        FastAPI (/ingest, /documents, /health, later /ask)   CLI (ingest, search, inspect)
                  ^
                  |
        React UI (web/)  --  live mode: calls the API
                         --  demo mode: canned answers (Vercel)
```

## Rules

- Route handlers and CLI commands call only `RagService`; they never import retrieval,
  embedding or store modules directly.
- Every chunk carries `source` and `page`, and chunks never cross a page, so every result
  maps to one `[file, page]` citation. `Page.number` always matches the original file,
  even when empty pages were dropped.
- Embeddings are always computed by VectorNote and passed to Chroma; Chroma's own
  embedding functions and telemetry are not used.
- `data/` and `chroma_db/` are never committed.

## Ingestion

1. **Load** (`ingestion/loaders.py`): PDF through pymupdf, Markdown and text as one page.
2. **Clean** (`ingestion/cleaning.py`): ligatures, soft hyphens, hyphenated line breaks,
   whitespace; running headers, footers and page counters (English and French styles) are
   removed when they repeat at the edges of at least half the pages; empty pages are dropped.
3. **Chunk** (`ingestion/chunking.py`): lines and sentences packed up to 800 characters with
   up to 100 characters of overlap, made of whole sentences. A tiny trailing piece is merged
   into the previous chunk. IDs look like `lecture.pdf#p3-c1-9f2a1b7c`.
4. **Embed** (`embeddings/`): `all-MiniLM-L6-v2` through sentence-transformers, batched,
   L2-normalized, loaded lazily.
5. **Store** (`store/chroma_store.py`): persistent Chroma collection with cosine similarity.
   The embedding model name and each file's content hash are stored with the index.

`RagService.ingest_path` skips files whose content hash is unchanged. An edited file
replaces its old chunks only after the new embeddings were computed, so a failure never
leaves the index empty. Uploads are saved into `data/` under a sanitized name and only
replace an existing file once they ingest successfully.

## API

| Method | Path | Status |
|---|---|---|
| GET | `/health` | done |
| GET | `/documents` | done |
| POST | `/ingest` | done |
| POST | `/ask` | stub (501), Phase 3 |
