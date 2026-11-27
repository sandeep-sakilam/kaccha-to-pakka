"""Explanations in the owner's language. The LLM only rephrases the structured reasons; it never
adds or drops one. Its output is checked line by line against the reason list (count and every
number); on any mismatch, or if the LLM is down, the fixed templates are used."""

import json
import re
from dataclasses import dataclass
from typing import Any

from app.adapters.errors import AdapterError
from app.adapters.gateway import AIGateway

T: dict[str, dict[str, str]] = {
    "money_months": {
        "en": "{months} months of real payments in your bank account",
        "hi": "आपके बैंक खाते में {months} महीने के असली भुगतान",
    },
    "cash_sales_deposited": {
        "en": "Cash sales deposited in the bank in {months} months",
        "hi": "{months} महीनों में नकद बिक्री बैंक में जमा हुई",
    },
    "daily_sales_agree": {
        "en": "Your daily sales agreed with the bank for {months} months",
        "hi": "{months} महीनों तक आपकी रोज़ की बिक्री बैंक से मेल खाई",
    },
    "daily_sales_below_bank": {
        "en": "In {months} months you told less sales than the bank shows",
        "hi": "{months} महीनों में आपने बैंक से कम बिक्री बताई",
    },
    "daily_sales_far_above_bank": {
        "en": "In {months} months your told sales were far above the bank",
        "hi": "{months} महीनों में बताई बिक्री बैंक से बहुत ज़्यादा थी",
    },
    "registration_verified": {
        "en": "Your {source} registration is confirmed by the government register",
        "hi": "आपका {source} पंजीकरण सरकारी रजिस्टर से पक्का हुआ",
    },
    "registration_not_active": {
        "en": "Your {source} number is not active in the government register",
        "hi": "आपका {source} नंबर सरकारी रजिस्टर में चालू नहीं है",
    },
    "add_registration": {
        "en": "Add your Udyam or GST number (free Udyam registration takes minutes)",
        "hi": "अपना उद्यम या GST नंबर जोड़ें (मुफ़्त उद्यम पंजीकरण कुछ मिनट में होता है)",
    },
    "no_money_data": {"en": "No bank or UPI data yet", "hi": "अभी कोई बैंक या UPI डेटा नहीं"},
    "pdf_only_capped": {
        "en": "Only a PDF statement, so the band can be at most C",
        "hi": "सिर्फ़ PDF स्टेटमेंट है, इसलिए ज़्यादा से ज़्यादा C बैंड",
    },
    "ledger_matches": {
        "en": "{percent}% of your ledger matches your bank payments",
        "hi": "आपके खाते का {percent}% बैंक भुगतान से मिलता है",
    },
    "no_ledger": {"en": "No ledger added yet", "hi": "अभी कोई खाता-बही नहीं जोड़ी"},
    "credit_repaid_bank": {
        "en": "{percent}% of the credit you gave {customers} customers came back through the bank",
        "hi": "{customers} ग्राहकों को दिए उधार का {percent}% बैंक से वापस आया",
    },
    "matches_rest_on_owner": {
        "en": "{percent}% of your matched ledger rests on your own answers about names",
        "hi": "आपके मिलान किए खाते का {percent}% नामों पर आपके अपने जवाबों पर टिका है",
    },
    "suppliers_paid_bank": {
        "en": "{percent}% of the goods you bought on credit from {suppliers} suppliers was paid "
        "through the bank",
        "hi": "{suppliers} सप्लायरों से उधार लिए सामान का {percent}% बैंक से चुकाया गया",
    },
    "pay_suppliers_by_bank": {
        "en": "Pay your suppliers by UPI or bank transfer",
        "hi": "सप्लायरों को UPI या बैंक से भुगतान करें",
    },
    "mostly_cash_entries": {
        "en": "{count} ledger entries are cash, which the bank cannot show",
        "hi": "खाते की {count} एंट्री नकद हैं, जो बैंक में नहीं दिखतीं",
    },
    "ledger_copied_from_bank": {
        "en": "A ledger copied from the bank statement adds nothing new",
        "hi": "बैंक स्टेटमेंट से उतारा गया खाता कुछ नया नहीं जोड़ता",
    },
    "partners_confirmed": {
        "en": "{count} trading partners confirmed you",
        "hi": "{count} व्यापारी साथियों ने आपकी पुष्टि की",
    },
    "few_confirmations": {
        "en": "Only {count} trading partners have confirmed so far",
        "hi": "अभी तक सिर्फ़ {count} व्यापारी साथियों ने पुष्टि की",
    },
    "confirmation_discrepancy": {
        "en": "A partner's answer did not match the payments",
        "hi": "एक साथी का जवाब भुगतानों से मेल नहीं खाया",
    },
    "business_age": {
        "en": "Your business has been running for {years} years",
        "hi": "आपका व्यापार {years} साल से चल रहा है",
    },
    "age_not_proven": {
        "en": "You said {claimed} years in business; papers and bank data show {proven}",
        "hi": "आपने {claimed} साल का व्यापार बताया; कागज़ और बैंक डेटा {proven} दिखाते हैं",
    },
    "address_proof": {
        "en": "{count} bill or licence shows your shop's name and address",
        "hi": "{count} बिल या लाइसेंस पर आपकी दुकान का नाम और पता है",
    },
    "add_address_proof": {
        "en": "Photograph a recent electricity bill or your shop licence",
        "hi": "हाल का बिजली बिल या दुकान का लाइसेंस फ़ोटो करें",
    },
    "presence_checks": {
        "en": "{count} shop checks passed on random days",
        "hi": "अनजान दिनों पर दुकान की {count} जाँच सफल रहीं",
    },
    "presence_missed": {
        "en": "{count} shop checks were missed or failed",
        "hi": "दुकान की {count} जाँच छूटीं या असफल रहीं",
    },
    "under_3_months": {
        "en": "Only {months} months of data, so confidence is low",
        "hi": "सिर्फ़ {months} महीने का डेटा है, इसलिए भरोसा कम है",
    },
    "money_data_old": {
        "en": "Your latest bank data is {days} days old",
        "hi": "आपका नया बैंक डेटा {days} दिन पुराना है",
    },
    "on_hold": {
        "en": "Your passport is on hold while we check something",
        "hi": "कुछ जाँच चल रही है, इसलिए आपका पासपोर्ट रुका हुआ है",
    },
    "link_bank": {"en": "Link your bank account", "hi": "अपना बैंक खाता जोड़ें"},
    "record_payments_in_ledger": {
        "en": "Write every payment in your ledger with the name",
        "hi": "हर भुगतान नाम के साथ खाते में लिखें",
    },
    "confirm_ledger_entries": {
        "en": "Confirm your ledger entries",
        "hi": "अपने खाते की एंट्री की पुष्टि करें",
    },
    "ledger_unconfirmed": {
        "en": "Your ledger entries are not confirmed yet",
        "hi": "आपके खाते की एंट्री की अभी पुष्टि नहीं हुई",
    },
    "add_ledger": {"en": "Add your ledger pages", "hi": "अपने खाते के पन्ने जोड़ें"},
    "write_full_names": {
        "en": "Write customers' full names in your ledger",
        "hi": "खाते में ग्राहकों के पूरे नाम लिखें",
    },
    "ask_customers_upi": {
        "en": "Ask credit customers to pay you back by UPI",
        "hi": "उधार वाले ग्राहकों से UPI से पैसे लौटाने को कहें",
    },
    "ask_partners": {
        "en": "Ask {more} more suppliers or customers to confirm",
        "hi": "{more} और सप्लायर या ग्राहकों से पुष्टि करवाएँ",
    },
    "shop_photo": {"en": "Take a photo of your shop front", "hi": "अपनी दुकान के सामने की फ़ोटो लें"},
    "refresh_bank_data": {"en": "Refresh your bank data", "hi": "अपना बैंक डेटा नया करें"},
}
BAND_LABEL = {
    "A": {"en": "Very strong", "hi": "बहुत मज़बूत"},
    "B": {"en": "Strong", "hi": "मज़बूत"},
    "C": {"en": "Fair", "hi": "ठीक"},
    "D": {"en": "Weak", "hi": "कमज़ोर"},
    "E": {"en": "Very weak", "hi": "बहुत कमज़ोर"},
    "U": {"en": "Insufficient evidence", "hi": "सबूत काफ़ी नहीं"},
}
CONFIDENCE_LABEL = {
    "High": {"en": "high confidence", "hi": "ज़्यादा भरोसा"},
    "Medium": {"en": "medium confidence", "hi": "मध्यम भरोसा"},
    "Low": {"en": "low confidence", "hi": "कम भरोसा"},
}
STATUS_LABEL = {
    "on_hold": {"en": "On hold for review", "hi": "जाँच के लिए रुका"},
    "stale": {"en": "Expired: add new data", "hi": "पुराना: नया डेटा जोड़ें"},
    "final": {"en": "Active", "hi": "चालू"},
}


