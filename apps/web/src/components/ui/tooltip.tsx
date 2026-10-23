import type { ReactNode } from "react";
import { cn } from "./cn";

// CSS-only tooltip: shows on hover and keyboard focus of the trigger. The trigger must be focusable
// and the text is exposed via aria-describedby, so it is announced like a native description.
export function Tooltip({
  id,
  content,
  side = "top",
  children,
  className,
}: {
  id: string;
  content: ReactNode;
  side?: "top" | "bottom";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("group/tooltip relative inline-flex", className)} aria-describedby={id}>
      {children}
      <span
        id={id}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute left-1/2 z-50 w-max max-w-64 -translate-x-1/2 rounded-sm bg-primary px-2 py-1 text-xs text-primary-foreground opacity-0 shadow-md transition-opacity",
          "group-focus-within/tooltip:opacity-100 group-hover/tooltip:opacity-100",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
        )}
      >
        {content}
      </span>
    </span>
  );
}
