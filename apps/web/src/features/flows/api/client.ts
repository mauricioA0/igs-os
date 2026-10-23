import createClient from "openapi-fetch";
import type { paths } from "@/lib/api/schema";
import { sharedApiKey } from "@/lib/api/server";

// Server-side client for this feature. Reads work as the public demo tenant (no credentials);
// writes need an ops API key in IGS_API_KEY — never exposed to the browser.
// TODO(X1): swap for the shared client in src/lib/api once it lands.
export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function api() {
  const key = sharedApiKey();
  return createClient<paths>({
    baseUrl: API_URL,
    headers: key ? { Authorization: `Bearer ${key}` } : undefined,
    fetch: (req: Request) => fetch(req, { cache: "no-store" }),
  });
}

export type Problem = { title?: string; detail?: string; status?: number; type?: string; errors?: unknown };

export function problemMessage(error: unknown, fallback = "No se pudo completar la operación."): string {
  const p = error as Problem | undefined;
  if (!p) return fallback;
  if (p.status === 401 || p.status === 403) return "La demo pública es de solo lectura: guardar, publicar y probar requieren una cuenta de ops.";
  if (p.status === 412) return "Alguien guardó una versión más nueva del borrador. Recargá para ver los cambios.";
  if (p.status === 409) return p.detail ?? "El flow tiene que estar publicado antes de probarlo.";
  return p.detail ?? p.title ?? fallback;
}
