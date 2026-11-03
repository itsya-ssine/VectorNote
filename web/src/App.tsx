import { useCallback, useMemo, useState } from "react";
import { Chat } from "./components/Chat";
import { DemoBanner } from "./components/DemoBanner";
import { Sidebar } from "./components/Sidebar";
import { DEMO_MODE } from "./lib/api";

export default function App() {
  const [documents, setDocuments] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  const closeNav = useCallback(() => setNavOpen(false), []);

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
          open={navOpen}
          onClose={closeNav}
          excluded={excluded}
          onExcludedChange={setExcluded}
          onDocumentsChange={setDocuments}
        />
        {navOpen && <div className="backdrop" onClick={closeNav} aria-hidden="true" />}
        <main className="main">
          <Chat sources={sources} onOpenNav={() => setNavOpen(true)} />
        </main>
      </div>
    </div>
  );
}
