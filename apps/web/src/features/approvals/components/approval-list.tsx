import { Clock } from "lucide-react";
import { cn } from "@/components/ui";
import { expiryState, formatRemaining } from "../lib/expiry";
import { effectiveStatus } from "../lib/status";
import type { ApprovalSummary } from "../types";
import { RISK_LABEL, STATUS_LABEL } from "./labels";
import { PILL_GROUP, PILL_GROUP_ACTIVE, PILL_GROUP_IDLE, PILL_GROUP_ITEM, TAG, TAG_TONE, tagTone } from "./pills";

export type ListView = "pending" | "resolved" | "all";

const VIEWS: { id: ListView; label: string }[] = [
  { id: "pending", label: "Pendientes" },
  { id: "resolved", label: "Resueltas" },
  { id: "all", label: "Todas" },
];

const RISKS: { id: "all" | "external" | "internal"; label: string }[] = [
  { id: "all", label: "Todos" },
  { id: "external", label: "Sale afuera" },
  { id: "internal", label: "Internos" },
];

export function filterApprovals(
  items: ApprovalSummary[],
  view: ListView,
  risk: "all" | "external" | "internal",
  now: Date,
) {
  return items.filter((a) => {
    const status = effectiveStatus(a, now);
    if (view === "pending" && status !== "pending") return false;
    if (view === "resolved" && status === "pending") return false;
    if (risk === "external" && a.risk_class !== "external") return false;
    if (risk === "internal" && a.risk_class === "external") return false;
    return true;
  });
}

// Presentational list + filters. Selection and filters are owned by the container.
export function ApprovalList({
  items,
  counts,
  view,
  risk,
  selectedId,
  now,
  onView,
  onRisk,
  onSelect,
}: {
  items: ApprovalSummary[];
  counts: Record<ListView, number>;
  view: ListView;
  risk: "all" | "external" | "internal";
  selectedId?: string;
  now: Date;
  onView: (v: ListView) => void;
  onRisk: (r: "all" | "external" | "internal") => void;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div role="group" aria-label="Estado" className={cn(PILL_GROUP, "w-full justify-between")}>
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={view === v.id}
              onClick={() => onView(v.id)}
              className={cn(PILL_GROUP_ITEM, "flex-1 justify-center", view === v.id ? PILL_GROUP_ACTIVE : PILL_GROUP_IDLE)}
            >
              {v.label}
              <span className={cn("tabular-nums", view === v.id ? "text-card/60" : "text-muted-foreground")}>{counts[v.id]}</span>
            </button>
          ))}
        </div>
        <div role="group" aria-label="Riesgo" className="flex flex-wrap items-center gap-1">
          <span className="eyebrow mr-1 text-[11px] text-muted-foreground">Riesgo</span>
          {RISKS.map((r) => (
            <button
              key={r.id}
              type="button"
              aria-pressed={risk === r.id}
              onClick={() => onRisk(r.id)}
              className={cn(
                PILL_GROUP_ITEM,
                "h-7 border px-3",
                risk === r.id ? "border-foreground bg-foreground text-card" : "border-line text-foreground/70 hover:border-line-strong hover:text-foreground",
              )}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>
      {items.length === 0 ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-10 text-center text-sm text-muted-foreground">
          {view === "pending" ? "No hay nada esperando tu decisión." : "No hay aprobaciones con estos filtros."}
        </p>
      ) : (
        <ul className="space-y-2" aria-label="Aprobaciones">
          {items.map((a) => {
            const exp = a.status === "pending" ? expiryState(a.expires_at, now) : { kind: "none" as const };
            const status = STATUS_LABEL[effectiveStatus(a, now)];
            const selected = a.id === selectedId;
            return (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onSelect(a.id)}
                  aria-current={selected ? "true" : undefined}
                  className={cn(
                    "group relative w-full rounded-lg border bg-card p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected ? "border-foreground/60 bg-raised" : "border-line hover:border-line-strong hover:bg-raised/60",
                  )}
                >
                  {selected && <span aria-hidden className="absolute inset-y-3 left-0 w-0.5 rounded-full bg-foreground" />}
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className={cn(TAG, tagTone(RISK_LABEL[a.risk_class].tone))}>{RISK_LABEL[a.risk_class].label}</span>
                    {effectiveStatus(a, now) !== "pending" && <span className={cn(TAG, tagTone(status.tone))}>{status.label}</span>}
                    {exp.kind === "pending" && (
                      <span className={cn(TAG, "ml-auto tabular-nums", exp.urgent ? TAG_TONE.danger : TAG_TONE.neutral)}>
                        <Clock aria-hidden className="size-3" />
                        vence en {formatRemaining(exp.remainingMs)}
                      </span>
                    )}
                  </div>
                  <p className="type-small-title mt-3 text-foreground">{a.title}</p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
