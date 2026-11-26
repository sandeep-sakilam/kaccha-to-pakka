import AxeBuilder from "@axe-core/playwright";
import { test, expect, type Page } from "@playwright/test";
import { onboard } from "./helpers";

async function audit(page: Page, name: string) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const summary = results.violations.map((v) => `${name}: ${v.id} (${v.impact}) ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`);
  expect(summary).toEqual([]);
}

test("welcome, never-do and login screens have no WCAG 2.2 AA violations", async ({ page }) => {
  await page.goto("/");
  await audit(page, "welcome-hi");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await audit(page, "welcome-en");
  await page.getByRole("button", { name: /what we never do/i }).click();
  await audit(page, "never");
  await page.goto("/start");
  await audit(page, "login");
});

test("owner screens have no WCAG 2.2 AA violations", async ({ page }) => {
  await onboard(page, "A11y Kirana");
  await audit(page, "home");
  await page.getByRole("button", { name: "My Trust Passport" }).click();
  await page.getByRole("button", { name: "Make my passport" }).click();
  await expect(page.getByTestId("band")).toBeVisible();
  await audit(page, "passport");
  await page.goto("/lender");
  await audit(page, "lender");
});
