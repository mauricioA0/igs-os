import type { Metadata } from "next";
import type { ReactNode } from "react";
import { listAccounts } from "@/features/accounts/api";
import { CopilotDrawer } from "@/features/copilot";
import { GuideWidget } from "@/features/guide";
import { OpsShell } from "@/features/ops-shell/ops-shell.container";
import { listTrips } from "@/features/trips/api";

export const metadata: Metadata = { title: { default: "Operaciones", template: "%s · Ops · IGS OS" } };

/** id → readable name, so the copilot's context chips say "Lakeshore University", not a UUID. */
async function contextLabels(): Promise<Record<string, string>> {
  const [trips, accounts] = await Promise.all([listTrips().catch(() => []), listAccounts().catch(() => [])]);
  return Object.fromEntries([
    ...trips.map((t) => [t.id, `${t.team.organization ?? t.title} · ${t.city}`]),
    ...accounts.map((a) => [a.id, a.name]),
  ]);
}

export default async function OpsLayout({ children }: { children: ReactNode }) {
  return (
    <OpsShell
      copilot={
        <>
          <CopilotDrawer labels={await contextLabels()} />
          <GuideWidget locale="es" placement="ops" />
        </>
      }
    >
      {children}
    </OpsShell>
  );
}
