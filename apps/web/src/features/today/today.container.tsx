import Link from "next/link";
import { connection } from "next/server";
import { ApiUnavailable, CountryTag, Pill, Progress } from "@/features/ops-shell/bits";
import { ReasonText } from "@/features/ops-shell/source-text";
import { daysBetween, fmtRange, fmtRelative, fmtWeekday, todayIso } from "@/features/ops-shell/format";
import { ITEM_KIND, ITEM_STATUS, RISK_CLASS, SLOT, SLOT_ORDER } from "@/features/ops-shell/labels";
import { getAccount, listAccounts } from "@/features/accounts/api";
import { getTrip, isOpen, listTrips, tripDay, type TripDetail, type TripItem } from "@/features/trips/api";
import { unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { serverApi } from "@/lib/api/server";
import { DayStrip } from "./components/day-strip";
import { KpiRow } from "./components/kpi-row";
import { PillLink } from "./components/pill-link";
import { RedSpotlight } from "./components/red-spotlight";

type Approval = components["schemas"]["ApprovalSummary"];
/** A client the deterministic health rules flag red, with its first reason (never from the model). */
type RedAccount = { id: string; name: string; reason: string | undefined };

async function redAccounts(): Promise<RedAccount[]> {
  const red = (await listAccounts()).filter((a) => a.health === "red");
  const details = await Promise.all(red.map((a) => getAccount(a.id)));
  return red.map((a, i) => ({ id: a.id, name: a.name, reason: details[i]?.health_reasons?.[0] }));
}

async function load() {
  // `status=pending` is the effective status: approvals past their expiry are excluded by the API,
  // and `counts` is the same number the sidebar badge and the inbox show.
  const [trips, approvals, counts, red] = await Promise.all([
    listTrips(),
    unwrap(serverApi().GET("/v1/approvals", { params: { query: { status: "pending", limit: 100 } } })),
    unwrap(serverApi().GET("/v1/approvals/counts")),
    redAccounts(),
  ]);
  const active = trips.filter((t) => t.status === "in_progress" || t.status === "confirmed");
  const details = (await Promise.all(active.map((t) => getTrip(t.id)))).filter((t): t is TripDetail => t !== null);
  return { details, approvals: approvals.items, pendingCount: counts.pending, red };
}

export async function TodayContainer() {
  await connection();
  const today = todayIso();
  let data: Awaited<ReturnType<typeof load>>;
  try {
    data = await load();
  } catch (error) {
    return (
      <div className="space-y-10">
        <Hero today={today} summary="No pudimos traer el estado de la operación." />
        <ApiUnavailable error={error} what="el resumen de hoy" />
      </div>
    );
  }
  return <TodayView today={today} now={new Date()} {...data} />;
}

function bySlot(a: TripItem, b: TripItem) {
  return SLOT_ORDER.indexOf(a.slot) - SLOT_ORDER.indexOf(b.slot);
}

function when(item: TripItem) {
  return item.time ? item.time.slice(0, 5) : (SLOT[item.slot] ?? item.slot);
}

function Hero({ today, summary }: { today: string; summary: string }) {
  return (
    <header className="pt-4 sm:pt-8">
      <p className="eyebrow-wide">{fmtWeekday(today)}</p>
      <h1 className="type-mega mt-4">
        <span className="headline-muted block">Hoy en</span>
        Operación.
      </h1>
      <p className="mt-6 max-w-2xl font-body text-base text-muted-foreground">{summary}</p>
    </header>
  );
}

function SectionHead({ id, title, action }: { id: string; title: string; action?: { href: string; label: string } }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <h2 id={id} className="type-section leading-[0.95]">
        {title}
      </h2>
      {action && <PillLink href={action.href}>{action.label}</PillLink>}
    </div>
  );
}

