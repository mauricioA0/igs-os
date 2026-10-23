// Coach-facing proposal (presentational, server-rendered). One package price per person —
// never cost lines or margin (reviews/ux/v3-coach.md P1) — and one clear path to "Reserve".
import "./print.css";
import { formatDate, usd, type Proposal, type ProposalItem, type ProposalOpponent } from "../api";
import { SiteFooter } from "../site-chrome";
import { PrintButton, ReserveForm, StickyReserveBar } from "./reserve";

const SLOT_LABEL = { morning: "AM", afternoon: "PM", evening: "Eve" } as const;

export function ProposalView({ p }: { p: Proposal }) {
  const dates = `${formatDate(p.start_date)} – ${formatDate(p.end_date, { month: "short", day: "numeric", year: "numeric" })}`;
  const items = p.itinerary.flatMap((d) => d.items);
  const matches = items.filter((i) => i.kind === "match").length;
  const experiences = items.filter((i) => i.kind === "experience").length;
  const travelers = p.travelers ?? 0;
  const enrollmentTotal = p.enrollment_fee_usd * Math.max(travelers, 1);
  return (
    <article className="proposal-root bg-background text-foreground">
      <Hero p={p} dates={dates} matches={matches} />
      <TrustStrip />
      <Section id="overview" kicker="The tour" title={<><span className="headline-muted">Built for teams.</span> Designed for growth.</>}>
        <p className="copy-long max-w-3xl">{overview(p, matches, experiences)}</p>
        <dl className="mt-10 grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-line bg-white/10 sm:grid-cols-4">
          <Fact k="Dates" v={dates} />
          <Fact k="Travelers" v={travelers ? String(travelers) : "TBC"} />
          <Fact k="Matches" v={String(matches)} />
          <Fact k="Experiences" v={String(experiences)} />
        </dl>
      </Section>
      {p.opponents.length > 0 && (
        <Section id="opponents" kicker="Competition" title={<><span className="headline-muted">Real sport.</span> Real opponents.</>}>
          <ul className="grid gap-4 md:grid-cols-3">
            {p.opponents.map((o) => (
              <OpponentCard key={o.name} o={o} teamLevel={p.level_score} />
            ))}
          </ul>
        </Section>
      )}
      <Section id="itinerary" kicker={`${p.days} days`} title="Day by day" className="proposal-itinerary-wrap">
        <ol className="proposal-itinerary grid gap-3 md:grid-cols-2">
          {p.itinerary.map((d) => (
            <li key={d.day} className="proposal-day flex gap-5 rounded-lg border border-line bg-card p-5">
              <p className="w-14 shrink-0 text-center">
                <span className="block text-[0.6875rem] font-semibold uppercase tracking-[0.2em] text-muted-foreground">Day</span>
                <span className="kpi-number block text-5xl">{String(d.day).padStart(2, "0")}</span>
              </p>
              <div className="min-w-0 flex-1">
              <p className="eyebrow text-xs">
                {formatDate(d.date, { weekday: "long", month: "short", day: "numeric" })}
              </p>
              <ul className="mt-3 space-y-2 text-sm leading-5">
                {d.items.length === 0 && <li className="text-muted-foreground">Free time</li>}
                {d.items.map((item, i) => (
                  <ItineraryLine key={i} item={item} />
                ))}
              </ul>
              </div>
            </li>
          ))}
        </ol>
      </Section>
      <Section id="included" kicker="All set" title="What's included">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="proposal-card rounded-lg border border-line bg-card p-6">
            <p className="type-small-title">Included</p>
            <List items={p.included} mark="✓" />
          </div>
          <div className="proposal-card rounded-lg border border-line p-6">
            <p className="type-small-title text-muted-headline">Not included</p>
            <List items={p.not_included} mark="–" muted />
          </div>
        </div>
      </Section>
      <Section id="reserve" kicker="Enrollment" title={<><span className="headline-muted">One price.</span> Everything on the ground.</>} className="proposal-investment">
        <div className="grid grid-cols-[minmax(0,1fr)] gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
          <div className="proposal-card stadium-art relative overflow-hidden rounded-lg border border-line p-6 sm:p-8">
            <div className="relative z-10">
            <p className="eyebrow text-xs">Per person</p>
            <p className="kpi-number mt-3 text-7xl">{usd(p.price_per_person_usd)}</p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              All-inclusive on the ground, flights excluded. Coach spots: 1 free for every 15
              players.
            </p>
            <dl className="mt-6 space-y-3 border-t border-line pt-5 text-sm">
              <Row k="Enrollment fee (non-refundable)" v={`${usd(p.enrollment_fee_usd)} per traveler`} />
              <Row
                k="Payment plan"
                v={`${usd(p.installment_usd)} at ${p.first_installment_due_days} and ${p.second_installment_due_days} days after enrollment`}
              />
              <Row k="Final balance due" v={formatDate(p.balance_due, { month: "long", day: "numeric", year: "numeric" })} />
              <Row k="Proposal valid until" v={formatDate(p.valid_until, { month: "long", day: "numeric", year: "numeric" })} />
            </dl>
            </div>
          </div>
          <div className="no-print space-y-4">
            <ol className="grid gap-3 text-sm sm:grid-cols-3">
              {[
                ["1", "Reserve", "Tell us you're in. No charge yet."],
                ["2", "We confirm", "Availability, rooms and opponents within one business day."],
                ["3", "Enroll", `${usd(p.enrollment_fee_usd)} per traveler locks hotel and matches.`],
              ].map(([n, t, d]) => (
                <li key={n} className="rounded-lg border border-line bg-card p-4">
                  <p className="kpi-number text-4xl text-muted-headline">0{n}</p>
                  <p className="type-small-title mt-3">{t}</p>
                  <p className="mt-2 leading-5 text-muted-foreground">{d}</p>
                </li>
              ))}
            </ol>
            <ReserveForm proposalRef={p.ref} enrollmentFee={p.enrollment_fee_usd} enrollmentTotal={enrollmentTotal} alreadyRequested={p.enrollment_requested} />
          </div>
        </div>
      </Section>
      <SiteFooter />
      <StickyReserveBar
        pricePerPerson={usd(p.price_per_person_usd)}
        validUntil={formatDate(p.valid_until)}
      />
    </article>
  );
}

