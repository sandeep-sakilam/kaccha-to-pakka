import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner says a credit entry and a cash repayment aloud; both are saved as said", async ({ page }) => {
  await onboard(page, "Udhaar Kirana");
  await page.getByRole("button", { name: /Read ledger aloud/ }).click();

  await page.getByLabel("Or type here").fill("Sharma ji ke naam 1200 likhe");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByTestId("voice-prompt")).toContainText("of goods on credit");
  await page.getByRole("button", { name: "Yes", exact: true }).click();

  await page.getByLabel("Or type here").fill("Sharma ji se 500 nakad mile");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByTestId("voice-prompt")).toContainText("received in cash");
  await page.getByRole("button", { name: "Yes", exact: true }).click();

  await expect(page.getByText("2 entries ready")).toBeVisible();
  await page.getByRole("button", { name: /Save all entries/ }).click();
  await expect(page.getByRole("status").filter({ hasText: "Entries saved" })).toBeVisible();

  const ledger = await page.evaluate(async () => {
    const h = { Authorization: `Bearer ${localStorage.getItem("ktp.token")}` };
    const biz = ((await (await fetch("/api/businesses", { headers: h })).json()) as { id: string }[])[0].id;
    return (await (await fetch(`/api/businesses/${biz}/ledger`, { headers: h })).json()) as { amount_paise: number; kind: string; paid_by: string | null }[];
  });
  expect(ledger.map((e) => [e.amount_paise, e.kind, e.paid_by])).toEqual([
    [120000, "credit_given", null],
    [50000, "money", "cash"],
  ]);
});
