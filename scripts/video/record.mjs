// Records the demo video scene by scene (one WebM per scene) against a running local stack.
//
//   node scripts/video/record.mjs            # web on http://localhost:3320 (see scripts/video/README.md)
//
// Each scene runs in its own browser context so it gets its own video file; the guided tour's
// step lives in the URL (?tour=N), so scenes start straight on their page. A cursor overlay is
// injected because headless recordings don't show the pointer.
import { mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../..");
const require = createRequire(join(root, "apps/web/package.json"));
const { chromium } = require("@playwright/test");

const BASE = process.env.VIDEO_BASE_URL ?? "http://localhost:3320";
const OUT = join(root, "build/video/raw");
const SIZE = { width: 1920, height: 1080 };
const IDS = {
  account: "17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8",
  trip: "c0b16481-9260-5765-8dd1-788c7b2a63ab",
  approval: "d129a224-c013-5340-b0eb-95fe1c3fb000",
  execution: "57c5d89c-7923-572a-beec-09b92e5e1f29",
};

const CURSOR = `
  (() => {
    const install = () => {
      if (document.getElementById("__cursor")) return;
      const c = document.createElement("div");
      c.id = "__cursor";
      Object.assign(c.style, {
        position: "fixed", left: "0px", top: "0px", width: "22px", height: "22px",
        marginLeft: "-11px", marginTop: "-11px", borderRadius: "50%", zIndex: 2147483647,
        pointerEvents: "none", background: "rgba(20,20,20,.35)", border: "2px solid #fff",
        boxShadow: "0 0 0 1px rgba(0,0,0,.4)", transition: "transform .12s ease",
      });
      document.documentElement.appendChild(c);
      addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; }, true);
      addEventListener("mousedown", () => { c.style.transform = "scale(.7)"; }, true);
      addEventListener("mouseup", () => { c.style.transform = "scale(1)"; }, true);
    };
    if (document.readyState === "loading") addEventListener("DOMContentLoaded", install); else install();
  })();
`;

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
let mouse = { x: 960, y: 540 };

async function glide(page, target, { steps = 28 } = {}) {
  const box = await target.boundingBox();
  if (!box) return;
  const x = box.x + Math.min(box.width / 2, 120);
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps });
  mouse = { x, y };
}

async function smoothScroll(page, dy, ms = 1600) {
  await page.evaluate(
    ([d, t]) =>
      new Promise((done) => {
        const start = scrollY;
        const t0 = performance.now();
        const step = (now) => {
          const k = Math.min(1, (now - t0) / t);
          const ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
          scrollTo(0, start + d * ease);
          if (k < 1) requestAnimationFrame(step); else done();
        };
        requestAnimationFrame(step);
      }),
    [dy, ms],
  );
}

