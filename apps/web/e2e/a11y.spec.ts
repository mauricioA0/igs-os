import { expectNoSeriousA11yViolations, followLink, LAKESHORE, openOrFixme, ROUTES, test } from "./support";

// WCAG 2.2 AA spot audit (axe-core): serious and critical violations fail the build.
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
  test(`a11y: ${p.name}`, async ({ page }) => {
    await openOrFixme(page, p.url, p.owner);
    await page.waitForLoadState("networkidle");
    await expectNoSeriousA11yViolations(page);
  });
}

for (const theme of ["light", "dark"] as const) {
  test(`a11y: Lakeshore account (${theme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: theme });
    await openOrFixme(page, ROUTES.accounts, "X3");
    await followLink(page, LAKESHORE, "X3");
    await page.waitForLoadState("networkidle");
    await expectNoSeriousA11yViolations(page);
  });
}

test("a11y: Lakeshore trip", async ({ page }) => {
  await openOrFixme(page, ROUTES.trips, "X3");
  await followLink(page, LAKESHORE, "X3");
  await page.waitForLoadState("networkidle");
  await expectNoSeriousA11yViolations(page);
});

test("a11y: proposal", async ({ page }) => {
  await openOrFixme(page, ROUTES.landing, "X8");
  await followLink(page, /proposal/i, "X8/X7");
  await page.waitForLoadState("networkidle");
  await expectNoSeriousA11yViolations(page);
});
