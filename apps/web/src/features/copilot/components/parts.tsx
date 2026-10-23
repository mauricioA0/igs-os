// Presentational pieces of the copilot drawer: props in, markup out. No store, no fetch.
import { useId, useState, type ReactNode } from "react";

import { cn } from "@/components/ui/cn";

import { splitAnswer } from "../citations";
import { CHIP_KIND_LABEL } from "../context";
import type { ApprovalProposal, CitationSource, ContextChip, ToolStep } from "../types";

// ── Tool steps ───────────────────────────────────────────────────────────────

const TOOL_LABEL: Record<string, string> = {
  search_knowledge: "Buscando en la base de conocimiento",
  list_trips: "Revisando giras",
  get_trip: "Leyendo la gira",
  list_unconfirmed_items: "Buscando ítems sin confirmar",
  find_accounts: "Buscando clientes",
  get_account_brief: "Leyendo la ficha del cliente",
  search_account_history: "Buscando en el historial del cliente",
  list_stakeholders: "Revisando stakeholders",
  list_pending_approvals: "Revisando aprobaciones pendientes",
  list_flows: "Revisando flows",
  update_trip_item: "Actualizando un ítem",
  run_flow_test: "Probando un flow (sandbox)",
  request_approval: "Preparando una aprobación",
  send_proposal: "Preparando el envío de la propuesta",
  cancel_trip_item: "Preparando la cancelación de un ítem",
  set_trip_status: "Preparando el cambio de estado de la gira",
  daily_digest: "Armando el resumen del día",
  trip_readiness: "Revisando la documentación de los viajeros",
  update_traveler_document: "Actualizando un documento de viaje",
  list_payment_risks: "Revisando pagos vencidos y por vencer",
};

export function toolLabel(name: string): string {
  return TOOL_LABEL[name] ?? name.replaceAll("_", " ");
}

const STEP_ICON: Record<ToolStep["status"], { dot: string; label: string }> = {
  running: { dot: "bg-white/50", label: "en curso" },
  ok: { dot: "bg-success", label: "listo" },
  error: { dot: "bg-danger", label: "falló" },
  approval: { dot: "bg-warning", label: "necesita aprobación" },
};

export function ToolSteps({ steps }: { steps: ToolStep[] }) {
  if (!steps.length) return null;
  return (
    <ol className="divide-y divide-white/5 rounded-lg border border-white/10 font-body text-xs" aria-label="Pasos del copiloto">
      {steps.map((s) => {
        const icon = STEP_ICON[s.status];
        return (
          <li key={s.callId} className="flex items-center gap-3 px-3 py-2">
            <span
              aria-hidden
              className={cn("h-1.5 w-1.5 shrink-0 rounded-full", icon.dot, s.status === "running" && "animate-pulse motion-reduce:animate-none")}
            />
            <span className="text-white/80">{toolLabel(s.name)}</span>
            <span className="sr-only">: {icon.label}</span>
            {s.ms !== undefined && <span className="ml-auto font-mono text-[11px] tabular-nums text-white/40">{s.ms} ms</span>}
          </li>
        );
      })}
    </ol>
  );
}

// ── Answer with citation chips ─────────────────────────────────────────────

