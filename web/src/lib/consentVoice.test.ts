import { parseConsentCommand } from "./consentVoice";

test("withdraw phrases in Hinglish, Hindi and English", () => {
  expect(parseConsentCommand("consent wapas lo").withdraw).toBe(true);
  expect(parseConsentCommand("कंसेंट वापस लो").withdraw).toBe(true);
  expect(parseConsentCommand("withdraw consent").withdraw).toBe(true);
  expect(parseConsentCommand("hello").withdraw).toBe(false);
});

test("what it is for, or a number", () => {
  expect(parseConsentCommand("bank ka consent wapas lo").purposes).toEqual(["aa_fetch", "monthly_refresh"]);
  expect(parseConsentCommand("withdraw consent for the lender share").purposes).toEqual(["share_lender"]);
  expect(parseConsentCommand("सहायक का कंसेंट वापस लो").purposes).toEqual(["sahayak_help"]);
  expect(parseConsentCommand("withdraw consent 2").index).toBe(2);
  expect(parseConsentCommand("teen").index).toBe(3);
});
