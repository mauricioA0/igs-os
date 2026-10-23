import { ArrowLeft, Building2, ExternalLink } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { connection } from "next/server";
import { ApiUnavailable, CountryTag, Pill, Progress } from "@/features/ops-shell/bits";
import { fmtRange, todayIso, usd } from "@/features/ops-shell/format";
import { country, GENDER, SPORT, TRIP_STATUS } from "@/features/ops-shell/labels";
import { writeAccess } from "@/features/ops-shell/writes";
import { getTrip, isOpen, pricingOf, tripDay, type TripDetail } from "./api";
import { TripTimeline } from "./components/trip-timeline";

export async function TripDetailContainer({ id }: { id: string }) {
  await connection();
  let trip: TripDetail | null;
  let access: Awaited<ReturnType<typeof writeAccess>>;
  try {
    [trip, access] = await Promise.all([getTrip(id), writeAccess()]);
  } catch (error) {
    return <ApiUnavailable error={error} what="la gira" />;
  }
  if (!trip) notFound();
  return <TripDetailView trip={trip} today={todayIso()} readOnlyReason={access.canWrite ? undefined : access.reason} />;
}

function TripDetailView({ trip, today, readOnlyReason }: { trip: TripDetail; today: string; readOnlyReason?: string }) {
  const p = pricingOf(trip);
  const status = TRIP_STATUS[trip.status] ?? { label: trip.status, tone: "neutral" as const };
  const day = trip.status === "in_progress" ? tripDay(trip, today) : undefined;
  const active = trip.items.filter((i) => i.status !== "cancelled");
  const confirmed = active.filter((i) => i.status === "confirmed").length;
  const pct = active.length ? Math.round((confirmed / active.length) * 100) : 0;
  const open = active.filter(isOpen);
  const team = trip.team;
  const c = country(trip.country);
  const days = Math.max(1, ...trip.items.map((i) => i.day));
  const matches = active.filter((i) => i.kind === "match").length;

  // Providers and activity come from the items themselves: no extra round trip.
  const providers = [
    ...active
      .filter((i) => i.provider)
      .reduce((m, i) => {
        const key = i.provider!.id ?? i.provider!.name;
        const prev = m.get(key) ?? { name: i.provider!.name, kind: i.provider!.kind, total: 0, open: 0 };
        prev.total += 1;
        if (isOpen(i)) prev.open += 1;
        return m.set(key, prev);
      }, new Map<string, { name: string; kind?: string | null; total: number; open: number }>())
      .values(),
  ].sort((a, b) => b.open - a.open || b.total - a.total);
  const activity = trip.items
    .flatMap((i) =>
      (
        [
          [i.completed_at, "realizado"],
          [i.confirmed_at, "confirmado"],
          [i.requested_at, "solicitado"],
        ] as const
      )
        .filter(([at]) => at)
        .map(([at, what]) => ({ id: `${i.id}-${what}`, at: at as string, what, item: i })),
    )
    .sort((a, b) => b.at.localeCompare(a.at))
    .slice(0, 5);

  const kpis = [
    { k: "Días", v: days },
    { k: "Viajeros", v: team.group_size ?? "—" },
    { k: "Partidos", v: matches },
    { k: "Confirmado", v: `${pct}%` },
  ];

  return (
    <div className="space-y-10">
      <Link href="/ops/trips" className="inline-flex items-center gap-1.5 text-xs font-semibold text-foreground/70 hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden /> Giras
      </Link>

      <header className="stadium-art relative isolate overflow-hidden rounded-lg border border-line">
        <div aria-hidden className={`absolute inset-0 -z-10 bg-linear-to-r ${c.strip} to-transparent opacity-40`} />
        <div aria-hidden className="absolute inset-0 -z-10 bg-linear-to-t from-background via-background/60 to-transparent" />
        <div className="px-6 pb-8 pt-10 sm:px-10 sm:pt-16">
          <div className="flex flex-wrap items-center gap-2">
            <Pill tone={status.tone} className="rounded-full px-2.5">
              {day ? `${status.label} · día ${day}` : status.label}
            </Pill>
            {p.activeFlow && <Pill className="rounded-full px-2.5">Flow: {p.activeFlow}</Pill>}
          </div>
          <p className="eyebrow-wide mt-6 text-foreground">
            {[trip.code, trip.city].filter(Boolean).join(" · ").toUpperCase()}
          </p>
          <h1 className="type-hero mt-4 max-w-4xl">{team.organization ?? trip.title}</h1>
          <p className="mt-4 text-sm text-muted-foreground">
            {[
              p.program,
              team.sport && `${SPORT[team.sport] ?? team.sport} ${team.gender ? (GENDER[team.gender] ?? "") : ""}`.trim(),
              team.age_group,
              team.level_score != null && `nivel ${team.level_score}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <CountryTag name={trip.country} city={trip.city} />
            <span className="tabular-nums text-muted-foreground">{fmtRange(trip.start_date, trip.end_date)}</span>
          </p>
          <div className="mt-8 flex flex-wrap gap-2">
            <Link
              href={`/proposal/${trip.id}`}
              className="inline-flex h-10 items-center gap-2 rounded-full bg-foreground px-5 text-xs font-semibold text-background transition-colors hover:bg-foreground/85"
            >
              Ver propuesta <ExternalLink className="size-4" aria-hidden />
            </Link>
            {trip.account_id && (
              <Link
                href={`/ops/accounts/${trip.account_id}`}
                className="inline-flex h-10 items-center gap-2 rounded-full bg-foreground/10 px-5 text-xs font-semibold text-foreground/70 transition-colors hover:text-foreground"
              >
                <Building2 className="size-4" aria-hidden /> Ficha del cliente →
              </Link>
            )}
          </div>
        </div>
        <dl className="grid grid-cols-2 border-t border-line bg-background/70 backdrop-blur sm:grid-cols-4">
          {kpis.map(({ k, v }, n) => (
            <div key={k} className={`px-6 py-5 sm:px-10 ${n % 2 ? "border-l border-line" : ""} ${n >= 2 ? "border-t border-line sm:border-t-0 sm:border-l" : ""}`}>
              <dt className="eyebrow text-xs">{k}</dt>
              <dd className="kpi-number mt-2 tabular-nums">{v}</dd>
            </div>
          ))}
        </dl>
      </header>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-10 xl:grid-cols-[minmax(0,1fr)_340px]">
        <TripTimeline
          tripId={trip.id}
          items={trip.items}
          startDate={trip.start_date}
          currentDay={day}
          teamLevel={trip.team.level_score}
          readOnlyReason={readOnlyReason}
        />

        <aside className="space-y-4">
          <SideCard id="trip-status" title="Estado">
            <dl className="space-y-3 text-sm">
              <Row k="Gira">
                <Pill tone={status.tone} className="rounded-full px-2.5">
                  {status.label}
                </Pill>
              </Row>
              <Row k="Precio p/p">{usd(trip.price_per_person_usd)}</Row>
              <Row k="Pagado">
                {p.paidUsd !== undefined
                  ? `${p.depositPaidPct ?? "—"}% · ${usd(p.paidUsd)}${p.totalUsd ? ` de ${usd(p.totalUsd)}` : ""}`
                  : "—"}
              </Row>
            </dl>
            {trip.summary && <p className="mt-4 border-t border-line pt-4 text-sm text-muted-foreground">{trip.summary}</p>}
          </SideCard>

          <SideCard id="confirmations" title="Aprobaciones y confirmaciones">
            <div className="flex items-center gap-3">
              <Progress value={pct} label="Ítems confirmados" className="flex-1 bg-foreground/10" />
              <span className="text-sm tabular-nums">
                {confirmed}/{active.length}
              </span>
            </div>
            {open.length > 0 ? (
              <ul className="mt-4 space-y-2 text-sm">
                {open.slice(0, 6).map((i) => (
                  <li key={i.id}>
                    <a href={`#${i.id}`} className="flex gap-2 hover:underline">
                      <span className="w-7 shrink-0 font-display font-extrabold tabular-nums">D{i.day}</span>
                      <span className="min-w-0 truncate">{i.title}</span>
                    </a>
                  </li>
                ))}
                {open.length > 6 && <li className="text-xs text-muted-foreground">y {open.length - 6} más</li>}
              </ul>
            ) : (
              <p className="mt-4 text-sm text-muted-foreground">Todo confirmado.</p>
            )}
            <Link
              href="/ops/approvals"
              className="mt-4 inline-flex h-8 items-center rounded-full bg-foreground/10 px-4 text-xs font-semibold text-foreground/70 hover:text-foreground"
            >
              Bandeja de aprobaciones →
            </Link>
          </SideCard>

          <SideCard id="trip-coach" title="Coach">
            <p className="type-small-title">{team.coach_name ?? "Sin asignar"}</p>
            <p className="mt-3 text-xs text-muted-foreground">
              {[team.organization, team.group_size != null && `${team.group_size} viajeros`].filter(Boolean).join(" · ")}
            </p>
          </SideCard>

          {providers.length > 0 && (
            <SideCard id="trip-providers" title="Proveedores">
              <ul className="divide-y divide-line text-sm">
                {providers.slice(0, 6).map((pr) => (
                  <li key={pr.name} className="flex items-center justify-between gap-3 py-2 first:pt-0 last:pb-0">
                    <span className="min-w-0 truncate">{pr.name}</span>
                    {pr.open > 0 ? (
                      <Pill tone="warning" className="rounded-full px-2.5">
                        {pr.open} abiertos
                      </Pill>
                    ) : (
                      <span className="text-xs tabular-nums text-muted-foreground">{pr.total} ítems</span>
                    )}
                  </li>
                ))}
              </ul>
            </SideCard>
          )}

          {activity.length > 0 && (
            <SideCard id="trip-activity" title="Actividad">
              <ol className="space-y-3 text-sm">
                {activity.map((a) => (
                  <li key={a.id} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3">
                    <span aria-hidden className="mt-1.5 size-1.5 rounded-full bg-foreground/40" />
                    <p className="min-w-0">
                      <a href={`#${a.item.id}`} className="hover:underline">
                        {a.item.title}
                      </a>{" "}
                      <span className="text-muted-foreground">{a.what}</span>
                      <span className="block text-xs text-muted-foreground tabular-nums">{a.at.slice(0, 10)}</span>
                    </p>
                  </li>
                ))}
              </ol>
            </SideCard>
          )}
        </aside>
      </div>
    </div>
  );
}

function SideCard({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="rounded-lg border border-line bg-card p-5">
      <h2 id={id} className="type-small-title mb-4">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right tabular-nums">{children}</dd>
    </div>
  );
}