function Bold({ text }: { text: string }) {
  // Only **bold** is rendered; everything else is plain text (no HTML from the model).
  const pieces = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {pieces.map((p, i) =>
        p.startsWith("**") && p.endsWith("**") && p.length > 4 ? (
          <strong key={i} className="font-semibold text-white">{p.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  );
}

export function CitationChip({ source }: { source: CitationSource }) {
  const [open, setOpen] = useState(false);
  const previewId = useId();
  const descId = useId();
  return (
    <span className="relative inline-block align-baseline">
      {/* WCAG 2.5.3: name = visible text; the spoken "Fuente 1: email del …" is the description. */}
      <span id={descId} className="sr-only">
        {source.ariaLabel}
      </span>
      <button
        type="button"
        aria-describedby={open ? `${descId} ${previewId}` : descId}
        data-citation={source.n}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="mx-0.5 inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-px align-[1px] font-body text-[11px] font-semibold leading-4 text-white/80 transition-colors hover:bg-white/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="tabular-nums text-white/50">{source.n}</span>{" "}
        {source.label}
      </button>
      {open && (
        <span
          id={previewId}
          role="tooltip"
          className="absolute bottom-full left-0 z-20 mb-2 block w-72 rounded-lg border border-white/10 bg-raised p-3 font-body text-xs leading-5 text-foreground shadow-2xl"
        >
          {source.title && <span className="mb-1 block font-semibold text-white">{source.title}</span>}
          <span className="block text-muted-foreground">“{source.snippet}”</span>
        </span>
      )}
    </span>
  );
}

export function Answer({ text, citations }: { text: string; citations: CitationSource[] }) {
  const parts = splitAnswer(text, citations.length);
  return (
    <p className="whitespace-pre-wrap font-body text-[15px] leading-7 text-foreground/90">
      {parts.map((p, i) =>
        p.kind === "text" ? (
          <Bold key={i} text={p.text} />
        ) : (
          <CitationChip key={i} source={citations[p.n - 1]} />
        ),
      )}
    </p>
  );
}

export function Sources({ citations }: { citations: CitationSource[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-3 border-t border-white/10 pt-3">
      <p className="eyebrow text-[11px] text-muted-foreground">Fuentes</p>
      <ul className="mt-2 flex flex-wrap gap-1.5">
        {citations.map((c) => (
          <li key={c.n}>
            <CitationChip source={c} />
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── Approval card ──────────────────────────────────────────────────────────

export function ApprovalCard({ approval }: { approval: ApprovalProposal }) {
  return (
    // SpotlightCard look (stadium-art backdrop + dark overlay); inline until @/components/ui ships it.
    <div
      role="group"
      aria-label={`Aprobación pendiente: ${approval.title}`}
      className="stadium-art relative isolate overflow-hidden rounded-xl border border-white/10 bg-raised p-5"
    >
      <div aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(120%_80%_at_100%_0%,rgba(255,255,255,0.12),transparent_60%)]" />
      <div aria-hidden className="absolute inset-0 -z-10 bg-gradient-to-t from-black/70 to-transparent" />
      <p className="eyebrow flex items-center gap-2 text-[11px] text-white">
        <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-warning" />
        Necesita aprobación
      </p>
      <p className="type-card mt-3 font-sans text-xl leading-[1.05] tracking-[-0.05em] text-white">{approval.title}</p>
      <p className="mt-2 font-body text-xs leading-5 text-muted-foreground">
        Todavía no se hizo nada. Una persona tiene que aprobar esta acción exacta en IGS OS.
      </p>
      <div className="mt-4 flex items-center justify-between gap-3">
        <span className="truncate font-mono text-[11px] text-white/40" title={approval.payload_hash}>
          {approval.payload_hash.slice(0, 19)}
        </span>
        <a
          href={approval.review_url}
          className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-foreground px-4 font-body text-xs font-semibold text-background transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Revisar y aprobar
          <span aria-hidden>→</span>
        </a>
      </div>
    </div>
  );
}

// ── Context chips, prompts, states ─────────────────────────────────────────

export function ContextChips({ chips, onRemove }: { chips: ContextChip[]; onRemove: (c: ContextChip) => void }) {
  if (!chips.length) return null;
  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Contexto de la pregunta">
      {chips.map((c) => (
        <li
          key={`${c.kind}:${c.id}`}
          className="inline-flex h-7 items-center gap-1.5 rounded-full border border-white/10 bg-white/10 pl-3 pr-1 font-body text-[11px]"
        >
          <span className="font-semibold uppercase tracking-[0.08em] text-white/50">{CHIP_KIND_LABEL[c.kind]}</span>
          <span className="max-w-32 truncate font-semibold text-white">{c.label ?? c.id}</span>
          <button
            type="button"
            onClick={() => onRemove(c)}
            aria-label={`Quitar ${CHIP_KIND_LABEL[c.kind].toLowerCase()} ${c.label ?? c.id} del contexto`}
            className="inline-flex h-5 w-5 items-center justify-center rounded-full text-white/50 transition-colors hover:bg-white/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            ×
          </button>
        </li>
      ))}
    </ul>
  );
}

export function SuggestedPrompts({ prompts, onPick, disabled }: { prompts: string[]; onPick: (p: string) => void; disabled?: boolean }) {
  return (
    <div>
      <p className="eyebrow text-[11px] text-muted-foreground">Probá con</p>
      <ul className="mt-3 space-y-2">
        {prompts.map((p) => (
          <li key={p}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onPick(p)}
              className="group flex w-full items-center gap-3 rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-left font-body text-sm text-white/80 transition-colors hover:border-white/20 hover:bg-white/10 hover:text-white disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span className="flex-1">{p}</span>
              <span aria-hidden className="text-white/40 transition-transform group-hover:translate-x-0.5 group-hover:text-white">→</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Notice({ tone, title, children }: { tone: "danger" | "warning" | "info"; title: string; children?: ReactNode }) {
  const tones = { danger: "bg-danger", warning: "bg-warning", info: "bg-info" };
  return (
    <div role={tone === "danger" ? "alert" : "status"} className="rounded-lg border border-white/10 bg-white/5 p-4 font-body text-sm">
      <p className="flex items-center gap-2 font-semibold text-white">
        <span aria-hidden className={cn("h-1.5 w-1.5 shrink-0 rounded-full", tones[tone])} />
        {title}
      </p>
      {children && <div className="mt-1 text-xs text-muted-foreground">{children}</div>}
    </div>
  );
}

// ── MCP ─────────────────────────────────────────────────────────────────────

export function mcpCommand(mcpUrl: string): string {
  return `claude mcp add --transport http igs-os ${mcpUrl} --header "Authorization: Bearer $IGS_MCP_KEY"`;
}

export function McpPanel({ mcpUrl, onCopy, copied }: { mcpUrl: string; onCopy: () => void; copied: boolean }) {
  return (
    <section aria-labelledby="mcp-title" className="space-y-4 font-body text-sm">
      <p className="eyebrow text-[11px] text-muted-foreground">Claude Code · Claude Desktop</p>
      <h3 id="mcp-title" className="type-card font-sans text-2xl leading-[0.95] tracking-[-0.05em] text-white">Conectar por MCP</h3>
      <p className="text-sm leading-6 text-muted-foreground">
        Las mismas herramientas y las mismas reglas desde Claude Code o Claude Desktop. Una key de MCP
        puede proponer acciones, nunca aprobarlas.
      </p>
      <div className="overflow-hidden rounded-lg border border-white/10 bg-background">
        <div className="flex items-center gap-1.5 border-b border-white/10 px-3 py-2">
          <span aria-hidden className="h-2 w-2 rounded-full bg-white/15" />
          <span aria-hidden className="h-2 w-2 rounded-full bg-white/15" />
          <span aria-hidden className="h-2 w-2 rounded-full bg-white/15" />
          <span className="ml-2 font-mono text-[11px] text-white/40">terminal</span>
        </div>
        <pre className="overflow-x-auto whitespace-pre-wrap break-all p-4 font-mono text-[12px] leading-6 text-white/85">
          <code>{mcpCommand(mcpUrl)}</code>
        </pre>
      </div>
      <button
        type="button"
        onClick={onCopy}
        className={cn(
          "inline-flex h-9 items-center rounded-full px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          copied ? "bg-foreground text-background" : "bg-white/10 text-white/70 hover:bg-white/15 hover:text-white",
        )}
      >
        {copied ? "Copiado" : "Copiar comando"}
      </button>
    </section>
  );
}
