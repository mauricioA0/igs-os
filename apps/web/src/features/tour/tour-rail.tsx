"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";
import { cn } from "@/components/ui";
import { TOUR_PARAM, TOUR_STEPS, parseStep, stepUrl } from "./steps";

// How long to wait for a step's anchor before telling the visitor it's still loading. The rail
// itself never blocks: Next/Back work whether or not the spotlighted element has rendered.
const ANCHOR_WAIT_MS = 8000;
const SPOTLIGHT_CLASS = "tour-spotlight";

type AnchorState = "searching" | "found" | "missing";

/**
 * Bottom step rail for the guided demo. Driven by `?tour=<n>` so it needs no login, survives
 * reloads and shareable links, and works on any route that renders it (mount once in a layout).
 */
export function TourRail() {
  const params = useSearchParams();
  const step = parseStep(params.get(TOUR_PARAM));
  if (step === null) return null;
  return <Rail step={step} />;
}

function Rail({ step }: { step: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const current = TOUR_STEPS[step - 1];
  const onStepPage = pathname === current.href.split("?")[0];
  const anchor = useAnchor(onStepPage ? current.anchor : null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, [step]);

  const go = useCallback((n: number) => router.push(stepUrl(n)), [router]);
  const exit = useCallback(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete(TOUR_PARAM);
    router.replace(`${url.pathname}${url.search}`);
  }, [router]);

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Escape") exit();
    else if (e.key === "ArrowRight" && step < TOUR_STEPS.length) go(step + 1);
    else if (e.key === "ArrowLeft" && step > 1) go(step - 1);
  };

  return (
    <nav
      aria-label="Guided demo tour"
      onKeyDown={onKeyDown}
      className="tour-rail fixed inset-x-0 bottom-0 z-50 px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
    >
      <div className="tour-rail-bar mx-auto flex max-w-5xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:gap-5 sm:py-2.5 sm:pl-2.5">
        <ol className="tour-rail-steps flex shrink-0 items-center gap-1 self-start p-1 sm:self-auto" aria-label="Tour steps">
          {TOUR_STEPS.map((s, i) => {
            const n = i + 1;
            return (
              <li key={s.anchor}>
                <button
                  type="button"
                  onClick={() => go(n)}
                  aria-current={n === step ? "step" : undefined}
                  aria-label={`Step ${n}: ${s.title}`}
                  className={cn(
                    "tour-rail-dot grid size-7 place-items-center rounded-full text-xs font-semibold tabular-nums",
                    n === step ? "is-current" : n < step ? "is-done" : undefined,
                  )}
                >
                  {n}
                </button>
              </li>
            );
          })}
        </ol>

        <div className="min-w-0 flex-1" aria-live="polite">
          <h2 ref={headingRef} tabIndex={-1} className="tour-rail-title outline-none">
            <span className="tour-rail-count mr-2">
              {step}/{TOUR_STEPS.length}
            </span>
            {current.title}
          </h2>
          <p className="tour-rail-muted mt-1 line-clamp-3 text-xs leading-5 sm:line-clamp-2">{current.body}</p>
          {!onStepPage ? (
            <p className="tour-rail-muted mt-1 text-xs">
              This step is on another page —{" "}
              <button type="button" className="font-semibold text-white underline underline-offset-2" onClick={() => go(step)}>
                take me there
              </button>
              .
            </p>
          ) : anchor === "missing" ? (
            <p className="tour-rail-muted mt-1 text-xs">
              Still loading this part of the page — you can keep going.
            </p>
          ) : null}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button type="button" className="tour-pill tour-pill-ghost" onClick={exit}>
            Exit tour
          </button>
          <button type="button" className="tour-pill tour-pill-secondary" onClick={() => go(step - 1)} disabled={step === 1}>
            Back
          </button>
          {step < TOUR_STEPS.length ? (
            <button type="button" className="tour-pill tour-pill-primary" onClick={() => go(step + 1)}>
              Next <span aria-hidden>→</span>
            </button>
          ) : (
            <button type="button" className="tour-pill tour-pill-primary" onClick={exit}>
              Finish
            </button>
          )}
        </div>
      </div>
    </nav>
  );
}

/** Finds `[data-tour=<id>]` (waiting for slow renders), spotlights it and scrolls it into view. */
function useAnchor(id: string | null): AnchorState {
  // Keyed by anchor id so a new step starts as "searching" without resetting state in the effect.
  const [result, setResult] = useState<{ id: string; state: AnchorState } | null>(null);

  useEffect(() => {
    if (!id) return;
    let el: Element | null = null;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const attach = () => {
      el = document.querySelector(`[data-tour="${CSS.escape(id)}"]`);
      if (!el) return false;
      el.classList.add(SPOTLIGHT_CLASS);
      el.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
      setResult({ id, state: "found" });
      return true;
    };
    const observer = new MutationObserver(() => {
      if (attach()) observer.disconnect();
    });
    const frame = window.requestAnimationFrame(() => {
      if (!attach()) observer.observe(document.body, { childList: true, subtree: true });
    });
    const timer = window.setTimeout(() => {
      observer.disconnect();
      if (!el) setResult({ id, state: "missing" });
    }, ANCHOR_WAIT_MS);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
      window.clearTimeout(timer);
      (el as Element | null)?.classList.remove(SPOTLIGHT_CLASS);
    };
  }, [id]);

  return id && result?.id === id ? result.state : "searching";
}
