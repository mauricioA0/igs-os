import type { ApprovalStatus, ApprovalSummary } from "../types";
import type { Tone } from "@/components/ui";

export const STATUS_LABEL: Record<ApprovalStatus, { label: string; tone: Tone }> = {
  pending: { label: "Pendiente", tone: "warning" },
  approved: { label: "Aprobada", tone: "success" },
  rejected: { label: "Rechazada", tone: "danger" },
  expired: { label: "Vencida", tone: "neutral" },
  superseded: { label: "Reemplazada", tone: "neutral" },
};

export const RISK_LABEL: Record<ApprovalSummary["risk_class"], { label: string; tone: Tone }> = {
  external: { label: "Sale afuera", tone: "warning" },
  internal_write: { label: "Cambio interno", tone: "info" },
  read: { label: "Solo lectura", tone: "neutral" },
};
