"use client";

import { useState } from "react";
import { cn } from "@/components/ui";
import { fmtDateTime } from "@/features/ops-shell/format";
import { CHANNEL } from "@/features/ops-shell/labels";
import { ChannelIcon } from "./channel-icon";

export type TimelineEntry = {
  id: string;
  channel: string;
  direction?: string | null;
  occurredAt: string;
  subject?: string | null;
  excerpt?: string | null;
  who?: string;
};

const DIRECTION: Record<string, string> = { inbound: "Recibido de", outbound: "Enviado a", internal: "Nota interna" };

export function InteractionTimeline({ entries }: { entries: TimelineEntry[] }) {
  const [channel, setChannel] = useState("all");
  const present = ["all", ...new Set(entries.map((e) => e.channel))];
  const rows = entries
    .filter((e) => channel === "all" || e.channel === channel)
    .sort((a, b) => b.occurredAt.localeCompare(a.occurredAt));

  return (
    <section aria-labelledby="timeline">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <h2 id="timeline" className="type-section">
          Últimas interacciones
        </h2>
        <div
          role="group"
          aria-label="Filtrar por canal"
          className="flex flex-wrap gap-1 rounded-full border border-line bg-white/5 p-1"
        >
          {present.map((f) => (
            <button
              key={f}
              type="button"
              aria-pressed={channel === f}
              onClick={() => setChannel(f)}
              className={cn(
                "inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                channel === f ? "bg-white text-card" : "text-foreground/70 hover:text-foreground",
              )}
            >
              {f !== "all" && <ChannelIcon channel={f} className="size-3.5" />}
              {f === "all" ? "Todo" : (CHANNEL[f] ?? f)}
            </button>
          ))}
        </div>
      </div>
      <ol className="relative">
        {rows.map((e, idx) => (
          <li
            key={e.id}
            id={`i-${e.id}`}
            className="group relative flex scroll-mt-24 gap-4 rounded-lg pb-8 last:pb-0 target:bg-white/5 target:ring-2 target:ring-line-strong"
          >
            {idx < rows.length - 1 && (
              <span className="absolute bottom-0 left-5 top-11 w-px -translate-x-1/2 bg-line" aria-hidden />
            )}
            <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-white/10 text-foreground">
              <ChannelIcon channel={e.channel} />
            </span>
            <div className="min-w-0 flex-1 pt-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {CHANNEL[e.channel] ?? e.channel} · {fmtDateTime(e.occurredAt)}
                {(e.direction || e.who) && (
                  <span className="normal-case tracking-normal">
                    {" "}
                    · {e.direction ? (DIRECTION[e.direction] ?? e.direction) : ""}{" "}
                    {e.who && <span className="text-foreground">{e.who}</span>}
                  </span>
                )}
              </p>
              <p className="type-small-title mt-2 text-foreground">{e.subject ?? "Sin asunto"}</p>
              {e.excerpt && <p className="mt-2 line-clamp-3 max-w-3xl text-sm text-muted-foreground">{e.excerpt}</p>}
            </div>
          </li>
        ))}
        {rows.length === 0 && <li className="text-sm text-muted-foreground">Sin interacciones.</li>}
      </ol>
    </section>
  );
}
