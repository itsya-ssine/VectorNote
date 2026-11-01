# Architecture

```
PDFs / notes -> loaders -> cleaning -> chunking -> embeddings -> ChromaDB
                                                                   |
question -> RagService.search -> Retriever (vector | bm25 | hybrid) -> ranked chunks
                  |
                  +-- RagService.ask: relevance gate -> prompt -> Ollama -> answer with [n] citations
                  ^
                  |
        FastAPI (/ingest, /documents, /health, /ask)   CLI (ingest, search, ask, inspect)
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
| POST | `/ask` | done |

## Retrieval

`retrieval/retriever.py` offers three modes, chosen per call or through `VECTORNOTE_RETRIEVAL_MODE`:

- **vector:** cosine similarity of embeddings, from ChromaDB.
- **bm25:** Okapi BM25 over every chunk (`retrieval/bm25.py`, no extra dependency). Text is
  lowercased and accent-folded, with a small English and French stop list. The index lives in
  memory and is rebuilt when the store's on-disk revision counter changes, so an `ingest` run in
  another process is picked up.
- **hybrid:** the top candidates of both rankers are merged with Reciprocal Rank Fusion
  (`1 / (60 + rank)` per list, `retrieval/fusion.py`). Only ranks are used, so cosine and BM25
  never need a common scale. Every hybrid result also carries its `vector_score` (cosine) and
  `bm25_score`, fetched from the store or index when only one ranker found it.

`SearchResult.score` is the score of the mode that produced it and is only comparable within
that mode. `min_score` is always a minimum cosine similarity, so it works in `vector` and
`hybrid` modes and is refused in `bm25` mode. This is the threshold Phase 3 uses to decide
that the notes do not cover a question.

## Answering

`RagService.ask` (generation code in `generation/`):

1. **Gate:** retrieval runs with `min_score = VECTORNOTE_MIN_RELEVANCE` (a cosine threshold). With
   an empty index or no passage above the threshold, a fixed reply is returned and the model is
   never called. In `bm25` mode there is no cosine score, so the gate is skipped.
2. **Prompt:** the system prompt tells the model to use only the numbered passages, to cite them
   as `[n]`, and to reply `NOT_FOUND` when they do not contain the answer. The user message holds
   the passages (`[1] file, page N` followed by the text, within a 6000-character budget) and the
   question. Temperature is 0.1.
3. **Parse:** `[n]` markers (including `[1, 2]` and `[1][2]`) are mapped back to file and page;
   numbers outside the range are ignored as invented. `NOT_FOUND` becomes the same refusal reply
   as the gate. If the model cited nothing, the result is marked `cited = false` and lists all
   passages it was given, so the answer can still be checked.
4. **Errors:** `OllamaUnavailableError` (not running, timeout) and `OllamaModelNotFoundError`
   (`ollama pull <model>`) give one-line messages in the CLI and HTTP 503 from the API.

Numeric citations were chosen over `[file, page]` text because small local models copy a number
reliably but often garble file names; the API and CLI always map the numbers back to file and page.
