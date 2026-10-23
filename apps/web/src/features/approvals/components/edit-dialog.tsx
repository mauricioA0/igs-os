"use client";

import { useMemo, useState } from "react";
import { Button, Dialog, Input, Textarea } from "@/components/ui";
import { actionToText, diffLines, hasChanges } from "../lib/diff";
import { applyEdits, editableParams, type EditableParam } from "../lib/preview";
import type { ProposedAction } from "../types";
import { DiffView } from "./diff-view";

const FIELD_LABEL: Record<EditableParam, string> = { to: "Para", subject: "Asunto", body: "Mensaje" };

// Edit-and-approve: the approver edits what will be sent, sees the exact diff, and approves a
// new version (the API stores it as a new approval with its own fingerprint).
export function EditDialog({
  open,
  action,
  busy,
  onClose,
  onApprove,
}: {
  open: boolean;
  action: ProposedAction;
  busy: boolean;
  onClose: () => void;
  onApprove: (edited: ProposedAction) => void;
}) {
  const fields = editableParams(action);
  const [edits, setEdits] = useState<Partial<Record<EditableParam, string>>>({});
  const edited = useMemo(() => applyEdits(action, edits), [action, edits]);
  const diff = useMemo(() => diffLines(actionToText(action), actionToText(edited)), [action, edited]);
  const changed = hasChanges(diff);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Editar y aprobar"
      description="Se aprueba una versión nueva con estos cambios; la original queda como reemplazada."
      className="w-[min(44rem,calc(100vw-2rem))]"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancelar
          </Button>
          <Button onClick={() => onApprove(edited)} disabled={busy || !changed}>
            Aprobar con cambios
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {fields.map((key) => {
          const value = edits[key] ?? String((action.params ?? {})[key] ?? "");
          const set = (v: string) => setEdits((prev) => ({ ...prev, [key]: v }));
          return (
            <label key={key} className="block text-sm">
              <span className="font-medium">{FIELD_LABEL[key]}</span>
              {key === "body" ? (
                <Textarea value={value} onChange={(e) => set(e.target.value)} rows={8} className="mt-1 font-body" />
              ) : (
                <Input value={value} onChange={(e) => set(e.target.value)} className="mt-1" />
              )}
            </label>
          );
        })}
        <DiffView lines={diff} label={changed ? "Cambios respecto de lo propuesto" : "Sin cambios todavía"} />
      </div>
    </Dialog>
  );
}
