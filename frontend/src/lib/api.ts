export type Identity = { id: string; display_name: string };
export type Workspace = {
  id: string;
  name: string;
  role: "owner" | "admin" | "member";
};
export type Collection = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
};
export type Capabilities = { can_upload: boolean; can_manage: boolean };
export type Document = {
  id: string;
  original_filename: string;
  media_type: string;
  size_bytes: number;
  status: string;
};
export type Job = {
  id: string;
  document_id: string;
  status: string;
  stage: string;
  error_code: string | null;
  failure_reason: string | null;
};
export type Upload = {
  document_id: string;
  job_id: string;
  duplicate: boolean;
  dispatch: string;
};
export type Member = {
  membership_id: string;
  user_id: string;
  display_name: string;
  role: string;
};
export type Grant = {
  membership_id: string;
  permission: "read" | "write" | "manage";
};
export type SourceSpan = {
  locator: {
    block_number: number;
    page_number: number | null;
    heading_path: string[];
  };
  start_char: number;
  end_char: number;
};
export type Evidence = {
  chunk_id: string;
  document_id: string;
  content_text: string;
  source_spans: SourceSpan[];
};
export type Citation = {
  start: number;
  end: number;
  text: string;
  source_ids: string[];
};
export type AnswerResult = {
  outcome: "answered" | "partial" | "insufficient_evidence" | "failed";
  text: string;
  citations: Citation[];
  evidence: Evidence[];
  error_code: string | null;
  configuration: {
    timings?: {
      first_content_ms: number | null;
      total_ms: number;
      generation_ms: number | null;
    };
  };
};
export type AnswerSummary = {
  id: string;
  question: string;
  created_at: string;
  available: boolean;
};
export type AnswerDetail = AnswerSummary & { result: AnswerResult | null };
export type StreamEvent =
  | {
      type: "progress";
      stage: "retrieving" | "generating" | "validating" | "saving";
    }
  | { type: "content"; text: string }
  | { type: "citations"; citations: Citation[] }
  | { type: "complete"; answer_id: string; result: AnswerResult }
  | { type: "error"; code: string; message: string; answer_id: string | null };

export class APIError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
    this.name = "APIError";
  }
}

export function workspacePath(workspace: string, tail = "") {
  return `/v1/workspaces/${encodeURIComponent(workspace)}${tail}`;
}

export async function api<T>(
  path: string,
  identity = "",
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (identity) headers.set("X-Demo-User-ID", identity);
  if (options.body && typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new APIError(
      body?.error?.code ?? "request_failed",
      body?.error?.message ?? "The request could not be completed.",
      response.status,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}

export async function listAll<T>(
  path: string,
  identity: string,
  signal: AbortSignal,
): Promise<T[]> {
  const rows: T[] = [];
  for (let offset = 0; ; offset += 100) {
    const page = await api<T[]>(
      `${path}${path.includes("?") ? "&" : "?"}limit=100&offset=${offset}`,
      identity,
      { signal },
    );
    rows.push(...page);
    if (page.length < 100) return rows;
  }
}

export function uploadFile(
  path: string,
  identity: string,
  file: File,
  key: string,
  signal: AbortSignal,
  progress: (value: number) => void,
): Promise<Upload> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const cleanup = () => signal.removeEventListener("abort", abort);
    xhr.open("POST", `/api${path}`);
    xhr.setRequestHeader("X-Demo-User-ID", identity);
    xhr.setRequestHeader("Idempotency-Key", key);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable)
        progress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => {
      cleanup();
      reject(
        new APIError(
          "upload_interrupted",
          "Upload interrupted. Retry uses the same upload key.",
        ),
      );
    };
    xhr.onabort = () => {
      cleanup();
      reject(new DOMException("Upload stopped", "AbortError"));
    };
    xhr.onload = () => {
      cleanup();
      let body;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        reject(
          new APIError(
            "invalid_response",
            "The upload response could not be read.",
          ),
        );
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else
        reject(
          new APIError(
            body?.error?.code ?? "upload_failed",
            body?.error?.message ?? "Upload failed.",
            xhr.status,
          ),
        );
    };
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) {
      reject(new DOMException("Upload stopped", "AbortError"));
      cleanup();
      return;
    }
    const data = new FormData();
    // Some browsers do not identify Markdown and text MIME types.
    const mime =
      file.type ||
      (/\.md$/i.test(file.name)
        ? "text/markdown"
        : /\.txt$/i.test(file.name)
          ? "text/plain"
          : /\.pdf$/i.test(file.name)
            ? "application/pdf"
            : /\.html?$/i.test(file.name)
              ? "text/html"
              : "application/octet-stream");
    data.append("file", new File([file], file.name, { type: mime }));
    xhr.send(data);
  });
}

