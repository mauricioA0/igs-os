/**
 * Splits a brief into its first sentence and the rest, keeping the first sentence's "[n]"
 * citations with it. A period inside a number ("US$2.280") is not a sentence end.
 */
export function splitLead(text: string): [string, string] {
  const m = /^([\s\S]+?[.!?](?:\s*\[\d+\])*)\s+(?=\S)/.exec(text);
  return m ? [m[1], text.slice(m[0].length)] : [text, ""];
}
