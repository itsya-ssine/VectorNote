import { InfoIcon } from "./icons";

export function DemoBanner() {
  return (
    <div className="banner" role="status">
      <InfoIcon size={16} />
      <span>
        <strong>Static demo.</strong> The RAG backend is not connected. Clone the repository and run
        it locally with Ollama for full offline inference.
      </span>
    </div>
  );
}
