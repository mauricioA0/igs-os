// Browser client. Calls go to the same origin under `/api/igs/*`, which next.config rewrites to
// `API_URL`: no CORS, no API host or key in the bundle, and streaming (SSE) passes through.
// When real user auth lands, swap the rewrite for a route handler that adds the session token.
import { createApiClient, type ApiClient } from "./client";

export const BROWSER_API_BASE = "/api/igs";

let shared: ApiClient | undefined;

export function browserApi(): ApiClient {
  shared ??= createApiClient({ baseUrl: BROWSER_API_BASE });
  return shared;
}

/** Absolute-path URL for endpoints consumed outside openapi-fetch (SSE). */
export function browserApiUrl(path: string): string {
  return `${BROWSER_API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}
