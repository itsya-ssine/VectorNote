# VectorNote

Offline, privacy-first RAG study assistant. Ingest semester PDFs, slides and notes,
then ask questions about them locally with cited answers. No cloud API, no cost.

**Stack:** Python 3.11+, FastAPI, ChromaDB, sentence-transformers (`all-MiniLM-L6-v2`),
Ollama, React + TypeScript (Vite). A static demo of the same UI deploys to Vercel.

> Status: project skeleton. See the roadmap below.

## Quick start

```bash
# Backend
uv sync
uv run vectornote --version
ollama pull llama3.2:3b
uv run python scripts/smoke_ollama.py
uv run vectornote serve --reload        # http://localhost:8000/docs

# Frontend (second terminal)
cd web
cp .env.local.example .env.local
npm install
npm run dev                             # http://localhost:3000
```

## Development

```bash
make check          # flake8, mypy, pytest, web build
uv run pre-commit install
```

## Layout

```
src/vectornote/
  config.py       settings (env-driven)
  models.py       Document / Chunk / SearchResult
  service.py      RagService: the only entry point the API and CLI use
  cli.py          command-line entry point (ingest, ask, serve)
  api/            FastAPI app, routes, schemas
  ingestion/      loaders, cleaning, chunking
  embeddings/     embedding model wrapper
  store/          ChromaDB persistence
  retrieval/      vector + BM25 hybrid search
  generation/     Ollama client and prompts
web/              React + TypeScript UI, Vite (live mode + static demo mode for Vercel)
tests/            pytest suite
docs/             architecture notes
```

## Roadmap

- [x] Phase 0: repo, tooling, CI, API and UI skeleton
- [ ] Phase 1: ingestion (PDF/MD/TXT loaders, cleaning, chunking, embeddings, Chroma)
- [ ] Phase 2: retrieval (vector, hybrid, rerank)
- [ ] Phase 3: generation with citations, streaming
- [ ] Phase 4: evaluation
- [ ] Phase 5: wire the UI to the live API
- [ ] Phase 6: Vercel demo deployment
- [ ] Phase 7: Docker, demo video
