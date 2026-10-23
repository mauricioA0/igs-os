"use client";

import { AlertTriangle, ArrowRight, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { cn } from "@/components/ui";
import { Pill } from "@/features/ops-shell/bits";
import { fmtRange } from "@/features/ops-shell/format";
import { country, GENDER, SPORT, TRIP_STATUS } from "@/features/ops-shell/labels";

export type TripRow = {
  id: string;
  code: string;
  team: string;
  program?: string;
  sport?: string | null;
  gender?: string | null;
  levelScore?: number | null;
  city: string;
  country: string;
  startDate: string;
  endDate: string;
  travelers?: number | null;
  status: string;
  confirmedPct: number;
  confirmed: number;
  total: number;
  open: number;
};

// Drafts and cancelled trips stay under "Todas"; the pills are the site's five states.
const FILTERS: Array<{ id: string; label: string }> = [
  { id: "all", label: "Todas" },
  { id: "in_progress", label: "En curso" },
  { id: "confirmed", label: "Confirmadas" },
  { id: "proposed", label: "Propuestas" },
  { id: "completed", label: "Completadas" },
];

export function TripsTable({ rows }: { rows: TripRow[] }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter(
      (r) =>
        (filter === "all" || r.status === filter) &&
        (!q || `${r.code} ${r.team} ${r.program} ${r.city}`.toLowerCase().includes(q)),
    );
  }, [rows, filter, query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Filtrar por estado"
          className="relative flex max-w-full gap-1 overflow-x-auto rounded-full border border-line bg-foreground/5 p-1"
        >
          {FILTERS.map((f) => {
            const count = f.id === "all" ? rows.length : rows.filter((r) => r.status === f.id).length;
            const active = filter === f.id;
            return (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(f.id)}
                className={cn(
                  "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-4 text-xs font-semibold whitespace-nowrap transition-colors",
                  active ? "bg-foreground text-background" : "text-foreground/70 hover:text-foreground",
                )}
              >
                {f.label}
                <span className={cn("tabular-nums", active ? "opacity-60" : "opacity-50")}>{count}</span>
              </button>
            );
          })}
        </div>
        <label className="relative block w-full sm:w-72">
          <span className="sr-only">Buscar giras</span>
          <Search
            className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Equipo, código o ciudad"
            className="h-10 w-full rounded-full border border-line bg-card pl-10 pr-4 text-sm placeholder:text-muted-foreground focus:border-line-strong focus:outline-none"
          />
        </label>
      </div>

      <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line bg-card">
        {visible.map((r) => {
          const status = TRIP_STATUS[r.status] ?? { label: r.status, tone: "neutral" as const };
          const c = country(r.country);
          const meta = [
            r.program,
            r.sport && `${SPORT[r.sport] ?? r.sport} ${r.gender ? (GENDER[r.gender] ?? "") : ""}`.trim(),
            r.levelScore != null && `nivel ${r.levelScore}`,
            r.travelers != null && `${r.travelers} viajeros`,
          ].filter(Boolean);
          const live = r.status === "confirmed" || r.status === "in_progress";
          return (
            <li
              key={r.id}
              className="group relative grid gap-x-6 gap-y-3 px-5 py-5 transition-colors hover:bg-raised sm:px-6 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center"
            >
              <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", c.dot)} />
              <div className="min-w-0">
                <p className="eyebrow text-[0.6875rem] tracking-[0.2em]">{r.code}</p>
                <Link
                  href={`/ops/trips/${r.id}`}
                  aria-label={`${r.code} · ${r.team}`}
                  className="type-small-title mt-2 block truncate after:absolute after:inset-0 focus-visible:outline-none"
                >
                  {r.team}
                </Link>
                {meta.length > 0 && <p className="mt-2 truncate text-xs text-muted-foreground">{meta.join(" · ")}</p>}
              </div>

              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm">
                  <span aria-hidden className={cn("size-2 shrink-0 rounded-full", c.dot)} />
                  <span className="truncate">
                    {r.city} <span className="text-muted-foreground">· {c.label}</span>
                  </span>
                </p>
                <p className="mt-1 whitespace-nowrap text-xs text-muted-foreground tabular-nums">
                  {fmtRange(r.startDate, r.endDate)}
                </p>
              </div>

              <div className="min-w-0">
                <div className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="text-muted-foreground">Confirmado</span>
                  <span className="tabular-nums">
                    {r.confirmed}/{r.total}
                  </span>
                </div>
                <div
                  role="progressbar"
                  aria-label={`Confirmaciones ${r.code}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={r.confirmedPct}
                  className="mt-2 h-1 overflow-hidden rounded-full bg-foreground/10"
                >
                  <div className="h-full rounded-full bg-foreground" style={{ width: `${r.confirmedPct}%` }} />
                </div>
                {r.open > 0 && live && (
                  <p className="mt-2 flex items-center gap-1 text-xs font-semibold text-warning">
                    <AlertTriangle className="size-3.5" aria-hidden />
                    {r.open} sin confirmar
                  </p>
                )}
              </div>

              <div className="flex items-center gap-3 md:justify-end">
                <Pill tone={status.tone}>{status.label}</Pill>
                <span
                  aria-hidden
                  className="hidden size-8 items-center justify-center rounded-full bg-foreground/10 text-foreground/70 transition-colors group-hover:bg-foreground group-hover:text-background md:inline-flex"
                >
                  <ArrowRight className="size-4" />
                </span>
              </div>
            </li>
          );
        })}
        {visible.length === 0 && (
          <li className="px-6 py-14 text-center text-sm text-muted-foreground">No hay giras con ese filtro.</li>
        )}
      </ul>
    </div>
  );
}
