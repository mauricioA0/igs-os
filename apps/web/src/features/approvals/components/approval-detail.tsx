import { Clock, Fingerprint, Mail, MessageCircle, Undo2, Workflow, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/components/ui";
import { expiryState, formatInZone, formatRemaining, timezoneLabel } from "../lib/expiry";
import { fingerprint, type Channel, type Preview } from "../lib/preview";
import type { ApprovalDetail } from "../types";
import { RISK_LABEL, STATUS_LABEL } from "./labels";
import { TAG, TAG_TONE, tagTone } from "./pills";

const CHANNEL_ICON: Record<Channel, ReactNode> = {
  email: <Mail aria-hidden className="size-4" />,
  whatsapp: <MessageCircle aria-hidden className="size-4" />,
  change: <Wrench aria-hidden className="size-4" />,
  other: <Workflow aria-hidden className="size-4" />,
};

// Presentational: everything the approver needs to decide, nothing to fetch.
export function ApprovalDetailView({
  approval,
  preview,
  now,
  banner,
  footer,
}: {
  approval: ApprovalDetail;
  preview: Preview;
  now: Date;
  banner?: ReactNode;
  footer?: ReactNode;
}) {
  const exp = approval.status === "pending" ? expiryState(approval.expires_at, now) : { kind: "none" as const };
  const status = exp.kind === "expired" ? STATUS_LABEL.expired : STATUS_LABEL[approval.status];
  const tz = preview.timezone;

  const action = approval.risk_class === "external" ? "Envío" : approval.risk_class === "internal_write" ? "Cambio" : "Consulta";

  return (
    <article aria-labelledby="approval-title" className="space-y-6" data-tour="approval-card">
      <header className="space-y-4">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={cn(TAG, tagTone(RISK_LABEL[approval.risk_class].tone))}>{RISK_LABEL[approval.risk_class].label}</span>
          <span className={cn(TAG, tagTone(status.tone))}>{status.label}</span>
          <span
            className={cn(TAG, TAG_TONE.neutral, "ml-auto font-mono tracking-normal")}
            title="Si el contenido cambia, cambia la huella y hay que volver a aprobar."
          >
            <Fingerprint aria-hidden className="size-3" />
            <span className="sr-only">Huella del contenido:</span>
            {fingerprint(approval.payload_hash)}
          </span>
        </div>
        <p className="eyebrow-wide flex items-center gap-3 text-xs text-muted-foreground sm:text-sm">
          {CHANNEL_ICON[preview.channel]}
          {action} · {preview.channelLabel}
        </p>
        <h2 id="approval-title" className="type-card text-foreground">
          {approval.title}
        </h2>
        {preview.summary && <p className="max-w-prose font-body text-sm leading-6 text-muted-foreground">{preview.summary}</p>}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-body text-xs text-muted-foreground">
          {(preview.flowLabel || preview.nodeLabel) && (
            <span className="flex items-center gap-1.5">
              <Workflow aria-hidden className="size-3.5" />
              {[preview.flowLabel, preview.nodeLabel].filter(Boolean).join(" · ")}
            </span>
          )}
          {preview.requestedBy && <span>Pedido por {preview.requestedBy}</span>}
        </div>
      </header>

      {banner}

      <section aria-labelledby="send-title" className="overflow-hidden rounded-lg border border-line bg-card">
        <div className="flex items-center justify-between gap-2 border-b border-line bg-raised px-5 py-3">
          <h3 id="send-title" className="eyebrow flex items-center gap-2 text-[11px] text-foreground">
            {approval.risk_class === "external" ? "Lo que se va a enviar" : "Lo que va a cambiar"} · {preview.channelLabel}
          </h3>
          <span aria-hidden className="flex gap-1.5">
            <span className="size-2 rounded-full bg-white/15" />
            <span className="size-2 rounded-full bg-white/15" />
            <span className="size-2 rounded-full bg-white/15" />
          </span>
        </div>
        <dl className="divide-y divide-line font-body text-sm">
          {preview.to && <Row label="Para">{preview.to}</Row>}
          {preview.subject && <Row label="Asunto">{preview.subject}</Row>}
          {preview.rows.map((r) => (
            <Row key={r.label} label={r.label}>
              {r.value}
            </Row>
          ))}
        </dl>
        {preview.body && preview.channel === "change" && preview.rows.length > 0 ? (
          // The rows above already say the change in words; the raw record ids stay one click away.
          <details className="group border-t border-line px-5 py-4">
            <summary className="eyebrow cursor-pointer list-none text-[11px] text-muted-foreground hover:text-foreground">
              ids técnicos <span aria-hidden className="inline-block transition-transform group-open:rotate-90">›</span>
            </summary>
            <p className="mt-3 font-mono text-xs leading-5 break-words whitespace-pre-wrap text-muted-foreground">{preview.body}</p>
          </details>
        ) : preview.body && (
          <div className="border-t border-line px-5 py-5">
            <p className="eyebrow mb-3 text-[11px] text-muted-foreground">{preview.channel === "change" ? "Detalle" : "Mensaje"}</p>
            {preview.channel === "whatsapp" ? (
              <p className="ml-auto max-w-[85%] rounded-2xl rounded-tr-sm bg-raised px-4 py-3 font-body text-sm leading-6 whitespace-pre-wrap text-foreground">
                {preview.body}
              </p>
            ) : (
              <p className="font-body text-sm leading-6 whitespace-pre-wrap text-foreground/90">{preview.body}</p>
            )}
          </div>
        )}
      </section>

      {exp.kind !== "none" && (
        <section
          aria-label="Vencimiento"
          className={cn(
            "flex gap-3 rounded-lg border px-5 py-4 font-body text-sm",
            exp.kind === "expired" ? "border-line bg-white/5" : exp.urgent ? "border-danger/40 bg-danger/10" : "border-warning/30 bg-warning/5",
          )}
        >
          <Clock aria-hidden className={cn("mt-0.5 size-4 shrink-0", exp.kind === "pending" && (exp.urgent ? "text-danger" : "text-warning"))} />
          <div className="space-y-1">
            <p className="font-semibold text-foreground">
              {exp.kind === "expired"
                ? `Venció el ${formatInZone(exp.at, tz)} (${timezoneLabel(tz)})`
                : `Vence en ${formatRemaining(exp.remainingMs)} · ${formatInZone(exp.at, tz)} (${timezoneLabel(tz)})`}
            </p>
            <p className="text-muted-foreground">
              {exp.kind === "expired" ? "Ya no se puede decidir." : preview.onExpiry}
            </p>
          </div>
        </section>
      )}

      {approval.status !== "pending" && (
        <section aria-label="Decisión" className="rounded-lg border border-line bg-white/5 px-5 py-4 font-body text-sm">
          <p className="font-semibold text-foreground">
            {status.label}
            {approval.decided_at && ` · ${formatInZone(new Date(approval.decided_at), tz)}`}
          </p>
          {approval.comment && <p className="mt-1 text-muted-foreground">«{approval.comment}»</p>}
          {approval.superseded_by && (
            <p className="mt-1 flex items-center gap-1 text-muted-foreground">
              <Undo2 aria-hidden className="size-3.5" />
              Se aprobó una versión editada que la reemplaza.
            </p>
          )}
        </section>
      )}

      {footer}
    </article>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 px-5 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)]">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="break-words text-foreground">{children}</dd>
    </div>
  );
}
