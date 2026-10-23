"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { cn } from "./cn";
import { useControllableState } from "./use-controllable-state";

// Built on native <dialog> + showModal(): focus trap, Esc to close, inert background and top layer come from the browser.
type ModalProps = {
  /** Controlled: pass `open` (+ `onOpenChange`/`onClose`). Uncontrolled: `defaultOpen`. */
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Called whenever the modal closes (Esc, backdrop, close button). Kept for existing callers. */
  onClose?: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
};

function ModalBase({
  open: openProp,
  defaultOpen = false,
  onOpenChange,
  onClose: onCloseProp,
  title,
  description,
  children,
  footer,
  className,
}: ModalProps) {
  const [open, setOpen] = useControllableState({ value: openProp, defaultValue: defaultOpen, onChange: onOpenChange });
  const onClose = () => {
    setOpen(false);
    onCloseProp?.();
  };
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={`${id}-title`}
      aria-describedby={description ? `${id}-desc` : undefined}
      onClose={onClose}
      onClick={(e) => {
        // Click on the backdrop (the dialog element itself, outside the panel) closes.
        if (e.target === e.currentTarget) onClose();
      }}
      className={cn("bg-transparent p-0 text-foreground backdrop:backdrop-blur-[1px]", className)}
    >
      <div className="flex h-full flex-col bg-popover text-popover-foreground">
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h2 id={`${id}-title`} className="type-card">
              {title}
            </h2>
            {description && (
              <p id={`${id}-desc`} className="mt-1 text-sm text-muted-foreground">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </dialog>
  );
}

export function Dialog(props: ModalProps) {
  return (
    <ModalBase
      {...props}
      className={cn("m-auto w-[min(32rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-border shadow-2xl", props.className)}
    />
  );
}

// Side panel for detail views (execution inspector, trip item, copilot).
export function Sheet({ side = "right", ...props }: ModalProps & { side?: "right" | "left" }) {
  return (
    <ModalBase
      {...props}
      className={cn(
        "my-0 h-dvh max-h-dvh w-[min(28rem,100vw)] border-border shadow-2xl",
        side === "right" ? "mr-0 ml-auto border-l" : "mr-auto ml-0 border-r",
        props.className,
      )}
    />
  );
}
