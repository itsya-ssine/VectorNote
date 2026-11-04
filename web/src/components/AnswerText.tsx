import { splitAnswer } from "../lib/answer";
import type { Source } from "../lib/types";

interface Props {
  text: string;
  /** The sources of this answer. Markers without a matching source are shown but not clickable. */
  sources?: Source[];
  onCite: (number: number) => void;
}

/** Turns "[1]" citation markers in an answer into numbered chips that jump to the source. */
export function AnswerText({ text, sources, onCite }: Props) {
  return (
    <>
      {splitAnswer(text).map((part, i) => {
        if (part.kind === "text") return part.text;
        const source = sources?.find((s) => s.number === part.number);
        if (!source) {
          return (
            <span key={i} className="cite" aria-label={`Source ${part.number}`}>
              {part.number}
            </span>
          );
        }
        return (
          <button
            key={i}
            type="button"
            className="cite"
            title={`${source.source}, p. ${source.page}`}
            aria-label={`Source ${part.number}: ${source.source}, page ${source.page}`}
            onClick={() => onCite(part.number)}
          >
            {part.number}
          </button>
        );
      })}
    </>
  );
}
