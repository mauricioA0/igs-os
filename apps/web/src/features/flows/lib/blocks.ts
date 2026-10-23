import { portsOf } from "./catalog";
import { layoutFlow } from "./layout";
import type { FlowEdge, FlowNode } from "./types";

// Voiceflow-style blocks over our node graph: a block is a maximal linear run of steps
// (each one leads only to the next through "next", and the next has no other way in).
// The graph stays node-based (save, validate and publish never see blocks); blocks are
// only how the canvas draws it. A block's id is its first step's id, so the block's
// position is that node's position and every edge into a block lands on its first step.

export type Block = { id: string; nodeIds: string[] };

export const BLOCK_WIDTH = 288;
const HEADER_H = 46;
const STEP_H = 58;
const OUTPUT_H = 30;
const COL_GAP = 120;
const ROW_GAP = 56;

export function blocksOf(nodes: FlowNode[], edges: FlowEdge[], entry: string): { blocks: Block[]; blockOf: Map<string, string> } {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const incoming = new Map<string, number>();
  const outgoing = new Map<string, FlowEdge[]>();
  for (const e of edges) {
    if (!byId.has(e.from) || !byId.has(e.to)) continue;
    incoming.set(e.to, (incoming.get(e.to) ?? 0) + 1);
    outgoing.set(e.from, [...(outgoing.get(e.from) ?? []), e]);
  }

  // node → the step stacked right below it in the same block.
  const below = new Map<string, string>();
  for (const n of nodes) {
    const out = outgoing.get(n.id) ?? [];
    const ports = portsOf(n);
    if (ports.length !== 1 || ports[0] !== "next" || out.length !== 1) continue;
    const to = out[0].to;
    if ((out[0].port ?? "next") !== "next" || to === entry || to === n.id || incoming.get(to) !== 1) continue;
    below.set(n.id, to);
  }

  const stacked = new Set(below.values());
  const blocks: Block[] = [];
  const blockOf = new Map<string, string>();
  const build = (head: string) => {
    const ids: string[] = [];
    for (let id: string | undefined = head; id && !blockOf.has(id); id = below.get(id)) {
      blockOf.set(id, head);
      ids.push(id);
    }
    blocks.push({ id: head, nodeIds: ids });
  };
  const ordered = [...nodes].sort((a, b) => (a.id === entry ? -1 : b.id === entry ? 1 : 0));
  for (const n of ordered) if (!stacked.has(n.id)) build(n.id);
  // A closed loop of single steps has no head: start it anywhere.
  for (const n of ordered) if (!blockOf.has(n.id)) build(n.id);
  return { blocks, blockOf };
}

/** Last step of each block: the one whose ports are the block's outputs. */
export function lastStep(block: Block): string {
  return block.nodeIds[block.nodeIds.length - 1];
}

export function blockHeight(steps: number, outputs: string[]): number {
  const labeled = outputs.length === 1 && outputs[0] === "next" ? 0 : outputs.length;
  return HEADER_H + steps * STEP_H + labeled * OUTPUT_H + 12;
}

/** Edges as the canvas draws them: links inside a block disappear, the rest leave from the block. */
export function blockEdges<E extends { id: string; source: string; target: string; sourceHandle?: string | null }>(
  edges: E[],
  blockOf: Map<string, string>,
): E[] {
  const out: E[] = [];
  for (const e of edges) {
    const from = blockOf.get(e.source);
    const to = blockOf.get(e.target);
    if (!from || !to) continue;
    if (from === to && e.target !== to) continue; // stacked inside the same block
    out.push({ ...e, source: from, sourceHandle: e.sourceHandle ?? "next" });
  }
  return out;
}

/**
 * Left-to-right layout of blocks: the layered layout of the block graph gives each block a
 * column and an order, then each column stacks its blocks by their real height.
 */
