import type { components } from "./schema";

export type Problem = components["schemas"]["Problem"];

/** An RFC 9457 problem returned by `services/core`, or a transport failure shaped like one. */
export class ApiError extends Error {
  readonly status: number;
  readonly type: string;
  readonly title: string;
  readonly detail?: string;
  readonly requestId?: string;
  readonly errors?: Problem["errors"];

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.type = problem.type;
    this.title = problem.title;
    this.detail = problem.detail ?? undefined;
    this.requestId = problem.request_id ?? undefined;
    this.errors = problem.errors;
  }

  /** The API's problem `type` slug, e.g. "approval-changed", "not-found". */
  get code(): string {
    return this.type.split("/").pop() ?? this.type;
  }
}

export function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).status === "number" &&
    typeof (value as Problem).title === "string"
  );
}

/** Builds an ApiError from whatever a failed response carried (problem+json or not). */
export function toApiError(body: unknown, response?: Response): ApiError {
  if (isProblem(body)) return new ApiError({ ...body, type: body.type ?? "about:blank" });
  const status = response?.status ?? 0;
  return new ApiError({
    type: status ? "about:blank" : "network-error",
    title: response?.statusText || (status ? `HTTP ${status}` : "Network error"),
    status,
    detail: typeof body === "string" ? body : undefined,
    request_id: response?.headers.get("x-request-id") ?? undefined,
  });
}
