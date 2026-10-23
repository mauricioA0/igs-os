"use client";

// Client container: owns the chat store instance and wires it to the presentational pieces.
import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useStore } from "zustand";
import {
  ChatHeader,
  Composer,
  DemoFooter,
  Disclosure,
  MessageBubble,
  QuickReplies,
  Starters,
  Typing,
} from "./components";
import { HANDOFF_TEXT, createChatStore, rememberedConversation, type ChatState, type ChatStore } from "./chat-store";

const ChatContext = createContext<ChatStore | null>(null);

function useChat<T>(selector: (s: ChatState) => T): T {
  const store = useContext(ChatContext);
  if (!store) throw new Error("useChat must be used inside <CoachChat>");
  return useStore(store, selector);
}

export function CoachChat() {
  const [store] = useState(createChatStore);
  useEffect(() => {
    const id = rememberedConversation();
    if (id) void store.getState().resume(id);
    return () => store.getState().dispose();
  }, [store]);
  return (
    <ChatContext.Provider value={store}>
      <ChatFrame />
    </ChatContext.Provider>
  );
}

const DEFAULT_DISCLOSURE =
  "You're chatting with the IGS AI concierge. A person from our team reviews every proposal before it's sent.";

function ChatFrame() {
  const phase = useChat((s) => s.phase);
  const messages = useChat((s) => s.messages);
  const awaiting = useChat((s) => s.awaitingReply);
  const error = useChat((s) => s.error);
  const disclosure = useChat((s) => s.disclosure);
  const send = useChat((s) => s.send);
  const reset = useChat((s) => s.reset);
  const [draft, setDraft] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, awaiting]);

  const last = messages.at(-1);
  const options = last?.role === "assistant" ? last.options : [];
  const busy = phase === "starting" || awaiting;
  const status =
    phase === "ended" ? "Conversation closed" : busy ? "typing…" : "Online · replies in seconds";

  const submit = (text: string) => {
    void send(text);
    setDraft("");
  };

  return (
    <div className="flex h-[calc(100dvh-4rem)] flex-col sm:items-center sm:justify-center sm:py-8 lg:items-end lg:py-10">
      <div className="flex h-full w-full flex-col overflow-hidden bg-card sm:h-[min(840px,100%)] sm:max-w-md sm:rounded-xl sm:border sm:border-line sm:shadow-2xl">
        <ChatHeader status={status} onRestart={messages.length ? reset : undefined} />
        <div className="flex-1 overflow-y-auto bg-background px-4 py-5" role="log" aria-live="polite" aria-label="Conversation">
          <Disclosure text={disclosure ?? DEFAULT_DISCLOSURE} onHandoff={phase === "open" ? () => submit(HANDOFF_TEXT) : undefined} />
          {messages.length === 0 && phase !== "starting" && <Starters onPick={submit} disabled={busy} />}
          <div className="space-y-3">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {busy && <Typing />}
          </div>
          {error && (
            <p role="alert" className="mt-3 rounded-sm border border-danger-border bg-danger-soft px-3 py-2 text-sm">
              {error}
            </p>
          )}
          <div ref={bottom} />
        </div>
        <QuickReplies options={options} disabled={busy} onPick={submit} />
        <Composer
          value={draft}
          onChange={setDraft}
          onSubmit={() => submit(draft)}
          disabled={busy}
          placeholder={phase === "ended" ? "Start a new conversation" : "Tell us about your team…"}
        />
        <DemoFooter className="bg-background px-4 pb-3" />
      </div>
    </div>
  );
}
