import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { mockApi, posted } from "@/test-api";
import { renderAt } from "@/test-utils";
import Confirm from "./Confirm";
import Helpers from "./Helpers";
import ImportCsv from "./ImportCsv";
import LinkBank from "./LinkBank";
import Partners from "./Partners";
import ReconQuestions from "./ReconQuestions";
import Review from "./Review";
import SahayakHome from "./SahayakHome";
import SandboxAA from "./SandboxAA";
import Shares from "./Shares";
import Statement from "./Statement";
import LenderHome from "./lender/LenderHome";
import LenderView from "./lender/LenderView";
import VerifyPassport from "./lender/VerifyPassport";

const click = async (text: string | RegExp) => {
  const el = await vi.waitFor(() => screen.getAllByText(text)[0]);
  await act(async () => fireEvent.click(el));
};
const keypad = async (digits: string) => {
  for (const d of digits) await act(async () => fireEvent.click(screen.getAllByText(d, { selector: "button" })[0]));
};
const at = (path: string, route: string, el: JSX.Element) =>
  renderAt(
    <Routes>
      <Route path={route} element={el} />
      <Route path="*" element={<p>elsewhere</p>} />
    </Routes>,
    path,
  );

beforeEach(() => setLanguage("en"));

test("link bank goes to the Sandbox AA page, which approves and fetches", async () => {
  const calls = mockApi([
    [/POST .*\/aa\/consent/, () => ({ consent_id: "c1", redirect_url: "/sandbox/aa/approve/h1", sandbox: true })],
    [/sandbox\/aa\/h1\/decide/, () => ({ status: "ACTIVE" })],
    [/aa\/c1\/fetch/, () => ({ accounts: [{ bank: "Sandbox Bank", txns: 120 }] })],
  ]);
  renderAt(
    <Routes>
      <Route path="/link-bank/:businessId" element={<LinkBank />} />
      <Route path="/sandbox/aa/approve/:handle" element={<SandboxAA />} />
    </Routes>,
    "/link-bank/b1",
  );
  await click("Link bank");
  await click("Approve");
  expect(await vi.waitFor(() => screen.getByTestId("aa-status"))).toHaveTextContent("120 payments received from Sandbox Bank");
  expect(posted(calls, /aa\/consent/)[0].body).toEqual({ monthly_refresh: true });
});

test("sandbox AA reject", async () => {
  mockApi([[/decide/, () => ({ status: "REJECTED" })]]);
  at("/sandbox/aa/approve/h1", "/sandbox/aa/approve/:handle", <SandboxAA />);
  await click("Reject");
  expect(await vi.waitFor(() => screen.getByTestId("aa-status"))).toHaveTextContent("Nothing was shared");
});

test("partners: system-picked list, phone keypad, invite", async () => {
  const list = [{ counterparty_id: "cp1", masked_id: "gup•••@oksbi", registered_name: "GUPTA TRADERS", relationship: "supplier", value_paise: 4000000, months_active: 6, invite_status: null as string | null }];
  const calls = mockApi([
    [/POST .*\/invites$/, () => {
      list[0].invite_status = "sent";
      return {};
    }],
    [/counterparties\/top/, () => list],
  ]);
  at("/partners/b1", "/partners/:businessId", <Partners />);
  await vi.waitFor(() => screen.getByText("GUPTA TRADERS"));
  await click("Send invite");
  await keypad("9811100001");
  await click("Send invite");
  expect(posted(calls, /invites/)[0].body).toMatchObject({ counterparty_id: "cp1", phone: "9811100001" });
  expect(await vi.waitFor(() => screen.getByTestId("invite-status"))).toHaveTextContent("Invite sent");
});

