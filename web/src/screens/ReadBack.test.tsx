import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import ReadBack from "./ReadBack";

test("owner corrects a misread amount with the keypad", async () => {
  setLanguage("en");
  const queue = [
    { entry: { id: "e1", amount_paise: 100000, direction: "in", party_text: "Sharma ji" }, prompt: "Sharma ji, one thousand rupees, received on 12 October: right?", reason: "page_total" },
  ];
  const calls: { url: string; body: unknown }[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/confirm")) {
      calls.push({ url: u, body: JSON.parse(String(init?.body)) });
      queue.pop();
      return new Response("{}", { headers: { "content-type": "application/json" } });
    }
    return new Response(JSON.stringify(u.includes("/readback") ? queue : {}), { headers: { "content-type": "application/json" } });
  });
  renderAt(
    <Routes>
      <Route path="/readback/:businessId" element={<ReadBack />} />
    </Routes>,
    "/readback/b1",
  );
  expect(await screen.findByTestId("readback-prompt")).toHaveTextContent("one thousand rupees");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /no/i })));
  for (const d of "4000") await act(async () => fireEvent.click(screen.getByRole("button", { name: new RegExp(`^${d}$`) })));
  expect(screen.getByText("four thousand rupees")).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save" })));
  expect(calls[0].body).toEqual({ correct: false, amount_paise: 400000, direction: "in" });
  expect(await screen.findByText(/All entries checked/)).toBeInTheDocument();
});
