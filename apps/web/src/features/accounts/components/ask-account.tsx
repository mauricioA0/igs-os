"use client";

import { ArrowRight, Loader2, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import { unwrap } from "@/lib/api/client";
import { browserApi } from "@/lib/api/browser";
import { ApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";
import { type CitationSource, CitedText } from "./citations";

type AskOut = components["schemas"]["AskOut"];

type Turn =
  | { q: string; state: "loading" }
  | { q: string; state: "done"; answer: AskOut }
  | { q: string; state: "error"; message: string };

/**
 * "Preguntá sobre este cliente": POST /v1/accounts/{id}/ask. The API answers only from the
 * account's interactions and SQL state, with citations, or abstains. `previews` maps interaction
 * ids to the subject shown on hover of each citation chip.
 */
export function AskAccount({
  accountId,
  accountName,
  suggestions,
  previews,
}: {
  accountId: string;
  accountName: string;
  suggestions: string[];
  previews: Record<string, string>;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const busy = turns.some((t) => t.state === "loading");

  async function ask(raw: string) {
    const q = raw.trim();
    if (!q || busy) return;
    setDraft("");
    setTurns((t) => [...t, { q, state: "loading" }]);
    let next: Turn;
    try {
      const answer = await unwrap(
        browserApi().POST("/v1/accounts/{account_id}/ask", {
          params: { path: { account_id: accountId } },
          body: { question: q },
        }),
      );
      next = { q, state: "done", answer };
    } catch (error) {
      next = { q, state: "error", message: describe(error) };
    }
    setTurns((t) => t.map((turn) => (turn.q === q && turn.state === "loading" ? next : turn)));
  }

  return (
    <section
      aria-labelledby="ask"
      className="rounded-xl border border-line bg-card px-5 py-8 sm:px-10 sm:py-12"
      data-tour="copilot-ask"
    >
      <p className="eyebrow text-xs">Copiloto</p>
      <h2 id="ask" className="type-section mt-3">
        Preguntá sobre este cliente
      </h2>

      <form
        className="mt-8 flex items-center gap-2 rounded-full border border-line bg-background p-1.5 pl-5 transition-colors focus-within:border-line-strong focus-within:ring-2 focus-within:ring-ring"
        onSubmit={(e) => {
          e.preventDefault();
          void ask(draft);
        }}
      >
        <Search className="size-5 shrink-0 text-muted-foreground" aria-hidden />
        <label htmlFor="ask-input" className="sr-only">
          Pregunta sobre {accountName}
        </label>
        <input
          id="ask-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Ej.: ¿quién firma en ${accountName}?`}
          className="h-12 min-w-0 flex-1 bg-transparent text-base placeholder:text-muted-foreground focus:outline-none"
        />
        <button
          type="submit"
          disabled={busy || !draft.trim()}
          className="inline-flex h-11 shrink-0 items-center gap-1.5 rounded-full bg-white px-5 text-xs font-semibold text-card transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40"
        >
          Preguntar <ArrowRight className="size-4" aria-hidden />
        </button>
      </form>

      {suggestions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              disabled={busy}
              onClick={() => ask(s)}
              className="inline-flex h-8 items-center rounded-full bg-white/10 px-4 text-xs font-semibold text-foreground/70 transition-colors hover:bg-white/20 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div aria-live="polite" className="mt-8 space-y-6 empty:hidden">
        {turns.map((t, idx) => (
          <div key={idx} className="space-y-3 border-t border-line pt-6">
            <p className="type-small-title text-foreground">{t.q}</p>
            {t.state === "loading" && (
              <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Buscando en las interacciones de {accountName}…
              </p>
            )}
            {t.state === "error" && <p className="text-sm text-danger">{t.message}</p>}
            {t.state === "done" && <AnswerView answer={t.answer} previews={previews} />}
          </div>
        ))}
      </div>

      <p className="mt-6 text-xs text-muted-foreground">
        Responde solo con lo que está en las interacciones y en el estado de la cuenta, siempre con la fuente.
      </p>
    </section>
  );
}

function AnswerView({ answer, previews }: { answer: AskOut; previews: Record<string, string> }) {
  const sources: CitationSource[] = answer.citations.map((c) => ({
    n: c.n,
    label: c.label,
    interactionId: c.interaction_id,
    preview: c.interaction_id ? previews[c.interaction_id] : undefined,
  }));
  return (
    <div className="space-y-2">
      <p className="eyebrow flex items-center gap-1.5 text-xs">
        <Sparkles className="size-3.5" aria-hidden />
        {answer.grounded ? `${answer.citations.length} fuentes citadas` : "Sin fuentes: el agente prefiere no adivinar"}
      </p>
      <p className="max-w-3xl text-base leading-relaxed text-foreground/90">
        <CitedText text={answer.text} sources={sources} />
      </p>
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === "ai-unavailable")
      return "El asistente no está disponible: la IA no está configurada en este entorno.";
    if (error.status >= 500 || error.status === 0)
      return "El asistente no está disponible ahora (el modelo no respondió). Probá de nuevo en un rato.";
    return error.detail ?? error.title;
  }
  return "No pudimos enviar la pregunta.";
}
