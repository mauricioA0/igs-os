"use client";

import { AlertTriangle, CheckCircle2, Inbox } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import { capabilityFor, PrincipalProvider, withPermission } from "@/components/hoc";
import { EmptyState } from "@/components/ui";
import { principalFromMe } from "@/features/_shared/providers";
import { decideApproval, fetchApproval } from "./actions";
import { ApprovalDetailView } from "./components/approval-detail";
import { ApprovalList, filterApprovals, type ListView } from "./components/approval-list";
import { DecisionPanel } from "./components/decision-panel";
import { DiffView } from "./components/diff-view";
import { EditDialog } from "./components/edit-dialog";
import { actionToText, diffLines, type DiffLine } from "./lib/diff";
import { DEFAULT_TIMEZONE } from "./lib/expiry";
import { effectiveStatus } from "./lib/status";
import { commandForKey, moveSelection, selectionAfterRemoval } from "./lib/keyboard";
import { editableParams, fingerprint, toPreview } from "./lib/preview";
import type { ApiProblem, ApprovalDetail, ApprovalSummary, Me, ProposedAction } from "./types";

// Deciding is an internal write for the approver (the approved action itself runs server-side).
const GuardedDecisionPanel = withPermission(DecisionPanel, {
  toolClass: "internal_write",
  mode: "disable",
  deniedTitle: "Solo ops puede decidir",
});

type Notice =
  | { kind: "changed"; diff: DiffLine[] }
  | { kind: "error"; message: string }
  | { kind: "done"; message: string };

const PROBLEM_COPY: Record<string, string> = {
  "already-decided": "Otra persona ya decidió esta aprobación. Actualizamos la vista.",
  expired: "La aprobación venció antes de que la decidieras. No se envió nada.",
  forbidden: "Esta aprobación está asignada a otro rol.",
  "not-found": "Esta aprobación ya no existe.",
  "network-error": "No pudimos conectar con la API. Probá de nuevo.",
};

function useNow(initial: number): Date {
  const [now, setNow] = useState(initial);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  return new Date(now);
}

