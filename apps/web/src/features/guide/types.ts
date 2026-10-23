// Wire types for POST /v1/guide/turns (services/core/src/igs_core/guide/routes.py). The event
// stream is the copilot's schema; the guide only uses start/text/tool_*/done/error.
import type { CopilotEvent } from "@/features/copilot";

export type GuideLocale = "es" | "en";

export type GuideTurnRequest = {
  message: string;
  conversation_id?: string;
  /** Route the visitor is on, so the guide can explain that screen. */
  page?: string;
};

export type GuideEvent = CopilotEvent;

export type GuideTransport = (
  request: GuideTurnRequest,
  signal: AbortSignal,
) => AsyncIterable<GuideEvent>;

/** A button the guide offered via its `suggest_route` tool. */
export type RouteSuggestion = { path: string; label: string };

export type GuideMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  routes: RouteSuggestion[];
  status: "streaming" | "done" | "error" | "stopped";
  error?: string;
};
