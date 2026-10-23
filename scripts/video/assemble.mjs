// Assembles the demo video from recorded scenes + TTS narration.
//
//   node scripts/video/assemble.mjs
//
// Inputs:  build/video/raw/<scene>.webm (record.mjs), build/video/audio/<scene>.mp3 (tts.py),
//          scripts/video/narration.json.
// Outputs: docs/delivery/video/igs-os-demo.mp4 and igs-os-teaser.mp4.
//
// The local ffmpeg has no libass/freetype, so title cards and burned-in subtitles are rendered
// as PNGs by Playwright (with the brand fonts) and composited with ffmpeg's overlay filter.
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const require = createRequire(join(root, "apps/web/package.json"));
const { chromium } = require("@playwright/test");

const BUILD = join(root, "build/video");
const RAW = join(BUILD, "raw");
const AUDIO = join(BUILD, "audio");
const WORK = join(BUILD, "work");
const OUT_DIR = join(root, "docs/delivery/video");
const W = 1920;
const H = 1080;
const FPS = 30;
const LEAD = 0.5; // seconds of picture before the voice starts
const TAIL = 0.9; // seconds after the voice ends
const SKIP = 0.6; // trim the blank first frames of each recording

const scenes = JSON.parse(readFileSync(join(here, "narration.json"), "utf8"));
const teaser = JSON.parse(readFileSync(join(here, "teaser.json"), "utf8"));

const ff = (args) => execFileSync("ffmpeg", ["-v", "error", "-y", ...args], { stdio: "inherit" });
const duration = (file) =>
  Number(
    execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file])
      .toString()
      .trim(),
  );

// ── Overlays (Playwright → transparent PNG) ──────────────────────────────────────────────────

const FONTS =
  '<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@800;900&family=DM+Sans:wght@400;500;600&family=Montserrat:wght@400;500&display=swap" rel="stylesheet">';

// Same look as the site: near-black, two-tone condensed headline, wide DM Sans eyebrow.
function cardHtml({ eyebrow, title, subtitle }) {
  return `<!doctype html><html><head>${FONTS}<style>
    html,body{margin:0;width:${W}px;height:${H}px;background:#0D0D0D;color:#F2F2F2;font-family:'Montserrat',sans-serif}
    body{background:radial-gradient(ellipse at 70% 10%,rgba(255,255,255,.08),transparent 55%),#0D0D0D}
    .wrap{position:absolute;left:160px;right:160px;top:50%;transform:translateY(-50%)}
    .eyebrow{font-family:'DM Sans';font-weight:600;letter-spacing:.375em;text-transform:uppercase;font-size:26px;color:#FFFFFF}
    h1{font-family:'Barlow Condensed';font-weight:900;text-transform:uppercase;font-size:190px;line-height:.8;letter-spacing:-.025em;margin:34px 0 40px}
    h1 .muted{color:#7A7A7A}
    p{font-size:34px;line-height:1.4;max-width:1300px;color:#999999;margin:0}
    .foot{position:absolute;left:160px;bottom:80px;font-size:22px;color:#7A7A7A}
    .poc{display:inline-block;margin-left:18px;padding:6px 16px;border-radius:999px;background:rgba(255,255,255,.1);color:#F2F2F2;font:600 20px/1 'Montserrat';letter-spacing:.05em;vertical-align:middle}
  </style></head><body><div class="wrap"><div class="eyebrow">${eyebrow}<span class="poc">POC</span></div><h1>${title}</h1><p>${subtitle}</p></div>
  <div class="foot">Proof of concept with fictional data · built by Mauricio Villalba · not an official Infinity Global Sports product</div></body></html>`;
}

function captionHtml(text) {
  return `<!doctype html><html><head>${FONTS}<style>
    html,body{margin:0;width:${W}px;height:${H}px;background:transparent}
    .cap{position:absolute;left:50%;bottom:150px;transform:translateX(-50%);max-width:1500px;
      background:rgba(10,10,10,.82);color:#fff;font:500 38px/1.3 'DM Sans',sans-serif;
      padding:14px 26px;border-radius:6px;text-align:center}
  </style></head><body><div class="cap">${text}</div></body></html>`;
}

/**
 * Caption cards: one sentence per card (split on . ? ! ; —). A sentence longer than a card is
 * split at clause boundaries (commas, colons) and only word-wrapped inside a clause that is
 * itself too long, so a card never ends mid-clause.
 */
