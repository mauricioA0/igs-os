"use client";

import { Handle, Position, useStore, type Node, type NodeProps } from "@xyflow/react";
import { memo } from "react";
import { BLOCK_WIDTH } from "../lib/blocks";
import { categories, nodeCatalog, nodeSummary, nodeTitle, portLabel } from "../lib/catalog";
import { NODE_WIDTH } from "../lib/layout";
import type { FlowNode, NodeVisualStatus } from "../lib/types";
import { StepIcon } from "./step-icon";

export type FlowNodeData = {
  node: FlowNode;
  ports: string[];
  isEntry: boolean;
  status?: NodeVisualStatus;
  issue?: "error" | "warning";
  dimmed?: boolean;
};

export type FlowRFNode = Node<FlowNodeData, "flow">;

// Color only means state: run status on executions, validation issues on the editor.
export const statusStyle: Record<NodeVisualStatus, { dot: string; label: string }> = {
  succeeded: { dot: "bg-success", label: "Completó" },
  failed: { dot: "bg-danger", label: "Falló" },
  running: { dot: "bg-info", label: "Corriendo" },
  waiting: { dot: "bg-warning", label: "Esperando" },
  skipped: { dot: "bg-muted-foreground", label: "Salteado" },
  pending: { dot: "bg-border", label: "No llegó" },
};

const COMPACT_BELOW_ZOOM = 0.6;
const BLOCK_COMPACT_BELOW_ZOOM = 0.42;
const handleClass = "!size-3 !border-2 !border-muted-foreground !bg-background";

