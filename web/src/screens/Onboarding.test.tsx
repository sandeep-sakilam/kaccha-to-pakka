import { act, fireEvent, screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { setLanguage } from "@/i18n";
import { mockApi, posted } from "@/test-api";
import { renderAt } from "@/test-utils";
import Consent from "./Consent";
import Home from "./Home";
import Interview from "./Interview";
import Login from "./Login";
import Never from "./Never";

const keypad = async (digits: string) => {
  for (const d of digits) await act(async () => fireEvent.click(screen.getAllByText(d, { selector: "button" })[0]));
};
const click = async (text: string) => {
  const el = await vi.waitFor(() => screen.getByText(text));
  await act(async () => fireEvent.click(el));
};

beforeEach(() => setLanguage("en"));

test("login: phone, sandbox OTP, new PIN", async () => {
  const calls = mockApi([
    [/POST .*\/auth\/otp\/request/, () => ({ sandbox_code: "123456" })],
    [/POST .*\/auth\/otp\/verify/, () => ({ token: "t", stage: "otp", has_pin: false, new_device: true })],
    [/POST .*\/auth\/pin\/set/, () => ({ stage: "full" })],
  ]);
  renderAt(
    <Routes>
      <Route path="/start" element={<Login />} />
      <Route path="/consent" element={<p>consent page</p>} />
    </Routes>,
    "/start",
  );
  await keypad("9812345678");
  await click("Send OTP");
  expect(await vi.waitFor(() => screen.getByTestId("sandbox-otp"))).toHaveTextContent("123456");
  await keypad("123456");
  await click("Check OTP");
  await vi.waitFor(() => screen.getByText(/New phone noticed/));
  await keypad("4826");
  await click("Next");
  expect(posted(calls, /pin\/set/)[0].body).toEqual({ pin: "4826" });
  expect(posted(calls, /otp\/request/)[0].body).toMatchObject({ phone: "9812345678" });
});

test("login shows the API error", async () => {
  mockApi([[/POST .*\/auth\/otp\/request/, () => new Response(JSON.stringify({ code: "bad_phone", message: "Enter a 10-digit Indian mobile number" }), { status: 401, headers: { "content-type": "application/json" } })]]);
  renderAt(<Login />);
  await keypad("1234567890");
  await click("Send OTP");
  expect(await vi.waitFor(() => screen.getByRole("alert"))).toHaveTextContent("10-digit");
});

test("consent screen reads the notice and records the yes", async () => {
  const calls = mockApi([[/consents\/notice/, () => ({ lines: ["What we collect: …", "We never sell your data."] })]]);
  renderAt(
    <Routes>
      <Route path="/consent" element={<Consent />} />
      <Route path="/interview" element={<p>interview</p>} />
    </Routes>,
    "/consent",
  );
  await vi.waitFor(() => screen.getByText("We never sell your data."));
  await click("No");
  expect(screen.getByText(/Without your yes/)).toBeInTheDocument();
  await click("Yes, I agree");
  expect(posted(calls, /\/consents$/)[0].body).toEqual({ purpose: "build_passport" });
});

test("interview builds the profile from typed answers", async () => {
  const answers: Record<string, unknown> = {
    full_name: { value: "Ramesh Kumar Sharma", confirm: "Your full name: Ramesh Kumar Sharma. Right?" },
    name: { value: "Sharma Kirana", confirm: "Shop name: Sharma Kirana. Right?" },
    since: { value: 2012, confirm: "Running since 2012. Right?" },
    place: { value: "Rajwada", confirm: "Your shop is at Rajwada. Right?" },
  };
  const calls = mockApi([
    [/onboarding\/interpret/, (c) => ({ ...(answers[(c.body as { question: string }).question] as object), field: "x", transcript: "t", understood: true })],
    [/POST .*\/businesses$/, () => ({ id: "b1" })],
  ]);
  renderAt(
    <Routes>
      <Route path="/interview" element={<Interview />} />
      <Route path="/capture/:b/:k" element={<p>capture page</p>} />
    </Routes>,
    "/interview",
  );
  const answer = async (text: string) => {
    fireEvent.change(screen.getByLabelText("Or type here"), { target: { value: text } });
    await click("Next");
    await click("Yes");
  };
  await answer("Ramesh Kumar Sharma");
  await answer("Sharma Kirana");
  await click("Kirana / grocery");
  await answer("2012");
  await answer("Rajwada");
  fireEvent.change(screen.getByLabelText("PAN (optional, verifies your name)"), { target: { value: "abcde1234f" } });
  await click("Skip");
  await vi.waitFor(() => screen.getByText("capture page"));
  expect(posted(calls, /auth\/identity/)[0].body).toEqual({ full_name: "Ramesh Kumar Sharma", pan: "ABCDE1234F" });
  expect(posted(calls, /\/businesses$/)[0].body).toMatchObject({ name: "Sharma Kirana", category: "kirana", started_year: 2012, address: "Rajwada" });
});

test("home lists the business, open tasks and starts presence checks", async () => {
  const calls = mockApi([
    [/GET .*\/businesses$/, () => [{ id: "b1", name: "Sharma Kirana", category: "kirana", address: "Rajwada", started_on: "2012-01-01" }]],
    [/readback/, () => [{}, {}]],
    [/needs-voice/, () => [{ evidence_id: "e1" }]],
    [/recon\/questions/, () => [{}]],
    [/GET .*\/presence$/, () => []],
    [/presence\/start/, () => [{ status: "scheduled" }]],
  ]);
  renderAt(<Home />);
  expect(await vi.waitFor(() => screen.getByTestId("business-name"))).toHaveTextContent("Sharma Kirana");
  await vi.waitFor(() => screen.getByText("2 entries to check"));
  expect(screen.getByText(/1 page\(s\) could not be read/)).toBeInTheDocument();
  expect(screen.getByText("1 name question(s) to answer")).toBeInTheDocument();
  await click("Start shop presence checks");
  expect(posted(calls, /presence\/start/)).toHaveLength(1);
});

test("home without a business offers setup", async () => {
  mockApi([[/GET .*\/businesses$/, () => []]]);
  renderAt(<Home />);
  await vi.waitFor(() => screen.getByText("Let us set up your business."));
});

test("never-do screen lists the promises", () => {
  renderAt(<Never />);
  expect(screen.getByText("We never sell your data.")).toBeInTheDocument();
});
