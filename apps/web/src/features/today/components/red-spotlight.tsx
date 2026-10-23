import { ReasonText } from "@/features/ops-shell/source-text";

import { PillLink } from "./pill-link";

// The red client as the site's photo-backed card: CSS-only stadium art, never a real photo.
export function RedSpotlight({
  account,
  nextStep,
  approvalHref,
  more,
}: {
  account: { id: string; name: string; reason: string | undefined };
  nextStep: string;
  approvalHref: string;
  more: number;
}) {
  return (
    <section
      aria-labelledby="spotlight-title"
      className="stadium-art relative isolate overflow-hidden rounded-lg border border-line bg-card"
    >
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-linear-to-t from-background via-background/70 to-transparent"
      />
      <div className="flex min-h-80 flex-col justify-end gap-5 p-6 sm:p-10">
        <p className="eyebrow flex items-center gap-2 text-foreground">
          <span className="size-2 rounded-full bg-danger" aria-hidden />
          Cliente en rojo{more > 0 ? ` · +${more}` : ""}
        </p>
        <h2 id="spotlight-title" className="type-hero max-w-3xl">
          {account.name}
        </h2>
        {account.reason && (
          <p className="max-w-2xl text-base text-foreground/90">
            <ReasonText reason={account.reason} />
          </p>
        )}
        <div className="max-w-2xl border-l-2 border-line-strong pl-4">
          <p className="eyebrow">Próximo paso</p>
          <p className="mt-1 text-sm text-muted-foreground">{nextStep}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <PillLink href={`/ops/accounts/${account.id}`} variant="primary">
            Ver cliente
          </PillLink>
          <PillLink href={approvalHref}>Revisar aprobación</PillLink>
        </div>
      </div>
    </section>
  );
}
