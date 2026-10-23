// Line diff (LCS) for "what changed" views: edit-and-approve and approval-changed (409).

export type DiffLine = { kind: "same" | "added" | "removed"; text: string };

export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n");
  const b = after.split("\n");
  // lcs[i][j] = length of the LCS of a[i:] and b[j:]
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      out.push({ kind: "removed", text: a[i++] });
    } else {
      out.push({ kind: "added", text: b[j++] });
    }
  }
  while (i < a.length) out.push({ kind: "removed", text: a[i++] });
  while (j < b.length) out.push({ kind: "added", text: b[j++] });
  return out;
}

export function hasChanges(lines: DiffLine[]): boolean {
  return lines.some((l) => l.kind !== "same");
}

// Stable, human-readable text of an action so two versions can be diffed line by line.
export function actionToText(action: { action: string; params?: Record<string, unknown> }): string {
  const lines = [`acción: ${action.action}`];
  for (const key of Object.keys(action.params ?? {}).sort()) {
    const value = (action.params ?? {})[key];
    if (typeof value === "string") {
      const [first, ...rest] = value.split("\n");
      lines.push(`${key}: ${first}`, ...rest.map((r) => `  ${r}`));
    } else {
      lines.push(`${key}: ${JSON.stringify(value)}`);
    }
  }
  return lines.join("\n");
}