function Hero({ p, dates, matches }: { p: Proposal; dates: string; matches: number }) {
  return (
    <header data-tour="proposal-hero" className="proposal-hero relative isolate overflow-hidden px-6 pb-16 pt-14 sm:px-8 sm:pb-24 sm:pt-24 lg:min-h-[78vh]">
      <div aria-hidden className="stadium-art absolute inset-0 -z-10" />
      <div aria-hidden className="stadium-streaks absolute inset-0 -z-10" />
      <div className="site-container flex h-full flex-col justify-end">
        <p className="eyebrow-wide text-white">Tour proposal · {p.ref.toUpperCase().replace(/^T-/, "IGS-")}</p>
        <h1 className="type-mega mt-6">
          <span className="headline-muted">{p.days} days in</span>
          <br />
          {p.city}.
        </h1>
        <p className="type-card mt-8">
          {p.team}
          {p.program ? ` · ${p.program}` : ""}
        </p>
        <p className="mt-3 text-base text-muted-foreground">
          {dates} · {p.travelers ?? "TBC"} travelers · {matches} matches
        </p>
        <div className="mt-10 flex flex-wrap items-center gap-3">
          <a href="#reserve" className="no-print pill pill-lg pill-primary pill-arrow">
            Reserve your spot
          </a>
          <PrintButton />
          <p className="ml-1 flex items-baseline gap-2">
            <span className="kpi-number text-4xl">{usd(p.price_per_person_usd)}</span>
            <span className="text-sm text-muted-foreground">per person, all-inclusive</span>
          </p>
        </div>
      </div>
    </header>
  );
}

