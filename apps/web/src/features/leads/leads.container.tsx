import { Info } from "lucide-react";
import { connection } from "next/server";
import { ApiUnavailable, PageHeader } from "@/features/ops-shell/bits";
import { usd } from "@/features/ops-shell/format";
import { writeAccess } from "@/features/ops-shell/writes";
import { listLeads, type LeadsResult } from "./api";
import { LeadsBoard } from "./components/leads-board";

export async function LeadsContainer() {
  await connection();
  let result: LeadsResult;
  let access: Awaited<ReturnType<typeof writeAccess>>;
  try {
    [result, access] = await Promise.all([listLeads(), writeAccess()]);
  } catch (error) {
    return <ApiUnavailable error={error} what="los leads" />;
  }
  const { leads, live } = result;
  const open = leads.filter((l) => l.stage !== "won" && l.stage !== "lost");
  const pipeline = open.reduce((n, l) => n + l.valueUsd, 0);
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Ventas"
        title="Leads"
        description="Consultas de coaches por chat, web, email o referidos. El agente de ventas califica cada una y deja el resumen; vos movés las tarjetas cuando cambia algo."
        actions={
          <div className="text-right">
            <p className="eyebrow text-[11px] text-muted-foreground">Pipeline abierto</p>
            <p className="kpi-number mt-1 text-5xl">{usd(pipeline)}</p>
          </div>
        }
      />
      {!live && (
        <p role="note" className="flex items-start gap-2 rounded-lg border border-info/30 bg-info/10 px-4 py-3 font-body text-xs">
          <Info className="mt-px size-3.5 shrink-0 text-info" aria-hidden />
          Datos de ejemplo: esta versión de la API no expone leads. Los cambios de etapa se ven solo en esta pantalla.
        </p>
      )}
      <LeadsBoard
        initial={leads}
        nowIso={new Date().toISOString()}
        live={live}
        readOnlyReason={access.canWrite ? undefined : access.reason}
      />
    </div>
  );
}
