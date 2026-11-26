import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner links a bank through the Sandbox Account Aggregator", async ({ page }) => {
  await onboard(page, "Bank Test Kirana");
  await page.getByRole("button", { name: /Link bank account/ }).click();
  await page.getByRole("button", { name: "Link bank", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Sandbox Account Aggregator" })).toBeVisible();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByTestId("aa-status")).toContainText(/payments received from Sandbox Bank/);
});
