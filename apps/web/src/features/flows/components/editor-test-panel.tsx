"use client";

import { ExternalLink, Play, RotateCcw, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui";
import { startTestRun } from "../actions";
import { nodeCatalog, nodeTitle } from "../lib/catalog";
import type { ExecutionDetail, ExecutionStatus, FlowNode, FlowNodeType, NodeRun, NodeVisualStatus } from "../lib/types";
import { statusStyle } from "./flow-node";
import { ExecStatus } from "./status";
import { StepIcon } from "./step-icon";

const TERMINAL: ExecutionStatus[] = ["succeeded", "failed", "cancelled"];

/** A test run of the published version, followed live over the app's SSE proxy. */
export function useTestRun(flowId: string, flowKey: string) {
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [execution, setExecution] = useState<ExecutionDetail | null>(null);
  const [live, setLive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!executionId) return;
    const source = new EventSource(`/ops/flows/${encodeURIComponent(flowKey)}/executions/${encodeURIComponent(executionId)}/stream`);
    source.onopen = () => setLive(true);
    source.addEventListener("snapshot", (e) => setExecution(JSON.parse((e as MessageEvent).data) as ExecutionDetail));
    source.addEventListener("node_run", (e) => {
      const run = JSON.parse((e as MessageEvent).data) as NodeRun;
      setExecution((x) => {
        if (!x) return x;
        const runs = x.node_runs.some((r) => r.id === run.id) ? x.node_runs.map((r) => (r.id === run.id ? run : r)) : [...x.node_runs, run];
        const waiting = runs.some((r) => r.status === "waiting");
        return { ...x, node_runs: runs, status: x.status === "running" && waiting ? "waiting" : x.status };
      });
    });
    source.addEventListener("end", (e) => {
      const end = JSON.parse((e as MessageEvent).data) as { status: ExecutionStatus; error: Record<string, unknown> | null };
      setExecution((x) => (x ? { ...x, status: end.status, error: end.error } : x));
      setLive(false);
      source.close();
    });
    source.onerror = () => setLive(false);
    return () => source.close();
  }, [executionId, flowKey]);

  const start = async () => {
    setStarting(true);
    setError(null);
    setExecution(null);
    const res = await startTestRun(flowId, { type: "manual", test: true });
    setStarting(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setExecutionId(res.executionId);
  };

  // Latest run per node, for the step dots on the canvas.
  const statuses = useMemo(() => {
    const map = new Map<string, NodeVisualStatus>();
    for (const r of execution?.node_runs ?? []) map.set(r.node_id, (r.status in statusStyle ? r.status : "running") as NodeVisualStatus);
    return map;
  }, [execution]);

  return { executionId, execution, live, starting, error, start, statuses };
}

type TestRun = ReturnType<typeof useTestRun>;

