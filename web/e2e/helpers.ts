import { expect, type Page } from "@playwright/test";

export async function typeDigits(page: Page, digits: string) {
  for (const d of digits) await page.getByRole("group", { name: "keypad" }).getByRole("button", { name: d, exact: true }).click();
}

/** Sign up a new owner in English and finish onboarding (skips the shop photo). */
export async function onboard(page: Page, name = "Test Kirana") {
  await page.goto("/");
  await page.getByRole("button", { name: "English", exact: true }).click();
  await page.getByRole("button", { name: "Start" }).click();
  const phone = "9" + String(Math.floor(Math.random() * 1e9)).padStart(9, "0");
  await typeDigits(page, phone);
  await page.getByRole("button", { name: "Send OTP" }).click();
  const otp = (await page.getByTestId("sandbox-otp").textContent())!.replace(/\D/g, "");
  await typeDigits(page, otp);
  await page.getByRole("button", { name: "Check OTP" }).click();
  await expect(page.getByText(/4-digit PIN/).first()).toBeVisible();
  await typeDigits(page, "4826");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes, I agree" }).click();
  await page.getByLabel("Or type here").fill(name);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await page.getByRole("button", { name: /Kirana \/ grocery/ }).click();
  await page.getByLabel("Or type here").fill("2012");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await page.getByLabel("Or type here").fill("Rajwada");
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Yes", exact: true }).click();
  await page.getByRole("button", { name: "Skip" }).click();
  await page.goto("/home");
  await expect(page.getByTestId("business-name")).toHaveText(name);
  return phone;
}
