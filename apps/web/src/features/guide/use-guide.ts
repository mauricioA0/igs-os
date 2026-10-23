"use client";

import { useCallback, useRef, useState } from "react";

import type { GuideMessage, GuideTransport, RouteSuggestion } from "./types";

let seq = 0;
const nextId = () => `g${++seq}`;

function routeFrom(output: unknown): RouteSuggestion | null {
  if (!output || typeof output !== "object") return null;
  const { path, label } = output as Record<string, unknown>;
  // Only same-site paths become links; the API validates too, this is belt and braces.
  if (typeof path !== "string" || typeof label !== "string") return null;
  if (!path.startsWith("/") || path.startsWith("//")) return null;
  return { path, label };
}

/** Conversation state for the guide widget: send, stream into the last message, stop. */
export function useGuide(transport: GuideTransport, page?: string) {
  const [messages, setMessages] = useState<GuideMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const conversation = useRef<string | undefined>(undefined);
  const abort = useRef<AbortController | null>(null);

  const patch = useCallback((id: string, f: (m: GuideMessage) => GuideMessage) => {
    setMessages((all) => all.map((m) => (m.id === id ? f(m) : m)));
  }, []);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || abort.current) return;
      const answerId = nextId();
      setMessages((all) => [
        ...all,
        { id: nextId(), role: "user", text: message, routes: [], status: "done" },
        { id: answerId, role: "assistant", text: "", routes: [], status: "streaming" },
      ]);
      const controller = new AbortController();
      abort.current = controller;
      setBusy(true);
      try {
        const stream = transport(
          { message, conversation_id: conversation.current, page },
          controller.signal,
        );
        for await (const event of stream) {
          switch (event.type) {
            case "start":
              conversation.current = event.conversation_id;
              break;
            case "text":
              patch(answerId, (m) => ({ ...m, text: m.text + event.delta }));
              break;
            case "tool_end": {
              const route = event.name === "suggest_route" && !event.is_error ? routeFrom(event.output) : null;
              if (route) patch(answerId, (m) => ({ ...m, routes: [...m.routes, route] }));
              break;
            }
            case "error":
              patch(answerId, (m) => ({ ...m, status: "error", error: event.message }));
              break;
            case "done":
              patch(answerId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
              break;
          }
        }
        patch(answerId, (m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
      } catch (err) {
        const stopped = controller.signal.aborted;
        patch(answerId, (m) => ({
          ...m,
          status: stopped ? "stopped" : "error",
          error: stopped ? undefined : err instanceof Error ? err.message : String(err),
        }));
      } finally {
        abort.current = null;
        setBusy(false);
      }
    },
    [page, patch, transport],
  );

  const stop = useCallback(() => abort.current?.abort(), []);

  return { messages, busy, send, stop };
}
