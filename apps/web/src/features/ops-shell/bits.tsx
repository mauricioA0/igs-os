// Small presentational pieces shared by the ops features.
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/components/ui";
import { ApiError } from "@/lib/api/errors";
import { country, type Tone } from "./labels";

// Status pills as on the site: neutral white/10 pill, the color lives only in the dot.
const dots: Record<Tone, string> = {
  neutral: "bg-muted-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  live: "bg-success animate-pulse",
};

export function Pill({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-secondary px-2.5 py-0.5 font-body text-2xs font-semibold uppercase tracking-wide text-foreground/85",
        className,
      )}
    >
      <span className={cn("size-1.5 shrink-0 rounded-full", dots[tone])} aria-hidden />
      {children}
    </span>
  );
}

export function CountryTag({ name, city }: { name: string; city?: string }) {
  const c = country(name);
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className={cn("size-2 rounded-full", c.dot)} aria-hidden />
      {city ?? c.label}
      {city && <span className="text-muted-foreground">· {c.label}</span>}
    </span>
  );
}

export function Progress({ value, className, label }: { value: number; className?: string; label: string }) {
  const tone = value >= 90 ? "bg-success" : value >= 60 ? "bg-foreground" : "bg-warning";
  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}
      role="progressbar"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div className={cn("h-full rounded-full", tone)} style={{ width: `${value}%` }} />
    </div>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="type-hero mt-2">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionTitle({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="eyebrow">{children}</h2>
      {action}
    </div>
  );
}

export function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "warning" | "danger";
}) {
  return (
    <div className="rounded-md border border-border bg-card p-4">
      <p className="eyebrow">{label}</p>
      <p
        className={cn(
          "display mt-2 text-5xl tabular-nums",
          tone === "warning" && "text-warning",
          tone === "danger" && "text-danger",
        )}
      >
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Shown by containers when `services/core` can't be reached or answers with a problem. */
export function ApiUnavailable({ error, what }: { error: unknown; what: string }) {
  const detail =
    error instanceof ApiError
      ? `${error.status ? `${error.status} · ` : ""}${error.detail ?? error.title}`
      : error instanceof Error
        ? error.message
        : "Error desconocido";
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-warning/40 bg-warning/10 p-4 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
      <div>
        <p className="font-semibold">No pudimos cargar {what}.</p>
        <p className="mt-1 text-muted-foreground">
          La API de IGS OS no respondió ({detail}). Verificá que <code>services/core</code> esté corriendo y que{" "}
          <code>API_URL</code> apunte a ella.
        </p>
      </div>
    </div>
  );
}
