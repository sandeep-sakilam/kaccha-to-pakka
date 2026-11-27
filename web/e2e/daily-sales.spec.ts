import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner tells today's sales by typing, hears it back and sees it saved", async ({ page }) => {
  await onboard(page, "Bikri Kirana");
  await page.getByRole("button", { name: /Tell today's sales/ }).click();
  await page.getByLabel("Or type here").fill("aaj ki bikri 4200");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByTestId("sales-prompt")).toHaveText("Today's sales, four thousand two hundred rupees: right?");
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await expect(page.getByTestId("sales-recent")).toContainText("₹4,200");
});
