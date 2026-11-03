export interface Source {
  number: number;
  source: string;
  page: number;
  snippet: string;
  score: number;
}

/** The final result of a question, as returned by `/ask` and by the `done` stream event. */
export interface AskResult {
  answer: string;
  answered: boolean;
  standalone_question: string;
  cited: boolean;
  sources: Source[];
}

/** One earlier message, in the shape the API expects for follow-up questions. */
export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  /** The question as it was rewritten for searching (follow-ups only). */
  searchedFor?: string;
  /** False when the assistant said it could not find the answer in the documents. */
  answered?: boolean;
  streaming?: boolean;
  stopped?: boolean;
  error?: boolean;
}

export interface DocumentInfo {
  name: string;
  size_bytes: number;
}

export interface IngestResult {
  filename: string;
  status: string;
  chunks_added: number;
}

export type UploadPhase = "uploading" | "indexing" | "done" | "error";

export interface UploadItem {
  id: string;
  name: string;
  /** 0 to 100, only meaningful while uploading. */
  percent: number;
  phase: UploadPhase;
  message?: string;
}
