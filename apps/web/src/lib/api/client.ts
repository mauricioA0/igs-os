import createClient, { type Client, type Middleware } from "openapi-fetch";
import { toApiError } from "./errors";
import type { paths } from "./schema";

export type ApiClient = Client<paths>;

export type ApiClientOptions = {
  baseUrl: string;
  /** Extra headers on every request (e.g. Authorization from a server-side session). */
  headers?: HeadersInit;
  fetch?: typeof fetch;
};

const requestId: Middleware = {
  onRequest({ request }) {
    if (!request.headers.has("x-request-id") && typeof crypto?.randomUUID === "function") {
      request.headers.set("x-request-id", crypto.randomUUID());
    }
    return request;
  },
};

export function createApiClient({ baseUrl, headers, fetch: fetchImpl }: ApiClientOptions): ApiClient {
  const client = createClient<paths>({ baseUrl, headers, fetch: fetchImpl });
  client.use(requestId);
  return client;
}

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Turns openapi-fetch's `{ data, error }` into a value or a thrown `ApiError`, so containers can
 * `await unwrap(api.GET(...))` and let error boundaries / `error.tsx` handle failures.
 */
export async function unwrap<T>(result: Promise<FetchResult<T>>): Promise<T> {
  let resolved: FetchResult<T>;
  try {
    resolved = await result;
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw toApiError(cause instanceof Error ? cause.message : undefined);
  }
  const { data, error, response } = resolved;
  if (!response.ok || error !== undefined) throw toApiError(error, response);
  return data as T;
}