const MAX = 84;
function chunks(text) {
  // Break only where the punctuation is followed by a space, so "igs-os.vercel.app" stays whole.
  const sentences = text.split(/(?<=[.!?;—])\s+/).map((x) => x.trim()).filter(Boolean);
  const out = [];
  for (const sentence of sentences) {
    if (sentence.length <= MAX) { out.push(sentence); continue; }
    const clauses = sentence.split(/(?<=[,:])\s+/).map((x) => x.trim()).filter(Boolean);
    let cur = "";
    for (const clause of clauses) {
      if (clause.length > MAX) {
        if (cur) { out.push(cur); cur = ""; }
        let line = "";
        for (const word of clause.split(" ")) {
          if ((line + " " + word).trim().length > MAX && line) { out.push(line.trim()); line = word; }
          else line += " " + word;
        }
        if (line.trim()) out.push(line.trim());
      } else if ((cur + " " + clause).trim().length > MAX) {
        out.push(cur);
        cur = clause;
      } else {
        cur = (cur + " " + clause).trim();
      }
    }
    if (cur) out.push(cur);
  }
  return out;
}

async function renderPng(page, html, file, transparent) {
  await page.setContent(html, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: file, omitBackground: transparent });
}

// ── Segments ─────────────────────────────────────────────────────────────────────────────────

const VCODEC = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", String(FPS)];
const ACODEC = ["-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2"];

/** Timed caption overlays: [png, start, end] with start/end relative to the voice start. */
function timedCaptions(pngs, texts, voice) {
  const total = texts.reduce((n, t) => n + t.length, 0);
  let t = LEAD;
  return pngs.map((png, i) => {
    const span = (texts[i].length / total) * voice;
    const item = [png, t, t + span];
    t += span;
    return item;
  });
}

function overlayGraph(baseLabel, captions, firstInput) {
  let graph = "";
  let last = baseLabel;
  captions.forEach(([, a, b], i) => {
    const out = `v${i}`;
    graph += `;[${last}][${firstInput + i}:v]overlay=0:0:enable='between(t,${a.toFixed(2)},${b.toFixed(2)})'[${out}]`;
    last = out;
  });
  return { graph, last };
}

function sceneSegment({ video, audio, captions, out, length, from = SKIP, fadeIn = true }) {
  const inputs = ["-ss", String(from), "-i", video, "-i", audio, ...captions.flatMap(([png]) => ["-loop", "1", "-i", png])];
  const fades = `${fadeIn ? `fade=t=in:st=0:d=0.35,` : ""}fade=t=out:st=${(length - 0.35).toFixed(2)}:d=0.35`;
  const base = `[0:v]fps=${FPS},scale=${W}:${H},tpad=stop_mode=clone:stop_duration=60,trim=duration=${length.toFixed(2)},setpts=PTS-STARTPTS,${fades}[base]`;
  const { graph, last } = overlayGraph("base", captions, 2);
  const audioGraph = `;[1:a]adelay=${Math.round(LEAD * 1000)}|${Math.round(LEAD * 1000)},apad,atrim=duration=${length.toFixed(2)},afade=t=out:st=${(length - 0.3).toFixed(2)}:d=0.3[a]`;
  ff([...inputs, "-filter_complex", base + graph + audioGraph, "-map", `[${last}]`, "-map", "[a]", "-t", length.toFixed(2), ...VCODEC, ...ACODEC, out]);
}

function cardSegment({ png, audio, captions = [], out, length }) {
  const inputs = ["-loop", "1", "-i", png];
  if (audio) inputs.push("-i", audio);
  else inputs.push("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo");
  inputs.push(...captions.flatMap(([p]) => ["-loop", "1", "-i", p]));
  const base = `[0:v]fps=${FPS},scale=${W}:${H},trim=duration=${length.toFixed(2)},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.4,fade=t=out:st=${(length - 0.4).toFixed(2)}:d=0.4[base]`;
  const { graph, last } = overlayGraph("base", captions, 2);
  const audioGraph = audio
    ? `;[1:a]adelay=${Math.round(LEAD * 1000)}|${Math.round(LEAD * 1000)},apad,atrim=duration=${length.toFixed(2)}[a]`
    : `;[1:a]atrim=duration=${length.toFixed(2)}[a]`;
  ff([...inputs, "-filter_complex", base + graph + audioGraph, "-map", `[${last}]`, "-map", "[a]", "-t", length.toFixed(2), ...VCODEC, ...ACODEC, out]);
}

function concat(segments, out) {
  const list = join(WORK, `${Date.now()}-list.txt`);
  writeFileSync(list, segments.map((s) => `file '${s}'`).join("\n"));
  ff(["-f", "concat", "-safe", "0", "-i", list, "-c", "copy", "-movflags", "+faststart", out]);
}

// ── Main ─────────────────────────────────────────────────────────────────────────────────────

rmSync(WORK, { recursive: true, force: true });
mkdirSync(WORK, { recursive: true });
mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H } });

