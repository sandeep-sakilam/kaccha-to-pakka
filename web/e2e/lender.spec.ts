import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner shares with a lender; lender sees watermark, verifies QR, forged QR fails", async ({ page, context }) => {
  await onboard(page, "Lender Test Kirana");
  await page.getByRole("button", { name: "My Trust Passport" }).click();
  await page.getByRole("button", { name: "Make my passport" }).click();
  await expect(page.getByTestId("band")).toBeVisible();
  const verifyUrl = await page.evaluate(async () => {
    const id = location.pathname.split("/").pop();
    const res = await fetch(`/api/businesses/${id}/passport`, { headers: { Authorization: `Bearer ${localStorage.getItem("ktp.token")}` } });
    return ((await res.json()) as { verify_url: string }).verify_url;
  });
  await page.getByRole("button", { name: "Share with a lender" }).click();
  await page.getByLabel("Lender name and branch").fill("SBI Rajwada branch");
  await page.getByRole("button", { name: "Create share link" }).click();
  const link = (await page.getByTestId("share-link").first().textContent())!;

  const lender = await context.newPage();
  await lender.goto(new URL(link).pathname);
  await expect(lender.getByTestId("watermark")).toContainText("Shared with SBI Rajwada branch");
  await expect(lender.getByTestId("live-status")).toContainText("Valid");

  const path = new URL(verifyUrl);
  await lender.goto(path.pathname + path.hash);
  await expect(lender.getByTestId("signature")).toContainText("Signature valid");
  await lender.goto(path.pathname + path.hash.slice(0, -8) + "AAAAAAAA");
  await expect(lender.getByTestId("signature")).toContainText("NOT valid");

  await page.reload();
  await expect(page.getByTestId("access-log")).toContainText("SBI Rajwada branch viewed");
});
