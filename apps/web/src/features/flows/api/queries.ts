import { api } from "./client";
import type { ExecutionDetail, ExecutionSummary, FlowDetail, FlowSummary, FlowVersion } from "../lib/types";

export async function listFlows(): Promise<FlowSummary[]> {
  const { data, error } = await api().GET("/v1/flows");
  if (error || !data) throw new Error("No se pudieron cargar los flows");
  return data;
}

export async function getFlowByKey(key: string): Promise<{ flow: FlowDetail; etag: string } | null> {
  const flows = await listFlows();
  const summary = flows.find((f) => f.key === key);
  if (!summary) return null;
  const { data, error, response } = await api().GET("/v1/flows/{flow_id}", { params: { path: { flow_id: summary.id } } });
  if (error || !data) return null;
  return { flow: data, etag: response.headers.get("etag") ?? `"rev-${data.draft_revision}"` };
}

export async function getVersion(flowId: string, version: number): Promise<FlowVersion | null> {
  const { data } = await api().GET("/v1/flows/{flow_id}/versions/{version}", {
    params: { path: { flow_id: flowId, version } },
  });
  return data ?? null;
}

export async function listExecutions(flowId?: string, limit = 20): Promise<ExecutionSummary[]> {
  const { data } = await api().GET("/v1/executions", {
    params: { query: { flow_id: flowId, limit } },
  });
  return data?.items ?? [];
}

export async function getExecution(id: string): Promise<ExecutionDetail | null> {
  const { data } = await api().GET("/v1/executions/{execution_id}", { params: { path: { execution_id: id } } });
  return data ?? null;
}

export async function pendingApprovalFor(executionId: string) {
  const { data } = await api().GET("/v1/approvals", {
    params: { query: { execution_id: executionId, status: "pending", limit: 1 } },
  });
  const first = data?.items?.[0];
  if (!first) return null;
  const detail = await api().GET("/v1/approvals/{approval_id}", { params: { path: { approval_id: first.id } } });
  return detail.data ?? null;
}
