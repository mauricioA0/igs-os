"use client";

import type { ComponentType } from "react";
import { displayNameOf } from "./display-name";
import { useCapability, type ToolClass } from "./permissions";

type Disableable = { disabled?: boolean };

/**
 * Hides (default) or disables an action the current principal can't perform. UX only: the API
 * re-checks every call. "propose" counts as allowed here — pair external actions with
 * `withApprovalGate` so they turn into approval requests.
 */
export function withPermission<P extends object>(
  Component: ComponentType<P>,
  opts: { toolClass: ToolClass; mode?: "hide" | "disable"; deniedTitle?: string },
) {
  function WithPermission(props: P) {
    const capability = useCapability(opts.toolClass);
    if (capability !== "deny") return <Component {...props} />;
    if ((opts.mode ?? "hide") === "hide") return null;
    const disabledProps: Disableable & { "aria-disabled": true; title?: string } = {
      disabled: true,
      "aria-disabled": true,
      title: opts.deniedTitle ?? "No tenés permiso para esta acción",
    };
    return <Component {...props} {...disabledProps} />;
  }
  WithPermission.displayName = `withPermission(${displayNameOf(Component as ComponentType<never>)})`;
  return WithPermission;
}
