"use client";

import "@xyflow/react/dist/style.css";
import "./flows.css";

import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
} from "@xyflow/react";
import { ChevronLeft, LayoutGrid, Maximize, Play } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { Button, PillGroup, PillNavItem } from "@/components/ui";
import { publishDraft, saveDraft, validateGraph } from "../actions";
import { BLOCK_WIDTH, blockEdges, blockHeight, blocksOf, blocksOverlap, lastStep, layoutBlocks, openingViewport, type Block } from "../lib/blocks";
import { stepsOf } from "../lib/steps";
import { useColorMode } from "../lib/use-color-mode";
import type { ExecutionSummary, FlowEdge, FlowGraph, FlowNodeType } from "../lib/types";
import { EditorStoreProvider, useEditor, useEditorApi, type EditorInit } from "../store";
import { DND_TYPE, FlowPanel, NodePanel, Palette, ProblemsPanel } from "./editor-panels";
import { TestPanel, useTestRun } from "./editor-test-panel";
import { blockNodeTypes, type BlockRFNode, type FlowRFNode } from "./flow-node";
import { StepsView } from "./steps-view";

type Props = EditorInit & { name: string; executions: ExecutionSummary[]; canWrite: boolean };

// Saved positions from the old one-node-per-card canvas would pile blocks on top of each other:
// lay the blocks out left to right instead (the new positions are saved with the next edit).
function withBlockLayout(graph: FlowGraph): FlowGraph {
  if (!blocksOverlap(graph.nodes, graph.edges, graph.entry)) return graph;
  const pos = layoutBlocks(graph.nodes, graph.edges, graph.entry);
  return { ...graph, nodes: graph.nodes.map((n) => (pos[n.id] ? { ...n, position: pos[n.id] } : n)) };
}

export function FlowEditorContainer({ executions, canWrite, name, ...init }: Props) {
  const [prepared] = useState(() => ({ ...init, graph: withBlockLayout(init.graph) }));
  return (
    <EditorStoreProvider init={prepared}>
      <ReactFlowProvider>
        <Editor name={name} executions={executions} canWrite={canWrite} />
      </ReactFlowProvider>
    </EditorStoreProvider>
  );
}

function graphOf(nodes: FlowRFNode[], edges: Edge[]): Pick<FlowGraph, "nodes" | "edges"> {
  return {
    nodes: nodes.map((n) => n.data.node),
    edges: edges.map((e) => ({ from: e.source, to: e.target, ...(e.sourceHandle && e.sourceHandle !== "next" ? { port: e.sourceHandle } : {}) })),
  };
}

const typing = (el: EventTarget) => el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));

