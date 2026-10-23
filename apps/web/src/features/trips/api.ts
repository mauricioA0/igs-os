// Server-side reads for trips. Containers call these; presentational components get plain props.
import { unwrap } from "@/lib/api/client";
import { toApiError } from "@/lib/api/errors";
import { serverApi } from "@/lib/api/server";
import type { components } from "@/lib/api/schema";

export type TripSummary = components["schemas"]["TripSummary"];
// Richer item fields from wave 4 (`time`, `alert`, opponent and provider). Optional until the
// regenerated API types include them, so older API versions still render.
export type TripItem = components["schemas"]["TripItem"] & {
  time?: string | null;
  alert?: string | null;
  opponent?: { id?: string; name: string; level_score?: number | null } | null;
  provider?: { id?: string; name: string; kind?: string | null } | null;
};

export async function listTrips(): Promise<TripSummary[]> {
  const page = await unwrap(serverApi().GET("/v1/trips", { params: { query: { limit: 100 } } }));
  return page.items;
}

export type TripDetail = Omit<components["schemas"]["TripDetail"], "items"> & { items: TripItem[] };

export async function getTrip(id: string): Promise<TripDetail | null> {
  const { data, error, response } = await serverApi().GET("/v1/trips/{trip_id}", {
    params: { path: { trip_id: id } },
  });
  if (response.status === 404 || response.status === 422) return null; // unknown or malformed id
  if (!data) throw toApiError(error, response);
  return data;
}

/** Snapshot fields the seed stores on `trips.pricing` (team label, payments). */
export function pricingOf(trip: TripDetail) {
  const p = (trip.pricing ?? {}) as Record<string, unknown>;
  const team = (p.team ?? {}) as Record<string, unknown>;
  return {
    program: typeof team.program === "string" ? team.program : undefined,
    totalUsd: typeof p.total_usd === "number" ? p.total_usd : undefined,
    paidUsd: typeof p.paid_usd === "number" ? p.paid_usd : undefined,
    depositPaidPct: typeof p.deposit_paid_pct === "number" ? p.deposit_paid_pct : undefined,
    activeFlow: typeof p.active_flow === "string" ? p.active_flow : undefined,
  };
}

export function isOpen(item: TripItem) {
  return item.status === "pending" || item.status === "requested";
}

export function tripDay(trip: { start_date: string }, today: string) {
  const ms = new Date(`${today}T00:00:00Z`).getTime() - new Date(`${trip.start_date}T00:00:00Z`).getTime();
  return Math.round(ms / 86_400_000) + 1;
}
