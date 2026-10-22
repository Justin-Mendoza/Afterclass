"use client";

import { useEffect, useRef, useState } from "react";
import {
  aborted,
  api,
  listAll,
  message,
  uploadFile,
  workspacePath,
  type Capabilities,
  type Collection,
  type Document,
  type Job,
  type Upload,
} from "../lib/api";
import { Icon } from "./icons";

export function Documents({
  identity,
  workspace,
  collection,
  capabilities,
  onChange,
}: {
  identity: string;
  workspace: string;
  collection: Collection;
  capabilities: Capabilities;
  onChange: () => void;
}) {
  const [documents, setDocuments] = useState<Document[] | null>(null);
  const [error, setError] = useState("");
  const [upload, setUpload] = useState<{ file: File; key: string } | null>(
    null,
  );
  const [progress, setProgress] = useState<number | null>(null);
  const [ticket, setTicket] = useState<Upload | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [jobError, setJobError] = useState("");
  const [reload, setReload] = useState(0);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const uploadController = useRef<AbortController | null>(null);
  const base = workspacePath(workspace, `/collections/${collection.id}`);
  useEffect(() => () => uploadController.current?.abort(), []);
  useEffect(() => {
    const controller = new AbortController();
    listAll<Document>(`${base}/documents`, identity, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) {
          setDocuments(rows);
          setError("");
        }
      })
      .catch((e) => {
        if (!aborted(e)) setError(message(e));
      });
    return () => controller.abort();
  }, [base, identity, reload]);
  useEffect(() => {
    if (!ticket) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Job>(
          workspacePath(workspace, `/jobs/${ticket!.job_id}`),
          identity,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setJob(next);
        setJobError("");
        if (["succeeded", "failed", "cancelled"].includes(next.status)) {
          setReload((v) => v + 1);
          onChange();
        } else timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!aborted(e))
          setJobError(
            "Could not check processing status. Your upload is saved; check again below.",
          );
      }
    }
    void poll();
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [ticket, workspace, identity, onChange]);
  async function send(file: File, key: string) {
    uploadController.current?.abort();
    const controller = new AbortController();
    uploadController.current = controller;
    setUpload({ file, key });
    setProgress(0);
    setTicket(null);
    setJob(null);
    setError("");
    setJobError("");
    try {
      const receipt = await uploadFile(
        `${base}/documents`,
        identity,
        file,
        key,
        controller.signal,
        setProgress,
      );
      if (!controller.signal.aborted) {
        setTicket(receipt);
        setProgress(null);
        setReload((v) => v + 1);
        onChange();
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(message(e));
        setProgress(null);
      }
    }
  }
  function choose(file: File | undefined) {
    if (file && progress === null) void send(file, crypto.randomUUID());
  }
  async function remove(document: Document) {
    if (
      !window.confirm(
        `Delete “${document.original_filename}” and remove it from search?`,
      )
    )
      return;
    try {
      await api(
        `${workspacePath(workspace, `/documents/${document.id}`)}`,
        identity,
        { method: "DELETE" },
      );
      setReload((v) => v + 1);
      onChange();
    } catch (e) {
      setError(message(e));
    }
  }
  return (
    <section
      className="view-enter documents-view"
      aria-labelledby="documents-title"
    >
      <div className="section-heading">
        <div>
          <p className="eyebrow">Your source material</p>
          <h1 id="documents-title">
            Make room for ideas<span className="pencil-dot">.</span>
          </h1>
          <p className="muted">
            Add files to <strong>{collection.name}</strong>. They become
            searchable when processing finishes.
          </p>
        </div>
        <span className="hand-note">start with what you know ↙</span>
      </div>
      {capabilities.can_upload ? (
        <div
          className={`upload-zone sketch-border ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            choose(e.dataTransfer.files[0]);
          }}
        >
          <span className="icon-bubble">
            <Icon name="upload" size={28} />
          </span>
          <h2>Drop a document here</h2>
          <p className="muted">
            PDF, plain text, Markdown, or HTML · up to 20 MB
          </p>
          <input
            ref={fileInput}
            tabIndex={-1}
            type="file"
            accept=".pdf,.txt,.md,.markdown,.html,.htm"
            aria-label="Choose a document to upload"
            onChange={(e) => {
              choose(e.target.files?.[0]);
              e.target.value = "";
            }}
            className="visually-hidden"
          />
          <button
            className="button primary"
            disabled={progress !== null}
            onClick={() => fileInput.current?.click()}
          >
            <Icon name="plus" />
            {progress !== null ? "Uploading…" : "Choose a file"}
          </button>
        </div>
      ) : (
        <div className="notice">
          You can read this collection. Uploading requires write access.
        </div>
      )}
      {progress !== null && (
        <div className="upload-status" role="status">
          <span>Uploading {upload?.file.name}</span>
          <progress value={progress} max={100} aria-label="Upload progress" />
          <span>
            {progress}% · Processing begins after the upload is saved.
          </span>
        </div>
      )}
      {ticket && (
        <div
          className={`notice ${job?.status === "failed" ? "error" : ""}`}
          role="status"
        >
          <Icon name={job?.status === "succeeded" ? "check" : "files"} />
          <div>
            <strong>
              {job?.status === "succeeded"
                ? "Ready to ask questions"
                : job?.status === "failed"
                  ? "Processing failed"
                  : job?.status === "cancelled"
                    ? "Processing cancelled"
                    : "Upload saved · processing your document"}
            </strong>
            <p>
              {job?.status === "succeeded"
                ? "Your document has been indexed and is ready for search."
                : job?.status === "failed"
                  ? `The file was saved, but processing failed (${job.error_code ?? "processing_error"}).`
                  : job
                    ? `Current stage: ${job.stage.replaceAll("_", " ")}`
                    : ticket.dispatch === "pending"
                      ? "Waiting for the ingestion worker. Your upload receipt is saved."
                      : "Checking the ingestion job…"}
            </p>
            <small>Job {ticket.job_id}</small>
          </div>
        </div>
      )}
      {jobError && (
        <div className="notice error" role="alert">
          {jobError}
          <button
            className="text-button"
            onClick={() => setTicket((value) => value && { ...value })}
          >
            Check status again
          </button>
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
          {upload && !ticket && (
            <button
              className="text-button"
              onClick={() => void send(upload.file, upload.key)}
            >
              Retry upload
            </button>
          )}
        </div>
      )}
      <div className="list-heading">
        <h2>In this collection</h2>
        <span className="count">{documents?.length ?? "—"} files</span>
        <button
          className="icon-button"
          title="Refresh documents"
          aria-label="Refresh documents"
          onClick={() => setReload((v) => v + 1)}
        >
          <Icon name="retry" size={17} />
        </button>
      </div>
      {!documents ? (
        <p className="muted" role="status">
          Loading documents…
        </p>
      ) : documents.length === 0 ? (
        <div className="empty-inline">
          <Icon name="files" />
          <p>No documents yet. Add your first source above.</p>
        </div>
      ) : (
        <div className="document-list">
          {documents.map((document) => (
            <article className="document-row" key={document.id}>
              <span className="file-icon">
                <Icon name="files" />
              </span>
              <div className="file-info">
                <strong>{document.original_filename}</strong>
                <span>
                  {Math.max(1, Math.round(document.size_bytes / 1024))} KB
                </span>
              </div>
              <span className={`status-pill ${document.status}`}>
                {document.status.replaceAll("_", " ")}
              </span>
              {capabilities.can_upload && (
                <button
                  className="icon-button danger"
                  title="Delete document"
                  aria-label={`Delete ${document.original_filename}`}
                  onClick={() => void remove(document)}
                >
                  <Icon name="close" size={16} />
                </button>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
