import { cn } from "@/components/ui";
import { HEALTH } from "@/features/ops-shell/labels";

const TONE: Record<string, { dot: string; pill: string }> = {
  red: { dot: "bg-danger", pill: "border-danger/40 bg-danger/15 text-danger" },
  amber: { dot: "bg-warning", pill: "border-warning/40 bg-warning/15 text-warning" },
  green: { dot: "bg-success", pill: "border-success/40 bg-success/15 text-success" },
};

export const HEALTH_DOT: Record<string, string> = { red: "bg-danger", amber: "bg-warning", green: "bg-success" };

/** Rule-based account health as a status pill; `data-health` is what the demo story asserts. */
export function HealthPill({ health, size = "md" }: { health: string; size?: "md" | "lg" }) {
  const tone = TONE[health] ?? { dot: "bg-muted-foreground", pill: "border-line bg-white/10 text-foreground" };
  return (
    <span
      data-health={health}
      className={cn(
        "inline-flex items-center gap-2 rounded-full border font-sans font-semibold",
        size === "lg" ? "h-11 px-5 text-sm uppercase tracking-wider" : "h-7 px-3 text-xs",
        tone.pill,
      )}
    >
      <span className={cn("rounded-full", size === "lg" ? "size-2.5" : "size-2", tone.dot)} aria-hidden />
      {HEALTH[health]?.label ?? health}
    </span>
  );
}
