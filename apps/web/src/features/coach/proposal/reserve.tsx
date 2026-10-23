"use client";

// Reserve flow: the coach asks to enroll the team; the API creates a pending enrollment approval
// for ops (IGS terms: US$95 non-refundable enrollment fee per traveler).
// Nothing is charged here — the copy says so, and ops sends the invoice after checking.
import { useState, useSyncExternalStore } from "react";
import { coachApi, usd, type ReserveResult } from "../api";

type Props = {
  proposalRef: string;
  enrollmentFee: number;
  enrollmentTotal: number;
  alreadyRequested: boolean;
};

export function ReserveForm({ proposalRef, enrollmentFee, enrollmentTotal, alreadyRequested }: Props) {
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">(
    alreadyRequested ? "done" : "idle",
  );
  const [result, setResult] = useState<ReserveResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (state === "done") {
    return (
      <div role="status" className="rounded-lg border border-success-border bg-success-soft p-6">
        <p className="type-card">Reservation requested</p>
        <p className="mt-2 text-sm">
          {result?.message ??
            "Our team has your request and will confirm availability and send the enrollment invoice within one business day. Nothing has been charged."}
        </p>
      </div>
    );
  }

  return (
    <form
      className="grid gap-4 rounded-lg border border-line bg-card p-6 sm:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        const data = new FormData(e.currentTarget);
        setState("sending");
        setError(null);
        try {
          const res = await coachApi.reserve(proposalRef, {
            name: String(data.get("name") ?? ""),
            email: String(data.get("email") ?? ""),
            note: String(data.get("note") ?? "") || undefined,
          });
          setResult(res);
          setState("done");
        } catch (err) {
          const status = (err as { status?: number }).status;
          setError(
            status === 422
              ? "Please check your name and email."
              : status === 429
                ? "Too many attempts — please wait a few minutes."
                : "We couldn't send your request. Please try again or reply in the chat.",
          );
          setState("error");
        }
      }}
    >
      <label className="grid gap-1 text-sm">
        <span className="eyebrow text-xs">Your name</span>
        <input name="name" required minLength={2} maxLength={120} autoComplete="name" className="h-12 rounded-full border border-line bg-white/5 px-5 text-base focus-visible:border-line-strong focus-visible:outline-2 focus-visible:outline-ring sm:text-sm" />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="eyebrow text-xs">Email</span>
        <input name="email" type="email" required maxLength={254} autoComplete="email" className="h-12 rounded-full border border-line bg-white/5 px-5 text-base focus-visible:border-line-strong focus-visible:outline-2 focus-visible:outline-ring sm:text-sm" />
      </label>
      <label className="grid gap-1 text-sm sm:col-span-2">
        <span className="eyebrow text-xs">Anything we should know? (optional)</span>
        <textarea name="note" maxLength={1000} rows={2} className="rounded-2xl border border-line bg-white/5 px-5 py-3 text-base focus-visible:border-line-strong focus-visible:outline-2 focus-visible:outline-ring sm:text-sm" />
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger sm:col-span-2">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
        <button
          type="submit"
          disabled={state === "sending"}
          className="pill pill-lg pill-primary pill-arrow"
        >
          {state === "sending" ? "Sending…" : `Reserve · ${usd(enrollmentFee)} enrollment per traveler`}
        </button>
        <p className="text-xs text-muted-foreground">
          No charge now. Enrollment for the group: {usd(enrollmentTotal)}, invoiced after we confirm availability.
        </p>
      </div>
    </form>
  );
}

const subscribe = (cb: () => void) => {
  window.addEventListener("scroll", cb, { passive: true });
  return () => window.removeEventListener("scroll", cb);
};

/** Mobile-only bar with price and the primary action, shown once the hero CTA scrolls away. */
export function StickyReserveBar({ pricePerPerson, validUntil }: { pricePerPerson: string; validUntil: string }) {
  const show = useSyncExternalStore(
    subscribe,
    () => window.scrollY > 480,
    () => false,
  );
  return (
    <div
      aria-hidden={!show}
      className={`no-print fixed inset-x-0 bottom-0 z-40 border-t border-line bg-raised/95 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur transition-transform sm:hidden ${show ? "translate-y-0" : "translate-y-full"}`}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="kpi-number text-3xl">{pricePerPerson}</p>
          <p className="mt-1 text-xs text-muted-foreground">per person · valid until {validUntil}</p>
        </div>
        <a
          href="#reserve"
          tabIndex={show ? 0 : -1}
          className="pill pill-md pill-primary pill-arrow"
        >
          Reserve
        </a>
      </div>
    </div>
  );
}

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="no-print pill pill-lg pill-secondary"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
        <path d="M12 3v12m0 0-4-4m4 4 4-4M5 21h14" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Download PDF
    </button>
  );
}
