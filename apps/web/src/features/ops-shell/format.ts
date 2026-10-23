// Deterministic formatting for the ops panel (es-AR conventions).
//
// Hand-rolled on purpose: `Intl` output differs between Node's ICU and each browser (month
// abbreviations with or without a dot, narrow no-break spaces, "a. m." vs "a.m."), and those
// differences were the source of the hydration mismatch on the account page. These helpers give
// the same string on the server and in the browser.

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MONTHS_LONG = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
];
const WEEKDAYS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

const DAY_MS = 86_400_000;

// Ops works on Buenos Aires time (UTC-3, no DST since 2009).
export const OPS_UTC_OFFSET_HOURS = -3;

/** UTC midnight of a `YYYY-MM-DD` (or the date part of an ISO datetime). */
function dateOnly(iso: string): Date {
  return new Date(`${iso.slice(0, 10)}T00:00:00Z`);
}

/** Wall-clock parts of an instant at a fixed UTC offset. */
function at(instant: string | Date, offsetHours = OPS_UTC_OFFSET_HOURS): Date {
  const t = typeof instant === "string" ? new Date(instant).getTime() : instant.getTime();
  return new Date(t + offsetHours * 3_600_000);
}

/** Today's date (`YYYY-MM-DD`) in Buenos Aires. */
export function todayIso(now: Date = new Date()): string {
  return at(now).toISOString().slice(0, 10);
}

export function daysBetween(from: string, to: string): number {
  return Math.round((dateOnly(to).getTime() - dateOnly(from).getTime()) / DAY_MS);
}

export function addDays(iso: string, days: number): string {
  return new Date(dateOnly(iso).getTime() + days * DAY_MS).toISOString().slice(0, 10);
}

/** "22 oct" */
export function fmtDate(iso: string): string {
  const d = dateOnly(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** "22 oct 2026" */
export function fmtDateYear(iso: string): string {
  const d = dateOnly(iso);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "18 oct – 27 oct" */
export function fmtRange(start: string, end: string): string {
  return `${fmtDate(start)} – ${fmtDate(end)}`;
}

/** "Jueves 22 de octubre" */
export function fmtWeekday(iso: string): string {
  const d = dateOnly(iso);
  const s = `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} de ${MONTHS_LONG[d.getUTCMonth()]}`;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "10:30" at Buenos Aires time. */
export function fmtTime(instant: string): string {
  const d = at(instant);
  return `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

/** "15 oct · 10:30" at Buenos Aires time. */
export function fmtDateTime(instant: string): string {
  const d = at(instant);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} · ${fmtTime(instant)}`;
}

/** "hace 2 h", "hace 3 días", "en 46 h". `now` is passed in so callers decide where it's read. */
export function fmtRelative(instant: string, now: Date): string {
  const diffMin = Math.round((new Date(instant).getTime() - now.getTime()) / 60_000);
  const abs = Math.abs(diffMin);
  const value =
    abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} días`;
  return diffMin < 0 ? `hace ${value}` : `en ${value}`;
}

/** "US$ 72.540" — prefixed so it never reads as pesos (content-and-accessibility.md). */
export function usd(amount: number): string {
  const rounded = Math.round(amount);
  const digits = Math.abs(rounded)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${rounded < 0 ? "−" : ""}US$ ${digits}`;
}
