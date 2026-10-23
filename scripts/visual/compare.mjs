#!/usr/bin/env node
// Visual comparison of every IGS OS route against the public IGS site.
//
//   node scripts/visual/compare.mjs                 # full: fresh DB, API, isolated build, shots, sheets
//   SKIP_BUILD=1 node scripts/visual/compare.mjs    # reuse the last isolated build
//   SITE_SHOTS=/path/to/igs-style node scripts/visual/compare.mjs
//
// Needs: Docker db up (localhost:5433), uv, Node 24, ffmpeg. Starts its own API (:8040) on a
// throwaway database (igs_test_visual, migrated + seeded + reset) and a production build of
// apps/web (:3360) built from a scratch copy, so other work in apps/web can't swap chunks under
// the screenshots. The copilot runs in its scripted fake mode; no model is called.
//
// Output (docs/reviews/visual/): <route>.<viewport>.png (ours), sheet-<route>.<viewport>.png (site
// left, ours right), checklist.md (measured deviations per route). Sheets contain screenshots of
// the IGS site, so the PNGs are gitignored: they are review material, never shipped.
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = join(ROOT, "docs/reviews/visual");
const WORK = process.env.VISUAL_WORK ?? join(tmpdir(), "igs-visual");
const COPY = join(WORK, "repo");
const LOGS = join(WORK, "logs");
const SITE = process.env.SITE_SHOTS ?? join(WORK, "igs-style");
const API_PORT = 8040;
const WEB_PORT = 3360;
const DB = "igs_test_visual";
const DB_URL = `postgres://igs:igs@localhost:5433/${DB}`;
const API = `http://localhost:${API_PORT}`;
const WEB = `http://localhost:${WEB_PORT}`;
const CROP = { desktop: 2200, mobile: 2600 }; // sheet height cap (px of each column)

// Deterministic fixture ids (uuid5 of the seed keys, see igs_common.seed.fixture_id).
const IDS = {
  account: "17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8",
  trip: "c0b16481-9260-5765-8dd1-788c7b2a63ab",
  execution: "57c5d89c-7923-572a-beec-09b92e5e1f29",
};

// slug, path, owning file, closest site page (screenshot basename in SITE)
const ROUTES = [
  ["landing", "/", "apps/web/src/app/(site)/page.tsx", ""],
  ["design", "/design", "apps/web/src/app/(site)/design/page.tsx", ""],
  ["ops-today", "/ops", "apps/web/src/features/today", ""],
  ["ops-trips", "/ops/trips", "apps/web/src/features/trips", "college-soccer-tours"],
  ["ops-trip", `/ops/trips/${IDS.trip}`, "apps/web/src/features/trips", "plan-a-tour"],
  ["ops-accounts", "/ops/accounts", "apps/web/src/features/accounts", "about"],
  ["ops-account", `/ops/accounts/${IDS.account}`, "apps/web/src/features/accounts", "about"],
  ["ops-approvals", "/ops/approvals", "apps/web/src/features/approvals", "about"],
  ["ops-leads", "/ops/leads", "apps/web/src/features/leads", "about"],
  ["ops-flows", "/ops/flows", "apps/web/src/features/flows", "college-soccer-tours"],
  ["ops-flow", "/ops/flows/inbound-inquiry", "apps/web/src/features/flows", ""],
  ["ops-execution", `/ops/flows/inbound-inquiry/executions/${IDS.execution}`, "apps/web/src/features/flows", ""],
  ["chat", "/chat", "apps/web/src/features/coach", "plan-a-tour"],
  ["proposal", `/proposal/${IDS.trip}`, "apps/web/src/features/coach/proposal", "plan-a-tour"],
];
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };

// The measured contract (docs/design/igs-site-style.md).
const SPEC = {
  bg: "rgb(13, 13, 13)",
  surfaces: ["rgb(13, 13, 13)", "rgb(23, 23, 23)", "rgb(38, 38, 38)", "rgb(255, 255, 255)", "rgb(242, 242, 242)"],
  fg: ["rgb(242, 242, 242)", "rgb(255, 255, 255)"],
  displayFonts: /barlow condensed|dm sans/i,
  bodyFont: /montserrat/i,
  navFont: /montserrat/i,
};

