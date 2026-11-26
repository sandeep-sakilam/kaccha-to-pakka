import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import PassportScreen from "./PassportScreen";

const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "content-type": "application/json" } });

test("shows band, headline and coaching with an action", async () => {
  setLanguage("en");
  vi.mocked(fetch).mockImplementation(async (url) => {
    const u = String(url);
    if (u.endsWith("/passport"))
      return json({ id: "p1", status: "valid", valid_until: "2027-01-25T00:00:00Z", qr_png_b64: "", verify_url: "x", vc: { credentialSubject: { band: "B", sandbox: true } } });
    if (u.includes("/explanation"))
      return json({
        band: "B",
        band_label: "Strong",
        confidence_label: "high confidence",
        status: "final",
        status_label: "Active",
        headline: "Your passport is strong because 82% of your ledger matches your bank payments.",
        positives: ["82% of your ledger matches your bank payments"],
        gaps: [],
        improve: ["Ask 2 more suppliers or customers to confirm"],
      });
    if (u.includes("/assessments/latest")) return json({ reasons: { improve: [{ code: "ask_partners" }] } });
    return json({ any_sandbox: true, services: {} });
  });
  renderAt(
    <Routes>
      <Route path="/passport/:businessId" element={<PassportScreen />} />
    </Routes>,
    "/passport/b1",
  );
  expect(await screen.findByTestId("band")).toHaveTextContent("B");
  expect(screen.getByTestId("headline")).toHaveTextContent("82%");
  expect(screen.getByTestId("coaching")).toHaveTextContent("Ask 2 more");
  expect(screen.getByRole("button", { name: "Do it now" })).toBeInTheDocument();
});