def template(code: str, params: dict[str, Any], lang: str) -> str:
    t = T.get(code, {}).get(lang) or T.get(code, {}).get("en") or code
    try:
        return t.format(**params)
    except (KeyError, IndexError):
        return t


@dataclass(frozen=True)
class Explanation:
    language: str
    band_label: str
    confidence_label: str
    status_label: str
    headline: str
    positives: list[str]
    gaps: list[str]
    improve: list[str]
    source: str  # llm | template


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def _llm_lines(ai: AIGateway, items: list[dict[str, Any]], lang: str) -> list[str] | None:
    system = (
        "Rewrite each reason as one short, warm sentence for a small shop owner in "
        f"{'Hindi' if lang == 'hi' else 'simple English'}. Keep every number exactly. "
        "Do not add, merge, drop or reorder reasons. Reply with a JSON list of strings, "
        "one per reason, nothing else."
    )
    try:
        out = ai.generate(system, json.dumps(items, ensure_ascii=False), lang).value
        m = re.search(r"\[.*\]", out, re.S)
        lines = json.loads(m.group(0)) if m else None
    except (AdapterError, json.JSONDecodeError):
        return None
    if not isinstance(lines, list) or len(lines) != len(items):
        return None
    for line, item in zip(lines, items, strict=True):
        if not isinstance(line, str) or not line.strip() or len(line) > 200:
            return None
        expected = sorted(str(v) for v in item["params"].values() if isinstance(v, int))
        if sorted(_numbers(line)) != expected:
            return None  # a number was changed, dropped or invented
    return [s.strip() for s in lines]


