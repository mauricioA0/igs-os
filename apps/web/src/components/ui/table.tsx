import type { ComponentProps } from "react";
import { cn } from "./cn";

export function Table({ className, ...props }: ComponentProps<"table">) {
  return (
    <div className="relative w-full overflow-x-auto rounded-lg border border-border bg-card">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

export function THead({ className, ...props }: ComponentProps<"thead">) {
  return <thead className={cn("border-b border-border bg-raised/40", className)} {...props} />;
}

export function TBody({ className, ...props }: ComponentProps<"tbody">) {
  return <tbody className={cn("[&_tr:last-child]:border-0", className)} {...props} />;
}

export function TR({ className, ...props }: ComponentProps<"tr">) {
  return <tr className={cn("border-b border-border transition-colors hover:bg-foreground-strong/[0.03]", className)} {...props} />;
}

export function TH({ className, ...props }: ComponentProps<"th">) {
  return (
    <th
      scope="col"
      className={cn("h-10 px-3 text-left align-middle font-body text-2xs font-semibold tracking-[0.06em] text-muted-foreground uppercase", className)}
      {...props}
    />
  );
}

export function TD({ className, ...props }: ComponentProps<"td">) {
  return <td className={cn("px-3 py-2.5 align-middle", className)} {...props} />;
}

export function TableCaption({ className, ...props }: ComponentProps<"caption">) {
  return <caption className={cn("py-3 text-xs text-muted-foreground", className)} {...props} />;
}