const opening = join(WORK, "card-open.png");
await renderPng(page, cardHtml({
  eyebrow: "Infinity Global Sports · v0 demo",
  title: '<span class="muted">IGS</span> OS',
  subtitle: "The operating system for a sports tour operator: agents and durable flows do the work, people stay in control.",
}), opening, false);
const closing = join(WORK, "card-close.png");
await renderPng(page, cardHtml({
  eyebrow: "https://igs-os.vercel.app",
  title: '<span class="muted">IGS OS</span> · v0',
  subtitle: "Account 360 · copilot + MCP · human approvals · Voiceflow-style flows on Temporal · real-time guide · evals and accessibility checks in CI.",
}), closing, false);

async function captionsFor(id, text, voice) {
  const texts = chunks(text);
  const pngs = [];
  for (const [i, t] of texts.entries()) {
    const png = join(WORK, `cap-${id}-${i}.png`);
    await renderPng(page, captionHtml(t), png, true);
    pngs.push(png);
  }
  return timedCaptions(pngs, texts, voice);
}

// Full video
const segments = [];
const openSeg = join(WORK, "00-open.mp4");
cardSegment({ png: opening, out: openSeg, length: 3.2 });
segments.push(openSeg);
let total = 3.2;
for (const s of scenes) {
  const audio = join(AUDIO, `${s.id}.mp3`);
  const voice = duration(audio);
  const video = join(RAW, `${s.id}.webm`);
  // "fit": "clip" scenes (the copilot) run until the recorded action finishes, not the voice.
  const clip = s.fit === "clip" && existsSync(video) ? duration(video) - SKIP : 0;
  const length = Math.max(LEAD + voice + TAIL, clip);
  // `caption` overrides what's shown when the spoken text differs (e.g. a URL read aloud).
  const captions = await captionsFor(s.id, s.caption ?? s.text, voice);
  const out = join(WORK, `${s.id}.mp4`);
  if (existsSync(video)) sceneSegment({ video, audio, captions, out, length });
  else cardSegment({ png: closing, audio, captions, out, length: length + 1.2 });
  segments.push(out);
  total += existsSync(video) ? length : length + 1.2;
  console.log(`${s.id}: ${length.toFixed(1)}s`);
}
const demo = join(OUT_DIR, "igs-os-demo.mp4");
concat(segments, demo);
console.log(`demo: ${duration(demo).toFixed(1)}s (planned ${total.toFixed(1)}s) → ${demo}`);

// Teaser (~30 s): one voice line over fast cuts.
const teaserAudio = join(AUDIO, "teaser.mp3");
const tVoice = duration(teaserAudio);
const tSegs = [];
const cuts = teaser.cuts; // [{scene, from, length}]
const cutTotal = cuts.reduce((n, c) => n + c.length, 0);
const tCaps = await captionsFor("teaser", teaser.text, tVoice);
// One continuous picture track: cut segments without audio, then lay the voice over the whole.
for (const [i, c] of cuts.entries()) {
  const out = join(WORK, `t-${i}.mp4`);
  if (c.scene === "card-open" || c.scene === "card-close") {
    const png = c.scene === "card-open" ? opening : closing;
    ff(["-loop", "1", "-i", png, "-vf", `fps=${FPS},scale=${W}:${H},fade=t=in:st=0:d=0.3,fade=t=out:st=${c.length - 0.3}:d=0.3`, "-t", String(c.length), "-an", ...VCODEC, out]);
  } else {
    ff(["-ss", String(c.from), "-i", join(RAW, `${c.scene}.webm`), "-vf", `fps=${FPS},scale=${W}:${H},tpad=stop_mode=clone:stop_duration=30,trim=duration=${c.length},setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.25,fade=t=out:st=${c.length - 0.25}:d=0.25`, "-t", String(c.length), "-an", ...VCODEC, out]);
  }
  tSegs.push(out);
}
const silent = join(WORK, "teaser-silent.mp4");
concat(tSegs, silent);
const { graph, last } = overlayGraph("0:v", tCaps, 2);
const teaserOut = join(OUT_DIR, "igs-os-teaser.mp4");
ff([
  "-i", silent, "-i", teaserAudio, ...tCaps.flatMap(([p]) => ["-loop", "1", "-i", p]),
  "-filter_complex", graph.replace(/^;/, "") + `;[1:a]adelay=${Math.round(LEAD * 1000)}|${Math.round(LEAD * 1000)},apad,atrim=duration=${cutTotal}[a]`,
  "-map", `[${last}]`, "-map", "[a]", "-t", String(cutTotal), ...VCODEC, ...ACODEC, "-movflags", "+faststart", teaserOut,
]);
console.log(`teaser: ${duration(teaserOut).toFixed(1)}s → ${teaserOut}`);
await browser.close();
