import { cn } from "./cn";

// Our own "IGS OS" mark (never the site's logo): a white tile with "OS" cut out, plus the wordmark.
export function BrandMark({ className, wordmark = true }: { className?: string; wordmark?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5 text-foreground", className)}>
      <span
        aria-hidden
        className="grid size-8 place-items-center rounded-md bg-foreground-strong font-display text-sm leading-none font-black tracking-tight text-background"
      >
        OS
      </span>
      {wordmark ? (
        <span className="font-display text-lg leading-none font-extrabold tracking-[0.02em] uppercase">IGS OS</span>
      ) : (
        <span className="sr-only">IGS OS</span>
      )}
    </span>
  );
}
