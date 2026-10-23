import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Bot, ChevronDown, ChevronLeft, ChevronRight, Menu, Plus, Search, Trash2 } from "lucide-react";
import {
  Avatar,
  Badge,
  BrandMark,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  CountryTag,
  EmptyState,
  Field,
  IconButton,
  Input,
  Kbd,
  PillGroup,
  PillNav,
  PillNavItem,
  Select,
  SiteFooter,
  Skeleton,
  SpotlightCard,
  Stat,
  StatusBadge,
  StatusDot,
  Table,
  TableCaption,
  TBody,
  TD,
  TH,
  THead,
  TR,
  Textarea,
  ThemeToggle,
  Tooltip,
  fieldA11y,
  statusVocabulary,
  type StatusDomain,
} from "@/components/ui";
import { OverlayDemo, TabsDemo } from "./interactive";

export const metadata: Metadata = { title: "Design system" };

// Shared names from docs/design/igs-site-style.md, with the values measured on the site.
const siteTokens: [token: string, utility: string, value: string][] = [
  ["background", "bg-background", "#0D0D0D"],
  ["card", "bg-card", "#171717"],
  ["raised", "bg-raised", "#262626"],
  ["foreground", "text-foreground", "#F2F2F2"],
  ["foreground-strong", "text-foreground-strong", "#FFFFFF"],
  ["muted-foreground", "text-muted-foreground", "#999999"],
  ["muted-headline", "text-muted-headline", "#7A7A7A"],
  ["line", "border-line", "white / 10%"],
  ["line-strong", "border-line-strong", "white / 20%"],
  ["nav-idle", "text-nav-idle", "white / 70%"],
  ["primary", "bg-primary", "#FFFFFF"],
  ["secondary", "bg-secondary", "white / 10%"],
];
const hues = ["success", "warning", "danger", "info", "brand", "ai"];
const countries = ["argentina", "brazil-green", "brazil-gold", "usa-red", "costa-rica", "spain"];
const canvasTokens = ["canvas", "canvas-dot", "edge", "edge-active", "node-ai", "node-conversation", "node-logic", "node-integration", "node-human"];

const typeSpecs: [cls: string, spec: string, sample: ReactNode][] = [
  ["type-mega", "Barlow Condensed 900 · clamp(48–128px) · lh .8 · −.025em", <>Hoy en operación.</>],
  ["type-hero", "Barlow Condensed 800 · clamp(40–60px) · lh .8 · −.025em", <>Running every tour from one console.</>],
  ["type-section", "DM Sans 400 · clamp(32–48px) · lh .8 · −.06em", <>Trips that need you today</>],
  ["type-statement", "DM Sans 400 · clamp(32–60px) · lh 1 · −.06em", <>Agents draft. People approve.</>],
  ["type-card", "DM Sans 400 · 30px · lh .95 · −.05em", <>Buenos Aires · 10 days</>],
  ["type-small-title", "DM Sans 400 · 20px · lh 1.05 · −.06em", <>Pre-departure check</>],
  ["eyebrow-wide", "DM Sans 600 · 22px (16 mobile) · +.375em · upper", <>Plan a tour</>],
  ["eyebrow", "Montserrat 600 · 12px ops / text-base site · +.025em · upper · muted", <>Trips in progress</>],
  ["kpi-number", "Barlow Condensed 900 · 64px · lh .85 · tabular", <>2,280</>],
];

const NAV = ["Home", "Soccer Tours", "Camps", "Family Experiences", "Other Sports", "About", "Gallery"];
const WITH_MENU = new Set(["Camps", "Other Sports"]);

function Section({ id, eyebrow, title, children }: { id: string; eyebrow: string; title: string; children: ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="border-t border-line py-14 md:py-16">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={`${id}-title`} className="type-section mt-4">
        {title}
      </h2>
      <div className="mt-10">{children}</div>
    </section>
  );
}

function Spec({ children }: { children: ReactNode }) {
  return <code className="font-mono text-2xs text-muted-foreground">{children}</code>;
}