function TodayView({
  today,
  now,
  details,
  approvals,
  pendingCount,
  red,
}: {
  today: string;
  now: Date;
  details: TripDetail[];
  approvals: Approval[];
  pendingCount: number;
  red: RedAccount[];
}) {
  const live = details.filter((t) => t.status === "in_progress");
  const upcoming = details
    .filter((t) => t.status === "confirmed" && daysBetween(today, t.start_date) >= 0)
    .sort((a, b) => a.start_date.localeCompare(b.start_date));
  const week = upcoming.filter((t) => daysBetween(today, t.start_date) <= 7);
  // One queue (UX review V1 P5): open items happening today or tomorrow on live trips, plus open
  // items on trips leaving within a week.
  const attention = details.flatMap((t) => {
    const day = t.status === "in_progress" ? tripDay(t, today) : undefined;
    const soon = t.status === "confirmed" && daysBetween(today, t.start_date) <= 7;
    return t.items
      .filter(isOpen)
      .filter((i) => (day !== undefined ? i.day >= day && i.day <= day + 1 : soon))
      .map((item) => ({ trip: t, item, when: day !== undefined ? (item.day === day ? "Hoy" : "Mañana") : "Antes de salir" }));
  });
  const unconfirmed = details.reduce((n, t) => n + t.items.filter(isOpen).length, 0);
  const travellers = live.reduce((n, t) => n + (t.team.group_size ?? 0), 0);

  const spotlight = red[0];
  // The approval about the red client, matched on its name ("Lakeshore University" → "Lakeshore").
  const key = spotlight?.name.split(" ")[0]?.toLowerCase();
  const related = key ? approvals.find((a) => a.title.toLowerCase().includes(key)) : undefined;

  const summary = [
    `${live.length} ${live.length === 1 ? "gira en curso" : "giras en curso"}`,
    `${attention.length + red.length} cosas para mirar`,
    `${pendingCount} ${pendingCount === 1 ? "decisión pendiente" : "decisiones pendientes"}`,
  ].join(" · ");

  return (
    <div className="space-y-14 pb-16">
      <Hero today={today} summary={`${summary}.`} />

      <KpiRow
        items={[
          { label: "Giras en curso", value: live.length, hint: `${travellers} viajeros en destino` },
          { label: "Salidas en 7 días", value: week.length, hint: week[0]?.team.organization ?? "sin salidas cercanas" },
          {
            label: "Aprobaciones pendientes",
            value: pendingCount,
            hint: `${unconfirmed} ítems sin confirmar`,
            tone: pendingCount ? "warning" : undefined,
          },
          {
            label: "Clientes en rojo",
            value: red.length,
            hint: spotlight?.name ?? "todos en verde o amarillo",
            tone: red.length ? "danger" : undefined,
          },
        ]}
      />

      {spotlight && (
        <RedSpotlight
          account={spotlight}
          more={red.length - 1}
          nextStep={related?.title ?? "Revisar las aprobaciones pendientes y el historial del cliente."}
          approvalHref={related ? `/ops/approvals?id=${related.id}` : "/ops/approvals"}
        />
      )}

      {live.map((trip) => {
        const day = tripDay(trip, today);
        const lastDay = Math.max(day, ...trip.items.map((i) => i.day));
        return (
          <section key={trip.id} aria-labelledby={`live-${trip.id}`} className="space-y-6">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div className="space-y-3">
                <Pill tone="live">
                  En curso · día {day} de {lastDay}
                </Pill>
                <h2 id={`live-${trip.id}`} className="type-hero">
                  {trip.team.organization ?? trip.title}
                </h2>
                <CountryTag name={trip.country} city={trip.city} />
              </div>
              <PillLink href={`/ops/trips/${trip.id}`}>Ver gira</PillLink>
            </div>
            <div className="rounded-lg border border-line bg-card">
              <DayStrip trip={trip} day={day} lastDay={lastDay} />
            </div>
            <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line md:grid-cols-2">
              {[
                { label: "Hoy", list: trip.items.filter((i) => i.day === day).sort(bySlot) },
                { label: "Mañana", list: trip.items.filter((i) => i.day === day + 1).sort(bySlot) },
              ].map(({ label, list }) => (
                <div key={label} className="bg-card p-6">
                  <p className="type-small-title mb-5">{label}</p>
                  <ul className="space-y-4">
                    {list.map((item) => (
                      <li key={item.id} className="flex gap-4">
                        <span className="w-16 shrink-0 pt-0.5 text-xs tabular-nums text-muted-foreground">
                          {when(item)}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">{item.title}</p>
                          <p className="text-xs text-muted-foreground">
                            {[
                              ITEM_KIND[item.kind] ?? item.kind,
                              ITEM_STATUS[item.status]?.label ?? item.status,
                              item.opponent?.level_score != null && `rival nivel ${item.opponent.level_score}`,
                              item.provider?.name,
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </p>
                          {item.alert && (
                            <p className="mt-1 flex items-start gap-1.5 text-xs font-semibold text-danger">
                              <span className="mt-1 size-1.5 shrink-0 rounded-full bg-danger" aria-hidden />
                              {item.alert}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                    {list.length === 0 && <li className="text-sm text-muted-foreground">Sin actividades.</li>}
                  </ul>
                </div>
              ))}
            </div>
          </section>
        );
      })}

      <div className="grid gap-14 xl:grid-cols-[minmax(0,1fr)_380px]">
        <div className="space-y-14">
          <section aria-labelledby="attention-title" data-tour="today-queue">
            <SectionHead id="attention-title" title={`Atención · ${red.length + attention.length}`} />
            {red.length + attention.length === 0 ? (
              <p className="border-y border-line py-5 text-sm text-muted-foreground">Nada urgente sin confirmar.</p>
            ) : (
              <ul className="divide-y divide-line border-y border-line">
                {red.map((a) => (
                  <li key={a.id}>
                    <Link
                      href={`/ops/accounts/${a.id}`}
                      className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-start gap-4 py-4 transition-colors hover:bg-foreground/5"
                    >
                      <span className="eyebrow pt-0.5 text-danger">Cliente</span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium">Cliente en rojo: {a.name}</p>
                        {a.reason && (
                          <p className="mt-1 text-xs text-muted-foreground">
                            <ReasonText reason={a.reason} />
                          </p>
                        )}
                      </div>
                      <Pill tone="danger">En rojo</Pill>
                    </Link>
                  </li>
                ))}
                {attention.map(({ trip, item, when: label }) => (
                  <li key={item.id}>
                    <Link
                      href={`/ops/trips/${trip.id}#${item.id}`}
                      className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-start gap-4 py-4 transition-colors hover:bg-foreground/5"
                    >
                      <span className="pt-0.5 text-xs tabular-nums text-muted-foreground">
                        <span className="block font-semibold text-foreground">{label}</span>
                        {item.time ? item.time.slice(0, 5) : `día ${item.day}`}
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{item.title}</p>
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {[trip.code, trip.team.organization, `día ${item.day}`, item.provider?.name]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                        {item.alert && <p className="mt-1 text-xs font-semibold text-danger">{item.alert}</p>}
                      </div>
                      <Pill tone={ITEM_STATUS[item.status]?.tone ?? "neutral"}>
                        {ITEM_STATUS[item.status]?.label ?? item.status}
                      </Pill>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="upcoming-title">
            <SectionHead id="upcoming-title" title="Próximas salidas" action={{ href: "/ops/trips", label: "Todas las giras" }} />
            <ul className="grid gap-3 md:grid-cols-2">
              {upcoming.map((trip) => {
                const active = trip.items.filter((i) => i.status !== "cancelled");
                const confirmed = active.filter((i) => i.status === "confirmed").length;
                const pct = active.length ? Math.round((confirmed / active.length) * 100) : 0;
                return (
                  <li key={trip.id}>
                    <Link
                      href={`/ops/trips/${trip.id}`}
                      className="block rounded-lg border border-line bg-card p-5 transition-colors hover:border-line-strong"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{trip.code}</span>
                        <span className="eyebrow">en {daysBetween(today, trip.start_date)} días</span>
                      </div>
                      <p className="type-card mt-3">{trip.team.organization ?? trip.title}</p>
                      <p className="mt-2 text-xs text-muted-foreground">
                        {trip.city} · {fmtRange(trip.start_date, trip.end_date)}
                      </p>
                      <div className="mt-4 flex items-center gap-2">
                        <Progress value={pct} label={`Confirmaciones ${trip.code ?? ""}`} className="flex-1" />
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {confirmed}/{active.length}
                        </span>
                      </div>
                    </Link>
                  </li>
                );
              })}
              {upcoming.length === 0 && <li className="text-sm text-muted-foreground">Sin salidas confirmadas.</li>}
            </ul>
          </section>
        </div>

        <aside aria-labelledby="approvals-title">
          <SectionHead id="approvals-title" title="Esperan tu decisión" action={{ href: "/ops/approvals", label: "Bandeja" }} />
          <ul className="divide-y divide-line border-y border-line">
            {approvals.map((a) => {
              const risk = RISK_CLASS[a.risk_class] ?? { label: a.risk_class, tone: "neutral" as const };
              return (
                <li key={a.id}>
                  <Link
                    href={`/ops/approvals?id=${a.id}`}
                    className="block py-4 transition-colors hover:bg-foreground/5"
                  >
                    <p className="text-sm font-medium">{a.title}</p>
                    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <Pill tone={risk.tone}>{risk.label}</Pill>
                      {a.expires_at && <span>vence {fmtRelative(a.expires_at, now)}</span>}
                    </p>
                  </Link>
                </li>
              );
            })}
            {approvals.length === 0 && (
              <li className="py-4 text-sm text-muted-foreground">No hay nada esperando tu decisión.</li>
            )}
          </ul>
        </aside>
      </div>
    </div>
  );
}
