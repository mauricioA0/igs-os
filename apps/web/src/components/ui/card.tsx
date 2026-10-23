import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";

// Flat #171717 surface with a white/10 hairline, radius 8px — the site's cards.
export function Card({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("rounded-lg border border-line bg-card p-5 text-card-foreground", className)} {...props} />;
}

export function CardHeader({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="min-w-0">
        <h3 className="font-sans text-lg leading-tight font-normal tracking-[-0.03em]">{title}</h3>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

// Photo-style card: CSS stadium art behind a dark overlay, content anchored to the bottom.
// Give it a height with `min-h-*` (cn() does not merge, so the base sets none).
export function SpotlightCard({
  eyebrow,
  title,
  action,
  className,
  children,
  ...props
}: Omit<ComponentProps<"div">, "title"> & { eyebrow?: ReactNode; title?: ReactNode; action?: ReactNode }) {
  return (
    <div
      className={cn("stadium-art flex flex-col justify-end rounded-lg border border-line p-6 text-foreground", className)}
      {...props}
    >
      <span aria-hidden className="pointer-events-none absolute inset-0 bg-linear-to-t from-background via-background/75 to-transparent" />
      <div className="relative">
        {eyebrow && <p className="eyebrow text-foreground-strong">{eyebrow}</p>}
        {title && <h3 className="type-hero mt-3">{title}</h3>}
        {children && <div className="mt-3 max-w-prose text-sm text-muted-foreground">{children}</div>}
        {action && <div className="mt-5 flex flex-wrap gap-2">{action}</div>}
      </div>
    </div>
  );
}
