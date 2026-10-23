import { sharedApiKey } from "@/lib/api/server";
import { proxyIdentity } from "@/lib/api/client-ip";

// Same-origin proxy for the copilot SSE stream. Mount as a Route Handler:
//   // app/api/copilot/turns/route.ts
//   export { POST } from "@/features/copilot/server/proxy";
//   export const runtime = "nodejs"; // segment config must be declared in the route file itself
//   export const dynamic = "force-dynamic";
// Server-only: the browser never sees the API URL or a key (API_URL, IGS_API_KEY are server env).

const MAX_BODY = 32_000;

export function POST(request: Request): Promise<Response> {
  return proxySse(request, {
    path: "/v1/copilot/turns",
    unavailable: ["copilot-unavailable", "No pudimos conectar con el copiloto."],
  });
}

/** Forwards one JSON POST to a core SSE endpoint and streams the answer back unbuffered. */
export async function proxySse(
  request: Request,
  { path, unavailable }: { path: string; unavailable: [code: string, detail: string] },
): Promise<Response> {
  const api = process.env.API_URL ?? "http://localhost:8000";
  const body = await request.text();
  if (body.length > MAX_BODY) {
    return problem(413, "payload-too-large", "La pregunta es demasiado larga.");
  }
  const headers: Record<string, string> = {
    "content-type": "application/json",
    accept: "text/event-stream",
  };
  const key = sharedApiKey();
  if (key) headers.authorization = `Bearer ${key}`;
  const requestId = request.headers.get("x-request-id");
  if (requestId) headers["x-request-id"] = requestId;
  Object.assign(headers, proxyIdentity(request.headers));

  let upstream: Response;
  try {
    upstream = await fetch(`${api.replace(/\/$/, "")}${path}`, {
      method: "POST",
      headers,
      body,
      signal: request.signal,
    });
  } catch {
    return problem(503, ...unavailable);
  }
  if (!upstream.ok || !upstream.body) {
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/problem+json" },
    });
  }
  return new Response(upstream.body, {
    status: 200,
    headers: {
      "content-type": "text/event-stream",
      "cache-control": "no-cache, no-transform",
      "x-accel-buffering": "no",
    },
  });
}

function problem(status: number, code: string, detail: string): Response {
  return Response.json(
    { type: `https://igs-os.dev/problems/${code}`, title: code, status, detail },
    { status, headers: { "content-type": "application/problem+json" } },
  );
}
