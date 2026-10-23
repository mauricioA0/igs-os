"use client";

import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import { createContext, createElement, useContext, useState, type ReactNode } from "react";
import { createStore, useStore, type StoreApi } from "zustand";
import { useShallow } from "zustand/react/shallow";
import type { FlowRFNode } from "./components/flow-node";
import { defaultConfig, portsOf } from "./lib/catalog";
import { edgeFor, toReactFlow } from "./lib/to-react-flow";
import type { FlowGraph, FlowNode, FlowNodeType, ValidationProblem } from "./lib/types";

export type EditorView = "canvas" | "steps";
export type Busy = "saving" | "validating" | "publishing" | "running" | null;
export type Notice = { kind: "ok" | "error" | "info"; message: string } | null;

type EditorState = {
  flowId: string;
  flowKey: string;
  etag: string;
  publishedVersion: number | null;
  base: FlowGraph; // everything but nodes/edges (trigger, settings, variables…)
  nodes: FlowRFNode[];
  edges: Edge[];
  selectedId: string | null;
  changes: number;
  problems: ValidationProblem[];
  showProblems: boolean;
  view: EditorView;
  busy: Busy;
  notice: Notice;

  onNodesChange: (changes: NodeChange<FlowRFNode>[]) => void;
  onEdgesChange: (changes: EdgeChange[]) => void;
  connect: (c: Connection) => void;
  addNode: (type: FlowNodeType, position: { x: number; y: number }) => void;
  updateNode: (id: string, patch: Partial<FlowNode>) => void;
  deleteNode: (id: string) => void;
  select: (id: string | null) => void;
  setView: (view: EditorView) => void;
  setProblems: (problems: ValidationProblem[], show?: boolean) => void;
  setShowProblems: (show: boolean) => void;
  setBusy: (busy: Busy) => void;
  setNotice: (notice: Notice) => void;
  markSaved: (etag: string) => void;
  markPublished: (version: number) => void;
  graph: () => FlowGraph;
};

export type EditorInit = { flowId: string; flowKey: string; etag: string; publishedVersion: number | null; graph: FlowGraph };

const isMoveOnly = (c: NodeChange) => c.type === "position" || c.type === "dimensions" || c.type === "select";

export function createEditorStore(init: EditorInit): StoreApi<EditorState> {
  const { nodes, edges } = toReactFlow(init.graph);
  return createStore<EditorState>()((set, get) => ({
    flowId: init.flowId,
    flowKey: init.flowKey,
    etag: init.etag,
    publishedVersion: init.publishedVersion,
    base: init.graph,
    nodes,
    edges,
    selectedId: null,
    changes: 0,
    problems: [],
    showProblems: false,
    view: "canvas",
    busy: null,
    notice: null,

    onNodesChange: (changes) =>
      set((s) => ({
        nodes: applyNodeChanges(changes, s.nodes),
        // Dragging counts as an edit (positions are saved); selection and measuring don't.
        changes: s.changes + changes.filter((c) => (c.type === "position" && !c.dragging) || !isMoveOnly(c)).length,
      })),
    onEdgesChange: (changes) =>
      set((s) => ({
        edges: applyEdgeChanges(changes, s.edges),
        changes: s.changes + changes.filter((c) => c.type === "remove").length,
      })),
    connect: (c) =>
      set((s) => ({
        // One edge per output port: a new connection replaces the old one.
        edges: addEdge(
          edgeFor(c.source, c.target, c.sourceHandle ?? undefined),
          s.edges.filter((e) => !(e.source === c.source && e.sourceHandle === c.sourceHandle)),
        ),
        changes: s.changes + 1,
      })),
    addNode: (type, position) =>
      set((s) => {
        let n = 1;
        while (s.nodes.some((x) => x.id === `${type}_${n}`)) n++;
        const node: FlowNode = { id: `${type}_${n}`, type, config: defaultConfig(type) };
        return {
          nodes: [
            ...s.nodes.map((x) => ({ ...x, selected: false })),
            { id: node.id, type: "flow", position, selected: true, data: { node, ports: portsOf(node), isEntry: false } },
          ],
          selectedId: node.id,
          changes: s.changes + 1,
        };
      }),
    updateNode: (id, patch) =>
      set((s) => ({
        nodes: s.nodes.map((n) => {
          if (n.id !== id) return n;
          const node = { ...n.data.node, ...patch };
          return { ...n, data: { ...n.data, node, ports: portsOf(node) } };
        }),
        changes: s.changes + 1,
      })),
    deleteNode: (id) =>
      set((s) => {
        const target = s.nodes.find((n) => n.id === id);
        if (!target || target.data.isEntry) return s;
        return {
          nodes: s.nodes.filter((n) => n.id !== id),
          edges: s.edges.filter((e) => e.source !== id && e.target !== id),
          selectedId: s.selectedId === id ? null : s.selectedId,
          changes: s.changes + 1,
        };
      }),
    select: (id) => set((s) => ({ selectedId: id, nodes: s.nodes.map((n) => (n.selected === (n.id === id) ? n : { ...n, selected: n.id === id })) })),
    setView: (view) => set({ view }),
    setProblems: (problems, show = true) =>
      set((s) => ({
        problems,
        showProblems: show,
        nodes: s.nodes.map((n) => {
          const mine = problems.filter((p) => p.node_id === n.id);
          const issue = mine.some((p) => p.severity === "error") ? "error" : mine.length ? "warning" : undefined;
          return n.data.issue === issue ? n : { ...n, data: { ...n.data, issue } };
        }),
      })),
    setShowProblems: (showProblems) => set({ showProblems }),
    setBusy: (busy) => set({ busy }),
    setNotice: (notice) => set({ notice }),
    markSaved: (etag) => set({ etag, changes: 0 }),
    markPublished: (version) => set({ publishedVersion: version }),
    graph: () => {
      const s = get();
      return {
        ...s.base,
        nodes: s.nodes.map((n) => ({ ...n.data.node, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } })),
        edges: s.edges.map((e) => ({
          from: e.source,
          to: e.target,
          ...(e.sourceHandle && e.sourceHandle !== "next" ? { port: e.sourceHandle } : {}),
        })),
      };
    },
  }));
}

const EditorContext = createContext<StoreApi<EditorState> | null>(null);

// One store per mounted editor (never a module singleton: two editors must not share state,
// and module scope is shared across requests on the server).
export function EditorStoreProvider({ init, children }: { init: EditorInit; children: ReactNode }) {
  const [store] = useState(() => createEditorStore(init));
  return createElement(EditorContext.Provider, { value: store }, children);
}

export function useEditor<T>(selector: (s: EditorState) => T): T {
  const store = useContext(EditorContext);
  if (!store) throw new Error("useEditor must be used inside <EditorStoreProvider>");
  return useStore(store, useShallow(selector));
}

export function useEditorApi(): StoreApi<EditorState> {
  const store = useContext(EditorContext);
  if (!store) throw new Error("useEditorApi must be used inside <EditorStoreProvider>");
  return store;
}
