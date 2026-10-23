import type { ReactNode } from "react";

/** Branded full-page message for error and not-found states (one look on every surface). */
export function ErrorScreen({
  lang,
  eyebrow,
  title,
  body,
  actions,
}: {
  lang: "es" | "en";
  eyebrow: string;
  title: string;
  body: string;
  actions: ReactNode;
}) {
  return (
    <main lang={lang} className="mx-auto flex min-h-[60dvh] w-full max-w-xl flex-1 flex-col justify-center px-6 py-16">
      <p className="eyebrow text-muted-foreground">{eyebrow}</p>
      <h1 className="display mt-3 text-4xl leading-none sm:text-5xl">{title}</h1>
      <p className="mt-4 text-base text-muted-foreground">{body}</p>
      <div className="mt-8 flex flex-wrap gap-3">{actions}</div>
    </main>
  );
}

export const linkClass =
  "inline-flex items-center rounded-md border border-border px-4 py-2 text-sm font-semibold hover:border-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
export const primaryClass =
  "inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
