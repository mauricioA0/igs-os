import { cn } from "./cn";

export type Country = "Argentina" | "Brazil" | "Costa Rica" | "Spain" | "USA";

// Stripe colors echo each flag; the text label carries the meaning, color is decoration.
const stripes: Record<Country, string[]> = {
  Argentina: ["bg-argentina", "bg-white", "bg-argentina"],
  Brazil: ["bg-brazil-green", "bg-brazil-gold", "bg-brazil-green"],
  "Costa Rica": ["bg-costa-rica", "bg-usa-red", "bg-costa-rica"],
  Spain: ["bg-usa-red", "bg-spain", "bg-usa-red"],
  USA: ["bg-usa-red", "bg-white", "bg-usa-navy"],
};

export function CountryTag({ country, city, className }: { country: Country; city?: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-line bg-card px-2.5 py-0.5 text-xs font-medium",
        className,
      )}
    >
      <span aria-hidden className="flex h-3 w-1.5 flex-col overflow-hidden rounded-[1px] ring-1 ring-border">
        {stripes[country].map((c, i) => (
          <span key={i} className={cn("flex-1", c)} />
        ))}
      </span>
      {city ? `${city}, ${country}` : country}
    </span>
  );
}
