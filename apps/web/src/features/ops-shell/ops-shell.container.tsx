import Link from "next/link";
import type { ReactNode } from "react";
import { PocBadge } from "@/features/guide/poc-badge";
import { serverApi } from "@/lib/api/server";
import { CopilotPill, MobileNav, PillNav, ShellThemeToggle } from "./nav";

async function pendingApprovals(): Promise<number | null> {
  try {
    // One source of truth with the inbox and Today's KPI: the API counts by effective status
    // (a pending approval past its expiry counts as expired).
    const { data } = await serverApi().GET("/v1/approvals/counts");
    return data ? data.pending : null;
  } catch {
    return null; // the shell renders without the badge; pages show their own error
  }
}

/** Our own wordmark (never IGS's logo): condensed caps like the site's headlines. */
function Wordmark() {
  return (
    <Link
      href="/ops"
      className="flex items-baseline gap-1.5 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <span className="whitespace-nowrap font-display text-2xl font-extrabold uppercase leading-none tracking-tight">
        IGS OS
      </span>
      <span className="eyebrow hidden text-2xs lg:inline">Operaciones</span>
    </Link>
  );
}

/**
 * Ops app frame, after the site's header: a dark sticky bar with the wordmark, a centered pill
 * nav and the copilot pill; on phones a bottom pill bar. Pages sit in a 1280px container.
 */
export async function OpsShell({ children, copilot }: { children: ReactNode; copilot?: ReactNode }) {
  const pending = await pendingApprovals();
  return (
    <div className="flex min-h-dvh flex-col bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto grid h-16 max-w-7xl grid-cols-[auto_1fr_auto] md:grid-cols-[1fr_auto_1fr] items-center gap-4 px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Wordmark />
            <PocBadge />
          </div>
          <PillNav pendingApprovals={pending} />
          <div className="flex items-center justify-end gap-2">
            <CopilotPill />
            <ShellThemeToggle />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 px-6 pb-44 pt-10 md:pb-24 md:pt-14 lg:px-8">
        {children}
      </main>
      <footer className="hidden border-t border-border md:block">
        <p className="mx-auto max-w-7xl px-6 py-6 text-xs text-muted-foreground lg:px-8">
          Demo con datos ficticios. Las acciones externas siempre pasan por una aprobación.
        </p>
      </footer>
      <MobileNav pendingApprovals={pending} />
      {copilot}
    </div>
  );
}
