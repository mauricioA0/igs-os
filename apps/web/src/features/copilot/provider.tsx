"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { useStore } from "zustand";

import { createCopilotStore, type CopilotActions, type CopilotState, type CopilotStore } from "./store";
import type { CopilotTransport } from "./types";

const CopilotContext = createContext<CopilotStore | null>(null);

export function CopilotProvider({
  transport,
  children,
}: {
  transport: CopilotTransport;
  children: ReactNode;
}) {
  // Created once per provider instance; the transport is fixed for the provider's lifetime.
  const [store] = useState(() => createCopilotStore(transport));
  return <CopilotContext.Provider value={store}>{children}</CopilotContext.Provider>;
}

export function useCopilot<T>(selector: (state: CopilotState & CopilotActions) => T): T {
  const store = useContext(CopilotContext);
  if (!store) throw new Error("useCopilot must be used inside <CopilotProvider>");
  return useStore(store, selector);
}
