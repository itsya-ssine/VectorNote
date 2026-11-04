import { useEffect, useRef, useState } from "react";
import { copyText } from "../lib/answer";
import { CheckIcon, CopyIcon } from "./icons";

interface Props {
  /** Called when the button is pressed, so the text is always the latest one. */
  getText: () => string;
  label?: string;
  /** Icon only, for tight spaces. The label is still used for screen readers. */
  compact?: boolean;
}

export function CopyButton({ getText, label = "Copy", compact = false }: Props) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function onClick() {
    const ok = await copyText(getText());
    setState(ok ? "copied" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1800);
  }

  const text = state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : label;
  return (
    <button
      type="button"
      className={`action-btn${compact ? " compact" : ""}${state === "failed" ? " failed" : ""}`}
      onClick={() => void onClick()}
      aria-label={compact ? label : undefined}
      title={compact ? text : undefined}
    >
      {state === "copied" ? <CheckIcon size={14} /> : <CopyIcon size={14} />}
      {!compact && <span>{text}</span>}
      <span className="sr-only" role="status">
        {state === "copied" ? "Copied to clipboard" : state === "failed" ? "Copy failed" : ""}
      </span>
    </button>
  );
}
