import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/components/ui";

// Site-style navigation pill (contract: primary = white pill, secondary = white/10). Kept local so
// the dashboard doesn't depend on when the shared Button gains `withArrow`.
export function PillLink({
  href,
  children,
  variant = "secondary",
  className,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary";
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex h-9 items-center gap-1.5 rounded-full px-5 font-body text-xs font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground",
        variant === "primary"
          ? "bg-foreground text-background hover:bg-foreground/90"
          : "bg-foreground/10 text-foreground/70 hover:text-foreground",
        className,
      )}
    >
      {children}
      <span aria-hidden>→</span>
    </Link>
  );
}
