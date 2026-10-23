// What the approver sees: exactly what will be sent, derived from the approval's action + details.

import type { ApprovalDetail } from "../types";

export type Channel = "email" | "whatsapp" | "change" | "other";

export type Preview = {
  channel: Channel;
  channelLabel: string;
  to?: string;
  subject?: string;
  body?: string;
  rows: { label: string; value: string }[];
  summary?: string;
  requestedBy?: string;
  flowLabel?: string;
  nodeLabel?: string;
  onExpiry: string;
  timezone: string;
};

const ACTION_CHANNEL: Record<string, Channel> = {
  send_email: "email",
  send_proposal: "email",
  send_whatsapp: "whatsapp",
  update_trip_item: "change",
  set_trip_status: "change",
  cancel_trip_item: "change",
};

const CHANNEL_LABEL: Record<Channel, string> = {
  email: "Email",
  whatsapp: "WhatsApp",
  change: "Cambio en la gira",
  other: "Acción",
};

function str(v: unknown): string | undefined {
  return typeof v === "string" && v.trim() ? v : undefined;
}

function rowsOf(v: unknown): { label: string; value: string }[] {
  if (!Array.isArray(v)) return [];
  return v.flatMap((r) =>
    r && typeof r === "object" && "label" in r && "value" in r ? [{ label: String(r.label), value: String(r.value) }] : [],
  );
}

export function toPreview(a: Pick<ApprovalDetail, "proposed_action" | "details" | "execution_id">, fallbackTz: string): Preview {
  const params = (a.proposed_action.params ?? {}) as Record<string, unknown>;
  const d = (a.details ?? {}) as Record<string, unknown>;
  const preview = (d.preview && typeof d.preview === "object" ? d.preview : {}) as Record<string, unknown>;
  const channel = ACTION_CHANNEL[a.proposed_action.action] ?? "other";
  const rows = rowsOf(d.payload).length ? rowsOf(d.payload) : rowsOf(params.changes ?? params.payload);
  const inFlow = Boolean(a.execution_id || d.flow);
  return {
    channel,
    channelLabel: CHANNEL_LABEL[channel],
    // The action params are what actually gets sent; the stored preview is only a fallback.
    to: str(params.to) ?? str(preview.to),
    subject: str(params.subject) ?? str(preview.subject),
    body: str(params.body) ?? str(params.summary) ?? str(preview.body),
    rows,
    summary: str(d.summary),
    requestedBy: str(d.requested_by),
    flowLabel: str(d.flow_label),
    nodeLabel: str(d.node_label),
    onExpiry:
      str(d.on_expiry) ??
      (inFlow
        ? "Si vence, no se envía nada: el flow sigue por la rama «vencida» y avisa a ops."
        : "Si vence, no se envía nada y queda registrada como vencida."),
    timezone: str(d.timezone) ?? fallbackTz,
  };
}

// "sha256:7f3a…" → "7f3a9c2e": short, stable fingerprint to compare by eye.
export function fingerprint(hash: string): string {
  const hex = hash.includes(":") ? hash.split(":")[1] : hash;
  return hex.slice(0, 8);
}

// Fields an approver may edit before approving (edit-and-approve). Anything else stays as proposed.
export const EDITABLE_PARAMS = ["to", "subject", "body"] as const;
export type EditableParam = (typeof EDITABLE_PARAMS)[number];

export function editableParams(action: { params?: Record<string, unknown> }): EditableParam[] {
  return EDITABLE_PARAMS.filter((k) => typeof (action.params ?? {})[k] === "string");
}

export function applyEdits<T extends { action: string; params?: Record<string, unknown> }>(
  action: T,
  edits: Partial<Record<EditableParam, string>>,
): T {
  const params = { ...(action.params ?? {}) };
  for (const key of editableParams(action)) {
    if (edits[key] !== undefined) params[key] = edits[key];
  }
  return { ...action, params };
}
