import { test, expect, type Page } from "@playwright/test";

async function typeDigits(page: Page, digits: string) {
  for (const d of digits) await page.getByRole("group", { name: "keypad" }).getByRole("button", { name: d, exact: true }).click();
}

test("owner joins by phone, consents, and builds a profile", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await page.getByRole("button", { name: "Start" }).click();

  const phone = "98" + String(Date.now()).slice(-8);
  await typeDigits(page, phone);
  await page.getByRole("button", { name: "Send OTP" }).click();
  const otpText = await page.getByTestId("sandbox-otp").textContent();
  await typeDigits(page, otpText!.replace(/\D/g, ""));
  await page.getByRole("button", { name: "Check OTP" }).click();

  await expect(page.getByText("Make a 4-digit PIN")).toBeVisible();
  await typeDigits(page, "4826");
  await page.getByRole("button", { name: "Next" }).click();

  await expect(page.getByRole("heading", { name: "Before we start" })).toBeVisible();
  await expect(page.getByText(/never sell your data/)).toBeVisible();
  await page.getByRole("button", { name: "Yes, I agree" }).click();

  await page.getByLabel("Or type here").fill("Sharma Kirana");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByTestId("confirm-box")).toContainText("Sharma Kirana");
  await page.getByRole("button", { name: "Yes", exact: true }).click();

  await page.getByRole("button", { name: /Kirana \/ grocery/ }).click();
  await page.getByLabel("Or type here").fill("2012 se");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await page.getByLabel("Or type here").fill("Rajwada ke paas");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();

  await page.getByRole("button", { name: "Skip" }).click();

  await expect(page.getByRole("heading", { name: "Photo of your shop front" })).toBeVisible();
  await page.waitForFunction(() => (document.querySelector("video") as HTMLVideoElement | null)?.videoWidth);
  await page.getByRole("button", { name: "Take photo" }).click();
  await expect(page.getByTestId("capture-status")).toHaveText("Photo sent!");
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("business-name")).toHaveText("Sharma Kirana");
});
