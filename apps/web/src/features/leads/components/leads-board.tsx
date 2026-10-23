"use client";

import { Bot, ChevronLeft, ChevronRight, Globe, Info, Lock, Mail, MessageSquare, Users } from "lucide-react";
import { useState, useTransition } from "react";
import { Button, cn, Dialog, Field, fieldA11y, Textarea } from "@/components/ui";
import { fmtRelative, usd } from "@/features/ops-shell/format";
import { country, GENDER, SPORT } from "@/features/ops-shell/labels";
import { updateLeadStatus } from "../actions";
import { type Lead, LEAD_STAGE, type LeadStage } from "../data";

const STAGES: LeadStage[] = ["new", "qualified", "proposal_sent", "won", "lost"];

// Mirrors igs_common.domain.transitions (lead), so the board never offers a move the API rejects.
const ALLOWED: Record<LeadStage, LeadStage[]> = {
  new: ["qualified", "lost"],
  qualified: ["proposal_sent", "lost"],
  proposal_sent: ["won", "lost", "qualified"],
  won: [],
  lost: ["qualified"],
};

function canMove(from: LeadStage, to: LeadStage): boolean {
  return ALLOWED[from].includes(to);
}

const SOURCE = {
  chat: { label: "Chat", icon: MessageSquare },
  web: { label: "Web", icon: Globe },
  email: { label: "Email", icon: Mail },
  referral: { label: "Referido", icon: Users },
} as const;

