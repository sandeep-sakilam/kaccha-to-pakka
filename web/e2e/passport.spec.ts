import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner links a bank, makes a passport and sees coaching", async ({ page }) => {
  await onboard(page, "Passport Kirana");
  await page.getByRole("button", { name: /Link bank account/ }).click();
  await page.getByRole("button", { name: "Link bank", exact: true }).click();
  await page.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByTestId("aa-status")).toContainText(/payments received/);
  await page.getByRole("button", { name: "Done" }).click();
  await page.getByRole("button", { name: "My Trust Passport" }).click();
  await page.getByRole("button", { name: "Make my passport" }).click();
  await expect(page.getByTestId("band")).toHaveText(/[A-E]/);
  await expect(page.getByTestId("headline")).toContainText("Your passport");
  await expect(page.getByTestId("coaching")).toContainText(/Ask 3 more suppliers/);
  await expect(page.getByAltText(/lender scans this/)).toBeVisible();
});
