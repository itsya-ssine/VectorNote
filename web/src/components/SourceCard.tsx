import { useState } from "react";
import type { Source } from "../lib/types";
import { CopyButton } from "./CopyButton";

// The card shows about three lines; a longer passage gets a "Show more" toggle.
const LONG_SNIPPET = 120;

interface Props {
  source: Source;
  /** DOM id, used by the citation markers in the answer to scroll here. */
  id: string;
  /** True for a moment after the person clicked the matching citation. */
  highlighted?: boolean;
}

export function SourceCard({ source, id, highlighted = false }: Props) {
  const [expanded, setExpanded] = useState(false);
  const long = source.snippet.length > LONG_SNIPPET;

  return (
    <li id={id} tabIndex={-1} className={`source${highlighted ? " highlight" : ""}`}>
      <div className="source-head">
        <span className="source-number" aria-label={`Source ${source.number}`}>
          {source.number}
        </span>
        <span className="source-file" title={source.source}>
          {source.source}
        </span>
        <span className="source-page">p. {source.page}</span>
        <CopyButton
          compact
          label="Copy passage"
          getText={() => `${source.snippet}\n— ${source.source}, p. ${source.page}`}
        />
      </div>
      <p className={`source-snippet${expanded ? " expanded" : ""}`}>{source.snippet}</p>
      {long && (
        <button
          type="button"
          className="source-more"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      )}
    </li>
  );
}
