"use client";

import "@xyflow/react/dist/style.css";
import "./flows.css";

import { Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, type Edge, type ReactFlowInstance } from "@xyflow/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { cancelExecution, decideApproval } from "../actions";
import { humanDuration, nodeCatalog, nodeTitle } from "../lib/catalog";
import { formatDateTime, formatMs, msBetween, OPS_TIME_ZONE } from "../lib/format";
import { stepsOf } from "../lib/steps";
import { BLOCK_WIDTH, blockEdges, blockHeight, blocksOf, lastStep, layoutBlocks, openingViewport } from "../lib/blocks";
import { portsOf } from "../lib/catalog";
import { edgeFor } from "../lib/to-react-flow";
import type { ExecutionDetail, ExecutionStatus, FlowGraph, NodeRun, NodeVisualStatus } from "../lib/types";
import { useColorMode } from "../lib/use-color-mode";
import { blockNodeTypes, statusStyle, type BlockRFNode } from "./flow-node";
import { JsonView, Section } from "./json-view";
import { ExecStatus, StepStatus } from "./status";
import { StepsView } from "./steps-view";
import { flowDisplayName } from "../lib/display-names";
import { usd } from "@/features/ops-shell/format";

export type PendingApproval = {
  id: string;
  title: string;
  node_id: string | null;
  expires_at: string | null;
  payload_hash: string;
  proposed_action: { action: string; params: Record<string, unknown> };
};

type Props = {
  flow: FlowGraph;
  flowKey: string;
  initial: ExecutionDetail;
  approval: PendingApproval | null;
  canWrite: boolean;
  streamUrl: string;
};

export function ExecutionViewerContainer(props: Props) {
  return (
    <ReactFlowProvider>
      <Viewer {...props} />
    </ReactFlowProvider>
  );
}

const TERMINAL: ExecutionStatus[] = ["succeeded", "failed", "cancelled"];

// Live node runs over SSE (proxied by the app so the browser never holds an API key).
function useExecutionStream(initial: ExecutionDetail, url: string) {
  const [execution, setExecution] = useState(initial);
  const [live, setLive] = useState(false);
  useEffect(() => {
    if (TERMINAL.includes(initial.status)) return;
    const source = new EventSource(url);
    source.onopen = () => setLive(true);
    source.addEventListener("snapshot", (e) => setExecution(JSON.parse((e as MessageEvent).data) as ExecutionDetail));
    source.addEventListener("node_run", (e) => {
      const run = JSON.parse((e as MessageEvent).data) as NodeRun;
      setExecution((x) => {
        const runs = x.node_runs.some((r) => r.id === run.id) ? x.node_runs.map((r) => (r.id === run.id ? run : r)) : [...x.node_runs, run];
        const waiting = runs.some((r) => r.status === "waiting");
        return { ...x, node_runs: runs, status: x.status === "running" && waiting ? "waiting" : x.status };
      });
    });
    source.addEventListener("end", (e) => {
      const end = JSON.parse((e as MessageEvent).data) as { status: ExecutionStatus; error: Record<string, unknown> | null };
      setExecution((x) => ({ ...x, status: end.status, error: end.error }));
      setLive(false);
      source.close();
    });
    source.onerror = () => setLive(false);
    return () => source.close();
  }, [initial.status, url]);
  return { execution, live };
}

