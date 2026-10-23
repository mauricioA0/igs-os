"use client";

import { createContext, useContext, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "./cn";
import { useControllableState } from "./use-controllable-state";

type Ctx = { value: string; setValue: (v: string) => void; baseId: string };
const TabsContext = createContext<Ctx | null>(null);

function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs components must be used inside <Tabs>");
  return ctx;
}

// WAI-ARIA tabs: arrow keys move between tabs, Home/End jump, only the active tab is in the tab order.
export function Tabs({
  defaultValue,
  value: controlled,
  onValueChange,
  className,
  children,
}: {
  defaultValue: string;
  value?: string;
  onValueChange?: (v: string) => void;
  className?: string;
  children: ReactNode;
}) {
  const [value, setValue] = useControllableState({ value: controlled, defaultValue, onChange: onValueChange });
  const baseId = useId();
  return (
    <TabsContext.Provider value={{ value, setValue, baseId }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const onKeyDown = (e: KeyboardEvent) => {
    const tabs = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]:not(:disabled)') ?? []);
    const i = tabs.indexOf(document.activeElement as HTMLButtonElement);
    if (i < 0) return;
    const next =
      e.key === "ArrowRight" ? tabs[(i + 1) % tabs.length] :
      e.key === "ArrowLeft" ? tabs[(i - 1 + tabs.length) % tabs.length] :
      e.key === "Home" ? tabs[0] :
      e.key === "End" ? tabs[tabs.length - 1] : undefined;
    if (next) {
      e.preventDefault();
      next.focus();
      next.click();
    }
  };
  return (
    <div
      ref={ref}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cn("relative inline-flex max-w-full items-center gap-1 overflow-x-auto rounded-full border border-line bg-foreground-strong/5 p-1 [scrollbar-width:none]", className)}
    >
      {children}
    </div>
  );
}

export function TabsTrigger({ value, disabled, children }: { value: string; disabled?: boolean; children: ReactNode }) {
  const { value: active, setValue, baseId } = useTabs();
  const selected = active === value;
  return (
    <button
      type="button"
      role="tab"
      id={`${baseId}-tab-${value}`}
      aria-selected={selected}
      aria-controls={`${baseId}-panel-${value}`}
      tabIndex={selected ? 0 : -1}
      disabled={disabled}
      onClick={() => setValue(value)}
      className={cn(
        "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-4 font-body text-xs font-semibold whitespace-nowrap transition-colors disabled:opacity-50 [&_svg]:size-3.5",
        selected ? "bg-primary text-primary-foreground" : "text-nav-idle hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, className, children }: { value: string; className?: string; children: ReactNode }) {
  const { value: active, baseId } = useTabs();
  if (active !== value) return null;
  return (
    <div
      role="tabpanel"
      id={`${baseId}-panel-${value}`}
      aria-labelledby={`${baseId}-tab-${value}`}
      tabIndex={0}
      className={cn("pt-4", className)}
    >
      {children}
    </div>
  );
}
