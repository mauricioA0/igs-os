import type { ReactNode } from "react";
import { cn } from "./cn";

// One badge for every surface: pills, as on infinityglobalsports.com. Variants:
//   status — white/10 pill + colored dot; color means state, nothing else
//   label  — outlined uppercase eyebrow (Montserrat 600) for categories and metadata
//   kind   — filled neutral, optionally with an icon (risk, decision, commitment…)
export type Tone = "neutral" | "info" | "success" | "warning" | "danger" | "brand" | "ai" | "solid" | "live";
export type BadgeVariant = "status" | "label" | "kind";

// Status pills carry no tinted fill (the site has no accent color in chrome): a white/10 pill
// with the state in the dot. `solid` stays the white pill.
const statusTone: Record<Tone, string> = {
  neutral: "border-transparent bg-secondary text-foreground/85",
  info: "border-transparent bg-secondary text-foreground/85",
  success: "border-transparent bg-secondary text-foreground/85",
  warning: "border-transparent bg-secondary text-foreground/85",
  danger: "border-transparent bg-secondary text-foreground/85",
  brand: "border-transparent bg-secondary text-foreground/85",
  ai: "border-transparent bg-secondary text-foreground/85",
  solid: "border-primary bg-primary text-primary-foreground",
  live: "border-transparent bg-secondary text-foreground",
};

const dotTone: Record<Tone, string> = {
  neutral: "bg-muted-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  brand: "bg-brand",
  ai: "bg-ai",
  solid: "bg-primary-foreground",
  live: "bg-success-fill",
};

export function Badge({
  tone = "neutral",
  variant = "status",
  icon,
  className,
  children,
}: {
  tone?: Tone;
  variant?: BadgeVariant;
  /** @deprecated status badges always show their dot now. */
  dot?: boolean;
  icon?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 whitespace-nowrap rounded-full border font-body font-medium [&_svg]:size-3 [&_svg]:shrink-0",
        variant === "label"
          ? "border-line-strong bg-transparent px-2 py-px text-2xs font-semibold uppercase tracking-[0.06em] text-muted-foreground"
          : "px-2.5 py-0.5 text-xs",
        variant === "status" && statusTone[tone],
        variant === "kind" && "border-line bg-secondary text-foreground",
        className,
      )}
    >
      {variant === "status" && tone !== "solid" && (
        <span
          aria-hidden
          className={cn("size-1.5 shrink-0 rounded-full", dotTone[tone], tone === "live" && "animate-pulse")}
        />
      )}
      {icon}
      {children}
    </span>
  );
}

// ── Status vocabulary ─────────────────────────────────────────────────────
// Every status used across the product, per domain, with one tone and labels in both UI languages.

export type StatusDomain =
  | "trip"
  | "item"
  | "lead"
  | "approval"
  | "execution"
  | "flow"
  | "account"
  | "health"
  | "sentiment"
  | "fact";

type Entry = { tone: Tone; es: string; en: string };

