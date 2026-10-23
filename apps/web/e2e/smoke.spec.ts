import { expect, followLink, LAKESHORE, openOrFixme, ROUTES, test } from "./support";

// Every top-level route renders without server errors, hydration mismatches or uncaught throws.
const pages: Array<{ name: string; url: string; owner: string }> = [
  { name: "landing", url: ROUTES.landing, owner: "X8" },
  { name: "design system", url: ROUTES.design, owner: "X2" },
  { name: "coach chat", url: ROUTES.chat, owner: "X7" },
  { name: "ops today", url: ROUTES.today, owner: "X3" },
  { name: "trips", url: ROUTES.trips, owner: "X3" },
  { name: "leads", url: ROUTES.leads, owner: "X3" },
  { name: "accounts", url: ROUTES.accounts, owner: "X3" },
  { name: "approvals", url: ROUTES.approvals, owner: "X4" },
  { name: "flows", url: ROUTES.flows, owner: "X6" },
];

for (const p of pages) {
  test(`${p.name} renders cleanly`, async ({ page, consoleLog }) => {
    await openOrFixme(page, p.url, p.owner);
    await expect(page.locator("main, [role=main]").first()).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(consoleLog.errors, "console errors").toEqual([]);
  });
}

test("ops panel declares Spanish, coach surfaces English", async ({ page }) => {
  // V1 S1: the ops UI is Spanish but declared lang="en". Per-surface lang is X2's wave-3 work.
  await openOrFixme(page, ROUTES.today, "X3");
  const opsLang = await page.locator("html").getAttribute("lang");
  await openOrFixme(page, ROUTES.chat, "X7");
  const coachLang = await page.locator("html").getAttribute("lang");
  test.fixme(
    !(opsLang?.startsWith("es") && coachLang?.startsWith("en")),
    `per-surface lang not implemented yet (X2): ops=${opsLang} coach=${coachLang}`,
  );
});

test("trip detail opens from the trips list", async ({ page, consoleLog }) => {
  await openOrFixme(page, ROUTES.trips, "X3");
  await followLink(page, LAKESHORE, "X3");
  await expect(page.getByText(LAKESHORE).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(consoleLog.errors, "console errors").toEqual([]);
});

test("account detail opens from the accounts list", async ({ page, consoleLog }) => {
  await openOrFixme(page, ROUTES.accounts, "X3");
  await followLink(page, LAKESHORE, "X3");
  await expect(page.getByText(LAKESHORE).first()).toBeVisible();
  await page.waitForLoadState("networkidle");
  // V1 found a hydration mismatch here (es-AR time formatting).
  expect(consoleLog.errors, "console errors").toEqual([]);
});

test("unknown ids return 404", async ({ page }) => {
  for (const url of [
    "/ops/trips/00000000-0000-0000-0000-000000000000",
    "/ops/accounts/00000000-0000-0000-0000-000000000000",
    "/proposal/does-not-exist",
  ]) {
    const res = await page.goto(url);
    expect(res?.status(), url).toBe(404);
  }
});
