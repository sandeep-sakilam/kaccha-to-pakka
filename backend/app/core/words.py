"""Amounts and dates in words, because digits are where errors hide when read aloud."""

from datetime import date

_HI = [
    "शून्य",
    "एक",
    "दो",
    "तीन",
    "चार",
    "पाँच",
    "छह",
    "सात",
    "आठ",
    "नौ",
    "दस",
    "ग्यारह",
    "बारह",
    "तेरह",
    "चौदह",
    "पंद्रह",
    "सोलह",
    "सत्रह",
    "अठारह",
    "उन्नीस",
    "बीस",
    "इक्कीस",
    "बाईस",
    "तेईस",
    "चौबीस",
    "पच्चीस",
    "छब्बीस",
    "सत्ताईस",
    "अट्ठाईस",
    "उनतीस",
    "तीस",
    "इकतीस",
    "बत्तीस",
    "तैंतीस",
    "चौंतीस",
    "पैंतीस",
    "छत्तीस",
    "सैंतीस",
    "अड़तीस",
    "उनतालीस",
    "चालीस",
    "इकतालीस",
    "बयालीस",
    "तैंतालीस",
    "चवालीस",
    "पैंतालीस",
    "छियालीस",
    "सैंतालीस",
    "अड़तालीस",
    "उनचास",
    "पचास",
    "इक्यावन",
    "बावन",
    "तिरपन",
    "चौवन",
    "पचपन",
    "छप्पन",
    "सत्तावन",
    "अट्ठावन",
    "उनसठ",
    "साठ",
    "इकसठ",
    "बासठ",
    "तिरसठ",
    "चौंसठ",
    "पैंसठ",
    "छियासठ",
    "सड़सठ",
    "अड़सठ",
    "उनहत्तर",
    "सत्तर",
    "इकहत्तर",
    "बहत्तर",
    "तिहत्तर",
    "चौहत्तर",
    "पचहत्तर",
    "छिहत्तर",
    "सतहत्तर",
    "अठहत्तर",
    "उन्यासी",
    "अस्सी",
    "इक्यासी",
    "बयासी",
    "तिरासी",
    "चौरासी",
    "पचासी",
    "छियासी",
    "सत्तासी",
    "अट्ठासी",
    "नवासी",
    "नब्बे",
    "इक्यानबे",
    "बानवे",
    "तिरानवे",
    "चौरानवे",
    "पचानवे",
    "छियानवे",
    "सत्तानवे",
    "अट्ठानवे",
    "निन्यानवे",
]
_EN1 = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_EN10 = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_UNITS_HI = [(10_000_000, "करोड़"), (100_000, "लाख"), (1000, "हज़ार"), (100, "सौ")]
_UNITS_EN = [(10_000_000, "crore"), (100_000, "lakh"), (1000, "thousand"), (100, "hundred")]
_MONTHS_HI = [
    "जनवरी",
    "फ़रवरी",
    "मार्च",
    "अप्रैल",
    "मई",
    "जून",
    "जुलाई",
    "अगस्त",
    "सितंबर",
    "अक्टूबर",
    "नवंबर",
    "दिसंबर",
]
_MONTHS_EN = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def hindi_number(n: int) -> str:
    if n < 100:
        return _HI[n]
    parts = []
    for size, word in _UNITS_HI:
        if n >= size:
            parts.append(f"{hindi_number(n // size)} {word}")
            n %= size
    if n:
        parts.append(_HI[n])
    return " ".join(parts)


def english_number(n: int) -> str:
    if n < 20:
        return _EN1[n]
    if n < 100:
        return _EN10[n // 10] + (f"-{_EN1[n % 10]}" if n % 10 else "")
    parts = []
    for size, word in _UNITS_EN:
        if n >= size:
            parts.append(f"{english_number(n // size)} {word}")
            n %= size
    if n:
        parts.append(english_number(n))
    return " ".join(parts)


def rupees_words(paise: int, lang: str) -> str:
    rupees, p = divmod(paise, 100)
    if lang == "hi":
        out = f"{hindi_number(rupees)} रुपये"
        return out + (f" {hindi_number(p)} पैसे" if p else "")
    out = f"{english_number(rupees)} rupees"
    return out + (f" {english_number(p)} paise" if p else "")


def date_words(d: date, lang: str) -> str:
    if lang == "hi":
        return f"{d.day} {_MONTHS_HI[d.month - 1]}"
    return f"{d.day} {_MONTHS_EN[d.month - 1]}"
