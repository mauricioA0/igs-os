"use server";

import { revalidatePath } from "next/cache";
import { api, problemMessage, type Problem } from "./api/client";
import type { FlowGraph, ValidationProblem } from "./lib/types";

export type ActionError = { ok: false; message: string; status?: number; problems?: ValidationProblem[] };

export type SaveResult = { ok: true; etag: string; revision: number } | ActionError;
export type ValidateResult = { ok: true; valid: boolean; problems: ValidationProblem[] } | ActionError;
export type PublishResult = { ok: true; version: number } | ActionError;
export type StartResult = { ok: true; executionId: string } | ActionError;

function fail(error: unknown): ActionError {
  const p = error as Problem | undefined;
  const problems = Array.isArray(p?.errors) && p.status === 422 && p.type?.endsWith("flow-invalid") ? (p.errors as ValidationProblem[]) : undefined;
  return { ok: false, message: problemMessage(error), status: p?.status, problems };
}

export async function saveDraft(flowId: string, etag: string, graph: FlowGraph): Promise<SaveResult> {
  const { data, error, response } = await api().PUT("/v1/flows/{flow_id}/draft", {
    params: { path: { flow_id: flowId }, header: { "If-Match": etag } },
    body: { graph },
  });
  if (error || !data) return fail(error);
  return { ok: true, etag: response.headers.get("etag") ?? `"rev-${data.draft_revision}"`, revision: data.draft_revision };
}

export async function validateGraph(flowId: string, graph: FlowGraph): Promise<ValidateResult> {
  const { data, error } = await api().POST("/v1/flows/{flow_id}/validate", {
    params: { path: { flow_id: flowId } },
    body: { graph },
  });
  if (error || !data) return fail(error);
  return { ok: true, valid: data.ok, problems: data.problems };
}

export async function publishDraft(flowId: string, flowKey: string, etag: string, changelog: string): Promise<PublishResult> {
  const { data, error } = await api().POST("/v1/flows/{flow_id}/publish", {
    params: { path: { flow_id: flowId }, header: { "If-Match": etag } },
    body: { changelog },
  });
  if (error || !data) return fail(error);
  revalidatePath(`/ops/flows/${flowKey}`);
  revalidatePath("/ops/flows");
  return { ok: true, version: data.version };
}

export async function startTestRun(flowId: string, trigger: Record<string, unknown>): Promise<StartResult> {
  const { data, error } = await api().POST("/v1/flows/{flow_id}/executions", {
    params: { path: { flow_id: flowId } },
    body: { trigger, vars: {} },
  });
  if (error || !data) return fail(error);
  return { ok: true, executionId: data.id };
}

export async function decideApproval(
  approvalId: string,
  payloadHash: string,
  decision: "approved" | "rejected",
  comment?: string,
): Promise<{ ok: true } | ActionError> {
  const { error } = await api().POST("/v1/approvals/{approval_id}/decision", {
    params: { path: { approval_id: approvalId } },
    body: { decision, payload_hash: payloadHash, comment },
  });
  if (error) return fail(error);
  return { ok: true };
}

export async function cancelExecution(executionId: string): Promise<{ ok: true } | ActionError> {
  const { error } = await api().POST("/v1/executions/{execution_id}/cancel", {
    params: { path: { execution_id: executionId } },
  });
  if (error) return fail(error);
  return { ok: true };
}
