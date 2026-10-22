// A fixed upstream, not a general proxy. The backend owns all authorization.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ path: string[] }> };

async function forward(request: Request, context: Context) {
  const { path } = await context.params;
  if (path[0] !== "v1" || path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part))) {
    return Response.json(
      { error: { code: "not_found", message: "Endpoint not found." } },
      { status: 404 },
    );
  }
  const upstream = new URL(
    `/${path.join("/")}`,
    process.env.API_INTERNAL_URL || "http://127.0.0.1:8000",
  );
  upstream.search = new URL(request.url).search;
  const headers = new Headers();
  for (const key of [
    "content-type",
    "accept",
    "x-demo-user-id",
    "idempotency-key",
    "last-event-id",
  ]) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  const controller = new AbortController();
  const abort = () => controller.abort();
  request.signal.addEventListener("abort", abort, { once: true });
  if (request.signal.aborted) controller.abort();
  const cleanup = () => request.signal.removeEventListener("abort", abort);
  try {
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      signal: controller.signal,
      cache: "no-store",
      redirect: "manual",
    };
    if (!["GET", "HEAD"].includes(request.method)) {
      init.body = request.body;
      init.duplex = "half";
    }
    const response = await fetch(upstream, init);
    const outgoing = new Headers({
      "Cache-Control": "no-store",
      "X-Accel-Buffering": "no",
    });
    for (const key of ["content-type", "content-disposition", "x-request-id"]) {
      const value = response.headers.get(key);
      if (value) outgoing.set(key, value);
    }
    if (!response.body) {
      cleanup();
      return new Response(null, { status: response.status, headers: outgoing });
    }
    const reader = response.body.getReader();
    const body = new ReadableStream({
      async pull(sink) {
        try {
          const { done, value } = await reader.read();
          if (done) {
            cleanup();
            sink.close();
            reader.releaseLock();
          } else sink.enqueue(value);
        } catch (error) {
          cleanup();
          controller.abort();
          sink.error(error);
        }
      },
      async cancel() {
        cleanup();
        controller.abort();
        await reader.cancel().catch(() => {});
      },
    });
    return new Response(body, { status: response.status, headers: outgoing });
  } catch {
    cleanup();
    return Response.json(
      {
        error: {
          code: "api_unavailable",
          message:
            "The API is unavailable. Check that the local stack is running.",
        },
      },
      { status: 503 },
    );
  }
}

export {
  forward as GET,
  forward as POST,
  forward as PATCH,
  forward as PUT,
  forward as DELETE,
};
