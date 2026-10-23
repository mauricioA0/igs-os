import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

// The site's header navigation: a pill group on a dark bar, the active item a white pill.

export function PillGroup({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cn("inline-flex items-center gap-1 rounded-full border border-line bg-foreground-strong/5 p-1", className)}
      {...props}
    />
  );
}

export function pillClasses(active = false, className?: string) {
  return cn(
    "inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full px-4 font-body text-xs font-semibold whitespace-nowrap transition-colors duration-(--duration-fast) [&_svg]:size-3.5 [&_svg]:shrink-0",
    active ? "bg-primary text-primary-foreground" : "text-nav-idle hover:text-foreground",
    className,
  );
}

type ItemProps = { active?: boolean; className?: string; children: ReactNode };

/** A link (with `href`) or a button (without); `active` marks the current page. */
export function PillNavItem(
  props: (ItemProps & Omit<ComponentProps<typeof Link>, "className" | "children">) | (ItemProps & { href?: undefined } & Omit<ComponentProps<"button">, "className" | "children">),
) {
  const { active = false, className, children, ...rest } = props;
  if (rest.href !== undefined) {
    return (
      <Link
        aria-current={active ? "page" : undefined}
        className={pillClasses(active, className)}
        {...(rest as Omit<ComponentProps<typeof Link>, "className" | "children">)}
      >
        {children}
      </Link>
    );
  }
  const { type = "button", ...button } = rest as ComponentProps<"button">;
  return (
    <button type={type} aria-pressed={active} className={pillClasses(active, className)} {...button}>
      {children}
    </button>
  );
}

/** `<nav>` landmark wrapping a PillGroup; `label` names the landmark. */
export function PillNav({ label, className, children }: { label: string; className?: string; children: ReactNode }) {
  return (
    <nav aria-label={label} className={className}>
      <PillGroup className="relative max-w-full overflow-x-auto [scrollbar-width:none]">{children}</PillGroup>
    </nav>
  );
}
