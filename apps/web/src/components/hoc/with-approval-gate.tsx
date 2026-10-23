"use client";

import { createContext, useCallback, useContext, useState, type ComponentType, type ReactNode } from "react";
import { displayNameOf } from "./display-name";
import { useCapability, type ToolClass } from "./permissions";

/** What the gated action would do, sent to the API as an approval request. */
export type ProposedAction = {
  action: string;
  params: Record<string, unknown>;
  summary: string;
  subject?: { type: string; id: string };
};

export type ApprovalRef = { id: string; reviewUrl?: string };

/** Provided by the approvals feature (creates the approval via the API). */
export type ProposeFn = (action: ProposedAction) => Promise<ApprovalRef>;

const ApprovalGateContext = createContext<ProposeFn | null>(null);

export function ApprovalGateProvider({ propose, children }: { propose: ProposeFn; children: ReactNode }) {
  return <ApprovalGateContext.Provider value={propose}>{children}</ApprovalGateContext.Provider>;
}

/** Props the gate injects/overrides on the wrapped action component. */
export type GatedProps = {
  onConfirm?: () => void | Promise<void>;
  pending?: boolean;
  /** Set once the action became an approval request instead of running. */
  approval?: ApprovalRef;
};

/**
 * External/destructive actions never run from the UI: when the principal may only *propose*,
 * `onConfirm` creates an approval (exact action + params) instead of executing. Allowed actions
 * call the original `onConfirm` untouched.
 */
export function withApprovalGate<P extends GatedProps>(
  Component: ComponentType<P>,
  opts: { toolClass?: ToolClass; describe: (props: P) => ProposedAction },
) {
  function WithApprovalGate(props: P) {
    const capability = useCapability(opts.toolClass ?? "external");
    const propose = useContext(ApprovalGateContext);
    const [state, setState] = useState<{ pending: boolean; approval?: ApprovalRef }>({ pending: false });

    const onConfirm = useCallback(async () => {
      if (capability !== "propose") return props.onConfirm?.();
      if (!propose) throw new Error("withApprovalGate needs an <ApprovalGateProvider>");
      setState({ pending: true });
      try {
        const approval = await propose(opts.describe(props));
        setState({ pending: false, approval });
      } catch (error) {
        setState({ pending: false });
        throw error;
      }
    }, [capability, propose, props]);

    return (
      <Component
        {...props}
        onConfirm={onConfirm}
        pending={state.pending || props.pending}
        approval={state.approval ?? props.approval}
      />
    );
  }
  WithApprovalGate.displayName = `withApprovalGate(${displayNameOf(Component as ComponentType<never>)})`;
  return WithApprovalGate;
}