// Screenshot-faithful replica of the site's header + hero, with our own mark, copy and CSS-only art.
function SiteReplica() {
  return (
    <div className="overflow-hidden rounded-xl border border-line bg-background">
      <header className="flex h-[4.75rem] items-center justify-between gap-4 px-4 md:px-10 xl:px-20">
        <BrandMark wordmark={false} />
        <PillNav label="Replica navigation" className="hidden lg:block">
          {NAV.map((item) => (
            <PillNavItem key={item} href="#replica" active={item === "Home"}>
              {item}
              {WITH_MENU.has(item) && <ChevronDown aria-hidden />}
            </PillNavItem>
          ))}
        </PillNav>
        <span className="hidden lg:block">
          <ButtonLink href="#replica" variant="outline" withArrow>
            Contact Us
          </ButtonLink>
        </span>
        <IconButton label="Open menu" size="md" className="lg:hidden">
          <Menu />
        </IconButton>
      </header>
      <div className="flex flex-col gap-6 px-6 pt-20 pb-16 md:flex-row md:items-end md:justify-between md:px-10 md:pt-28 md:pb-20 xl:px-20">
        <h3 className="type-hero max-w-3xl text-foreground-strong">
          Running every tour
          <br />
          from one console.
        </h3>
        <p className="eyebrow text-base font-medium md:text-right">Agent-native operations for sports tours</p>
      </div>
      <div className="stadium-art relative h-72 md:h-[32.5rem]">
        <IconButton label="Previous slide" className="absolute top-1/2 left-4 -translate-y-1/2">
          <ChevronLeft />
        </IconButton>
        <IconButton label="Next slide" className="absolute top-1/2 right-4 -translate-y-1/2">
          <ChevronRight />
        </IconButton>
        <div aria-hidden className="absolute bottom-5 left-1/2 flex -translate-x-1/2 items-center gap-1.5">
          <span className="h-1.5 w-6 rounded-full bg-foreground-strong" />
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className="size-1.5 rounded-full bg-foreground-strong/50" />
          ))}
        </div>
      </div>
      <div className="px-6 py-16 md:px-10 md:py-24 xl:px-20">
        <h3 className="type-mega">
          <span className="headline-muted">More than a dashboard.</span>
          <br />
          An operating system.
        </h3>
      </div>
    </div>
  );
}