export function layoutBlocks(nodes: FlowNode[], edges: FlowEdge[], entry: string): Record<string, { x: number; y: number }> {
  const { blocks, blockOf } = blocksOf(nodes, edges, entry);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const collapsed = {
    id: "blocks",
    name: "blocks",
    trigger: { type: "manual" },
    entry,
    nodes: blocks.map((b) => byId.get(b.id)!),
    edges: blockEdges(
      edges.map((e, i) => ({ id: String(i), source: e.from, target: e.to, sourceHandle: e.port })),
      blockOf,
    )
      .filter((e) => e.source !== e.target)
      .map((e) => ({ from: e.source, to: e.target })),
  };
  const raw = layoutFlow(collapsed);
  const columns = new Map<number, Array<{ id: string; x: number }>>();
  for (const b of blocks) {
    const p = raw[b.id] ?? { x: 0, y: 0 };
    const col = Math.round(p.y);
    columns.set(col, [...(columns.get(col) ?? []), { id: b.id, x: p.x }]);
  }
  const heightOf = new Map(blocks.map((b) => [b.id, blockHeight(b.nodeIds.length, portsOf(byId.get(lastStep(b))!))]));
  const positions: Record<string, { x: number; y: number }> = {};
  [...columns.keys()]
    .sort((a, b) => a - b)
    .forEach((key, colIndex) => {
      const col = columns.get(key)!.sort((a, b) => a.x - b.x);
      const total = col.reduce((h, c) => h + heightOf.get(c.id)! + ROW_GAP, -ROW_GAP);
      let y = -total / 2;
      for (const c of col) {
        positions[c.id] = { x: colIndex * (BLOCK_WIDTH + COL_GAP), y: Math.round(y) };
        y += heightOf.get(c.id)! + ROW_GAP;
      }
    });
  return positions;
}

/** True when blocks drawn at the saved positions would overlap (e.g. positions from the old top-down canvas). */
export function blocksOverlap(nodes: FlowNode[], edges: FlowEdge[], entry: string): boolean {
  const { blocks } = blocksOf(nodes, edges, entry);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const boxes = [];
  for (const b of blocks) {
    const p = byId.get(b.id)?.position;
    if (!p) return true;
    boxes.push({ x: p.x, y: p.y, h: blockHeight(b.nodeIds.length, portsOf(byId.get(lastStep(b))!)) });
  }
  for (let i = 0; i < boxes.length; i++)
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i];
      const b = boxes[j];
      if (Math.abs(a.x - b.x) < BLOCK_WIDTH + 16 && a.y < b.y + b.h + 8 && b.y < a.y + a.h + 8) return true;
    }
  return false;
}

export type Box = { x: number; y: number; w: number; h: number };

/**
 * Opening viewport for a block canvas of `size`: the whole flow when it reads at ≥ `minFit` zoom;
 * otherwise `zoom` on `focus` (default: the first box), left-anchored or centered (`center`).
 */
export function openingViewport(
  boxes: Box[],
  size: { width: number; height: number },
  opts: { focus?: Box; center?: boolean; zoom?: number; minFit?: number; pad?: number } = {},
): { x: number; y: number; zoom: number } {
  const { zoom = 0.7, minFit = 0.5, pad = 64 } = opts;
  if (!boxes.length) return { x: 0, y: 0, zoom: 1 };
  const minX = Math.min(...boxes.map((b) => b.x));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxX = Math.max(...boxes.map((b) => b.x + b.w));
  const maxY = Math.max(...boxes.map((b) => b.y + b.h));
  const fit = Math.min(0.9, (size.width - 2 * pad) / (maxX - minX), (size.height - 2 * pad) / (maxY - minY));
  if (fit >= minFit) {
    return {
      x: (size.width - (maxX - minX) * fit) / 2 - minX * fit,
      y: (size.height - (maxY - minY) * fit) / 2 - minY * fit,
      zoom: fit,
    };
  }
  const f = opts.focus ?? boxes[0];
  let x = pad - f.x * zoom;
  if (opts.center) {
    // Center the focus, but don't cut the flow's left blocks in half: pull right until the left
    // edge is in view, as long as the focus itself stays on screen.
    const centered = size.width / 2 - (f.x + f.w / 2) * zoom;
    const leftInView = Math.max(centered, pad - minX * zoom);
    x = Math.min(leftInView, size.width - pad - (f.x + f.w) * zoom);
  }
  return { x, y: size.height / 2 - (f.y + Math.min(f.h, 180) / 2) * zoom, zoom };
}
