import type { Source } from "./types";

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; number: number };

// "[1]", and also "[1, 2]" (the model sometimes groups citations); "[1][2]" is two matches.
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/** Splits an answer into plain text and citation markers, one marker per source number. */
export function splitAnswer(text: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: text.slice(last, start) });
    for (const number of match[1].split(",")) parts.push({ kind: "cite", number: Number(number) });
    last = start + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}

/** The answer followed by the list of sources it cites, as plain text for the clipboard. */
export function answerForClipboard(answer: string, sources: Source[] = []): string {
  if (sources.length === 0) return answer;
  const lines = sources.map((s) => `[${s.number}] ${s.source}, p. ${s.page}`);
  return `${answer}\n\nSources:\n${lines.join("\n")}`;
}

/** Copies text to the clipboard. Resolves to false when the browser refuses. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Not a secure page, or permission denied: try the older way below.
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

/** DOM id of a source card, so a citation marker can scroll to it. */
export function sourceDomId(messageId: string, number: number): string {
  return `src-${messageId}-${number}`;
}
