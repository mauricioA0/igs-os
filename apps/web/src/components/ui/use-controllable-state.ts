"use client";

import { useCallback, useState } from "react";

/**
 * One implementation of controlled + uncontrolled state for every stateful primitive
 * (docs/architecture/frontend.md §2). Pass `value` to control it; omit it to let the component
 * own the state, seeded by `defaultValue`. `onChange` fires in both modes, only on real changes.
 */
export function useControllableState<T>({
  value,
  defaultValue,
  onChange,
}: {
  value?: T;
  defaultValue: T;
  onChange?: (value: T) => void;
}): readonly [T, (next: T | ((prev: T) => T)) => void] {
  const [internal, setInternal] = useState(defaultValue);
  const isControlled = value !== undefined;
  const current = isControlled ? value : internal;

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      const resolved = typeof next === "function" ? (next as (p: T) => T)(current) : next;
      if (Object.is(resolved, current)) return;
      if (!isControlled) setInternal(resolved);
      onChange?.(resolved);
    },
    [current, isControlled, onChange],
  );

  return [current, set] as const;
}
