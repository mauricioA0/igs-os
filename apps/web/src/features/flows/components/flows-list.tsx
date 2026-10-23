import Link from "next/link";
import { categories, nodeCatalog, triggerLabel } from "../lib/catalog";
import { flowDisplayDescription, flowDisplayName } from "../lib/display-names";
import { formatDateTime } from "../lib/format";
import type { DayRuns } from "../lib/runs-strip";
import type { ExecutionStatus, ExecutionSummary, FlowGraph, FlowSummary } from "../lib/types";
import { ExecStatus } from "./status";

// `days`: executions per Buenos Aires day for the last week (lib/runs-strip), computed by the page.
export type FlowCard = { summary: FlowSummary; graph: FlowGraph | null; executions: ExecutionSummary[]; days: DayRuns[] };

// Bottom-up stacking order of the mini bars; color only means state.
const STACK: { status: ExecutionStatus; fill: string }[] = [
  { status: "succeeded", fill: "bg-success" },
  { status: "running", fill: "bg-info" },
  { status: "waiting", fill: "bg-warning" },
  { status: "failed", fill: "bg-danger" },
  { status: "cancelled", fill: "bg-muted-foreground" },
];

const pill =
  "inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function FlowsList({ flows }: { flows: FlowCard[] }) {
  return (
    <main className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-8 sm:py-14">
      <p className="eyebrow-wide text-muted-foreground">Automatizaciones · conversaciones</p>
      <h1 className="type-mega mt-4">
        <span className="headline-muted block">Flows que</span>
        <span className="block">operan solos.</span>
      </h1>
      <p className="mt-6 max-w-2xl text-base text-muted-foreground">
        Cada flow es un grafo versionado: editás el borrador, publicás una versión que ya no cambia, y cada ejecución queda fija en la versión con la
        que arrancó. Las esperas y aprobaciones son durables: sobreviven a deploys y reinicios.
      </p>
      {flows.length === 0 && <p className="mt-10 text-sm text-muted-foreground">Todavía no hay flows en este espacio.</p>}
      <ul className="mt-12 grid gap-4 md:grid-cols-2">
        {flows.map(({ summary, graph, executions, days }) => {
          const counts = new Map<string, number>();
          for (const n of graph?.nodes ?? []) {
            const c = nodeCatalog[n.type]?.category;
            if (c) counts.set(c, (counts.get(c) ?? 0) + 1);
          }
          const week = days.reduce((n, d) => n + d.total, 0);
          const waiting = executions.filter((e) => e.status === "waiting").length;
          const failed = executions.filter((e) => e.status === "failed").length;
          const name = flowDisplayName(summary.key, summary.name);
          return (
            <li key={summary.id} className="group flex flex-col rounded-lg border border-line bg-card transition-colors hover:border-line-strong">
              <div className="flex flex-1 flex-col p-6 sm:p-8">
                <div className="flex items-start justify-between gap-4">
                  <p className="eyebrow text-muted-foreground">{graph ? triggerLabel(graph.trigger) : "Sin disparador"}</p>
                  <span
                    className={`inline-flex h-6 shrink-0 items-center rounded-full px-2.5 text-xs font-semibold ${
                      summary.published_version ? "bg-white/10 text-foreground" : "border border-line text-muted-foreground"
                    }`}
                  >
                    {summary.published_version ? `v${summary.published_version}` : "Borrador"}
                  </span>
                </div>
                <h2 className="type-card mt-4">
                  <Link href={`/ops/flows/${summary.key}`} className="hover:underline focus-visible:outline-none focus-visible:underline">
                    {name}
                  </Link>
                </h2>
                <p className="mt-3 line-clamp-3 text-sm text-muted-foreground">{flowDisplayDescription(summary.key, summary.description)}</p>
                {counts.size > 0 && (
                  <div className="mt-5 flex flex-wrap gap-1.5">
                    {[...counts].map(([c, n]) => (
                      <span key={c} className="inline-flex h-6 items-center gap-1 rounded-full border border-line px-2.5 text-xs text-muted-foreground">
                        <span aria-hidden>{categories[c as keyof typeof categories].mark}</span>
                        {n} {categories[c as keyof typeof categories].label}
                      </span>
                    ))}
                  </div>
                )}

                <div className="mt-8 flex items-end justify-between gap-6">
                  <div>
                    <p className="kpi-number text-5xl">{week}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {week === 1 ? "ejecución" : "ejecuciones"} · 7 días
                      {waiting > 0 && <span className="text-warning"> · {waiting} esperando</span>}
                      {failed > 0 && <span className="text-danger"> · {failed} con error</span>}
                    </p>
                  </div>
                  <RunsStrip days={days} />
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-6 py-4 sm:px-8">
                <ul className="flex min-w-0 flex-wrap gap-1.5" aria-label="Últimas ejecuciones">
                  {executions.slice(0, 3).map((e) => (
                    <li key={e.id}>
                      <Link
                        href={`/ops/flows/${summary.key}/executions/${e.id}`}
                        className="inline-flex items-center gap-2 rounded-full text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        title={`${e.trigger_kind} · ${formatDateTime(e.started_at)}`}
                      >
                        <ExecStatus status={e.status} />
                        <span className="hidden tabular-nums sm:inline">{formatDateTime(e.started_at)}</span>
                      </Link>
                    </li>
                  ))}
                  {executions.length === 0 && <li className="text-xs text-muted-foreground">Sin ejecuciones todavía</li>}
                </ul>
                <Link href={`/ops/flows/${summary.key}`} aria-label={`Abrir ${name}`} className={`${pill} bg-foreground text-background hover:bg-foreground/85`}>
                  Abrir <span aria-hidden>→</span>
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </main>
  );
}

function RunsStrip({ days }: { days: DayRuns[] }) {
  const max = Math.max(1, ...days.map((d) => d.total));
  return (
    <figure className="shrink-0" aria-label={`Ejecuciones por día, últimos 7 días: ${days.map((d) => d.total).join(", ")}`}>
      <div className="flex h-14 items-end gap-1">
        {days.map((d) => (
          <div key={d.day} className="flex h-full w-4 flex-col justify-end" title={`${d.day}: ${d.total}`}>
            {d.total === 0 ? (
              <div className="h-0.5 rounded-full bg-white/10" />
            ) : (
              <div className="flex flex-col-reverse overflow-hidden rounded-sm" style={{ height: `${(d.total / max) * 100}%` }}>
                {STACK.map(({ status, fill }) =>
                  d.byStatus[status] ? <div key={status} className={fill} style={{ flexGrow: d.byStatus[status] }} /> : null,
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <figcaption className="mt-1.5 flex gap-1" aria-hidden>
        {days.map((d) => (
          <span key={d.day} className="w-4 text-center text-[10px] font-semibold text-muted-foreground">
            {d.label}
          </span>
        ))}
      </figcaption>
    </figure>
  );
}