function parseStreamEvent(value: unknown): StreamEvent {
  if (!value || typeof value !== "object")
    throw new APIError("invalid_stream", "The answer stream was interrupted.");
  const event = value as Record<string, unknown>;
  const bad = () =>
    new APIError("invalid_stream", "The answer stream was interrupted.");
  switch (event.type) {
    case "progress":
      if (
        !["retrieving", "generating", "validating", "saving"].includes(
          String(event.stage),
        )
      )
        throw bad();
      break;
    case "content":
      if (typeof event.text !== "string" || event.text.length > 100_000)
        throw bad();
      break;
    case "citations":
      if (!Array.isArray(event.citations)) throw bad();
      break;
    case "complete": {
      const result = event.result as AnswerResult | undefined;
      if (
        typeof event.answer_id !== "string" ||
        !result ||
        typeof result.text !== "string" ||
        !["answered", "partial", "insufficient_evidence"].includes(
          result.outcome,
        ) ||
        !Array.isArray(result.citations) ||
        !Array.isArray(result.evidence)
      )
        throw bad();
      for (const citation of result.citations) {
        if (
          !Number.isInteger(citation.start) ||
          !Number.isInteger(citation.end) ||
          citation.start < 0 ||
          citation.end <= citation.start ||
          !Array.isArray(citation.source_ids)
        )
          throw bad();
      }
      break;
    }
    case "error":
      if (typeof event.code !== "string" || typeof event.message !== "string")
        throw bad();
      break;
    default:
      throw bad();
  }
  return value as StreamEvent;
}

export async function readAnswerStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "";
  let sequence = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      if (buffer.length > 2_000_000)
        throw new APIError(
          "invalid_stream",
          "The answer stream was interrupted.",
        );
      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const fields = frame
          .split("\n")
          .filter((line) => line && !line.startsWith(":"));
        if (!fields.length) continue;
        const field = (name: string) =>
          fields
            .filter((line) => line.startsWith(`${name}:`))
            .map((line) => line.slice(name.length + 1).replace(/^ /, ""));
        const ids = field("id");
        if (
          ids.length !== 1 ||
          !/^\d+$/.test(ids[0]) ||
          Number(ids[0]) !== sequence + 1
        )
          throw new APIError(
            "invalid_stream",
            "The answer stream was interrupted.",
          );
        sequence++;
        const event = parseStreamEvent(JSON.parse(field("data").join("\n")));
        if (field("event")[0] !== event.type)
          throw new APIError(
            "invalid_stream",
            "The answer stream was interrupted.",
          );
        onEvent(event);
        if (event.type === "complete" || event.type === "error") return;
      }
      if (done)
        throw new APIError(
          "interrupted",
          "Connection interrupted. Check history before retrying.",
        );
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export async function streamAnswer(
  workspace: string,
  identity: string,
  question: string,
  collection: string,
  signal: AbortSignal,
  onEvent: (event: StreamEvent) => void,
) {
  const response = await fetch(
    `/api${workspacePath(workspace, "/answers/stream")}`,
    {
      method: "POST",
      cache: "no-store",
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-Demo-User-ID": identity,
        Accept: "text/event-stream",
      },
      body: JSON.stringify({ question, collection_id: collection || null }),
    },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new APIError(
      body?.error?.code ?? "request_failed",
      body?.error?.message ?? "The answer could not be started.",
      response.status,
    );
  }
  if (
    !response.headers.get("content-type")?.startsWith("text/event-stream") ||
    !response.body
  )
    throw new APIError(
      "invalid_stream",
      "The answer stream could not be opened.",
    );
  await readAnswerStream(response.body, onEvent);
}

export function message(error: unknown) {
  return error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
}
export function aborted(error: unknown) {
  return error instanceof Error && error.name === "AbortError";
}
