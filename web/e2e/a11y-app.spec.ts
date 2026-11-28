import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { onboard } from "./helpers";

async function audit(page: Page, name: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
  return results.violations.map((v) => `${name}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
}

test("home, passport, share and lender screens have no WCAG 2.2 AA violations", async ({ page, context }) => {
  await onboard(page, "Audit Kirana");
  await page.waitForTimeout(400);
  const found = await audit(page, "home");
  await page.getByRole("button", { name: "My Trust Passport" }).click();
  await page.getByRole("button", { name: "Make my passport" }).click();
  await expect(page.getByTestId("band")).toBeVisible();
  await page.waitForTimeout(400);
  found.push(...(await audit(page, "passport")));
  await page.getByRole("button", { name: "Share with a lender" }).click();
  await page.getByLabel("Lender name and branch").fill("SBI Rajwada branch");
  await page.getByRole("button", { name: "Create share link" }).click();
  const link = (await page.getByTestId("share-link").first().textContent())!;
  await page.waitForTimeout(400);
  found.push(...(await audit(page, "shares")));
  const lender = await context.newPage();
  await lender.goto(new URL(link).pathname);
  await expect(lender.getByTestId("live-status")).toBeVisible();
  await lender.waitForTimeout(400);
  found.push(...(await audit(lender, "lender")));
  expect(found).toEqual([]);
});