test("confirm page: Sandbox ₹1 proof then bucketed claim", async () => {
  let status = "opened";
  const calls = mockApi([
    [/GET .*\/invites\/tok$/, () => ({ business_name: "Sharma Kirana", city: "Indore", relationship: "supplier", masked_id: "gup•••@oksbi", status, language: "en", sandbox: true })],
    [/penny-drop\/check/, () => {
      status = "proven";
      return { status: "proven", reason: null };
    }],
    [/penny-drop$/, () => ({ ref: "r1", upi_link: "upi://pay", sandbox: true, pay_to_vpa: "verify@sandbox" })],
    [/sandbox\/payments\/r1\/pay/, () => ({ status: "PAID" })],
    [/invites\/tok\/claim/, () => ({ status: "confirmed" })],
    [/invites\/tok\/disputes/, () => []],
  ]);
  at("/confirm/tok", "/confirm/:token", <Confirm />);
  await vi.waitFor(() => screen.getByText(/Sharma Kirana \(Indore\) says you are their Supplier/));
  await click("Pay ₹1 with UPI");
  fireEvent.change(screen.getByLabelText("Your UPI ID"), { target: { value: "gupta@oksbi" } });
  fireEvent.change(screen.getByLabelText("Name on your bank account"), { target: { value: "GUPTA TRADERS" } });
  await click("Pay ₹1 with UPI");
  await vi.waitFor(() => screen.getByText(/Your account is confirmed/));
  await click("3 to 5 years");
  await click("₹10k-25k");
  await click("On time");
  await click("Confirm");
  expect(posted(calls, /claim/)[0].body).toMatchObject({ relationship: "supplier", years_trading: "3-5", monthly_value: "10k-25k", payment_behaviour: "on_time" });
  expect(await vi.waitFor(() => screen.getByTestId("claim-status"))).toHaveTextContent("signed and saved");
});

test("confirm page shows the rejection message", async () => {
  mockApi([[/GET .*\/invites\/tok$/, () => ({ business_name: "Raju", city: null, relationship: "supplier", masked_id: "x", status: "rejected", language: "en", sandbox: true })]]);
  at("/confirm/tok", "/confirm/:token", <Confirm />);
  expect(await vi.waitFor(() => screen.getByTestId("confirm-status"))).toHaveTextContent("different account than the one in their payments");
});

test("confirm page with a bad link", async () => {
  mockApi([[/invites\/bad/, () => new Response("{}", { status: 404, headers: { "content-type": "application/json" } })]]);
  at("/confirm/bad", "/confirm/:token", <Confirm />);
  await vi.waitFor(() => screen.getByText("This link is not valid any more."));
});

test("shares: create, list, revoke, access log", async () => {
  const shares = [{ id: "s1", lender_org: "SBI Rajwada branch", scope: "summary", expires_at: "2026-12-27T00:00:00Z", state: "active", link: "http://x/l/abc", views: 1 }];
  const calls = mockApi([
    [/POST .*\/shares\/s1\/revoke/, () => {
      shares[0].state = "revoked";
      return {};
    }],
    [/POST .*\/shares$/, () => ({})],
    [/GET .*\/shares$/, () => shares],
    [/access-logs/, () => [{ lender_org: "SBI Rajwada branch", viewer: "SBI Rajwada branch", viewed_at: "2026-11-27T10:00:00Z" }]],
  ]);
  at("/shares/b1", "/shares/:businessId", <Shares />);
  fireEvent.change(screen.getByLabelText("Lender name and branch"), { target: { value: "Coop Bank" } });
  await click("Summary and evidence");
  await click("7 days");
  await click("Create share link");
  expect(posted(calls, /\/shares$/)[0].body).toEqual({ lender_org: "Coop Bank", scope: "evidence", days: 7 });
  expect(await vi.waitFor(() => screen.getByTestId("access-log"))).toHaveTextContent("SBI Rajwada branch viewed");
  await click("Stop sharing");
  expect(posted(calls, /s1\/revoke/)).toHaveLength(1);
});

