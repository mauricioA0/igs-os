import { cn } from "@/components/ui";
import { addDays, fmtDate } from "@/features/ops-shell/format";
import { country } from "@/features/ops-shell/labels";
import { isOpen, type TripDetail } from "@/features/trips/api";

// "La Tira" (docs/reviews/ux/v5-visual-system.md): the whole trip as one row of days, a country
// accent line on top, today marked like a scoreboard, one dot per alert or open item.
export function DayStrip({ trip, day, lastDay }: { trip: TripDetail; day: number; lastDay: number }) {
  const days = Array.from({ length: lastDay }, (_, i) => i + 1);
  return (
    <div className="relative overflow-x-auto">
      <div className={cn("h-0.5 min-w-max", country(trip.country).dot)} aria-hidden />
      <ol className="flex min-w-max" aria-label={`Días de la gira, hoy es el día ${day} de ${lastDay}`}>
        {days.map((d) => {
          const items = trip.items.filter((i) => i.day === d);
          const alerts = items.filter((i) => i.alert).length;
          const open = items.filter(isOpen).length;
          const current = d === day;
          return (
            <li
              key={d}
              aria-current={current ? "date" : undefined}
              className={cn(
                "flex w-24 shrink-0 flex-col gap-1 border-r border-line px-3 py-3 last:border-r-0",
                current && "bg-foreground text-background",
              )}
            >
              <span
                className={cn(
                  "font-display text-2xl leading-none font-black tabular-nums uppercase",
                  d < day && "text-muted-foreground",
                )}
              >
                {current ? `Día ${d}/${lastDay}` : d}
              </span>
              <span className={cn("text-xs", current ? "text-background/70" : "text-muted-foreground")}>
                {fmtDate(addDays(trip.start_date, d - 1))}
              </span>
              <span
                className={cn("flex h-2 gap-1", d < day && "opacity-50")}
                role="img"
                aria-label={`${alerts} alertas, ${open} sin confirmar`}
              >
                {Array.from({ length: alerts }, (_, i) => (
                  <span key={`a${i}`} className="size-1.5 rounded-full bg-danger" />
                ))}
                {Array.from({ length: open }, (_, i) => (
                  <span key={`o${i}`} className="size-1.5 rounded-full bg-warning" />
                ))}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