// One node per card (the execution viewer draws runs this way).
function FlowNodeCard({ data, selected }: NodeProps<FlowRFNode>) {
  const { node, ports, isEntry, status, issue, dimmed } = data;
  const compact = useStore((s) => s.transform[2] < COMPACT_BELOW_ZOOM);
  const spec = nodeCatalog[node.type];
  const summary = nodeSummary(node);
  const ring = issue === "error" ? "border-danger" : issue === "warning" ? "border-warning" : selected ? "border-foreground" : "border-line";
  const waiting = status === "waiting";

  return (
    <div
      style={{ width: NODE_WIDTH }}
      aria-label={`${spec.label}: ${nodeTitle(node)}${status ? ` · ${statusStyle[status].label}` : ""}${issue ? ` · ${issue === "error" ? "con errores" : "con advertencias"}` : ""}`}
      className={`relative rounded-xl border bg-card text-card-foreground transition-opacity ${ring} ${dimmed ? "opacity-40" : ""} ${waiting ? "motion-safe:animate-pulse" : ""}`}
    >
      {!isEntry && <Handle type="target" position={Position.Top} className={handleClass} />}
      {compact ? (
        // Zoomed out: a readable pill instead of 6 px text.
        <div className="flex items-center gap-3 px-4 py-5">
          <StepIcon type={node.type} className="size-10" />
          <span className="display truncate text-4xl leading-none">{nodeTitle(node)}</span>
          {status && <span className={`ml-auto size-6 shrink-0 rounded-full ${statusStyle[status].dot}`} />}
        </div>
      ) : (
        <>
          <div className="flex items-start gap-2.5 px-3 pb-2.5 pt-2.5">
            <StepIcon type={node.type} className="mt-0.5" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="eyebrow text-2xs">{spec.label}</span>
                {isEntry && <span className="rounded-full bg-primary px-1.5 text-2xs font-semibold text-primary-foreground">Inicio</span>}
              </div>
              <div className="truncate font-sans text-sm font-semibold leading-tight tracking-tight first-letter:uppercase">{nodeTitle(node)}</div>
              {summary && <div className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted-foreground">{summary}</div>}
            </div>
            {status && <span title={statusStyle[status].label} className={`mt-1 size-2.5 shrink-0 rounded-full ${statusStyle[status].dot}`} />}
          </div>
          {ports.length > 0 && (
            <div className="flex justify-around border-t border-line px-1 pb-1.5 pt-1">
              {ports.map((p) => (
                <span key={p} className={`text-2xs font-semibold ${p === "error" ? "text-danger" : "text-muted-foreground"}`}>
                  {portLabel(p)}
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {ports.map((p, i) => (
        <Handle
          key={p}
          id={p}
          type="source"
          position={Position.Bottom}
          style={{ left: `${((i + 0.5) / ports.length) * 100}%` }}
          className={`${handleClass} ${p === "error" ? "!border-danger" : ""}`}
        />
      ))}
    </div>
  );
}

export const FlowNodeView = memo(FlowNodeCard);
export const nodeTypes = { flow: FlowNodeView };

// ── Blocks (editor canvas) ─────────────────────────────────────────────────

export type BlockStep = {
  node: FlowNode;
  isEntry: boolean;
  issue?: "error" | "warning";
  status?: NodeVisualStatus;
};

export type BlockData = {
  steps: BlockStep[];
  outputs: string[]; // ports of the last step
  selectedStepId: string | null;
  dropTarget?: boolean;
};

export type BlockRFNode = Node<BlockData, "block">;

/** A Voiceflow-style block: a title, the steps stacked inside, and its outputs on the right edge. */
function BlockCard({ id, data, selected }: NodeProps<BlockRFNode>) {
  const { steps, outputs, selectedStepId, dropTarget } = data;
  const compact = useStore((s) => s.transform[2] < BLOCK_COMPACT_BELOW_ZOOM);
  const head = steps[0];
  const isEntry = head?.isEntry;
  const issue = steps.some((s) => s.issue === "error") ? "error" : steps.some((s) => s.issue === "warning") ? "warning" : undefined;
  const plainNext = outputs.length === 1 && outputs[0] === "next";
  const border =
    issue === "error" ? "border-danger" : issue === "warning" ? "border-warning" : selected ? "border-line-strong" : dropTarget ? "border-foreground" : "border-line";

  return (
    <div
      data-block-id={id}
      style={{ width: BLOCK_WIDTH }}
      aria-label={`Bloque ${head ? nodeTitle(head.node) : id}, ${steps.length} ${steps.length === 1 ? "paso" : "pasos"}`}
      className={`relative rounded-xl border bg-card text-card-foreground shadow-[0_12px_32px_-16px_rgb(0_0_0/0.8)] transition-colors ${border} ${selected ? "ring-1 ring-line-strong" : ""}`}
    >
      {!isEntry && <Handle type="target" position={Position.Left} style={{ top: 23 }} className={handleClass} />}
      <header className="flex h-[46px] items-center gap-2 border-b border-line px-3">
        {isEntry && (
          <span className="inline-flex h-5 items-center rounded-full bg-primary px-2 font-body text-2xs font-semibold text-primary-foreground">Inicio</span>
        )}
        <span className={`min-w-0 flex-1 truncate font-sans font-semibold tracking-tight first-letter:uppercase ${compact ? "text-3xl" : "text-sm"}`}>
          {head ? nodeTitle(head.node) : id}
        </span>
        {!compact && steps.length > 1 && <span className="font-body text-2xs text-muted-foreground tabular-nums">{steps.length} pasos</span>}
      </header>

      {compact ? (
        <div className="flex gap-1.5 px-3 py-3">
          {steps.map((s) => (
            <StepIcon key={s.node.id} type={s.node.type} className="size-10" />
          ))}
        </div>
      ) : (
        <ol className="space-y-1 p-1.5">
          {steps.map((s, i) => (
            <StepRow key={s.node.id} step={s} selected={s.node.id === selectedStepId} last={i === steps.length - 1} handle={plainNext && i === steps.length - 1} />
          ))}
        </ol>
      )}

      {!plainNext && outputs.length > 0 && (
        <ul className="border-t border-line py-1">
          {outputs.map((p) => (
            <li key={p} className="relative flex h-[30px] items-center justify-end gap-2 pl-3 pr-5">
              <span className={`font-body text-2xs font-semibold uppercase tracking-wide ${p === "error" ? "text-danger" : "text-muted-foreground"}`}>{portLabel(p)}</span>
              <Handle id={p} type="source" position={Position.Right} className={`${handleClass} ${p === "error" ? "!border-danger" : ""}`} />
            </li>
          ))}
        </ul>
      )}
      {plainNext && compact && <Handle id="next" type="source" position={Position.Right} className={handleClass} />}
    </div>
  );
}

function StepRow({ step, selected, last, handle }: { step: BlockStep; selected: boolean; last: boolean; handle: boolean }) {
  const { node, issue, status } = step;
  const spec = nodeCatalog[node.type];
  const summary = nodeSummary(node);
  const pause = node.type === "approval" || node.type === "wait" || node.type === "capture";
  const tone =
    issue === "error"
      ? "border-danger bg-danger-soft"
      : issue === "warning"
        ? "border-warning bg-warning-soft"
        : selected
          ? "border-foreground bg-raised"
          : "border-transparent bg-background/60 hover:border-line-strong";
  const running = status === "running" || status === "waiting";

  return (
    <li
      data-step-id={node.id}
      aria-current={selected ? "step" : undefined}
      className={`relative flex min-h-[54px] cursor-pointer items-start gap-2.5 rounded-lg border px-2.5 py-2 transition-colors ${tone} ${
        node.type === "approval" ? "border-l-2 border-l-warning" : node.type === "wait" ? "border-dashed" : ""
      } ${running ? "ring-1 ring-info motion-safe:animate-pulse" : ""}`}
    >
      <StepIcon type={node.type} />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 font-body text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
          {spec.label}
          <span aria-hidden className="text-muted-headline">·</span>
          <span className="font-normal normal-case tracking-normal">{categories[spec.category].label}</span>
          {pause && (
            <span className={`ml-auto rounded-full px-1.5 normal-case tracking-normal ${node.type === "approval" ? "bg-warning-soft text-warning" : "bg-muted text-muted-foreground"}`}>
              {node.type === "approval" ? "persona decide" : node.type === "wait" ? "espera" : "respuesta"}
            </span>
          )}
        </p>
        <p className="truncate font-sans text-sm font-semibold leading-tight tracking-tight text-foreground first-letter:uppercase">{nodeTitle(node)}</p>
        {summary && <p className="mt-0.5 truncate font-body text-xs text-muted-foreground">{summary}</p>}
      </div>
      {status && <span title={statusStyle[status].label} className={`mt-1 size-2 shrink-0 rounded-full ${statusStyle[status].dot}`} />}
      {issue && <span className="sr-only">{issue === "error" ? "con errores" : "con advertencias"}</span>}
      {handle && last && <Handle id="next" type="source" position={Position.Right} style={{ right: -7 }} className={handleClass} />}
    </li>
  );
}

export const BlockNodeView = memo(BlockCard);
export const blockNodeTypes = { block: BlockNodeView };
