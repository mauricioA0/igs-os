// Site-style pill classes (docs/design/igs-site-style.md): white primary, white/10 secondary,
// rounded-full, Montserrat 600 12px. Local so this feature doesn't depend on Button variants in flux.
export const PILL =
  "inline-flex h-9 items-center justify-center gap-2 rounded-full px-4 font-body text-xs font-semibold whitespace-nowrap transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-40 [&_svg]:size-3.5";
export const PILL_PRIMARY = "bg-foreground text-card hover:bg-foreground/90";
export const PILL_SECONDARY = "bg-white/10 text-foreground/70 hover:bg-white/15 hover:text-foreground";
export const PILL_GHOST = "text-foreground/70 hover:bg-white/5 hover:text-foreground";
export const PILL_DANGER = "border border-danger/40 text-danger hover:bg-danger/10";
export const PILL_DANGER_SOLID = "bg-danger text-white hover:bg-danger/90";
/** Small kbd pill shown inside a pill button. */
export const KBD_PILL =
  "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 font-mono text-[10px] leading-none";
/** PillGroup container: white/5 track with the active item as a white pill. */
export const PILL_GROUP = "inline-flex flex-wrap items-center gap-1 rounded-full border border-line bg-white/5 p-1";
export const PILL_GROUP_ITEM =
  "inline-flex h-8 items-center gap-1.5 rounded-full px-3.5 font-body text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
export const PILL_GROUP_ACTIVE = "bg-foreground text-card";
export const PILL_GROUP_IDLE = "text-foreground/70 hover:text-foreground";
/** Static tag pill (risk, status, fingerprint, countdown). */
export const TAG = "inline-flex h-6 items-center gap-1 rounded-full border px-2.5 font-body text-[11px] font-semibold";
export const TAG_TONE = {
  neutral: "border-line bg-white/5 text-muted-foreground",
  info: "border-info/30 bg-info/10 text-info",
  success: "border-success/30 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/10 text-warning",
  danger: "border-danger/30 bg-danger/10 text-danger",
} as const;
export type TagTone = keyof typeof TAG_TONE;

export function tagTone(tone: string): string {
  return TAG_TONE[(tone in TAG_TONE ? tone : "neutral") as TagTone];
}
