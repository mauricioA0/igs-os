import type { ExecutionStatus, NodeVisualStatus } from "../lib/types";

// Site-style status pills (rounded-full on dark, hairline border); color only means state.
const execStyle: Record<ExecutionStatus, { dot: string; label: string }> = {
  running: { dot: "bg-info", label: "Corriendo" },
  waiting: { dot: "bg-warning", label: "Esperando" },
  succeeded: { dot: "bg-success", label: "Completada" },
  failed: { dot: "bg-danger", label: "Falló" },
  cancelled: { dot: "bg-muted-foreground", label: "Cancelada" },
};

const stepStyle: Record<NodeVisualStatus, { dot: string; label: string }> = {
  succeeded: { dot: "bg-success", label: "Hecho" },
  failed: { dot: "bg-danger", label: "Falló" },
  running: { dot: "bg-info", label: "Corriendo" },
  waiting: { dot: "bg-warning", label: "Esperando" },
  skipped: { dot: "bg-muted-foreground", label: "Salteado" },
  pending: { dot: "bg-muted-foreground/40", label: "No llegó" },
};

export const execDot = (status: ExecutionStatus) => execStyle[status].dot;

function Pill({ dot, label, pulse }: { dot: string; label: string; pulse?: boolean }) {
  return (
    <span className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-full border border-line bg-white/5 px-2.5 text-xs font-semibold text-foreground">
      <span aria-hidden className={`size-1.5 rounded-full ${dot} ${pulse ? "animate-pulse motion-reduce:animate-none" : ""}`} />
      {label}
    </span>
  );
}

export function ExecStatus({ status }: { status: ExecutionStatus }) {
  const s = execStyle[status];
  return <Pill dot={s.dot} label={s.label} pulse={status === "running" || status === "waiting"} />;
}

export function StepStatus({ status }: { status: NodeVisualStatus }) {
  const s = stepStyle[status];
  return <Pill dot={s.dot} label={s.label} pulse={status === "waiting" || status === "running"} />;
}
