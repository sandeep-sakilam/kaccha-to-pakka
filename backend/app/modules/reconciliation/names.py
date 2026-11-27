"""Name matching across scripts: "शर्मा जी" in a ledger vs "RAKESH SHARMA" from the bank.

Devanagari is transliterated to Latin with a small deterministic table, honorifics and business
suffixes are dropped, and token-set similarity (rapidfuzz) is computed. No AI.
"""

import re
import unicodedata

from rapidfuzz import fuzz

CONSONANTS = {
    "क": "k",
    "ख": "kh",
    "ग": "g",
    "घ": "gh",
    "ङ": "n",
    "च": "ch",
    "छ": "chh",
    "ज": "j",
    "झ": "jh",
    "ञ": "n",
    "ट": "t",
    "ठ": "th",
    "ड": "d",
    "ढ": "dh",
    "ण": "n",
    "त": "t",
    "थ": "th",
    "द": "d",
    "ध": "dh",
    "न": "n",
    "प": "p",
    "फ": "ph",
    "ब": "b",
    "भ": "bh",
    "म": "m",
    "य": "y",
    "र": "r",
    "ल": "l",
    "व": "v",
    "श": "sh",
    "ष": "sh",
    "स": "s",
    "ह": "h",
    "क़": "q",
    "ख़": "kh",
    "ग़": "g",
    "ज़": "z",
    "ड़": "r",
    "ढ़": "rh",
    "फ़": "f",
}
VOWELS = {
    "अ": "a",
    "आ": "aa",
    "इ": "i",
    "ई": "ee",
    "उ": "u",
    "ऊ": "oo",
    "ऋ": "ri",
    "ए": "e",
    "ऐ": "ai",
    "ओ": "o",
    "औ": "au",
}
MATRAS = {
    "ॉ": "o",
    "ॅ": "e",
    "ा": "aa",
    "ि": "i",
    "ी": "ee",
    "ु": "u",
    "ू": "oo",
    "ृ": "ri",
    "े": "e",
    "ै": "ai",
    "ो": "o",
    "ौ": "au",
    "ं": "n",
    "ँ": "n",
    "ः": "h",
}
VIRAMA = "्"
NUKTA = "़"

HONORIFICS = {
    "sa",  # Marwari "saa"/"sahab": "Jain sa"
    "saa",
    "saab",
    "sab",
    "sahib",
    "ji",
    "jee",
    "bhai",
    "bhaiya",
    "seth",
    "sethji",
    "sahab",
    "saheb",
    "babu",
    "shri",
    "sri",
    "smt",
    "mr",
    "mrs",
    "ms",
    "dr",
    "bhau",
    "didi",
    "behen",
    "ben",
    "kaka",
    "chacha",
    "mama",
    "uncle",
    "aunty",
    "madam",
    "sir",
    "m/s",
    "ms.",
}
BUSINESS_WORDS = {
    "cloth",
    "house",
    "bhandar",
    "kendra",
    "emporium",
    "mill",
    "mills",
    "industries",
    "udyog",
    "traders",
    "trader",
    "trading",
    "store",
    "stores",
    "enterprises",
    "enterprise",
    "and",
    "sons",
    "co",
    "company",
    "agency",
    "agencies",
    "kirana",
    "general",
    "pvt",
    "ltd",
    "private",
    "limited",
    "wholesale",
    "mart",
    "shop",
    "dukan",
    "&",
}


def transliterate(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    out: list[str] = []
    chars = list(text)
    i = 0
    while i < len(chars):
        ch = chars[i]
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if nxt == NUKTA and ch + NUKTA in CONSONANTS:
            ch, i = ch + NUKTA, i + 1
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if ch in CONSONANTS:
            out.append(CONSONANTS[ch])
            if nxt == VIRAMA:
                i += 2
                continue
            if nxt in MATRAS:
                out.append(MATRAS[nxt])
                i += 2
                continue
            following = chars[i + 1] if i + 1 < len(chars) else " "
            # schwa deletion: no inherent 'a' at the end of a word
            if following.strip() and following not in " ,./-":
                out.append("a")
            i += 1
            continue
        if ch in VOWELS:
            out.append(VOWELS[ch])
        elif ch in MATRAS:
            out.append(MATRAS[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _fold(word: str) -> str:
    """Collapse spelling variation: aa->a, ee->i, oo->u, double letters, sh/s, v/w."""
    w = word.replace("aa", "a").replace("ee", "i").replace("oo", "u").replace("w", "v")
    w = w.replace("sh", "s").replace("ph", "f").replace("z", "j")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w.rstrip("a") if len(w) > 3 else w


def normalise(name: str | None) -> str:
    if not name:
        return ""
    t = transliterate(name).lower()
    t = re.sub(r"[@].*$", "", t)  # a UPI ID: keep only the handle
    t = re.sub(r"[^a-z\s]", " ", t)
    words = [re.sub(r"(ji|jee|bhai)$", "", w) if len(w) > 5 else w for w in t.split()]
    words = [w for w in words if w not in HONORIFICS and w not in BUSINESS_WORDS]
    return " ".join(_fold(w) for w in words)


def similarity(a: str | None, b: str | None) -> float:
    """0..100. Token-set ratio so 'Sharma' vs 'Rakesh Sharma' scores high."""
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    return float(max(fuzz.token_set_ratio(na, nb), fuzz.partial_ratio(na, nb) - 10))
