import type { Metadata } from "next";
import { ApprovalsInbox } from "@/features/approvals/approvals-inbox";
import { loadInbox } from "@/features/approvals/data";
import { effectiveStatus } from "@/features/approvals/lib/status";

export const metadata: Metadata = { title: "Aprobaciones · IGS OS" };

// Server container: fetches the inbox, the caller and the selected approval; the client
// container takes over selection, keyboard and decisions.
export default async function ApprovalsPage({ searchParams }: { searchParams: Promise<{ id?: string }> }) {
  const { id } = await searchParams;
  const { items, me, selected, now } = await loadInbox(id);
  const pending = items.filter((a) => effectiveStatus(a, new Date(now)) === "pending").length;
  return (
    <div lang="es" className="space-y-8">
      <header className="space-y-4">
        <p className="eyebrow-wide text-xs text-muted-foreground sm:text-sm">Operaciones</p>
        <h1 className="type-hero">
          <span className="headline-muted">Bandeja de</span> aprobaciones
        </h1>
        <p className="max-w-prose font-body text-sm leading-6 text-muted-foreground">
          {pending
            ? `${pending} ${pending === 1 ? "decisión espera" : "decisiones esperan"} tu OK. Nada sale de IGS sin pasar por acá.`
            : "Nada espera tu OK ahora."}
        </p>
      </header>
      <ApprovalsInbox initialItems={items} initialDetail={selected} me={me} serverNow={now} />
    </div>
  );
}
