"use client";

import { createContext, useContext, type ComponentType, type ReactNode } from "react";
import { displayNameOf } from "./display-name";

export type Flags = Readonly<Record<string, boolean>>;

const FlagsContext = createContext<Flags>({});

export function FeatureFlagsProvider({ flags, children }: { flags: Flags; children: ReactNode }) {
  return <FlagsContext.Provider value={flags}>{children}</FlagsContext.Provider>;
}

export function useFlag(flag: string): boolean {
  return useContext(FlagsContext)[flag] ?? false;
}

/** Renders the component only when `flag` is on (off by default, e.g. in the demo tenant). */
export function withFeatureFlag<P extends object>(
  Component: ComponentType<P>,
  flag: string,
  fallback: ReactNode = null,
) {
  function WithFeatureFlag(props: P) {
    return useFlag(flag) ? <Component {...props} /> : fallback;
  }
  WithFeatureFlag.displayName = `withFeatureFlag(${displayNameOf(Component as ComponentType<never>)})`;
  return WithFeatureFlag;
}
