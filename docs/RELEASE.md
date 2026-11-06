# Screenshot and publishing v1.0.0

There is no video demo. The README shows one screenshot, and the [live demo](https://vector-note.vercel.app/) lets anyone try the UI.

## Take the screenshot

Save it as **`docs/assets/screenshot.png`** (the README already points to that path).

```bash
git switch main && git pull --ff-only origin main
make install
ollama pull llama3.2:3b

VECTORNOTE_DATA_DIR=/tmp/demo-data VECTORNOTE_CHROMA_DIR=/tmp/demo-chroma make dev
```

1. Open <http://localhost:3000> in a private window, about 1280x720, zoom 110%, bookmarks bar hidden, one theme (not a mix).
2. Upload `eval/example/corpus/os-lecture.pdf` (original lecture notes, safe to show). Do not use a real course PDF.
3. Ask **What is the difference between a mutex and a semaphore?** and wait for the answer.
4. Click **[1]** so the source passage is open and highlighted. Take the screenshot with the sidebar, the answer and the highlighted source all visible.
5. Save it as PNG, under about 500 KB (squoosh.app or `pngquant` if it is larger).

## Publish v1.0.0

After the showcase pull request is merged:

1. **Tag the release.** The workflow checks that the tag matches the version in the code, publishes the two Docker images and creates the GitHub release from `CHANGELOG.md`.
   ```bash
   git switch main && git pull --ff-only origin main
   git tag -a v1.0.0 -m "VectorNote 1.0.0"
   git push origin v1.0.0
   ```
   Watch it under the **Actions** tab (three jobs: verify, images, release). If `verify` fails, it says which file has another version; fix it, then delete and recreate the tag (`git tag -d v1.0.0 && git push origin :refs/tags/v1.0.0`).
2. **Make the images public.** A new package on ghcr.io starts out private. On GitHub open your profile, **Packages**, `vectornote-api`, **Package settings**, **Change visibility**, **Public**. Do the same for `vectornote-web`. Check it from a machine that is not logged in: `docker logout ghcr.io; docker pull ghcr.io/itsya-ssine/vectornote-api:1.0.0`.
3. **Try the one-command path** in an empty folder: `mkdir t && cd t && mkdir data && curl -O https://raw.githubusercontent.com/itsya-ssine/VectorNote/main/docker-compose.prebuilt.yml && docker compose -f docker-compose.prebuilt.yml up`, then open <http://localhost:3000>.
4. **Fill in the repository page** (the gear next to **About**):
   - Description: `Offline, privacy-first RAG study assistant: cited answers from your own PDFs and notes. FastAPI, ChromaDB, Ollama, React.`
   - Website: `https://vector-note.vercel.app/`
   - Topics: `rag`, `retrieval-augmented-generation`, `ollama`, `chromadb`, `fastapi`, `react`, `typescript`, `llm`, `offline`, `privacy`, `vector-search`, `bm25`, `sentence-transformers`, `study-assistant`
5. **Social preview:** Settings, General, Social preview, upload `docs/assets/social-preview.png` (1280×640). Links to the repository then show that card on LinkedIn and Slack.
6. **Pin the repository** on your GitHub profile and link it from your portfolio.