const env = {
  ...process.env,
  PATH: `${process.env.HOME}/.nvm/versions/node/v24.13.0/bin:${process.env.PATH}`,
  DATABASE_URL: DB_URL,
  IGS_DATABASE_URL: DB_URL,
  IGS_TEST_ADMIN_URL: "postgresql://igs:igs@localhost:5433/igs",
  IGS_DB_APP_ROLE: "igs_app",
};
delete env.OPENAI_API_KEY; // never a paid call from a screenshot run
delete env.IGS_MODELS_URL; // hash embedder: retrieval works offline

const children = [];
function cleanup() {
  for (const c of children) {
    try {
      process.kill(-c.pid, "SIGTERM"); // whole process group: pnpm/uv leave their servers behind
    } catch {}
  }
}
process.on("exit", cleanup);
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => process.exit(130));

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { cwd: ROOT, env, encoding: "utf8", ...opts });
  if (r.status !== 0) {
    throw new Error(`${cmd} ${args.join(" ")} failed (${r.status})\n${r.stderr || r.stdout}`);
  }
  return r.stdout.trim();
}

function start(name, cmd, args, opts = {}) {
  const log = join(LOGS, `${name}.log`);
  const child = spawn("bash", ["-c", `exec ${[cmd, ...args].map((a) => `'${a}'`).join(" ")} >'${log}' 2>&1`], {
    cwd: ROOT,
    env,
    detached: true,
    stdio: "ignore",
    ...opts,
  });
  children.push(child);
  return child;
}

async function waitHttp(url, seconds) {
  for (let i = 0; i < seconds; i++) {
    try {
      const r = await fetch(url);
      if (r.status < 500) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`timeout waiting for ${url} (logs in ${LOGS})`);
}

function portFree(port) {
  return spawnSync("lsof", ["-ti", `tcp:${port}`, "-sTCP:LISTEN"], { encoding: "utf8" }).stdout.trim() === "";
}

// ── 1. data + API ────────────────────────────────────────────────────────────

async function startApi() {
  console.log(`▸ database ${DB} (migrate + seed + reset)`);
  run("uv", [
    "run",
    "python",
    "-c",
    `from igs_common.testing import prepare_database; prepare_database(${JSON.stringify(DB)})`,
  ]);
  run("uv", ["run", "python", "-m", "igs_common.seed"]);
  run("uv", ["run", "python", "-m", "igs_common.seed", "--reset-demo"]);
  spawnSync("uv", ["run", "python", "-m", "igs_common.ingest", "index-all", "--tenant", "igs"], {
    cwd: ROOT,
    env,
    stdio: "ignore",
  });

  console.log(`▸ API :${API_PORT}`);
  if (!portFree(API_PORT)) throw new Error(`port ${API_PORT} is busy`);
  start("api", "uv", ["run", "uvicorn", "igs_core.app:create_app", "--factory", "--port", String(API_PORT)]);
  await waitHttp(`${API}/readyz`, 90);
  return run("uv", [
    "run",
    "python",
    "services/core/scripts/mint_api_key.py",
    "--tenant",
    "igs",
    "--name",
    "visual compare",
    "--scope",
    "igs:read",
    "--scope",
    "igs:write",
    "--scope",
    "igs:approve",
    "--expires-days",
    "1",
    "--as-user",
    "lucia.fernandez@igs-demo.example",
  ], { stdio: ["ignore", "pipe", "ignore"] });
}

// ── 2. isolated web build ────────────────────────────────────────────────────

async function startWeb(key) {
  const web = join(COPY, "apps/web");
  const webEnv = {
    ...env,
    API_URL: API,
    NEXT_PUBLIC_API_URL: API,
    NEXT_PUBLIC_COPILOT_FAKE: "1",
    IGS_WEB_ALLOW_SHARED_KEY: "1",
    IGS_API_KEY: key,
  };
  if (!process.env.SKIP_BUILD || !existsSync(join(web, ".next"))) {
    console.log("▸ web: isolated copy + next build");
    // Whole repo (pnpm's relative node_modules links included): Turbopack refuses node_modules
    // symlinked from outside its root, so a copy of apps/web alone can't build.
    mkdirSync(COPY, { recursive: true });
    run("rsync", ["-a", "--delete", "--exclude", "/services/models/models", "--exclude", ".venv", "--exclude", ".git",
      "--exclude", "/apps/web/.next", "--exclude", "/build", "--exclude", "/spikes", "--exclude", "/infra",
      "--exclude", "/docs/reviews/visual", "--exclude", ".env.local", `${ROOT}/`, `${COPY}/`]);
    const b = spawnSync("pnpm", ["build"], { cwd: web, env: webEnv, encoding: "utf8" });
    writeFileSync(join(LOGS, "web-build.log"), `${b.stdout}\n${b.stderr}`);
    if (b.status !== 0) throw new Error(`web build failed: ${join(LOGS, "web-build.log")}`);
  }
  console.log(`▸ web :${WEB_PORT}`);
  if (!portFree(WEB_PORT)) throw new Error(`port ${WEB_PORT} is busy`);
  start("web", "pnpm", ["start", "-p", String(WEB_PORT)], { cwd: web, env: webEnv });
  await waitHttp(`${WEB}/`, 120);
}

// ── 3. screenshots + measurements ────────────────────────────────────────────

// Runs in the page: computed styles of the things the contract pins down.
function measure() {
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
  };
  const pick = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    return {
      text: (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60),
      family: s.fontFamily,
      size: s.fontSize,
      weight: s.fontWeight,
      tracking: s.letterSpacing,
      lineHeight: s.lineHeight,
      transform: s.textTransform,
      color: s.color,
      bg: s.backgroundColor,
      radius: s.borderTopLeftRadius,
      height: Math.round(el.getBoundingClientRect().height),
    };
  };
  const all = (sel, n = 12) => [...document.querySelectorAll(sel)].filter(vis).slice(0, n).map(pick);
  const bgs = new Map();
  for (const el of document.querySelectorAll("body *")) {
    if (!vis(el)) continue;
    const c = getComputedStyle(el).backgroundColor;
    if (c && c !== "rgba(0, 0, 0, 0)" && c !== "transparent") bgs.set(c, (bgs.get(c) || 0) + 1);
  }
  const paragraphs = [...document.querySelectorAll("main p, main li, main td")].filter(vis).slice(0, 40).map(pick);
  return {
    title: document.title,
    html: document.documentElement.className,
    body: pick(document.body),
    h1: pick([...document.querySelectorAll("h1")].find(vis)),
    h2: all("h2", 6),
    nav: all("nav a, nav button, [role=tab]", 14),
    buttons: all("main button, main a[class*=rounded]", 16),
    inputs: all("main input, main textarea, main select", 6),
    paragraphs,
    backgrounds: [...bgs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 14),
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
    // Outermost elements that stick out to the right (their parent fits): the ones to fix.
    overflowers: [...document.querySelectorAll("body *")]
      .filter((e) => {
        const out = (n) => n.getBoundingClientRect().right > window.innerWidth + 1 && getComputedStyle(n).position !== "fixed";
        return vis(e) && out(e) && e.parentElement && !out(e.parentElement);
      })
      .slice(0, 4)
      .map((e) => `${e.tagName.toLowerCase()} "${(e.textContent || "").trim().slice(0, 30)}" right=${Math.round(e.getBoundingClientRect().right)} .${String(e.className).split(" ").slice(0, 6).join(".")}`),
    errorText: /something went wrong|application error|algo salió mal|no se pudo/i.test(document.body.innerText),
  };
}

