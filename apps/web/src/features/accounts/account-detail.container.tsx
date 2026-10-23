import { ArrowLeft, ArrowRight, Sparkles } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import { cn } from "@/components/ui";
import { ApiUnavailable, Pill } from "@/features/ops-shell/bits";
import { fmtDate, fmtDateTime, fmtRange, fmtRelative } from "@/features/ops-shell/format";
import {
  ACCOUNT_KIND,
  ACCOUNT_STATUS,
  CHANNEL,
  country,
  FACT_KIND,
  ROLE,
  ROLE_ORDER,
  programLabel,
  SENTIMENT,
  TRIP_STATUS,
} from "@/features/ops-shell/labels";
import { listTrips, type TripSummary } from "@/features/trips/api";
import { type AccountDetail, type Brief, getAccount, getBrief, type InteractionSummary } from "./api";
import { AskAccount } from "./components/ask-account";
import { type CitationSource, CitationChip, CitedText } from "./components/citations";
import { HealthPill } from "./components/health-pill";
import { InteractionTimeline } from "./components/interaction-timeline";
import { ReasonText, SourceText } from "@/features/ops-shell/source-text";
import { splitLead } from "./brief-text";
import { AI_UNAVAILABLE_COPY, type AiUnavailable, aiUnavailable } from "./ai-errors";

const SUGGESTIONS = ["¿Quién decide la compra?", "¿Qué está bloqueando hoy?", "¿Cómo viene el pago?"];

export async function AccountDetailContainer({ id }: { id: string }) {
  await connection();
  let account: AccountDetail | null;
  try {
    account = await getAccount(id);
  } catch (error) {
    return <ApiUnavailable error={error} what="el cliente" />;
  }
  if (!account) notFound();

  const [briefResult, trips] = await Promise.all([
    getBrief(id),
    listTrips().catch(() => [] as TripSummary[]),
  ]);
  return (
    <AccountDetailView
      account={account}
      brief={"brief" in briefResult ? briefResult.brief : null}
      briefUnavailable={"error" in briefResult ? aiUnavailable(briefResult.error) : null}
      trips={trips.filter((t) => t.account_id === id)}
      now={new Date()}
    />
  );
}

function sourceOf(i: InteractionSummary, people: Map<string, string>): CitationSource {
  const who = i.stakeholder_id ? people.get(i.stakeholder_id) : undefined;
  return {
    n: 0,
    label: [CHANNEL[i.channel] ?? i.channel, fmtDate(i.occurred_at), who].filter(Boolean).join(" · "),
    interactionId: i.id,
    preview: previewOf(i),
  };
}

/** What a citation shows on hover: the quoted passage when the API sends it, else the subject. */
function previewOf(i: InteractionSummary): string | undefined {
  const excerpt = i.excerpt?.trim();
  if (excerpt) return i.subject ? `${i.subject} — ${excerpt}` : excerpt;
  return i.subject ?? undefined;
}

const FACT_ORDER = ["risk", "commitment", "decision", "budget", "preference", "status"];

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
}

