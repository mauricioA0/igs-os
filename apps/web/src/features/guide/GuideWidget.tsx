"use client";

// Floating "Asistente": a public, read-only guide that explains IGS OS in real time. Mounted on
// every surface (site, coach, ops). It never acts: it answers and offers route pills.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { cn } from "@/components/ui/cn";

import { fakeGuideTransport, sseGuideTransport } from "./transport";
import type { GuideLocale, GuideMessage, GuideTransport } from "./types";
import { useGuide } from "./use-guide";

export const GUIDE_COPY = {
  es: {
    open: "Asistente",
    title: "Asistente IGS OS",
    close: "Cerrar asistente",
    banner: "POC · Datos ficticios, no hay información real de IGS · Chat en tiempo real con IA",
    placeholder: "Preguntá qué hace cada pantalla…",
    send: "Enviar",
    stop: "Detener",
    typing: "Escribiendo…",
    stopped: "Detenido.",
    script: "modo guion",
    teaser: "¿Te muestro cómo funciona IGS OS?",
    fictional: "datos ficticios",
    hello:
      "Hola, soy el asistente de IGS OS. Te explico qué hace cada pantalla y cómo podría ayudar a IGS. Los datos son ficticios.",
    suggestions: ["¿Qué es IGS OS?", "¿Qué veo en esta pantalla?", "¿Cómo ayudaría a la operación de IGS?"],
  },
  en: {
    open: "Assistant",
    title: "IGS OS Assistant",
    close: "Close assistant",
    banner: "POC · Fictional data, no real IGS information · Real-time AI chat",
    placeholder: "Ask what each screen does…",
    send: "Send",
    stop: "Stop",
    typing: "Typing…",
    stopped: "Stopped.",
    script: "script mode",
    teaser: "Want a quick tour of IGS OS?",
    fictional: "fictional data",
    hello:
      "Hi, I'm the IGS OS assistant. I can explain each screen and how it could help IGS. All data is fictional.",
    suggestions: ["What is IGS OS?", "What am I looking at?", "How would this help IGS operations?"],
  },
} as const;

export type GuideWidgetProps = {
  locale: GuideLocale;
  /** `ops` sits bottom-left (the copilot drawer owns the right) and above the mobile pill bar. */
  placement?: "site" | "ops";
  endpoint?: string;
  defaultOpen?: boolean;
  /** Tests: inject a transport instead of SSE. */
  transport?: GuideTransport;
};

function pickTransport(props: GuideWidgetProps): { transport: GuideTransport; scripted: boolean } {
  if (props.transport) return { transport: props.transport, scripted: false };
  const fake =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("guide") === "fake";
  return fake
    ? { transport: fakeGuideTransport(props.locale), scripted: true }
    : { transport: sseGuideTransport(props.endpoint), scripted: false };
}

