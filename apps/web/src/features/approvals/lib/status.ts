import type { ApprovalStatus } from "../types";

// A pending approval past its expiry can't be decided: treat it as expired everywhere in the UI
// (the API rejects it with 409 `expired` and the expiry job flips the row later).
export function effectiveStatus(a: { status: ApprovalStatus; expires_at?: string | null }, now: Date): ApprovalStatus {
  if (a.status === "pending" && a.expires_at && new Date(a.expires_at).getTime() <= now.getTime()) return "expired";
  return a.status;
}