function TokenGrid() {
  return (
    <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
      {siteTokens.map(([token, utility, value]) => (
        <div key={token} className="flex items-center gap-4 bg-background p-4">
          <span className="size-12 shrink-0 rounded-md border border-line" style={{ background: `var(--${token})` }} />
          <div className="min-w-0">
            <p className="font-mono text-xs text-foreground">{utility}</p>
            <p className="mt-1 text-xs text-muted-foreground">{value}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function Ramps() {
  return (
    <div className="grid gap-3">
      {hues.map((n) => (
        <div key={n} className="flex flex-wrap items-center gap-2">
          <code className="w-16 font-mono text-xs text-muted-foreground">{n}</code>
          {["", "-soft", "-border", "-fill"].map((suffix) => (
            <span
              key={suffix}
              title={`${n}${suffix}`}
              className="size-7 shrink-0 rounded-full border border-line"
              style={{ background: `var(--${n}${suffix})` }}
            />
          ))}
          <Badge tone={n as "success"} dot>
            {n} badge
          </Badge>
          <span
            className="rounded-full px-2.5 py-0.5 text-xs font-semibold"
            style={{ color: `var(--${n}-fill-foreground)`, background: `var(--${n}-fill)` }}
          >
            fill
          </span>
        </div>
      ))}
    </div>
  );
}

function Vocabulary() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {(Object.keys(statusVocabulary) as StatusDomain[]).map((domain) => (
        <div key={domain} className="flex flex-wrap items-center gap-1.5">
          <code className="w-20 font-mono text-xs text-muted-foreground">{domain}</code>
          {Object.keys(statusVocabulary[domain]).map((s) => (
            <StatusBadge key={s} status={s} domain={domain} lang="en" />
          ))}
        </div>
      ))}
    </div>
  );
}

const FOOTER_COLUMNS = [
  { title: "Operations", links: ["Today", "Trips", "Accounts", "Approvals"].map((label) => ({ label, href: "#footer" })) },
  { title: "Automation", links: ["Flows", "Executions", "Traces"].map((label) => ({ label, href: "#footer" })) },
  { title: "Destinations", links: ["Buenos Aires, Argentina", "Rio de Janeiro, Brazil", "San José, Costa Rica"].map((label) => ({ label, href: "#footer" })) },
];

export default function DesignPage() {
  const ids = (s: string) => `design-${s}`;
  return (
    <main className="flex-1 bg-background">
      <div className="mx-auto max-w-7xl px-4 py-10 md:px-8 md:py-16">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow-wide text-muted-foreground">Design system</p>
            <h1 className="type-mega mt-6">
              <span className="headline-muted">IGS OS,</span>
              <br />
              site-matched.
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Dark is the default · light is opt-in</span>
            <ThemeToggle lang="en" />
          </div>
        </div>
        <p className="mt-8 max-w-2xl text-lg leading-7 text-muted-foreground">
          Measured with <code className="font-mono text-sm">getComputedStyle</code> on the public site and rebuilt from free fonts and
          CSS only. Every name below is the shared contract in <code className="font-mono text-sm">docs/design/igs-site-style.md</code>.
        </p>

        <div id="replica" className="mt-14">
          <SiteReplica />
        </div>

        <Section id="color" eyebrow="Color" title="Exact chrome, color only from status">
          <TokenGrid />
          <div className="mt-10 grid gap-10 lg:grid-cols-2">
            <div>
              <p className="eyebrow mb-4">Status tones (ink · soft · border · fill)</p>
              <Ramps />
            </div>
            <div className="space-y-8">
              <div>
                <p className="eyebrow mb-4">Country accents (decorative + ink)</p>
                <div className="flex flex-wrap gap-x-5 gap-y-2">
                  {countries.map((t) => (
                    <span key={t} className="flex items-center gap-2 text-sm font-semibold" style={{ color: `var(--${t}-ink)` }}>
                      <span className="size-2.5 rounded-full" style={{ background: `var(--${t})` }} />
                      {t}
                    </span>
                  ))}
                </div>
              </div>
              <div>
                <p className="eyebrow mb-4">Flow canvas</p>
                <div className="flex flex-wrap gap-2">
                  {canvasTokens.map((t) => (
                    <span key={t} title={t} className="flex items-center gap-2 rounded-full border border-line px-2 py-1 font-mono text-2xs">
                      <span className="size-3 rounded-full border border-line" style={{ background: `var(--${t})` }} />
                      {t}
                    </span>
                  ))}
                </div>
              </div>
              <p className="text-sm text-muted-foreground">
                All pairs are checked against WCAG 2.2 AA by <code className="font-mono">pnpm --filter web tokens:check</code>, translucent
                tokens composited over the surface they sit on.
              </p>
            </div>
          </div>
        </Section>

        <Section id="type" eyebrow="Typography" title="Condensed caps, tight DM Sans, Montserrat body">
          <div className="divide-y divide-line">
            {typeSpecs.map(([cls, spec, sample]) => (
              <div key={cls} className="grid gap-3 py-6 md:grid-cols-[14rem_1fr] md:items-baseline">
                <div>
                  <p className="font-mono text-xs text-foreground">.{cls}</p>
                  <Spec>{spec}</Spec>
                </div>
                <p className={cls}>{sample}</p>
              </div>
            ))}
            <div className="grid gap-3 py-6 md:grid-cols-[14rem_1fr] md:items-baseline">
              <div>
                <p className="font-mono text-xs text-foreground">.headline-muted</p>
                <Spec>#7A7A7A, first line of two-tone headlines</Spec>
              </div>
              <p className="type-hero">
                <span className="headline-muted">More than a tour.</span> A competitive immersion.
              </p>
            </div>
            <div className="grid gap-3 py-6 md:grid-cols-[14rem_1fr]">
              <div>
                <p className="font-mono text-xs text-foreground">body · font-body</p>
                <Spec>Montserrat 400 · 16/24 · long copy 18/28 muted</Spec>
              </div>
              <div className="max-w-prose space-y-3">
                <p>Ops talks to the copilot; the copilot drafts, people approve the exact payload.</p>
                <p className="text-lg leading-7 text-muted-foreground">
                  Every action that leaves the building waits for a person, and every answer cites the email, call or document it came
                  from.
                </p>
                <p className="text-sm text-muted-foreground">Small · Montserrat 400 · 14/20</p>
              </div>
            </div>
          </div>
        </Section>

        <Section id="actions" eyebrow="Actions" title="Pills, always">
          <div className="space-y-8">
            <div className="flex flex-wrap items-center gap-3">
              <Button withArrow>Plan a tour</Button>
              <Button variant="secondary" withArrow>
                Contact us
              </Button>
              <Button variant="ghost">Cancel</Button>
              <Button variant="danger">
                <Trash2 />
                Delete draft
              </Button>
              <Button variant="outline">Outline (legacy)</Button>
              <Button disabled>Disabled</Button>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm">Small</Button>
              <Button size="md">Medium</Button>
              <Button size="lg" withArrow>
                Large
              </Button>
              <IconButton label="Search" size="sm">
                <Search />
              </IconButton>
              <IconButton label="Add" size="md">
                <Plus />
              </IconButton>
              <IconButton label="Copilot" size="lg" variant="primary">
                <Bot />
              </IconButton>
            </div>
            <div className="space-y-3">
              <PillNav label="Ops navigation sample">
                {["Hoy", "Viajes", "Clientes", "Aprobaciones", "Leads", "Flows", "Trazas"].map((item) => (
                  <PillNavItem key={item} href="#actions" active={item === "Hoy"}>
                    {item}
                  </PillNavItem>
                ))}
              </PillNav>
              <div>
                <PillGroup>
                  <PillNavItem active>All</PillNavItem>
                  <PillNavItem>Waiting</PillNavItem>
                  <PillNavItem>Failed</PillNavItem>
                </PillGroup>
              </div>
            </div>
            <TabsDemo />
            <div className="flex flex-wrap items-center gap-4">
              <OverlayDemo />
              <Tooltip id={ids("tip")} content="Ask the ops copilot">
                <IconButton label="Copilot">
                  <Bot />
                </IconButton>
              </Tooltip>
              <span className="text-sm text-muted-foreground">
                Command menu <Kbd>⌘</Kbd> <Kbd>K</Kbd>
              </span>
            </div>
          </div>
        </Section>

        <Section id="surfaces" eyebrow="Surfaces" title="Flat cards and photo-style spotlights">
          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <SpotlightCard
              eyebrow="Critical · decides in 9 days"
              title={
                <>
                  <span className="headline-muted">Lakeshore</span> Women&apos;s Soccer
                </>
              }
              action={
                <>
                  <ButtonLink href="#surfaces" size="sm" withArrow>
                    Open account
                  </ButtonLink>
                  <Button size="sm" variant="secondary">
                    Ask copilot
                  </Button>
                </>
              }
              className="min-h-80"
            >
              Enrollment fees (24 × US$95) are a week overdue and a rival quote landed at USD 2,750 per person.
            </SpotlightCard>
            <Card>
              <CardHeader
                title="Pre-departure check"
                description="Runs 30 days before every confirmed trip."
                action={<StatusBadge status="published" domain="flow" lang="en" />}
              />
              <p className="text-sm text-muted-foreground">Requests confirmations from every provider and escalates after 48 h.</p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Badge variant="label">Automation</Badge>
                <Badge variant="kind">Commitment</Badge>
                <Badge tone="live">Live</Badge>
              </div>
            </Card>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Trips in progress" value={12} delta={20} hint="vs last month" />
            <Stat label="Waiting on you" value={4} hint="approvals" />
            <Stat label="Overdue fees" value="2,280" hint="US$ · Lakeshore" />
            <Stat label="p95 agent latency" value="4.1s" delta={-8} invert hint="last 7 days" />
          </div>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-line bg-raised p-5">
              <p className="eyebrow">bg-raised</p>
              <p className="type-small-title mt-4">Raised panel</p>
            </div>
            <EmptyState icon={<Search />} title="No traces yet" description="Runs appear here as soon as an agent acts." />
            <Card className="space-y-3">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-20" />
            </Card>
          </div>
        </Section>

        <Section id="status" eyebrow="Status" title="One vocabulary, color means state">
          <Vocabulary />
          <div className="mt-8 flex flex-wrap items-center gap-6">
            <StatusDot status="running" domain="execution" lang="en" />
            <StatusDot status="waiting" domain="execution" label="Waiting for approval" />
            <StatusDot status="in_progress" domain="trip" lang="en" />
            <StatusDot status="failed" domain="execution" lang="en" />
            <CountryTag country="Argentina" city="Buenos Aires" />
            <CountryTag country="Brazil" city="Rio de Janeiro" />
            <CountryTag country="Costa Rica" />
            <Avatar name="Lucía Fernández" />
            <Avatar name="Trip Planner" kind="agent" />
          </div>
        </Section>

        <Section id="data" eyebrow="Data entry" title="Forms and tables on #171717">
          <div className="grid gap-8 lg:grid-cols-2">
            <Card className="grid gap-4">
              <Field id={ids("team")} label="Team name" hint="As it appears on the proposal.">
                <Input placeholder="Lakeshore Women's Soccer" {...fieldA11y(ids("team"), { hint: true })} />
              </Field>
              <Field id={ids("size")} label="Group size" error="Must be between 12 and 60.">
                <Input type="number" defaultValue={7} {...fieldA11y(ids("size"), { error: true })} />
              </Field>
              <Field id={ids("dest")} label="Destination">
                <Select {...fieldA11y(ids("dest"))} defaultValue="Argentina">
                  <option>Argentina</option>
                  <option>Brazil</option>
                  <option>Costa Rica</option>
                </Select>
              </Field>
              <Field id={ids("notes")} label="Notes for ops">
                <Textarea placeholder="Two players vegetarian…" {...fieldA11y(ids("notes"))} />
              </Field>
            </Card>
            <Table>
              <TableCaption>Pending provider confirmations</TableCaption>
              <THead>
                <TR>
                  <TH>Day</TH>
                  <TH>Item</TH>
                  <TH>Status</TH>
                </TR>
              </THead>
              <TBody>
                <TR>
                  <TD className="tabular-nums">2</TD>
                  <TD>vs Deportivo Belgrano Femenino</TD>
                  <TD>
                    <StatusBadge status="requested" domain="item" lang="en" />
                  </TD>
                </TR>
                <TR>
                  <TD className="tabular-nums">4</TD>
                  <TD>Stadium tour</TD>
                  <TD>
                    <StatusBadge status="confirmed" domain="item" lang="en" />
                  </TD>
                </TR>
                <TR>
                  <TD className="tabular-nums">6</TD>
                  <TD>Palermo Sports Hotel</TD>
                  <TD>
                    <StatusBadge status="pending" domain="item" lang="en" />
                  </TD>
                </TR>
              </TBody>
            </Table>
          </div>
        </Section>

        <Section id="light" eyebrow="Light theme" title="Opt-in, same names">
          <div className="light rounded-xl border border-line bg-background p-6 text-foreground md:p-10">
            <p className="eyebrow">Inside a .light subtree</p>
            <p className="type-hero mt-4">
              <span className="headline-muted">Same tokens,</span> light values.
            </p>
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button withArrow>Primary</Button>
              <Button variant="secondary">Secondary</Button>
              <Badge tone="success" dot>
                Confirmed
              </Badge>
              <Badge tone="warning">Pending</Badge>
              <Badge tone="danger">Critical</Badge>
            </div>
          </div>
        </Section>
      </div>

      <div id="footer">
        <SiteFooter
          columns={FOOTER_COLUMNS}
          note="Agents, durable flows and cited answers for sports tour operations."
          cta={
            <ButtonLink href="#footer" variant="secondary" withArrow>
              Contact us
            </ButtonLink>
          }
          legal={
            <>
              <span>© 2026 IGS OS demo. Fictional data.</span>
              <span>New York · Denver · Buenos Aires</span>
            </>
          }
        />
      </div>
    </main>
  );
}
