import { Fragment, useId } from "react";
import { cn } from "@/components/ui";

/** What a chip needs to describe its source without opening it. */
export type CitationSource = {
  n: number;
  /** "Email · 15 oct · Karen Liu", as returned by the API. */
  label: string;
  interactionId?: string | null;
  /** Short preview of the cited interaction: subject and, when available, the quoted excerpt. */
  preview?: string;
};

/**
 * A citation as a readable chip with a preview on hover/focus (UX review V1 P3): replaces "[4]",
 * which had no accessible name. Links to the interaction in the timeline when it's on the page.
 */
export function CitationChip({ source }: { source: CitationSource }) {
  const href = source.interactionId ? `#i-${source.interactionId}` : undefined;
  // WCAG 2.5.3: the accessible name is the visible text (from content); the longer
  // description ("Fuente 1: …") goes in aria-describedby.
  const descId = useId();
  const description = `Fuente ${source.n}${source.preview ? `: ${source.preview}` : ""}`;
  const chip = (
    <>
      <span className="tabular-nums text-muted-foreground">{source.n}</span>{" "}
      <span className="truncate font-medium">{source.label}</span>
    </>
  );
  const className =
    "inline-flex max-w-64 items-center gap-1 rounded-full bg-white/10 px-2 align-baseline font-body text-2xs font-semibold leading-5 tracking-normal text-foreground/80 transition-colors hover:bg-white/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
  return (
    <span className="group relative inline-block">
      {href ? (
        <a href={href} aria-describedby={descId} data-citation={source.n} className={className}>
          {chip}
        </a>
      ) : (
        // A button (not a focusable span) so the chip's visible text is its accessible name.
        <button type="button" aria-describedby={descId} data-citation={source.n} className={className}>
          {chip}
        </button>
      )}
      <span id={descId} className="sr-only">
        {description}
      </span>
      {source.preview && (
        <span
          aria-hidden
          role="tooltip"
          className="pointer-events-none absolute bottom-full left-0 z-20 mb-2 hidden w-72 rounded-lg border border-line bg-raised p-3 font-sans text-xs tracking-normal text-foreground shadow-lg group-focus-within:block group-hover:block"
        >
          <span className="block font-semibold">{source.label}</span>
          <span className="mt-0.5 block text-muted-foreground">{source.preview}</span>
        </span>
      )}
    </span>
  );
}

/** Renders model text where `[n]` markers become citation chips. Unknown markers stay as text. */
export function CitedText({ text, sources, className }: { text: string; sources: CitationSource[]; className?: string }) {
  const byN = new Map(sources.map((s) => [s.n, s]));
  const parts = text.split(/(\[\d+\])/g);
  return (
    <span className={cn(className)}>
      {parts.map((part, idx) => {
        const m = /^\[(\d+)\]$/.exec(part);
        const source = m ? byN.get(Number(m[1])) : undefined;
        if (!source) return <Fragment key={idx}>{part}</Fragment>;
        return (
          <Fragment key={idx}>
            {" "}
            <CitationChip source={source} />
          </Fragment>
        );
      })}
    </span>
  );
}
