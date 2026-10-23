import type { CopilotEvent, CopilotTransport, TurnRequest } from "./types";

/** The API answered but the copilot can't run (no model configured): 503 copilot-unavailable. */
export class CopilotUnavailableError extends Error {
  constructor(message = "El copiloto no está configurado en este entorno.") {
    super(message);
    this.name = "CopilotUnavailableError";
  }
}

export class CopilotHttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "CopilotHttpError";
  }
}

type RawEvent = { event: string; data: string };

/** Parses a `text/event-stream` body into `{event, data}` frames (comments and pings skipped). */
export async function* readSse(body: ReadableStream<Uint8Array>): AsyncGenerator<RawEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      // Normalize line endings on the whole buffer, not per chunk: a CRLF can be split across two
      // chunks ("…\r" | "\n…"), which used to merge two frames into one. A trailing lone "\r" waits
      // for the next chunk; any other bare CR is a line end per the SSE spec.
      buffer = (buffer + decoder.decode(value, { stream: true }))
        .replace(/\r\n/g, "\n")
        .replace(/\r(?!$)/g, "\n");
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = parseFrame(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (frame) yield frame;
        boundary = buffer.indexOf("\n\n");
      }
    }
    const tail = parseFrame(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): RawEvent | null {
  let event = "message";
  const data: string[] = [];
  for (const line of frame.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

export function toCopilotEvent({ event, data }: RawEvent): CopilotEvent | null {
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return null;
  }
  return { ...payload, type: event } as CopilotEvent;
}

/**
 * Real transport. The browser talks to a same-origin Next route that proxies to the core API
 * (see `server/proxy.ts`), so no API key or backend URL reaches the client.
 */
export function sseTransport(endpoint = "/api/copilot/turns"): CopilotTransport {
  return async function* run(request: TurnRequest, signal: AbortSignal) {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(request),
      signal,
    });
    if (res.status === 503) {
      const problem = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new CopilotUnavailableError(problem?.detail ?? undefined);
    }
    if (!res.ok || !res.body) {
      const problem = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new CopilotHttpError(res.status, problem?.detail ?? `Error ${res.status}`);
    }
    for await (const raw of readSse(res.body)) {
      const event = toCopilotEvent(raw);
      if (event) yield event;
    }
  };
}
