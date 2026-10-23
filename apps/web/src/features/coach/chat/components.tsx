// Presentational pieces of the coach chat: props in, markup out (no store, no API).
import Link from "next/link";
import { Fragment, type ReactNode } from "react";
import type { ChatAttachment, ChatMessage, ChatOption } from "../api";

export function ChatHeader({ status, onRestart }: { status: string; onRestart?: () => void }) {
  return (
    <header className="stadium-art relative flex items-center gap-3 overflow-hidden border-b border-line px-4 py-4">
      <div className="relative z-10 grid size-10 place-items-center rounded-full bg-primary font-display text-base font-extrabold uppercase text-primary-foreground">
        AI
      </div>
      <div className="relative z-10 min-w-0 flex-1">
        <p className="truncate font-display text-2xl font-extrabold uppercase leading-none tracking-[-0.025em]">Tour concierge</p>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          <span className="h-2 w-2 rounded-full bg-success" aria-hidden />
          {status}
        </p>
      </div>
      {onRestart && (
        <button type="button" onClick={onRestart} className="pill pill-secondary relative z-10">
          New chat
        </button>
      )}
    </header>
  );
}

export function Disclosure({ text, onHandoff }: { text: string; onHandoff?: () => void }) {
  return (
    <div className="mx-auto mb-5 flex max-w-sm flex-col items-center gap-2 rounded-lg border border-line bg-white/5 px-4 py-3 text-center text-xs leading-5 text-muted-foreground">
      <p>
        <span className="mr-1.5 inline-flex h-5 items-center rounded-full bg-white/10 px-2 font-semibold uppercase tracking-wide text-foreground">
          AI
        </span>
        {text}
      </p>
      {onHandoff && (
        <button type="button" onClick={onHandoff} className="pill pill-secondary pill-arrow">
          Talk to a person
        </button>
      )}
    </div>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <p className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm leading-6 text-primary-foreground">
          {message.text}
        </p>
      </div>
    );
  }
  const proposals = message.attachments.filter(isProposalLink);
  return (
    <div className="flex flex-col items-start gap-2">
      <div className="max-w-[85%] rounded-2xl rounded-bl-sm border border-line bg-card px-4 py-2.5 text-sm leading-6 text-foreground/90 [&_strong]:font-semibold [&_strong]:text-white">
        <span className="sr-only">Concierge: </span>
        <RichText text={message.text} />
      </div>
      {proposals.map((a) => (
        <ProposalCard key={a.url} href={a.url!} label={a.label} />
      ))}
    </div>
  );
}

function isProposalLink(a: ChatAttachment): boolean {
  return a.kind === "link" && typeof a.url === "string" && a.url.startsWith("/proposal/");
}

/** Markdown-light: **bold** and line breaks as React nodes (never injected HTML). */
export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <Fragment key={i}>
          {bold(line)}
          {i < lines.length - 1 && <br />}
        </Fragment>
      ))}
    </>
  );
}

function bold(line: string): ReactNode[] {
  return line
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
        <strong key={i}>{part.slice(2, -2)}</strong>
      ) : (
        part
      ),
    );
}

export function ProposalCard({ href, label }: { href: string; label?: string }) {
  return (
    <Link
      href={href}
      className="group block w-[85%] overflow-hidden rounded-lg border border-line bg-card transition hover:border-line-strong"
    >
      <div className="stadium-art relative overflow-hidden px-4 pb-5 pt-6">
        <p className="eyebrow relative z-10 text-xs text-white">Your tour proposal</p>
        <p className="type-hero relative z-10 mt-2 text-3xl">{label ?? "Ready to review"}</p>
        <p className="relative z-10 mt-2 text-xs leading-5 text-muted-foreground">
          Itinerary, opponents at your level and one all-inclusive price per person.
        </p>
      </div>
      <p className="flex items-center justify-between px-4 py-3">
        <span className="pill pill-primary pill-arrow">View your proposal</span>
      </p>
    </Link>
  );
}

export function Typing() {
  return (
    <div className="flex justify-start" role="status" aria-label="Concierge is typing">
      <div className="flex gap-1 rounded-2xl rounded-bl-sm border border-line bg-card px-4 py-3.5">
        {[0, 150, 300].map((d) => (
          <span
            key={d}
            className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground motion-reduce:animate-none"
            style={{ animationDelay: `${d}ms` }}
          />
        ))}
      </div>
    </div>
  );
}

export function QuickReplies({
  options,
  disabled,
  onPick,
}: {
  options: ChatOption[];
  disabled?: boolean;
  onPick: (text: string) => void;
}) {
  if (options.length === 0) return null;
  return (
    // Wraps instead of scrolling sideways, so no reply is ever cut off on a phone.
    <div className="flex flex-wrap gap-2 px-4 pb-3" role="group" aria-label="Suggested replies">
      {options.map((o) => (
        <button
          key={o.id ?? o.label}
          type="button"
          disabled={disabled}
          onClick={() => onPick(o.value ?? o.label)}
          className="pill pill-md pill-secondary h-auto min-h-9 whitespace-normal py-2 text-left"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Composer({
  value,
  disabled,
  placeholder,
  onChange,
  onSubmit,
}: {
  value: string;
  disabled?: boolean;
  placeholder: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  return (
    <form
      className="flex items-center gap-2 border-t border-line bg-background px-3 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <label htmlFor="coach-message" className="sr-only">
        Message
      </label>
      <input
        id="coach-message"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={2000}
        autoComplete="off"
        className="h-11 min-w-0 flex-1 rounded-full border border-line bg-white/5 px-5 text-base outline-none placeholder:text-muted-foreground focus-visible:border-line-strong focus-visible:ring-2 focus-visible:ring-ring sm:text-sm"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="Send"
        className="flex h-11 w-11 items-center justify-center rounded-full bg-primary text-primary-foreground transition disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        <svg aria-hidden viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2}>
          <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
    </form>
  );
}

export function Starters({ onPick, disabled }: { onPick: (text: string) => void; disabled?: boolean }) {
  const starters = [
    "Women's soccer, NCAA D1 — Buenos Aires in March",
    "Club U17 boys soccer, 18 players",
    "What does a 10-day tour cost?",
    "Do we need a visa for Brazil?",
  ];
  return (
    <div className="mx-auto max-w-sm space-y-4 py-6 text-center">
      <p className="type-hero">
        <span className="headline-muted">Train. Compete.</span>
        <br />
        Experience.
      </p>
      <p className="text-sm leading-6 text-muted-foreground">
        Tell me about your team and I&apos;ll match opponents at your level and draft a full tour in
        minutes.
      </p>
      <div className="flex flex-wrap justify-center gap-2 pt-2">
        {starters.map((s) => (
          <button
            key={s}
            type="button"
            disabled={disabled}
            onClick={() => onPick(s)}
            className="pill pill-md pill-secondary h-auto min-h-10 whitespace-normal py-2"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

export function DemoFooter({ className = "" }: { className?: string }) {
  return (
    <p className={`text-center text-[11px] text-muted-foreground ${className}`}>
      Demo built by Mauricio Villalba — not an official Infinity Global Sports product.
    </p>
  );
}
