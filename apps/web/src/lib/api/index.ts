// Isomorphic entry: types, errors, the client factory and SSE. `serverApi` lives in
// `@/lib/api/server` and `browserApi` in `@/lib/api/browser` so neither leaks into the other.
export { createApiClient, unwrap, type ApiClient, type ApiClientOptions } from "./client";
export { ApiError, isProblem, toApiError, type Problem } from "./errors";
export { readEvents, streamSse, type SseEvent, type SseOptions } from "./sse";
export type { components, operations, paths } from "./schema";

import type { components } from "./schema";
/** Shorthand for a response/request schema: `Schema<"TripDetail">`. */
export type Schema<K extends keyof components["schemas"]> = components["schemas"][K];
