"use client";

// Client container: wires the per-instance store, the route context and the ⌘J shortcut to the
// presentational parts. Mount once in the ops shell: <CopilotDrawer />.
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useShallow } from "zustand/react/shallow";

import { cn } from "@/components/ui/cn";

import {
  Answer,
  ApprovalCard,
  ContextChips,
  McpPanel,
  Notice,
  Sources,
  SuggestedPrompts,
  ToolSteps,
  mcpCommand,
} from "./components/parts";
import { chipsFromPath, screenFromPath } from "./context";
import { fakeTransport } from "./fake";
import { promptsFor } from "./prompts";
import { CopilotProvider, useCopilot } from "./provider";
import { sseTransport } from "./sse";
import { activeChips } from "./store";
import type { CopilotTransport, Turn } from "./types";

export type CopilotDrawerProps = {
  /** Same-origin proxy to POST /v1/copilot/turns (see server/proxy.ts). */
  endpoint?: string;
  /** Public MCP URL shown in the "Conectar por MCP" panel. */
  mcpUrl?: string;
  /** id → human label for context chips (e.g. {"t-2711": "Lakeshore · Buenos Aires"}). */
  labels?: Record<string, string>;
  defaultOpen?: boolean;
  /** Tests/storybook: inject a transport instead of SSE. */
  transport?: CopilotTransport;
};

// `?copilot=fake` works in production too: it is the live-demo fallback when the model is down.
// The scripted transport never calls the API, so it can't spend, leak or change anything; the
// drawer says so with a "modo guion" badge.
function pickTransport(props: CopilotDrawerProps): { transport: CopilotTransport; scripted: boolean } {
  if (props.transport) return { transport: props.transport, scripted: false };
  const fakeByEnv = process.env.NEXT_PUBLIC_COPILOT_FAKE === "1";
  const fakeByQuery =
    typeof window !== "undefined" && new URLSearchParams(window.location.search).get("copilot") === "fake";
  return fakeByEnv || fakeByQuery
    ? { transport: fakeTransport(), scripted: true }
    : { transport: sseTransport(props.endpoint), scripted: false };
}

export function CopilotDrawer(props: CopilotDrawerProps) {
  const [{ transport, scripted }] = useState(() => pickTransport(props));
  return (
    <CopilotProvider transport={transport}>
      <Drawer {...props} scripted={scripted} />
    </CopilotProvider>
  );
}

