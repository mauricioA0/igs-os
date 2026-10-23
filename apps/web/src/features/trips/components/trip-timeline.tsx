"use client";

import {
  AlertTriangle,
  Circle,
  Clock,
  Dumbbell,
  Info,
  Lock,
  type LucideIcon,
  PlaneLanding,
  PlaneTakeoff,
  Sparkles,
  Sun,
  Trophy,
} from "lucide-react";
import { useMemo, useState, useTransition } from "react";
import { cn } from "@/components/ui";
import { Pill } from "@/features/ops-shell/bits";
import { addDays, fmtWeekday } from "@/features/ops-shell/format";
import { ITEM_KIND, ITEM_STATUS, SLOT, SLOT_ORDER } from "@/features/ops-shell/labels";
import { updateTripItemStatus } from "../actions";
import type { TripItem } from "../api";

type View = "all" | "open" | "matches";

const VIEWS: Array<{ id: View; label: string }> = [
  { id: "all", label: "Todo" },
  { id: "open", label: "Sin confirmar" },
  { id: "matches", label: "Partidos" },
];

const KIND_ICON: Record<string, LucideIcon> = {
  arrival: PlaneLanding,
  departure: PlaneTakeoff,
  match: Trophy,
  training: Dumbbell,
  experience: Sparkles,
  free: Sun,
};

// Primary action first, the risky "reopen" kept secondary (UX review V1 P4). Mirrors the API's
// transitions so no button leads to a 409.
type ItemStatus = TripItem["status"];

const NEXT_ACTIONS: Record<ItemStatus, Array<{ to: ItemStatus; label: string; primary?: boolean }>> = {
  pending: [
    { to: "confirmed", label: "Confirmar", primary: true },
    { to: "requested", label: "Marcar solicitado" },
  ],
  requested: [
    { to: "confirmed", label: "Confirmar", primary: true },
    { to: "pending", label: "Volver a pendiente" },
  ],
  confirmed: [
    { to: "completed", label: "Marcar realizado", primary: true },
    { to: "pending", label: "Reabrir" },
  ],
  // Completed is terminal (igs_common.domain.transitions): a correction is a new item.
  completed: [],
  cancelled: [{ to: "pending", label: "Restaurar" }],
};

/**
 * Day-by-day itinerary with status actions.
 *
 * Changes go to `PATCH /v1/trips/{id}/items/{item_id}` through a server action. The row updates
 * optimistically and rolls back with the API's reason if the write fails (e.g. the read-only demo).
 */
