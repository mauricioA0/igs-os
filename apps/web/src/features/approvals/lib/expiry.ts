// Expiry countdown in the destination's local time ("hora de Buenos Aires").

export const DEFAULT_TIMEZONE = "America/Argentina/Buenos_Aires";

const TZ_LABEL: Record<string, string> = {
  "America/Argentina/Buenos_Aires": "hora de Buenos Aires",
  "America/Sao_Paulo": "hora de Río de Janeiro",
  "America/Costa_Rica": "hora de San José",
  "Europe/Madrid": "hora de Madrid",
};

export function timezoneLabel(tz: string): string {
  return TZ_LABEL[tz] ?? tz;
}

export type ExpiryState =
  | { kind: "none" }
  | { kind: "expired"; at: Date }
  | { kind: "pending"; at: Date; remainingMs: number; urgent: boolean };

export function expiryState(expiresAt: string | null | undefined, now: Date): ExpiryState {
  if (!expiresAt) return { kind: "none" };
  const at = new Date(expiresAt);
  const remainingMs = at.getTime() - now.getTime();
  if (remainingMs <= 0) return { kind: "expired", at };
  return { kind: "pending", at, remainingMs, urgent: remainingMs < 2 * 60 * 60 * 1000 };
}

export function formatRemaining(ms: number): string {
  const minutes = Math.max(1, Math.floor(ms / 60_000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) {
    const rest = minutes % 60;
    return rest ? `${hours} h ${rest} min` : `${hours} h`;
  }
  return `${Math.floor(hours / 24)} días`;
}

// Fixed es-AR formatting with an explicit zone so server and client render the same string.
export function formatInZone(date: Date, tz: string): string {
  return new Intl.DateTimeFormat("es-AR", {
    timeZone: tz,
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}
