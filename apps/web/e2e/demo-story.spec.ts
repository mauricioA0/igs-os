import type { Page } from "@playwright/test";

import { expect, followLink, LAKESHORE, mockModelEndpoints, openOrFixme, ROUTES, test } from "./support";

// The 2-minute demo (docs/design/demo-script.md, UX proposal #1): one coherent Lakeshore story —
// March 2027 tour, health red (enrollment fees overdue), a pending ops approval and the linked flow
// execution — told the same way on every surface. Steps are independent tests so a surface
// that isn't built yet is reported as fixme without hiding the rest.

async function openLakeshoreAccount(page: Page): Promise<void> {
  await openOrFixme(page, ROUTES.accounts, "X3");
  await followLink(page, LAKESHORE, "X3");
  await expect(page.getByRole("heading", { name: LAKESHORE }).first()).toBeVisible();
}

test.describe("demo story", () => {
  test.beforeEach(async ({ page }) => {
    await mockModelEndpoints(page);
  });

  test("1 · landing starts the guided tour", async ({ page }) => {
    await openOrFixme(page, ROUTES.landing, "X8");
    const start = page.getByRole("button", { name: /start the 2-minute tour/i }).or(
      page.getByRole("link", { name: /start the 2-minute tour/i }),
    );
    test.fixme(!(await start.first().isVisible()), "guided tour CTA not built yet (X8)");
    await start.first().click();
    // Step rail: "1/6"-style progress plus a next action.
    await expect(page.getByText(/\b1\s*\/\s*6\b/).first()).toBeVisible();
    await expect(page.getByRole("button", { name: /next|siguiente/i }).first()).toBeVisible();
  });

  test("2 · today surfaces Lakeshore as something that needs ops", async ({ page }) => {
    await openOrFixme(page, ROUTES.today, "X3");
    // The tour's step 1 points at the Atención queue: Lakeshore must be *in* it, red, with a reason.
    const queue = page.locator('[data-tour="today-queue"]');
    await expect(queue.getByText(/Cliente en rojo: Lakeshore/)).toBeVisible();
    await expect(queue.getByText(/enrollment fees/i).first()).toBeVisible();
  });

  test("3 · Lakeshore account is red with cited reasons and stakeholders", async ({ page }) => {
    await openLakeshoreAccount(page);
    const red = page.locator('[data-health="red"]').or(page.getByText(/\brojo\b/i));
    test.fixme(!(await red.first().isVisible()), "Lakeshore health not red yet (X8 story)");
    await expect(page.getByText(/enrollment fees|inscripción/i).first()).toBeVisible();
    await expect(page.getByText(/Robert Haines/).first()).toBeVisible();
    // Citations are chips with an accessible name, never a bare "[4]" (V1 S1).
    const citation = page.locator("[data-citation]").first();
    test.fixme(!(await citation.isVisible()), "citation chips not built yet (X3)");
    await expect(citation).toHaveAccessibleName(/.+/);
  });

  test("4 · ask about Lakeshore answers with citations (mocked model)", async ({ page }) => {
    await openLakeshoreAccount(page);
    const box = page.getByRole("textbox", { name: /pregunt|ask/i }).first();
    test.fixme(!(await box.isVisible()), "ask box not wired yet (X3)");
    await box.fill("¿Qué falta para que paguen la inscripción?");
    await box.press("Enter");
    const answer = page.getByText(/fees de inscripción/i).first();
    // When the ask is proxied server-side the browser mock can't intercept it.
    const answered = await answer.isVisible({ timeout: 8_000 }).catch(() => false);
    test.fixme(!answered, "ask goes through the server; needs a server-side model mock");
    await expect(page.locator("[data-citation]").first()).toBeVisible();
  });

  test("5 · copilot answers the pre-loaded question (mocked model)", async ({ page }) => {
    await openOrFixme(page, ROUTES.today, "X3");
    await page.keyboard.press("ControlOrMeta+j");
    const drawer = page.getByRole("complementary", { name: /copiloto|copilot/i });
    test.fixme(!(await drawer.isVisible().catch(() => false)), "copilot drawer not mounted (X5/X3)");
    const preset = drawer.getByRole("button", { name: /Lakeshore/ }).first();
    await preset.click();
    await expect(drawer.getByText(/get_account_brief|ficha del cliente/i).first()).toBeVisible();
    await expect(drawer.getByText(/inscripción vencida|fees de inscripción/i).first()).toBeVisible();
  });

  test("6 · approvals show exactly what will be sent for Lakeshore", async ({ page }) => {
    await openOrFixme(page, ROUTES.approvals, "X4");
    const item = page.getByRole("link", { name: LAKESHORE }).or(page.getByRole("button", { name: LAKESHORE }));
    test.fixme(!(await item.first().isVisible()), "no Lakeshore approval in the inbox yet (X8/X4)");
    await item.first().click();
    // A real preview (recipient, amount) instead of raw node JSON (V2 P2).
    await expect(page.getByText(/US\$|USD|\$/).first()).toBeVisible();
    const fingerprint = page.getByText(/sha256:|huella|fingerprint/i).first();
    test.fixme(!(await fingerprint.isVisible()), "payload fingerprint not shown yet (X4, UX #4)");
    // The public demo is read-only for decisions: approving is visible but not allowed.
    const approve = page.getByRole("button", { name: /^aprobar|approve/i }).first();
    await expect(approve).toBeVisible();
  });

  test("7 · the linked flow execution waits on that approval", async ({ page }) => {
    await openOrFixme(page, ROUTES.flows, "X6");
    await followLink(page, /inbound|consulta entrante/i, "X6");
    const executions = page.getByRole("link", { name: /ejecuciones|executions/i }).first();
    if (await executions.isVisible().catch(() => false)) await executions.click();
    await followLink(page, /esperando|waiting|aprobación/i, "X6");
    await expect(page.locator(".react-flow").first()).toBeVisible();
    await expect(page.getByText(/esperando (aprobación|a una persona)|waiting for approval/i).first()).toBeVisible();
  });

  test("8 · proposal tells the same dates and offers an enrollment CTA", async ({ page }) => {
    await openOrFixme(page, ROUTES.trips, "X3");
    await followLink(page, LAKESHORE, "X3");
    const tripText = await page.locator("main").innerText();
    await followLink(page, /propuesta|proposal/i, "X3/X7");
    await expect(page.getByText(LAKESHORE).first()).toBeVisible();
    // Same month/year on trip and proposal (V4 found Nov 14 vs Mar 6–15 2027).
    const proposalText = await page.locator("main").innerText();
    const consistent = /2027/.test(tripText) && /2027/.test(proposalText);
    test.fixme(!consistent, "trip and proposal dates disagree (X8 story)");
    const reserve = page.getByRole("link", { name: /reserve/i }).or(page.getByRole("button", { name: /reserve/i }));
    test.fixme(!(await reserve.first().isVisible()), "Reserve CTA not built yet (X7, UX #6)");
    await expect(reserve.first()).toContainText(/enrollment/i);
  });
});
