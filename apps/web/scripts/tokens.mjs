#!/usr/bin/env node
// Design tokens for IGS OS, generated from three base values and checked against WCAG 2.2 AA.
//
//   node scripts/tokens.mjs          → writes src/app/tokens.css and prints the contrast report
//   node scripts/tokens.mjs --check  → exits 1 if tokens.css is stale or any pair fails AA
//
// Inputs (keep them few; everything else derives from them):
//   BASE_HUE    warm hue of the neutrals — the cream of infinityglobalsports.com (hsl 40 7% 95%)
//   ACCENT_HUE  brand accent — Argentina blue (hsl 210 50% 67%)
//   CONTRAST    0 = default, 1 = high-contrast (darker muted text and borders)
// Values are OKLCH so lightness steps are perceptually even across hues. The dark theme's chrome
// uses the exact hex values measured on infinityglobalsports.com (docs/design/igs-site-style.md);
// hex may carry alpha (#FFFFFF1A) and is checked composited over the surface it sits on.
// Dark is the default for every surface; `.light` on <html> or any subtree opts into light.

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const BASE_HUE = 75;
const ACCENT_HUE = 245;
const CONTRAST = 0;

const here = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(here, "../src/app/tokens.css");

// ── Color math (OKLCH → sRGB → WCAG luminance) ────────────────────────────

