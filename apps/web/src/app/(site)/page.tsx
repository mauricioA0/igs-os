import Link from "next/link";
import "@/features/coach/coach.css";
import { SiteFooter, SiteHeader } from "@/features/coach/site-chrome";
import { DEMO_IDS, TOUR_START_URL, TOUR_STEPS, stepUrl } from "@/features/tour";

// Secondary entry points for visitors who'd rather explore than follow the tour.
const surfaces = [
  { href: "/ops", label: "Ops panel", note: "Today, trips, leads and Account 360." },
  { href: "/ops/approvals", label: "Approvals", note: "What the agents want to do, before they do it." },
  { href: "/ops/flows", label: "Flows", note: "Visual editor and durable executions." },
  { href: "/chat", label: "Coach chat", note: "The inquiry a coach starts on the site." },
  { href: `/proposal/${DEMO_IDS.lakeshoreTrip}`, label: "Proposal", note: "What the coach receives." },
  { href: "/design", label: "Design system", note: "Tokens and components." },
];

export default function Home() {
  return (
    // The landing borrows the coach surfaces' site look; `dark` sits outside `igs-site` so the
    // scoped site palette wins over the generic dark tokens.
    <div className="dark flex flex-1 flex-col">
      <div className="igs-site flex flex-1 flex-col">
        <SiteHeader />
        <main className="flex flex-1 flex-col">
          <section aria-labelledby="hero" className="relative isolate overflow-hidden px-6 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-28 lg:min-h-[80vh]">
            <div aria-hidden className="stadium-art absolute inset-0 -z-10" />
            <div aria-hidden className="stadium-streaks absolute inset-0 -z-10" />
            <div className="site-container">
              <p className="eyebrow-wide text-white">IGS OS · v0</p>
              <h1 id="hero" className="type-mega mt-8">
                <span className="headline-muted">The operating system</span>
                <br />
                for Infinity Global Sports.
              </h1>
              <p className="copy-long mt-10 max-w-2xl">
                The ops team runs every tour with agents and durable flows, and stays in control
                through approvals. Coaches get a concierge and a proposal in minutes.
              </p>
              <div className="mt-10 flex flex-wrap gap-3">
                <Link href={TOUR_START_URL} className="pill pill-lg pill-primary pill-arrow">
                  Start the 2-minute tour
                </Link>
                <a href="#intro-video" className="pill pill-lg pill-secondary">
                  ▶ Watch the intro (2:27)
                </a>
                <Link href="/chat" className="pill pill-lg pill-secondary">
                  Plan a tour as a coach
                </Link>
              </div>
            </div>
          </section>

          <section id="intro-video" aria-labelledby="intro-heading" className="site-section scroll-mt-20 border-t border-line">
            <div className="site-container">
              <p className="eyebrow-wide text-xs sm:text-base">Intro video</p>
              <h2 id="intro-heading" className="type-statement mt-6 max-w-4xl">
                <span className="headline-muted">Two minutes,</span> the whole system.
              </h2>
              <p className="copy-long mt-6 max-w-2xl">
                A POC with fictional data: no real IGS information. Narrated walk-through of the ops
                day, Account 360, the copilot, approvals, durable flows and what the coach receives.
              </p>
              <video
                className="mt-10 aspect-video w-full rounded-lg border border-line bg-card"
                src="/demo/igs-os-demo.mp4"
                poster="/demo/poster.jpg"
                controls
                preload="none"
                playsInline
              >
                <a href="/demo/igs-os-demo.mp4">Download the intro video</a>
              </video>
            </div>
          </section>

          <section aria-labelledby="tour-heading" className="site-section border-t border-line">
            <div className="site-container">
              <p className="eyebrow-wide text-xs sm:text-base">The guided tour</p>
              <h2 id="tour-heading" className="type-statement mt-6 max-w-4xl">
                <span className="headline-muted">One story, six stops.</span> From the ops queue to
                the proposal the coach receives.
              </h2>
              <p className="copy-long mt-6 max-w-2xl">
                Lakeshore University&apos;s March 2027 tour is at risk, with a decision due Oct 31.
                Follow it end to end. No login.
              </p>
              <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {TOUR_STEPS.map((step, i) => (
                  <li key={step.anchor}>
                    <Link
                      href={stepUrl(i + 1)}
                      className="group flex h-full flex-col rounded-lg border border-line bg-card p-6 transition hover:border-line-strong"
                    >
                      <span className="kpi-number text-5xl text-muted-headline transition group-hover:text-foreground">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <span className="type-card mt-6">{step.title}</span>
                      <span className="mt-3 line-clamp-3 text-sm leading-6 text-muted-foreground">{step.body}</span>
                    </Link>
                  </li>
                ))}
              </ol>
              <Link href={TOUR_START_URL} className="pill pill-lg pill-primary pill-arrow mt-10">
                Start the tour
              </Link>
            </div>
          </section>

          <nav aria-labelledby="explore-heading" className="site-section border-t border-line">
            <div className="site-container">
              <p className="eyebrow-wide text-xs sm:text-base">Explore</p>
              <h2 id="explore-heading" className="type-section mt-6">
                <span className="headline-muted">Or explore</span> on your own.
              </h2>
              <ul className="mt-12 grid gap-px overflow-hidden rounded-lg border border-line bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
                {surfaces.map((s) => (
                  <li key={s.href}>
                    <Link href={s.href} className="group flex h-full flex-col bg-background p-6 transition hover:bg-card">
                      <span className="type-small-title flex items-center justify-between">
                        {s.label}
                        <span aria-hidden className="text-muted-foreground transition group-hover:translate-x-1 group-hover:text-foreground">
                          →
                        </span>
                      </span>
                      <span className="mt-3 text-sm leading-6 text-muted-foreground">{s.note}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        </main>
        <SiteFooter />
      </div>
    </div>
  );
}