test("lender view shows scope, evidence and watermark", async () => {
  mockApi([[/\/l\/tok/, () => ({
    lender_org: "SBI Rajwada branch", scope: "evidence",
    passport: { id: "p1", status: "valid", valid_until: "2027-01-01T00:00:00Z", vc: { credentialSubject: { band: "B", confidence: "High", sandbox: true } } },
    explanation: { headline: "Your passport is strong because …", band_label: "Strong", positives: ["12 months of payments"], gaps: [] },
    business: { name: "Sharma Kirana", category: "kirana", city: "Indore", since: 2012 },
    evidence: { monthly_totals_paise: { "2026-10": { in: 5000000, out: 2000000 } }, confirmations: [{ label: "verified supplier, trading 5+ years", status: "confirmed" }], presence: { done: 3, failed: 0, missed: 0 }, records: { match_rate: 0.82 }, evidence_items: [{ type: "aa_fetch", status: "parsed", file_hash: null }], flags: [{ code: "x", detail: "flag detail" }] },
  })]]);
  at("/l/tok", "/l/:token", <LenderView />);
  expect(await vi.waitFor(() => screen.getByTestId("watermark"))).toHaveTextContent("Shared with SBI Rajwada branch");
  expect(screen.getByTestId("evidence")).toHaveTextContent("verified supplier, trading 5+ years");
  expect(screen.getByText("82%")).toBeInTheDocument();
  expect(screen.getByText("flag detail")).toBeInTheDocument();
});

test("lender view shows a credit book as plain facts", async () => {
  mockApi([[/\/l\/tok/, () => ({
    lender_org: "SBI Rajwada branch", scope: "evidence",
    passport: { id: "p1", status: "valid", valid_until: "2027-01-01T00:00:00Z", vc: { credentialSubject: { band: "B", confidence: "High", sandbox: true } } },
    explanation: { headline: "Your passport is strong because …", band_label: "Strong", positives: [], gaps: [] },
    business: { name: "Sharma Kirana", category: "kirana", city: "Indore", since: 2012 },
    evidence: {
      monthly_totals_paise: {}, confirmations: [], presence: { done: 0, failed: 0, missed: 0 }, evidence_items: [], flags: [],
      avg_monthly_inflow_paise: 10000000,
      registration: { status: "verified", source: "udyam", registered_on: "2021-03-02" },
      cash_deposit_paise: 2400000,
      cash_deposit_months: 4,
      records: {
        match_rate: 0.9, cash_entries: 4, credit_entries: 40, credit_customers: 12, repeat_credit_customers: 9,
        credit_given_paise: 4000000, credit_repaid_bank_paise: 2800000, credit_repaid_cash_paise: 800000,
        credit_outstanding_paise: 400000, median_days_to_repay: 33, owner_confirmed_share: 0.25,
        daily_sales_months_checked: 3, daily_sales_months_agree: 2,
      },
    },
  })]]);
  at("/l/tok", "/l/:token", <LenderView />);
  const book = await vi.waitFor(() => screen.getByTestId("credit-book"));
  expect(book).toHaveTextContent("₹40,000 given on credit to 12 customers");
  expect(book).toHaveTextContent("70% came back through the bank");
  expect(book).toHaveTextContent("20% came back in cash, as the owner wrote it");
  expect(book).toHaveTextContent("Customers usually paid after 33 days");
  expect(book).toHaveTextContent("9 regular credit customers");
  expect(book).toHaveTextContent("₹4,000 still unpaid (4% of a month's money in)");
  expect(screen.getByText(/4 ledger entries are written as cash/)).toBeInTheDocument();
  expect(screen.getByText(/25% of the matched value links names to payers because the owner said so/)).toBeInTheDocument();
  expect(screen.getByTestId("registration")).toHaveTextContent("Udyam registration confirmed in the government register");
  expect(screen.getByTestId("cash-deposits")).toHaveTextContent("₹24,000 paid in as cash in 4 of the last 12 months");
  expect(screen.getByTestId("daily-sales-check")).toHaveTextContent("agreed with the bank in 2 of 3 months checked");
});

test("lender view of a revoked share", async () => {
  mockApi([[/\/l\/old/, () => new Response(JSON.stringify({ code: "share_revoked", message: "This share has revoked." }), { status: 410, headers: { "content-type": "application/json" } })]]);
  at("/l/old", "/l/:token", <LenderView />);
  await vi.waitFor(() => screen.getByText("This share has revoked."));
});

