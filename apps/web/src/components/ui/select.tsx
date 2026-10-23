import type { ComponentProps } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "./cn";
import { fieldClasses } from "./input";

// Native <select> styled to match inputs: keyboard and screen-reader behavior for free.
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select className={cn(fieldClasses, "appearance-none pr-9", className)} {...props}>
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
    </div>
  );
}