export const statusVocabulary: Record<StatusDomain, Record<string, Entry>> = {
  trip: {
    draft: { tone: "neutral", es: "Borrador", en: "Draft" },
    proposed: { tone: "info", es: "Propuesta", en: "Proposed" },
    confirmed: { tone: "success", es: "Confirmada", en: "Confirmed" },
    in_progress: { tone: "live", es: "En curso", en: "On tour" },
    completed: { tone: "neutral", es: "Completada", en: "Completed" },
    cancelled: { tone: "danger", es: "Cancelada", en: "Cancelled" },
  },
  item: {
    pending: { tone: "warning", es: "Pendiente", en: "Pending" },
    requested: { tone: "info", es: "Solicitado", en: "Requested" },
    confirmed: { tone: "success", es: "Confirmado", en: "Confirmed" },
    completed: { tone: "neutral", es: "Hecho", en: "Done" },
    cancelled: { tone: "danger", es: "Cancelado", en: "Cancelled" },
  },
  lead: {
    new: { tone: "info", es: "Nuevo", en: "New" },
    qualified: { tone: "brand", es: "Calificado", en: "Qualified" },
    proposal_sent: { tone: "solid", es: "Propuesta enviada", en: "Proposal sent" },
    won: { tone: "success", es: "Ganado", en: "Won" },
    lost: { tone: "neutral", es: "Perdido", en: "Lost" },
  },
  approval: {
    pending: { tone: "warning", es: "Pendiente", en: "Pending" },
    approved: { tone: "success", es: "Aprobada", en: "Approved" },
    rejected: { tone: "danger", es: "Rechazada", en: "Rejected" },
    expired: { tone: "neutral", es: "Vencida", en: "Expired" },
    superseded: { tone: "neutral", es: "Reemplazada", en: "Superseded" },
  },
  execution: {
    pending: { tone: "neutral", es: "En cola", en: "Queued" },
    running: { tone: "info", es: "Ejecutando", en: "Running" },
    waiting: { tone: "warning", es: "Esperando", en: "Waiting" },
    succeeded: { tone: "success", es: "OK", en: "Succeeded" },
    completed: { tone: "success", es: "Completada", en: "Completed" },
    failed: { tone: "danger", es: "Falló", en: "Failed" },
    skipped: { tone: "neutral", es: "Omitido", en: "Skipped" },
    cancelled: { tone: "neutral", es: "Cancelada", en: "Cancelled" },
  },
  flow: {
    draft: { tone: "neutral", es: "Borrador", en: "Draft" },
    published: { tone: "success", es: "Publicado", en: "Published" },
    archived: { tone: "neutral", es: "Archivado", en: "Archived" },
  },
  account: {
    prospect: { tone: "info", es: "Prospecto", en: "Prospect" },
    active: { tone: "success", es: "Activo", en: "Active" },
    past: { tone: "neutral", es: "Anterior", en: "Past" },
    churned: { tone: "danger", es: "Perdido", en: "Churned" },
  },
  health: {
    green: { tone: "success", es: "Sano", en: "Healthy" },
    amber: { tone: "warning", es: "Atención", en: "At risk" },
    red: { tone: "danger", es: "Crítico", en: "Critical" },
  },
  sentiment: {
    positive: { tone: "success", es: "Positivo", en: "Positive" },
    neutral: { tone: "neutral", es: "Neutral", en: "Neutral" },
    negative: { tone: "danger", es: "Negativo", en: "Negative" },
    unknown: { tone: "neutral", es: "Sin datos", en: "Unknown" },
  },
  fact: {
    status: { tone: "neutral", es: "Estado", en: "Status" },
    commitment: { tone: "info", es: "Compromiso", en: "Commitment" },
    risk: { tone: "danger", es: "Riesgo", en: "Risk" },
    preference: { tone: "neutral", es: "Preferencia", en: "Preference" },
    budget: { tone: "brand", es: "Presupuesto", en: "Budget" },
    decision: { tone: "success", es: "Decisión", en: "Decision" },
  },
};

// Domain-less lookup for callers that only have a status string (earlier domains win).
export const statusTones: Record<string, Tone> = Object.fromEntries(
  Object.values(statusVocabulary)
    .flatMap((d) => Object.entries(d))
    .reverse()
    .map(([status, e]) => [status, e.tone]),
);

export function statusEntry(status: string, domain?: StatusDomain): Entry {
  const hit = domain ? statusVocabulary[domain][status] : undefined;
  const label = status.replace(/_/g, " ");
  return hit ?? { tone: statusTones[status] ?? "neutral", es: label, en: label };
}

export function StatusBadge({
  status,
  domain,
  label,
  lang = "es",
  dot,
  className,
}: {
  status: string;
  domain?: StatusDomain;
  label?: ReactNode;
  lang?: "es" | "en";
  dot?: boolean;
  className?: string;
}) {
  const entry = statusEntry(status, domain);
  return (
    <Badge tone={entry.tone} dot={dot} className={className}>
      {label ?? entry[lang]}
    </Badge>
  );
}
