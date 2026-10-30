# VectorNote web UI

React + TypeScript frontend built with Vite.

Two modes, one codebase:

| Mode | When | Behavior |
|---|---|---|
| **Live** | `VITE_DEMO_MODE=false` | Talks to the FastAPI backend at `VITE_API_URL` |
| **Static demo** | `VITE_DEMO_MODE=true` (set in `.env.production`) | Canned answers with citations and a "Static Demo Mode" banner. This is what Vercel deploys. |

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
