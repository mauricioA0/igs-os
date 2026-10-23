import { Fragment, type ReactNode } from "react";

// Pretty JSON with CEL templates ({{ … }}) highlighted. Text nodes only (no innerHTML).
export function JsonView({ value, className = "" }: { value: unknown; className?: string }) {
  const text = value === undefined || value === null ? "—" : JSON.stringify(value, null, 2);
  return (
    <pre className={`overflow-auto rounded-lg border border-line bg-background p-2.5 font-mono text-foreground text-xs leading-relaxed ${className}`}>
      {highlight(text)}
    </pre>
  );
}

function highlight(text: string): ReactNode[] {
  return text.split(/(\{\{[^}]*\}\})/g).map((part, i) =>
    part.startsWith("{{") ? (
      <mark key={i} className="rounded bg-info-soft px-0.5 text-info">
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function Section({ title, children, defaultOpen = true }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  return (
    <details open={defaultOpen} className="group border-b border-line px-4 py-3">
      <summary className="eyebrow flex cursor-pointer list-none items-center justify-between hover:text-foreground">
        {title}
        <span aria-hidden className="transition group-open:rotate-90">›</span>
      </summary>
      <div className="mt-2.5 space-y-2 font-body text-sm">{children}</div>
    </details>
  );
}
