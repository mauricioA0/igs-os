// QA D-07: the ops UI is Spanish, but facts and reasons quote what clients wrote, often in
// English. System text stays Spanish; quoted evidence keeps its original language, marked with
// `lang` (screen readers switch voice) and a short visible label.

const EN_HINTS = /\b(the|and|was|were|will|with|for|our|their|is|are|has|have|due|by|of)\b/gi;
const ES_HINTS = /\b(el|la|los|las|que|con|para|por|una|del|está|son|hasta|según)\b/gi;

export function looksEnglish(text: string): boolean {
  const en = text.match(EN_HINTS)?.length ?? 0;
  const es = text.match(ES_HINTS)?.length ?? 0;
  return en >= 2 && en > es;
}

/** Quoted client text; tagged as English when it is. */
export function SourceText({ text, className }: { text: string; className?: string }) {
  if (!looksEnglish(text)) return <span className={className}>{text}</span>;
  return (
    <span className={className}>
      <q lang="en">{text}</q> <span className="whitespace-nowrap text-2xs text-muted-foreground">(original en inglés)</span>
    </span>
  );
}

/** "Riesgo abierto: <statement>" → Spanish label + quoted statement. */
export function ReasonText({ reason }: { reason: string }) {
  const at = reason.indexOf(": ");
  if (at <= 0) return <SourceText text={reason} />;
  return (
    <span>
      {reason.slice(0, at)}: <SourceText text={reason.slice(at + 2)} />
    </span>
  );
}
