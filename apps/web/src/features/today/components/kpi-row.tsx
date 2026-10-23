import { cn } from "@/components/ui";

export type KpiItem = { label: string; value: number; hint?: string; tone?: "danger" | "warning" };

export function KpiRow({ items }: { items: KpiItem[] }) {
  return (
    <section aria-label="Indicadores" className="grid grid-cols-2 border-y border-line lg:grid-cols-4">
      {items.map((k, i) => (
        <div
          key={k.label}
          className={cn(
            "px-1 py-6 sm:px-6",
            i % 2 === 1 && "border-l border-line pl-4",
            i >= 2 && "border-t border-line lg:border-t-0",
            i === 2 && "lg:border-l",
          )}
        >
          <p className="eyebrow">{k.label}</p>
          <p
            className={cn(
              "kpi-number mt-3",
              k.tone === "danger" && "text-danger",
              k.tone === "warning" && "text-warning",
            )}
          >
            {k.value}
          </p>
          {k.hint && <p className="mt-2 text-xs text-muted-foreground">{k.hint}</p>}
        </div>
      ))}
    </section>
  );
}
