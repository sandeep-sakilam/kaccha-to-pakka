"""Turn one spoken ledger entry into fields, by rules.

"Sharma ji se chaar hazaar mile 12 October" -> party "Sharma ji", ₹4,000, in, 12 Oct.
The owner always hears the result in words and says yes or no; nothing is saved on a guess.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta

from app.core.words import _HI

ROMAN_0_99 = {
    "ek": 1,
    "do": 2,
    "teen": 3,
    "tin": 3,
    "char": 4,
    "chaar": 4,
    "paanch": 5,
    "panch": 5,
    "chhe": 6,
    "chhah": 6,
    "che": 6,
    "saat": 7,
    "sat": 7,
    "aath": 8,
    "ath": 8,
    "nau": 9,
    "das": 10,
    "gyarah": 11,
    "barah": 12,
    "terah": 13,
    "chaudah": 14,
    "pandrah": 15,
    "solah": 16,
    "satrah": 17,
    "atharah": 18,
    "unnis": 19,
    "bees": 20,
    "bis": 20,
    "pachchis": 25,
    "pachees": 25,
    "tees": 30,
    "tis": 30,
    "paintis": 35,
    "chalis": 40,
    "chaalis": 40,
    "paintalis": 45,
    "pachas": 50,
    "pachaas": 50,
    "pachpan": 55,
    "saath": 60,
    "sath": 60,
    "painsath": 65,
    "sattar": 70,
    "pachhattar": 75,
    "assi": 80,
    "pachasi": 85,
    "nabbe": 90,
    "pachanve": 95,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
DEV_0_99 = {w: i for i, w in enumerate(_HI)} | {"पांच": 5, "छः": 6}
MULTIPLIERS = {
    "sau": 100,
    "so": 100,
    "सौ": 100,
    "hundred": 100,
    "hazaar": 1000,
    "hazar": 1000,
    "hajar": 1000,
    "हज़ार": 1000,
    "हजार": 1000,
    "thousand": 1000,
    "lakh": 100_000,
    "lac": 100_000,
    "लाख": 100_000,
    "crore": 10_000_000,
    "karod": 10_000_000,
    "करोड़": 10_000_000,
}
HALF = {"dedh": 1.5, "डेढ़": 1.5, "dhai": 2.5, "ढाई": 2.5, "sawa": 1.25, "सवा": 1.25}
IN_WORDS = [
    "mile",
    "mila",
    "mili",
    "मिले",
    "मिला",
    "जमा",
    "jama",
    "aaye",
    "aaya",
    "आए",
    "received",
    "got",
    "liye",
    "लिए",
    "wapas",
]
OUT_WORDS = [
    "diye",
    "diya",
    "दिए",
    "दिया",
    "नाम",
    "naam",
    "paid",
    "gave",
    "bheje",
    "भेजे",
    "chukaye",
    "चुकाए",
    "udhaar diya",
]
MONTHS = {
    "jan": 1,
    "january": 1,
    "जनवरी": 1,
    "feb": 2,
    "february": 2,
    "फ़रवरी": 2,
    "फरवरी": 2,
    "mar": 3,
    "march": 3,
    "मार्च": 3,
    "apr": 4,
    "april": 4,
    "अप्रैल": 4,
    "may": 5,
    "मई": 5,
    "jun": 6,
    "june": 6,
    "जून": 6,
    "jul": 7,
    "july": 7,
    "जुलाई": 7,
    "aug": 8,
    "august": 8,
    "अगस्त": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "सितंबर": 9,
    "सितम्बर": 9,
    "oct": 10,
    "october": 10,
    "अक्टूबर": 10,
    "nov": 11,
    "november": 11,
    "नवंबर": 11,
    "नवम्बर": 11,
    "dec": 12,
    "december": 12,
    "दिसंबर": 12,
    "दिसम्बर": 12,
}
PARTY_MARKERS = r"\s+(se|ko|से|को|ne|ने|ka|ki|का|की|from|to)\s+"


@dataclass(frozen=True)
class ParsedEntry:
    amount_paise: int | None
    party_text: str | None
    direction: str | None
    entry_date: date | None

    @property
    def understood(self) -> bool:
        return self.amount_paise is not None and self.direction is not None


def _num(token: str) -> float | None:
    t = token.lower().strip(".,")
    if re.fullmatch(r"\d+(\.\d+)?", t.replace(",", "")):
        return float(t.replace(",", ""))
    if t in HALF:
        return HALF[t]
    return ROMAN_0_99.get(t, DEV_0_99.get(token))


def parse_amount(text: str) -> int | None:
    """Indian-style amount from digits and/or number words, in paise."""
    tokens = re.findall(r"[\w\.,ऀ-ॿ]+", text.lower())
    total = 0.0
    current = 0.0
    seen = False
    for tok in tokens:
        tok = tok.strip(",")
        mult = MULTIPLIERS.get(tok)
        if mult:
            current = (current or 1) * mult
            if mult >= 1000:
                total += current
                current = 0
            seen = True
            continue
        n = _num(tok)
        if n is not None:
            if re.fullmatch(r"(19|20)\d\d", tok) and seen:
                continue
            current += n
            seen = True
        elif (
            seen
            and (current or total)
            and tok not in {"aur", "और", "and", "rupaye", "rupees", "rs", "₹", "रुपये", "रुपए"}
        ):
            # stop at the first non-number word after a number run, unless a day+month follows
            if tok in MONTHS:
                current = 0
                break
            break
    value = total + current
    if value <= 0:
        return None
    return round(value * 100)


def parse_direction(text: str) -> str | None:
    t = f" {text.lower()} "
    out = any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", t) for w in OUT_WORDS)
    inn = any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", t) for w in IN_WORDS)
    if out and not inn:
        return "out"
    if inn and not out:
        return "in"
    return None


def parse_date(text: str, today: date) -> date | None:
    t = text.lower()
    if re.search(r"(?<!\w)(aaj|आज|today)(?!\w)", t):
        return today
    if re.search(r"(?<!\w)(kal|कल|yesterday)(?!\w)", t):
        return today - timedelta(days=1)
    for m in re.finditer(r"(\d{1,2})\s*(?:tarikh|तारीख)?\s*([a-z\u0900-\u097F]+)", t):
        month = MONTHS.get(m.group(2))
        if month and 1 <= int(m.group(1)) <= 31:
            year = today.year if month <= today.month else today.year - 1
            try:
                return date(year, month, int(m.group(1)))
            except ValueError:
                return None
    return None


def parse_party(text: str) -> str | None:
    parts = re.split(PARTY_MARKERS, text.strip(), maxsplit=1, flags=re.I)
    if len(parts) >= 3 and parts[0].strip():
        cand = parts[0].strip(" ,.")
        if parse_amount(cand) is None:
            return cand[:200]
    return None


def parse_entry(text: str, today: date | None = None) -> ParsedEntry:
    today = today or date.today()
    party = parse_party(text)
    rest = text
    if party:
        rest = re.split(PARTY_MARKERS, text, maxsplit=1, flags=re.I)[-1]
    # remove a "12 October" date before reading the amount so 12 is not added to it
    rest_no_date = re.sub(
        r"\d{1,2}\s*(tarikh|तारीख)?\s*(" + "|".join(MONTHS) + r")\b", " ", rest, flags=re.I
    )
    return ParsedEntry(
        parse_amount(rest_no_date), party, parse_direction(text), parse_date(text, today)
    )
