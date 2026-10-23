import { cn } from "./cn";
import { statusEntry, type StatusDomain, type Tone } from "./badge";

const dot: Record<Tone, string> = {
  neutral: "bg-muted-foreground",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  brand: "bg-brand",
  ai: "bg-ai",
  solid: "bg-primary",
  live: "bg-success-fill",
};

// Compact status for dense tables and flow nodes. The label is always rendered (visually or for
// screen readers), so color is never the only signal.
export function StatusDot({
  status,
  domain,
  label,
  lang = "es",
  pulse,
  showLabel = true,
  className,
}: {
  status: string;
  domain?: StatusDomain;
  label?: string;
  lang?: "es" | "en";
  pulse?: boolean;
  showLabel?: boolean;
  className?: string;
}) {
  const entry = statusEntry(status, domain);
  const animate = pulse ?? entry.tone === "live";
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-sm", className)}>
      <span className="relative flex size-2">
        {animate && (
          <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", dot[entry.tone])} />
        )}
        <span className={cn("relative inline-flex size-2 rounded-full", dot[entry.tone])} />
      </span>
      <span className={cn(!showLabel && "sr-only")}>{label ?? entry[lang]}</span>
    </span>
  );
}