export function GuideWidget(props: GuideWidgetProps) {
  const { locale, placement = "site", defaultOpen = false } = props;
  const copy = GUIDE_COPY[locale];
  const [{ transport, scripted }] = useState(() => pickTransport(props));
  const page = usePathname() ?? undefined;
  const { messages, busy, send, stop } = useGuide(transport, page);
  const [open, setOpen] = useState(defaultOpen);
  const [draft, setDraft] = useState("");
  const panelId = useId();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim() || busy) return;
    void send(draft);
    setDraft("");
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) submit(e);
    if (e.key === "Escape") setOpen(false);
  };

  // A chat bubble in the bottom-right corner, like a support chat. Ops phones have the bottom
  // pill bar: stay above it. The coach chat (/chat) is already an AI chat, so no bubble there.
  const hidden = page?.startsWith("/chat") ?? false;
  const corner = cn("right-4 sm:right-6 sm:bottom-6", placement === "ops" ? "bottom-24" : "bottom-4");
  // A one-line teaser pops out once, a moment after load, until the visitor opens the chat.
  const [teaser, setTeaser] = useState(false);
  const [opened, setOpened] = useState(defaultOpen);
  useEffect(() => {
    // Shown for a few seconds only, so it never sits on top of the page's own buttons.
    const show = setTimeout(() => setTeaser(true), 2500);
    const hide = setTimeout(() => setTeaser(false), 9000);
    return () => {
      clearTimeout(show);
      clearTimeout(hide);
    };
  }, []);
  const toggle = (next: boolean) => {
    setOpen(next);
    if (next) setOpened(true);
  };

  if (hidden) return null;

  return (
    <div className={cn("guide-widget fixed z-40 flex flex-col gap-3 no-print", corner)}>
      {open && (
        <section
          id={panelId}
          role="dialog"
          aria-label={copy.title}
          className="guide-pop flex max-h-[min(70dvh,640px)] w-[min(calc(100vw-1.5rem),400px)] flex-col overflow-hidden rounded-3xl border border-line bg-card text-foreground shadow-2xl"
        >
          <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
            <div className="min-w-0">
              <p className="eyebrow text-2xs">IGS OS</p>
              <h2 className="type-small-title truncate">{copy.title}</h2>
            </div>
            <div className="flex items-center gap-2">
              {scripted && (
                <span className="rounded-full bg-white/10 px-2.5 py-1 text-2xs font-semibold uppercase tracking-wide">
                  {copy.script}
                </span>
              )}
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label={copy.close}
                className="grid size-8 place-items-center rounded-full bg-white/10 text-sm hover:bg-white/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                ✕
              </button>
            </div>
          </header>

          <p
            role="note"
            data-testid="guide-poc-banner"
            className="border-b border-line bg-raised px-4 py-2 text-2xs font-semibold uppercase leading-relaxed tracking-wide text-foreground"
          >
            {copy.banner}
          </p>

          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite">
            <Bubble role="assistant" text={copy.hello} />
            {messages.map((m) => (
              <MessageView key={m.id} message={m} copy={copy} />
            ))}
            {messages.length === 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {copy.suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="rounded-full border border-line bg-white/5 px-3 py-1.5 text-xs font-semibold text-foreground/80 hover:border-line-strong hover:text-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form onSubmit={submit} className="flex items-end gap-2 border-t border-line p-3">
            <label htmlFor={`${panelId}-input`} className="sr-only">
              {copy.placeholder}
            </label>
            <textarea
              id={`${panelId}-input`}
              ref={inputRef}
              rows={1}
              value={draft}
              maxLength={2000}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              placeholder={copy.placeholder}
              className="max-h-28 min-h-10 flex-1 resize-none rounded-2xl border border-line bg-white/5 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
            {busy ? (
              <button
                type="button"
                onClick={stop}
                aria-label={copy.stop}
                className="grid size-10 shrink-0 place-items-center rounded-full bg-white/10 hover:bg-white/20"
              >
                ■
              </button>
            ) : (
              <button
                type="submit"
                aria-label={copy.send}
                disabled={!draft.trim()}
                className="grid size-10 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground disabled:opacity-40"
              >
                ↑
              </button>
            )}
          </form>
        </section>
      )}

      {teaser && !open && !opened && (
        <button
          type="button"
          onClick={() => toggle(true)}
          className="guide-pop max-w-60 rounded-2xl border border-line bg-card px-4 py-3 text-left text-sm text-foreground shadow-xl hover:border-line-strong"
        >
          {copy.teaser}
          <span className="mt-1 block text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
            POC · {copy.fictional}
          </span>
        </button>
      )}

      <button
        type="button"
        aria-label={`${open ? copy.close : copy.open} · POC`}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => toggle(!open)}
        className="relative grid size-14 place-items-center rounded-full bg-primary text-primary-foreground shadow-2xl transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95"
      >
        {open ? (
          <span aria-hidden className="text-lg">✕</span>
        ) : (
          <svg aria-hidden viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
            <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
          </svg>
        )}
        {!open && (
          <span className="absolute -right-1 -top-1 rounded-full border border-line-strong bg-background px-1.5 py-0.5 text-[9px] font-bold uppercase leading-none tracking-wide text-foreground">
            POC
          </span>
        )}
      </button>
    </div>
  );
}

function Bubble({ role, text }: { role: "user" | "assistant"; text: string }) {
  return (
    <p
      className={cn(
        "max-w-[88%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
        role === "user"
          ? "ml-auto bg-primary text-primary-foreground"
          : "bg-white/5 text-foreground",
      )}
    >
      {text}
    </p>
  );
}

function MessageView({
  message,
  copy,
}: {
  message: GuideMessage;
  copy: (typeof GUIDE_COPY)[GuideLocale];
}) {
  if (message.role === "user") return <Bubble role="user" text={message.text} />;
  const typing = message.status === "streaming" && !message.text;
  return (
    <div className="space-y-2" data-status={message.status}>
      {typing ? (
        <p className="inline-flex items-center gap-2 rounded-2xl bg-white/5 px-3.5 py-2.5 text-sm text-muted-foreground">
          <span aria-hidden className="flex gap-1">
            <span className="size-1.5 animate-pulse rounded-full bg-white/60" />
            <span className="size-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:150ms]" />
            <span className="size-1.5 animate-pulse rounded-full bg-white/60 [animation-delay:300ms]" />
          </span>
          {copy.typing}
        </p>
      ) : (
        message.text && <Bubble role="assistant" text={message.text} />
      )}
      {message.status === "error" && (
        <p role="alert" className="text-xs text-danger">
          {message.error}
        </p>
      )}
      {message.status === "stopped" && <p className="text-xs text-muted-foreground">{copy.stopped}</p>}
      {message.routes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.routes.map((r) => (
            <Link
              key={`${r.path}-${r.label}`}
              href={r.path}
              className="rounded-full bg-primary px-3.5 py-1.5 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              {r.label} →
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
