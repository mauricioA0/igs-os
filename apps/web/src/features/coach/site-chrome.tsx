// Site-like chrome for coach surfaces and the landing: dark top bar with our own "IGS OS" mark,
// centered pill nav and a "Contact us →" pill, plus the footer with columns and the marquee.
// Never IGS's logo or photos. Shared SiteFooter/PillNav from @/components/ui can replace these.
import Link from "next/link";
import { PocBadge } from "@/features/guide/poc-badge";
import { SiteNav } from "./site-nav";

type NavItem = { href: string; label: string };

export function SiteMark() {
  return (
    <Link href="/" className="flex items-center gap-2 rounded-full focus-visible:outline-2 focus-visible:outline-offset-4">
      <span aria-hidden className="grid size-8 place-items-center rounded-sm bg-primary font-display text-sm font-extrabold leading-none text-primary-foreground">
        OS
      </span>
      <span className="font-display text-xl font-extrabold uppercase leading-none tracking-tight">IGS OS</span>
    </Link>
  );
}

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-line bg-background/90 backdrop-blur no-print">
      <div className="site-container flex h-16 items-center justify-between gap-4 px-4 sm:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <SiteMark />
          <PocBadge label="POC · fictional data" />
        </div>
        <SiteNav />
        <Link href="/chat" className="pill pill-secondary pill-arrow px-5">
          Contact us
        </Link>
      </div>
    </header>
  );
}

const FOOTER_COLUMNS: { title: string; links: NavItem[] }[] = [
  {
    title: "Programs",
    links: [
      { href: "/chat", label: "College soccer tours" },
      { href: "/chat", label: "Club & academy tours" },
      { href: "/chat", label: "World Cup experiences" },
    ],
  },
  {
    title: "IGS OS",
    links: [
      { href: "/ops", label: "Ops panel" },
      { href: "/ops/approvals", label: "Approvals" },
      { href: "/ops/flows", label: "Flows" },
    ],
  },
  {
    title: "Destinations",
    links: [
      { href: "/chat", label: "Buenos Aires" },
      { href: "/chat", label: "Rio de Janeiro" },
      { href: "/chat", label: "São Paulo" },
    ],
  },
];

const MARQUEE = ["Train. Compete. Experience.", "Argentina · Brazil · World Cup"];

export function SiteFooter({ className = "" }: { className?: string }) {
  const phrases = [...MARQUEE, ...MARQUEE];
  return (
    <footer className={`bg-raised no-print ${className}`}>
      <div aria-hidden className="marquee border-b border-line py-6">
        <div className="marquee-track">
          {[...phrases, ...phrases].map((p, i) => (
            <span key={i} className="font-display text-4xl font-extrabold uppercase tracking-[0.06em] sm:text-6xl">
              {p}
            </span>
          ))}
        </div>
      </div>
      <div className="site-container grid gap-10 px-6 py-12 sm:grid-cols-2 sm:px-8 lg:grid-cols-[1.4fr_repeat(3,1fr)]">
        <div>
          <SiteMark />
          <p className="mt-4 max-w-xs text-sm text-muted-foreground">
            Train. Compete. Experience. The operating system behind every tour.
          </p>
        </div>
        {FOOTER_COLUMNS.map((col) => (
          <nav key={col.title} aria-label={col.title}>
            <p className="eyebrow text-xs">{col.title}</p>
            <ul className="mt-3 space-y-2 text-sm">
              {col.links.map((l) => (
                <li key={l.label}>
                  <Link href={l.href} className="text-foreground/80 hover:text-white">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        ))}
      </div>
      <p className="site-container border-t border-line px-6 py-5 text-xs text-muted-foreground sm:px-8">
        Demo with fictional data. Built by Mauricio Villalba — not an official Infinity Global Sports product.
      </p>
    </footer>
  );
}
