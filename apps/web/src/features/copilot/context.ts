import type { ContextChip } from "./types";

/**
 * What the user is looking at, derived from the ops route. Only ids leave the browser; the
 * server resolves them under the caller's tenant (the tenant itself is never a chip).
 */
export function chipsFromPath(pathname: string, labels: Record<string, string> = {}): ContextChip[] {
  const segments = pathname.split("?")[0].split("/").filter(Boolean);
  const at = (name: string) => {
    const i = segments.indexOf(name);
    return i !== -1 && segments[i + 1] ? decodeURIComponent(segments[i + 1]) : undefined;
  };
  const chips: ContextChip[] = [];
  const trip = at("trips");
  if (trip) chips.push({ kind: "trip", id: trip, label: labels[trip] });
  const account = at("accounts");
  if (account) chips.push({ kind: "account", id: account, label: labels[account] });
  const lead = at("leads");
  if (lead) chips.push({ kind: "lead", id: lead, label: labels[lead] });
  const flow = at("flows");
  if (flow) chips.push({ kind: "flow", id: flow, label: labels[flow] });
  const execution = at("executions");
  if (execution) chips.push({ kind: "execution", id: execution, label: labels[execution] });
  return chips;
}

export type Screen = "today" | "trips" | "trip" | "accounts" | "account" | "approvals" | "flows" | "flow" | "leads" | "other";

export function screenFromPath(pathname: string): Screen {
  const s = pathname.split("?")[0].split("/").filter(Boolean);
  const i = s.indexOf("ops");
  const section = i === -1 ? undefined : s[i + 1];
  const hasId = i !== -1 && Boolean(s[i + 2]);
  switch (section) {
    case undefined:
      return i === -1 ? "other" : "today";
    case "trips":
      return hasId ? "trip" : "trips";
    case "accounts":
      return hasId ? "account" : "accounts";
    case "flows":
      return hasId ? "flow" : "flows";
    case "approvals":
      return "approvals";
    case "leads":
      return "leads";
    default:
      return "other";
  }
}

export const CHIP_KIND_LABEL: Record<ContextChip["kind"], string> = {
  trip: "Gira",
  trip_day: "Día",
  lead: "Lead",
  account: "Cliente",
  flow: "Flow",
  execution: "Ejecución",
};
