import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { DEMO_MODE, deleteDocument, listDocuments, uploadDocument } from "../lib/api";
import type { DocumentInfo, UploadItem } from "../lib/types";
import { CloseIcon, LockIcon, LogoMark, TrashIcon, UploadIcon } from "./icons";

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

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot === -1 ? "FILE" : name.slice(dot + 1, dot + 5).toUpperCase();
}

interface Props {
  /** Whether the sidebar is shown as a drawer (small screens only). */
  open: boolean;
  onClose: () => void;
  /** Names of the files that are left out of searches. */
  excluded: string[];
  onExcludedChange: (names: string[]) => void;
  /** Called with the current file names whenever the list changes. */
  onDocumentsChange: (names: string[]) => void;
}

export function Sidebar({ open, onClose, excluded, onExcludedChange, onDocumentsChange }: Props) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadItem[]>([]);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(true);
  const input = useRef<HTMLInputElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await listDocuments();
      setDocs(list);
      setLoadError(null);
      onDocumentsChange(list.map((d) => d.name));
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load the documents.");
    } finally {
      setLoading(false);
    }
  }, [onDocumentsChange]);

  // When the drawer opens on a small screen, keyboard focus moves into it.
  useEffect(() => {
    if (open) closeButton.current?.focus();
  }, [open]);

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

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!uploading) void onFiles(e.dataTransfer.files);
  }

  function toggle(name: string) {
    onExcludedChange(
      excluded.includes(name) ? excluded.filter((n) => n !== name) : [...excluded, name],
    );
  }

  return (
    <aside className={`sidebar${open ? " open" : ""}`} aria-label="Documents">
      <div className="sidebar-head">
        <div className="brand-row">
          <LogoMark size={34} />
          <div className="brand-text">
            <h1 className="brand">VectorNote</h1>
            <p className="tagline">Offline study assistant</p>
          </div>
          <button
            ref={closeButton}
            className="icon-btn sidebar-close"
            aria-label="Close sidebar"
            onClick={onClose}
          >
            <CloseIcon />
          </button>
        </div>

        <button
          className={`dropzone${dragging ? " dragging" : ""}`}
          disabled={uploading}
          onClick={() => input.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            if (!uploading) setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <span className="dropzone-icon">
            <UploadIcon size={18} />
          </span>
          <span className="dropzone-title">{uploading ? "Uploading..." : "Upload documents"}</span>
          <span className="dropzone-sub">PDF, Markdown or text. Drop files here.</span>
        </button>
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.md,.txt"
          hidden
          onChange={(e) => void onFiles(e.target.files)}
        />
      </div>

      <div className="sidebar-body">
        {uploads.length > 0 && (
          <ul className="uploads" aria-live="polite">
            {uploads.map((u) => (
              <li key={u.id} className={`upload-item ${u.phase}`}>
                <span className="doc-name">{u.name}</span>
                {u.phase === "uploading" && (
                  <progress value={u.percent} max={100} aria-label={`Uploading ${u.name}`} />
                )}
                {u.phase === "indexing" && (
                  <span className="status">Indexing, this can take a while...</span>
                )}
                {(u.phase === "done" || u.phase === "error") && (
                  <span className={u.phase === "error" ? "status failed" : "status"}>
                    {u.message}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}

        {notice && <p className="status failed">{notice}</p>}

        <h2 className="section-title">
          Documents
          {docs.length > 0 && <span className="count">{docs.length}</span>}
        </h2>
        {loadError && (
          <p className="status failed">
            {loadError}{" "}
            <button className="link" onClick={() => void refresh()}>
              Retry
            </button>
          </p>
        )}
        <ul className="docs" aria-busy={loading}>
          {loading &&
            [0, 1, 2].map((i) => (
              <li key={i} className="skeleton-row" aria-hidden="true">
                <span className="skeleton skeleton-badge" />
                <span className="skeleton-lines">
                  <span className="skeleton skeleton-line" />
                  <span className="skeleton skeleton-line short" />
                </span>
              </li>
            ))}
          {!loading && docs.length === 0 && !loadError && (
            <li className="empty">No documents yet.</li>
          )}
          {docs.map((d) => {
            const off = excluded.includes(d.name);
            return (
              <li key={d.name} className={`doc${off ? " off" : ""}`}>
                <label className="doc-pick" title="Include in searches">
                  <input type="checkbox" checked={!off} onChange={() => toggle(d.name)} />
                  <span className="file-badge" aria-hidden="true">
                    {extensionOf(d.name)}
                  </span>
                  <span className="doc-meta">
                    <span className="doc-name" title={d.name}>
                      {d.name}
                    </span>
                    <span className="doc-size">{formatSize(d.size_bytes)}</span>
                  </span>
                </label>
                <button
                  className="doc-delete"
                  aria-label={`Remove ${d.name}`}
                  title="Remove"
                  disabled={deleting === d.name}
                  onClick={() => void onDelete(d.name)}
                >
                  <TrashIcon size={16} />
                </button>
              </li>
            );
          })}
        </ul>
        {docs.length > 1 && <p className="hint">Untick a document to leave it out of the search.</p>}
      </div>

      {!DEMO_MODE && (
        <div className="sidebar-foot">
          <LockIcon size={14} />
          <span>Runs locally. Your files never leave this machine.</span>
        </div>
      )}
    </aside>
  );
}
