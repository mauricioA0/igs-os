import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, readEvents, streamSse, unwrap } from ".";

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { headers: { "content-type": "application/json" }, ...init });

function sseBody(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

describe("api client", () => {
  it("returns data and sends a request id", async () => {
    const fetchMock = vi.fn(async (req: Request) => {
      expect(req.headers.get("x-request-id")).toBeTruthy();
      return json({ items: [], next_cursor: null });
    });
    const api = createApiClient({ baseUrl: "http://api.test", fetch: fetchMock as typeof fetch });
    const page = await unwrap(api.GET("/v1/trips"));
    expect(page.items).toEqual([]);
    expect((fetchMock.mock.calls[0][0] as Request).url).toBe("http://api.test/v1/trips");
  });

  it("turns problem+json into a typed ApiError", async () => {
    const fetchMock = vi.fn(async () =>
      json(
        { type: "https://igs.example/problems/approval-changed", title: "Changed", status: 409, request_id: "r1" },
        { status: 409 },
      ),
    );
    const api = createApiClient({ baseUrl: "http://api.test", fetch: fetchMock as typeof fetch });
    const error = await unwrap(api.GET("/v1/trips")).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 409, code: "approval-changed", requestId: "r1" });
  });

  it("wraps non-problem failures", async () => {
    const fetchMock = vi.fn(async () => new Response("bad gateway", { status: 502, statusText: "Bad Gateway" }));
    const api = createApiClient({ baseUrl: "http://api.test", fetch: fetchMock as typeof fetch });
    await expect(unwrap(api.GET("/v1/trips"))).rejects.toMatchObject({ status: 502, title: "Bad Gateway" });
  });
});

describe("readEvents", () => {
  it("parses named events, multi-line data, ids and comments across chunk boundaries", async () => {
    const events = [];
    for await (const e of readEvents(
      sseBody([": ping\r\n\r\nevent: tool_start\r\nid: 1\r\ndata: {\"name\":", "\"get_trip\"}\r\n\r\n", "data: a\ndata: b\n\n"]),
    )) {
      events.push(e);
    }
    expect(events).toEqual([
      { event: "tool_start", id: "1", data: '{"name":"get_trip"}' },
      { data: "a\nb" },
    ]);
  });
});

describe("streamSse", () => {
  it("POSTs a body, parses JSON data and stops at the terminal event", async () => {
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.method).toBe("POST");
      expect(JSON.parse(init.body as string)).toEqual({ message: "hola" });
      return new Response(sseBody(['event: text\ndata: {"delta":"Ho"}\n\n', 'event: done\ndata: {}\n\n', "event: text\ndata: {}\n\n"]));
    });
    const seen: string[] = [];
    await streamSse("/api/igs/v1/copilot/turns", {
      method: "POST",
      body: { message: "hola" },
      fetch: fetchMock as unknown as typeof fetch,
      onEvent: (e) => seen.push(e.event),
      isTerminal: (e) => e.event === "done",
    });
    expect(seen).toEqual(["text", "done"]);
  });

  it("reconnects GET streams with Last-Event-ID after a drop", async () => {
    let call = 0;
    const fetchMock = vi.fn(async (_url: string, init: RequestInit) => {
      call++;
      if (call === 1) return new Response(sseBody(["id: 7\nevent: node_run\ndata: {}\n\n"]));
      expect(new Headers(init.headers).get("last-event-id")).toBe("7");
      return new Response(sseBody(['event: end\ndata: {"status":"completed"}\n\n']));
    });
    const seen: string[] = [];
    await streamSse("/api/igs/v1/executions/x/stream", {
      fetch: fetchMock as unknown as typeof fetch,
      retryDelayMs: 1,
      onEvent: (e) => seen.push(e.event),
      isTerminal: (e) => e.event === "end",
    });
    expect(seen).toEqual(["node_run", "end"]);
    expect(call).toBe(2);
  });

  it("does not retry client errors and surfaces the problem", async () => {
    const fetchMock = vi.fn(async () => json({ type: "about:blank", title: "Forbidden", status: 403 }, { status: 403 }));
    await expect(
      streamSse("/x", { fetch: fetchMock as unknown as typeof fetch, onEvent: () => {}, retryDelayMs: 1 }),
    ).rejects.toMatchObject({ status: 403 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("stops quietly when aborted", async () => {
    const controller = new AbortController();
    controller.abort();
    const fetchMock = vi.fn();
    await streamSse("/x", { fetch: fetchMock as unknown as typeof fetch, signal: controller.signal, onEvent: () => {} });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
