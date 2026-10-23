import { cn } from "./cn";

const sizes = { sm: "size-7 text-2xs", md: "size-9 text-xs", lg: "size-12 text-sm" };

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

// `kind="agent"` marks AI actors so people and agents are never confused in timelines.
export function Avatar({
  name,
  src,
  kind = "person",
  size = "md",
  className,
}: {
  name: string;
  src?: string;
  kind?: "person" | "agent";
  size?: keyof typeof sizes;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full font-semibold",
        kind === "agent" ? "bg-primary text-primary-foreground ring-2 ring-offset-1 ring-offset-background ring-ai" : "bg-muted text-foreground",
        sizes[size],
        className,
      )}
      title={kind === "agent" ? `${name} (AI agent)` : name}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- avatars may come from arbitrary hosts
        <img src={src} alt={name} className="size-full object-cover" />
      ) : (
        <>
          <span aria-hidden>{initials(name)}</span>
          <span className="sr-only">{kind === "agent" ? `${name} (AI agent)` : name}</span>
        </>
      )}
    </span>
  );
}