test("QR verification offline with the published key, then live status", async () => {
  mockApi([
    [/ktp-keys/, () => ({ keys: [{ public_key: "DANnJudx+WRxr39RW9QGwJhn8FCnhBhv8AYvooO7UQQ=" }] })],
    [/passports\/11111111-2222-3333-4444-555555555555\/status/, () => ({ status: "revoked" })],
  ]);
  at("/v/11111111-2222-3333-4444-555555555555#eNpNjs1Og0AUhV_F3DVjCkx_IOmG_khIMQEbE7ubAjNOKASRVrDpI7j0DcbElXHlsr7KPIqX6MKzmJxz8uXOOUIF7hEO4JoGyBRcMP9ELBSxUYSiyPCfwIASUa2-tPrUby9afWh1vtDqVavvvlJnrd7xRTBBMJc1KxmGLQavLzkaX4p79I8Nei5LtsNw2GOwBtaYDHBB_1H9W4wucVJt9jweaep9ZuDZfnDeVISnJktTi7KJbcEJGeyzxYgWO1tklEdOsH5Y3RSzed0uuokYyzaZh9eV42-Y8K_iwNyyNd2ERXcbiW65evJoYgdimD7H8TITYdB6zl3ul3wWTadw-gGl4GM8", "/v/:passportId", <VerifyPassport />);
  expect(await vi.waitFor(() => screen.getByTestId("signature"))).toHaveTextContent("Signature valid");
  expect(await vi.waitFor(() => screen.getByTestId("live-status"))).toHaveTextContent("Revoked");
});

test("QR for a different passport id fails", async () => {
  mockApi([[/ktp-keys/, () => ({ keys: [{ public_key: "DANnJudx+WRxr39RW9QGwJhn8FCnhBhv8AYvooO7UQQ=" }] })]]);
  at("/v/other#eNpNjs1Og0AUhV_F3DVjCkx_IOmG_khIMQEbE7ubAjNOKASRVrDpI7j0DcbElXHlsr7KPIqX6MKzmJxz8uXOOUIF7hEO4JoGyBRcMP9ELBSxUYSiyPCfwIASUa2-tPrUby9afWh1vtDqVavvvlJnrd7xRTBBMJc1KxmGLQavLzkaX4p79I8Nei5LtsNw2GOwBtaYDHBB_1H9W4wucVJt9jweaep9ZuDZfnDeVISnJktTi7KJbcEJGeyzxYgWO1tklEdOsH5Y3RSzed0uuokYyzaZh9eV42-Y8K_iwNyyNd2ERXcbiW65evJoYgdimD7H8TITYdB6zl3ul3wWTadw-gGl4GM8", "/v/:passportId", <VerifyPassport />);
  expect(await vi.waitFor(() => screen.getByTestId("signature"))).toHaveTextContent("NOT valid");
});

test("lender home opens a pasted link", async () => {
  mockApi([]);
  at("/lender", "/lender", <LenderHome />);
  fireEvent.change(screen.getByLabelText("Paste passport or share link"), { target: { value: "https://pakka.example/l/abc" } });
  await click("Open");
  await vi.waitFor(() => screen.getByText("elsewhere"));
});

test("owner adds a helper with chosen permissions", async () => {
  const links = [] as { id: string; sahayak_name: string; phone_last4: string; permissions: string[]; revoked_at: string | null }[];
  const calls = mockApi([
    [/POST .*\/sahayaks$/, () => {
      links.push({ id: "l1", sahayak_name: "Kavita", phone_last4: "0001", permissions: ["capture"], revoked_at: null });
      return {};
    }],
    [/sahayaks\/l1\/revoke/, () => ({})],
    [/GET .*\/sahayaks$/, () => links],
    [/directory/, () => [{ name: "Sunita SHG", phone_last4: "0009" }]],
  ]);
  at("/helpers/b1", "/helpers/:businessId", <Helpers />);
  await vi.waitFor(() => screen.getByText(/Sunita SHG/));
  await keypad("9822200001");
  await click("Read ledger aloud");
  await click("Add helper");
  expect(posted(calls, /\/sahayaks$/)[0].body).toEqual({ phone: "9822200001", permissions: ["capture", "readback"] });
  await click("Remove");
  expect(posted(calls, /l1\/revoke/)).toHaveLength(1);
});

