// Same-origin proxy to the core guide (see features/copilot/server/proxy.ts): the browser never
// sees the API host or a key, and the visitor's address rides along for rate limiting.
import { proxySse } from "@/features/copilot/server/proxy";

export function POST(request: Request): Promise<Response> {
  return proxySse(request, {
    path: "/v1/guide/turns",
    unavailable: ["guide-unavailable", "No pudimos conectar con el asistente."],
  });
}

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
