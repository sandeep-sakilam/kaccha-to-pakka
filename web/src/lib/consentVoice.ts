/**
 * Voice command for withdrawing consent: "consent wapas lo", "withdraw consent", "कंसेंट वापस लो",
 * optionally with what it is for ("bank", "lender", "sahayak", "location") or a number from the list.
 */

const WITHDRAW = [/wapas\s*lo/i, /vapas\s*lo/i, /withdraw/i, /वापस\s*लो/, /वापस\s*लें/, /revoke/i, /हटाओ/, /hatao/i];

const HINTS: [RegExp, string[]][] = [
  [/bank|बैंक|account|खाता/i, ["aa_fetch", "monthly_refresh"]],
  [/lender|loan|share|ऋण|बैंक को|sbi|कर्ज़/i, ["share_lender"]],
  [/sahayak|helper|सहायक|madad/i, ["sahayak_help"]],
  [/location|gps|लोकेशन|jagah/i, ["presence_location"]],
  [/photo|original|फ़ोटो|फोटो/i, ["keep_originals"]],
  [/training|ai|सिखा/i, ["model_training"]],
  [/passport|पासपोर्ट/i, ["build_passport"]],
];

const NUMBER_WORDS: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, ek: 1, do: 2, teen: 3, char: 4, chaar: 4, paanch: 5, एक: 1, दो: 2, तीन: 3, चार: 4, पाँच: 5 };

export type ConsentCommand = { withdraw: boolean; purposes: string[] | null; index: number | null };

export function parseConsentCommand(text: string): ConsentCommand {
  const t = text.trim();
  const withdraw = WITHDRAW.some((r) => r.test(t));
  // "lender" hints must win over "bank" when someone says "share with bank"
  let purposes: string[] | null = null;
  for (const [re, ps] of HINTS) {
    if (re.test(t)) {
      purposes = ps;
      if (ps[0] === "share_lender") break;
    }
  }
  const digit = t.match(/\b(\d{1,2})\b/);
  const word = t
    .toLowerCase()
    .split(/\s+/)
    .map((w) => NUMBER_WORDS[w])
    .find((n) => n !== undefined);
  const index = digit ? Number(digit[1]) : (word ?? null);
  return { withdraw, purposes, index };
}
