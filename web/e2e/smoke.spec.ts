import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/meta/sandbox", (r) =>
    r.fulfill({ json: { any_sandbox: true, services: { ai: true } } }),
  );
});

test("welcome loads in Hindi, switches language, shows Sandbox and installable manifest", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "नमस्ते! स्वागत है" })).toBeVisible();
  await expect(page.getByTestId("sandbox-badge")).toBeVisible();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(page.getByRole("heading", { name: /welcome/i })).toBeVisible();
  await page.getByRole("button", { name: /what we never do/i }).click();
  await expect(page.getByText("We never sell your data.")).toBeVisible();
  const manifest = await page.locator('link[rel="manifest"]').getAttribute("href");
  expect(manifest).toBeTruthy();
});
