import { useEffect, useRef, useState, type FormEvent, type UIEvent } from "react";
import { MAX_HISTORY, askStream, isAbort } from "../lib/api";
import type { ChatMessage, ChatTurn } from "../lib/types";
import { answerForClipboard, sourceDomId } from "../lib/answer";
import { AnswerText } from "./AnswerText";
import { CopyButton } from "./CopyButton";
import {
  ArrowDownIcon,
  ArrowIcon,
  ChevronIcon,
  LogoMark,
  MenuIcon,
  PlusIcon,
  RetryIcon,
  SendIcon,
  StopIcon,
} from "./icons";
import { SourceCard } from "./SourceCard";

const SUGGESTIONS = [
  "What is a mutex and how can it cause a deadlock?",
  "How does a subnet mask work?",
];

const MAX_TURN_CHARS = 8000; // the API rejects longer messages

interface Props {
  /** Files to search in, or undefined to search everything. */
  sources?: string[];
  /** False when no document is indexed yet; undefined while the list is still loading. */
  hasDocuments?: boolean;
  /** Opens the document sidebar (small screens only). */
  onOpenNav: () => void;
}

function historyOf(messages: ChatMessage[]): ChatTurn[] {
  return messages
    .filter((m) => !m.error && m.content.trim() !== "")
    .slice(-MAX_HISTORY)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_TURN_CHARS) }));
}

