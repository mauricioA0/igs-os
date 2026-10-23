import { OPS_TIME_ZONE } from "./format";
import type { ExecutionStatus } from "./types";

export type DayRuns = { day: string; label: string; total: number; byStatus: Partial<Record<ExecutionStatus, number>> };

const dayKey = new Intl.DateTimeFormat("en-CA", { timeZone: OPS_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit" });
const dayLabel = new Intl.DateTimeFormat("es-AR", { timeZone: OPS_TIME_ZONE, weekday: "narrow" });

/** Executions per Buenos Aires calendar day for the last `days` days, oldest first. */
export function runsByDay(
  executions: { started_at: string; status: ExecutionStatus }[],
  now = Date.now(),
  days = 7,
): DayRuns[] {
  const out: DayRuns[] = [];
  const index = new Map<string, DayRuns>();
  for (let i = days - 1; i >= 0; i--) {
    const at = new Date(now - i * 86_400_000);
    const entry: DayRuns = { day: dayKey.format(at), label: dayLabel.format(at).toUpperCase(), total: 0, byStatus: {} };
    out.push(entry);
    index.set(entry.day, entry);
  }
  for (const e of executions) {
    const entry = index.get(dayKey.format(new Date(e.started_at)));
    if (!entry) continue;
    entry.total += 1;
    entry.byStatus[e.status] = (entry.byStatus[e.status] ?? 0) + 1;
  }
  return out;
}