// Client container: owns selection, filters, keyboard and the decide flow; renders presentational parts.
export function ApprovalsInbox({
  initialItems,
  initialDetail,
  me,
  serverNow,
}: {
  initialItems: ApprovalSummary[];
  initialDetail?: ApprovalDetail;
  me: Me;
  serverNow: number;
}) {
  const router = useRouter();
  const now = useNow(serverNow);
  const [items, setItems] = useState(initialItems);
  const [details, setDetails] = useState<Record<string, ApprovalDetail>>(
    initialDetail ? { [initialDetail.id]: initialDetail } : {},
  );
  const [view, setView] = useState<ListView>("pending");
  const [risk, setRisk] = useState<"all" | "external" | "internal">("all");
  const [selectedId, setSelectedId] = useState(initialDetail?.id);
  const [comment, setComment] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [busy, startTransition] = useTransition();
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  // After router.refresh() the server sends a fresh list: adopt it (state derived from props).
  const [prevInitial, setPrevInitial] = useState(initialItems);
  if (prevInitial !== initialItems) {
    setPrevInitial(initialItems);
    setItems(initialItems);
  }

  const minute = Math.floor(now.getTime() / 60_000); // re-filter when an approval expires
  const visible = useMemo(() => filterApprovals(items, view, risk, new Date(minute * 60_000)), [items, view, risk, minute]);
  const counts = useMemo(() => {
    const at = new Date(minute * 60_000);
    return {
      pending: filterApprovals(items, "pending", risk, at).length,
      resolved: filterApprovals(items, "resolved", risk, at).length,
      all: filterApprovals(items, "all", risk, at).length,
    };
  }, [items, risk, minute]);
  const detail = selectedId ? details[selectedId] : undefined;
  const preview = detail ? toPreview(detail, DEFAULT_TIMEZONE) : undefined;
  const decidable = detail ? effectiveStatus(detail, now) === "pending" : false;
  const [armed, setArmed] = useState(false);
  useEffect(() => {
    if (!armed) return;
    const t = setTimeout(() => setArmed(false), 4000);
    return () => clearTimeout(t);
  }, [armed]);

  const select = useCallback(
    (id: string | undefined) => {
      setSelectedId(id);
      setComment("");
      setRejecting(false);
      setArmed(false);
      setNotice(null);
      // Shareable ?id= without a server round trip (router.replace would re-render the route and
      // remount the inbox, dropping focus mid-decision).
      window.history.replaceState(null, "", id ? `/ops/approvals?id=${id}` : "/ops/approvals");
    },
    [],
  );

  // Load the detail of the selected approval on demand.
  useEffect(() => {
    if (!selectedId || details[selectedId]) return;
    let live = true;
    void fetchApproval(selectedId).then((r) => {
      if (!live) return;
      if (r.ok) setDetails((d) => ({ ...d, [r.data.id]: r.data }));
      else setNotice({ kind: "error", message: PROBLEM_COPY[r.problem.code] ?? r.problem.title });
    });
    return () => {
      live = false;
    };
  }, [selectedId, details]);

  const afterDecision = useCallback(
    (decidedId: string, updated: ApprovalDetail, message: string, replaces?: string) => {
      const pendingIds = filterApprovals(items, "pending", risk, new Date()).map((a) => a.id);
      setItems((prev) => {
        const next = prev.map((a) => (a.id === decidedId ? { ...a, status: replaces ? ("superseded" as const) : updated.status } : a));
        return replaces ? [{ ...updated }, ...next] : next;
      });
      setDetails((d) => ({ ...d, [updated.id]: updated }));
      setNotice({ kind: "done", message });
      const nextId = view === "pending" ? selectionAfterRemoval(pendingIds, decidedId) : updated.id;
      setSelectedId(nextId);
      window.history.replaceState(null, "", nextId ? `/ops/approvals?id=${nextId}` : "/ops/approvals");
      setComment("");
      setRejecting(false);
      setArmed(false);
      router.refresh();
    },
    [items, risk, view, router],
  );

  const handleProblem = useCallback(async (id: string, problem: ApiProblem, before: ApprovalDetail) => {
    const fresh = await fetchApproval(id);
    if (fresh.ok) {
      setDetails((d) => ({ ...d, [id]: fresh.data }));
      setItems((prev) => prev.map((a) => (a.id === id ? { ...a, status: fresh.data.status } : a)));
    }
    if (problem.code === "approval-changed" && fresh.ok) {
      setNotice({
        kind: "changed",
        diff: diffLines(actionToText(before.proposed_action), actionToText(fresh.data.proposed_action)),
      });
      return;
    }
    setNotice({ kind: "error", message: PROBLEM_COPY[problem.code] ?? problem.detail ?? problem.title });
  }, []);

  const decide = useCallback(
    (decision: "approved" | "rejected", editedAction?: ProposedAction) => {
      if (!detail) return;
      const before = detail;
      startTransition(async () => {
        const r = await decideApproval(before.id, {
          decision,
          payload_hash: before.payload_hash,
          comment: comment.trim() || null,
          edited_action: editedAction ?? null,
        });
        if (!r.ok) return handleProblem(before.id, r.problem, before);
        setEditing(false);
        const out = r.data;
        if (out.superseded) {
          afterDecision(
            before.id,
            out.approval,
            `Aprobada con cambios. Nueva huella ${fingerprint(out.approval.payload_hash)} (reemplaza ${fingerprint(before.payload_hash)}).`,
            out.superseded,
          );
        } else {
          afterDecision(before.id, out.approval, decision === "approved" ? "Aprobada. El flow sigue con lo que viste." : "Rechazada. No se envió nada.");
        }
      });
    },
    [detail, comment, afterDecision, handleProblem],
  );

  const principal = principalFromMe(me);
  const canAct = Boolean(decidable) && capabilityFor(principal, "internal_write") === "allow";

  // J/K/A/R/E, ignored while typing or with a dialog open.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (editing || busy) return;
      if (e.key === "Escape") {
        setArmed(false);
        setRejecting(false);
        return;
      }
      // Writing a rejection reason: no single-key shortcut may fire, even before focus lands.
      if (rejecting) return;
      const cmd = commandForKey({ key: e.key, metaKey: e.metaKey, ctrlKey: e.ctrlKey, altKey: e.altKey, target: e.target as HTMLElement | null });
      if (!cmd) return;
      if (cmd === "next" || cmd === "prev") {
        e.preventDefault();
        select(moveSelection(visible.map((a) => a.id), selectedId, cmd));
        return;
      }
      if (!canAct) return;
      e.preventDefault();
      if (cmd === "approve") {
        if (armed) decide("approved");
        else setArmed(true);
      }
      if (cmd !== "approve") setArmed(false);
      if (cmd === "reject") setRejecting(true);
      if (cmd === "edit" && detail && editableParams(detail.proposed_action).length) setEditing(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, busy, rejecting, visible, selectedId, canAct, decide, detail, select, armed]);

  // Move focus to the reason as soon as the reject step renders.
  useEffect(() => {
    if (rejecting) reasonRef.current?.focus();
  }, [rejecting, selectedId]);

  const banner =
    notice?.kind === "changed" ? (
      <div role="alert" className="space-y-3 rounded-lg border border-warning/30 bg-warning/5 p-4 font-body text-sm">
        <p className="flex items-center gap-2 font-semibold">
          <AlertTriangle aria-hidden className="size-4" /> El contenido cambió mientras lo revisabas. Revisá la diferencia y decidí de nuevo.
        </p>
        <DiffView lines={notice.diff} label="Antes → ahora" />
      </div>
    ) : notice?.kind === "error" ? (
      <p role="alert" className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/10 p-4 font-body text-sm">
        <AlertTriangle aria-hidden className="size-4" /> {notice.message}
      </p>
    ) : notice?.kind === "done" ? (
      <p role="status" className="flex items-center gap-2 rounded-lg border border-success/30 bg-success/10 p-4 font-body text-sm">
        <CheckCircle2 aria-hidden className="size-4" /> {notice.message}
      </p>
    ) : null;

  return (
    <PrincipalProvider principal={principal}>
      <div className="grid items-start gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <ApprovalList
          items={visible}
          counts={counts}
          view={view}
          risk={risk}
          selectedId={selectedId}
          now={now}
          onView={setView}
          onRisk={setRisk}
          onSelect={select}
        />
        <div className="min-w-0 rounded-xl border border-line bg-card p-5 sm:p-8 lg:sticky lg:top-20" aria-live="polite">
          {!selectedId ? (
            <div className="space-y-4">
              {banner}
              <EmptyState icon={<Inbox />} title="Bandeja al día" description="Cuando un agente o un flow necesite tu OK, aparece acá." />
            </div>
          ) : !detail || !preview ? (
            notice ? banner : <DetailSkeleton />
          ) : (
            <>
              <ApprovalDetailView
                approval={detail}
                preview={preview}
                now={now}
                banner={banner}
                footer={
                  decidable ? (
                    <GuardedDecisionPanel
                      rejecting={rejecting}
                      armed={armed}
                      comment={comment}
                      busy={busy}
                      canEdit={editableParams(detail.proposed_action).length > 0}
                      reasonRef={reasonRef}
                      onComment={setComment}
                      onApprove={() => decide("approved")}
                      onEdit={() => setEditing(true)}
                      onStartReject={() => setRejecting(true)}
                      onCancelReject={() => setRejecting(false)}
                      onConfirmReject={() => decide("rejected")}
                    />
                  ) : null
                }
              />
              {editing && (
                <EditDialog
                  key={detail.id}
                  open={editing}
                  action={detail.proposed_action}
                  busy={busy}
                  onClose={() => setEditing(false)}
                  onApprove={(edited) => decide("approved", edited)}
                />
              )}
            </>
          )}
        </div>
      </div>
    </PrincipalProvider>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-4" aria-label="Cargando aprobación">
      <div className="h-6 w-40 animate-pulse rounded-full bg-white/5" />
      <div className="h-10 w-3/4 animate-pulse rounded-lg bg-white/5" />
      <div className="h-48 animate-pulse rounded-lg bg-white/5" />
    </div>
  );
}
