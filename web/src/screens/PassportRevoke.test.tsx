import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import * as voice from "@/lib/voice";
import PassportScreen from "./PassportScreen";

const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "content-type": "application/json" } });

test("owner withdraws the passport after a spoken confirmation", async () => {
  setLanguage("en");
  const spoken = vi.spyOn(voice, "speak");
  let status = "valid";
  const calls: string[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const u = String(url);
    if (init?.method === "POST") calls.push(u);
    if (u.endsWith("/passport/revoke")) {
      status = "revoked";
      return json({});
    }
    if (u.endsWith("/passport"))
      return json({ id: "p1", status, valid_until: "2027-01-25T00:00:00Z", qr_png_b64: "", verify_url: "x", vc: { credentialSubject: { band: "C", sandbox: true } } });
    if (u.includes("/explanation"))
      return json({ band: "C", band_label: "Fair", confidence_label: "", status: "final", status_label: "Active", headline: "h", positives: [], gaps: [], improve: [] });
    if (u.includes("/assessments/latest")) return json({ reasons: { improve: [] } });
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/passport/:businessId" element={<PassportScreen />} />
    </Routes>,
    "/passport/b1",
  );
  const withdraw = await vi.waitFor(() => screen.getByText("Withdraw my passport"), { timeout: 3000 });
  await act(async () => fireEvent.click(withdraw));
  expect(screen.getByRole("alert")).toHaveTextContent("Lenders who scan it");
  expect(spoken).toHaveBeenCalledWith([expect.stringContaining("Withdraw your passport?")], "en");
  await act(async () => fireEvent.click(screen.getByText("Yes, withdraw it")));
  expect(calls.some((c) => c.endsWith("/businesses/b1/passport/revoke"))).toBe(true);
  await vi.waitFor(() => expect(screen.getByTestId("revoked")).toBeInTheDocument(), { timeout: 3000 });
});
