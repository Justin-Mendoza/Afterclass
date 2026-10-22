"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from "react";
import { Documents } from "../components/documents";
import { Icon } from "../components/icons";
import { Permissions } from "../components/permissions";
import {
  APIError,
  aborted,
  api,
  listAll,
  message,
  streamAnswer,
  workspacePath,
  type AnswerDetail,
  type AnswerResult,
  type AnswerSummary,
  type Capabilities,
  type Collection,
  type Document as SourceDocument,
  type Evidence,
  type Identity,
  type Workspace,
} from "../lib/api";

type View = "ask" | "documents" | "permissions";
type AnswerState = {
  question: string;
  draft: string;
  result: AnswerResult | null;
  id: string;
  status:
    | "idle"
    | "loading"
    | "running"
    | "complete"
    | "stopped"
    | "interrupted"
    | "error"
    | "unavailable";
  stage: string;
  notice: string;
};
const emptyAnswer = (): AnswerState => ({
  question: "",
  draft: "",
  result: null,
  id: "",
  status: "idle",
  stage: "",
  notice: "",
});
const stageLabels: Record<string, string> = {
  retrieving: "Finding relevant passages",
  generating: "Writing a draft",
  validating: "Checking citations",
  saving: "Saving your answer",
};
const outcomeLabels = {
  answered: "Citations checked",
  partial: "Partial answer",
  insufficient_evidence: "Not enough evidence",
  failed: "Could not verify",
};

function subscribeMobile(onChange: () => void) {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia("(max-width: 720px)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
function mobileSnapshot() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 720px)").matches
  );
}

