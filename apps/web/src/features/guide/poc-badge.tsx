import { cn } from "@/components/ui/cn";

/** Persistent header badge: this is a proof of concept running on fictional data. */
export function PocBadge({ label = "POC · datos ficticios", className }: { label?: string; className?: string }) {
  return (
    <span
      title={label}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border border-line bg-white/5 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wide text-foreground/80",
        className,
      )}
    >
      <span aria-hidden className="size-1.5 rounded-full bg-warning" />
      {/* Phones show just "POC"; the full label stays available as the accessible name. */}
      <span aria-hidden className="sm:hidden">POC</span>
      <span className="sr-only sm:not-sr-only">{label}</span>
    </span>
  );
}
