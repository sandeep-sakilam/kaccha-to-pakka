"""Voice interview: turn a spoken answer into a profile field, by rules (no AI judgement).

Speech to text gives a transcript; these rules pull out the category, the start year and the
place. The owner then hears the result and says yes or no, so nothing is saved on a guess.
"""

import re
from dataclasses import dataclass
from datetime import date

CATEGORIES: dict[str, list[str]] = {
    "kirana": ["kirana", "किराना", "grocery", "general store", "रसन", "राशन", "ration", "dukaan"],
    "namkeen": ["namkeen", "नमकीन", "sev", "सेव", "mithai", "मिठाई", "sweet", "farsan", "snack"],
    "tailor": ["tailor", "दर्जी", "darzi", "silai", "सिलाई", "boutique", "blouse", "कपड़े सिल"],
    "vegetables": ["sabzi", "सब्ज़ी", "सब्जी", "vegetable", "fruit", "फल"],
    "dairy": ["doodh", "दूध", "dairy", "milk", "paneer"],
    "food_stall": ["chai", "चाय", "nashta", "नाश्ता", "poha", "पोहा", "thela", "ठेला", "dhaba"],
    "salon": ["salon", "parlour", "पार्लर", "nai", "नाई", "barber"],
    "mobile_repair": ["mobile", "मोबाइल", "repair", "रिपेयर"],
    "hardware": ["hardware", "हार्डवेयर", "paint", "cement", "sanitary"],
    "manufacturing": ["factory", "फैक्ट्री", "manufactur", "बनाते", "workshop", "karkhana"],
}

HINDI_NUMBERS = {
    "एक": 1,
    "ek": 1,
    "दो": 2,
    "do": 2,
    "तीन": 3,
    "teen": 3,
    "चार": 4,
    "char": 4,
    "chaar": 4,
    "पाँच": 5,
    "पांच": 5,
    "paanch": 5,
    "panch": 5,
    "छह": 6,
    "chhah": 6,
    "che": 6,
    "सात": 7,
    "saat": 7,
    "आठ": 8,
    "aath": 8,
    "नौ": 9,
    "nau": 9,
    "दस": 10,
    "das": 10,
    "बारह": 12,
    "barah": 12,
    "पंद्रह": 15,
    "pandrah": 15,
    "बीस": 20,
    "bees": 20,
    "पच्चीस": 25,
    "pachchis": 25,
    "तीस": 30,
    "tees": 30,
}

INDORE_AREAS = [
    "rajwada",
    "राजवाड़ा",
    "sarafa",
    "सराफा",
    "palasia",
    "पलासिया",
    "vijay nagar",
    "विजय नगर",
    "khajrana",
    "खजराना",
    "malharganj",
    "मल्हारगंज",
    "sudama nagar",
    "सुदामा नगर",
    "chhoti gwaltoli",
    "bhawarkua",
    "भंवरकुआं",
    "sanyogitaganj",
]


@dataclass(frozen=True)
class Interpretation:
    field: str
    value: str | int | None
    confirm_en: str
    confirm_hi: str
    understood: bool


def interpret_category(text: str) -> Interpretation:
    t = text.lower()
    for cat, words in CATEGORIES.items():
        if any(w.lower() in t for w in words):
            return Interpretation(
                "category",
                cat,
                f"You sell: {cat.replace('_', ' ')}. Right?",
                f"आप बेचते हैं: {cat}. सही?",
                True,
            )
    return Interpretation(
        "category",
        "other",
        "Other kind of business. Right?",
        "दूसरा व्यापार। सही?",
        bool(text.strip()),
    )


def interpret_since(text: str, today: date | None = None) -> Interpretation:
    today = today or date.today()
    t = text.lower()
    year: int | None = None
    m = re.search(r"\b(19[5-9]\d|20[0-4]\d)\b", t)
    if m:
        year = int(m.group(1))
    else:
        m = re.search(r"(\d{1,2})\s*(saal|sal|साल|years?|varsh|वर्ष)", t)
        n: int | None = int(m.group(1)) if m else None
        if n is None:
            for word, val in HINDI_NUMBERS.items():
                if re.search(rf"(?<!\w){re.escape(word)}(?!\w)\s*(saal|sal|साल|years?|वर्ष)", t):
                    n = val
                    break
        if n is not None:
            year = today.year - n
    if year is None or year > today.year:
        return Interpretation(
            "started_year",
            None,
            "I did not catch the year. Please say it again.",
            "साल समझ नहीं आया। फिर से बोलिए।",
            False,
        )
    return Interpretation(
        "started_year", year, f"Running since {year}. Right?", f"{year} से चल रहा है। सही?", True
    )


def interpret_place(text: str) -> Interpretation:
    t = text.strip()
    area = next((a for a in INDORE_AREAS if a.lower() in t.lower()), None)
    value = area.title() if area else t[:200]
    return Interpretation(
        "address",
        value or None,
        f"Your shop is at {value}. Right?",
        f"आपकी दुकान {value} में है। सही?",
        bool(value),
    )


def interpret_name(text: str) -> Interpretation:
    t = re.sub(
        r"^(mera|meri|my|हमारी|मेरी|मेरा)\s+(dukaan|dukan|shop|दुकान)\s+(ka|ki|का|की)?\s*"
        r"(naam|name|नाम)?\s*(hai|है)?\s*",
        "",
        text.strip(),
        flags=re.I,
    )
    t = re.sub(r"\s*(hai|है)\.?$", "", t, flags=re.I).strip(" .")
    return Interpretation(
        "name", t[:200] or None, f"Shop name: {t}. Right?", f"दुकान का नाम: {t}। सही?", bool(t)
    )


INTERPRETERS = {
    "category": interpret_category,
    "since": interpret_since,
    "place": interpret_place,
    "name": interpret_name,
}
