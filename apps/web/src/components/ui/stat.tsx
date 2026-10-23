import type { ReactNode } from "react";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Card } from "./card";
import { cn } from "./cn";

// KPI tile: the number in Barlow Condensed 900 (.kpi-number). `delta` is a signed change shown with
// an arrow; `invert` for metrics where down is good (latency, cost). `valueClassName` resizes it.
export function Stat({
  label,
  value,
  hint,
  delta,
  invert = false,
  className,
  valueClassName,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  delta?: number;
  invert?: boolean;
  className?: string;
  valueClassName?: string;
}) {
  const good = delta === undefined ? undefined : invert ? delta < 0 : delta > 0;
  return (
    <Card className={cn("p-5", className)}>
      <p className="eyebrow">{label}</p>
      <p className={cn("kpi-number mt-3", valueClassName)}>{value}</p>
      {(hint || delta !== undefined) && (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          {delta !== undefined && (
            <span className={cn("inline-flex items-center font-semibold", good ? "text-success" : "text-danger")}>
              {delta >= 0 ? <ArrowUpRight className="size-3.5" aria-hidden /> : <ArrowDownRight className="size-3.5" aria-hidden />}
              {Math.abs(delta)}%
            </span>
          )}
          {hint}
        </p>
      )}
    </Card>
  );
}
