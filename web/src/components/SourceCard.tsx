import type { Source } from "../lib/types";

export function SourceCard({ source }: { source: Source }) {
  return (
    <li className="source">
      <div className="source-head">
        <span className="source-number" aria-label={`Source ${source.number}`}>
          {source.number}
        </span>
        <span className="source-file" title={source.source}>
          {source.source}
        </span>
        <span className="source-page">p. {source.page}</span>
      </div>
      <p className="source-snippet">{source.snippet}</p>
    </li>
  );
}
