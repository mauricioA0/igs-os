import type { components } from "@/lib/api/schema";

export type ApprovalSummary = components["schemas"]["ApprovalSummary"];
export type ApprovalDetail = components["schemas"]["ApprovalDetail"];
export type ApprovalDecisionIn = components["schemas"]["ApprovalDecisionIn"];
export type ApprovalDecisionOut = components["schemas"]["ApprovalDecisionOut"];
export type ProposedAction = components["schemas"]["ProposedAction"];
export type Me = components["schemas"]["Me"];
export type ApprovalStatus = ApprovalSummary["status"];

// Server actions can't throw rich errors to the client: failures come back as data.
export type ApiProblem = { status: number; code: string; title: string; detail?: string };
export type Result<T> = { ok: true; data: T } | { ok: false; problem: ApiProblem };