export function LeadsBoard({
  initial,
  nowIso,
  live,
  readOnlyReason,
}: {
  initial: Lead[];
  nowIso: string;
  /** False when the API has no leads endpoint and the board shows sample data (local moves only). */
  live: boolean;
  /** Set when this viewer can't write (the public demo); moves are disabled with this reason. */
  readOnlyReason?: string;
}) {
  const now = new Date(nowIso);
  const [leads, setLeads] = useState(initial);
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<LeadStage | null>(null);
  const [losing, setLosing] = useState<Lead | null>(null);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState<{ tone: "info" | "danger"; text: string } | null>(null);
  const [, startTransition] = useTransition();
  const locked = live && Boolean(readOnlyReason);

  function move(id: string, stage: LeadStage) {
    const lead = leads.find((l) => l.id === id);
    if (!lead || lead.stage === stage || locked) return;
    if (live && !canMove(lead.stage, stage)) {
      setNotice({
        tone: "danger",
        text: `${lead.organization} no puede pasar de «${LEAD_STAGE[lead.stage]}» a «${LEAD_STAGE[stage]}».`,
      });
      return;
    }
    if (stage === "lost") {
      setReason("");
      setLosing(lead);
      return;
    }
    commit(lead, stage);
  }

  function commit(lead: Lead, stage: LeadStage, lostReason?: string) {
    setLeads((prev) => prev.map((l) => (l.id === lead.id ? { ...l, stage, lostReason } : l)));
    if (!live) return;
    setNotice(null);
    startTransition(async () => {
      const result = await updateLeadStatus(lead.id, stage, lostReason);
      if (result.ok) {
        setNotice({ tone: "info", text: `${lead.organization} pasó a «${LEAD_STAGE[stage]}».` });
      } else {
        setLeads((prev) => prev.map((l) => (l.id === lead.id ? lead : l)));
        setNotice({ tone: "danger", text: result.message });
      }
    });
  }

  function shift(lead: Lead, dir: -1 | 1) {
    const next = STAGES[STAGES.indexOf(lead.stage) + dir];
    if (next) move(lead.id, next);
  }

  function canShift(lead: Lead, dir: -1 | 1): boolean {
    const next = STAGES[STAGES.indexOf(lead.stage) + dir];
    return Boolean(next) && (!live || canMove(lead.stage, next));
  }

  return (
    <div className="space-y-3">
      {locked && (
        <p className="flex items-start gap-2 rounded-lg border border-line bg-white/5 px-4 py-3 font-body text-xs text-muted-foreground">
          <Lock className="mt-px size-3.5 shrink-0" aria-hidden />
          {readOnlyReason}
        </p>
      )}
      <p
        role="status"
        aria-live="polite"
        className={cn(
          "flex items-start gap-2 rounded-lg border px-4 py-3 font-body text-xs",
          !notice && "sr-only",
          notice?.tone === "danger" ? "border-danger/30 bg-danger/10" : "border-info/30 bg-info/10",
        )}
      >
        {notice && (
          <Info className={cn("mt-px size-3.5 shrink-0", notice.tone === "danger" ? "text-danger" : "text-info")} aria-hidden />
        )}
        {notice?.text}
      </p>
    {/* Scrolls sideways on narrow screens: focusable so keyboard users can scroll it (WCAG 2.1.1). */}
    <div
      role="region"
      aria-label="Tablero de leads por etapa"
      tabIndex={0}
      className="relative -mx-4 overflow-x-auto px-4 pb-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:-mx-8 sm:px-8 lg:-mx-10 lg:px-10"
    >
      <div className="grid min-w-6xl grid-cols-5 gap-4">
        {STAGES.map((stage) => {
          const column = leads.filter((l) => l.stage === stage);
          const total = column.reduce((n, l) => n + l.valueUsd, 0);
          return (
            <section
              key={stage}
              aria-labelledby={`col-${stage}`}
              onDragOver={(e) => {
                e.preventDefault();
                setOver(stage);
              }}
              onDragLeave={() => setOver((s) => (s === stage ? null : s))}
              onDrop={(e) => {
                e.preventDefault();
                if (dragId) move(dragId, stage);
                setDragId(null);
                setOver(null);
              }}
              className={cn(
                "flex min-h-96 flex-col rounded-xl border p-2 transition-colors",
                over === stage ? "border-foreground/60 bg-raised" : "border-line bg-white/[0.02]",
              )}
            >
              <header className="mb-3 border-b border-line px-2 pt-2 pb-3">
                <div className="flex items-center justify-between gap-2">
                  <h2
                    id={`col-${stage}`}
                    className="font-display text-xl leading-none font-extrabold tracking-tight text-foreground uppercase"
                  >
                    {LEAD_STAGE[stage]}
                  </h2>
                  <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-white/10 px-2 font-body text-[11px] font-semibold tabular-nums text-foreground/80">
                    {column.length}
                  </span>
                </div>
                <p className="kpi-number mt-2 text-2xl text-muted-headline">{usd(total)}</p>
              </header>
              <ul className="flex flex-1 flex-col gap-2">
                {column.map((lead) => {
                  const Source = SOURCE[lead.source].icon;
                  const idx = STAGES.indexOf(lead.stage);
                  return (
                    <li
                      key={lead.id}
                      draggable={!locked}
                      onDragStart={() => setDragId(lead.id)}
                      onDragEnd={() => setDragId(null)}
                      className={cn(
                        "group rounded-lg border border-line bg-card p-4 transition-colors hover:border-line-strong",
                        !locked && "cursor-grab active:cursor-grabbing",
                        dragId === lead.id && "opacity-40",
                        // Lost leads read as archived without dimming text below AA contrast.
                        lead.stage === "lost" && "border-dashed bg-transparent",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="type-small-title truncate pb-0.5 text-foreground">{lead.organization}</p>
                          <p className="mt-1.5 truncate font-body text-xs text-muted-foreground">{lead.program}</p>
                        </div>
                        <span
                          className={cn("mt-1 size-2 shrink-0 rounded-full", country(lead.country).dot)}
                          title={country(lead.country).label}
                        />
                      </div>
                      <p className="eyebrow mt-3 text-[10px] leading-4 text-muted-foreground">
                        {[`${SPORT[lead.sport] ?? lead.sport} ${GENDER[lead.gender] ?? ""}`.trim(), `Nivel ${lead.levelScore}`, `${lead.groupSize} pax`].join(" · ")}
                      </p>
                      <p className="mt-1 font-body text-xs text-muted-foreground">{lead.travelWindow}</p>
                      <p className="mt-3 flex gap-2 border-l-2 border-line-strong pl-3 font-body text-xs leading-5 text-muted-foreground">
                        <Bot className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                        <span>
                          <span className="sr-only">Resumen del agente: </span>
                          {lead.agentSummary}
                        </span>
                      </p>
                      <p className="mt-3 inline-flex max-w-full items-center gap-1 rounded-full bg-white/10 px-3 py-1 font-body text-[11px] font-semibold text-foreground">
                        <span aria-hidden>→</span> <span className="truncate">{lead.nextStep}</span>
                      </p>
                      {lead.stage === "lost" && lead.lostReason && (
                        <p className="mt-2 font-body text-xs text-muted-foreground">Motivo: {lead.lostReason}</p>
                      )}
                      <div className="mt-3 flex items-center justify-between border-t border-line pt-3 font-body text-xs text-muted-foreground">
                        <span className="flex items-center gap-1">
                          <Source className="size-3.5" aria-hidden /> {SOURCE[lead.source].label} · {fmtRelative(lead.lastActivity, now)}
                        </span>
                        <span className="font-display text-base font-extrabold tabular-nums text-foreground">{usd(lead.valueUsd)}</span>
                      </div>
                      {/* Keyboard alternative to drag and drop. */}
                      <div
                        className={cn(
                          "mt-2 flex justify-between gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100",
                          locked && "hidden",
                        )}
                      >
                        <button
                          onClick={() => shift(lead, -1)}
                          disabled={!canShift(lead, -1)}
                          className="inline-flex h-7 items-center gap-0.5 rounded-full bg-white/5 px-2.5 font-body text-[11px] font-semibold text-foreground/70 hover:bg-white/10 hover:text-foreground disabled:invisible"
                          aria-label={`Mover ${lead.organization} a ${LEAD_STAGE[STAGES[idx - 1]] ?? ""}`}
                        >
                          <ChevronLeft className="size-3.5" aria-hidden /> {LEAD_STAGE[STAGES[idx - 1]]}
                        </button>
                        <button
                          onClick={() => shift(lead, 1)}
                          disabled={!canShift(lead, 1)}
                          className="inline-flex h-7 items-center gap-0.5 rounded-full bg-white/5 px-2.5 font-body text-[11px] font-semibold text-foreground/70 hover:bg-white/10 hover:text-foreground disabled:invisible"
                          aria-label={`Mover ${lead.organization} a ${LEAD_STAGE[STAGES[idx + 1]] ?? ""}`}
                        >
                          {LEAD_STAGE[STAGES[idx + 1]]} <ChevronRight className="size-3.5" aria-hidden />
                        </button>
                      </div>
                    </li>
                  );
                })}
                {column.length === 0 && (
                  <li className="flex flex-1 items-center justify-center rounded-lg border border-dashed border-line p-6 text-center font-body text-xs text-muted-foreground">
                    Soltá un lead acá
                  </li>
                )}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
      <Dialog
        open={losing !== null}
        onOpenChange={(open) => !open && setLosing(null)}
        title={losing ? `Marcar ${losing.organization} como perdido` : "Marcar como perdido"}
        description="El motivo queda en el lead y alimenta los reportes de pérdidas."
        footer={
          <>
            <Button variant="ghost" onClick={() => setLosing(null)}>
              Cancelar
            </Button>
            <Button
              disabled={reason.trim().length < 3}
              onClick={() => {
                if (losing) commit(losing, "lost", reason.trim());
                setLosing(null);
              }}
            >
              Marcar perdido
            </Button>
          </>
        }
      >
        <Field id="lost-reason" label="Motivo" hint="Por ejemplo: eligió otra agencia, presupuesto, fechas.">
          <Textarea
            {...fieldA11y("lost-reason", { hint: true })}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            required
          />
        </Field>
      </Dialog>
    </div>
  );
}
