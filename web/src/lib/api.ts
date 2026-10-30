import { DEMO_DOCUMENTS, demoAnswer } from "./demo";
import type { AskResponse, DocumentInfo } from "./types";

export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";
export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function failure(res: Response): Promise<Error> {
  let detail = `Request failed (${res.status})`;
  try {
    const body = (await res.json()) as { detail?: string };
    if (body.detail) detail = body.detail;
  } catch {
    // keep the default message
  }
  return new Error(detail);
}

export async function ask(question: string, topK = 5): Promise<AskResponse> {
  if (DEMO_MODE) return demoAnswer(question);
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, top_k: topK }),
  });
  if (!res.ok) throw await failure(res);
  return (await res.json()) as AskResponse;
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  if (DEMO_MODE) return DEMO_DOCUMENTS;
  const res = await fetch(`${API_URL}/documents`);
  if (!res.ok) throw await failure(res);
  return (await res.json()) as DocumentInfo[];
}

export async function uploadDocument(file: File): Promise<void> {
  if (DEMO_MODE) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    return;
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/ingest`, { method: "POST", body: form });
  if (!res.ok) throw await failure(res);
}
