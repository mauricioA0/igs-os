// Server-Sent Events over fetch (not EventSource): supports POST bodies (copilot turns), custom
// headers, AbortSignal, and reconnect with backoff for GET streams (execution progress).
import { toApiError } from "./errors";

export type SseEvent<T = unknown> = {
  event: string;
  data: T;
  id?: string;
};

export type SseOptions<T> = {
  method?: "GET" | "POST";
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
  onEvent: (event: SseEvent<T>) => void;
  onOpen?: () => void;
  /** Reconnect after the stream drops. Default: true for GET, false for POST (not idempotent). */
  reconnect?: boolean;
  /** Stop for good after this event (e.g. `end` of an execution). */
  isTerminal?: (event: SseEvent<T>) => boolean;
  maxRetries?: number;
  /** Base backoff in ms; doubles per attempt, capped at 15 s, with jitter. */
  retryDelayMs?: number;
  fetch?: typeof fetch;
};

/** Resolves when the stream ends (terminal event, server close without reconnect, or abort). */
export async function streamSse<T = unknown>(url: string, options: SseOptions<T>): Promise<void> {
  const {
    method = "GET",
    body,
    signal,
    onEvent,
    onOpen,
    isTerminal,
    maxRetries = 8,
    retryDelayMs = 500,
    fetch: fetchImpl = fetch,
  } = options;
  const reconnect = options.reconnect ?? method === "GET";
  let lastEventId: string | undefined;
  let serverRetry: number | undefined;

  for (let attempt = 0; ; attempt++) {
    if (signal?.aborted) return;
    const headers = new Headers(options.headers);
    headers.set("accept", "text/event-stream");
    if (body !== undefined) headers.set("content-type", "application/json");
    if (lastEventId) headers.set("last-event-id", lastEventId);

    let done = false;
    try {
      const response = await fetchImpl(url, {
        method,
        headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal,
        cache: "no-store",
      });
      if (!response.ok || !response.body) {
        const text = await response.text().catch(() => "");
        let parsed: unknown = text;
        try {
          parsed = JSON.parse(text);
        } catch {
          // not JSON: keep the text as the problem detail
        }
        const error = toApiError(parsed, response);
        // 4xx won't fix itself on retry.
        if (!reconnect || (response.status >= 400 && response.status < 500)) throw error;
        throw new RetryableError(error);
      }
      attempt = 0;
      onOpen?.();
      for await (const raw of readEvents(response.body)) {
        if (raw.retry !== undefined) serverRetry = raw.retry;
        if (raw.id !== undefined) lastEventId = raw.id;
        if (raw.data === undefined) continue; // comment / ping
        const event: SseEvent<T> = { event: raw.event ?? "message", data: parseData<T>(raw.data), id: raw.id };
        onEvent(event);
        if (isTerminal?.(event)) {
          done = true;
          break;
        }
      }
      if (done || !reconnect) return;
    } catch (error) {
      if (signal?.aborted || isAbort(error)) return;
      const cause = error instanceof RetryableError ? error.cause : error;
      if (!reconnect || !(error instanceof RetryableError || error instanceof TypeError)) throw cause;
      if (attempt >= maxRetries) throw cause;
    }
    await sleep(backoff(attempt, serverRetry ?? retryDelayMs), signal);
  }
}

class RetryableError extends Error {
  constructor(readonly cause: unknown) {
    super("retryable stream failure");
  }
}

type RawEvent = { event?: string; data?: string; id?: string; retry?: number };

/** Minimal text/event-stream parser (WHATWG §9.2): handles CRLF, multi-line data and comments. */
export async function* readEvents(stream: ReadableStream<Uint8Array>): AsyncGenerator<RawEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let current: RawEvent = {};
  let data: string[] = [];
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = buffer.search(/\r\n|\r|\n/)) !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + (buffer.startsWith("\r\n", newline) ? 2 : 1));
        if (line === "") {
          if (data.length || current.event || current.id !== undefined || current.retry !== undefined) {
            yield { ...current, data: data.length ? data.join("\n") : undefined };
          }
          current = {};
          data = [];
          continue;
        }
        if (line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon === -1 ? line : line.slice(0, colon);
        const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "data") data.push(value);
        else if (field === "event") current.event = value;
        else if (field === "id") current.id = value;
        else if (field === "retry" && /^\d+$/.test(value)) current.retry = Number(value);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseData<T>(raw: string): T {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return raw as T;
  }
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function backoff(attempt: number, base: number): number {
  const capped = Math.min(base * 2 ** attempt, 15_000);
  return capped / 2 + Math.random() * (capped / 2);
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}
