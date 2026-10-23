import { Check, Pencil, X } from "lucide-react";
import type { RefObject } from "react";
import { cn, Textarea } from "@/components/ui";
import { KBD_PILL, PILL, PILL_DANGER, PILL_DANGER_SOLID, PILL_GHOST, PILL_PRIMARY, PILL_SECONDARY } from "./pills";

const READ_ONLY = "Modo solo lectura: podés ver todo lo que se va a enviar, pero solo ops puede aprobar o rechazar.";

// Presentational: approve / edit / reject. Mode and texts are controlled by the container.
export function DecisionPanel({
  disabled: denied = false,
  rejecting,
  armed,
  comment,
  busy,
  disabledReason,
  canEdit,
  reasonRef,
  onComment,
  onApprove,
  onEdit,
  onStartReject,
  onCancelReject,
  onConfirmReject,
}: {
  /** Set by `withPermission` when the principal can't decide (demo, viewers). */
  disabled?: boolean;
  rejecting: boolean;
  /** First keyboard A arms the approval; a second A confirms (a stray keystroke never sends). */
  armed: boolean;
  comment: string;
  busy: boolean;
  disabledReason?: string;
  canEdit: boolean;
  reasonRef: RefObject<HTMLTextAreaElement | null>;
  onComment: (v: string) => void;
  onApprove: () => void;
  onEdit: () => void;
  onStartReject: () => void;
  onCancelReject: () => void;
  onConfirmReject: () => void;
}) {
  const reason = denied ? READ_ONLY : disabledReason;
  const disabled = busy || Boolean(reason);
  return (
    <section aria-label="Decidir" className="space-y-4 rounded-lg border border-line bg-raised p-5">
      {reason && (
        <p role="note" className="rounded-lg border border-line bg-white/5 px-4 py-3 font-body text-sm text-muted-foreground">
          {reason}
        </p>
      )}
      <label className="block font-body text-sm">
        <span className="eyebrow text-[11px] text-muted-foreground">
          {rejecting ? "Motivo del rechazo (obligatorio)" : "Comentario (opcional)"}
        </span>
        <Textarea
          ref={reasonRef}
          value={comment}
          onChange={(e) => onComment(e.target.value)}
          rows={2}
          disabled={disabled}
          placeholder={rejecting ? "Ej.: el precio está fuera de política" : "Queda en el registro de auditoría"}
          className="mt-2 rounded-lg border-line bg-card"
        />
      </label>
      {armed && (
        <p role="status" className="font-body text-sm font-semibold text-warning">
          Vas a aprobar esto tal cual. Presioná A de nuevo para confirmar o Esc para cancelar.
        </p>
      )}
      {rejecting ? (
        <div className="flex flex-wrap gap-2">
          <button type="button" className={cn(PILL, PILL_DANGER_SOLID)} onClick={onConfirmReject} disabled={disabled || !comment.trim()}>
            <X aria-hidden /> Confirmar rechazo
          </button>
          <button type="button" className={cn(PILL, PILL_GHOST)} onClick={onCancelReject} disabled={busy}>
            Cancelar
          </button>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onApprove}
            disabled={disabled}
            aria-keyshortcuts="A"
            className={cn(PILL, PILL_PRIMARY, "h-10 px-5", armed && "ring-2 ring-warning ring-offset-2 ring-offset-raised")}
          >
            <Check aria-hidden /> {armed ? "Presioná A otra vez para aprobar" : "Aprobar"}
            <kbd className={cn(KBD_PILL, "bg-card/10 text-card")}>A</kbd>
          </button>
          {canEdit && (
            <button type="button" className={cn(PILL, PILL_SECONDARY, "h-10")} onClick={onEdit} disabled={disabled} aria-keyshortcuts="E">
              <Pencil aria-hidden /> Editar y aprobar <kbd className={cn(KBD_PILL, "bg-white/10")}>E</kbd>
            </button>
          )}
          <button
            type="button"
            className={cn(PILL, PILL_DANGER, "h-10 sm:ml-auto")}
            onClick={onStartReject}
            disabled={disabled}
            aria-keyshortcuts="R"
          >
            <X aria-hidden /> Rechazar <kbd className={cn(KBD_PILL, "bg-danger/15")}>R</kbd>
          </button>
        </div>
      )}
      <p className="flex flex-wrap items-center gap-x-1.5 gap-y-1 font-body text-xs text-muted-foreground">
        <Key>J</Key> <Key>K</Key> para moverte · <Key>A</Key> dos veces para aprobar · <Key>Esc</Key> cancela. Aprobar envía
        exactamente lo que ves arriba.
      </p>
    </section>
  );
}

function Key({ children }: { children: string }) {
  return <kbd className={cn(KBD_PILL, "border border-line bg-white/5 text-foreground/70")}>{children}</kbd>;
}
