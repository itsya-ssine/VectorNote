export interface Source {
  source: string;
  page: number;
  snippet: string;
  score: number;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  error?: boolean;
}

export interface DocumentInfo {
  name: string;
  size_bytes: number;
}
