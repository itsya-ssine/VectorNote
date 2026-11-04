# VectorNote web UI

React + TypeScript frontend built with Vite.

Two modes, one codebase:

| Mode | When | Behavior |
|---|---|---|
| **Live** | `VITE_DEMO_MODE=false` | Talks to the FastAPI backend at `VITE_API_URL` |
| **Static demo** | `VITE_DEMO_MODE=true` (set in `.env.production`) | Canned answers with citations and a "Static Demo Mode" banner. This is what Vercel deploys. |

## What the live UI does

- **Chat:** answers stream in word by word (`POST /ask/stream`), with a Stop button. Follow-up
  questions work because the last 10 messages are sent with each question; when the server
  rewrites a follow-up, the question it searched for is shown. "New conversation" clears the chat.
- **Sources:** every answer lists the passages it cites, numbered like the `[1]` markers in the text.
  The markers are buttons: press one to open the list, scroll to that passage and highlight it
  (hover shows the file and page). Long passages have a "Show more" toggle.
- **Copy:** each answer has a Copy button that copies the text followed by its list of sources
  (`[1] file.pdf, p. 12`), and each passage has a small button that copies just that passage.
- **Empty and error states:** with no document indexed yet, the chat explains how to add one instead of
  offering questions. A failed answer (backend down, model missing) has a "Try again" button that
  asks the same question again. When the documents do not contain the answer, the reply is styled as
  a refusal and suggests rephrasing or checking the ticked documents.
- **Uploads:** several files at a time, each with a progress bar, then "Indexing" while the server
  embeds it. A file that fails (wrong type, unreadable PDF) shows its own error and does not stop the others.
- **Documents:** the list comes from `GET /documents`; the × button removes a file and its indexed passages.
- **Search filter:** untick a document to leave it out of the search. Nothing is filtered until you untick one.

In static demo mode the same screens run on canned data, so uploads and deletes only change the list in the page.

## Local development

```bash
cp .env.local.example .env.local
npm install
npm run dev          # http://localhost:3000
```

Run the backend from the repo root in another terminal: `uv run vectornote serve --reload`.

## Build

```bash
npm run build        # type-check, then bundle to dist/
npm run preview      # serve the production build locally (demo mode)
```

## Deploy the demo to Vercel

Import the GitHub repo and set **Root Directory** to `web`. Vercel detects Vite
(build command `npm run build`, output `dist`), so no other configuration is needed.
