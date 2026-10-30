import { useEffect, useRef, useState, type FormEvent } from "react";
import { ask } from "../lib/api";
import type { ChatMessage } from "../lib/types";
import { SourceCard } from "./SourceCard";

const SUGGESTIONS = [
  "What is a mutex and how can it cause a deadlock?",
  "How does a subnet mask work?",
];

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send(question: string) {
    const text = question.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { id: crypto.randomUUID(), role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await ask(text);
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "assistant", content: res.answer, sources: res.sources },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((m) => [
        ...m,
        { id: crypto.randomUUID(), role: "assistant", content: message, error: true },
      ]);
    } finally {
      setLoading(false);
    }
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
                <button key={s} className="chip" onClick={() => void send(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}${m.error ? " error" : ""}`}>
            <p>{m.content}</p>
            {m.sources && m.sources.length > 0 && (
              <details className="sources" open>
                <summary>{m.sources.length} source(s)</summary>
                <ul>
                  {m.sources.map((s, i) => (
                    <SourceCard key={`${s.source}-${s.page}-${i}`} source={s} />
                  ))}
                </ul>
              </details>
            )}
          </div>
        ))}

        {loading && <div className="msg assistant typing">Thinking...</div>}
        <div ref={bottom} />
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question about your documents"
          aria-label="Question"
        />
        <button type="submit" disabled={loading || input.trim() === ""}>
          Send
        </button>
      </form>
    </section>
  );
}
