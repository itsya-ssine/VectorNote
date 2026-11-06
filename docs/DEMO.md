# Recording the demo and publishing v1.0.0

The goal is one clip of 60 to 90 seconds that shows the whole idea: **upload a PDF, ask a question, watch the answer stream, click a citation to see the page it came from.** You need it twice: a GIF for the README and an MP4 for LinkedIn and your portfolio.

## 1. Prepare

Use a separate data folder, so the recording never touches your own documents:

```bash
git switch main && git pull --ff-only origin main
make install
ollama pull llama3.2:3b          # or llama3.2:1b, see the note below

VECTORNOTE_DATA_DIR=/tmp/demo-data VECTORNOTE_CHROMA_DIR=/tmp/demo-chroma make dev
```

- **Sample document:** `eval/example/corpus/os-lecture.pdf`, six pages of original lecture notes (processes and threads, mutual exclusion, semaphores, deadlock, paging, page replacement). Do not use a real course PDF in a public video.
- **Speed:** `llama3.2:3b` takes close to a minute per answer on a CPU. Either record in real time and speed up the waiting in the editor, or record with `VECTORNOTE_LLM_MODEL=llama3.2:1b` (several times faster, with weaker citations). Use the same model that you describe in the video.
- **Warm up first.** Ask one question before recording, so the embedding model and the language model are already loaded. Then delete the document in the sidebar and start the take from the empty screen.
- **Browser:** a fresh profile or a private window, 1280×720 (a region of that size is easy to record), page zoom 110%, bookmarks bar hidden, notifications off, light or dark theme but not a mix. Open <http://localhost:3000>.

## 2. Shot list

| Time | On screen | What you do |
|---|---|---|
| 0:00 | Empty state: "Add a document to get started" | Hold for two seconds. |
| 0:03 | Sidebar | Drag `os-lecture.pdf` onto it. The progress bar runs, the file appears in the list. |
| 0:10 | Chat | Type **What is the difference between a mutex and a semaphore?** and press Enter. The answer streams in with `[1]` `[2]` markers. (Cut or speed up the wait before the first word.) |
| 0:30 | Answer | Click **[1]**: the sources open, scroll to the passage and highlight it. Click "Show more" on the card. |
| 0:42 | Chat | Type **explain that more**. The line "Searching for: ..." shows the question was rewritten from the conversation. |
| 0:58 | Chat | Type **Who won the 2018 World Cup?** The answer is "I couldn't find the answer to that in your documents." and it comes back at once, because no model call is made. |
| 1:06 | Answer | Press the Copy button, or untick the document in the sidebar. |
| 1:10 | Title card (added in the editor) | "VectorNote: offline RAG study assistant. github.com/itsya-ssine/VectorNote". Hold for three seconds. |

Three things that make the clip convincing: the citation highlight (it proves the answer comes from the page), the refusal (it proves the model does not make things up), and the "Searching for" line (it proves follow-ups work).

## 3. Record

- **OBS Studio** (works on X11 and Wayland): add a Window Capture or Screen Capture source, crop it to the browser window, output to MP4.
- **ffmpeg on X11:** `ffmpeg -f x11grab -framerate 30 -video_size 1280x720 -i :0.0+100,100 -c:v libx264 -preset veryfast -crf 20 demo-raw.mp4` (the numbers after `:0.0+` are the position of the window).
- **Wayland:** OBS, or the screen recorder built into GNOME (Ctrl+Alt+Shift+R).

Trim it to 90 seconds at most. To speed up only the waiting parts, split the clip at those points in any editor (Kdenlive, Shotcut, DaVinci Resolve) and set that segment to 4× speed. Keep the typing at normal speed.

## 4. Make the GIF

```bash
ffmpeg -i demo.mp4 \
  -vf "fps=12,scale=900:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer:bayer_scale=5" \
  -loop 0 docs/assets/demo.gif
ls -lh docs/assets/demo.gif        # aim for under 8 MB
```

If it is too big, lower `fps` to 10 and the width to 800, or shorten the clip. A different option that needs no GIF: drag the MP4 into a comment box on GitHub (an issue or a pull request, no need to submit it). GitHub uploads it and gives you a `https://github.com/user-attachments/assets/...` link; paste that link on its own line in the README and GitHub shows a video player.

Then add this line to the README, right under the "Live demo" paragraph, and commit it (`docs: add the demo GIF`):

```markdown
![VectorNote demo: upload a PDF, ask a question, click a citation](docs/assets/demo.gif)
```

## 5. Publish v1.0.0

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