export function TestPanel({
  run,
  flowKey,
  nodes,
  canRun,
  disabledReason,
  onFocus,
  onClose,
}: {
  run: TestRun;
  flowKey: string;
  nodes: Map<string, FlowNode>;
  canRun: boolean;
  disabledReason?: string;
  onFocus: (nodeId: string) => void;
  onClose: () => void;
}) {
  const { execution, executionId, live, starting, error, start } = run;
  const runs = useMemo(() => [...(execution?.node_runs ?? [])].sort((a, b) => a.started_at.localeCompare(b.started_at)), [execution]);
  const waitingForUser = runs.some((r) => r.status === "waiting" && (r.node_type === "capture" || r.node_type === "choice" || r.node_type === "agent"));
  const done = execution ? TERMINAL.includes(execution.status) : false;

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start gap-2 border-b border-line px-4 pb-3 pt-3.5">
        <div className="min-w-0 flex-1">
          <p className="eyebrow">Probar</p>
          <p className="mt-1 font-sans text-xl tracking-tight">Ejecución de prueba</p>
          <div className="mt-1.5 flex items-center gap-2 font-body text-xs text-muted-foreground">
            {execution ? <ExecStatus status={execution.status} /> : <span>{executionId ? "Conectando…" : "Corre la versión publicada, marcada como prueba."}</span>}
            {live && (
              <span className="inline-flex items-center gap-1">
                <span aria-hidden className="size-1.5 rounded-full bg-success motion-safe:animate-pulse" /> en vivo
              </span>
            )}
          </div>
        </div>
        <button type="button" onClick={onClose} aria-label="Cerrar prueba" className="grid size-8 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Button variant="primary" size="sm" className="rounded-full" onClick={start} disabled={!canRun || starting || (!!executionId && !done && !error)} title={disabledReason}>
          {executionId ? <RotateCcw aria-hidden /> : <Play aria-hidden />}
          {starting ? "Arrancando…" : executionId ? "Reiniciar" : "Iniciar prueba"}
        </Button>
        {executionId && (
          <Link href={`/ops/flows/${flowKey}/executions/${executionId}`} className="inline-flex h-8 items-center gap-1.5 rounded-full bg-muted px-3 font-body text-xs font-semibold text-muted-foreground hover:text-foreground">
            Ver ejecución <ExternalLink aria-hidden className="size-3.5" />
          </Link>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto bg-background px-3 py-4" aria-live="polite">
        {!canRun && disabledReason && <p className="rounded-lg border border-line bg-card px-3 py-2.5 font-body text-xs leading-relaxed text-muted-foreground">{disabledReason}</p>}
        {error && <p className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2.5 font-body text-xs text-danger">{error}</p>}
        {!executionId && canRun && !error && (
          <p className="px-1 font-body text-xs leading-relaxed text-muted-foreground">
            Lo que el bot diga aparece como conversación; el resto de los pasos, como eventos. Clic en uno lo marca en el canvas.
          </p>
        )}
        {runs.map((r) => (
          <RunEntry key={r.id} run={r} node={nodes.get(r.node_id)} onFocus={() => onFocus(r.node_id)} />
        ))}
        {waitingForUser && (
          <p className="rounded-lg border border-dashed border-line px-3 py-2.5 font-body text-xs leading-relaxed text-muted-foreground">
            El flow espera la respuesta del usuario. En una prueba manual nadie contesta: la espera vence según el paso, o probalo desde el chat del coach.
          </p>
        )}
        {execution?.error && done && (
          <p className="rounded-lg border border-danger-border bg-danger-soft px-3 py-2.5 font-body text-xs text-danger">
            {String((execution.error as { message?: unknown }).message ?? JSON.stringify(execution.error))}
          </p>
        )}
      </div>
    </div>
  );
}

const CONVERSATIONAL = new Set<FlowNodeType>(["say", "capture", "choice", "agent"]);

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v : undefined;
}

/** What the bot said in this run, if anything. */
function botText(run: NodeRun, node?: FlowNode): string | undefined {
  const out = (run.output ?? {}) as Record<string, unknown>;
  const inp = (run.input ?? {}) as Record<string, unknown>;
  switch (run.node_type) {
    case "say":
      return str(out.text) ?? str(node?.config?.text);
    case "capture":
      return str(inp.prompt) ?? str(node?.config?.prompt);
    case "choice":
      return str(inp.prompt) ?? str(inp.text) ?? str(node?.config?.prompt);
    case "agent":
      return str(out.text) ?? str(out.reply) ?? str(out.say);
    default:
      return undefined;
  }
}

export function duration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1).replace(".", ",")} s`;
  return ms < 3_600_000 ? `${Math.round(ms / 60_000)} min` : `${(ms / 3_600_000).toFixed(1).replace(".", ",")} h`;
}

function userText(run: NodeRun): string | undefined {
  const out = (run.output ?? {}) as Record<string, unknown>;
  return str(out.userText) ?? str(out.reply) ?? str((out.selected as { label?: unknown } | undefined)?.label);
}

function RunEntry({ run, node, onFocus }: { run: NodeRun; node?: FlowNode; onFocus: () => void }) {
  const type = (run.node_type in nodeCatalog ? run.node_type : "action") as FlowNodeType;
  const title = node ? nodeTitle(node) : run.node_id;
  const status = statusStyle[run.status as NodeVisualStatus];
  const said = CONVERSATIONAL.has(type) ? botText(run, node) : undefined;
  const reply = CONVERSATIONAL.has(type) && run.node_type !== "say" ? userText(run) : undefined;
  const failure = run.error ? String((run.error as { message?: unknown }).message ?? run.error.type ?? "Falló") : undefined;

  return (
    <div className="space-y-1.5">
      {said && (
        <button type="button" onClick={onFocus} className="block max-w-[88%] rounded-2xl rounded-bl-md border border-line bg-card px-3.5 py-2.5 text-left font-body text-sm leading-relaxed text-foreground hover:border-line-strong">
          {said}
        </button>
      )}
      {reply && <p className="ml-auto max-w-[80%] rounded-2xl rounded-br-md bg-primary px-3.5 py-2 font-body text-sm text-primary-foreground">{reply}</p>}
      <button
        type="button"
        onClick={onFocus}
        className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left font-body text-xs transition-colors hover:bg-card ${type === "approval" && run.status === "waiting" ? "border border-l-2 border-warning-border border-l-warning bg-warning-soft" : ""}`}
      >
        <StepIcon type={type} className="size-6" />
        <span className="min-w-0 flex-1 truncate">
          <span className="text-muted-foreground">{nodeCatalog[type].label} · </span>
          <span className="text-foreground first-letter:uppercase">{title}</span>
        </span>
        {run.duration_ms != null && <span className="tabular-nums text-muted-foreground">{duration(run.duration_ms)}</span>}
        <span title={status?.label ?? run.status} className={`size-2 shrink-0 rounded-full ${status?.dot ?? "bg-border"}`} />
      </button>
      {type === "approval" && run.status === "waiting" && (
        <Link href="/ops/approvals" className="ml-10 inline-flex font-body text-xs font-semibold text-warning underline-offset-2 hover:underline">
          Decidir en Aprobaciones →
        </Link>
      )}
      {failure && <p className="ml-10 font-body text-xs text-danger">{failure}</p>}
    </div>
  );
}
