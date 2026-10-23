"use client";

import type { ReactNode } from "react";
import {
  ApprovalGateProvider,
  FeatureFlagsProvider,
  PrincipalProvider,
  TrackingProvider,
  type Flags,
  type Principal,
  type ProposeFn,
  type Role,
  type TrackFn,
} from "@/components/hoc";
import type { Schema } from "@/lib/api";

const ROLES: readonly Role[] = ["owner", "ops", "sales", "viewer"];

/** `/v1/me` → the principal the HOCs read. Unknown roles degrade to read-only. */
export function principalFromMe(me: Schema<"Me">): Principal {
  const role = (ROLES as readonly string[]).includes(me.role) ? (me.role as Role) : "viewer";
  return { kind: me.kind, role };
}

const proposeUnavailable: ProposeFn = async () => {
  throw new Error("Proposing approvals isn't wired on this surface");
};

/**
 * Client-side context for the HOCs, mounted once per surface layout (ops shell, public pages).
 * The layout (a Server Component) fetches `/v1/me` and passes the principal down.
 */
export function AppProviders({
  principal,
  flags = {},
  propose = proposeUnavailable,
  track,
  children,
}: {
  principal: Principal | null;
  flags?: Flags;
  propose?: ProposeFn;
  track?: TrackFn;
  children: ReactNode;
}) {
  const tree = (
    <PrincipalProvider principal={principal}>
      <FeatureFlagsProvider flags={flags}>
        <ApprovalGateProvider propose={propose}>{children}</ApprovalGateProvider>
      </FeatureFlagsProvider>
    </PrincipalProvider>
  );
  return track ? <TrackingProvider track={track}>{tree}</TrackingProvider> : tree;
}
