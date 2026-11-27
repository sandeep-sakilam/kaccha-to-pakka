import { test, expect } from "@playwright/test";
import { onboard } from "./helpers";

test("owner photographs a bill with the live camera; it is read and judged by the rules", async ({ page }) => {
  await onboard(page, "Bill Kirana");
  await page.getByRole("button", { name: /Electricity bill or shop licence/ }).click();
  await expect(page.getByRole("heading", { name: "Bill or shop licence" })).toBeVisible();
  await page.waitForFunction(() => (document.querySelector("video") as HTMLVideoElement | null)?.videoWidth);
  await page.getByRole("button", { name: "Take photo" }).click();
  await expect(page.getByTestId("capture-status")).toHaveText("Photo sent!");
  // The browser's test camera shows no real bill, so the rules do not count it, and say why.
  const doc = await page.evaluate(async () => {
    const h = { Authorization: `Bearer ${localStorage.getItem("ktp.token")}` };
    const biz = ((await (await fetch("/api/businesses", { headers: h })).json()) as { id: string }[])[0].id;
    const items = (await (await fetch(`/api/businesses/${biz}/evidence?kind=address_proof`, { headers: h })).json()) as { status: string }[];
    return items.map((e) => e.status);
  });
  expect(doc).toEqual(["rejected"]);
});
