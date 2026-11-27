import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { CounterpartyDispute } from "@/components/CounterpartyDispute";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import Disputes from "./Disputes";

const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "content-type": "application/json" } });

test("owner contests a ledger entry and follows its status", async () => {
  setLanguage("en");
  const rows: unknown[] = [];
  const posted: unknown[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.endsWith("/disputes") && init?.method === "POST") {
      posted.push(JSON.parse(String(init.body)));
      rows.push({ id: "d1", target_type: "ledger_entry", reason: "Amount is wrong", status: "open", resolution: null, created_at: "2026-11-27T10:00:00Z" });
      return json({});
    }
    if (u.endsWith("/disputes")) return json(rows);
    if (u.endsWith("/ledger")) return json([{ id: "e1", entry_date: "2026-10-12", party_text: "Sharma ji", amount_paise: 400000 }]);
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/disputes/:businessId" element={<Disputes />} />
    </Routes>,
    "/disputes/b1",
  );
  await act(async () => fireEvent.click(await vi.waitFor(() => screen.getByText("A ledger entry"))));
  const select = await vi.waitFor(() => screen.getByRole("combobox"));
  await act(async () => fireEvent.change(select, { target: { value: "e1" } }));
  fireEvent.change(screen.getByLabelText("Tell us what is wrong"), { target: { value: "Amount is wrong" } });
  await act(async () => fireEvent.click(screen.getByText("Send")));
  expect(posted[0]).toEqual({ target_type: "ledger_entry", target_id: "e1", reason: "Amount is wrong" });
  await vi.waitFor(() => expect(screen.getByTestId("dispute-list")).toHaveTextContent("Being checked"));
});

test("counterparty raises a dispute from the invite link and sees the decision", async () => {
  setLanguage("en");
  let rows: unknown[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    if (String(url).endsWith("/dispute") && init?.method === "POST") {
      rows = [{ id: "d2", target_type: "attestation", reason: "Never traded", status: "resolved", resolution: "upheld", created_at: "2026-11-27T10:00:00Z" }];
      return json({});
    }
    return json(rows);
  });
  renderAt(<CounterpartyDispute token="tok" />);
  await act(async () => fireEvent.click(screen.getByText("Something wrong? Tell us")));
  fireEvent.change(screen.getByLabelText("Tell us what is wrong"), { target: { value: "Never traded" } });
  await act(async () => fireEvent.click(screen.getByText("Send")));
  await vi.waitFor(() => expect(screen.getByTestId("dispute-list")).toHaveTextContent("You were right"));
});
