import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

export const fieldClasses =
  "h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground " +
  "disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-danger";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(fieldClasses, className)} {...props} />;
}

export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(fieldClasses, "h-auto min-h-24 py-2", className)} {...props} />;
}

export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("text-sm font-medium", className)} {...props} />;
}

// Label + control + hint/error. Pass the same `id` to the control with `fieldA11y(id, …)` so all three are announced.
export function fieldA11y(id: string, { hint, error }: { hint?: unknown; error?: unknown } = {}) {
  return {
    id,
    "aria-describedby": error ? `${id}-error` : hint ? `${id}-hint` : undefined,
    "aria-invalid": error ? true : undefined,
  };
}

export function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
