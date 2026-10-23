// Per-instance chat store (Zustand vanilla + context, see docs/architecture/frontend.md §5):
// the conversation lifecycle, the SSE stream of concierge replies and the coach's messages.
import { createStore, type StoreApi } from "zustand/vanilla";
import { coachApi, type ChatMessage } from "../api";

export type ChatPhase = "idle" | "starting" | "open" | "ended" | "error";

export type ChatState = {
  phase: ChatPhase;
  conversationId: string | null;
  disclosure: string | null;
  messages: ChatMessage[];
  /** The coach is waiting for the concierge's next reply. */
  awaitingReply: boolean;
  error: string | null;
  start: (firstMessage?: string) => Promise<void>;
  send: (text: string) => Promise<void>;
  resume: (conversationId: string) => Promise<void>;
  reset: () => void;
  dispose: () => void;
};

export type ChatStore = StoreApi<ChatState>;

const STORAGE_KEY = "igs.coach.conversation";
export const HANDOFF_TEXT = "I'd like to talk to a person, please.";

function remember(id: string | null) {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Private mode / blocked storage: the chat still works, it just won't survive a reload.
  }
}

export function rememberedConversation(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function friendly(error: unknown): string {
  if (error && typeof error === "object" && "status" in error) {
    const status = (error as { status: number }).status;
    if (status === 429) return "You're sending messages quickly — give it a few seconds.";
    if (status === 409) return "This conversation has ended. Start a new one any time.";
  }
  return "The concierge is unavailable right now. Please try again in a moment.";
}

export function createChatStore(): ChatStore {
  let source: EventSource | null = null;

  return createStore<ChatState>()((set, get) => {
    const add = (incoming: ChatMessage[]) =>
      set((s) => {
        const seen = new Set(s.messages.map((m) => m.id));
        const fresh = incoming.filter((m) => !seen.has(m.id));
        if (fresh.length === 0) return s;
        const messages = [...s.messages, ...fresh].sort((a, b) => a.at.localeCompare(b.at));
        const replied = fresh.some((m) => m.role === "assistant");
        return { messages, awaitingReply: replied ? false : s.awaitingReply };
      });

    const listen = (conversationId: string) => {
      source?.close();
      source = new EventSource(coachApi.streamUrl(conversationId));
      source.addEventListener("message", (event) => {
        add([JSON.parse((event as MessageEvent<string>).data) as ChatMessage]);
      });
      source.addEventListener("end", () => {
        source?.close();
        source = null;
        set({ phase: "ended", awaitingReply: false });
      });
      // EventSource reconnects on its own (Last-Event-ID resumes); only surface hard failures.
      source.onerror = () => {
        if (source?.readyState === EventSource.CLOSED) set({ error: friendly(null) });
      };
    };

    const optimistic = (text: string): ChatMessage => ({
      id: `local-${crypto.randomUUID()}`,
      role: "user",
      text,
      at: new Date().toISOString(),
      options: [],
      attachments: [],
    });

    return {
      phase: "idle",
      conversationId: null,
      disclosure: null,
      messages: [],
      awaitingReply: false,
      error: null,

      async start(firstMessage) {
        if (get().phase === "starting") return;
        set({ phase: "starting", error: null, awaitingReply: true });
        if (firstMessage) add([optimistic(firstMessage)]);
        try {
          const conversation = await coachApi.startConversation(firstMessage);
          remember(conversation.conversation_id);
          set({
            phase: "open",
            conversationId: conversation.conversation_id,
            disclosure: conversation.ai_disclosure,
          });
          listen(conversation.conversation_id);
        } catch (error) {
          set({ phase: "error", error: friendly(error), awaitingReply: false });
        }
      },

      async send(text) {
        const trimmed = text.trim();
        const { conversationId, phase } = get();
        if (!trimmed) return;
        if (!conversationId || phase === "ended" || phase === "error") {
          await get().start(trimmed);
          return;
        }
        add([optimistic(trimmed)]);
        set({ awaitingReply: true, error: null });
        try {
          await coachApi.sendMessage(conversationId, trimmed);
        } catch (error) {
          set({ awaitingReply: false, error: friendly(error) });
        }
      },

      async resume(conversationId) {
        try {
          const transcript = await coachApi.transcript(conversationId);
          const ended = ["succeeded", "failed", "cancelled"].includes(transcript.status);
          set({
            conversationId,
            messages: transcript.messages,
            phase: ended ? "ended" : "open",
            awaitingReply: false,
          });
          if (!ended) listen(conversationId);
        } catch {
          remember(null);
          set({ phase: "idle", conversationId: null, messages: [] });
        }
      },

      reset() {
        source?.close();
        source = null;
        remember(null);
        set({
          phase: "idle",
          conversationId: null,
          disclosure: null,
          messages: [],
          awaitingReply: false,
          error: null,
        });
      },

      dispose() {
        source?.close();
        source = null;
      },
    };
  });
}
