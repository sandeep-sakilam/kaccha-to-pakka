import { act, fireEvent, screen } from "@testing-library/react";
import { setLanguage } from "@/i18n";
import { renderAt } from "@/test-utils";
import Consents from "./Consents";

const json = (b: unknown) => new Response(JSON.stringify(b), { headers: { "content-type": "application/json" } });

function setup() {
  const rows: { id: string; purpose: string; why: string; granted_at: string; expires_at: string | null; revoked_at: string | null; active: boolean }[] = [
    { id: "c1", purpose: "build_passport", why: "To build your Trust Passport.", granted_at: "2026-11-01T00:00:00Z", expires_at: null, revoked_at: null, active: true },
    { id: "c2", purpose: "aa_fetch", why: "To read your bank data.", granted_at: "2026-11-01T00:00:00Z", expires_at: "2027-11-01T00:00:00Z", revoked_at: null, active: true },
    { id: "c3", purpose: "share_lender", why: "To show your passport to one lender.", granted_at: "2026-11-01T00:00:00Z", expires_at: null, revoked_at: null, active: true },
  ];
  const revoked: string[] = [];
  vi.mocked(fetch).mockImplementation(async (url, init) => {
    const m = String(url).match(/\/consents\/(c\d)\/revoke/);
    if (m && init?.method === "POST") {
      revoked.push(m[1]);
      const r = rows.find((x) => x.id === m[1])!;
      r.active = false;
      r.revoked_at = "2026-11-27T00:00:00Z";
      return json(r);
    }
    return json(String(url).includes("/consents") ? rows : { any_sandbox: true, services: {} });
  });
  return revoked;
}

test("every consent is listed and one tap withdraws it", async () => {
  setLanguage("en");
  const revoked = setup();
  renderAt(<Consents />);
  await vi.waitFor(() => expect(screen.getAllByText("Withdraw")).toHaveLength(3));
  await act(async () => fireEvent.click(screen.getAllByText("Withdraw")[1]));
  expect(revoked).toEqual(["c2"]);
  await vi.waitFor(() => expect(screen.getByTestId("consent-message")).toHaveTextContent("Withdrawn: To read your bank data."));
});

test("voice command withdraws the named consent; a bare command asks which one", async () => {
  setLanguage("en");
  const revoked = setup();
  renderAt(<Consents />);
  await vi.waitFor(() => expect(screen.getAllByText("Withdraw")).toHaveLength(3));
  const say = async (text: string) => {
    fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: text } });
    await act(async () => fireEvent.submit(screen.getByLabelText("Or type here").closest("form")!));
  };
  await say("consent wapas lo");
  expect(screen.getByTestId("consent-message")).toHaveTextContent("Which one?");
  expect(revoked).toEqual([]);
  await say("withdraw consent for the lender share");
  expect(revoked).toEqual(["c3"]);
});