function oklchToLinearRgb([L, C, H]) {
  const h = (H * Math.PI) / 180;
  const a = C * Math.cos(h);
  const b = C * Math.sin(h);
  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.291485548 * b;
  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

const inGamut = (rgb) => rgb.every((v) => v >= -0.0005 && v <= 1.0005);

// Reduce chroma until the color fits sRGB, so what we check is what browsers render.
function fit([L, C, H]) {
  let c = C;
  while (c > 0 && !inGamut(oklchToLinearRgb([L, c, H]))) c -= 0.002;
  return [L, Math.max(c, 0), H];
}

// A token value is either OKLCH [L, C, H] or a hex string (#RGB, #RRGGBB, #RRGGBBAA).
const isHex = (v) => typeof v === "string";

const toGamma = (v) => (v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055);
const toLinear = (v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);

// Gamma-encoded sRGB + alpha, each 0–1.
function rgba(value) {
  if (isHex(value)) {
    let h = value.slice(1);
    if (h.length <= 4) h = [...h].map((c) => c + c).join("");
    const n = (i) => parseInt(h.slice(i, i + 2), 16) / 255;
    return [n(0), n(2), n(4), h.length === 8 ? n(6) : 1];
  }
  const lin = oklchToLinearRgb(fit(value)).map((v) => Math.min(Math.max(v, 0), 1));
  return [...lin.map(toGamma), 1];
}

// Resolve a (possibly translucent) color to opaque gamma sRGB over `under` — CSS blends in sRGB.
// `under` is another token value or an already-flattened `{ rgb }`.
function flatten(value, under) {
  if (value && value.rgb) return value.rgb;
  const [r, g, b, a] = rgba(value);
  if (a >= 1 || under === undefined) return [r, g, b];
  const u = flatten(under);
  return [r, g, b].map((v, i) => v * a + u[i] * (1 - a));
}

const luminanceOf = (rgb) => {
  const [r, g, b] = rgb.map(toLinear);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

// `fg` composited over `bg`, and `bg` itself composited over `base` (the page under it).
function contrast(fg, bg, base) {
  const back = flatten(bg, base);
  const front = flatten(fg, { rgb: back });
  const [a, b] = [luminanceOf(front), luminanceOf(back)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

const css = (value) => {
  if (isHex(value)) return value;
  const [l, c, h] = fit(value);
  return `oklch(${(l * 100).toFixed(1)}% ${c.toFixed(3)} ${h.toFixed(0)})`;
};

// ── Scales ────────────────────────────────────────────────────────────────

const k = CONTRAST; // pulls text darker/lighter and borders stronger in high-contrast mode

// 12-step neutral ramp (1 = app background … 12 = text), Radix/Geist-style roles.
const grayL = {
  light: [0.99, 0.968, 0.948, 0.925, 0.905, 0.878, 0.835, 0.72 - 0.05 * k, 0.6, 0.54, 0.47 - 0.06 * k, 0.205],
  // Pure neutral, anchored on the site: 1 = #0D0D0D, 3 = #171717, 5 = #262626, 11 = #999, 12 = #F2F2F2.
  dark: [0.159, 0.18, 0.203, 0.235, 0.269, 0.3, 0.34, 0.42 + 0.05 * k, 0.53, 0.6, 0.683 + 0.05 * k, 0.961],
};
const grayC = 0.006;
const gray = (theme, step) => [grayL[theme][step - 1], theme === "dark" ? 0 : step >= 11 ? grayC * 0.6 : grayC, BASE_HUE];

// The site's dark chrome, measured (docs/design/igs-site-style.md → Color).
const SITE = {
  bg: "#0D0D0D",
  surface: "#171717",
  surface2: "#262626",
  fg: "#F2F2F2",
  fgStrong: "#FFFFFF",
  muted: "#999999",
  mutedHeadline: "#7A7A7A",
  line: "#FFFFFF1A",
  lineStrong: "#FFFFFF33",
  navIdle: "#FFFFFFB3",
};

// Status, accent and country hues: [hue, chroma]. Ink = text/icon; fill = solid backgrounds.
const hues = {
  success: [152, 0.13],
  warning: [62, 0.14],
  danger: [27, 0.17],
  info: [250, 0.13],
  brand: [ACCENT_HUE, 0.11], // Argentina-blue accent; `--accent` stays the neutral hover surface
  ai: [300, 0.13],
};

// Brand accents, taken from the marketing site's CSS.
const countries = {
  argentina: [0.72, 0.08, 245], // hsl(210 50% 67%)
  "brazil-green": [0.6, 0.15, 150], // #009c3b
  "brazil-gold": [0.86, 0.17, 92], // #FFCB05
  "brazil-lime": [0.93, 0.15, 128], // #BFFF78
  "usa-red": [0.49, 0.17, 22], // #B22234
  "usa-navy": [0.3, 0.12, 262], // #002776
  "costa-rica": [0.45, 0.15, 263],
  spain: [0.82, 0.16, 85],
  warm: [0.66, 0.05, 60], // #B2896C
};

function themeTokens(theme) {
  const light = theme === "light";
  const t = {};
  for (let s = 1; s <= 12; s++) t[`gray-${s}`] = gray(theme, s);

  // Semantic surface/text tokens (names unchanged so existing utilities keep working).
  if (light) {
    t.background = gray(theme, 2);
    t.foreground = gray(theme, 12);
    t["foreground-strong"] = "#000000";
    t.card = [1, 0, 0];
    t.raised = gray(theme, 4);
    t.primary = "#171717";
    t["primary-foreground"] = "#FFFFFF";
    t.secondary = "#0000000F";
    t["secondary-foreground"] = gray(theme, 12);
    t.muted = gray(theme, 4);
    t["muted-foreground"] = gray(theme, 11);
    t["muted-headline"] = gray(theme, 9);
    t.accent = gray(theme, 3);
    t.border = gray(theme, 6);
    t.line = "#0000001A";
    t["line-strong"] = "#00000033";
    t["nav-idle"] = "#000000B3";
    t.input = gray(theme, 9); // 3:1 against card and background (WCAG 1.4.11)
    t.ring = gray(theme, 12);
    t["surface-inverse"] = [0.17, 0.004, BASE_HUE];
    t["surface-inverse-foreground"] = [0.97, 0.004, BASE_HUE];
    t["surface-inverse-muted"] = [0.74, 0.004, BASE_HUE];
  } else {
    t.background = SITE.bg;
    t.foreground = SITE.fg;
    t["foreground-strong"] = SITE.fgStrong;
    t.card = SITE.surface;
    t.raised = SITE.surface2;
    t.primary = SITE.fgStrong; // white pill, #171717 text — the site's active nav and primary CTA
    t["primary-foreground"] = SITE.surface;
    t.secondary = SITE.line; // white/10 pill
    t["secondary-foreground"] = SITE.fg;
    t.muted = "#1F1F1F";
    t["muted-foreground"] = SITE.muted;
    t["muted-headline"] = SITE.mutedHeadline;
    t.accent = SITE.surface2; // hover surface on cards
    t.border = SITE.line;
    t.line = SITE.line;
    t["line-strong"] = SITE.lineStrong;
    t["nav-idle"] = SITE.navIdle;
    t.input = "#6B6B6B"; // 3:1 against card and background (WCAG 1.4.11)
    t.ring = SITE.fg;
    t["surface-inverse"] = SITE.fg;
    t["surface-inverse-foreground"] = SITE.surface;
    t["surface-inverse-muted"] = "#5C5C5C";
  }
  t["card-foreground"] = t.foreground;
  t.popover = light ? t.card : SITE.surface;
  t["popover-foreground"] = t.foreground;
  t["accent-foreground"] = t.foreground;

  for (const [name, [h, c]] of Object.entries(hues)) {
    // Ink: readable on card, background and on its own soft tint.
    // Dark: bright ink and a low, saturated tint that reads on #0D0D0D/#171717 without glowing.
    t[name] = light ? [0.49, c, h] : [0.8, c * 0.85, h];
    t[`${name}-soft`] = light ? [0.955, c * 0.22, h] : [0.245, c * 0.45, h];
    t[`${name}-border`] = light ? [0.82, c * 0.5, h] : [0.38, c * 0.6, h];
    t[`${name}-fill`] = light ? [0.53, c, h] : [0.74, c, h];
    t[`${name}-fill-foreground`] = light ? [1, 0, 0] : SITE.bg;
  }
  t.destructive = t["danger-fill"];
  t["destructive-foreground"] = t["danger-fill-foreground"];

  for (const [name, [L, C, H]] of Object.entries(countries)) {
    t[name] = [L, C, H]; // decorative: stripes, dots, fills next to text
    t[`${name}-ink`] = light ? [Math.min(L, 0.47), C * 0.9, H] : [Math.max(L, 0.8), C * 0.8, H];
  }

  // Flow canvas.
  t.canvas = light ? gray(theme, 3) : "#0A0A0A";
  t["canvas-dot"] = light ? gray(theme, 7) : "#2E2E2E";
  t.edge = gray(theme, 9);
  t["edge-active"] = gray(theme, 12);
  // Node categories: shape/glyph carry the category, these only tint the glyph and border.
  t["node-ai"] = t.ai;
  t["node-conversation"] = t.brand;
  t["node-logic"] = gray(theme, 11);
  t["node-integration"] = light ? [0.49, 0.12, 165] : [0.8, 0.1, 165];
  t["node-human"] = light ? [0.52, 0.14, 55] : [0.8, 0.12, 55];
  return t;
}

const light = themeTokens("light");
const dark = themeTokens("dark");

// ── Contrast checks ───────────────────────────────────────────────────────

// [foreground, background, minimum ratio, note, what a translucent background sits on]
const textPairs = [
  ["foreground", "background", 4.5],
  ["foreground", "card", 4.5],
  ["foreground", "raised", 4.5],
  ["foreground-strong", "background", 4.5],
  ["muted-foreground", "background", 4.5],
  ["muted-foreground", "card", 4.5],
  ["muted-foreground", "raised", 4.5, "footer copy"],
  ["muted-foreground", "muted", 4.5],
  ["muted-headline", "background", 3, "two-tone headlines are large display text"],
  ["muted-headline", "card", 3, "two-tone headlines are large display text"],
  ["nav-idle", "background", 4.5, "idle nav pills"],
  ["nav-idle", "card", 4.5, "idle nav pills on a card"],
  ["nav-idle", "secondary", 4.5, "secondary button idle label", "background"],
  ["primary-foreground", "primary", 4.5],
  ["primary", "background", 3, "primary pill edge (1.4.11)"],
  ["secondary-foreground", "secondary", 4.5, "", "background"],
  ["secondary-foreground", "secondary", 4.5, "", "card"],
  ["surface-inverse-foreground", "surface-inverse", 4.5],
  ["surface-inverse-muted", "surface-inverse", 4.5],
  ["destructive-foreground", "destructive", 4.5],
  ["line-strong", "background", 1.3, "hover border, decorative"],
  ["edge", "canvas", 3, "edges are non-text UI"],
  ["input", "card", 3, "input borders (1.4.11)"],
  ["input", "background", 3, "input borders (1.4.11)"],
  ["ring", "background", 3, "focus ring"],
  ["ring", "card", 3, "focus ring"],
  ["node-logic", "card", 4.5],
  ["node-integration", "card", 4.5],
  ["node-human", "card", 4.5],
];
for (const name of [...Object.keys(hues)]) {
  textPairs.push([name, "card", 4.5], [name, "background", 4.5], [name, "raised", 4.5], [name, `${name}-soft`, 4.5]);
  textPairs.push([`${name}-fill-foreground`, `${name}-fill`, 4.5]);
  textPairs.push([`${name}-border`, `${name}-soft`, 1.2, "soft border, decorative"]);
}
for (const name of Object.keys(countries)) textPairs.push([`${name}-ink`, "background", 4.5], [`${name}-ink`, "card", 4.5]);

function report(theme, t) {
  const rows = [];
  for (const [fg, bg, min, note, base = "background"] of textPairs) {
    const ratio = contrast(t[fg], t[bg], t[base]);
    const on = rgba(t[bg])[3] < 1 ? `${bg} over ${base}` : bg;
    rows.push({ theme, fg, bg: on, ratio, min, ok: ratio >= min, note });
  }
  // Tinted badges as rendered: ink on a 10% tint of itself over the card (bg-*/10).
  for (const name of Object.keys(hues)) {
    const ink = flatten(t[name]);
    const card = flatten(t.card);
    const tint = { rgb: ink.map((v, i) => v * 0.1 + card[i] * 0.9) };
    const ratio = contrast(t[name], tint);
    rows.push({ theme, fg: name, bg: `${name}/10 over card`, ratio, min: 4.5, ok: ratio >= 4.5 });
  }
  return rows;
}

const rows = [...report("light", light), ...report("dark", dark)];
const failures = rows.filter((r) => !r.ok);

// ── Output ────────────────────────────────────────────────────────────────

const header = `/* GENERATED by scripts/tokens.mjs — do not edit by hand.
 * Inputs: BASE_HUE=${BASE_HUE} ACCENT_HUE=${ACCENT_HUE} CONTRAST=${CONTRAST}.
 * ${rows.length} contrast pairs checked, ${failures.length} below WCAG 2.2 AA.
 * Theme: dark is the default everywhere; \`.light\` on <html> or on any subtree opts into light,
 * and \`.dark\` inside a light subtree switches back. */
`;

const block = (selector, t, scheme) =>
  `${selector} {\n${Object.entries(t)
    .map(([name, value]) => `  --${name}: ${css(value)};`)
    .join("\n")}\n  color-scheme: ${scheme};\n}\n`;

const output = header + "\n" + block(":root,\n.dark", dark, "dark") + "\n" + block(".light", light, "light");

const check = process.argv.includes("--check");
if (check) {
  let current = "";
  try {
    current = readFileSync(OUT, "utf8");
  } catch {}
  if (current !== output) {
    console.error("tokens.css is stale: run `pnpm --filter web tokens`");
    process.exitCode = 1;
  }
} else {
  writeFileSync(OUT, output);
}

const fmt = (r) =>
  `${r.ok ? "ok  " : "FAIL"} ${r.theme.padEnd(5)} ${r.ratio.toFixed(2).padStart(5)}:1 (≥${r.min}) ${r.fg} on ${r.bg}${r.note ? ` — ${r.note}` : ""}`;
if (process.argv.includes("--verbose") || failures.length) rows.forEach((r) => console.log(fmt(r)));
console.log(`${rows.length} pairs checked, ${failures.length} failing`);
if (failures.length) process.exitCode = 1;
