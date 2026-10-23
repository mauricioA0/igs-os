import { createStore } from "zustand/vanilla";

import { collectCitations } from "./citations";
import { CopilotUnavailableError } from "./sse";
import type {
  ApprovalProposal,
  ContextChip,
  CopilotEvent,
  CopilotTransport,
  ToolStep,
  Turn,
} from "./types";

export type Availability = "unknown" | "available" | "unavailable";

export type CopilotState = {
  open: boolean;
  conversationId?: string;
  turns: Turn[];
  /** Chips derived from the route; the user can remove any before asking. */
  context: ContextChip[];
  dismissed: string[];
  availability: Availability;
  busy: boolean;
};

export type CopilotActions = {
  setOpen: (open: boolean) => void;
  toggle: () => void;
  setRouteContext: (chips: ContextChip[]) => void;
  removeChip: (chip: ContextChip) => void;
  send: (message: string) => Promise<void>;
  cancel: () => void;
  reset: () => void;
};

export type CopilotStore = ReturnType<typeof createCopilotStore>;

const chipKey = (c: ContextChip) => `${c.kind}:${c.id}`;

export function activeChips(state: Pick<CopilotState, "context" | "dismissed">): ContextChip[] {
  return state.context.filter((c) => !state.dismissed.includes(chipKey(c)));
}

let turnSeq = 0;

/** One store per drawer instance (never module-level: Next shares modules across requests). */
export function createCopilotStore(transport: CopilotTransport, initial?: Partial<CopilotState>) {
  let controller: AbortController | null = null;

  return createStore<CopilotState & CopilotActions>()((set, get) => {
    const patchTurn = (id: string, patch: (turn: Turn) => Turn) =>
      set((s) => ({ turns: s.turns.map((t) => (t.id === id ? patch(t) : t)) }));

    const apply = (id: string, event: CopilotEvent) => {
      switch (event.type) {
        case "start":
          set({ conversationId: event.conversation_id, availability: "available" });
          return;
        case "text":
          patchTurn(id, (t) => ({ ...t, text: t.text + event.delta }));
          return;
        case "tool_start": {
          const step: ToolStep = {
            callId: event.call_id,
            name: event.name,
            input: event.input,
            status: "running",
          };
          patchTurn(id, (t) => ({ ...t, steps: [...t.steps, step] }));
          return;
        }
        case "tool_end":
          patchTurn(id, (t) => ({
            ...t,
            citations: event.is_error ? t.citations : collectCitations(t.citations, event.output),
            steps: t.steps.map((s) =>
              s.callId === event.call_id
                ? {
                    ...s,
                    status: isApproval(event.output) ? "approval" : event.is_error ? "error" : "ok",
                    ms: event.ms,
                    output: event.output,
                  }
                : s,
            ),
          }));
          return;
        case "approval_required": {
          const proposal: ApprovalProposal = {
            status: "approval_required",
            approval_id: event.approval_id,
            title: event.title,
            payload_hash: event.payload_hash,
            review_url: event.review_url,
            message: event.message,
          };
          patchTurn(id, (t) =>
            t.approvals.some((a) => a.approval_id === proposal.approval_id)
              ? t
              : { ...t, approvals: [...t.approvals, proposal] },
          );
          return;
        }
        case "done":
          set({ conversationId: event.conversation_id });
          patchTurn(id, (t) => ({ ...t, status: t.status === "error" ? "error" : "done" }));
          return;
        case "error":
          patchTurn(id, (t) => ({
            ...t,
            status: "error",
            error: { code: event.code, message: event.message },
          }));
          return;
      }
    };

    return {
      open: false,
      turns: [],
      context: [],
      dismissed: [],
      availability: "unknown",
      busy: false,
      ...initial,

      setOpen: (open) => set({ open }),
      toggle: () => set((s) => ({ open: !s.open })),
      setRouteContext: (chips) =>
        set((s) => {
          const same =
            s.context.length === chips.length &&
            s.context.every((c, i) => chipKey(c) === chipKey(chips[i]) && c.label === chips[i].label);
          return same ? s : { context: chips, dismissed: [] };
        }),
      removeChip: (chip) => set((s) => ({ dismissed: [...s.dismissed, chipKey(chip)] })),

      send: async (raw) => {
        const message = raw.trim();
        if (!message || get().busy) return;
        const id = `turn-${++turnSeq}`;
        const turn: Turn = {
          id,
          question: message,
          steps: [],
          text: "",
          citations: [],
          approvals: [],
          status: "streaming",
        };
        controller = new AbortController();
        set((s) => ({ turns: [...s.turns, turn], busy: true }));
        try {
          for await (const event of transport(
            { message, conversation_id: get().conversationId, context: activeChips(get()) },
            controller.signal,
          )) {
            apply(id, event);
          }
          patchTurn(id, (t) => (t.status === "streaming" ? { ...t, status: "done" } : t));
        } catch (err) {
          if (err instanceof CopilotUnavailableError) set({ availability: "unavailable" });
          const aborted = err instanceof DOMException && err.name === "AbortError";
          patchTurn(id, (t) => ({
            ...t,
            status: "error",
            error: aborted
              ? { code: "cancelled", message: "Cancelaste la respuesta." }
              : err instanceof CopilotUnavailableError
                ? { code: "copilot-unavailable", message: err.message }
                : { code: "network", message: "No pudimos hablar con el copiloto. Probá de nuevo." },
          }));
        } finally {
          controller = null;
          set({ busy: false });
        }
      },
      cancel: () => controller?.abort(),
      reset: () => {
        controller?.abort();
        set({ turns: [], conversationId: undefined });
      },
    };
  });
}

function isApproval(output: unknown): boolean {
  return (
    typeof output === "object" &&
    output !== null &&
    (output as { status?: unknown }).status === "approval_required"
  );
}
