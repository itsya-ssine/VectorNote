import { useEffect, useRef, useState, type FormEvent } from "react";
import { MAX_HISTORY, askStream, isAbort } from "../lib/api";
import type { ChatMessage, ChatTurn } from "../lib/types";
import { SourceCard } from "./SourceCard";

const SUGGESTIONS = [
  "What is a mutex and how can it cause a deadlock?",
  "How does a subnet mask work?",
];

const MAX_TURN_CHARS = 8000; // the API rejects longer messages

interface Props {
  /** Files to search in, or undefined to search everything. */
  sources?: string[];
}

function historyOf(messages: ChatMessage[]): ChatTurn[] {
  return messages
    .filter((m) => !m.error && m.content.trim() !== "")
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_TURN_CHARS) }));
}

export function Chat({ sources }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  const nothingSelected = sources !== undefined && sources.length === 0;

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy]);

  // Leaving the page stops the model instead of letting it write for nobody.
  useEffect(() => () => abort.current?.abort(), []);

  function patch(id: string, change: (m: ChatMessage) => ChatMessage) {
    setMessages((all) => all.map((m) => (m.id === id ? change(m) : m)));
  }

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy || nothingSelected) return;

    const history = historyOf(messages);
    const replyId = crypto.randomUUID();
    setInput("");
    setMessages((all) => [
      ...all,
      { id: crypto.randomUUID(), role: "user", content: text },
      { id: replyId, role: "assistant", content: "", streaming: true },
    ]);
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;

    try {
      const result = await askStream(
        text,
        {
          onQuery: (q) => patch(replyId, (m) => ({ ...m, searchedFor: q })),
          onToken: (piece) => patch(replyId, (m) => ({ ...m, content: m.content + piece })),
        },
        { history, sources, signal: controller.signal },
      );
      patch(replyId, (m) => ({
        ...m,
        content: result.answer,
        sources: result.sources,
        answered: result.answered,
        streaming: false,
      }));
    } catch (err) {
      if (isAbort(err)) {
        patch(replyId, (m) => ({ ...m, streaming: false, stopped: true }));
      } else {
        const message = err instanceof Error ? err.message : "Something went wrong.";
        patch(replyId, (m) => ({
          ...m,
          content: m.content ? `${m.content}\n\n${message}` : message,
          streaming: false,
          error: true,
        }));
      }
    } finally {
      abort.current = null;
      setBusy(false);
    }
  }

  function stop() {
    abort.current?.abort();
  }

  function reset() {
    abort.current?.abort();
    setMessages([]);
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  return (
    <section className="chat">
      <div className="messages">
        {messages.length === 0 && (
          <div className="welcome">
            <h2>Ask anything about your notes</h2>
            <p>Answers come only from your documents, with the page they were found on.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  className="chip"
                  disabled={nothingSelected}
                  onClick={() => void send(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={
              `msg ${m.role}` +
              (m.error ? " error" : "") +
              (m.answered === false ? " refused" : "")
            }
          >
            {m.searchedFor && <p className="searched">Searching for: {m.searchedFor}</p>}
            {m.streaming && m.content === "" ? (
              <p className="typing">Searching your documents...</p>
            ) : (
              <p>
                {m.content}
                {m.streaming && <span className="cursor" aria-hidden="true" />}
              </p>
            )}
            {m.stopped && <p className="stopped">Stopped.</p>}
            {m.sources && m.sources.length > 0 && (
              <details className="sources" open>
                <summary>{m.sources.length} source(s)</summary>
                <ul>
                  {m.sources.map((s) => (
                    <SourceCard key={`${s.number}-${s.source}-${s.page}`} source={s} />
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {messages.length > 0 && (
        <div className="chat-tools">
          <button className="link" onClick={reset}>
            New conversation
          </button>
        </div>
      )}

      {sources !== undefined && (
        <p className="filter-note" role="status">
          {nothingSelected
            ? "No document is selected. Tick at least one in the sidebar."
            : `Searching only in ${sources.length} selected document${sources.length === 1 ? "" : "s"}.`}
        </p>
      )}

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your documents"
          aria-label="Question"
          disabled={nothingSelected}
        />
        {busy ? (
          <button type="button" className="stop" onClick={stop}>
            Stop
          </button>
        ) : (
          <button type="submit" disabled={nothingSelected || input.trim() === ""}>
            Send
          </button>
        )}
      </form>
    </section>
  );
}