function TrustStrip() {
  const items = [
    ["24/7", "Bilingual tour leader with your team"],
    ["AFA", "Certified coaches and referees"],
    ["Private", "Bus and safe-neighborhood hotels"],
    ["Matched", "Opponents within one level of yours"],
  ];
  return (
    <ul className="site-container grid grid-cols-2 border-y border-line sm:grid-cols-4">
      {items.map(([k, v]) => (
        <li key={k} className="border-line px-6 py-6 odd:border-r sm:border-r sm:last:border-r-0">
          <p className="kpi-number text-4xl">{k}</p>
          <p className="mt-2 text-xs leading-5 text-muted-foreground">{v}</p>
        </li>
      ))}
    </ul>
  );
}

function Section({
  id,
  kicker,
  title,
  className = "",
  children,
}: {
  id: string;
  kicker: string;
  title: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={`proposal-section site-section scroll-mt-20 ${className}`}>
      <div className="site-container">
        <p className="eyebrow-wide text-xs sm:text-base">{kicker}</p>
        <h2 id={`${id}-title`} className="type-section mb-10 mt-5">
          {title}
        </h2>
        {children}
      </div>
    </section>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div className="bg-card p-5">
      <dt className="eyebrow text-xs">{k}</dt>
      <dd className="type-small-title mt-3">{v}</dd>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right font-semibold">{v}</dd>
    </div>
  );
}

function List({ items, mark, muted }: { items: string[]; mark: string; muted?: boolean }) {
  return (
    <ul className="mt-5 space-y-3 text-sm leading-5">
      {items.map((it) => (
        <li key={it} className={`flex gap-3 ${muted ? "text-muted-foreground" : ""}`}>
          <span aria-hidden className="grid size-5 shrink-0 place-items-center rounded-full bg-white/10 text-[0.6875rem] font-bold">
            {mark}
          </span>
          {it}
        </li>
      ))}
    </ul>
  );
}

function ItineraryLine({ item }: { item: ProposalItem }) {
  return (
    <li className="flex gap-2">
      <span className="w-12 shrink-0 pt-px text-xs font-semibold tabular-nums text-muted-foreground">
        {item.time ?? SLOT_LABEL[item.slot]}
      </span>
      <span>
        {item.kind === "match" ? <strong className="font-semibold text-white">{item.title}</strong> : item.title}
        {item.experience && item.experience !== item.title && (
          <span className="text-muted-foreground"> · {item.experience}</span>
        )}
      </span>
    </li>
  );
}

/** Coach-facing overview composed from the trip, so internal summaries never leak verbatim. */
function overview(p: Proposal, matches: number, experiences: number): string {
  const team = p.program ? `${p.team} ${p.program}` : p.team;
  const parts = [
    `${p.days} days in ${p.city} for ${team}`,
    matches ? `${matches} competitive matches against opponents picked for your level` : null,
    "training with certified local coaches",
    experiences ? `${experiences} experiences off the pitch` : null,
  ].filter(Boolean);
  return `${parts.join(", ")}. Everything on the ground is handled by our team — you focus on the game.`;
}

/** Level relative to the visiting team, never the raw internal score (coach-experience.md). */
function relativeLevel(level: number, team: number | null): string {
  if (team == null) return "Competitive";
  const diff = level - team;
  if (diff >= 1) return "A step up";
  if (diff <= -1) return "A confidence game";
  return "Evenly matched";
}

function OpponentCard({ o, teamLevel }: { o: ProposalOpponent; teamLevel: number | null }) {
  const label = relativeLevel(o.level_score, teamLevel);
  return (
    <li className="proposal-card flex flex-col rounded-lg border border-line bg-card p-6 transition hover:border-line-strong">
      <p className="eyebrow text-xs">{o.city}</p>
      <p className="type-card mt-3">{o.name}</p>
      <div className="mt-6" aria-label={`Level: ${label}`}>
        <div aria-hidden className="flex gap-0.5">
          {Array.from({ length: 10 }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full ${i < o.level_score ? "bg-foreground" : "bg-white/10"} ${
                teamLevel != null && i === teamLevel - 1 ? "outline outline-1 outline-offset-1 outline-foreground" : ""
              }`}
            />
          ))}
        </div>
        <p className="mt-2 inline-flex h-6 items-center rounded-full bg-white/10 px-2.5 text-[0.6875rem] font-semibold uppercase tracking-wide">
          {label}
        </p>
      </div>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">{o.description}</p>
    </li>
  );
}