async function shoot(browser) {
  const results = [];
  for (const [vp, size] of Object.entries(VIEWPORTS)) {
    const ctx = await browser.newContext({ viewport: size, deviceScaleFactor: 1, colorScheme: "dark", reducedMotion: "reduce" });
    const page = await ctx.newPage();
    for (const [slug, path, owner, site] of ROUTES) {
      const file = join(OUT, `${slug}.${vp}.png`);
      let m = null;
      let status = 0;
      try {
        const res = await page.goto(WEB + path, { waitUntil: "networkidle", timeout: 45_000 });
        status = res?.status() ?? 0;
        await page.waitForTimeout(600);
        await page.screenshot({ path: file, fullPage: true });
        m = await page.evaluate(measure);
      } catch (err) {
        console.warn(`  ! ${vp} ${path}: ${err.message.split("\n")[0]}`);
      }
      console.log(`  ${vp.padEnd(7)} ${String(status).padEnd(4)} ${path}`);
      results.push({ slug, path, owner, site, vp, status, file, m });
    }
    await ctx.close();
  }
  return results;
}

// ── 4. side-by-side sheets (ffmpeg) ──────────────────────────────────────────

function sheet(r) {
  const site = join(SITE, `${r.vp}_${r.site}.png`);
  if (!existsSync(r.file) || !existsSync(site)) return null;
  const w = r.vp === "desktop" ? 960 : 390;
  const h = CROP[r.vp];
  const col = `scale=${w}:-2,crop=${w}:'min(ih,${h})':0:0,pad=${w}:${h}:0:0:color=0x0D0D0D`;
  const out = join(OUT, `sheet-${r.slug}.${r.vp}.png`);
  const g = spawnSync("ffmpeg", [
    "-y", "-loglevel", "error", "-i", site, "-i", r.file,
    "-filter_complex", `[0]${col}[a];[1]${col}[b];[a][b]hstack=inputs=2:shortest=0,pad=iw+24:ih:12:0:color=0x333333`,
    "-frames:v", "1", out,
  ]);
  return g.status === 0 ? out : null;
}

