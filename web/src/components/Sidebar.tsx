import { useCallback, useEffect, useRef, useState } from "react";
import { deleteDocument, listDocuments, uploadDocument } from "../lib/api";
import type { DocumentInfo, UploadItem } from "../lib/types";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function resultMessage(status: string, chunks: number): string {
  if (status === "unchanged") return "Already indexed, nothing changed.";
  const verb = status === "updated" ? "Updated" : "Indexed";
  return `${verb}: ${chunks} passage${chunks === 1 ? "" : "s"}.`;
}

interface Props {
  /** Names of the files that are left out of searches. */
  excluded: string[];
  onExcludedChange: (names: string[]) => void;
  /** Called with the current file names whenever the list changes. */
  onDocumentsChange: (names: string[]) => void;
}

export function Sidebar({ excluded, onExcludedChange, onDocumentsChange }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listDocuments();
      setDocs(list);
      setLoadError(null);
      onDocumentsChange(list.map((d) => d.name));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load the documents.");
    }
  }, [onDocumentsChange]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function updateUpload(id: string, change: Partial<UploadItem>) {
    setUploads((all) => all.map((u) => (u.id === id ? { ...u, ...change } : u)));
  }

  async function onFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    const batch = Array.from(files);
    const items: UploadItem[] = batch.map((file) => ({
      id: crypto.randomUUID(),
      name: file.name,
      percent: 0,
      phase: "uploading",
    }));
    setNotice(null);
    setUploads(items);
    setUploading(true);
    // One file at a time: indexing is heavy, and a failure should not stop the others.
    for (const [index, file] of batch.entries()) {
      const id = items[index].id;
      try {
        const result = await uploadDocument(file, (loaded, total) => {
          const percent = Math.round((loaded / total) * 100);
          updateUpload(id, percent >= 100 ? { percent, phase: "indexing" } : { percent });
        });
        updateUpload(id, {
          phase: "done",
          percent: 100,
          message: resultMessage(result.status, result.chunks_added),
        });
      } catch (err) {
        updateUpload(id, {
          phase: "error",
          message: err instanceof Error ? err.message : "Upload failed.",
        });
      }
    }
    setUploading(false);
    if (input.current) input.current.value = ""; // allow choosing the same file again
    await refresh();
  }

  async function onDelete(name: string) {
    if (!window.confirm(`Remove "${name}" and its indexed passages?`)) return;
    setDeleting(name);
    setNotice(null);
    try {
      await deleteDocument(name);
      onExcludedChange(excluded.filter((n) => n !== name));
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Could not remove the document.");
    } finally {
      setDeleting(null);
    }
  }

  function toggle(name: string) {
    onExcludedChange(
      excluded.includes(name) ? excluded.filter((n) => n !== name) : [...excluded, name],
    );
  }

  return (
    <aside className="sidebar">
      <h1 className="brand">VectorNote</h1>
      <p className="tagline">Offline study assistant</p>

      <button className="upload" disabled={uploading} onClick={() => input.current?.click()}>
        {uploading ? "Uploading..." : "Upload documents"}
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept=".pdf,.md,.txt"
        hidden
        onChange={(e) => void onFiles(e.target.files)}
      />

      {uploads.length > 0 && (
        <ul className="uploads" aria-live="polite">
          {uploads.map((u) => (
            <li key={u.id} className={`upload-item ${u.phase}`}>
              <span className="doc-name">{u.name}</span>
              {u.phase === "uploading" && (
                <progress value={u.percent} max={100} aria-label={`Uploading ${u.name}`} />
              )}
              {u.phase === "indexing" && <span className="status">Indexing, this can take a while...</span>}
              {(u.phase === "done" || u.phase === "error") && (
                <span className={u.phase === "error" ? "status failed" : "status"}>{u.message}</span>
              )}
            </li>
          ))}
        </ul>
      )}

      {notice && <p className="status failed">{notice}</p>}

      <h2 className="section-title">Documents</h2>
      {loadError && (
        <p className="status failed">
          {loadError}{" "}
          <button className="link" onClick={() => void refresh()}>
            Retry
          </button>
        </p>
      )}
      <ul className="docs">
        {docs.length === 0 && !loadError && <li className="empty">No documents yet.</li>}
        {docs.map((d) => (
          <li key={d.name} className="doc">
            <label className="doc-pick" title="Include in searches">
              <input
                type="checkbox"
                checked={!excluded.includes(d.name)}
                onChange={() => toggle(d.name)}
              />
              <span className="doc-name">{d.name}</span>
            </label>
            <span className="doc-size">{formatSize(d.size_bytes)}</span>
            <button
              className="doc-delete"
              aria-label={`Remove ${d.name}`}
              disabled={deleting === d.name}
              onClick={() => void onDelete(d.name)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      {docs.length > 1 && (
        <p className="hint">Untick a document to leave it out of the search.</p>
      )}
    </aside>
  );
}
