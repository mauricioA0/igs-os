import { MarkerType, type Edge } from "@xyflow/react";
import type { FlowNodeData, FlowRFNode } from "../components/flow-node";
import { portLabel, portsOf } from "./catalog";
import { layoutFlow } from "./layout";
import type { FlowGraph } from "./types";

// Saved positions win; nodes without one get the layered auto-layout.
export function toReactFlow(
  flow: FlowGraph,
  extra?: (nodeId: string) => Partial<FlowNodeData>,
): { nodes: FlowRFNode[]; edges: Edge[] } {
  const auto = flow.nodes.some((n) => !n.position || (n.position.x === 0 && n.position.y === 0)) ? layoutFlow(flow) : {};
  const nodes: FlowRFNode[] = flow.nodes.map((n) => ({
    id: n.id,
    type: "flow",
    position: auto[n.id] ?? n.position ?? { x: 0, y: 0 },
    data: { node: n, ports: portsOf(n), isEntry: n.id === flow.entry, ...extra?.(n.id) },
  }));
  return { nodes, edges: flow.edges.map((e) => edgeFor(e.from, e.to, e.port)) };
}

export function edgeFor(from: string, to: string, port?: string): Edge {
  const handle = port ?? "next";
  return {
    id: `${from}:${handle}->${to}`,
    source: from,
    sourceHandle: handle,
    target: to,
    type: "smoothstep",
    label: port && port !== "next" ? portLabel(port) : undefined,
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 3,
    markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
    style: port === "error" ? { strokeDasharray: "5 4" } : undefined,
  };
}