export function Chat({ sources, hasDocuments, onOpenNav }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  // Follow the answer as it streams, unless the person scrolled up to read something.
  const following = useRef(true);
  const [away, setAway] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const [highlight, setHighlight] = useState<{ messageId: string; number: number } | null>(null);

  const noDocuments = hasDocuments === false;
  const nothingSelected = sources !== undefined && sources.length === 0;
  const blocked = noDocuments || nothingSelected;

  useEffect(() => {
    if (!following.current) return;
    bottom.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy]);

  function onScroll(e: UIEvent<HTMLDivElement>) {
    const el = e.currentTarget;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    following.current = atBottom;
    setAway(!atBottom);
  }

  function jumpToLatest() {
    following.current = true;
    setAway(false);
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }

  // Keyboard shortcuts: "/" focuses the question, Esc stops the answer, Alt+N starts over.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.defaultPrevented) return;
      const target = e.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.isContentEditable;
      if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        field.current?.focus();
      } else if (e.key === "Escape" && abort.current) {
        abort.current.abort();
      } else if (e.altKey && e.code === "KeyN") {
        e.preventDefault();
        reset();
        field.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // reset only uses a ref and a state setter, so the first version is always current.
  }, []);

  // Leaving the page stops the model instead of letting it write for nobody.
  useEffect(() => () => abort.current?.abort(), []);

  // The highlight of a clicked citation fades after a moment.
  useEffect(() => {
    if (!highlight) return;
    const timer = window.setTimeout(() => setHighlight(null), 1800);
    return () => window.clearTimeout(timer);
  }, [highlight]);

  function patch(id: string, change: (m: ChatMessage) => ChatMessage) {
    setMessages((all) => all.map((m) => (m.id === id ? change(m) : m)));
  }

  /** `base` is the conversation the question continues; a retry passes the messages before it. */
  async function send(question: string, base: ChatMessage[] = messages) {
    const text = question.trim();
    if (!text || busy || blocked) return;

    const history = historyOf(base);
    const replyId = crypto.randomUUID();
    setInput("");
    following.current = true;
    setAway(false);
    setMessages([
      ...base,
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

  /** Asks the question of a failed reply again, replacing the failed exchange. */
  function retry(replyId: string) {
    const index = messages.findIndex((m) => m.id === replyId);
    const question = index > 0 ? messages[index - 1] : undefined;
    if (!question || question.role !== "user") return;
    void send(question.content, messages.slice(0, index - 1));
  }

  /** A citation marker was pressed: open the sources, scroll to the card and flash it. */
  function openSource(messageId: string, number: number) {
    const card = document.getElementById(sourceDomId(messageId, number));
    if (!card) return;
    const details = card.closest("details");
    if (details) details.open = true;
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    card.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "nearest" });
    card.focus({ preventScroll: true });
    setHighlight({ messageId, number });
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  const scope = noDocuments
    ? "No documents yet"
    : sources === undefined
      ? "All documents"
      : nothingSelected
        ? "No document selected"
        : `${sources.length} document${sources.length === 1 ? "" : "s"} selected`;

  return (
    <section className="chat">
      <header className="chat-header">
        <button className="icon-btn menu-btn" aria-label="Open documents" onClick={onOpenNav}>
          <MenuIcon />
        </button>
        <div className="chat-title">
          <h2>Chat</h2>
          <span className={`pill${blocked ? " warn" : ""}`} role="status">
            {scope}
          </span>
        </div>
        {messages.length > 0 && (
          <button className="btn-ghost" onClick={reset}>
            <PlusIcon size={16} />
            New chat
          </button>
        )}
      </header>

      <div className="scroll" onScroll={onScroll}>
        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-logo">
                <LogoMark size={52} />
              </div>
              {noDocuments ? (
                <>
                  <h2>Add a document to get started</h2>
                  <p>
                    Upload a PDF, Markdown or text file in the sidebar. VectorNote indexes it on
                    your machine, then answers with the page each passage came from.
                  </p>
                  <button className="btn-ghost mobile-only" onClick={onOpenNav}>
                    Open documents
                  </button>
                </>
              ) : (
                <>
                  <h2>Ask anything about your notes</h2>
                  <p>Answers come only from your documents, with the page they were found on.</p>
                  <div className="suggestions">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        className="chip"
                        disabled={blocked}
                        onClick={() => void send(s)}
                      >
                        <span>{s}</span>
                        <ArrowIcon size={16} />
                      </button>
                    ))}
                  </div>
                  {nothingSelected && (
                    <p className="welcome-note">Tick at least one document in the sidebar to start.</p>
                  )}
                </>
              )}
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
              {m.role === "assistant" && (
                <div className="avatar">
                  <LogoMark size={28} />
                </div>
              )}
              <div className="msg-body">
                {m.searchedFor && <p className="searched">Searching for: {m.searchedFor}</p>}
                {m.streaming && m.content === "" ? (
                  <p className="typing" aria-label="Searching your documents">
                    <span className="dots" aria-hidden="true">
                      <i />
                      <i />
                      <i />
                    </span>
                    Searching your documents
                  </p>
                ) : (
                  <p>
                    {m.role === "assistant" ? (
                      <AnswerText
                        text={m.content}
                        sources={m.sources}
                        onCite={(n) => openSource(m.id, n)}
                      />
                    ) : (
                      m.content
                    )}
                    {m.streaming && <span className="cursor" aria-hidden="true" />}
                  </p>
                )}
                {m.stopped && <p className="stopped">Stopped.</p>}
                {m.answered === false && !m.streaming && (
                  <p className="refused-hint">
                    Try rephrasing the question, or check which documents are ticked in the sidebar.
                  </p>
                )}
                {m.sources && m.sources.length > 0 && (
                  <details className="sources" open>
                    <summary>
                      <ChevronIcon size={14} className="chevron" />
                      {m.sources.length} source{m.sources.length === 1 ? "" : "s"}
                    </summary>
                    <ul>
                      {m.sources.map((s) => (
                        <SourceCard
                          key={`${s.number}-${s.source}-${s.page}`}
                          id={sourceDomId(m.id, s.number)}
                          source={s}
                          highlighted={highlight?.messageId === m.id && highlight.number === s.number}
                        />
                      ))}
                    </ul>
                  </details>
                )}
                {m.role === "assistant" && !m.streaming && m.content !== "" && (
                  <div className="msg-actions">
                    {m.error ? (
                      <button
                        type="button"
                        className="action-btn"
                        disabled={busy || blocked}
                        onClick={() => retry(m.id)}
                      >
                        <RetryIcon size={14} />
                        <span>Try again</span>
                      </button>
                    ) : (
                      m.answered !== false && (
                        <CopyButton getText={() => answerForClipboard(m.content, m.sources)} />
                      )
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <div className="jump-wrap">
          {away && messages.length > 0 && (
            <button type="button" className="jump" onClick={jumpToLatest}>
              <ArrowDownIcon size={14} />
              {busy ? "Follow answer" : "Latest"}
            </button>
          )}
        </div>
      </div>

      <div className="composer-wrap">
        <form className="composer" onSubmit={onSubmit}>
          <input
            ref={field}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={
              noDocuments ? "Upload a document to start asking" : "Ask a question about your documents"
            }
            aria-label="Question"
            disabled={blocked}
          />
          {busy ? (
            <button type="button" className="send stop" onClick={stop} aria-label="Stop generating">
              <StopIcon size={16} />
            </button>
          ) : (
            <button
              type="submit"
              className="send"
              aria-label="Send"
              disabled={blocked || input.trim() === ""}
            >
              <SendIcon size={18} />
            </button>
          )}
        </form>
        <p className="composer-note">
          Answers are generated locally and grounded in your documents.
          <span className="shortcuts">
            <kbd>/</kbd> ask <kbd>Esc</kbd> stop <kbd>Alt</kbd>+<kbd>N</kbd> new chat
          </span>
        </p>
      </div>
    </section>
  );
}
