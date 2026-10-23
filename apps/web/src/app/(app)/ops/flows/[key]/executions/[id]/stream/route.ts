import { API_URL } from "@/features/flows/api/client";
import { sharedApiKey } from "@/lib/api/server";

// Proxies the API's execution SSE so the browser never talks to the API with a key.
export async function GET(request: Request, ctx: { params: Promise<{ key: string; id: string }> }) {
  const { id } = await ctx.params;
  const key = sharedApiKey();
  const upstream = await fetch(`${API_URL}/v1/executions/${encodeURIComponent(id)}/stream`, {
    headers: { Accept: "text/event-stream", ...(key ? { Authorization: `Bearer ${key}` } : {}) },
    signal: request.signal,
    cache: "no-store",
  });
  if (!upstream.ok || !upstream.body) {
    return new Response(null, { status: upstream.status === 404 ? 404 : 502 });
  }
  return new Response(upstream.body, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform", Connection: "keep-alive" },
  });
}