STRONG_BANDS = {"A", "B", "C"}


def _lower_first(text: str, lang: str) -> str:
    return text[0].lower() + text[1:] if lang == "en" and text else text


def _headline(
    band: str, status: str, groups: dict[str, list[dict[str, Any]]], label: str, lang: str
) -> str:
    """A, B, C: built from strengths. D, E and U (weak): built only from gaps and what would
    raise it, never from strengths, so a weak passport is never explained by its good points."""

    def lines(key: str, n: int) -> list[str]:
        return [template(r["code"], r.get("params", {}), lang) for r in groups[key][:n]]

    if status == "on_hold":
        return template("on_hold", {}, lang) + "."
    hi = lang == "hi"
    if band in STRONG_BANDS:
        pos = lines("positives", 2)
        if pos:
            joined = (" और " if hi else " and ").join(_lower_first(p, lang) for p in pos)
            return (
                f"आपका पासपोर्ट {label} है क्योंकि {joined}।"
                if hi
                else f"Your passport is {label.lower()} because {joined}."
            )
        return f"आपका पासपोर्ट: {label}।" if hi else f"Your passport: {label}."
    gaps, improve = lines("gaps", 1), lines("improve", 1)
    head = (
        f"आपका पासपोर्ट {label} है"
        if hi
        else f"Your passport is {label.lower()}"
        if band != "U"
        else "Your passport does not have enough evidence yet"
    )
    if hi and band == "U":
        head = "आपके पासपोर्ट के लिए अभी सबूत काफ़ी नहीं हैं"
    parts = [head + (f": {_lower_first(gaps[0], lang)}" if gaps else "")]
    if improve:
        parts.append(
            f"इसे बढ़ाने के लिए: {improve[0]}"
            if hi
            else f"To raise it: {_lower_first(improve[0], lang)}"
        )
    return ("। ".join(parts) + "।") if hi else (". ".join(parts) + ".")


def explain(
    band: str,
    confidence: str,
    status: str,
    reasons: dict[str, Any],
    lang: str,
    ai: AIGateway | None = None,
) -> Explanation:
    lang = "hi" if lang == "hi" else "en"
    groups = {k: reasons.get(k, []) for k in ("positives", "gaps", "improve")}
    items = [{"code": r["code"], "params": r.get("params", {})} for k in groups for r in groups[k]]
    lines = _llm_lines(ai, items, lang) if ai and items else None
    source = "llm" if lines else "template"
    if lines is None:
        lines = [template(i["code"], i["params"], lang) for i in items]
    it = iter(lines)
    out = {k: [next(it) for _ in groups[k]] for k in groups}
    label = BAND_LABEL.get(band, BAND_LABEL["U"])[lang]
    headline = _headline(band, status, groups, label, lang)
    return Explanation(
        lang,
        label,
        CONFIDENCE_LABEL.get(confidence, {}).get(lang, confidence),
        STATUS_LABEL.get(status, {}).get(lang, status),
        headline,
        out["positives"],
        out["gaps"],
        out["improve"],
        source,
    )