async function scene(browser, id, run) {
  const dir = join(OUT, id);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const context = await browser.newContext({
    viewport: SIZE,
    recordVideo: { dir, size: SIZE },
    colorScheme: "dark",
    locale: "es-AR",
  });
  await context.addInitScript(CURSOR);
  const page = await context.newPage();
  await page.mouse.move(mouse.x, mouse.y);
  const t0 = Date.now();
  try {
    await run(page);
  } finally {
    await context.close();
  }
  const [file] = readdirSync(dir).filter((f) => f.endsWith(".webm"));
  renameSync(join(dir, file), join(OUT, `${id}.webm`));
  rmSync(dir, { recursive: true, force: true });
  console.log(`${id}: ${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

// The "Copiloto ⌘J" pill in the ops header (the shortcut is the same; a visible click reads better).
async function openCopilot(page) {
  const button = page.getByRole("button", { name: /^Copiloto/ }).first();
  await glide(page, button);
  await button.click();
  await page.getByRole("complementary", { name: /Copiloto/ }).waitFor();
}

async function open(page, path) {
  await page.goto(BASE + path, { waitUntil: "networkidle" });
  await wait(600);
}

const scenes = {
  "01-landing": async (page) => {
    await open(page, "/");
    await wait(2500);
    const cta = page.getByRole("link", { name: /Start the 2-minute tour/ });
    await glide(page, cta);
    await wait(5500);
    await page.mouse.down();
    await page.mouse.up();
    await wait(1500);
  },
  "02-today": async (page) => {
    await open(page, "/ops?tour=1");
    await wait(2500);
    // Lakeshore surfaces in "pending approvals" (its trip departs in March, so it isn't in
    // the today/tomorrow queue); the tour spotlights the queue.
    await glide(page, page.locator('[data-tour="today-queue"]'));
    await wait(4500);
    const lakeshore = page.getByText(/Lakeshore University/).first();
    await lakeshore.scrollIntoViewIfNeeded();
    await glide(page, lakeshore);
    await wait(7000);
  },
  "03-account": async (page) => {
    await open(page, `/ops/accounts/${IDS.account}?tour=2`);
    await wait(2500);
    await glide(page, page.locator('[data-tour="account-health"]').getByText(/Riesgo|rojo|Rojo/).first());
    await wait(3500);
    const chip = page.locator("a[aria-describedby], span[tabindex='0'][aria-describedby]").first();
    await chip.scrollIntoViewIfNeeded();
    await glide(page, chip);
    await chip.hover();
    await wait(4500);
    await smoothScroll(page, 420, 2000);
    await wait(3500);
  },
  "04-copilot": async (page) => {
    await open(page, `/ops/accounts/${IDS.account}`);
    await wait(400);
    await openCopilot(page);
    const drawer = page.getByRole("complementary", { name: /Copiloto/ });
    await wait(400);
    const preset = drawer.getByRole("button", { name: /Lakeshore/ }).first();
    await glide(page, preset, { steps: 16 });
    await preset.click();
    // Hold until the answer has fully streamed (the drawer's live region announces "done").
    await page.getByText("El copiloto terminó de responder.").waitFor({ state: "attached", timeout: 60000 });
    await wait(1500);
  },
  "05-approvals": async (page) => {
    await open(page, `/ops/approvals?id=${IDS.approval}&tour=4`);
    await wait(1400);
    await glide(page, page.locator('[data-tour="approval-card"]').locator("h1, h2").first());
    await wait(2000);
    await smoothScroll(page, 360, 1200);
    await wait(700);
    const approve = page.getByRole("button", { name: /^Aprobar$|Aprobar/ }).first();
    await approve.scrollIntoViewIfNeeded();
    await glide(page, approve, { steps: 18 });
    await wait(400);
    await approve.click();
    await wait(700);
    await page.getByRole("button", { name: /Presioná A otra vez|Aprobar/ }).first().click();
    await wait(900);
    // The inbox advances to the next pending item; show Lakeshore's resolved state instead.
    const resolved = page.getByRole("button", { name: /^Resueltas/ }).first();
    await glide(page, resolved, { steps: 16 });
    await resolved.click();
    await wait(500);
    await page.getByText(/IGS-2711/).first().click().catch(() => {});
    await wait(3000);
  },
  "06-editor": async (page) => {
    await open(page, "/ops/flows/inbound-inquiry");
    await wait(2500);
    // Pick a block on the canvas, then open the test panel (without starting a run).
    const block = page.locator(".react-flow__node").nth(1);
    await glide(page, block);
    await block.click().catch(() => {});
    await wait(2500);
    const library = page.getByRole("searchbox").first();
    await glide(page, library).catch(() => {});
    await wait(2000);
    const test = page.getByRole("button", { name: /Probar/ }).first();
    await glide(page, test);
    await test.click();
    await wait(4000);
  },
  "07-execution": async (page) => {
    await open(page, `/ops/flows/inbound-inquiry/executions/${IDS.execution}?tour=5`);
    await wait(3500);
    await glide(page, page.locator('[data-tour="execution-graph"]'));
    await wait(3500);
    const steps = page.getByRole("button", { name: "Pasos" }).first();
    await glide(page, steps);
    await steps.click();
    await wait(4000);
  },
  "08-proposal": async (page) => {
    await open(page, `/proposal/${IDS.trip}?tour=6`);
    await wait(2500);
    await smoothScroll(page, 900, 2600);
    await wait(1800);
    await smoothScroll(page, 1400, 2600);
    await wait(1500);
    const reserve = page.getByRole("button", { name: /Reserve/ }).first();
    await reserve.scrollIntoViewIfNeeded().catch(() => {});
    await glide(page, reserve).catch(() => {});
    await wait(2000);
  },
  "09-guide": async (page) => {
    // The coach's chat on the site, then the guide bubble (scripted: ?guide=fake).
    await open(page, "/chat?guide=fake");
    await wait(3000);
    const bubble = page.getByRole("button", { name: /Assistant · POC/ });
    await glide(page, bubble);
    await wait(800);
    await bubble.click();
    await page.getByTestId("guide-poc-banner").waitFor();
    await glide(page, page.getByTestId("guide-poc-banner"), { steps: 16 });
    await wait(2500);
    const ask = page.getByRole("button", { name: "What is IGS OS?" });
    await glide(page, ask, { steps: 16 });
    await ask.click();
    await page.getByRole("link", { name: /Open the ops panel/ }).waitFor({ timeout: 30000 });
    await wait(4500);
  },
  "10-mcp": async (page) => {
    await open(page, "/ops");
    await openCopilot(page);
    const drawer = page.getByRole("complementary", { name: /Copiloto/ });
    const tab = drawer.getByRole("tab", { name: "MCP" });
    await glide(page, tab);
    await tab.click();
    await wait(5000);
    await open(page, "/design");
    await smoothScroll(page, 900, 2400);
    await wait(3000);
  },
};

const only = process.argv.slice(2);
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ headless: true });
for (const [id, run] of Object.entries(scenes)) {
  if (only.length && !only.includes(id)) continue;
  await scene(browser, id, run);
}
await browser.close();