function Viewer({ flow, flowKey, initial, approval, canWrite, streamUrl }: Props) {
  const router = useRouter();
  const { execution, live } = useExecutionStream(initial, streamUrl);
  const [view, setView] = useState<"canvas" | "steps">("canvas");
  const [toast, setToast] = useState<{ kind: "ok" | "error"; message: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const runs = useMemo(() => [...execution.node_runs].sort((a, b) => Date.parse(a.started_at) - Date.parse(b.started_at)), [execution.node_runs]);
  const lastRun = useMemo(() => {
    const m = new Map<string, NodeRun>();
    for (const r of runs) m.set(r.node_id, r);
    return m;
  }, [runs]);
  const statusOf = (id: string): NodeVisualStatus | undefined => lastRun.get(id)?.status as NodeVisualStatus | undefined;

  // Same Voiceflow-style blocks as the editor, laid out left to right and read-only. An edge is
  // "traversed" when its source ran and its target ran after it.
  const colorMode = useColorMode();
  const { blocks, blockOf, positions } = useMemo(() => {
    const { blocks, blockOf } = blocksOf(flow.nodes, flow.edges, flow.entry);
    return { blocks, blockOf, positions: layoutBlocks(flow.nodes, flow.edges, flow.entry) };
  }, [flow]);
  const edges = useMemo(() => {
    const ranAfter = (from: string, to: string) => {
      const a = lastRun.get(from);
      const b = lastRun.get(to);
      return !!a && !!b && Date.parse(b.started_at) >= Date.parse(a.started_at);
    };
    const raw: Edge[] = flow.edges.map((e) => ({
      ...edgeFor(e.from, e.to, e.port),
      label: undefined,
      className: ranAfter(e.from, e.to) ? "edge-active" : "edge-dim",
    }));
    return blockEdges(raw, blockOf);
  }, [flow, lastRun, blockOf]);
  const waitingRun = runs.find((r) => r.status === "waiting");
  const failedRun = [...runs].reverse().find((r) => r.status === "failed");
  const [selectedId, setSelectedId] = useState<string>(waitingRun?.node_id ?? failedRun?.node_id ?? runs.at(-1)?.node_id ?? flow.entry);
  const selectedRun = lastRun.get(selectedId);
  const selectedNode = flow.nodes.find((n) => n.id === selectedId);
  const nodeMap = useMemo(() => new Map(flow.nodes.map((n) => [n.id, n])), [flow]);
  const nodes = useMemo<BlockRFNode[]>(
    () =>
      blocks.map((b) => {
        const last = nodeMap.get(lastStep(b))!;
        return {
          id: b.id,
          type: "block",
          position: positions[b.id] ?? { x: 0, y: 0 },
          draggable: false,
          connectable: false,
          selected: b.nodeIds.includes(selectedId),
          data: {
            steps: b.nodeIds.map((id) => ({
              node: nodeMap.get(id)!,
              isEntry: id === flow.entry,
              status: lastRun.get(id)?.status as NodeVisualStatus | undefined,
            })),
            outputs: portsOf(last),
            selectedStepId: selectedId,
          },
        };
      }),
    [blocks, positions, nodeMap, selectedId, lastRun, flow.entry],
  );

  // Open on the step that matters (waiting, failed or last) at a readable zoom, or the whole flow
  // when it fits.
  const openOnSelected = (rf: ReactFlowInstance<BlockRFNode>) => {
    const el = document.querySelector<HTMLElement>("[data-tour='execution-graph']");
    if (!el) return void rf.fitView({ padding: 0.15 });
    const boxes = nodes.map((n) => ({
      x: n.position.x,
      y: n.position.y,
      w: BLOCK_WIDTH,
      h: blockHeight(n.data.steps.length, n.data.outputs),
    }));
    const focus = boxes[nodes.findIndex((n) => n.selected)];
    rf.setViewport(openingViewport(boxes, el.getBoundingClientRect(), { focus, center: true }));
  };
  const steps = useMemo(() => (view === "steps" ? stepsOf(flow) : []), [view, flow]);
  const readOnlyHint = "La demo pública es de solo lectura: aprobar o cancelar requiere una cuenta de ops.";

  const decide = async (decision: "approved" | "rejected") => {
    if (!approval) return;
    setBusy(true);
    const res = await decideApproval(approval.id, approval.payload_hash, decision);
    setBusy(false);
    setToast(res.ok ? { kind: "ok", message: decision === "approved" ? "Aprobado: la ejecución sigue por “aprobado”." : "Rechazado: la ejecución sigue por “rechazado”." } : { kind: "error", message: res.message });
    if (res.ok) router.refresh();
  };
  const cancel = async () => {
    setBusy(true);
    const res = await cancelExecution(execution.id);
    setBusy(false);
    setToast(res.ok ? { kind: "ok", message: "Cancelación pedida." } : { kind: "error", message: res.message });
    if (res.ok) router.refresh();
  };

  return (
    <div className="igs-flow flex min-h-[calc(100dvh-4rem)] flex-col bg-background">
      <header className="border-b border-line px-4 pb-5 pt-6 sm:px-8">
        <Link href={`/ops/flows/${flowKey}`} className="eyebrow text-muted-foreground hover:text-foreground">
          ← Volver al flow
        </Link>
        <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-3">
          <h1 className="type-hero">
            <span className="headline-muted">Ejecución · </span>
            {flowDisplayName(flowKey, flow.name)}
          </h1>
          <div className="flex flex-wrap items-center gap-2 pb-0.5">
            <ExecStatus status={execution.status} />
            <span className="inline-flex h-6 items-center rounded-full bg-white/10 px-2.5 font-mono text-xs" title={execution.id}>
              #{execution.id.slice(0, 8)}
            </span>
            <span className="inline-flex h-6 items-center rounded-full bg-white/10 px-2.5 text-xs font-semibold">fija en v{execution.version}</span>
            {live && (
              <span className="inline-flex h-6 items-center gap-1.5 rounded-full border border-info/40 px-2.5 text-xs font-semibold text-info">
                <span aria-hidden className="size-1.5 rounded-full bg-info motion-safe:animate-pulse" /> en vivo
              </span>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <div role="group" aria-label="Vista" className="flex rounded-full border border-line bg-white/5 p-1">
              {(["canvas", "steps"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className={`${pill} h-7 px-3.5 ${view === v ? "bg-foreground text-background" : "text-foreground/70 hover:text-foreground"}`}
                >
                  {v === "canvas" ? "Canvas" : "Pasos"}
                </button>
              ))}
            </div>
            {!TERMINAL.includes(execution.status) && (
              <button type="button" onClick={cancel} disabled={!canWrite || busy} title={canWrite ? undefined : readOnlyHint} className={`${pill} bg-white/10 text-danger hover:bg-white/15`}>
                Cancelar
              </button>
            )}
          </div>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          {execution.trigger_kind} · arrancó {formatDateTime(execution.started_at)} (hora de Buenos Aires)
        </p>
      </header>

      {approval && <ApprovalBanner approval={approval} flow={flow} canWrite={canWrite} busy={busy} onDecide={decide} hint={readOnlyHint} />}
      {toast && (
        <div role="status" className="px-4 pt-4 sm:px-8">
          <p className={`inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm ${toast.kind === "error" ? "border-danger/40 text-danger" : "border-success/40 text-success"}`}>
            <span aria-hidden className={`size-1.5 rounded-full ${toast.kind === "error" ? "bg-danger" : "bg-success"}`} />
            {toast.message}
          </p>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
        <div className="relative min-h-[380px] min-w-0 flex-1" data-tour="execution-graph">
          {view === "canvas" ? (
            <>
              <ReactFlow<BlockRFNode>
                nodes={nodes}
                edges={edges}
                nodeTypes={blockNodeTypes}
                colorMode={colorMode}
                onInit={openOnSelected}
                onNodeClick={(e, n) => {
                  const step = (e.target as Element).closest("[data-step-id]")?.getAttribute("data-step-id");
                  setSelectedId(step ?? n.id);
                }}
                nodesDraggable={false}
                nodesConnectable={false}
                // Read-only graph: edges aren't actionable, so they shouldn't be tab stops (QA D-08).
                edgesFocusable={false}
                minZoom={0.2}
                proOptions={{ hideAttribution: true }}
              >
                <Background variant={BackgroundVariant.Dots} gap={18} size={1.2} />
                <Controls showInteractive={false} />
              </ReactFlow>
              <Legend />
            </>
          ) : (
            <StepsView steps={steps} nodes={nodeMap} selectedId={selectedId} onSelect={setSelectedId} statusOf={statusOf} />
          )}
        </div>
        <aside aria-label="Detalle del nodo" className="hidden w-[380px] shrink-0 overflow-y-auto border-l border-line bg-card md:block">
          <div className="border-b border-line px-5 py-5">
            <p className="eyebrow text-muted-foreground">{selectedNode ? nodeCatalog[selectedNode.type].label : "Nodo"}</p>
            <p className="type-small-title mt-2 first-letter:uppercase">{selectedNode ? nodeTitle(selectedNode) : selectedId}</p>
            {selectedRun ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <StepStatus status={visual(selectedRun.status)} />
                <span className="inline-flex h-6 items-center rounded-full border border-line px-2.5">intento {selectedRun.attempt}</span>
                <span className="tabular-nums">
                  {selectedRun.status === "waiting" ? `esperando hace ${formatMs(msBetween(selectedRun.started_at, null))}` : formatMs(selectedRun.duration_ms)}
                </span>
              </div>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">No llegó a correr en esta ejecución.</p>
            )}
          </div>
          {selectedRun && (
            <>
              {selectedRun.error && (
                <Section title="Error">
                  <JsonView value={selectedRun.error} />
                </Section>
              )}
              <Section title="Entrada">
                <JsonView value={selectedRun.input} className="max-h-[260px]" />
              </Section>
              <Section title="Salida">
                <JsonView value={selectedRun.output} className="max-h-[260px]" />
              </Section>
            </>
          )}
          <Section title="Disparo" defaultOpen={false}>
            <JsonView value={execution.trigger_payload} />
          </Section>
          <Section title="Variables" defaultOpen={false}>
            <JsonView value={execution.vars} />
          </Section>
        </aside>
      </div>

      <Timeline runs={runs} selectedId={selectedId} onSelect={setSelectedId} flow={flow} />
    </div>
  );
}

const pill =
  "inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-full px-5 text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50";

const visual = (s: string): NodeVisualStatus => (s in statusStyle ? (s as NodeVisualStatus) : "pending");

// What the person is approving, in words, before any JSON (v2-flows P2). Spotlight card: the one
// thing on this screen a person has to act on.
function ApprovalBanner({
  approval,
  flow,
  canWrite,
  busy,
  onDecide,
  hint,
}: {
  approval: PendingApproval;
  flow: FlowGraph;
  canWrite: boolean;
  busy: boolean;
  onDecide: (d: "approved" | "rejected") => void;
  hint: string;
}) {
  const node = flow.nodes.find((n) => n.id === approval.node_id);
  const p = approval.proposed_action.params;
  const preview = [
    ["Acción", approval.proposed_action.action],
    ["Para", p.to ?? p.recipient ?? p.email],
    ["Asunto", p.subject],
    ["Precio", p.pricePerPersonUsd ? `${usd(Number(p.pricePerPersonUsd))} por persona` : undefined],
  ].filter(([, v]) => v != null && v !== "") as Array<[string, unknown]>;
  return (
    <div className="px-4 pt-5 sm:px-8">
      <section aria-label="Aprobación pendiente" className="stadium-art relative isolate overflow-hidden rounded-lg border border-line">
        <div aria-hidden className="absolute inset-0 -z-10 bg-gradient-to-r from-background/95 via-background/80 to-background/40" />
        <div className="flex flex-wrap items-end gap-6 p-6 sm:p-8">
          <div className="min-w-0 flex-1">
            <p className="eyebrow inline-flex items-center gap-2 text-warning">
              <span aria-hidden className="size-1.5 rounded-full bg-warning motion-safe:animate-pulse" />
              Esperando a una persona
            </p>
            <p className="type-card mt-3 max-w-3xl">{approval.title}</p>
            <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
              La ejecución está pausada en “{node ? nodeTitle(node) : approval.node_id}”.
              {approval.expires_at
                ? ` Vence ${formatDateTime(approval.expires_at)} (hora de Buenos Aires); si nadie decide, sigue por “vencido”.`
                : " No vence."}
            </p>
            {preview.length > 0 && (
              <dl className="mt-5 grid max-w-3xl grid-cols-[auto_1fr] gap-x-5 gap-y-1.5 border-t border-line pt-4 text-sm">
                {preview.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="eyebrow text-muted-foreground">{k}</dt>
                    <dd className="min-w-0 truncate text-foreground">{String(v)}</dd>
                  </div>
                ))}
              </dl>
            )}
            <p className="mt-3 font-mono text-xs text-muted-foreground" title="Huella del contenido exacto: si cambia, hay que aprobar de nuevo">
              huella {approval.payload_hash.replace(/^sha256:/, "").slice(0, 12)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/ops/approvals?id=${approval.id}`} className={`${pill} text-foreground/70 hover:text-foreground`}>
              Ver completo <span aria-hidden>→</span>
            </Link>
            <button type="button" onClick={() => onDecide("rejected")} disabled={!canWrite || busy} title={canWrite ? undefined : hint} className={`${pill} bg-white/10 text-foreground/80 hover:bg-white/15 hover:text-foreground`}>
              Rechazar
            </button>
            <button type="button" onClick={() => onDecide("approved")} disabled={!canWrite || busy} title={canWrite ? undefined : hint} className={`${pill} bg-foreground text-background hover:bg-foreground/85`}>
              Aprobar <span aria-hidden>→</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

function Timeline({ runs, selectedId, onSelect, flow }: { runs: NodeRun[]; selectedId: string; onSelect: (id: string) => void; flow: FlowGraph }) {
  // Log scale so a 3-week wait and a 2 ms node are both visible; waits are hatched, not filled.
  const durations = runs.map((r) => r.duration_ms ?? msBetween(r.started_at, r.finished_at));
  const max = Math.max(...durations, 1);
  const width = (ms: number) => Math.max(2, (Math.log10(ms + 1) / Math.log10(max + 1)) * 100);
  return (
    <section aria-label="Línea de tiempo" className="shrink-0 border-t border-line bg-card px-4 py-5 sm:px-8">
      <div className="mb-3 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <p className="eyebrow text-foreground">Línea de tiempo</p>
        <p className="text-xs text-muted-foreground">
          <span className="kpi-number text-2xl text-foreground">{runs.length}</span> {runs.length === 1 ? "nodo" : "nodos"} · escala logarítmica · horas en{" "}
          {OPS_TIME_ZONE.split("/").at(-1)?.replace("_", " ")}
        </p>
      </div>
      {runs.length === 0 && <p className="text-xs text-muted-foreground">Todavía no corrió ningún nodo.</p>}
      <ol className="space-y-0.5">
        {runs.map((r, i) => {
          const node = flow.nodes.find((n) => n.id === r.node_id);
          const waiting = r.status === "waiting";
          const ms = durations[i];
          const label = waiting
            ? node?.type === "wait" && typeof node.config?.duration === "string"
              ? `espera ${humanDuration(node.config.duration)}`
              : "esperando"
            : formatMs(ms);
          return (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => onSelect(r.node_id)}
                aria-current={selectedId === r.node_id ? "true" : undefined}
                className={`grid w-full grid-cols-[2rem_minmax(0,160px)_1fr_auto] items-center gap-3 rounded-full px-3 py-1 text-left text-xs transition-colors hover:bg-white/5 sm:grid-cols-[2rem_200px_1fr_120px] ${
                  selectedId === r.node_id ? "bg-white/10" : ""
                }`}
              >
                <span className="font-display text-base font-black leading-none tabular-nums text-muted-headline">{String(i + 1).padStart(2, "0")}</span>
                <span className="truncate">{node ? nodeTitle(node) : r.node_id}</span>
                <span className="h-2 rounded-full bg-white/5">
                  <span
                    className={`block h-full rounded-full ${waiting ? "igs-wait-stripes" : statusStyle[visual(r.status)].dot}`}
                    style={{ width: `${waiting ? 100 : width(ms)}%` }}
                  />
                </span>
                <span className="text-right font-display text-sm font-extrabold tabular-nums tracking-tight text-muted-foreground">{label}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Legend() {
  return (
    <div className="absolute left-3 top-3 z-10 flex flex-wrap gap-1.5">
      {(["succeeded", "failed", "waiting", "pending"] as const).map((s) => (
        <StepStatus key={s} status={s} />
      ))}
    </div>
  );
}
