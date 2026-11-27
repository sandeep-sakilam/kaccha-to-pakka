import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import VoiceEntry from "./VoiceEntry";

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });

test("two misses switch to big-button entry", async () => {
  setLanguage("en");
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (String(url).includes("/parse")) return json({ understood: false, amount_paise: null, direction: null, party_text: null, entry_date: null, prompt: null, stt_confidence: 0 });
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/voice-entry/:businessId" element={<VoiceEntry />} />
    </Routes>,
    "/voice-entry/b1",
  );
  for (let i = 0; i < 2; i++) {
    fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: "hmm" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Next" })));
  }
  expect(await screen.findByTestId("buttons-mode")).toBeInTheDocument();
});

test("a heard entry is read back and added on yes", async () => {
  setLanguage("en");
  vi.mocked(fetch).mockImplementation(async (url) => {
    if (String(url).includes("/parse"))
      return json({ understood: true, amount_paise: 400000, direction: "in", party_text: "Sharma ji", entry_date: "2026-10-12", prompt: "Sharma ji, four thousand rupees, received on 12 October: right?", stt_confidence: 0.9 });
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/voice-entry/:businessId" element={<VoiceEntry />} />
    </Routes>,
    "/voice-entry/b1",
  );
  fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: "Sharma ji se chaar hazaar mile" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Next" })));
  expect(await screen.findByTestId("voice-prompt")).toHaveTextContent("four thousand rupees");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Yes" })));
  expect(screen.getByText("1 entries ready")).toBeInTheDocument();
});

test("credit spoken aloud is saved as credit given", async () => {
  setLanguage("en");
  const saved: unknown[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/parse"))
      return json({ understood: true, amount_paise: 120000, direction: "out", kind: "credit_given", paid_by: null, party_text: "Sharma ji", entry_date: null, prompt: "Sharma ji took one thousand two hundred rupees of goods on credit: right?", stt_confidence: 0.9 });
    if (u.endsWith("/voice-entries")) {
      saved.push(JSON.parse(String(init?.body)));
      return json({ evidence_id: "e1", created: true, entries: 1 });
    }
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/voice-entry/:businessId" element={<VoiceEntry />} />
    </Routes>,
    "/voice-entry/b1",
  );
  fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: "Sharma ji ke naam 1200 likhe" } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Next" })));
  expect(await screen.findByTestId("voice-prompt")).toHaveTextContent("on credit");
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Yes" })));
  await act(async () => fireEvent.click(screen.getByRole("button", { name: /Save/ })));
  expect(saved[0]).toMatchObject({ entries: [{ amount_paise: 120000, direction: "out", kind: "credit_given", paid_by: null, party_text: "Sharma ji" }] });
});
