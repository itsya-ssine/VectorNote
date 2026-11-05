import { DEMO_DOCUMENTS, demoResult, sleep } from "./demo";
import { parseSse } from "./sse";
import type { AskResult, ChatTurn, DocumentInfo, IngestResult } from "./types";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Earlier messages sent along with a question, so follow-ups can be understood. */
export const MAX_HISTORY = 10;

function describe(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (status === 413) return "The file is too large.";
  if (status === 422) return "The request was not valid.";
  return `Request failed (${status})`;
}

async function failure(res: Response): Promise<Error> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // keep the default message
  }
  return new Error(describe(res.status, body));
}

export function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

// ---- questions -----------------------------------------------------------

export interface AskOptions {
  history?: ChatTurn[];
  /** Only search these files. Leave out to search everything. */
  sources?: string[];
  signal?: AbortSignal;
}

export interface StreamHandlers {
  /** A follow-up was rewritten into this standalone question before searching. */
  onQuery?: (question: string) => void;
  /** The next piece of the answer. */
  onToken: (text: string) => void;
}

/**
 * Ask a question and receive the answer piece by piece (Server-Sent Events).
 *
 * Resolves with the final result (answer, citations). Rejects with an `Error` whose message
 * can be shown to the person, or with an `AbortError` when `signal` is aborted.
 */
export async function askStream(
  question: string,
  handlers: StreamHandlers,
  options: AskOptions = {},
): Promise<AskResult> {
  if (DEMO_MODE) return demoStream(question, handlers, options);

  let res: Response;
  try {
    res = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: options.history ?? [],
        sources: options.sources,
      }),
      signal: options.signal,
    });
  } catch (err) {
    if (isAbort(err)) throw err;
    throw new Error("Could not reach the backend. Is `vectornote serve` running?");
  }
  if (!res.ok) throw await failure(res);
  if (!res.body) throw new Error("The browser did not provide a response stream.");

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let pending = "";
  let result: AskResult | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    pending += decoder.decode(value, { stream: !done });
    const parsed = parseSse(done ? pending + "\n\n" : pending);
    pending = parsed.rest;
    for (const event of parsed.events) {
      const data = JSON.parse(event.data) as Record<string, unknown>;
      if (event.event === "query") handlers.onQuery?.(String(data.question ?? ""));
      else if (event.event === "token") handlers.onToken(String(data.text ?? ""));
      else if (event.event === "done") result = data as unknown as AskResult;
      else if (event.event === "error") {
        throw new Error(String(data.detail ?? "The model failed while answering."));
      }
    }
    if (done) break;
  }
  if (result === null) throw new Error("The connection closed before the answer was complete.");
  return result;
}

async function demoStream(
  question: string,
  handlers: StreamHandlers,
  options: AskOptions,
): Promise<AskResult> {
  const { signal } = options;
  await sleep(500, signal);
  const result = demoResult(question, options.history, options.sources);
  if (result.standalone_question) handlers.onQuery?.(result.standalone_question);
  for (const word of result.answer.split(/(?<= )/)) {
    await sleep(35, signal);
    handlers.onToken(word);
  }
  return result;
}

// ---- documents -----------------------------------------------------------

let demoDocuments: DocumentInfo[] = [...DEMO_DOCUMENTS];

export async function listDocuments(): Promise<DocumentInfo[]> {
  if (DEMO_MODE) return [...demoDocuments];
  let res: Response;
  try {
    res = await fetch(`${API_URL}/documents`);
  } catch {
    throw new Error("Could not reach the backend.");
  }
  if (!res.ok) throw await failure(res);
  return (await res.json()) as DocumentInfo[];
}

/**
 * Upload one file and index it. `onProgress` reports the upload (bytes sent, bytes total);
 * once it reaches 100% the server is still reading and embedding the file, which is the
 * slow part for a large PDF.
 */
export function uploadDocument(
  file: File,
  onProgress: (loaded: number, total: number) => void,
): Promise<IngestResult> {
  if (DEMO_MODE) return demoUpload(file, onProgress);
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_URL}/ingest`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded, e.total);
    };
    xhr.onload = () => {
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // not JSON: fall back to the status message
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as IngestResult);
      else reject(new Error(describe(xhr.status, body)));
    };
    xhr.onerror = () => reject(new Error("Could not reach the backend."));
    xhr.send(form);
  });
}

async function demoUpload(
  file: File,
  onProgress: (loaded: number, total: number) => void,
): Promise<IngestResult> {
  const total = Math.max(file.size, 1);
  for (let step = 1; step <= 5; step++) {
    await sleep(120);
    onProgress((total * step) / 5, total);
  }
  await sleep(500);
  demoDocuments = [
    ...demoDocuments.filter((d) => d.name !== file.name),
    { name: file.name, size_bytes: file.size },
  ].sort((a, b) => a.name.localeCompare(b.name));
  return { filename: file.name, status: "added", chunks_added: 1 };
}

export async function deleteDocument(name: string): Promise<void> {
  if (DEMO_MODE) {
    demoDocuments = demoDocuments.filter((d) => d.name !== name);
    return;
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}/documents/${encodeURIComponent(name)}`, { method: "DELETE" });
  } catch {
    throw new Error("Could not reach the backend.");
  }
  if (!res.ok) throw await failure(res);
}
