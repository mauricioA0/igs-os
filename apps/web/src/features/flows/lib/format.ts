// Ops works from Buenos Aires: times are shown in that zone, always with an explicit timeZone so
// server and client render the same string (no hydration mismatch).
export const OPS_TIME_ZONE = "America/Argentina/Buenos_Aires";

const dateTime = new Intl.DateTimeFormat("es-AR", {
  timeZone: OPS_TIME_ZONE,
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dateTime.format(new Date(iso));
}

export function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
  const m = s / 60;
  if (m < 60) return `${Math.round(m)} min`;
  const h = m / 60;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} días`;
}

export function msBetween(start: string, end: string | null | undefined, now = Date.now()): number {
  return Math.max(0, (end ? Date.parse(end) : now) - Date.parse(start));
}
