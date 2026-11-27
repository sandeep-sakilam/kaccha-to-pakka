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
  expect(calls[0].body).toEqual({ correct: false, amount_paise: 400000, direction: "in", kind: "money", paid_by: null });
  expect(await screen.findByText(/All entries checked/)).toBeInTheDocument();
});

test("owner says a line was goods given on credit, keeping the amount", async () => {
  setLanguage("en");
  const queue = [
    { entry: { id: "e2", amount_paise: 50000, direction: "in", kind: "money", paid_by: null, party_text: "Sharma ji" }, prompt: "Sharma ji, five hundred rupees, received: right?", reason: "low_confidence" },
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
  await screen.findByTestId("readback-prompt");
  await act(async () => fireEvent.click(screen.getAllByRole("button", { name: /no/i })[0]));
  // Cash / UPI is asked only for money that moved.
  expect(screen.getByRole("radiogroup", { name: "How was it paid?" })).toBeInTheDocument();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Given on credit" })));
  expect(screen.queryByRole("radiogroup", { name: "How was it paid?" })).toBeNull();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save" })));
  expect(calls[0].body).toEqual({ correct: false, direction: "out", kind: "credit_given", paid_by: null });
});

test("owner says a line was goods bought on credit from a supplier", async () => {
  setLanguage("en");
  const queue = [
    { entry: { id: "e3", amount_paise: 1200000, direction: "out", kind: "money", paid_by: null, party_text: "Gupta Traders" }, prompt: "Gupta Traders, twelve thousand rupees, paid: right?", reason: "low_confidence" },
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
  await screen.findByTestId("readback-prompt");
  await act(async () => fireEvent.click(screen.getAllByRole("button", { name: /no/i })[0]));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Bought on credit" })));
  expect(screen.queryByRole("radiogroup", { name: "How was it paid?" })).toBeNull();
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Save" })));
  expect(calls[0].body).toEqual({ correct: false, direction: "in", kind: "credit_taken", paid_by: null });
});
