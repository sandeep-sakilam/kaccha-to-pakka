import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { mockApi, posted } from "@/test-api";
import { renderAt } from "@/test-utils";
import DailySales from "./DailySales";

const show = () =>
  renderAt(
    <Routes>
      <Route path="/daily-sales/:businessId" element={<DailySales />} />
    </Routes>,
    "/daily-sales/b1",
  );

test("owner says today's sales, hears it back and saves it", async () => {
  await setLanguage("en");
  const days: { sale_date: string; amount_paise: number; method: string }[] = [];
  const calls = mockApi([
    [/POST .*daily-sales\/parse/, () => ({ amount_paise: 420000, sale_date: "2026-11-27", understood: true, prompt: "Today's sales, four thousand two hundred rupees: right?" })],
    [/POST .*daily-sales$/, (c) => {
      days.push({ ...(c.body as { sale_date: string; amount_paise: number }), method: "typed" });
      return days[0];
    }],
    [/GET .*daily-sales$/, () => days],
  ]);
  show();
  fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: "aaj ki bikri 4200" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Next" })));
  expect(await vi.waitFor(() => screen.getByTestId("sales-prompt"))).toHaveTextContent("four thousand two hundred");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Yes" })));
  expect(posted(calls, /daily-sales$/)[0].body).toEqual({ sale_date: "2026-11-27", amount_paise: 420000, method: "typed" });
  expect(await vi.waitFor(() => screen.getByTestId("sales-recent"))).toHaveTextContent("₹4,200");
});

test("two misses switch to the keypad", async () => {
  await setLanguage("en");
  const calls = mockApi([
    [/POST .*daily-sales\/parse/, () => ({ amount_paise: null, sale_date: "2026-11-27", understood: false, prompt: null })],
    [/POST .*daily-sales$/, () => ({})],
    [/GET .*daily-sales$/, () => []],
  ]);
  show();
  for (let i = 0; i < 2; i++) {
    fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: "hmm" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Next" })));
  }
  await vi.waitFor(() => screen.getByTestId("sales-buttons"));
  for (const d of "3500") await act(async () => fireEvent.click(screen.getAllByText(d, { selector: "button" })[0]));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save for today" })));
  expect(posted(calls, /daily-sales$/)[0].body).toMatchObject({ amount_paise: 350000, method: "buttons" });
});
