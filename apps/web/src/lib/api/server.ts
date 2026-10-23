// Server-side client (Server Components, server actions, route handlers). Reads the private
// `API_URL`, so it never ends up in the browser bundle; importing this from a Client Component
// gets an undefined base URL and fails loudly in `serverApi()`.
import { createApiClient, type ApiClient } from "./client";

const DEFAULT_API_URL = "http://localhost:8000";

export function apiUrl(): string {
  return (process.env.API_URL ?? DEFAULT_API_URL).replace(/\/+$/, "");
}

/**
 * One client per call: headers may depend on the request (a user's session later). The demo
 * tenant needs no credentials; `IGS_API_KEY` is for server-to-server use outside the demo.
 */
export function serverApi(options: { headers?: HeadersInit } = {}): ApiClient {
  if (typeof window !== "undefined") throw new Error("serverApi() must run on the server");
  const headers = new Headers(options.headers);
  const key = sharedApiKey();
  if (key && !headers.has("authorization")) headers.set("authorization", `Bearer ${key}`);
  return createApiClient({ baseUrl: apiUrl(), headers });
}

/**
 * The server's shared API key, or `undefined`.
 *
 * The web app has no sign-in yet, so anything done with this key is done on behalf of *every*
 * visitor: server actions and proxy routes are public endpoints. Using an ops key there would
 * let anyone approve, publish or cancel (docs/reviews/security-2026-10.md, S-01). It is only
 * honored outside production, or when the deployment is itself access-controlled and says so
 * with `IGS_WEB_ALLOW_SHARED_KEY=1` (e.g. a password-protected staging).
 */
export function sharedApiKey(env: Record<string, string | undefined> = process.env): string | undefined {
  const key = env.IGS_API_KEY;
  if (!key) return undefined;
  if (env.NODE_ENV === "production" && env.IGS_WEB_ALLOW_SHARED_KEY !== "1") return undefined;
  return key;
}
