import { connection } from "next/server";
import { ApiUnavailable } from "@/features/ops-shell/bits";
import { getTrip, isOpen, listTrips, pricingOf, type TripDetail } from "./api";
import { type TripRow, TripsTable } from "./components/trips-table";

export async function TripsContainer() {
  await connection();
  let details: TripDetail[];
  try {
    const trips = await listTrips();
    details = (await Promise.all(trips.map((t) => getTrip(t.id)))).filter((t): t is TripDetail => t !== null);
  } catch (error) {
    return (
      <div className="space-y-8">
        <TripsHeader />
        <ApiUnavailable error={error} what="las giras" />
      </div>
    );
  }

  const rows: TripRow[] = details
    .map((t) => {
      const active = t.items.filter((i) => i.status !== "cancelled");
      const confirmed = active.filter((i) => i.status === "confirmed").length;
      return {
        id: t.id,
        code: t.code ?? t.id.slice(0, 8),
        team: t.team.organization ?? t.title,
        program: pricingOf(t).program,
        sport: t.team.sport,
        gender: t.team.gender,
        levelScore: t.team.level_score,
        city: t.city,
        country: t.country,
        startDate: t.start_date,
        endDate: t.end_date,
        travelers: t.team.group_size,
        status: t.status,
        confirmed,
        total: active.length,
        confirmedPct: active.length ? Math.round((confirmed / active.length) * 100) : 0,
        open: active.filter(isOpen).length,
      };
    })
    .sort((a, b) => a.startDate.localeCompare(b.startDate));

  return (
    <div className="space-y-8">
      <TripsHeader
        live={rows.filter((r) => r.status === "in_progress").length}
        open={rows.filter((r) => r.status === "confirmed" || r.status === "in_progress").reduce((n, r) => n + r.open, 0)}
      />
      <TripsTable rows={rows} />
    </div>
  );
}

function TripsHeader({ live, open }: { live?: number; open?: number }) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-6 border-b border-line pb-8">
      <div>
        <p className="eyebrow-wide text-muted-foreground">Operaciones</p>
        <h1 className="type-hero mt-4">Giras</h1>
        <p className="mt-4 max-w-xl text-sm text-muted-foreground">
          Cada gira con su estado y cuántos ítems faltan confirmar con proveedores.
        </p>
      </div>
      {live !== undefined && (
        <dl className="flex gap-10">
          <div>
            <dt className="eyebrow text-xs">En curso</dt>
            <dd className="kpi-number mt-2">{live}</dd>
          </div>
          <div>
            <dt className="eyebrow text-xs">Sin confirmar</dt>
            <dd className={`kpi-number mt-2 ${open ? "text-warning" : ""}`}>{open}</dd>
          </div>
        </dl>
      )}
    </header>
  );
}
