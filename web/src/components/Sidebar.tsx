import { useEffect, useRef, useState } from "react";
import { listDocuments, uploadDocument } from "../lib/api";
import type { DocumentInfo } from "../lib/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function Sidebar() {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setDocs(await listDocuments());
    } catch {
      setStatus("Could not reach the backend.");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setStatus("Uploading...");
    try {
      for (const file of Array.from(files)) await uploadDocument(file);
      setStatus(null);
      await refresh();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Upload failed.");
    }
  }

  return (
    <aside className="sidebar">
      <h1 className="brand">VectorNote</h1>
      <p className="tagline">Offline study assistant</p>

      <button className="upload" onClick={() => input.current?.click()}>
        Upload documents
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,.md,.txt"
        hidden
        onChange={(e) => void onFiles(e.target.files)}
      />
      {status && <p className="status">{status}</p>}

      <h2 className="section-title">Documents</h2>
      <ul className="docs">
        {docs.length === 0 && <li className="empty">No documents yet.</li>}
        {docs.map((d) => (
          <li key={d.name} className="doc">
            <span className="doc-name">{d.name}</span>
            <span className="doc-size">{formatSize(d.size_bytes)}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}