export function TripTimeline({
  tripId,
  items: initial,
  startDate,
  currentDay,
  teamLevel,
  readOnlyReason,
}: {
  tripId: string;
  items: TripItem[];
  startDate: string;
  currentDay?: number;
  /** The visiting team's level (1–10), to show each opponent relative to it. */
  teamLevel?: number | null;
  /** Set when this viewer can't write (the public demo); actions are disabled with this reason. */
  readOnlyReason?: string;
}) {
  const [items, setItems] = useState(initial);
  const [view, setView] = useState<View>("all");
  const [notice, setNotice] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  const days = useMemo(() => {
    const filtered = items.filter(
      (i) =>
        view === "all" ||
        (view === "open" && (i.status === "pending" || i.status === "requested")) ||
        (view === "matches" && i.kind === "match"),
    );
    const byDay = new Map<number, TripItem[]>();
    for (const item of filtered) byDay.set(item.day, [...(byDay.get(item.day) ?? []), item]);
    for (const list of byDay.values()) list.sort((a, b) => SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot));
    return [...byDay.entries()].sort(([a], [b]) => a - b);
  }, [items, view]);

  function setStatus(id: string, status: ItemStatus) {
    const previous = items.find((i) => i.id === id);
    if (!previous || readOnlyReason) return;
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, status } : i)));
    setPendingId(id);
    setNotice(null);
    startTransition(async () => {
      const result = await updateTripItemStatus(tripId, id, status);
      setPendingId(null);
      if (result.ok) {
        setItems((prev) => prev.map((i) => (i.id === id ? { ...i, ...result.data } : i)));
        setNotice({ tone: "info", text: `«${previous.title}» quedó ${ITEM_STATUS[status]?.label.toLowerCase() ?? status}.` });
      } else {
        setItems((prev) => prev.map((i) => (i.id === id ? previous : i)));
        setNotice({ tone: "danger", text: result.message });
      }
    });
  }

  // "La Tira": every day of the trip at a glance, from the live (optimistic) items.
  const strip = useMemo(() => {
    const total = Math.max(0, ...items.map((i) => i.day));
    return Array.from({ length: total }, (_, n) => {
      const list = items.filter((i) => i.day === n + 1 && i.status !== "cancelled");
      return {
        day: n + 1,
        count: list.length,
        open: list.filter((i) => i.status === "pending" || i.status === "requested").length,
        match: list.some((i) => i.kind === "match"),
      };
    });
  }, [items]);

  return (
    <section aria-labelledby="timeline-title" className="space-y-6">
      {strip.length > 0 && (
        <nav aria-label="La Tira: días de la gira" className="space-y-3">
          <p className="eyebrow text-xs">La Tira</p>
          <ol className="relative flex gap-1.5 overflow-x-auto pb-1">
            {strip.map((d) => {
              const isToday = d.day === currentDay;
              const isPast = currentDay !== undefined && d.day < currentDay;
              return (
                <li key={d.day} className="shrink-0">
                  <a
                    href={`#day-${d.day}`}
                    aria-current={isToday ? "date" : undefined}
                    className={cn(
                      "flex w-18 flex-col gap-1 rounded-md border px-3 py-2.5 transition-colors",
                      isToday
                        ? "border-foreground bg-foreground text-background"
                        : "border-line bg-card hover:border-line-strong",
                      isPast && "opacity-50",
                    )}
                  >
                    <span className="font-display text-2xl leading-none font-extrabold uppercase tabular-nums">
                      D{d.day}
                    </span>
                    <span className={cn("text-2xs uppercase tracking-wide", isToday ? "opacity-70" : "text-muted-foreground")}>
                      {fmtWeekday(addDays(startDate, d.day - 1))}
                    </span>
                    <span className="flex items-center gap-1" aria-hidden>
                      {d.match && <Trophy className="size-3" />}
                      <span
                        className={cn(
                          "h-1 flex-1 rounded-full",
                          d.count === 0 ? "bg-foreground/10" : d.open > 0 ? "bg-warning" : isToday ? "bg-background" : "bg-success",
                        )}
                      />
                    </span>
                    <span className="sr-only">
                      {d.count} ítems{d.open > 0 ? `, ${d.open} sin confirmar` : ""}
                      {d.match ? ", con partido" : ""}
                    </span>
                  </a>
                </li>
              );
            })}
          </ol>
        </nav>
      )}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 id="timeline-title" className="type-card">
          Itinerario
        </h2>
        <div
          role="group"
          aria-label="Filtrar itinerario"
          className="flex gap-1 rounded-full border border-line bg-foreground/5 p-1"
        >
          {VIEWS.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={view === v.id}
              onClick={() => setView(v.id)}
              className={cn(
                "h-7 rounded-full px-3.5 text-xs font-semibold transition-colors",
                view === v.id ? "bg-foreground text-background" : "text-foreground/70 hover:text-foreground",
              )}
            >
              {v.label}
            </button>
          ))}
        </div>
      </div>

      {readOnlyReason && (
        <p className="flex items-start gap-2 rounded-md border border-line bg-raised p-3 text-xs text-muted-foreground">
          <Lock className="mt-px size-3.5 shrink-0" aria-hidden />
          {readOnlyReason}
        </p>
      )}
      <p
        role="status"
        aria-live="polite"
        className={cn(
          "flex items-start gap-2 rounded-md border p-3 text-xs",
          !notice && "sr-only",
          notice?.tone === "danger" ? "border-danger/30 bg-danger/10" : "border-info/30 bg-info/10",
        )}
      >
        {notice && (
          <Info className={cn("mt-px size-3.5 shrink-0", notice.tone === "danger" ? "text-danger" : "text-info")} aria-hidden />
        )}
        {notice?.text}
      </p>

      <ol className="space-y-10">
        {days.map(([day, list]) => {
          const isToday = day === currentDay;
          const isPast = currentDay !== undefined && day < currentDay;
          return (
            <li key={day} id={`day-${day}`} className="scroll-mt-6">
              <div className={cn("flex items-baseline gap-3 border-b border-line pb-3", isPast && "opacity-50")}>
                <p className="type-hero tabular-nums">D{day}</p>
                <p className="eyebrow text-xs">{fmtWeekday(addDays(startDate, day - 1))}</p>
                {isToday && (
                  <Pill tone="live" className="rounded-full px-2.5">
                    Hoy
                  </Pill>
                )}
              </div>
              <ul className={cn("divide-y divide-line", isPast && "opacity-60")}>
                {list.map((item) => {
                  const status = ITEM_STATUS[item.status] ?? { label: item.status, tone: "neutral" as const };
                  const open = item.status === "pending" || item.status === "requested";
                  const urgent = open && currentDay !== undefined && item.day <= currentDay + 1;
                  const KindIcon = KIND_ICON[item.kind] ?? Circle;
                  return (
                    <li
                      key={item.id}
                      id={item.id}
                      className={cn(
                        "grid scroll-mt-6 grid-cols-[3.5rem_2.25rem_minmax(0,1fr)] gap-x-3 gap-y-3 rounded-md py-4 target:bg-raised target:ring-2 target:ring-ring sm:grid-cols-[4rem_2.25rem_minmax(0,1fr)_auto]",
                        urgent && "border-l-2 border-l-warning pl-2",
                      )}
                    >
                      <div className="pt-1.5 text-sm tabular-nums">
                        {item.time ? (
                          <span className="inline-flex items-center gap-1">
                            <Clock className="size-3 text-muted-foreground" aria-hidden />
                            {item.time.slice(0, 5)}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground">{SLOT[item.slot] ?? item.slot}</span>
                        )}
                      </div>
                      <span
                        aria-hidden
                        className={cn(
                          "inline-flex size-9 items-center justify-center rounded-full",
                          item.kind === "match" ? "bg-foreground text-background" : "bg-foreground/10 text-foreground/80",
                        )}
                      >
                        <KindIcon className="size-4" />
                      </span>
                      <div className="min-w-0">
                        <p className="eyebrow text-2xs tracking-[0.2em]">
                          {SLOT[item.slot] ?? item.slot} · {ITEM_KIND[item.kind] ?? item.kind}
                        </p>
                        <p className="mt-1 text-base font-medium tracking-tight">{item.title}</p>
                        {(item.opponent || item.provider) && (
                          <p className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                            {item.opponent && (
                              <span>
                                Rival: <span className="text-foreground">{item.opponent.name}</span>
                                {item.opponent.level_score != null && (
                                  <> · nivel {item.opponent.level_score}{levelHint(item.opponent.level_score, teamLevel)}</>
                                )}
                              </span>
                            )}
                            {item.provider && (
                              <span>
                                Proveedor: <span className="text-foreground">{item.provider.name}</span>
                              </span>
                            )}
                          </p>
                        )}
                        {item.alert && (
                          <p className="mt-2 flex items-start gap-1.5 text-xs font-semibold text-danger">
                            <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
                            {item.alert}
                          </p>
                        )}
                        {item.notes && <p className="mt-2 border-l-2 border-line pl-2 text-xs text-muted-foreground">{item.notes}</p>}
                        {urgent && (
                          <p className="mt-2 flex items-start gap-1.5 text-xs font-semibold text-warning">
                            <AlertTriangle className="mt-px size-3.5 shrink-0" aria-hidden />
                            {item.day === currentDay ? "Hoy" : "Mañana"} y todavía sin confirmar.
                          </p>
                        )}
                      </div>
                      <div className="col-span-3 col-start-1 flex flex-wrap items-center gap-2 sm:col-span-1 sm:col-start-auto sm:flex-col sm:items-end">
                        <Pill tone={status.tone} className="rounded-full px-2.5">
                          {status.label}
                        </Pill>
                        <div className="flex flex-wrap gap-1.5 sm:justify-end">
                          {(NEXT_ACTIONS[item.status] ?? []).map((a) => (
                            <button
                              key={a.to}
                              type="button"
                              disabled={Boolean(readOnlyReason) || pendingId === item.id}
                              title={readOnlyReason}
                              onClick={() => setStatus(item.id, a.to)}
                              className={cn(
                                "h-7 rounded-full px-3 text-xs font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                                a.primary
                                  ? "bg-foreground text-background hover:bg-foreground/85"
                                  : "bg-foreground/10 text-foreground/70 hover:text-foreground",
                              )}
                            >
                              {a.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </li>
          );
        })}
        {days.length === 0 && (
          <li className="rounded-lg border border-dashed border-line p-10 text-center text-sm text-muted-foreground">
            Nada para mostrar con este filtro.
          </li>
        )}
      </ol>
    </section>
  );
}

/** "(parejo)", "(+2 sobre el equipo)"… relative to the visiting team's level. */
function levelHint(level: number, team?: number | null): string {
  if (team == null) return "";
  const diff = level - team;
  if (diff === 0) return " (parejo)";
  return diff > 0 ? ` (+${diff} sobre el equipo)` : ` (${diff} bajo el equipo)`;
}
