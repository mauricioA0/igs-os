// Inbox shortcuts (J/K move, A approve, R reject, E edit), ignored while the user types.

export type Command = "next" | "prev" | "approve" | "reject" | "edit";

const KEYS: Record<string, Command> = {
  j: "next",
  arrowdown: "next",
  k: "prev",
  arrowup: "prev",
  a: "approve",
  r: "reject",
  e: "edit",
};

export type KeyLike = {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
  altKey?: boolean;
  target?: { tagName?: string; isContentEditable?: boolean } | null;
};

const TYPING_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function commandForKey(e: KeyLike): Command | null {
  if (e.metaKey || e.ctrlKey || e.altKey) return null;
  const t = e.target;
  if (t && (t.isContentEditable || (t.tagName && TYPING_TAGS.has(t.tagName.toUpperCase())))) return null;
  return KEYS[e.key.toLowerCase()] ?? null;
}

export function moveSelection(ids: readonly string[], current: string | undefined, dir: "next" | "prev"): string | undefined {
  if (ids.length === 0) return undefined;
  const at = current ? ids.indexOf(current) : -1;
  if (at === -1) return dir === "next" ? ids[0] : ids[ids.length - 1];
  const to = dir === "next" ? Math.min(at + 1, ids.length - 1) : Math.max(at - 1, 0);
  return ids[to];
}

// After a decision the decided item leaves the pending list: select its neighbour, not the top.
export function selectionAfterRemoval(ids: readonly string[], removed: string): string | undefined {
  const at = ids.indexOf(removed);
  const rest = ids.filter((id) => id !== removed);
  if (rest.length === 0) return undefined;
  return rest[Math.min(Math.max(at, 0), rest.length - 1)];
}
