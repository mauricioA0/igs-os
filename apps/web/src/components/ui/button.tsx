import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "./cn";

// Pills, as on infinityglobalsports.com: Montserrat 600, white primary, white/10 secondary.
// `outline` and `destructive` are kept for older screens (`destructive` = `danger`).
type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline" | "destructive";
type Size = "sm" | "md" | "lg" | "icon";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-foreground hover:bg-primary/90",
  secondary: "bg-secondary text-nav-idle hover:bg-line-strong hover:text-foreground",
  ghost: "text-nav-idle hover:bg-secondary hover:text-foreground",
  danger: "bg-danger-fill text-danger-fill-foreground hover:bg-danger-fill/90",
  outline: "border border-line-strong text-foreground hover:border-foreground/40 hover:bg-secondary",
  destructive: "bg-danger-fill text-danger-fill-foreground hover:bg-danger-fill/90",
};

const sizes: Record<Size, string> = {
  sm: "h-8 px-4 text-xs",
  md: "h-10 px-5 text-[0.8125rem]",
  lg: "h-12 px-6 text-sm",
  icon: "size-9",
};

export function buttonClasses(variant: Variant = "primary", size: Size = "md", className?: string) {
  return cn(
    "group/button inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-body font-semibold whitespace-nowrap transition-colors duration-(--duration-fast)",
    "disabled:pointer-events-none disabled:opacity-50 aria-disabled:pointer-events-none aria-disabled:opacity-50",
    "[&_svg]:size-4 [&_svg]:shrink-0",
    variants[variant],
    sizes[size],
    className,
  );
}

type Own = { variant?: Variant; size?: Size; /** Trailing → for navigation CTAs, as on the site. */ withArrow?: boolean };

function Label({ children, withArrow }: { children: ReactNode; withArrow?: boolean }) {
  if (!withArrow) return children;
  return (
    <>
      {children}
      <ArrowRight aria-hidden className="transition-transform duration-(--duration-base) group-hover/button:translate-x-0.5" />
    </>
  );
}

export function Button({
  variant,
  size,
  withArrow,
  className,
  type = "button",
  children,
  ...props
}: ComponentProps<"button"> & Own) {
  return (
    <button type={type} className={buttonClasses(variant, size, className)} {...props}>
      <Label withArrow={withArrow}>{children}</Label>
    </button>
  );
}

export function ButtonLink({ variant, size, withArrow, className, children, ...props }: ComponentProps<typeof Link> & Own) {
  return (
    <Link className={buttonClasses(variant, size, className)} {...props}>
      <Label withArrow={withArrow}>{children}</Label>
    </Link>
  );
}

// Round icon-only button (white/10 on dark). `label` is required: it is the accessible name.
type IconSize = "sm" | "md" | "lg";
const iconSizes: Record<IconSize, string> = { sm: "size-8 [&_svg]:size-4", md: "size-10 [&_svg]:size-4", lg: "size-12 [&_svg]:size-5" };

export function iconButtonClasses(variant: "primary" | "secondary" | "ghost" = "secondary", size: IconSize = "md", className?: string) {
  return cn(
    "inline-flex shrink-0 items-center justify-center rounded-full transition-colors duration-(--duration-fast) [&_svg]:shrink-0",
    "disabled:pointer-events-none disabled:opacity-50",
    variants[variant],
    iconSizes[size],
    className,
  );
}

export function IconButton({
  label,
  variant,
  size,
  className,
  type = "button",
  ...props
}: Omit<ComponentProps<"button">, "aria-label"> & { label: string; variant?: "primary" | "secondary" | "ghost"; size?: IconSize }) {
  return (
    <button type={type} aria-label={label} title={label} className={iconButtonClasses(variant, size, className)} {...props} />
  );
}
