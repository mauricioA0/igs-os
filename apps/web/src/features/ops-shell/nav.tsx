"use client";

import { Building2, CalendarDays, CheckCheck, LayoutGrid, MoreHorizontal, Plane, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { cn, Sheet, ThemeToggle } from "@/components/ui";

type NavItem = {
  href: string;
  label: string;
  icon: typeof CalendarDays;
  exact?: boolean;
  badge?: "approvals";
  /** One of the four items in the phone's bottom bar; the rest live under "Más". */
  primary?: boolean;
};

// Order follows the coordinator's day: what needs me today, then the objects behind it.
const NAV: NavItem[] = [
  { href: "/ops", label: "Hoy", icon: CalendarDays, exact: true, primary: true },
  { href: "/ops/trips", label: "Viajes", icon: Plane, primary: true },
  { href: "/ops/accounts", label: "Clientes", icon: Building2, primary: true },
  { href: "/ops/approvals", label: "Aprobaciones", icon: CheckCheck, badge: "approvals", primary: true },
  { href: "/ops/leads", label: "Leads", icon: LayoutGrid },
  { href: "/ops/flows", label: "Flows", icon: Workflow },
];

function isActive(pathname: string, { href, exact }: NavItem) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

// The site's pill: Montserrat 12px/600, 32px tall, white when active, white/70 otherwise.
const pill =
  "inline-flex h-8 items-center gap-1.5 rounded-full px-4 font-body text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const pillActive = "bg-foreground text-background";
const pillIdle = "text-foreground/70 hover:text-foreground";
const pillGroup = "flex items-center gap-0.5 rounded-full border border-border bg-foreground/5 p-1";

function Count({ value, active }: { value: number; active: boolean }) {
  return (
    <span
      className={cn(
        "min-w-4.5 rounded-full px-1.5 text-center text-2xs leading-4.5 tabular-nums",
        active ? "bg-background text-foreground" : "bg-danger-fill text-danger-fill-foreground",
      )}
      aria-label={`${value} pendientes`}
    >
      {value}
    </span>
  );
}

/** Desktop: the centered pill group of the site's header. */
export function PillNav({ pendingApprovals }: { pendingApprovals: number | null }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Operaciones" className={cn(pillGroup, "hidden md:flex")}>
      {NAV.map((item) => {
        const active = isActive(pathname, item);
        const badge = item.badge === "approvals" ? pendingApprovals : null;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(pill, active ? pillActive : pillIdle)}
          >
            {item.label}
            {badge ? <Count value={badge} active={active} /> : null}
          </Link>
        );
      })}
    </nav>
  );
}

/** Opens the copilot drawer (it listens for ⌘J / Ctrl+J). */
export function CopilotPill() {
  const open = () =>
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true, ctrlKey: true }));
  return (
    <button type="button" onClick={open} className={cn(pill, "bg-foreground/10 px-5", pillIdle)}>
      Copiloto
      <kbd className="font-mono text-2xs text-foreground/50">⌘J</kbd>
    </button>
  );
}

export function ShellThemeToggle() {
  return (
    <ThemeToggle
      lang="es"
      className="size-8 rounded-full bg-foreground/10 text-foreground/70 hover:text-foreground"
    />
  );
}

/** Phones: a bottom pill bar with the four primary places and a "Más" sheet for the rest. */
export function MobileNav({ pendingApprovals }: { pendingApprovals: number | null }) {
  const pathname = usePathname();
  const [more, setMore] = useState(false);
  const secondary = NAV.filter((n) => !n.primary);
  const moreActive = secondary.some((n) => isActive(pathname, n));
  return (
    <>
      <nav
        aria-label="Operaciones"
        className="fixed inset-x-3 bottom-3 z-40 pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        <div className={cn(pillGroup, "justify-between bg-card/95 backdrop-blur")}>
          {NAV.filter((n) => n.primary).map((item) => {
            const active = isActive(pathname, item);
            const badge = item.badge === "approvals" ? pendingApprovals : null;
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                className={cn(pill, "relative px-3", active ? pillActive : pillIdle)}
              >
                <Icon className="size-4" aria-hidden />
                {active && <span>{item.label}</span>}
                {badge ? <Count value={badge} active={active} /> : null}
              </Link>
            );
          })}
          <button
            type="button"
            onClick={() => setMore(true)}
            aria-haspopup="dialog"
            aria-label="Más secciones"
            className={cn(pill, "px-3", moreActive ? pillActive : pillIdle)}
          >
            <MoreHorizontal className="size-4" aria-hidden />
          </button>
        </div>
      </nav>
      <Sheet open={more} onOpenChange={setMore} title="Más">
        <ul className="flex flex-col gap-2">
          {secondary.map((item) => {
            const Icon = item.icon;
            const active = isActive(pathname, item);
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  onClick={() => setMore(false)}
                  aria-current={active ? "page" : undefined}
                  className={cn(pill, "h-11 w-full justify-start gap-3 text-sm", active ? pillActive : "bg-foreground/5 " + pillIdle)}
                >
                  <Icon className="size-4" aria-hidden />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </Sheet>
    </>
  );
}
