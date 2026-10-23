"use client";

import { Search, X } from "lucide-react";
import Link from "next/link";
import { useState, type DragEvent, type ReactNode } from "react";
import { Button } from "@/components/ui";
import { categories, humanDuration, nodeCatalog, nodeTitle, paletteGroups, portLabel, triggerLabel } from "../lib/catalog";
import { flowDisplayDescription } from "../lib/display-names";
import { formatDateTime } from "../lib/format";
import type { ExecutionSummary, FlowGraph, FlowNode, FlowNodeType, ValidationProblem } from "../lib/types";
import { JsonView, Section } from "./json-view";
import { ExecStatus } from "./status";
import { StepIcon } from "./step-icon";

export const DND_TYPE = "application/x-igs-node";

/** Step library: categories with a search, drag onto the canvas (or onto a block to stack it there). */
export function Palette({ readOnly, onAdd }: { readOnly: boolean; onAdd: (type: FlowNodeType) => void }) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const groups = paletteGroups
    .map((g) => ({
      ...g,
      types: g.types.filter((t) => !q || `${nodeCatalog[t].label} ${nodeCatalog[t].description} ${t}`.toLowerCase().includes(q)),
    }))
    .filter((g) => g.types.length > 0);

  return (
    <aside aria-label="Pasos" className="hidden w-[248px] shrink-0 flex-col border-r border-line bg-card lg:flex">
      <div className="border-b border-line px-3 pb-3 pt-3.5">
        <p className="eyebrow">Pasos</p>
        <label className="relative mt-2 block">
          <span className="sr-only">Buscar pasos</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Buscar…"
            className="h-9 w-full rounded-full border border-line bg-background pl-8 pr-3 font-body text-xs text-foreground placeholder:text-muted-foreground focus:border-line-strong focus:outline-none"
          />
        </label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-6 pt-3">
        {groups.length === 0 && <p className="font-body text-xs text-muted-foreground">Ningún paso coincide con “{query}”.</p>}
        {groups.map((g) => (
          <section key={g.category} className="mb-4">
            <h3 className="mb-1.5 font-body text-2xs font-semibold uppercase tracking-[0.12em] text-muted-headline">{categories[g.category].label}</h3>
            <ul className="grid grid-cols-2 gap-1.5">
              {g.types.map((t) => (
                <PaletteItem key={t} type={t} disabled={readOnly} onAdd={onAdd} />
              ))}
            </ul>
          </section>
        ))}
      </div>
      <p className="border-t border-line px-3 py-2.5 font-body text-2xs leading-snug text-muted-foreground">
        {readOnly ? "Vista de solo lectura." : "Arrastrá un paso al canvas o sobre un bloque. Clic lo suma al bloque elegido."}
      </p>
    </aside>
  );
}

function PaletteItem({ type, disabled, onAdd }: { type: FlowNodeType; disabled: boolean; onAdd: (type: FlowNodeType) => void }) {
  const spec = nodeCatalog[type];
  const onDragStart = (e: DragEvent) => {
    e.dataTransfer.setData(DND_TYPE, type);
    e.dataTransfer.effectAllowed = "move";
  };
  return (
    <li>
      <button
        type="button"
        draggable={!disabled}
        onDragStart={onDragStart}
        onClick={() => onAdd(type)}
        disabled={disabled}
        title={spec.description}
        className="flex w-full flex-col items-start gap-1.5 rounded-lg border border-line bg-background px-2 py-2 text-left transition-colors hover:border-line-strong hover:bg-raised disabled:opacity-60 enabled:cursor-grab enabled:active:cursor-grabbing"
      >
        <StepIcon type={type} className="size-6" />
        <span className="font-body text-xs font-semibold text-foreground">{spec.label}</span>
      </button>
    </li>
  );
}