function Editor({ name, executions, canWrite }: { name: string; executions: ExecutionSummary[]; canWrite: boolean }) {
  const s = useEditor((st) => ({
    flowId: st.flowId,
    flowKey: st.flowKey,
    nodes: st.nodes,
    edges: st.edges,
    selectedId: st.selectedId,
    changes: st.changes,
    problems: st.problems,
    showProblems: st.showProblems,
    publishedVersion: st.publishedVersion,
    view: st.view,
    busy: st.busy,
    notice: st.notice,
    base: st.base,
  }));
  const store = useEditorApi();
  const actions = store.getState();
  const router = useRouter();
  const { screenToFlowPosition, fitView, setViewport } = useReactFlow();
  const canvasRef = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState<"inspect" | "test">("inspect");
  const [dropBlock, setDropBlock] = useState<string | null>(null);
  const test = useTestRun(s.flowId, s.flowKey);
  const colorMode = useColorMode();

  // Warn before leaving with unsaved edits.
  useEffect(() => {
    if (!s.changes || !canWrite) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [s.changes, canWrite]);

  const entry = s.base.entry;
  const byId = useMemo(() => new Map(s.nodes.map((n) => [n.id, n])), [s.nodes]);
  const flowEdges = useMemo<FlowEdge[]>(() => s.edges.map((e) => ({ from: e.source, to: e.target, port: e.sourceHandle ?? undefined })), [s.edges]);
  const { blocks, blockOf } = useMemo(() => blocksOf(s.nodes.map((n) => n.data.node), flowEdges, entry), [s.nodes, flowEdges, entry]);
  const blockById = useMemo(() => new Map(blocks.map((b) => [b.id, b])), [blocks]);

  // The canvas draws blocks; the store (and everything saved) stays one node per step.
  const rfNodes = useMemo<BlockRFNode[]>(
    () =>
      blocks.map((b) => {
        const head = byId.get(b.id)!;
        return {
          id: b.id,
          type: "block",
          position: head.position,
          measured: head.measured,
          dragging: head.dragging,
          selected: !!s.selectedId && b.nodeIds.includes(s.selectedId),
          data: {
            steps: b.nodeIds.map((id) => {
              const n = byId.get(id)!;
              return { node: n.data.node, isEntry: n.data.isEntry, issue: n.data.issue, status: test.statuses.get(id) };
            }),
            outputs: byId.get(lastStep(b))!.data.ports,
            selectedStepId: s.selectedId,
            dropTarget: dropBlock === b.id,
          },
        };
      }),
    [blocks, byId, s.selectedId, test.statuses, dropBlock],
  );
  const rfEdges = useMemo(() => blockEdges(s.edges, blockOf).map((e) => ({ ...e, label: undefined })), [s.edges, blockOf]);

  const onNodesChange = (changes: NodeChange<BlockRFNode>[]) => {
    // Block id = its first step's id, so moves and measures apply to that node. Selection is ours.
    const kept = changes.filter((c) => c.type === "position" || c.type === "dimensions");
    if (kept.length) actions.onNodesChange(kept as unknown as NodeChange<FlowRFNode>[]);
  };

  const onConnect = (c: Connection) => {
    const block = blockById.get(c.source);
    if (block) actions.connect({ ...c, source: lastStep(block) });
  };

  /** Stack a new step at the end of `block` (keeping whatever came after it). */
  const appendTo = (block: Block, type: FlowNodeType) => {
    const tail = lastStep(block);
    const ports = byId.get(tail)?.data.ports ?? [];
    if (ports.length !== 1 || ports[0] !== "next") return false;
    const after = store.getState().edges.find((e) => e.source === tail && (e.sourceHandle ?? "next") === "next");
    const at = byId.get(block.id)!.position;
    actions.addNode(type, { x: at.x, y: at.y + 60 * block.nodeIds.length });
    const added = store.getState().selectedId!;
    actions.connect({ source: tail, sourceHandle: "next", target: added, targetHandle: null });
    if (after) actions.connect({ source: added, sourceHandle: "next", target: after.target, targetHandle: null });
    return true;
  };

  const addAt = (type: FlowNodeType, point: { x: number; y: number }, overBlock: string | null) => {
    const block = overBlock ? blockById.get(overBlock) : undefined;
    if (block && appendTo(block, type)) return;
    actions.addNode(type, screenToFlowPosition(point));
  };

  const blockUnder = (target: EventTarget | null) => (target instanceof Element ? target.closest("[data-block-id]")?.getAttribute("data-block-id") ?? null : null);

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDropBlock(null);
    const type = event.dataTransfer.getData(DND_TYPE) as FlowNodeType;
    if (type) addAt(type, { x: event.clientX, y: event.clientY }, blockUnder(event.target));
  };

  const onPaletteAdd = (type: FlowNodeType) => {
    if (s.view !== "canvas") actions.setView("canvas");
    const selectedBlock = s.selectedId ? blockOf.get(s.selectedId) ?? null : null;
    const rect = canvasRef.current?.getBoundingClientRect();
    addAt(type, { x: (rect?.left ?? 0) + (rect?.width ?? 0) / 2 - BLOCK_WIDTH / 2, y: (rect?.top ?? 0) + (rect?.height ?? 0) / 3 }, selectedBlock);
  };

  // Deleting a step in the middle of a block keeps the block joined.
  const removeStep = (id: string) => {
    const st = store.getState();
    if (st.nodes.find((n) => n.id === id)?.data.isEntry) return;
    const into = st.edges.filter((e) => e.target === id);
    const out = st.edges.filter((e) => e.source === id);
    const heal = into.length === 1 && out.length === 1 && (out[0].sourceHandle ?? "next") === "next" && blockOf.get(into[0].source) === blockOf.get(id) ? { from: into[0], to: out[0].target } : null;
    actions.deleteNode(id);
    if (heal) actions.connect({ source: heal.from.source, sourceHandle: heal.from.sourceHandle ?? "next", target: heal.to, targetHandle: null });
  };

  const detach = (id: string) => {
    const block = blockById.get(blockOf.get(id) ?? "");
    const link = store.getState().edges.find((e) => e.target === id);
    if (!block || !link || block.id === id) return;
    const at = byId.get(block.id)!.position;
    actions.onEdgesChange([{ type: "remove", id: link.id }]);
    actions.onNodesChange([{ type: "position", id, position: { x: at.x + BLOCK_WIDTH + 80, y: at.y + 58 * block.nodeIds.indexOf(id) }, dragging: false }]);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if ((e.key !== "Delete" && e.key !== "Backspace") || typing(e.target)) return;
    const picked = store.getState().edges.filter((x) => x.selected);
    if (picked.length) actions.onEdgesChange(picked.map((x): EdgeChange => ({ type: "remove", id: x.id })));
    else if (s.selectedId) removeStep(s.selectedId);
    else return;
    e.preventDefault();
  };

  const tidy = () => {
    const { nodes, edges, entry: start } = store.getState().graph();
    const pos = layoutBlocks(nodes, edges, start);
    actions.onNodesChange(Object.entries(pos).map(([id, position]) => ({ type: "position", id, position, dragging: false })));
    requestAnimationFrame(() => fitView({ duration: 300, padding: 0.15 }));
  };

  // Open like Voiceflow: at a readable zoom with the start block on the left, not the whole flow shrunk to fit.
  // Open with the whole flow in view when it reads at ≥ 0.5 zoom; otherwise anchor the start block
  // on the left (the canvas stops at the inspector, so nothing hides behind it).
  const openAtStart = () => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect || !blocks.length) return void fitView({ padding: 0.15 });
    const boxes = blocks.map((b) => {
      const p = byId.get(b.id)!.position;
      return { x: p.x, y: p.y, w: BLOCK_WIDTH, h: blockHeight(b.nodeIds.length, byId.get(lastStep(b))!.data.ports) };
    });
    const startBox = boxes[blocks.findIndex((b) => b.id === blockOf.get(entry))] ?? boxes[0];
    setViewport(openingViewport(boxes, rect, { focus: startBox, zoom: 0.7 }));
  };

  const validate = async (): Promise<boolean> => {
    actions.setBusy("validating");
    const res = await validateGraph(s.flowId, store.getState().graph());
    actions.setBusy(null);
    if (!res.ok) {
      actions.setNotice({ kind: "error", message: res.message });
      return false;
    }
    actions.setProblems(res.problems);
    return res.valid;
  };

  const save = async (): Promise<boolean> => {
    const st = store.getState();
    actions.setBusy("saving");
    const res = await saveDraft(st.flowId, st.etag, st.graph());
    actions.setBusy(null);
    if (!res.ok) {
      actions.setNotice({ kind: "error", message: res.message });
      return false;
    }
    actions.markSaved(res.etag);
    actions.setNotice({ kind: "ok", message: `Borrador guardado (revisión ${res.revision}).` });
    return true;
  };

  const publish = async () => {
    if (store.getState().changes && !(await save())) return;
    if (!(await validate())) return;
    const st = store.getState();
    actions.setBusy("publishing");
    const res = await publishDraft(st.flowId, st.flowKey, st.etag, "");
    actions.setBusy(null);
    if (!res.ok) {
      if (res.problems) actions.setProblems(res.problems);
      actions.setNotice({ kind: "error", message: res.message });
      return;
    }
    actions.markPublished(res.version);
    actions.setNotice({ kind: "ok", message: `Publicado v${res.version}. Las ejecuciones en curso siguen en su versión.` });
    router.refresh();
  };

  const selected = s.selectedId ? byId.get(s.selectedId) : undefined;
  const nodeMap = useMemo(() => new Map(s.nodes.map((n) => [n.id, n.data.node])), [s.nodes]);
  // Recomputed on every edit while the steps view is open (nodes/edges change identity).
  const { nodes: currentNodes, edges: currentEdges, view } = s;
  const steps = useMemo(
    () => (view === "steps" ? stepsOf({ ...(s.base as FlowGraph), ...graphOf(currentNodes, currentEdges) }) : []),
    [view, currentNodes, currentEdges, s.base],
  );
  const errors = s.problems.filter((p) => p.severity === "error").length;
  const issueOf = (id: string) => byId.get(id)?.data.issue;
  const statusOf = (id: string) => test.statuses.get(id);
  const writeHint = canWrite ? undefined : "La demo pública es de solo lectura: podés editar y validar acá, pero guardar, publicar y probar requieren una cuenta de ops.";
  const testBlocked = writeHint ?? (s.publishedVersion ? undefined : "Publicá una versión para probarla: la prueba corre siempre lo publicado.");
  const selectedBlock = selected ? blockOf.get(selected.id) : undefined;

  return (
    // Full-bleed under the ops header, like a canvas app: out of the shell's page container and padding.
    <div className="igs-flow -mt-10 ml-[calc(50%-50vw)] flex w-screen flex-col bg-background text-foreground md:-mb-16 md:-mt-14 md:h-[calc(100dvh-4rem)] md:min-h-[560px]">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-background px-3 py-2.5 sm:px-4">
        <Link href="/ops/flows" aria-label="Volver a Flows" title="Flows" className="grid size-8 shrink-0 place-items-center rounded-full bg-secondary text-nav-idle hover:text-foreground">
          <ChevronLeft className="size-4" />
        </Link>
        <div className="min-w-0">
          <p className="eyebrow leading-none">Flow</p>
          <h1 className="type-small-title truncate">{name}</h1>
        </div>
        <span className="inline-flex h-6 items-center rounded-full border border-line px-2.5 font-body text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
          {s.publishedVersion ? `v${s.publishedVersion} publicada` : "sin publicar"}
        </span>
        <span className={`inline-flex h-6 items-center rounded-full px-2.5 font-body text-2xs font-semibold ${s.changes ? "bg-warning-soft text-warning" : "text-muted-foreground"}`}>
          {s.changes ? `Borrador · ${s.changes} ${s.changes === 1 ? "cambio sin guardar" : "cambios sin guardar"}` : "Sin cambios"}
        </span>

        <PillGroup role="group" aria-label="Vista" className="ml-auto">
          {(["canvas", "steps"] as const).map((v) => (
            <PillNavItem key={v} active={s.view === v} onClick={() => actions.setView(v)}>
              {v === "canvas" ? "Canvas" : "Pasos"}
            </PillNavItem>
          ))}
        </PillGroup>

        <div className="flex flex-wrap items-center gap-1.5">
          <Button variant="ghost" size="sm" onClick={validate} disabled={!!s.busy}>
            {s.busy === "validating" ? "Validando…" : errors ? `Validar (${errors})` : "Validar"}
          </Button>
          <Button variant="secondary" size="sm" onClick={save} disabled={!canWrite || !!s.busy || !s.changes} title={writeHint}>
            {s.busy === "saving" ? "Guardando…" : "Guardar"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            aria-pressed={panel === "test"}
            onClick={() => setPanel(panel === "test" ? "inspect" : "test")}
            title="Corre la versión publicada en modo prueba y la sigue en vivo"
            className={panel === "test" ? "bg-line-strong text-foreground" : ""}
          >
            <Play aria-hidden /> Probar
          </Button>
          <Button variant="primary" size="sm" onClick={publish} disabled={!canWrite || !!s.busy} title={writeHint}>
            {s.busy === "publishing" ? "Publicando…" : `Publicar v${(s.publishedVersion ?? 0) + 1}`}
          </Button>
        </div>
      </div>
      {(s.notice || writeHint) && (
        <div
          role="status"
          className={`flex items-center justify-between gap-3 border-b border-line px-4 py-2 font-body text-xs ${
            s.notice?.kind === "error" ? "bg-danger-soft text-danger" : s.notice?.kind === "ok" ? "bg-success-soft text-success" : "bg-card text-muted-foreground"
          }`}
        >
          <span>{s.notice?.message ?? writeHint}</span>
          {s.notice && (
            <button type="button" onClick={() => actions.setNotice(null)} aria-label="Cerrar aviso" className="text-base">
              ×
            </button>
          )}
        </div>
      )}

      <div className="relative flex min-h-0 flex-1">
        {s.view === "canvas" && <Palette readOnly={false} onAdd={onPaletteAdd} />}
        <div
          ref={canvasRef}
          role="application"
          aria-label="Canvas del flow"
          tabIndex={-1}
          className="relative min-h-[520px] min-w-0 flex-1 outline-none md:min-h-0"
          onKeyDown={s.view === "canvas" ? onKeyDown : undefined}
          onDragOver={(e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            const over = blockUnder(e.target);
            if (over !== dropBlock) setDropBlock(over);
          }}
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropBlock(null);
          }}
          onDrop={onDrop}
        >
          {s.view === "canvas" ? (
            <ReactFlow<BlockRFNode>
              nodes={rfNodes}
              edges={rfEdges}
              nodeTypes={blockNodeTypes}
              colorMode={colorMode}
              onNodesChange={onNodesChange}
              onEdgesChange={actions.onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(e, node) => {
                const step = (e.target as Element).closest("[data-step-id]")?.getAttribute("data-step-id");
                actions.select(step ?? node.id);
              }}
              onPaneClick={() => actions.select(null)}
              onInit={openAtStart}
              minZoom={0.2}
              deleteKeyCode={null}
              proOptions={{ hideAttribution: true }}
            >
              <Background variant={BackgroundVariant.Dots} gap={20} size={1.4} />
              <Controls position="bottom-left" showInteractive={false} />
              <MiniMap position="bottom-right" pannable zoomable nodeBorderRadius={12} style={{ width: 180, height: 120 }} className="max-md:!hidden" />
            </ReactFlow>
          ) : (
            <StepsView steps={steps} nodes={nodeMap} selectedId={s.selectedId} onSelect={actions.select} issueOf={issueOf} statusOf={statusOf} />
          )}
          {s.view === "canvas" && (
            <PillGroup className="absolute left-3 top-3 z-[5] bg-card">
              <PillNavItem onClick={() => fitView({ duration: 300, padding: 0.15 })} title="Encuadrar todo el flow">
                <Maximize aria-hidden /> Encuadrar
              </PillNavItem>
              <PillNavItem onClick={tidy} title="Ordenar los bloques de izquierda a derecha">
                <LayoutGrid aria-hidden /> Ordenar
              </PillNavItem>
            </PillGroup>
          )}
          {s.showProblems && <ProblemsPanel problems={s.problems} onFocus={actions.select} onClose={() => actions.setShowProblems(false)} publishedVersion={s.publishedVersion} />}
        </div>
        <aside
          aria-label={panel === "test" ? "Prueba" : "Detalle"}
          // On phones the canvas has no side panel, but the test run still opens over it.
          className={`${panel === "test" ? "absolute inset-0 z-20" : "hidden"} w-full shrink-0 overflow-y-auto border-l border-line bg-card md:static md:block md:w-[360px]`}
        >
          {panel === "test" ? (
            <TestPanel
              run={test}
              flowKey={s.flowKey}
              nodes={nodeMap}
              canRun={!testBlocked}
              disabledReason={testBlocked}
              onFocus={actions.select}
              onClose={() => setPanel("inspect")}
            />
          ) : selected ? (
            <NodePanel
              node={selected.data.node}
              ports={selected.data.ports}
              isEntry={selected.data.isEntry}
              readOnly={false}
              problems={s.problems.filter((p) => p.node_id === selected.id)}
              onChange={(patch) => actions.updateNode(selected.id, patch)}
              onDelete={() => removeStep(selected.id)}
              onDetach={selectedBlock && selectedBlock !== selected.id ? () => detach(selected.id) : undefined}
              onClose={() => actions.select(null)}
            />
          ) : (
            <FlowPanel flow={s.base as FlowGraph} flowKey={s.flowKey} publishedVersion={s.publishedVersion} executions={executions} />
          )}
        </aside>
      </div>
    </div>
  );
}
