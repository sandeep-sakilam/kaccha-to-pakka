import { test, expect, devices } from "@playwright/test";

test.use({ ...devices["Moto G4"] });

test("first screen is usable on a slow 3G phone with a 4x slower CPU", async ({ page, context }) => {
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 400, downloadThroughput: (400 * 1024) / 8, uploadThroughput: (400 * 1024) / 8 });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  const start = Date.now();
  await page.goto("/");
  await expect(page.getByRole("button", { name: "English", exact: true })).toBeVisible({ timeout: 20_000 });
  const ms = Date.now() - start;
  console.log(`interactive after ${ms} ms on slow 3G`);
  expect(ms).toBeLessThan(15_000);
  const tap = await page.getByRole("button", { name: "English", exact: true }).boundingBox();
  expect(tap!.height).toBeGreaterThanOrEqual(48); // large tap targets
});

test("keyboard users can skip to content and see focus", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: /skip to main content|मुख्य हिस्से/i })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.lang)).toMatch(/hi|en/);
});
