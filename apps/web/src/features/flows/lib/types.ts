import type { components } from "@/lib/api/schema";

// Graph shapes the editor works with. The source of truth is packages/flow-schema/flow.schema.json;
// `src/lib/flow-schema.ts` has the generated full types — this is the subset the canvas needs.

export type FlowNodeType =
  | "agent"
  | "extract"
  | "classify"
  | "knowledge_search"
  | "say"
  | "capture"
  | "choice"
  | "condition"
  | "switch"
  | "set"
  | "map"
  | "subflow"
  | "wait"
  | "end"
  | "http"
  | "action"
  | "send_message"
  | "emit_event"
  | "approval";

export type FlowNode = {
  id: string;
  type: FlowNodeType;
  name?: string;
  config?: Record<string, unknown>;
  retry?: Record<string, unknown>;
  onError?: "fail" | "continue" | "branch";
  position?: { x: number; y: number };
};

export type FlowEdge = { from: string; to: string; port?: string };

export type FlowTrigger = { type: string } & Record<string, unknown>;

export type FlowGraph = {
  id: string;
  name: string;
  description?: string;
  trigger: FlowTrigger;
  entry: string;
  variables?: Array<{ name: string; type: string; sensitive?: boolean }>;
  nodes: FlowNode[];
  edges: FlowEdge[];
  settings?: Record<string, unknown>;
} & Record<string, unknown>;

export type FlowSummary = components["schemas"]["FlowSummary"];
export type FlowDetail = components["schemas"]["FlowDetail"];
export type FlowVersion = components["schemas"]["FlowVersionOut"];
export type ValidationProblem = components["schemas"]["ValidationProblem"];
export type ExecutionSummary = components["schemas"]["ExecutionSummary"];
export type ExecutionDetail = components["schemas"]["ExecutionDetail"];
export type NodeRun = components["schemas"]["NodeRunOut"];
export type ExecutionStatus = ExecutionSummary["status"];

// Visual status of a node on the canvas (derived from its latest run).
export type NodeVisualStatus = "succeeded" | "failed" | "running" | "waiting" | "skipped" | "pending";

export function asGraph(raw: unknown): FlowGraph {
  return raw as FlowGraph;
}