test("sahayak registers", async () => {
  const calls = mockApi([[/sahayak\/register/, () => ({ roles: ["sahayak"] })]]);
  at("/sahayak", "/sahayak", <SahayakHome />);
  fireEvent.change(screen.getByLabelText("Your name"), { target: { value: "Kavita" } });
  await click("Register as Sahayak");
  expect(posted(calls, /register/)[0].body).toEqual({ name: "Kavita", gender: null });
});

test("reviewer opens a case and decides", async () => {
  const calls = mockApi([
    [/review\/disputes\/d1\/resolve/, () => ({})],
    [/review\/disputes\/d1$/, () => ({ id: "d1", business: { name: "Raju General Store" }, target: { status: "on_hold" }, reason: "tamper" })],
    [/review\/disputes$/, () => [{ id: "d1", target_type: "evidence", reason: "tamper", raised_by: "system", created_at: "2026-11-27T00:00:00Z" }]],
    [/review\/sahayaks/, () => [{ sahayak_user_id: "s1234567890", actions_30d: 200, businesses: 6, failure_rate: 0.5, reasons: ["shared_device"] }]],
    [/review\/monitor/, () => ({ opened: 1 })],
  ]);
  at("/review", "/review", <Review />);
  await click("Open case");
  await vi.waitFor(() => screen.getByText("Raju General Store"));
  fireEvent.change(screen.getByLabelText("Note for the log"), { target: { value: "checked" } });
  await click("Upheld: problem is real");
  expect(posted(calls, /resolve/)[0].body).toEqual({ decision: "upheld", note: "checked" });
  await click("Run checks now");
  expect(posted(calls, /monitor/)).toHaveLength(1);
  expect(screen.getByText("shared_device")).toBeInTheDocument();
});

test("CSV and statement uploads report the result", async () => {
  mockApi([
    [/imports\/csv/, () => ({ rows: 4, source: "khatabook" })],
    [/statements/, () => new Response(JSON.stringify({ message: "This looks like a scanned PDF." }), { status: 400, headers: { "content-type": "application/json" } })],
  ]);
  const file = new File(["Date,You Gave,You Got"], "kb.csv", { type: "text/csv" });
  const { unmount } = at("/import/b1", "/import/:businessId", <ImportCsv />);
  await act(async () => fireEvent.change(document.querySelector("input[type=file]")!, { target: { files: [file] } }));
  expect(await vi.waitFor(() => screen.getByTestId("upload-status"))).toHaveTextContent("4 entries added from khatabook");
  unmount();
  at("/statement/b1", "/statement/:businessId", <Statement />);
  await act(async () => fireEvent.change(document.querySelector("input[type=file]")!, { target: { files: [new File(["%PDF"], "s.pdf")] } }));
  expect(await vi.waitFor(() => screen.getByRole("alert"))).toHaveTextContent("scanned PDF");
});

test("owner answers a name question", async () => {
  const qs = [{ party_text: "Pappu", counterparty_name: "PRADEEP KUMAR", prompt: "Is Pappu the same as PRADEEP KUMAR?", bank_txn_id: "t9" }];
  const calls = mockApi([
    [/recon\/answer/, () => {
      qs.pop();
      return { match_rate: 0.9 };
    }],
    [/recon\/questions/, () => qs],
  ]);
  at("/recon/b1", "/recon/:businessId", <ReconQuestions />);
  expect(await vi.waitFor(() => screen.getByTestId("recon-prompt"))).toHaveTextContent("Pappu");
  await click("Yes");
  // The payment's id goes with the answer, so the yes is remembered by UPI ID too.
  expect(posted(calls, /recon\/answer/)[0].body).toEqual({ party_text: "Pappu", counterparty_name: "PRADEEP KUMAR", same: true, bank_txn_id: "t9" });
  await vi.waitFor(() => screen.getByText(/90% of your ledger/));
});