// ── 5. checklist ─────────────────────────────────────────────────────────────

const px = (v) => parseFloat(v) || 0;
const em = (s) => (px(s.size) ? px(s.tracking) / px(s.size) : 0);

function deviations(r) {
  const m = r.m;
  const out = [];
  const add = (sev, area, what, file = r.owner) => out.push({ sev, area, what, file, route: r.path, vp: r.vp });
  if (!m) return [{ sev: 5, area: "render", what: `page did not render (HTTP ${r.status})`, file: r.owner, route: r.path, vp: r.vp }];
  if (r.status >= 400) add(5, "render", `HTTP ${r.status}`);
  if (m.errorText) add(4, "render", "error copy visible on the page");
  if (m.overflowX) add(4, "spacing", `horizontal scroll at this width (${m.overflowers.join("; ") || "culprit not found"})`);
  if (m.body.bg !== SPEC.bg) add(4, "color", `body background ${m.body.bg} (site #0D0D0D)`, "apps/web/src/app/globals.css");
  if (!SPEC.fg.includes(m.body.color)) add(2, "color", `body text ${m.body.color} (site #F2F2F2)`, "apps/web/src/app/globals.css");
  if (!SPEC.bodyFont.test(m.body.family)) add(4, "font", `body font ${m.body.family.split(",")[0]} (site Montserrat)`, "apps/web/src/app/layout.tsx");
  if (!/\bdark\b/.test(m.html)) add(3, "color", `<html> lacks .dark (class="${m.html}")`, "apps/web/src/app/layout.tsx");

  const h = m.h1;
  if (!h) add(3, "font", "no visible h1");
  else {
    if (!SPEC.displayFonts.test(h.family)) add(4, "font", `h1 "${h.text}" in ${h.family.split(",")[0]} (site Barlow/Klein Condensed or DM Sans)`);
    if (/barlow/i.test(h.family)) {
      if (h.transform !== "uppercase") add(3, "font", `condensed h1 "${h.text}" not uppercase`);
      if (px(h.lineHeight) / px(h.size) > 0.95) add(2, "size", `h1 line-height ${h.lineHeight} at ${h.size} (site 0.8)`);
      if (em(h) > -0.01) add(2, "tracking", `h1 tracking ${h.tracking} (site −0.025em)`);
      if (r.vp === "desktop" && px(h.size) < 48) add(3, "size", `h1 ${h.size} (site 60–128px display)`);
    } else if (/dm sans/i.test(h.family) && em(h) > -0.03) add(2, "tracking", `h1 tracking ${h.tracking} (site DM Sans −0.06em)`);
  }
  for (const s of m.h2) {
    if (!SPEC.displayFonts.test(s.family)) {
      add(2, "font", `h2 "${s.text}" in ${s.family.split(",")[0]}`);
      break;
    }
  }
  const navBad = m.nav.filter((n) => px(n.radius) < 12 || !SPEC.navFont.test(n.family));
  if (navBad.length) add(3, "nav", `${navBad.length}/${m.nav.length} nav items not Montserrat pills (e.g. "${navBad[0].text}" r=${navBad[0].radius}, ${navBad[0].family.split(",")[0]})`, "apps/web/src/features/ops-shell/nav.tsx");
  const activeWrong = m.nav.find((n) => n.bg === "rgb(255, 255, 255)" && n.color !== "rgb(23, 23, 23)");
  if (activeWrong) add(2, "nav", `active pill text ${activeWrong.color} (site #171717)`, "apps/web/src/features/ops-shell/nav.tsx");
  const btnBad = m.buttons.filter((b) => px(b.radius) < 12 && b.bg !== "rgba(0, 0, 0, 0)");
  if (btnBad.length) add(3, "buttons", `${btnBad.length} filled buttons not pills (e.g. "${btnBad[0].text}" r=${btnBad[0].radius})`);
  const btnFont = m.buttons.filter((b) => b.text && !SPEC.bodyFont.test(b.family));
  if (btnFont.length) add(2, "buttons", `${btnFont.length} buttons not in Montserrat (e.g. "${btnFont[0].text}")`, "apps/web/src/components/ui/button.tsx");
  const pBad = m.paragraphs.filter((p) => !SPEC.bodyFont.test(p.family) && !/mono/i.test(p.family));
  if (pBad.length > 3) add(3, "font", `${pBad.length} text blocks not in Montserrat (e.g. "${pBad[0].text}" in ${pBad[0].family.split(",")[0]})`);
  const off = m.backgrounds.filter(([c]) => {
    const rgb = c.match(/\d+(\.\d+)?/g)?.map(Number) ?? [];
    const alpha = rgb[3] ?? 1;
    if (alpha < 0.35) return false; // white/5–white/30 overlays are the site idiom
    if (SPEC.surfaces.includes(`rgb(${rgb.slice(0, 3).join(", ")})`)) return false;
    const [r0, g0, b0] = rgb;
    const gray = Math.max(r0, g0, b0) - Math.min(r0, g0, b0) < 10;
    return !gray || (r0 > 60 && r0 < 230); // tinted or mid-gray panels
  });
  if (off.length) add(2, "color", `off-palette surfaces: ${off.slice(0, 4).map(([c, n]) => `${c}×${n}`).join(", ")}`);
  return out;
}

