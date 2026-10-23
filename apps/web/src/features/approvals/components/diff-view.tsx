import { cn } from "@/components/ui";
import type { DiffLine } from "../lib/diff";

// Presentational: a unified diff with +/- markers that don't rely on color alone.
export function DiffView({ lines, label }: { lines: DiffLine[]; label: string }) {
  return (
    <figure className="overflow-hidden rounded-lg border border-line bg-background">
      <figcaption className="eyebrow border-b border-line bg-raised px-4 py-2 text-[11px] text-muted-foreground">{label}</figcaption>
      <pre className="max-h-72 overflow-auto px-4 py-3 font-mono text-xs leading-5">
        {lines.map((l, i) => (
          <div
            key={i}
            className={cn(
              "whitespace-pre-wrap",
              l.kind === "added" && "bg-success/10 text-success",
              l.kind === "removed" && "bg-danger/10 text-danger line-through decoration-danger/50",
            )}
          >
            <span aria-hidden className="mr-2 select-none">
              {l.kind === "added" ? "+" : l.kind === "removed" ? "−" : " "}
            </span>
            <span className="sr-only">{l.kind === "added" ? "Agregado: " : l.kind === "removed" ? "Quitado: " : ""}</span>
            {l.text || " "}
          </div>
        ))}
      </pre>
    </figure>
  );
}
