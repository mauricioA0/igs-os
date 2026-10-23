import type { CitationSource } from "./types";

// Tool outputs that carry citable passages (see igs_core.agent.tools):
//   search_account_history → [{id, channel, occurred_at, subject, excerpt, stakeholder}]
//   search_knowledge       → [{n, title, section, snippet, source_id}]
// The answer refers to them with [n] markers, numbered in the order sources were returned.

const CHANNEL_LABEL: Record<string, string> = {
  email: "Email",
  call: "Llamada",
  meeting: "Reunión",
  chat: "Chat",
  whatsapp: "WhatsApp",
  note: "Nota",
};

const CHANNEL_ARIA: Record<string, string> = {
  email: "email",
  call: "llamada",
  meeting: "reunión",
  chat: "chat",
  whatsapp: "WhatsApp",
  note: "nota interna",
};

type Row = Record<string, unknown>;

function isRow(value: unknown): value is Row {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

/** Finds every list of passage-like rows in a tool output, however it is wrapped. */
function passageRows(output: unknown, depth = 0): Row[] {
  if (depth > 3) return [];
  if (Array.isArray(output)) {
    const rows = output.filter(isRow);
    if (rows.some((r) => str(r.excerpt) || str(r.snippet))) {
      return rows.filter((r) => str(r.excerpt) || str(r.snippet));
    }
    return rows.flatMap((r) => passageRows(r, depth + 1));
  }
  if (isRow(output)) return Object.values(output).flatMap((v) => passageRows(v, depth + 1));
  return [];
}

function shortDate(iso: string | undefined): { short?: string; long?: string } {
  if (!iso) return {};
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return {};
  // Fixed time zone: the same string on server and client (no hydration drift).
  const opts = { timeZone: "America/Argentina/Buenos_Aires" } as const;
  return {
    short: date.toLocaleDateString("es-AR", { ...opts, day: "numeric", month: "short" }).replace(".", ""),
    long: date.toLocaleDateString("es-AR", { ...opts, day: "numeric", month: "long" }),
  };
}

export function toCitation(row: Row, n: number): CitationSource {
  const snippet = str(row.excerpt) ?? str(row.snippet) ?? "";
  if (str(row.channel)) {
    const channel = str(row.channel) ?? "note";
    const { short, long } = shortDate(str(row.occurred_at));
    const who = str(row.stakeholder);
    const label = [CHANNEL_LABEL[channel] ?? channel, short, who].filter(Boolean).join(" · ");
    const aria = [
      `Fuente ${n}: ${CHANNEL_ARIA[channel] ?? channel}`,
      long && `del ${long}`,
      who && `de ${who}`,
    ]
      .filter(Boolean)
      .join(" ");
    return {
      n,
      kind: "interaction",
      label,
      ariaLabel: aria,
      title: str(row.subject),
      snippet,
      sourceId: str(row.id),
    };
  }
  const title = str(row.title) ?? "Base de conocimiento";
  const section = str(row.section);
  return {
    n,
    kind: "document",
    label: section ? `${title} · ${section}` : title,
    ariaLabel: `Fuente ${n}: documento ${title}${section ? `, sección ${section}` : ""}`,
    title,
    snippet,
    sourceId: str(row.source_id) ?? str(row.id),
  };
}

/** Appends the passages of a tool output to the turn's citations, deduplicated by source. */
export function collectCitations(existing: CitationSource[], output: unknown): CitationSource[] {
  const seen = new Set(existing.map((c) => c.sourceId ?? `${c.label}|${c.snippet}`));
  const next = [...existing];
  for (const row of passageRows(output)) {
    const candidate = toCitation(row, next.length + 1);
    const key = candidate.sourceId ?? `${candidate.label}|${candidate.snippet}`;
    if (seen.has(key)) continue;
    seen.add(key);
    next.push(candidate);
  }
  return next;
}

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; n: number };

/** Splits the answer on [n] / [1, 2] markers; markers without a known source stay as text. */
export function splitAnswer(text: string, known: number): AnswerPart[] {
  const parts: AnswerPart[] = [];
  const re = /\[(\d+(?:\s*,\s*\d+)*)\]/g;
  let last = 0;
  for (const match of text.matchAll(re)) {
    const numbers = match[1].split(",").map((n) => Number.parseInt(n.trim(), 10));
    if (!numbers.every((n) => n >= 1 && n <= known)) continue;
    if (match.index > last) parts.push({ kind: "text", text: text.slice(last, match.index) });
    for (const n of numbers) parts.push({ kind: "cite", n });
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}