function writeChecklist(results, sheets) {
  const lines = [
    "# Visual comparison — checklist",
    "",
    `Generated ${new Date().toISOString()} by \`scripts/visual/compare.mjs\` against the contract in`,
    "`docs/design/igs-site-style.md`. Severity 5 = broken, 1 = polish. Sheets: site left, IGS OS right.",
    "",
  ];
  const all = [];
  for (const r of results) {
    const d = deviations(r);
    all.push(...d);
    const sh = sheets.get(`${r.slug}.${r.vp}`);
    lines.push(`## \`${r.path}\` — ${r.vp}`, "");
    lines.push(`Shot: \`${r.slug}.${r.vp}.png\`${sh ? ` · sheet: \`sheet-${r.slug}.${r.vp}.png\`` : ""} · owner: \`${r.owner}\``, "");
    if (r.m?.h1) lines.push(`h1: "${r.m.h1.text}" — ${r.m.h1.family.split(",")[0]} ${r.m.h1.weight} ${r.m.h1.size}/${r.m.h1.lineHeight}, tracking ${r.m.h1.tracking}, ${r.m.h1.transform}`, "");
    for (const area of ["render", "font", "size", "tracking", "color", "spacing", "nav", "buttons"]) {
      const hits = d.filter((x) => x.area === area);
      lines.push(`- [${hits.length ? " " : "x"}] **${area}**${hits.length ? `: ${hits.map((x) => `${x.what} (sev ${x.sev})`).join("; ")}` : ""}`);
    }
    lines.push("");
  }
  writeFileSync(join(OUT, "checklist.md"), lines.join("\n"));
  writeFileSync(join(OUT, "measurements.json"), JSON.stringify({ results: results.map(({ file, ...r }) => r), deviations: all }, null, 2));
  return all;
}

// ── main ─────────────────────────────────────────────────────────────────────

async function main() {
  mkdirSync(OUT, { recursive: true });
  mkdirSync(LOGS, { recursive: true });
  writeFileSync(join(OUT, ".gitignore"), "# Screenshots include the IGS public site: review material only.\n*.png\nmeasurements.json\n");
  const requireWeb = createRequire(join(ROOT, "apps/web/package.json"));
  const pw = await import(requireWeb.resolve("@playwright/test"));
  const chromium = pw.chromium ?? pw.default.chromium; // CJS package: named export may be on default

  const key = await startApi();
  await startWeb(key);

  console.log("▸ screenshots");
  const browser = await chromium.launch();
  const results = await shoot(browser);
  await browser.close();

  console.log("▸ sheets");
  const sheets = new Map();
  for (const r of results) {
    const s = sheet(r);
    if (s) sheets.set(`${r.slug}.${r.vp}`, s);
  }
  const devs = writeChecklist(results, sheets);
  console.log(`▸ ${results.length} shots, ${sheets.size} sheets, ${devs.length} deviations → ${OUT}`);
}

main()
  .catch((err) => {
    console.error(err.message);
    process.exitCode = 1;
  })
  .finally(cleanup);
