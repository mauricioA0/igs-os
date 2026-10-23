import { describe, expect, it } from "vitest";
import { blockEdges, blocksOf, blocksOverlap, layoutBlocks, openingViewport } from "./blocks";
import type { FlowEdge, FlowNode } from "./types";

const n = (id: string, type: FlowNode["type"] = "say", extra: Partial<FlowNode> = {}): FlowNode => ({ id, type, config: {}, ...extra });

// greet → ask → check(condition) ─true→ yes1 → yes2 → done
//                                  └false→ no1 ────────↗
const nodes = [n("greet"), n("ask"), n("check", "condition"), n("yes1"), n("yes2"), n("no1"), n("done", "end")];
const edges: FlowEdge[] = [
  { from: "greet", to: "ask" },
  { from: "ask", to: "check" },
  { from: "check", to: "yes1", port: "true" },
  { from: "check", to: "no1", port: "false" },
  { from: "yes1", to: "yes2" },
  { from: "yes2", to: "done" },
  { from: "no1", to: "done" },
];

describe("blocksOf", () => {
  it("stacks linear runs and ends a block at a fork or a join", () => {
    const { blocks, blockOf } = blocksOf(nodes, edges, "greet");
    expect(blocks.map((b) => b.nodeIds)).toEqual([["greet", "ask", "check"], ["yes1", "yes2"], ["no1"], ["done"]]);
    expect(blockOf.get("check")).toBe("greet");
    expect(blockOf.get("yes2")).toBe("yes1");
  });

  it("never stacks the entry under another step and keeps a node with an error branch last", () => {
    const loop = [n("a"), n("b", "action", { onError: "branch" }), n("c")];
    const { blocks } = blocksOf(loop, [{ from: "a", to: "b" }, { from: "b", to: "c" }, { from: "c", to: "a" }], "a");
    expect(blocks.map((b) => b.nodeIds)).toEqual([["a", "b"], ["c"]]);
  });

  it("gives every node a block even in a headless loop", () => {
    const { blockOf } = blocksOf([n("s"), n("x"), n("y")], [{ from: "x", to: "y" }, { from: "y", to: "x" }], "s");
    expect(new Set(blockOf.keys())).toEqual(new Set(["s", "x", "y"]));
  });
});

describe("blockEdges", () => {
  it("hides links inside a block and moves the rest to the block", () => {
    const { blockOf } = blocksOf(nodes, edges, "greet");
    const rf = edges.map((e) => ({ id: `${e.from}->${e.to}`, source: e.from, target: e.to, sourceHandle: e.port ?? null }));
    expect(blockEdges(rf, blockOf).map((e) => [e.source, e.sourceHandle, e.target])).toEqual([
      ["greet", "true", "yes1"],
      ["greet", "false", "no1"],
      ["yes1", "next", "done"],
      ["no1", "next", "done"],
    ]);
  });
});

describe("layoutBlocks", () => {
  it("lays blocks left to right without overlaps", () => {
    const pos = layoutBlocks(nodes, edges, "greet");
    expect(Object.keys(pos).sort()).toEqual(["done", "greet", "no1", "yes1"]);
    expect(pos.greet.x).toBeLessThan(pos.yes1.x);
    expect(pos.yes1.x).toBe(pos.no1.x);
    expect(pos.yes1.x).toBeLessThan(pos.done.x);
    const placed = nodes.map((x) => ({ ...x, position: pos[x.id] ?? { x: 0, y: 0 } }));
    expect(blocksOverlap(placed, edges, "greet")).toBe(false);
  });

  it("flags saved top-down positions that would overlap as blocks", () => {
    const topDown = nodes.map((x, i) => ({ ...x, position: { x: 0, y: i * 80 } }));
    expect(blocksOverlap(topDown, edges, "greet")).toBe(true);
  });
});

describe("openingViewport", () => {
  const box = (x: number) => ({ x, y: 0, w: 288, h: 200 });

  it("fits a small flow whole", () => {
    const v = openingViewport([box(0), box(400)], { width: 1200, height: 600 });
    expect(v.zoom).toBeGreaterThanOrEqual(0.5);
    expect(v.zoom).toBeLessThanOrEqual(0.9);
  });

  it("zooms to the focus of a wide flow without passing the left edge", () => {
    const boxes = [0, 400, 800, 1200, 1600, 2000, 2400].map(box);
    const v = openingViewport(boxes, { width: 800, height: 500 }, { focus: boxes[1], center: true, zoom: 0.7 });
    expect(v.zoom).toBe(0.7);
    expect(v.x).toBeLessThanOrEqual(64);
  });

  it("keeps the leftmost block whole when the focus still fits on screen", () => {
    const boxes = [0, 400, 800, 1200, 1600, 2000, 2400].map(box);
    const v = openingViewport(boxes, { width: 800, height: 500 }, { focus: boxes[1], center: true, zoom: 0.7 });
    expect(v.x).toBeGreaterThanOrEqual(64); // left edge (x=0) lands at the gutter, not cut off
    expect(v.x + (400 + 288) * 0.7).toBeLessThanOrEqual(800 - 64); // focus fully visible
  });

  it("puts the focus on screen even if that cuts the left blocks", () => {
    const boxes = [0, 400, 800, 1200, 1600, 2000, 2400].map(box);
    const v = openingViewport(boxes, { width: 800, height: 500 }, { focus: boxes[5], center: true, zoom: 0.7 });
    expect(v.x + 2000 * 0.7).toBeGreaterThanOrEqual(0);
    expect(v.x + (2000 + 288) * 0.7).toBeLessThanOrEqual(800 - 64);
  });
});
