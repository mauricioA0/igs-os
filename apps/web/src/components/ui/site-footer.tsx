import Link from "next/link";
import type { ReactNode } from "react";
import { BrandMark } from "./brand-mark";
import { cn } from "./cn";

export type FooterColumn = { title: string; links: { label: string; href: string }[] };

const DEFAULT_MARQUEE = ["Global sports experiences", "Train. Compete. Experience.", "Argentina · Brazil · World Cup", "Built for teams"];

// The site's footer: #262626, brand + link columns, a condensed uppercase marquee between hairlines,
// then the legal row.
export function SiteFooter({
  columns,
  marquee = DEFAULT_MARQUEE,
  brand = <BrandMark />,
  note,
  cta,
  legal,
  className,
}: {
  columns: FooterColumn[];
  marquee?: string[];
  brand?: ReactNode;
  note?: ReactNode;
  /** E.g. a secondary `ButtonLink withArrow`. */
  cta?: ReactNode;
  /** Bottom row content (copyright, terms). */
  legal?: ReactNode;
  className?: string;
}) {
  const strip = (hidden: boolean) => (
    <span aria-hidden={hidden || undefined} className="flex items-center">
      {marquee.map((phrase, i) => (
        <span key={i} className="flex items-center">
          <span className="px-12">{phrase}</span>
          <span aria-hidden className="text-muted-headline">
            /
          </span>
        </span>
      ))}
    </span>
  );
  return (
    <footer className={cn("bg-raised text-foreground", className)}>
      <div className="mx-auto max-w-7xl px-6 pt-16 pb-10 md:px-28 md:pt-24">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-6">
            {brand}
            {note && <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">{note}</p>}
            {cta}
          </div>
          {columns.map((col) => (
            <nav key={col.title} aria-label={col.title}>
              <p className="font-display text-sm font-extrabold tracking-[0.04em] uppercase">{col.title}</p>
              <ul className="mt-5 space-y-3 text-[0.8125rem]">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link href={l.href} className="text-muted-foreground transition-colors hover:text-foreground">
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="marquee mt-16 border-y border-line py-6 text-lg text-nav-idle">
          <div>
            {strip(false)}
            {strip(true)}
          </div>
        </div>
        {legal && (
          <div className="mt-10 flex flex-col gap-3 text-[0.8125rem] text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            {legal}
          </div>
        )}
      </div>
    </footer>
  );
}
