import { InfoIcon } from "./icons";

const LOCAL_URL = "https://github.com/itsya-ssine/VectorNote#quick-start";

export function DemoBanner() {
  return (
    <div className="banner" role="status">
      <InfoIcon size={16} />
      <span>
        <strong>Static demo.</strong> Answers are canned and nothing you type leaves your browser.
        VectorNote runs fully offline on your own documents:{" "}
        <a href={LOCAL_URL} target="_blank" rel="noopener noreferrer">
          run it locally
        </a>
        .
      </span>
    </div>
  );
}
