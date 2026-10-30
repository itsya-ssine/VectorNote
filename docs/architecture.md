# Architecture

```
PDFs / notes -> loaders -> cleaning -> chunking -> embeddings -> ChromaDB
                                                                   |
question -> RagService.ask -> retriever (vector + BM25, RRF) -> prompt -> Ollama
                  ^                                                      |
                  |                                                      v
        FastAPI (/ask, /ingest, /documents)  <----  answer + cited sources
                  ^
                  |
        React UI (web/)    --  live mode: calls the API
                           --  demo mode: canned answers (Vercel)
```

## Rules

- Route handlers and CLI commands call only `RagService`; they never import retrieval
  or generation modules directly.
- Every chunk carries `source` and `page` so every answer can cite its evidence.
- `data/` and `chroma_db/` are never committed.

## API

| Method | Path | Status |
|---|---|---|
| GET | `/health` | done |
| GET | `/documents` | done |
| POST | `/ingest` | stub (501), Phase 1 |
| POST | `/ask` | stub (501), Phase 3 |
