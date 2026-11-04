import { useCallback, useEffect, useMemo, useState } from "react";
import { Chat } from "./components/Chat";
import { DemoBanner } from "./components/DemoBanner";
import { Sidebar } from "./components/Sidebar";
import { DEMO_MODE } from "./lib/api";

export default function App() {
  const [documents, setDocuments] = useState<string[]>([]);
  const [documentsLoaded, setDocumentsLoaded] = useState(false);
  const [excluded, setExcluded] = useState<string[]>([]);
  const [navOpen, setNavOpen] = useState(false);
  const closeNav = useCallback(() => setNavOpen(false), []);
  useEffect(() => {
    if (!navOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeNav();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen, closeNav]);

  const onDocumentsChange = useCallback((names: string[]) => {
    setDocuments(names);
    setDocumentsLoaded(true);
  }, []);

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
          onDocumentsChange={onDocumentsChange}
        />
        {navOpen && <div className="backdrop" onClick={closeNav} aria-hidden="true" />}
        <main className="main">
          <Chat
            sources={sources}
            hasDocuments={documentsLoaded ? documents.length > 0 : undefined}
            onOpenNav={() => setNavOpen(true)}
          />
        </main>
      </div>
    </div>
  );
}
