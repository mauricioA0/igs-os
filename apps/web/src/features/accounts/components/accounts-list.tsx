"use client";

import { ArrowRight, Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { cn } from "@/components/ui";
import { ACCOUNT_KIND, ACCOUNT_STATUS, country, HEALTH, programLabel } from "@/features/ops-shell/labels";
import { ReasonText } from "@/features/ops-shell/source-text";
import { HEALTH_DOT, HealthPill } from "./health-pill";

export type AccountRow = {
  id: string;
  name: string;
  kind: string;
  country: string;
  location: string;
  programs: string[];
  health: string;
  status: string;
  tier?: string | null;
  /** First rule-based health reason ("Riesgo abierto: …"); absent when the account is healthy. */
  reason?: string;
};

const HEALTH_ORDER = ["red", "amber", "green"];

export function AccountsList({ accounts }: { accounts: AccountRow[] }) {
  const [health, setHealth] = useState("all");
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return accounts
      .filter((a) => health === "all" || a.health === health)
      .filter((a) => !q || `${a.name} ${a.location} ${a.programs.join(" ")}`.toLowerCase().includes(q))
      .sort((a, b) => HEALTH_ORDER.indexOf(a.health) - HEALTH_ORDER.indexOf(b.health) || a.name.localeCompare(b.name));
  }, [accounts, health, query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="group"
          aria-label="Filtrar por salud"
          className="flex flex-wrap gap-1 rounded-full border border-line bg-white/5 p-1"
        >
          <Chip active={health === "all"} onClick={() => setHealth("all")}>
            Todos <span className="tabular-nums opacity-60">{accounts.length}</span>
          </Chip>
          {HEALTH_ORDER.map((h) => (
            <Chip key={h} active={health === h} onClick={() => setHealth(h)}>
              <span className={cn("size-2 rounded-full", HEALTH_DOT[h])} aria-hidden />
              {HEALTH[h].label}{" "}
              <span className="tabular-nums opacity-60">{accounts.filter((a) => a.health === h).length}</span>
            </Chip>
          ))}
        </div>
        <label className="relative block w-full sm:w-72">
          <span className="sr-only">Buscar clientes</span>
          <Search
            className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cliente, ciudad o programa"
            className="h-10 w-full rounded-full border border-line bg-card pl-10 pr-4 text-sm placeholder:text-muted-foreground focus-visible:border-line-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </label>
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-line bg-card px-4 py-12 text-center text-sm text-muted-foreground">
          Sin resultados.
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {rows.map((a) => (
            <li key={a.id}>
              <Link
                href={`/ops/accounts/${a.id}`}
                className="group flex h-full flex-col gap-4 rounded-lg border border-line bg-card p-5 transition-colors hover:border-line-strong hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <div className="flex items-start justify-between gap-3">
                  <p className="eyebrow text-xs">
                    {[ACCOUNT_KIND[a.kind] ?? a.kind, country(a.country).label].filter(Boolean).join(" · ")}
                  </p>
                  <HealthPill health={a.health} />
                </div>
                <div>
                  <h2 className="type-card text-foreground">{a.name}</h2>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {[a.location, a.programs.map(programLabel).join(", "), a.tier && `Tier ${a.tier}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <p className="line-clamp-3 text-sm text-foreground/80">
                  {a.reason ? <ReasonText reason={a.reason} /> : <span className="text-muted-foreground">Sin alertas.</span>}
                </p>
                <div className="mt-auto flex items-center justify-between gap-2 border-t border-line pt-4 text-xs font-semibold">
                  <span className="rounded-full bg-white/10 px-3 py-1 text-foreground/70">
                    {ACCOUNT_STATUS[a.status] ?? a.status}
                  </span>
                  <span className="inline-flex items-center gap-1 text-foreground/70 group-hover:text-foreground">
                    Ver cliente <ArrowRight className="size-3.5" aria-hidden />
                  </span>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1.5 rounded-full px-4 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        active ? "bg-white text-card" : "text-foreground/70 hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}
