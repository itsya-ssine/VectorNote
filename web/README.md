# VectorNote web UI

React + TypeScript frontend built with Vite.

Two modes, one codebase:

| Mode | When | Behavior |
|---|---|---|
| **Live** | `VITE_DEMO_MODE=false` | Talks to the FastAPI backend at `VITE_API_URL` |
| **Static demo** | `VITE_DEMO_MODE=true` (set in `.env.production`) | Canned answers with citations and a banner that links to the setup instructions. This is what Vercel deploys. |

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

### What the demo knows

Seven topics over three made-up documents (`operating-systems-lecture-05.pdf`, `networks-summary.md`, `databases-exam-notes.pdf`): locks and deadlocks, subnets, TCP and UDP, paging, scheduling, SQL joins, and ACID transactions. It behaves like the real app where it can:

- answers stream word by word, with numbered citations that open the matching passage;
- a short follow-up such as "explain that more" is understood from the conversation and shown as a rewritten question;
- a question outside these topics gets the same "I couldn't find the answer" refusal as the real app, and unticking a document hides the answers that need it.

The topics live in `src/lib/demo.ts`; add one by copying an entry of `TOPICS`.

## Keyboard shortcuts

| Key | Action |
|---|---|
| `/` | Focus the question field (when you are not typing) |
| `Enter` | Send the question |
| `Esc` | Stop the answer being written; closes the documents drawer on small screens |
| `Alt` + `N` | Start a new chat |

## Small screens and touch

The documents sidebar becomes a drawer (menu button, or "Open documents" on the empty screen):
it takes keyboard focus when opened, `Esc` or a tap outside closes it, and it is out of the tab
order while closed. The question field uses a 16px font so iOS does not zoom into it, the composer
respects the home-indicator safe area, and buttons get larger tap targets on touch screens.

While an answer streams, the chat follows it. Scroll up to read something and it stops following;
a "Follow answer" button brings you back. The document list shows placeholder rows while it loads.

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

The demo is a static site: no server, no API keys, no environment variables to set.

1. On [vercel.com/new](https://vercel.com/new), import the GitHub repository.
2. Set **Root Directory** to `web`. Everything else comes from `web/vercel.json` (Vite, `npm ci`, `npm run build`, output `dist`).
3. Deploy. Every push to `main` then redeploys, and every pull request gets a preview URL.

Or from the terminal, in `web/`: `npx vercel` for a preview and `npx vercel --prod` for production.

`vercel.json` also caches the hashed files in `assets/` for a year and sets security headers, including a Content-Security-Policy that only allows the site's own files (the demo makes no network requests). If you point a build at a real API, add its address to `connect-src`.

`npm run check:demo` (run by CI and `make check` after the build) fails if the bundle contains backend code (`/ask/stream`, `localhost:8000`), if a file `index.html` points to is missing, or if `vercel.json` is invalid. So a broken demo is caught before Vercel sees it.
