import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  APIError,
  readAnswerStream,
  streamAnswer,
  uploadFile,
  type StreamEvent,
} from "./api";
const encode = new TextEncoder();
function stream(parts: string[]) {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const part of parts) controller.enqueue(encode.encode(part));
      controller.close();
    },
  });
}
function frame(id: number, event: StreamEvent) {
  return `id: ${id}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`;
}
const complete: StreamEvent = {
  type: "complete",
  answer_id: "one",
  result: {
    outcome: "answered",
    text: "Café 🚀",
    citations: [],
    evidence: [],
    error_code: null,
    configuration: {},
  },
};
afterEach(() => vi.unstubAllGlobals());

describe("answer stream protocol", () => {
  it("handles arbitrarily split UTF-8, CRLF, and heartbeats without duplicate content", async () => {
    const wire =
      `: keepalive\n\n${frame(1, { type: "content", text: "Café 🚀" })}${frame(2, complete)}`.replaceAll(
        "\n",
        "\r\n",
      );
    const bytes = encode.encode(wire);
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
        controller.close();
      },
    });
    const events: StreamEvent[] = [];
    await readAnswerStream(body, (event) => events.push(event));
    expect(events).toEqual([{ type: "content", text: "Café 🚀" }, complete]);
  });
  it("recognizes a terminal failure without waiting for completion", async () => {
    const events: StreamEvent[] = [];
    await readAnswerStream(
      stream([
        frame(1, {
          type: "error",
          code: "timeout",
          message: "Try again",
          answer_id: null,
        }),
      ]),
      (event) => events.push(event),
    );
    expect(events[0].type).toBe("error");
  });
  it.each([
    frame(1, { type: "content", text: "unfinished" }),
    `id: 2\nevent: content\ndata: {"type":"content","text":"out of order"}\n\n`,
    `id: 1\nevent: content\ndata: {"type":"progress","stage":"generating"}\n\n`,
    `id: 1\nevent: complete\ndata: {"type":"complete","answer_id":"x","result":{}}\n\n`,
    `id: 1\nevent: content\ndata: {"type":"content","text":3}\n\n`,
    `id: 1\nevent: progress\ndata: {"type":"progress","stage":"unknown"}\n\n`,
    `id: 1\nevent: mystery\ndata: {"type":"mystery"}\n\n`,
    `id: 1\nevent: citations\ndata: {"type":"citations","citations":null}\n\n`,
    `id: 1\nevent: error\ndata: {"type":"error","code":12}\n\n`,
    "id: 1\nevent: content\ndata: broken json\n\n",
  ])("rejects interrupted or malformed streams", async (value) => {
    await expect(readAnswerStream(stream([value]), () => {})).rejects.toThrow();
  });
  it("forwards identity, question, scope and abort without automatic retries", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(stream([frame(1, complete)]), {
        headers: { "content-type": "text/event-stream" },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    const controller = new AbortController();
    await streamAnswer(
      "workspace",
      "person",
      "Question",
      "collection",
      controller.signal,
      () => {},
    );
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0][1]).toMatchObject({
      signal: controller.signal,
      headers: { "X-Demo-User-ID": "person" },
    });
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
      question: "Question",
      collection_id: "collection",
    });
  });
  it("reports safe backend errors and rejects non-stream responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: { code: "access_denied", message: "Denied" },
          }),
          { status: 403 },
        ),
      ),
    );
    await expect(
      streamAnswer("w", "i", "Q", "", new AbortController().signal, () => {}),
    ).rejects.toMatchObject({ code: "access_denied", status: 403 });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not a stream")),
    );
    await expect(
      streamAnswer("w", "i", "Q", "", new AbortController().signal, () => {}),
    ).rejects.toThrow(APIError);
  });
});

describe("HTTP and uploads", () => {
  it("sends JSON and identity; handles empty replies and safe errors", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: { code: "denied", message: "No access" } }),
          { status: 403 },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    expect(
      await api("/v1/x", "person", { method: "PUT", body: "{}" }),
    ).toBeUndefined();
    expect(fetch.mock.calls[0][1].headers.get("X-Demo-User-ID")).toBe("person");
    await expect(api("/v1/x")).rejects.toThrow("No access");
  });
  it("keeps the upload key, reports byte progress, and propagates abort", async () => {
    const requests: XHR[] = [];
    class XHR {
      upload: { onprogress?: (e: ProgressEvent) => void } = {};
      headers: Record<string, string> = {};
      onload?: () => void;
      onabort?: () => void;
      status = 202;
      responseText = JSON.stringify({
        document_id: "d",
        job_id: "j",
        duplicate: false,
        dispatch: "sent",
      });
      open() {
        requests.push(this);
      }
      setRequestHeader(key: string, value: string) {
        this.headers[key] = value;
      }
      send() {}
      abort() {
        this.onabort?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", XHR);
    const controller = new AbortController();
    const progress = vi.fn();
    const pending = uploadFile(
      "/upload",
      "person",
      new File(["notes"], "notes.md"),
      "same-key",
      controller.signal,
      progress,
    );
    requests[0].upload.onprogress?.({
      lengthComputable: true,
      loaded: 5,
      total: 10,
    } as ProgressEvent);
    requests[0].onload?.();
    expect(await pending).toMatchObject({ job_id: "j" });
    expect(progress).toHaveBeenCalledWith(50);
    expect(requests[0].headers).toMatchObject({
      "Idempotency-Key": "same-key",
      "X-Demo-User-ID": "person",
    });
    const aborted = uploadFile(
      "/upload",
      "person",
      new File(["x"], "x.txt"),
      "same-key",
      controller.signal,
      progress,
    );
    controller.abort();
    await expect(aborted).rejects.toMatchObject({ name: "AbortError" });
  });
});
