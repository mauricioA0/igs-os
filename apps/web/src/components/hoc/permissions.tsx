"use client";

import { createContext, useContext, type ReactNode } from "react";

/** Mirrors the API's tool classes (`approvals.risk_class`, docs/architecture/security.md). */
export type ToolClass = "read" | "internal_write" | "external";
export type Role = "owner" | "ops" | "sales" | "viewer";

export type Principal = {
  kind: "user" | "demo" | "api_key";
  role: Role;
};

/** What the UI may offer for an action. The API enforces the same rules again. */
export type Capability = "allow" | "propose" | "deny";

/**
 * UX mirror of `igs_common.domain.tools.decide`:
 * - reads are open to everyone;
 * - internal writes need owner/ops/sales;
 * - external/destructive actions are never executed from the UI — at most proposed as an
 *   approval. The public demo can propose (so the approval card shows) but never approve.
 */
export function capabilityFor(principal: Principal | null, toolClass: ToolClass): Capability {
  if (toolClass === "read") return "allow";
  if (!principal) return "deny";
  if (principal.kind === "demo") return toolClass === "external" ? "propose" : "deny";
  if (principal.role === "viewer") return "deny";
  return toolClass === "external" ? "propose" : "allow";
}

const PrincipalContext = createContext<Principal | null>(null);

export function PrincipalProvider({ principal, children }: { principal: Principal | null; children: ReactNode }) {
  return <PrincipalContext.Provider value={principal}>{children}</PrincipalContext.Provider>;
}

export function usePrincipal(): Principal | null {
  return useContext(PrincipalContext);
}

export function useCapability(toolClass: ToolClass): Capability {
  return capabilityFor(usePrincipal(), toolClass);
}