function Drawer({
  mcpUrl = defaultMcpUrl(),
  labels,
  defaultOpen = false,
  scripted = false,
}: CopilotDrawerProps & { scripted?: boolean }) {
  const pathname = usePathname() ?? "/ops";
  const open = useCopilot((s) => s.open);
  const setOpen = useCopilot((s) => s.setOpen);
  const toggle = useCopilot((s) => s.toggle);
  const setRouteContext = useCopilot((s) => s.setRouteContext);
  const [tab, setTab] = useState<"chat" | "mcp">("chat");
  const panelRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen, setOpen]);

  useEffect(() => {
    setRouteContext(chipsFromPath(pathname, labels));
  }, [pathname, labels, setRouteContext]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  return (
    <>
      {/* Opened from the ops header pill "Copiloto ⌘J" (features/ops-shell/nav.tsx) or ⌘J itself. */}
      <aside
        ref={panelRef}
        aria-label="Copiloto"
        data-copilot-drawer
        hidden={!open}
        onKeyDown={(e: KeyboardEvent) => {
          if (e.key === "Escape") setOpen(false);
        }}
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-md flex-col border-l border-white/10 bg-card text-foreground shadow-[0_0_80px_rgba(0,0,0,0.6)]"
      >
        <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <div className="min-w-0">
            <p className="eyebrow text-[11px] text-muted-foreground">IGS OS</p>
            <h2 className="type-small-title font-sans text-xl leading-none tracking-[-0.06em]">Copiloto</h2>
          </div>
          {scripted && (
            <span
              title="Respuestas guionadas: no se llama al modelo ni a la API."
              className="inline-flex h-6 items-center gap-1.5 rounded-full border border-warning/40 bg-warning/10 px-2.5 font-body text-[11px] font-semibold text-warning"
            >
              <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-warning" />
              modo guion
            </span>
          )}
          <div
            role="tablist"
            aria-label="Vistas del copiloto"
            className="ml-2 flex gap-1 rounded-full border border-white/10 bg-white/5 p-1 font-body text-xs font-semibold"
          >
            {(["chat", "mcp"] as const).map((t) => (
              <button
                key={t}
                role="tab"
                type="button"
                aria-selected={tab === t}
                onClick={() => setTab(t)}
                className={cn(
                  "h-7 rounded-full px-3 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  tab === t ? "bg-foreground text-background" : "text-white/70 hover:text-white",
                )}
              >
                {t === "chat" ? "Chat" : "MCP"}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Cerrar copiloto"
            className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white/70 transition-colors hover:bg-white/15 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span aria-hidden>✕</span>
          </button>
        </header>
        {tab === "chat" ? <ChatView pathname={pathname} inputRef={inputRef} /> : <McpView mcpUrl={mcpUrl} />}
      </aside>
    </>
  );
}

function ChatView({ pathname, inputRef }: { pathname: string; inputRef: React.RefObject<HTMLTextAreaElement | null> }) {
  const turns = useCopilot((s) => s.turns);
  const busy = useCopilot((s) => s.busy);
  const availability = useCopilot((s) => s.availability);
  const chips = useCopilot(useShallow((s) => activeChips(s)));
  const send = useCopilot((s) => s.send);
  const cancel = useCopilot((s) => s.cancel);
  const reset = useCopilot((s) => s.reset);
  const removeChip = useCopilot((s) => s.removeChip);
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const last = turns.at(-1);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [turns]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!draft.trim()) return;
    void send(draft);
    setDraft("");
  };

  return (
    <>
      <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
        {availability === "unavailable" && (
          <Notice tone="warning" title="El copiloto no está disponible">
            Este entorno no tiene un modelo configurado. Todo lo demás del panel funciona igual.
          </Notice>
        )}
        {turns.length === 0 && (
          <SuggestedPrompts prompts={promptsFor(screenFromPath(pathname))} onPick={(p) => void send(p)} disabled={busy} />
        )}
        {turns.map((t) => (
          <TurnView key={t.id} turn={t} />
        ))}
        <div ref={endRef} />
        <p aria-live="polite" className="sr-only">
          {last?.status === "done" ? "El copiloto terminó de responder." : ""}
        </p>
      </div>
      <form onSubmit={submit} className="space-y-3 border-t border-white/10 px-5 py-4">
        <ContextChips chips={chips} onRemove={removeChip} />
        <label htmlFor="copilot-input" className="sr-only">
          Preguntale al copiloto
        </label>
        <div className="flex items-end gap-2 rounded-[28px] border border-white/10 bg-white/5 py-1.5 pl-5 pr-1.5 transition-colors focus-within:border-white/20">
          <textarea
            id="copilot-input"
            ref={inputRef}
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) submit(e);
            }}
            placeholder="Preguntá sobre giras, clientes o flows…"
            className="max-h-32 min-h-10 flex-1 resize-none bg-transparent py-2 font-body text-sm text-foreground placeholder:text-white/40 focus-visible:outline-none"
          />
          {busy ? (
            <button
              type="button"
              onClick={cancel}
              aria-label="Detener"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-white transition-colors hover:bg-white/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span aria-hidden className="h-3 w-3 rounded-[3px] bg-white" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!draft.trim()}
              aria-label="Enviar"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-foreground text-lg leading-none text-background transition-opacity hover:opacity-90 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <span aria-hidden>↑</span>
            </button>
          )}
        </div>
        <div className="flex items-center gap-2 font-body text-xs">
          {turns.length > 0 && (
            <button type="button" onClick={reset} className="rounded-full px-3 py-1 text-white/60 transition-colors hover:bg-white/10 hover:text-white">
              Nueva conversación
            </button>
          )}
          <span className="ml-auto text-white/40">Enter para enviar · Shift+Enter nueva línea</span>
        </div>
      </form>
    </>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <article className="space-y-3" aria-label={`Pregunta: ${turn.question}`}>
      <p className="ml-10 rounded-2xl rounded-br-md bg-white/10 px-4 py-2.5 font-body text-sm text-foreground">{turn.question}</p>
      <ToolSteps steps={turn.steps} />
      {turn.text && <Answer text={turn.text} citations={turn.citations} />}
      {turn.status === "streaming" && !turn.text && turn.steps.length === 0 && (
        <p className="eyebrow animate-pulse text-[11px] text-muted-foreground motion-reduce:animate-none">Pensando…</p>
      )}
      {turn.approvals.map((a) => (
        <ApprovalCard key={a.approval_id} approval={a} />
      ))}
      <Sources citations={turn.citations} />
      {turn.status === "done" && turn.text && turn.citations.length === 0 && (
        <p className="font-body text-xs text-white/40">Sin fuentes citadas en esta respuesta.</p>
      )}
      {turn.error && turn.error.code !== "copilot-unavailable" && (
        <Notice tone={turn.error.code === "cancelled" ? "info" : "danger"} title={turn.error.message} />
      )}
    </article>
  );
}

function McpView({ mcpUrl }: { mcpUrl: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex-1 overflow-y-auto px-5 py-5">
      <McpPanel
        mcpUrl={mcpUrl}
        copied={copied}
        onCopy={() => {
          void navigator.clipboard?.writeText(mcpCommand(mcpUrl)).then(() => setCopied(true));
        }}
      />
    </div>
  );
}

function defaultMcpUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return `${base.replace(/\/$/, "")}/mcp`;
}