export default function Home() {
  const [identities, setIdentities] = useState<Identity[]>([]);
  const [identity, setIdentity] = useState("");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState("");
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collection, setCollection] = useState("");
  const [capabilities, setCapabilities] = useState<Capabilities>({
    can_upload: false,
    can_manage: false,
  });
  const [history, setHistory] = useState<AnswerSummary[]>([]);
  const [view, setView] = useState<View>("ask");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerState>(emptyAnswer);
  const [source, setSource] = useState<{
    evidence: Evidence;
    document: SourceDocument;
  } | null>(null);
  const [sourceLoading, setSourceLoading] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [collectionForm, setCollectionForm] = useState<"new" | "edit" | null>(
    null,
  );
  const [collectionName, setCollectionName] = useState("");
  const [collectionDescription, setCollectionDescription] = useState("");
  const [collectionSaving, setCollectionSaving] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const streamController = useRef<AbortController | null>(null);
  const detailController = useRef<AbortController | null>(null);
  const sourceController = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const collectionContext = useRef("");
  const sourceTitle = useRef<HTMLHeadingElement>(null);
  const sourceOpener = useRef<HTMLElement | null>(null);
  const menuButton = useRef<HTMLButtonElement>(null);
  const isMobile = useSyncExternalStore(
    subscribeMobile,
    mobileSnapshot,
    () => false,
  );
  useEffect(() => {
    if (!source) return;
    sourceTitle.current?.focus({ preventScroll: true });
    if (window.matchMedia?.("(max-width: 1000px)").matches) {
      sourceTitle.current?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
    }
  }, [source]);
  useEffect(() => {
    if (!sidebarOpen) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSidebarOpen(false);
        menuButton.current?.focus();
      }
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [sidebarOpen]);
  const selectedCollection = collections.find((item) => item.id === collection);
  const selectedWorkspace = workspaces.find((item) => item.id === workspace);
  const refresh = useCallback(() => setReload((value) => value + 1), []);
  useEffect(
    () => () => {
      streamController.current?.abort();
      detailController.current?.abort();
      sourceController.current?.abort();
    },
    [],
  );
  useEffect(() => {
    const controller = new AbortController();
    api<Identity[]>("/v1/demo-users", "", { signal: controller.signal })
      .then((rows) => {
        if (controller.signal.aborted) return;
        setIdentities(rows);
        setIdentity(rows[0]?.id ?? "");
        setLoading(false);
        if (!rows.length)
          setError(
            "No demo identities found. Run the database seed command to get started.",
          );
      })
      .catch((e) => {
        if (!aborted(e)) {
          setError(message(e));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!identity) return;
    const controller = new AbortController();
    api<Workspace[]>("/v1/workspaces", identity, { signal: controller.signal })
      .then((rows) => {
        if (controller.signal.aborted) return;
        const requested = new URLSearchParams(window.location.search).get(
          "workspace",
        );
        setWorkspaces(rows);
        setWorkspace(
          rows.find((item) => item.id === requested)?.id ?? rows[0]?.id ?? "",
        );
        if (!rows.length) setError("This identity has no workspaces.");
      })
      .catch((e) => {
        if (!aborted(e)) setError(message(e));
      });
    return () => controller.abort();
  }, [identity]);
  useEffect(() => {
    if (!workspace) return;
    const controller = new AbortController();
    listAll<Collection>(
      workspacePath(workspace, "/collections"),
      identity,
      controller.signal,
    )
      .then((rows) => {
        if (!controller.signal.aborted) {
          setCollections(rows);
          const context = `${identity}:${workspace}`;
          const firstLoad = collectionContext.current !== context;
          collectionContext.current = context;
          setCollection((current) =>
            firstLoad
              ? (rows[0]?.id ?? "")
              : !current || rows.some((item) => item.id === current)
                ? current
                : (rows[0]?.id ?? ""),
          );
        }
      })
      .catch((e) => {
        if (!aborted(e)) setError(message(e));
      });
    return () => controller.abort();
  }, [identity, workspace, reload]);
  useEffect(() => {
    if (!workspace || !collection) return;
    const controller = new AbortController();
    api<Capabilities>(
      workspacePath(workspace, `/collections/${collection}/capabilities`),
      identity,
      { signal: controller.signal },
    )
      .then((value) => {
        if (!controller.signal.aborted) setCapabilities(value);
      })
      .catch((e) => {
        if (!aborted(e)) {
          setCapabilities({ can_upload: false, can_manage: false });
          setError(message(e));
        }
      });
    return () => controller.abort();
  }, [identity, workspace, collection, reload]);
  useEffect(() => {
    if (!workspace) return;
    const controller = new AbortController();
    listAll<AnswerSummary>(
      workspacePath(workspace, "/answers"),
      identity,
      controller.signal,
    )
      .then((rows) => {
        if (!controller.signal.aborted) setHistory(rows);
      })
      .catch((e) => {
        if (!aborted(e)) setError(message(e));
      });
    return () => controller.abort();
  }, [identity, workspace, reload]);

  useEffect(() => {
    if (!identity || !workspace) return;
    const query = new URLSearchParams(window.location.search);
    const id = query.get("answer");
    if (!id || query.get("workspace") !== workspace) return;
    const controller = new AbortController();
    const current = epoch.current;
    void api<AnswerDetail>(
      workspacePath(workspace, `/answers/${encodeURIComponent(id)}`),
      identity,
      { signal: controller.signal },
    )
      .then(async (detail) => {
        if (controller.signal.aborted || epoch.current !== current) return;
        setAnswer({
          ...emptyAnswer(),
          id,
          question: detail.question,
          result: detail.result,
          status: !detail.available
            ? "unavailable"
            : detail.result?.outcome === "failed"
              ? "error"
              : "complete",
          notice: !detail.available
            ? "This answer is unavailable because access to its sources changed."
            : detail.result?.outcome === "failed"
              ? "This answer could not be completed."
              : "",
        });
        setQuestion(detail.question);
        const sourceId = query.get("source");
        if (!sourceId || !detail.available) return;
        const evidence = detail.result?.evidence.find(
          (item) => item.chunk_id === sourceId,
        );
        if (!evidence) {
          setSourceError("This source does not belong to the saved answer.");
          return;
        }
        const sourceDocument = await api<SourceDocument>(
          workspacePath(workspace, `/documents/${evidence.document_id}`),
          identity,
          { signal: controller.signal },
        );
        if (!controller.signal.aborted && epoch.current === current)
          setSource({ evidence, document: sourceDocument });
      })
      .catch((e) => {
        if (!controller.signal.aborted && epoch.current === current) {
          setAnswer({ ...emptyAnswer(), status: "error", notice: message(e) });
          setSource(null);
        }
      });
    return () => controller.abort();
  }, [identity, workspace]);

  function clearContext() {
    epoch.current++;
    streamController.current?.abort();
    detailController.current?.abort();
    sourceController.current?.abort();
    setAnswer(emptyAnswer());
    setSource(null);
    setSourceError("");
    setSourceLoading(false);
    setError("");
    setQuestion("");
    setView("ask");
    setCapabilities({ can_upload: false, can_manage: false });
    setCollectionForm(null);
    setCollectionSaving(false);
    window.history.replaceState(null, "", window.location.pathname);
  }
  function chooseIdentity(id: string) {
    clearContext();
    setIdentity(id);
    setWorkspace("");
    setWorkspaces([]);
    setCollections([]);
    setCollection("");
    setHistory([]);
  }
  function chooseWorkspace(id: string) {
    clearContext();
    setWorkspace(id);
    setCollections([]);
    setCollection("");
    setHistory([]);
  }
  function chooseCollection(id: string) {
    clearContext();
    setCollection(id);
    setSidebarOpen(false);
  }
  function stop() {
    epoch.current++;
    streamController.current?.abort();
    streamController.current = null;
    setAnswer((value) => ({
      ...value,
      status: "stopped",
      draft: "",
      result: null,
      notice: "Generation stopped. Your unfinished draft was not saved.",
    }));
  }
  async function ask(text = question, scope = collection) {
    if (!text.trim() || !workspace || !identity) return;
    detailController.current?.abort();
    sourceController.current?.abort();
    streamController.current?.abort();
    const current = ++epoch.current;
    const controller = new AbortController();
    streamController.current = controller;
    setView("ask");
    setSource(null);
    setSourceError("");
    setSourceLoading(false);
    setError("");
    setSidebarOpen(false);
    setAnswer({
      ...emptyAnswer(),
      question: text.trim(),
      status: "running",
      stage: "retrieving",
    });
    const timeout = setTimeout(() => {
      if (epoch.current !== current) return;
      epoch.current++;
      controller.abort();
      setAnswer((value) => ({
        ...value,
        status: "interrupted",
        draft: "",
        notice:
          "Connection interrupted. Check history before retrying; the server may have finished saving.",
      }));
    }, 95_000);
    try {
      await streamAnswer(
        workspace,
        identity,
        text.trim(),
        scope,
        controller.signal,
        (event) => {
          if (epoch.current !== current) return;
          if (event.type === "progress")
            setAnswer((value) => ({ ...value, stage: event.stage }));
          else if (event.type === "content")
            setAnswer((value) => ({
              ...value,
              draft: value.draft + event.text,
            }));
          else if (event.type === "complete") {
            setAnswer((value) => ({
              ...value,
              status: "complete",
              draft: "",
              result: event.result,
              id: event.answer_id,
              stage: "",
            }));
            refresh();
            window.history.replaceState(
              null,
              "",
              `?workspace=${encodeURIComponent(workspace)}&answer=${encodeURIComponent(event.answer_id)}`,
            );
          } else if (event.type === "error") {
            setAnswer((value) => ({
              ...value,
              status: "error",
              draft: "",
              result: null,
              notice: event.message,
              id: event.answer_id ?? "",
            }));
            refresh();
          }
        },
      );
    } catch (e) {
      if (epoch.current === current && !aborted(e)) {
        const rejected = e instanceof APIError && e.status > 0;
        setAnswer((value) => ({
          ...value,
          status: rejected ? "error" : "interrupted",
          draft: "",
          result: null,
          notice: rejected
            ? message(e)
            : "Connection interrupted. Check history before retrying; the server may have finished saving.",
        }));
        refresh();
      }
    } finally {
      clearTimeout(timeout);
      if (epoch.current === current) streamController.current = null;
    }
  }
  async function openHistory(id: string, sourceId?: string) {
    streamController.current?.abort();
    detailController.current?.abort();
    sourceController.current?.abort();
    const current = ++epoch.current;
    const controller = new AbortController();
    detailController.current = controller;
    setView("ask");
    setAnswer({ ...emptyAnswer(), status: "loading" });
    setSource(null);
    setSourceError("");
    setSourceLoading(false);
    setSidebarOpen(false);
    try {
      const detail = await api<AnswerDetail>(
        workspacePath(workspace, `/answers/${encodeURIComponent(id)}`),
        identity,
        { signal: controller.signal },
      );
      if (epoch.current !== current) return;
      setAnswer({
        ...emptyAnswer(),
        question: detail.question,
        id,
        result: detail.result,
        status: !detail.available
          ? "unavailable"
          : detail.result?.outcome === "failed"
            ? "error"
            : "complete",
        notice: !detail.available
          ? "This answer is unavailable because access to its sources changed."
          : detail.result?.outcome === "failed"
            ? "This answer could not be completed. You can try the question again."
            : "",
      });
      setQuestion(detail.question);
      window.history.replaceState(
        null,
        "",
        `?workspace=${encodeURIComponent(workspace)}&answer=${encodeURIComponent(id)}${sourceId ? `&source=${encodeURIComponent(sourceId)}` : ""}`,
      );
      if (sourceId && detail.available) await openSource(id, sourceId, current);
    } catch (e) {
      if (epoch.current === current && !aborted(e))
        setAnswer({ ...emptyAnswer(), status: "error", notice: message(e) });
    }
  }
  async function openSource(
    id: string,
    chunk: string,
    current = epoch.current,
  ) {
    sourceOpener.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    sourceController.current?.abort();
    const controller = new AbortController();
    sourceController.current = controller;
    setSource(null);
    setSourceLoading(true);
    setSourceError("");
    try {
      const detail = await api<AnswerDetail>(
        workspacePath(workspace, `/answers/${encodeURIComponent(id)}`),
        identity,
        { signal: controller.signal },
      );
      if (controller.signal.aborted || epoch.current !== current) return;
      if (!detail.available || !detail.result) {
        setAnswer((value) => ({
          ...value,
          result: null,
          status: "unavailable",
          notice:
            "This answer is unavailable because access to its sources changed.",
        }));
        throw new Error("This source is no longer available to this identity.");
      }
      const evidence = detail.result.evidence.find(
        (item) => item.chunk_id === chunk,
      );
      if (!evidence)
        throw new Error("This source does not belong to the saved answer.");
      const sourceDocument = await api<SourceDocument>(
        workspacePath(workspace, `/documents/${evidence.document_id}`),
        identity,
        { signal: controller.signal },
      );
      if (controller.signal.aborted || epoch.current !== current) return;
      setSource({ evidence, document: sourceDocument });
      window.history.replaceState(
        null,
        "",
        `?workspace=${encodeURIComponent(workspace)}&answer=${encodeURIComponent(id)}&source=${encodeURIComponent(chunk)}`,
      );
    } catch (e) {
      if (!controller.signal.aborted && epoch.current === current)
        setSourceError(message(e));
    } finally {
      if (!controller.signal.aborted && epoch.current === current)
        setSourceLoading(false);
    }
  }
  async function download() {
    if (!source) return;
    const current = epoch.current;
    try {
      const response = await fetch(
        `/api${workspacePath(workspace, `/documents/${source.evidence.document_id}/content`)}`,
        { headers: { "X-Demo-User-ID": identity }, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error("The original file is not available to this identity.");
      const blob = await response.blob();
      if (current !== epoch.current) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = source.document.original_filename;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) {
      if (current === epoch.current) setSourceError(message(e));
    }
  }
  async function saveCollection(event: FormEvent) {
    event.preventDefault();
    if (!collectionName.trim()) return;
    const current = epoch.current;
    setCollectionSaving(true);
    setError("");
    try {
      const body = {
        name: collectionName.trim(),
        description: collectionDescription.trim() || null,
      };
      const path = workspacePath(
        workspace,
        `/collections${collectionForm === "edit" ? `/${collection}` : ""}`,
      );
      const saved = await api<Collection>(path, identity, {
        method: collectionForm === "edit" ? "PATCH" : "POST",
        body: JSON.stringify(
          collectionForm === "edit"
            ? body
            : {
                ...body,
                slug: `${
                  collectionName
                    .toLowerCase()
                    .replace(/[^a-z0-9]+/g, "-")
                    .replace(/^-|-$/g, "")
                    .slice(0, 60) || "collection"
                }-${crypto.randomUUID().slice(0, 8)}`,
              },
        ),
      });
      if (epoch.current !== current) return;
      if (saved.id !== collection) clearContext();
      setCollections((rows) => [
        ...rows.filter((item) => item.id !== saved.id),
        saved,
      ]);
      setCollection(saved.id);
      setCollectionForm(null);
      refresh();
    } catch (e) {
      if (epoch.current === current) setError(message(e));
    } finally {
      if (epoch.current === current) setCollectionSaving(false);
    }
  }
  const running = answer.status === "running";
  const hasSourcePanel = sourceLoading || source || sourceError;
  function answerText(): ReactNode {
    const result = answer.result;
    if (!result) return answer.draft;
    const characters = Array.from(result.text); // Backend/native citation offsets count Unicode characters, not JS UTF-16 units.
    const ends = [...new Set(result.citations.map((item) => item.end))].sort(
      (a, b) => a - b,
    );
    let start = 0;
    const nodes: ReactNode[] = [];
    for (const end of ends) {
      nodes.push(characters.slice(start, end).join(""));
      for (const [i, citation] of result.citations.entries()) {
        if (citation.end !== end) continue;
        for (const sourceId of citation.source_ids) {
          const index = result.evidence.findIndex(
            (item) => item.chunk_id === sourceId,
          );
          if (index !== -1)
            nodes.push(
              <button
                className={`citation ${source?.evidence.chunk_id === sourceId ? "selected" : ""}`}
                aria-label={`Open source ${index + 1}`}
                key={`${i}-${sourceId}`}
                onClick={() => void openSource(answer.id, sourceId)}
              >
                {index + 1}
              </button>,
            );
        }
      }
      start = end;
    }
    nodes.push(characters.slice(start).join(""));
    return nodes;
  }
  return (
    <div className="app-shell">
      <button
        ref={menuButton}
        aria-controls="workspace-navigation"
        className="mobile-menu icon-button"
        aria-label="Toggle navigation"
        aria-expanded={sidebarOpen}
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        <Icon name={sidebarOpen ? "close" : "book"} />
      </button>
      {sidebarOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <aside
        className={`sidebar ${sidebarOpen ? "open" : ""}`}
        id="workspace-navigation"
        inert={isMobile && !sidebarOpen}
        aria-label="Workspace navigation"
      >
        <Link className="brand" href="/" aria-label="Hybrid RAG Search home">
          <span className="brand-mark">
            <Icon name="book" size={27} />
          </span>
          <span>
            Hybrid RAG
            <span className="brand-caption">your document workspace</span>
          </span>
        </Link>
        <div className="scope-controls">
          <label htmlFor="identity">
            Demo identity <span className="tiny-label">simulated</span>
          </label>
          <select
            id="identity"
            value={identity}
            onChange={(e) => chooseIdentity(e.target.value)}
            disabled={loading}
          >
            {identities.map((item) => (
              <option value={item.id} key={item.id}>
                {item.display_name}
              </option>
            ))}
          </select>
          <label htmlFor="workspace">Workspace</label>
          <select
            id="workspace"
            value={workspace}
            onChange={(e) => chooseWorkspace(e.target.value)}
            disabled={!workspaces.length}
          >
            {workspaces.map((item) => (
              <option value={item.id} key={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <nav aria-label="Workspace views">
          <button
            className={`nav-link ${view === "ask" ? "active" : ""}`}
            onClick={() => {
              setView("ask");
              setSidebarOpen(false);
            }}
          >
            <Icon name="ask" />
            Ask a question
            <span className="nav-dot" />
          </button>
          <button
            className={`nav-link ${view === "documents" ? "active" : ""}`}
            onClick={() => {
              setView("documents");
              setSidebarOpen(false);
            }}
          >
            <Icon name="files" />
            Documents
          </button>
          {capabilities.can_manage && selectedCollection && (
            <button
              className={`nav-link ${view === "permissions" ? "active" : ""}`}
              onClick={() => {
                setView("permissions");
                setSidebarOpen(false);
              }}
            >
              <Icon name="shield" />
              Permissions
            </button>
          )}
        </nav>
        <div className="sidebar-section">
          <div className="sidebar-section-title">
            <span>Collections</span>
            {selectedWorkspace && selectedWorkspace.role !== "member" && (
              <button
                className="icon-button"
                aria-label="Create collection"
                onClick={() => {
                  setCollectionForm("new");
                  setCollectionName("");
                  setCollectionDescription("");
                }}
              >
                <Icon name="plus" size={16} />
              </button>
            )}
          </div>
          <button
            aria-pressed={!collection}
            className={`collection-link ${!collection ? "active" : ""}`}
            onClick={() => chooseCollection("")}
          >
            <span aria-hidden="true" className="collection-symbol">
              ◎
            </span>
            All accessible collections
          </button>
          {collections.map((item, index) => (
            <button
              aria-pressed={collection === item.id}
              title={item.name}
              className={`collection-link ${collection === item.id ? "active" : ""}`}
              key={item.id}
              onClick={() => chooseCollection(item.id)}
            >
              <span
                aria-hidden="true"
                className={`collection-symbol color-${index % 3}`}
              >
                ▱
              </span>
              <span className="truncate">{item.name}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-section history-section">
          <div className="sidebar-section-title">
            <span>Recent questions</span>
            <button
              className="icon-button"
              aria-label="Refresh history"
              onClick={refresh}
            >
              <Icon name="retry" size={14} />
            </button>
          </div>
          {history.length === 0 ? (
            <p className="sidebar-empty">
              Your questions will find a home here.
            </p>
          ) : (
            history.map((item) => (
              <button
                className={`history-link ${answer.id === item.id ? "active" : ""}`}
                title={item.question}
                key={item.id}
                onClick={() => void openHistory(item.id)}
              >
                <span aria-hidden="true" className="history-tick">
                  ↳
                </span>
                <span className="truncate">{item.question}</span>
                {!item.available && <Icon name="shield" size={12} />}
              </button>
            ))
          )}
        </div>
        <div className="sidebar-footer">
          <span className="little-pencil">✎</span>
          <p>
            A place for your files.
            <br />
            <strong>And your next good question.</strong>
          </p>
          <span className="local-label">LOCAL DEMO</span>
        </div>
      </aside>
      <div className="workspace-shell" inert={isMobile && sidebarOpen}>
        <header className="topbar">
          <div className="breadcrumb">
            <span>{selectedWorkspace?.name ?? "Your workspace"}</span>
            <Icon name="chevron" size={13} />
            <strong>
              {selectedCollection?.name ?? "All accessible collections"}
            </strong>
          </div>
          <div className="topbar-actions">
            {capabilities.can_manage && selectedCollection && (
              <button
                className="text-button"
                onClick={() => {
                  setCollectionForm("edit");
                  setCollectionName(selectedCollection.name);
                  setCollectionDescription(
                    selectedCollection.description ?? "",
                  );
                }}
              >
                Edit collection
              </button>
            )}
            <span className="private-label">
              <Icon name="shield" size={14} />
              Private answers
            </span>
          </div>
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className={`main-content ${hasSourcePanel && view === "ask" ? "with-source" : ""}`}
        >
          <div className="main-column">
            {error && (
              <div className="notice error" role="alert">
                {error}
                <button
                  className="icon-button"
                  aria-label="Dismiss error"
                  onClick={() => setError("")}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
            )}
            {loading && (
              <p className="muted" role="status">
                Opening your workspace…
              </p>
            )}
            {!loading && !identities.length && (
              <div className="empty-inline">
                <p>
                  Start the API and seed the demo database, then reload this
                  page.
                </p>
              </div>
            )}
            {collectionForm && (
              <form
                className="collection-form sketch-border view-enter"
                onSubmit={saveCollection}
              >
                <div className="list-heading">
                  <h2>
                    {collectionForm === "new"
                      ? "A new collection"
                      : "Edit collection"}
                  </h2>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Close collection form"
                    onClick={() => setCollectionForm(null)}
                  >
                    <Icon name="close" />
                  </button>
                </div>
                <label>
                  Name
                  <input
                    required
                    maxLength={200}
                    value={collectionName}
                    onChange={(e) => setCollectionName(e.target.value)}
                    placeholder="e.g. Biology readings"
                  />
                </label>
                <label>
                  Description
                  <textarea
                    maxLength={2000}
                    value={collectionDescription}
                    onChange={(e) => setCollectionDescription(e.target.value)}
                    placeholder="What belongs in this collection?"
                  />
                </label>
                <button className="button primary" disabled={collectionSaving}>
                  {collectionSaving ? "Saving…" : "Save collection"}
                </button>
              </form>
            )}
            {view === "documents" ? (
              selectedCollection ? (
                <Documents
                  key={`${identity}-${workspace}-${collection}`}
                  identity={identity}
                  workspace={workspace}
                  collection={selectedCollection}
                  capabilities={capabilities}
                  onChange={refresh}
                />
              ) : (
                <div className="empty-view">
                  <Icon name="files" size={42} />
                  <h1>Give your files a home.</h1>
                  <p>
                    Select a collection in the sidebar to view or upload
                    documents.
                  </p>
                </div>
              )
            ) : view === "permissions" ? (
              selectedCollection && capabilities.can_manage ? (
                <Permissions
                  key={`${identity}-${workspace}-${collection}`}
                  identity={identity}
                  workspace={workspace}
                  collection={selectedCollection}
                  onChange={refresh}
                />
              ) : (
                <div className="notice">
                  Choose a collection you can manage.
                </div>
              )
            ) : (
              <section className="ask-view">
                {answer.status === "idle" ? (
                  <div className="welcome view-enter">
                    <div className="paper-illustration" aria-hidden="true">
                      <div className="illustration-sheet">
                        <i />
                        <i />
                        <i />
                        <span>?</span>
                      </div>
                      <span className="orbit-star">✧</span>
                      <span className="orbit-line">⌁</span>
                    </div>
                    <p className="eyebrow">
                      A little curiosity goes a long way
                    </p>
                    <h1>
                      Your files.
                      <br />A fresh{" "}
                      <span className="pencil-underline">perspective.</span>
                    </h1>
                    <p className="welcome-copy">
                      Bring your documents. Ask what’s on your mind.
                      <br />
                      Find answers you can trace back to the source.
                    </p>
                    <div className="welcome-actions">
                      <button
                        className="button secondary"
                        onClick={() => setView("documents")}
                      >
                        <Icon name="upload" size={17} />
                        Add your documents
                      </button>
                      <span className="hand-note">then, ask away ↘</span>
                    </div>
                  </div>
                ) : (
                  <article
                    className="answer-card view-enter"
                    aria-labelledby="question-heading"
                  >
                    <div className="answer-question">
                      <span className="eyebrow">Your question</span>
                      <h1 id="question-heading">
                        {answer.question || "Opening saved answer…"}
                      </h1>
                    </div>
                    <div className="answer-header">
                      <span className="answer-symbol">
                        <Icon name="spark" size={19} />
                      </span>
                      <strong>From your documents</strong>
                      {running ? (
                        <span className="status-pill working" role="status">
                          <span className="pulse-dot" />
                          {stageLabels[answer.stage] ?? "Working"}
                        </span>
                      ) : (
                        answer.result && (
                          <span
                            role="status"
                            className={`status-pill ${answer.result.outcome}`}
                          >
                            {outcomeLabels[answer.result.outcome]}
                          </span>
                        )
                      )}
                    </div>
                    {running && (
                      <p className="draft-label" role="status">
                        Live draft · sources not yet verified
                      </p>
                    )}
                    {answer.status === "loading" && (
                      <p className="muted" role="status">
                        Checking access and loading the saved answer…
                      </p>
                    )}
                    {(answer.draft || answer.result?.text) && (
                      <div
                        className={`answer-body ${running ? "is-draft" : ""}`}
                      >
                        {answerText()}
                        {running && (
                          <span className="writing-cursor" aria-hidden="true" />
                        )}
                      </div>
                    )}
                    {running && !answer.draft && (
                      <div className="thinking" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </div>
                    )}
                    {answer.notice && (
                      <div
                        className={`notice ${answer.status === "error" ? "error" : ""}`}
                        role={
                          answer.status === "error" ||
                          answer.status === "interrupted"
                            ? "alert"
                            : "status"
                        }
                      >
                        <div>
                          <strong>
                            {answer.status === "interrupted"
                              ? "Connection interrupted"
                              : answer.status === "stopped"
                                ? "You stopped this answer"
                                : answer.status === "unavailable"
                                  ? "Source access changed"
                                  : "Couldn’t finish this answer"}
                          </strong>
                          <p>{answer.notice}</p>
                        </div>
                      </div>
                    )}
                    {["error", "interrupted", "stopped"].includes(
                      answer.status,
                    ) &&
                      answer.question && (
                        <button
                          className="button secondary"
                          onClick={() => void ask(answer.question, collection)}
                        >
                          <Icon name="retry" size={16} />
                          Retry question
                        </button>
                      )}
                    {answer.result && answer.result.evidence.length > 0 && (
                      <div className="source-chips" aria-label="Answer sources">
                        {answer.result.evidence.map((item, i) => (
                          <button
                            className={`source-chip ${source?.evidence.chunk_id === item.chunk_id ? "selected" : ""}`}
                            key={item.chunk_id}
                            onClick={() =>
                              void openSource(answer.id, item.chunk_id)
                            }
                          >
                            <span>{i + 1}</span>
                            <Icon name="files" size={14} />
                            {item.source_spans[0]?.locator.heading_path?.at(
                              -1,
                            ) ?? `Source ${i + 1}`}
                            <Icon name="chevron" size={12} />
                          </button>
                        ))}
                      </div>
                    )}
                    {answer.status === "complete" && (
                      <p className="answer-footnote">
                        <Icon name="check" size={13} />
                        Saved privately · citation checks verify source
                        references, not every claim.
                      </p>
                    )}
                  </article>
                )}
                <form
                  className="question-form sketch-border"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void ask();
                  }}
                >
                  <label htmlFor="question-input">
                    Ask a question about your documents
                  </label>
                  <textarea
                    id="question-input"
                    placeholder="What would you like to understand?"
                    value={question}
                    maxLength={4096}
                    disabled={running || !workspace}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        if (!running) void ask();
                      }
                    }}
                    rows={2}
                  />
                  <div className="composer-bottom">
                    <span className="scope-pill">
                      <Icon name="book" size={14} />
                      {selectedCollection?.name ?? "All accessible collections"}
                    </span>
                    {running ? (
                      <button
                        type="button"
                        className="button stop-button"
                        onClick={stop}
                      >
                        <Icon name="stop" size={15} />
                        Stop
                      </button>
                    ) : (
                      <button
                        type="submit"
                        className="ask-button"
                        aria-label="Ask question"
                        disabled={!question.trim() || !workspace}
                      >
                        <Icon name="arrow" size={22} />
                      </button>
                    )}
                  </div>
                </form>
                <div className="composer-note">
                  <span>Answers use your accessible documents.</span>
                  <span>Enter to ask · Shift + Enter for a new line</span>
                </div>
              </section>
            )}
          </div>
          {view === "ask" && hasSourcePanel && (
            <aside
              className="source-panel view-enter"
              aria-label="Source context"
            >
              <div className="source-heading">
                <div>
                  <p className="eyebrow">Follow the evidence</p>
                  <h2 ref={sourceTitle} tabIndex={-1}>
                    A closer look.
                  </h2>
                </div>
                <button
                  className="icon-button"
                  aria-label="Close source panel"
                  onClick={() => {
                    sourceController.current?.abort();
                    setSource(null);
                    setSourceLoading(false);
                    setSourceError("");
                    sourceOpener.current?.focus();
                  }}
                >
                  <Icon name="close" />
                </button>
              </div>
              {sourceLoading && (
                <p className="muted" role="status">
                  Checking source access…
                </p>
              )}
              {sourceError && (
                <div className="notice error" role="alert">
                  {sourceError}
                </div>
              )}
              {source && (
                <>
                  <div className="source-file">
                    <Icon name="files" size={24} />
                    <strong>{source.document.original_filename}</strong>
                  </div>
                  <div className="source-location">
                    {source.evidence.source_spans.map((span, i) => (
                      <span key={i}>
                        {span.locator.page_number
                          ? `Page ${span.locator.page_number}`
                          : `Block ${span.locator.block_number}`}
                        {span.locator.heading_path?.length
                          ? ` · ${span.locator.heading_path.join(" › ")}`
                          : ""}
                      </span>
                    ))}
                  </div>
                  <blockquote className="source-passage">
                    {source.evidence.content_text}
                  </blockquote>
                  <p className="source-caption">
                    The exact passage supplied for this answer. Page and heading
                    information come from the document parser.
                  </p>
                  <button
                    className="button secondary download-button"
                    onClick={() => void download()}
                  >
                    <Icon name="download" size={16} />
                    Download original
                  </button>
                </>
              )}
            </aside>
          )}
        </main>
      </div>
    </div>
  );
}
