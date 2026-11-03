import { useMemo, useState } from "react";
import { Chat } from "./components/Chat";
import { DemoBanner } from "./components/DemoBanner";
import { Sidebar } from "./components/Sidebar";
import { DEMO_MODE } from "./lib/api";

export default function App() {
  const [documents, setDocuments] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);

  // No filter at all unless the person unticked something, so new uploads are searched by default.
  const sources = useMemo(
    () => (excluded.length === 0 ? undefined : documents.filter((d) => !excluded.includes(d))),
    [documents, excluded],
  );

  return (
    <div className="shell">
      {DEMO_MODE && <DemoBanner />}
      <div className="layout">
        <Sidebar
          excluded={excluded}
          onExcludedChange={setExcluded}
          onDocumentsChange={setDocuments}
        />
        <main className="main">
          <Chat sources={sources} />
        </main>
      </div>
    </div>
  );
}
