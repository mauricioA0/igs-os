import { ApiError } from "@/lib/api/errors";

// QA D-14: "not configured" (503 ai-unavailable) is not "the model failed" (502/timeout).
export type AiUnavailable = "not-configured" | "failed";

export function aiUnavailable(error: unknown): AiUnavailable {
  return error instanceof ApiError && error.code === "ai-unavailable" ? "not-configured" : "failed";
}

export const AI_UNAVAILABLE_COPY: Record<AiUnavailable, string> = {
  "not-configured": "La IA no está configurada en este entorno",
  failed: "El modelo no respondió",
};
