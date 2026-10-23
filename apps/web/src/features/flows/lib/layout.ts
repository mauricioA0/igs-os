import type { FlowGraph } from "./types";

export const NODE_WIDTH = 240;
const X_GAP = 290;
const Y_GAP = 150;

/**
 * Layered (Sugiyama-lite) layout, top to bottom:
 * 1. drop back edges found by DFS from the entry so the graph is a DAG,
 * 2. layer = longest path from the entry,
 * 3. order each layer by the barycenter of its parents (one sweep) to cut crossings,
 * 4. center every layer on x = 0.
 * Nodes not reachable from the entry go to an extra bottom layer.
 */
export function layoutFlow(flow: FlowGraph): Record<string, { x: number; y: number }> {
  const ids = flow.nodes.map((n) => n.id);
  const out = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const e of flow.edges) out.get(e.from)?.push(e.to);

  const forward = new Map<string, string[]>(ids.map((id) => [id, []]));
  const state = new Map<string, 0 | 1 | 2>(); // 0 new, 1 on stack, 2 done
  const visit = (id: string) => {
    state.set(id, 1);
    for (const to of out.get(id) ?? []) {
      const s = state.get(to) ?? 0;
      if (s === 1) continue; // back edge
      forward.get(id)!.push(to);
      if (s === 0) visit(to);
    }
    state.set(id, 2);
  };
  if (out.has(flow.entry)) visit(flow.entry);

  // Longest-path layering via topological order (Kahn) over forward edges of reachable nodes.
  const reachable = ids.filter((id) => state.get(id) === 2);
  const indeg = new Map<string, number>(reachable.map((id) => [id, 0]));
  for (const id of reachable) for (const to of forward.get(id)!) indeg.set(to, (indeg.get(to) ?? 0) + 1);
  const layer = new Map<string, number>([[flow.entry, 0]]);
  const queue = reachable.filter((id) => indeg.get(id) === 0);
  while (queue.length) {
    const id = queue.shift()!;
    for (const to of forward.get(id)!) {
      layer.set(to, Math.max(layer.get(to) ?? 0, (layer.get(id) ?? 0) + 1));
      indeg.set(to, indeg.get(to)! - 1);
      if (indeg.get(to) === 0) queue.push(to);
    }
  }
  const maxLayer = Math.max(0, ...layer.values());
  for (const id of ids) if (!layer.has(id)) layer.set(id, maxLayer + 1);

  const layers: string[][] = [];
  for (const id of ids) (layers[layer.get(id)!] ??= []).push(id);

  const parents = new Map<string, string[]>(ids.map((id) => [id, []]));
  for (const [from, tos] of forward) for (const to of tos) parents.get(to)!.push(from);

  const order = new Map<string, number>();
  const positions: Record<string, { x: number; y: number }> = {};
  layers.forEach((row = [], depth) => {
    const sorted = [...row].sort((a, b) => barycenter(a) - barycenter(b));
    sorted.forEach((id, i) => {
      order.set(id, i);
      positions[id] = { x: (i - (sorted.length - 1) / 2) * X_GAP - NODE_WIDTH / 2, y: depth * Y_GAP };
    });
  });
  return positions;

  function barycenter(id: string) {
    const ps = parents.get(id)!.filter((p) => order.has(p));
    if (!ps.length) return ids.indexOf(id) / ids.length;
    return ps.reduce((sum, p) => sum + order.get(p)!, 0) / ps.length;
  }
}