function PanelHeader({ eyebrow, children, onClose }: { eyebrow: string; children: ReactNode; onClose?: () => void }) {
  return (
    <div className="flex items-start gap-2 border-b border-line px-4 pb-3 pt-3.5">
      <div className="min-w-0 flex-1">
        <p className="eyebrow">{eyebrow}</p>
        {children}
      </div>
      {onClose && (
        <button type="button" onClick={onClose} aria-label="Cerrar panel" className="grid size-8 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      )}
    </div>
  );
}

export function NodePanel({
  node,
  ports,
  isEntry,
  readOnly,
  problems,
  onChange,
  onDelete,
  onDetach,
  onClose,
}: {
  node: FlowNode;
  ports: string[];
  isEntry: boolean;
  readOnly: boolean;
  problems: ValidationProblem[];
  onChange: (patch: Partial<FlowNode>) => void;
  onDelete: () => void;
  /** Set when the step sits under another one in its block: moves it to a block of its own. */
  onDetach?: () => void;
  onClose: () => void;
}) {
  const spec = nodeCatalog[node.type];
  return (
    <div>
      <PanelHeader eyebrow={`${categories[spec.category].label} · ${spec.label}`} onClose={onClose}>
        <div className="mt-2 flex items-center gap-2.5">
          <StepIcon type={node.type} />
          <label className="sr-only" htmlFor={`name-${node.id}`}>
            Nombre del paso
          </label>
          <input
            id={`name-${node.id}`}
            value={node.name ?? ""}
            placeholder={nodeTitle(node)}
            readOnly={readOnly}
            onChange={(e) => onChange({ name: e.target.value || undefined })}
            className="min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 py-0.5 font-sans text-xl tracking-tight text-foreground hover:border-line focus:border-line-strong focus:outline-none placeholder:text-foreground first-letter:uppercase"
          />
        </div>
        <p className="mt-1 px-1 font-mono text-2xs text-muted-foreground">id: {node.id}</p>
        <p className="mt-2 font-body text-xs leading-relaxed text-muted-foreground">{spec.description}</p>
      </PanelHeader>
      {problems.length > 0 && (
        <div className="border-b border-line px-4 py-3">
          <ul className="space-y-1.5">
            {problems.map((p, i) => (
              <li
                key={i}
                className={`rounded-lg border px-2.5 py-1.5 font-body text-xs ${p.severity === "error" ? "border-danger-border bg-danger-soft text-danger" : "border-warning-border bg-warning-soft text-warning"}`}
              >
                {p.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      <NodeHelp node={node} />
      <Section title="Configuración">
        <ConfigEditor key={node.id} value={node.config ?? {}} readOnly={readOnly} onChange={(config) => onChange({ config })} />
        <p className="font-body text-xs text-muted-foreground">
          Lo resaltado son expresiones CEL que se evalúan al correr, sobre <code>vars</code>, <code>trigger</code>, <code>nodes.*</code> y <code>execution</code>.
        </p>
      </Section>
      <Section title="Si falla">
        <label className="flex items-center justify-between gap-2 font-body text-xs">
          Al fallar
          <select
            value={node.onError ?? "fail"}
            disabled={readOnly}
            onChange={(e) => onChange({ onError: e.target.value as FlowNode["onError"] })}
            className="h-8 rounded-full border border-line bg-background px-3 font-body text-xs text-foreground"
          >
            <option value="fail">detener la ejecución</option>
            <option value="continue">seguir igual</option>
            <option value="branch">ir por la salida “error”</option>
          </select>
        </label>
        <p className="font-body text-xs">
          <span className="text-muted-foreground">Reintentos:</span> {node.retry ? JSON.stringify(node.retry) : "los del tipo de paso"}
        </p>
      </Section>
      <Section title="Salidas">
        <div className="flex flex-wrap gap-1.5">
          {ports.length ? (
            ports.map((p) => (
              <span key={p} className={`rounded-full border px-2.5 py-0.5 font-body text-xs ${p === "error" ? "border-danger-border text-danger" : "border-line text-foreground"}`}>
                {portLabel(p)}
              </span>
            ))
          ) : (
            <span className="font-body text-xs text-muted-foreground">Paso final</span>
          )}
        </div>
      </Section>
      {!readOnly && (
        <div className="flex flex-wrap gap-2 px-4 py-4">
          {onDetach && (
            <Button variant="secondary" size="sm" className="rounded-full" onClick={onDetach} title="Lo saca del bloque y lo deja como bloque aparte, sin conexión de entrada">
              Separar del bloque
            </Button>
          )}
          <Button variant="ghost" size="sm" className="!text-danger" onClick={onDelete} disabled={isEntry}>
            {isEntry ? "El paso de inicio no se borra" : "Borrar paso"}
          </Button>
        </div>
      )}
    </div>
  );
}

// What waits and approvals mean in plain words (v2-flows P2).
function NodeHelp({ node }: { node: FlowNode }) {
  const c = node.config ?? {};
  if (node.type === "approval") {
    const roles = (c.assignees as { roles?: string[] } | undefined)?.roles?.join(", ") ?? "ops";
    return (
      <div className="border-b border-line border-l-2 border-l-warning bg-warning-soft px-4 py-3 font-body text-xs leading-relaxed text-foreground">
        La ejecución se pausa hasta que alguien de <strong>{roles}</strong> decida. Si nadie decide en{" "}
        <strong>{humanDuration(typeof c.expiresAfter === "string" ? c.expiresAfter : undefined)}</strong>, sigue por “vencido”. La persona ve exactamente lo que se va a enviar antes de aprobar.
      </div>
    );
  }
  if (node.type === "wait") {
    return (
      <div className="border-b border-dashed border-line bg-muted px-4 py-3 font-body text-xs leading-relaxed text-foreground">
        {c.mode === "until"
          ? "Espera hasta una fecha calculada. La espera es durable: sobrevive a deploys y reinicios, y no consume recursos."
          : `Espera ${humanDuration(typeof c.duration === "string" ? c.duration : undefined)}. Es durable: sobrevive a deploys y reinicios.`}
      </div>
    );
  }
  return null;
}

function ConfigEditor({ value, readOnly, onChange }: { value: Record<string, unknown>; readOnly: boolean; onChange: (v: Record<string, unknown>) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);
  if (readOnly) return <JsonView value={value} className="max-h-[360px]" />;
  return (
    <div>
      <label className="sr-only" htmlFor="node-config">
        Configuración (JSON)
      </label>
      <textarea
        id="node-config"
        value={text}
        spellCheck={false}
        rows={Math.min(16, text.split("\n").length + 1)}
        onChange={(e) => {
          setText(e.target.value);
          try {
            const parsed = JSON.parse(e.target.value) as unknown;
            if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("tiene que ser un objeto");
            setError(null);
            onChange(parsed as Record<string, unknown>);
          } catch (err) {
            setError(err instanceof Error ? err.message : "JSON inválido");
          }
        }}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "node-config-error" : undefined}
        className="w-full rounded-lg border border-line bg-background p-2.5 font-mono text-xs leading-relaxed text-foreground focus:border-line-strong focus:outline-none"
      />
      {error && (
        <p id="node-config-error" className="font-body text-xs text-danger">
          JSON inválido: {error}. El cambio no se aplica hasta que sea válido.
        </p>
      )}
    </div>
  );
}

export function FlowPanel({
  flow,
  flowKey,
  publishedVersion,
  executions,
}: {
  flow: FlowGraph;
  flowKey: string;
  publishedVersion: number | null;
  executions: ExecutionSummary[];
}) {
  const variables = flow.variables ?? [];
  return (
    <div>
      <PanelHeader eyebrow="Flow">
        <p className="mt-2 font-body text-sm leading-relaxed text-foreground">{flowDisplayDescription(flow.id, flow.description ?? "")}</p>
        <p className="mt-2 font-body text-xs text-muted-foreground">
          {publishedVersion ? `Publicado: v${publishedVersion}. Cada ejecución queda fija a la versión con la que arrancó.` : "Todavía no se publicó."}
        </p>
      </PanelHeader>
      <Section title="Disparador">
        <p className="font-body text-sm font-semibold">{triggerLabel(flow.trigger)}</p>
        {"filter" in flow.trigger && <JsonView value={{ filter: flow.trigger.filter }} />}
      </Section>
      <Section title={`Variables (${variables.length})`}>
        {variables.length === 0 && <p className="font-body text-xs text-muted-foreground">Este flow no declara variables.</p>}
        <ul className="divide-y divide-line rounded-lg border border-line">
          {variables.map((v) => (
            <li key={v.name} className="flex items-center gap-2 px-2.5 py-2 font-body text-xs">
              <code className="min-w-0 flex-1 truncate font-mono text-foreground">{`{${v.name}}`}</code>
              <span className="text-muted-foreground">{v.type}</span>
              {v.sensitive && <span className="rounded-full bg-warning-soft px-1.5 text-2xs text-warning">sensible</span>}
            </li>
          ))}
        </ul>
      </Section>
      <Section title={`Ejecuciones recientes (${executions.length})`}>
        {executions.length === 0 && <p className="font-body text-xs text-muted-foreground">Todavía no hay ejecuciones.</p>}
        <ul className="space-y-1.5">
          {executions.map((e) => (
            <li key={e.id}>
              <Link href={`/ops/flows/${flowKey}/executions/${e.id}`} className="block rounded-lg border border-line px-2.5 py-2 transition-colors hover:border-line-strong hover:bg-raised">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="font-mono">{e.id.slice(0, 8)}</span>
                  <ExecStatus status={e.status} />
                </div>
                <p className="mt-0.5 font-body text-xs text-muted-foreground">
                  {e.trigger_kind} · {formatDateTime(e.started_at)}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </Section>
      <Section title="Opciones" defaultOpen={false}>
        <JsonView value={flow.settings ?? {}} />
      </Section>
      <p className="px-4 py-3 font-body text-xs leading-relaxed text-muted-foreground">
        Elegí un paso para editarlo. Arrastrá desde una salida (●) hasta otro bloque para conectar; Suprimir borra el paso o la conexión elegida.
      </p>
    </div>
  );
}

export function ProblemsPanel({
  problems,
  onFocus,
  onClose,
  publishedVersion,
}: {
  problems: ValidationProblem[];
  onFocus: (id: string) => void;
  onClose: () => void;
  publishedVersion?: number | null;
}) {
  const errors = problems.filter((p) => p.severity === "error");
  const warnings = problems.filter((p) => p.severity === "warning");
  const title = errors.length
    ? `${errors.length} ${errors.length === 1 ? "error bloquea" : "errores bloquean"} la publicación`
    : warnings.length
      ? `Sin errores · ${warnings.length} ${warnings.length === 1 ? "advertencia" : "advertencias"}`
      : "La validación pasó";
  return (
    <div
      role="region"
      aria-label="Resultado de la validación"
      className="absolute left-1/2 top-4 z-10 w-[460px] max-w-[calc(100%-2rem)] -translate-x-1/2 rounded-xl border border-line-strong bg-card shadow-[0_24px_48px_-24px_rgb(0_0_0/0.9)]"
    >
      <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
        <p className="font-sans text-lg tracking-tight">{title}</p>
        <button type="button" onClick={onClose} aria-label="Cerrar" className="grid size-8 place-items-center rounded-full bg-muted text-muted-foreground hover:text-foreground">
          <X className="size-4" />
        </button>
      </div>
      <div className="max-h-[320px] space-y-1.5 overflow-y-auto px-4 py-3 text-sm">
        {problems.length === 0 && (
          <p className="font-body text-muted-foreground">
            Estructura, puertos, alcance, acciones y la regla de aprobaciones están bien.
            {publishedVersion ? ` Las ejecuciones nuevas arrancan en v${publishedVersion}.` : ""}
          </p>
        )}
        {[...errors, ...warnings].map((p, k) => (
          <button
            type="button"
            key={k}
            onClick={() => p.node_id && onFocus(p.node_id)}
            className="flex w-full items-start gap-2 rounded-lg border border-line px-2.5 py-2 text-left font-body text-xs transition-colors hover:border-line-strong hover:bg-raised"
          >
            <span aria-hidden className={`mt-1 size-2 shrink-0 rounded-full ${p.severity === "error" ? "bg-danger" : "bg-warning"}`} />
            <span>
              {p.node_id && <span className="font-mono font-semibold">{p.node_id} · </span>}
              {p.message}
              <span className="ml-1 text-muted-foreground">({p.code})</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