function AccountDetailView({
  account,
  brief,
  briefUnavailable,
  trips,
  now,
}: {
  account: AccountDetail;
  brief: Brief | null;
  briefUnavailable: AiUnavailable | null;
  trips: TripSummary[];
  now: Date;
}) {
  const people = new Map(account.stakeholders.map((s) => [s.id, s.name]));
  const interactions = new Map(account.recent_interactions.map((i) => [i.id, i]));
  const previews = Object.fromEntries(account.recent_interactions.map((i) => [i.id, previewOf(i) ?? ""]));
  const healthKey = brief?.health ?? account.health;
  // Health is rule-based and comes with the account itself; the brief only refreshes it.
  const healthReasons = brief?.health_reasons ?? account.health_reasons ?? [];
  const stakeholders = [...account.stakeholders].sort(
    (a, b) => ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || b.influence - a.influence,
  );
  // The API has no account owner; the person who signs is who ops needs to keep warm.
  const decider = stakeholders.find((s) => s.role === "decision_maker") ?? stakeholders[0];
  const lastContact = [...account.recent_interactions].sort((a, b) => b.occurred_at.localeCompare(a.occurred_at))[0];

  return (
    <div className="space-y-16">
      <header className="space-y-8 border-b border-line pb-10" data-tour="account-health">
        <Link
          href="/ops/accounts"
          className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white/10 px-4 text-xs font-semibold text-foreground/70 transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" aria-hidden /> Clientes
        </Link>
        <div className="space-y-4">
          <p className="eyebrow-wide text-muted-foreground">
            {[ACCOUNT_KIND[account.kind] ?? account.kind, country(account.country).label].join(" · ")}
          </p>
          <h1 className="type-hero">{account.name}</h1>
          <p className="text-muted-foreground">
            {[
              [account.city, account.state].filter(Boolean).join(", "),
              account.sport_programs.map(programLabel).join(", "),
              `Cliente desde ${fmtDate(account.created_at)}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_auto]">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <HealthPill health={healthKey} size="lg" />
              <span className="inline-flex h-11 items-center rounded-full bg-white/10 px-5 text-xs font-semibold text-foreground/70">
                {ACCOUNT_STATUS[account.status] ?? account.status}
              </span>
            </div>
            {healthReasons.length > 0 && (
              <ul className="max-w-2xl space-y-1 text-foreground/80">
                {healthReasons.map((r) => (
                  <li key={r}>
                    <ReasonText reason={r} />
                  </li>
                ))}
              </ul>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-8 gap-y-1 self-end text-sm lg:text-right">
            <dt className="eyebrow text-xs">Decide</dt>
            <dt className="eyebrow text-xs">Último contacto</dt>
            <dd className="text-foreground">{decider ? decider.name : "—"}</dd>
            <dd className="text-foreground">
              {lastContact ? (
                <a href={`#i-${lastContact.id}`} className="hover:underline">
                  {fmtRelative(lastContact.occurred_at, now)} · {CHANNEL[lastContact.channel] ?? lastContact.channel}
                </a>
              ) : (
                "Sin contacto registrado"
              )}
            </dd>
          </dl>
        </div>
      </header>

      <BriefSection brief={brief} unavailable={briefUnavailable} previews={previews} now={now} />

      <section aria-labelledby="stakeholders">
        <h2 id="stakeholders" className="type-section mb-8">
          Stakeholders
        </h2>
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {stakeholders.map((s) => {
            const days = s.last_contact_at
              ? Math.round((now.getTime() - new Date(s.last_contact_at).getTime()) / 86_400_000)
              : undefined;
            const cold = (days === undefined || days > 21) && s.influence >= 4;
            const sentiment = SENTIMENT[s.sentiment] ?? SENTIMENT.unknown;
            return (
              <li key={s.id} className="flex flex-col gap-4 rounded-lg border border-line bg-card p-5">
                <div className="flex items-start gap-4">
                  <span
                    className="flex size-12 shrink-0 items-center justify-center rounded-full bg-raised font-semibold text-foreground"
                    aria-hidden
                  >
                    {initials(s.name)}
                  </span>
                  <div className="min-w-0">
                    <p className="eyebrow text-xs">{ROLE[s.role] ?? s.role}</p>
                    <p className="type-small-title mt-2 text-foreground">{s.name}</p>
                    {s.title && <p className="mt-1 text-sm text-muted-foreground">{s.title}</p>}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-2">
                    <span className="sr-only">{`Influencia ${s.influence} de 5`}</span>
                    <span aria-hidden>Influencia</span>
                    <span className="inline-flex gap-1" aria-hidden>
                      {[1, 2, 3, 4, 5].map((n) => (
                        <span
                          key={n}
                          className={cn("size-2 rounded-full", n <= s.influence ? "bg-foreground" : "bg-white/15")}
                        />
                      ))}
                    </span>
                  </span>
                  <Pill tone={sentiment.tone}>{sentiment.label}</Pill>
                </div>
                <p className="text-xs text-muted-foreground">
                  {s.preferred_channel && <>{CHANNEL[s.preferred_channel] ?? s.preferred_channel} · </>}
                  <span className={cn(cold && "font-semibold text-warning")}>
                    {s.last_contact_at
                      ? `Último contacto ${fmtRelative(s.last_contact_at, now)}`
                      : "Sin contacto registrado"}
                  </span>
                </p>
                {s.notes && (
                  <p className="border-t border-line pt-4 text-sm text-foreground/80">
                    <SourceText text={s.notes} />
                  </p>
                )}
              </li>
            );
          })}
        </ul>
        <p className="mt-4 text-xs text-muted-foreground">
          Solo adultos. Los cambios que sugiere el agente quedan como propuesta hasta que alguien los aprueba.
        </p>
      </section>

      <section aria-labelledby="facts">
        <h2 id="facts" className="type-section mb-8">
          Compromisos y riesgos
        </h2>
        {account.facts.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nada registrado.</p>
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {[...account.facts]
              .sort((a, b) => FACT_ORDER.indexOf(a.kind) - FACT_ORDER.indexOf(b.kind))
              .map((f, idx) => {
                const kind = FACT_KIND[f.kind] ?? { label: f.kind, tone: "neutral" as const };
                const src = interactions.get(f.source_interaction_id);
                return (
                  <li key={f.id} className="grid gap-3 py-5 sm:grid-cols-[8rem_minmax(0,1fr)_auto] sm:items-baseline">
                    <span>
                      <Pill tone={kind.tone}>{kind.label}</Pill>
                    </span>
                    <p className="text-foreground">
                      <SourceText text={f.statement} />
                    </p>
                    <span className="sm:text-right">
                      {src ? (
                        <CitationChip source={{ ...sourceOf(src, people), n: idx + 1 }} />
                      ) : (
                        <span className="text-xs text-muted-foreground">Fuente fuera de las últimas interacciones</span>
                      )}
                    </span>
                  </li>
                );
              })}
          </ul>
        )}
      </section>

      <AskAccount accountId={account.id} accountName={account.name} suggestions={SUGGESTIONS} previews={previews} />

      <InteractionTimeline
        entries={account.recent_interactions.map((i) => ({
          id: i.id,
          channel: i.channel,
          direction: i.direction,
          occurredAt: i.occurred_at,
          subject: i.subject,
          excerpt: i.excerpt,
          who: i.stakeholder_id ? people.get(i.stakeholder_id) : undefined,
        }))}
      />

      {trips.length > 0 && (
        <section aria-labelledby="related">
          <h2 id="related" className="type-section mb-8">
            Giras
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {trips.map((t) => {
              const status = TRIP_STATUS[t.status] ?? { label: t.status, tone: "neutral" as const };
              return (
                <li key={t.id}>
                  <Link
                    href={`/ops/trips/${t.id}`}
                    className="group flex h-full flex-col gap-3 rounded-lg border border-line bg-card p-5 transition-colors hover:border-line-strong hover:bg-raised"
                  >
                    {t.code && <p className="eyebrow text-xs">{t.code}</p>}
                    <p className="type-small-title text-foreground">{t.city}</p>
                    <p className="text-sm text-muted-foreground">{fmtRange(t.start_date, t.end_date)}</p>
                    <div className="mt-auto flex items-center justify-between pt-2">
                      <Pill tone={status.tone}>{status.label}</Pill>
                      <ArrowRight
                        className="size-4 text-foreground/50 transition-colors group-hover:text-foreground"
                        aria-hidden
                      />
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

function BriefSection({
  brief,
  unavailable,
  previews,
  now,
}: {
  brief: Brief | null;
  unavailable: AiUnavailable | null;
  previews: Record<string, string>;
  now: Date;
}) {
  const sources: CitationSource[] =
    brief?.citations.map((c) => ({
      n: c.n,
      label: c.label,
      interactionId: c.interaction_id,
      preview: c.interaction_id ? previews[c.interaction_id] : undefined,
    })) ?? [];
  const [lead, rest] = brief ? splitLead(brief.text) : ["", ""];
  return (
    <section aria-labelledby="brief" className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="brief" className="type-section flex items-center gap-3">
          <Sparkles className="size-6 text-muted-headline" aria-hidden /> Resumen
        </h2>
        {brief && (
          <p className="text-xs text-muted-foreground">
            Generado {fmtRelative(brief.generated_at, now)} ({fmtDateTime(brief.generated_at)}) ·{" "}
            {brief.citations.length} fuentes · se actualiza con cada interacción nueva
          </p>
        )}
      </div>
      {brief ? (
        <div className="max-w-5xl space-y-6">
          {/* A long first sentence at statement size takes over the page; drop to card size. */}
          <p className={lead.length > 140 ? "type-card text-foreground" : "type-statement text-foreground"}>
            <CitedText text={lead} sources={sources} />
          </p>
          {rest && (
            <p className="max-w-3xl text-lg leading-7 text-muted-foreground">
              <CitedText text={rest} sources={sources} />
            </p>
          )}
        </div>
      ) : (
        <p className="max-w-3xl text-lg leading-7 text-muted-foreground">
          El resumen con fuentes no está disponible ({AI_UNAVAILABLE_COPY[unavailable ?? "failed"].toLowerCase()}).
          Debajo están el estado, los stakeholders y los hechos registrados, que no dependen del modelo.
        </p>
      )}
    </section>
  );
}
