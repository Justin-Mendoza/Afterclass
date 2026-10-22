import { afterEach, describe, expect, it, vi } from "vitest";
import { GET, POST } from "./route";
const context = (path: string[]) => ({ params: Promise.resolve({ path }) });
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("same-origin API forwarding", () => {
  it("uses a fixed upstream, allows only selected headers, and streams the body", async () => {
    vi.stubEnv("API_INTERNAL_URL", "http://internal-api:8000");
    const fetch = vi.fn().mockResolvedValue(
      new Response("event: complete\ndata: {}\n\n", {
        headers: {
          "content-type": "text/event-stream",
          "x-request-id": "safe",
        },
      }),
    );
    vi.stubGlobal("fetch", fetch);
    const request = new Request(
      "http://frontend/api/v1/workspaces/w/answers/stream",
      {
        method: "POST",
        body: "{}",
        headers: {
          "content-type": "application/json",
          "x-demo-user-id": "user",
          cookie: "private-cookie",
          authorization: "private-token",
        },
      },
    );
    const response = await POST(
      request,
      context(["v1", "workspaces", "w", "answers", "stream"]),
    );
    expect(String(fetch.mock.calls[0][0])).toBe(
      "http://internal-api:8000/v1/workspaces/w/answers/stream",
    );
    const options = fetch.mock.calls[0][1];
    expect(options.headers.get("x-demo-user-id")).toBe("user");
    expect(options.headers.has("cookie")).toBe(false);
    expect(options.headers.has("authorization")).toBe(false);
    expect(options.body).toBe(request.body);
    expect(options.duplex).toBe("half");
    expect(await response.text()).toContain("event: complete");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });
  it("aborts upstream work when the downstream stream is cancelled", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(new TextEncoder().encode(": keepalive\n\n"));
          },
        }),
      ),
    );
    vi.stubGlobal("fetch", fetch);
    const response = await GET(
      new Request("http://frontend/api/v1/x"),
      context(["v1", "x"]),
    );
    await response.body!.cancel();
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
  });
  it("rejects paths outside v1 and sanitizes upstream connection errors", async () => {
    const fetch = vi
      .fn()
      .mockRejectedValue(new Error("private upstream detail"));
    vi.stubGlobal("fetch", fetch);
    expect(
      (
        await GET(
          new Request("http://frontend/api/private"),
          context(["private"]),
        )
      ).status,
    ).toBe(404);
    expect(
      (
        await GET(
          new Request("http://frontend/api/v1/x"),
          context(["v1", "..", "x"]),
        )
      ).status,
    ).toBe(404);
    const response = await GET(
      new Request("http://frontend/api/v1/x"),
      context(["v1", "x"]),
    );
    expect(response.status).toBe(503);
    expect(await response.text()).not.toContain("private upstream detail");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
