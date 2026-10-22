import "@testing-library/jest-dom/vitest";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";
import type { AnswerResult, StreamEvent } from "../lib/api";

const result: AnswerResult = {
  outcome: "answered",
  text: "🚀 Receipts last 24 hours.",
  citations: [
    {
      start: 2,
      end: 24,
      text: "Receipts last 24 hours.",
      source_ids: ["chunk-a"],
    },
  ],
  evidence: [
    {
      chunk_id: "chunk-a",
      document_id: "document",
      content_text:
        "Receipts last 24 hours. Upload retries reuse the same key.",
      source_spans: [
        {
          locator: {
            block_number: 1,
            page_number: 2,
            heading_path: ["Upload retries"],
          },
          start_char: 0,
          end_char: 50,
        },
      ],
    },
  ],
  error_code: null,
  configuration: {},
};
let streamMode: "complete" | "interrupted" | "hold" | "failed" = "complete";
let fetchMock: ReturnType<typeof vi.fn>;
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
function sse(events: StreamEvent[], signal: AbortSignal, hold: boolean) {
  return new Response(
    new ReadableStream({
      start(controller) {
        events.forEach((event, i) =>
          controller.enqueue(
            new TextEncoder().encode(
              `id: ${i + 1}\nevent: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
            ),
          ),
        );
        if (hold)
          signal.addEventListener(
            "abort",
            () => controller.error(new DOMException("Stopped", "AbortError")),
            { once: true },
          );
        else controller.close();
      },
    }),
    { headers: { "content-type": "text/event-stream" } },
  );
}
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  streamMode = "complete";
  fetchMock = vi.fn(async (url: string, options: RequestInit = {}) => {
    const path = String(url);
    const identity = new Headers(options.headers).get("X-Demo-User-ID");
    if (path.endsWith("/demo-users"))
      return response([
        { id: "admin", display_name: "Demo Admin" },
        { id: "reader", display_name: "Read Only" },
      ]);
    if (path.endsWith("/workspaces"))
      return response([
        {
          id: "workspace",
          name: "My workspace",
          role: identity === "reader" ? "member" : "owner",
        },
      ]);
    if (path.includes("/collections?") && !path.includes("/documents"))
      return response([
        {
          id: identity === "reader" ? "read-collection" : "collection",
          name: identity === "reader" ? "Reading room" : "My documents",
          slug: "docs",
          description: null,
        },
      ]);
    if (path.endsWith("/capabilities"))
      return response({
        can_upload: identity !== "reader",
        can_manage: identity !== "reader",
      });
    if (path.includes("/answers?")) return response([]);
    if (path.includes("/documents?")) return response([]);
    if (path.endsWith("/documents/document"))
      return response({
        id: "document",
        original_filename: "notes.txt",
        status: "ready",
        size_bytes: 50,
        media_type: "text/plain",
      });
    if (path.endsWith("/answers/saved"))
      return response({
        id: "saved",
        question: "How long do receipts last?",
        created_at: "2026-10-19T00:00:00Z",
        available: true,
        result,
      });
    if (path.endsWith("/answers/stream")) {
      const events: StreamEvent[] = [
        { type: "progress", stage: "generating" },
        { type: "content", text: "An unfinished draft" },
      ];
      if (streamMode === "complete")
        events.push(
          { type: "citations", citations: result.citations },
          { type: "complete", answer_id: "saved", result },
        );
      if (streamMode === "failed")
        events.push({
          type: "error",
          code: "invalid_citation",
          message: "The answer could not be verified.",
          answer_id: "failed",
        });
      return sse(events, options.signal as AbortSignal, streamMode === "hold");
    }
    throw new Error(`Unexpected fixture request ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
async function ready() {
  render(<Home />);
  await screen
    .findByRole("option", { name: "My documents" })
    .catch(() => undefined);
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: /My documents/ }),
    ).toBeInTheDocument(),
  );
}
async function ask() {
  fireEvent.change(
    screen.getByLabelText("Ask a question about your documents"),
    { target: { value: "How long do receipts last?" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Ask question" }));
}

describe("document workspace", () => {
  it("loads real selectors, offers upload navigation, and keeps question scope explicit", async () => {
    await ready();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Your files.",
    );
    expect(screen.getByLabelText("Demo identity simulated")).toHaveValue(
      "admin",
    );
    fireEvent.click(screen.getByRole("button", { name: "Add your documents" }));
    expect(
      await screen.findByRole("button", { name: "Choose a file" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("PDF, plain text, Markdown, or HTML · up to 20 MB"),
    ).toBeInTheDocument();
  });
  it("replaces the draft with the final answer and inspects a currently authorized source", async () => {
    await ready();
    await ask();
    expect(
      await screen.findByText(/🚀 Receipts last 24 hours/),
    ).toBeInTheDocument();
    expect(screen.queryByText("An unfinished draft")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open source 1" }));
    expect(await screen.findByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText(/Page 2/)).toBeInTheDocument();
    expect(
      screen.getByText(result.evidence[0].content_text),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Download original" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        String(url).endsWith("/answers/saved"),
      ),
    ).toBe(true);
  });
  it("clears failed drafts and starts a fresh request only on manual retry", async () => {
    streamMode = "interrupted";
    await ready();
    await ask();
    expect(
      await screen.findByText("Connection interrupted"),
    ).toBeInTheDocument();
    expect(screen.queryByText("An unfinished draft")).not.toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/answers/stream"),
      ),
    ).toHaveLength(1);
    streamMode = "complete";
    fireEvent.click(screen.getByRole("button", { name: "Retry question" }));
    expect(
      await screen.findByText(/🚀 Receipts last 24 hours/),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/answers/stream"),
      ),
    ).toHaveLength(2);
  });
  it("stops an active request without leaving a draft or citations", async () => {
    streamMode = "hold";
    await ready();
    await ask();
    expect(await screen.findByText("An unfinished draft")).toBeInTheDocument();
    const request = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/answers/stream"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await act(async () => {});
    expect(screen.getByText("You stopped this answer")).toBeInTheDocument();
    expect(screen.queryByText("An unfinished draft")).not.toBeInTheDocument();
    expect(request?.[1].signal?.aborted).toBe(true);
  });
  it("shows safe validation failures and clears the draft", async () => {
    streamMode = "failed";
    await ready();
    await ask();
    expect(
      await screen.findByText("The answer could not be verified."),
    ).toBeInTheDocument();
    expect(screen.queryByText("An unfinished draft")).not.toBeInTheDocument();
  });
  it("switches identities without retaining answers, source context, or manager controls", async () => {
    await ready();
    await ask();
    await screen.findByText(/🚀 Receipts last 24 hours/);
    fireEvent.click(screen.getByRole("button", { name: "Open source 1" }));
    await screen.findByText("notes.txt");
    fireEvent.change(screen.getByLabelText("Demo identity simulated"), {
      target: { value: "reader" },
    });
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Reading room/ }),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("notes.txt")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/🚀 Receipts last 24 hours/),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Permissions" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Documents" }));
    expect(
      await screen.findByText(
        "You can read this collection. Uploading requires write access.",
      ),
    ).toBeInTheDocument();
  });
  it("loads direct citation links through the selected identity", async () => {
    window.history.replaceState(
      null,
      "",
      "/?workspace=workspace&answer=saved&source=chunk-a",
    );
    await ready();
    expect(await screen.findByText("notes.txt")).toBeInTheDocument();
    expect(screen.getByText(/🚀 Receipts last 24 hours/)).toBeInTheDocument();
  });
});

it("keeps the explicit all-collections scope after an answer refresh", async () => {
  await ready();
  fireEvent.click(
    screen.getByRole("button", {
      name: "All accessible collections",
    }),
  );
  await ask();
  await screen.findByText(/🚀 Receipts last 24 hours/);
  await waitFor(() =>
    expect(
      screen.getByRole("button", {
        name: "All accessible collections",
      }),
    ).toHaveAttribute("aria-pressed", "true"),
  );
  const request = fetchMock.mock.calls.find(([url]) =>
    String(url).endsWith("/answers/stream"),
  );
  expect(JSON.parse(request?.[1].body as string).collection_id).toBeNull();
});
