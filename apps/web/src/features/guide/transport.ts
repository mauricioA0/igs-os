import { readSse, toCopilotEvent } from "@/features/copilot/sse";

import type { GuideEvent, GuideLocale, GuideTransport } from "./types";

/** Real transport: same-origin Next route → core /v1/guide/turns (see server/proxy.ts). */
export function sseGuideTransport(endpoint = "/api/guide/turns"): GuideTransport {
  return async function* run(request, signal) {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "text/event-stream" },
      body: JSON.stringify(request),
      signal,
    });
    if (!res.ok || !res.body) {
      const problem = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(problem?.detail ?? `Error ${res.status}`);
    }
    for await (const raw of readSse(res.body)) {
      const event = toCopilotEvent(raw);
      if (event) yield event;
    }
  };
}

const SCRIPT: Record<GuideLocale, { text: string; route: { path: string; label: string } }> = {
  es: {
    text:
      "IGS OS es un POC con datos ficticios: Lakeshore y el resto de los clientes no son reales. " +
      "Empezá por Hoy, que ordena lo que necesita a una persona, y después abrí Aprobaciones: " +
      "ahí ves lo que los agentes quieren hacer antes de que lo hagan.",
    route: { path: "/ops/approvals", label: "Ver aprobaciones" },
  },
  en: {
    text:
      "IGS OS is a POC with fictional data: Lakeshore and the other clients aren't real. Start " +
      "with the 2-minute tour, then open the ops panel to see what the agents want to do before " +
      "they do it.",
    route: { path: "/ops", label: "Open the ops panel" },
  },
};

/**
 * `?guide=fake`: scripted answer streamed word by word. Never calls the API, so it can't spend or
 * leak anything; the panel shows a "script" badge while it's on.
 */
export function fakeGuideTransport(locale: GuideLocale, delayMs = 30): GuideTransport {
  return async function* run(request, signal) {
    const { text, route } = SCRIPT[locale];
    const wait = (ms: number) =>
      delayMs ? new Promise((r) => setTimeout(r, ms)) : Promise.resolve();
    const events: GuideEvent[] = [
      { type: "start", run_id: "guide-fake", conversation_id: request.conversation_id ?? "guide-fake" },
      { type: "tool_start", call_id: "g1", name: "suggest_route", input: route },
      { type: "tool_end", call_id: "g1", name: "suggest_route", output: route, is_error: false, ms: 1 },
    ];
    for (const word of text.match(/\S+\s*/g) ?? []) events.push({ type: "text", delta: word });
    events.push({
      type: "done",
      run_id: "guide-fake",
      conversation_id: request.conversation_id ?? "guide-fake",
      stop_reason: "end_turn",
    });
    for (const event of events) {
      if (signal.aborted) throw new DOMException("Aborted", "AbortError");
      await wait(delayMs);
      yield event;
    }
  };
}
