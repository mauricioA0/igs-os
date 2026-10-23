import AxeBuilder from "@axe-core/playwright";
import { expect, test as base, type Page } from "@playwright/test";

// Final URLs per docs/CONTRACTS.md (wave 3). Detail pages are reached by clicking, never by
// hard-coded ids: the seed uses deterministic UUIDs that the UI may or may not expose.
export const ROUTES = {
  landing: "/",
  design: "/design",
  chat: "/chat",
  today: "/ops",
  trips: "/ops/trips",
  leads: "/ops/leads",
  accounts: "/ops/accounts",
  approvals: "/ops/approvals",
  flows: "/ops/flows",
} as const;

export const LAKESHORE = /Lakeshore/i;

/** Errors the browser reports while a page is open (hydration mismatches, uncaught throws). */
export type ConsoleLog = { errors: string[] };

export const test = base.extend<{ consoleLog: ConsoleLog }>({
  consoleLog: async ({ page }, provide) => {
    const log: ConsoleLog = { errors: [] };
    page.on("pageerror", (err) => log.errors.push(`pageerror: ${err.message}`));
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      // Dev-only noise that isn't a product bug.
      if (/Download the React DevTools|favicon\.ico/.test(text)) return;
      log.errors.push(text);
    });
    await provide(log);
  },
});

export { expect };

/** Opens a route; marks the test fixme (with the reason) when the route isn't built yet. */
export async function openOrFixme(page: Page, url: string, owner: string): Promise<void> {
  const res = await page.goto(url);
  test.fixme(res?.status() === 404, `${url} not built yet (${owner})`);
  expect(res?.status(), `${url} status`).toBeLessThan(400);
}

/** Clicks the first link matching `name`; fixme when the page doesn't offer it yet. */
export async function followLink(page: Page, name: RegExp, owner: string): Promise<void> {
  const link = page.getByRole("link", { name }).first();
  const visible = await link.isVisible().catch(() => false);
  test.fixme(!visible, `no link matching ${name} yet (${owner})`);
  await link.click();
  await page.waitForLoadState("domcontentloaded");
}

/** axe-core WCAG 2.x A/AA scan; fails on serious or critical violations only. */
export async function expectNoSeriousA11yViolations(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    // React Flow's canvas renders decorative SVG handles; its keyboard list view is what we audit.
    .exclude(".react-flow__renderer")
    .analyze();
  const blocking = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical",
  );
  const summary = blocking.map(
    (v) => `${v.impact} ${v.id}: ${v.help} (${v.nodes.length}×) e.g. ${v.nodes[0]?.target.join(" ")}`,
  );
  expect(summary, "serious/critical axe violations").toEqual([]);
}

/**
 * Model-backed endpoints are mocked in the browser so e2e never calls a paid model. Works when
 * the UI calls the API from the client; when a server action proxies the call, the real API
 * answers (and without OPENAI_API_KEY it fails closed), which the tests treat as fixme.
 */
export async function mockModelEndpoints(page: Page): Promise<void> {
  await page.route(/\/v1\/accounts\/[^/]+\/ask$/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        answer:
          "Lakeshore está en rojo: los fees de inscripción (24 × US$95) vencieron hace una semana y la PO espera la aprobación de Robert Haines [1].",
        citations: [
          {
            n: 1,
            interaction_id: "00000000-0000-0000-0000-000000000001",
            channel: "email",
            occurred_at: "2026-10-15T14:00:00Z",
            stakeholder: "Robert Haines",
            excerpt: "The purchase order has to be re-approved by Robert Haines before we release the enrollment fees.",
          },
        ],
        grounded: true,
        model: "e2e-mock",
      }),
    }),
  );
  // Same wire format as services/core (igs_core/agent/routes.py): `event: <type>` + JSON data.
  const turn: Array<[string, Record<string, unknown>]> = [
    ["start", { run_id: "e2e", conversation_id: "e2e-conv" }],
    ["tool_start", { call_id: "c1", name: "get_account_brief", input: { account: "Lakeshore" } }],
    [
      "tool_end",
      { call_id: "c1", name: "get_account_brief", output: { health: "red" }, is_error: false, ms: 12 },
    ],
    ["text", { delta: "Lakeshore está en rojo por la inscripción vencida: falta que Haines re-apruebe la PO." }],
    ["done", { run_id: "e2e", conversation_id: "e2e-conv", stop_reason: "stop" }],
  ];
  await page.route(/\/(v1|api)\/copilot\/turns/, (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: turn.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(""),
    }),
  );
}
