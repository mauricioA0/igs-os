// Server-only: reads API_URL / IGS_API_KEY (see lib/api/server.ts).
import { isProblem } from "@/lib/api/errors";
import { apiUrl, serverApi, sharedApiKey } from "@/lib/api/server";

// Write endpoints added in wave 4 (PATCH trip items, PATCH leads) aren't in the generated
// `schema.d.ts` yet, so these go through `fetch` with the same base URL and credentials as
// `serverApi()`. Switch to the typed client once the types are regenerated.

export type WriteResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; code: string; message: string };

export async function apiWrite<T>(method: "PATCH" | "POST", path: string, body: unknown): Promise<WriteResult<T>> {
  const headers = new Headers({ "content-type": "application/json", accept: "application/json" });
  const key = sharedApiKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  let res: Response;
  try {
    res = await fetch(`${apiUrl()}${path}`, { method, headers, body: JSON.stringify(body), cache: "no-store" });
  } catch {
    return { ok: false, status: 0, code: "network-error", message: "No se pudo conectar con la API." };
  }
  const payload: unknown = await res.json().catch(() => null);
  if (res.ok) return { ok: true, data: payload as T };
  const code = isProblem(payload) ? (payload.type?.split("/").pop() ?? "error") : `http-${res.status}`;
  return { ok: false, status: res.status, code, message: writeMessage(res.status, code, payload) };
}

function writeMessage(status: number, code: string, payload: unknown): string {
  if (status === 403 || code === "read-only-demo") return READ_ONLY_REASON;
  if (status === 404 || status === 405) return "La API todavía no expone esta edición.";
  if (code === "invalid-transition") return "Ese cambio de estado no está permitido por las reglas del proceso.";
  if (code === "lost-reason-required") return "Falta el motivo de la pérdida.";
  // 409 covers both a disallowed transition and a concurrent change: the API's detail says which.
  if (isProblem(payload) && payload.detail) return payload.detail;
  if (status === 409) return "El estado cambió mientras lo mirabas. Recargá para ver la versión actual.";
  if (isProblem(payload)) return payload.title;
  return `No se pudo guardar (HTTP ${status}).`;
}

export const READ_ONLY_REASON =
  "La demo pública es de solo lectura: podés explorar todo, pero los cambios los hace el equipo de ops con su usuario.";

/** Whether this server can write on behalf of the viewer (the public demo can't). */
export async function writeAccess(): Promise<{ canWrite: boolean; reason?: string }> {
  const { data } = await serverApi().GET("/v1/me").catch(() => ({ data: undefined }));
  if (!data) return { canWrite: false, reason: "No se pudo verificar el acceso." };
  if (data.kind === "demo" || data.role === "viewer") return { canWrite: false, reason: READ_ONLY_REASON };
  return { canWrite: true };
}
