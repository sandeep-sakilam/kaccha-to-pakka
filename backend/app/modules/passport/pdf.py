"""Passport PDF in Hindi and English (WeasyPrint + Noto Sans Devanagari for correct shaping)."""

import base64
import html
import io
from pathlib import Path
from typing import Any

import qrcode
import qrcode.image.svg

FONTS = Path(__file__).resolve().parents[2] / "assets" / "fonts"


def qr_svg(data: str) -> str:
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()


def qr_png_b64(data: str) -> str:
    img = qrcode.make(data, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


RANGES = {
    "devanagari": "U+0900-097F, U+1CD0-1CF9, U+200C-200D, U+20A8, U+20B9, U+20F0, U+25CC, "
    "U+A830-A839, U+A8E0-A8FF",
    "latin": "U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, "
    "U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, "
    "U+FEFF, U+FFFD",
}


def _font_faces() -> str:
    """Each subset file only covers its own script, so unicode-range must route characters."""
    faces = []
    for weight in (400, 700):
        for subset, rng in RANGES.items():
            f = FONTS / f"noto-sans-devanagari-{subset}-{weight}-normal.woff"
            faces.append(
                f"@font-face {{ font-family: 'Noto{subset}'; font-weight: {weight}; "
                f"src: url('{f.as_uri()}'); unicode-range: {rng}; }}"
            )
    return "\n".join(faces)


LABELS = {
    "en": {
        "title": "Business Trust Passport",
        "band": "Trust band",
        "confidence": "Confidence",
        "status": "Status",
        "valid": "Valid until",
        "why": "Why",
        "gaps": "Gaps",
        "improve": "What would raise it",
        "pillars": "Pillars",
        "money": "Money",
        "records": "Records",
        "network": "Trading partners",
        "presence": "Presence",
        "verify": "Scan to verify the signature and live status",
        "sandbox": "SANDBOX: test data, not a real verification",
        "disclaimer": "Evidence and verification only. Not a credit score and not a loan "
        "offer: the lender decides.",
        "rules": "Rules version",
    },
    "hi": {
        "title": "बिज़नेस ट्रस्ट पासपोर्ट",
        "band": "ट्रस्ट बैंड",
        "confidence": "भरोसा",
        "status": "स्थिति",
        "valid": "कब तक मान्य",
        "why": "क्यों",
        "gaps": "कमियाँ",
        "improve": "इसे कैसे बढ़ाएँ",
        "pillars": "स्तंभ",
        "money": "पैसा",
        "records": "खाता-बही",
        "network": "व्यापारी साथी",
        "presence": "दुकान की मौजूदगी",
        "verify": "हस्ताक्षर और ताज़ा स्थिति जाँचने के लिए स्कैन करें",
        "sandbox": "सैंडबॉक्स: टेस्ट डेटा, असली जाँच नहीं",
        "disclaimer": "यह केवल सबूत और जाँच है। यह क्रेडिट स्कोर या कर्ज़ का वादा नहीं है: फ़ैसला ऋणदाता का है।",
        "rules": "नियम संस्करण",
    },
}


def render_html(
    passport: dict[str, Any], explanation: dict[str, Any], verify_url: str, lang: str
) -> str:
    L = LABELS["hi" if lang == "hi" else "en"]
    s = passport["credentialSubject"]
    e = html.escape

    def items(lines: list[str]) -> str:
        return "".join(f"<li>{e(x)}</li>" for x in lines) or "<li>—</li>"

    pillars = "".join(
        f"<tr><td>{L[k]}</td><td><div class='bar'><span style='width:{v}%'></span></div></td>"
        f"<td>{v:.0f}</td></tr>"
        for k, v in s["pillars"].items()
    )
    sandbox = f"<p class='sandbox'>{L['sandbox']}</p>" if s.get("sandbox") else ""
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><style>
{_font_faces()}
@page {{ size: A4; margin: 16mm; }}
body {{ font-family: 'Notolatin', 'Notodevanagari', sans-serif; color: #111; font-size: 11pt; }}
h1 {{ color: #14532d; margin: 0 0 4mm; font-size: 20pt; }}
.top {{ display: flex; justify-content: space-between; gap: 8mm; }}
.band {{ font-size: 48pt; font-weight: 700; color: #14532d; line-height: 1; }}
.meta td {{ padding: 1mm 4mm 1mm 0; }}
.bar {{ width: 60mm; height: 3mm; background: #e5e7eb; }}
.bar span {{ display: block; height: 3mm; background: #14532d; }}
.sandbox {{ background: #fde047; padding: 2mm; font-weight: 700; }}
.small {{ font-size: 8.5pt; color: #374151; }}
svg {{ width: 42mm; height: 42mm; }}
</style></head><body>
{sandbox}
<h1>{L["title"]}</h1>
<div class="top"><div>
<p style="font-size:14pt;font-weight:700">{e(s["name"])}</p>
<p>{e(s["category"])} · {e(s.get("city") or "")}</p>
<table class="meta">
<tr><td>{L["band"]}</td><td><span class="band">{e(s["band"])}</span>
 {e(explanation["band_label"])}</td></tr>
<tr><td>{L["confidence"]}</td><td>{e(explanation["confidence_label"])}</td></tr>
<tr><td>{L["status"]}</td><td>{e(explanation["status_label"])}</td></tr>
<tr><td>{L["valid"]}</td><td>{e(passport["validUntil"][:10])}</td></tr>
</table></div>
<div style="text-align:center">{qr_svg(verify_url)}<p class="small">{L["verify"]}</p></div></div>
<p style="font-size:12pt">{e(explanation["headline"])}</p>
<h3>{L["why"]}</h3><ul>{items(explanation["positives"])}</ul>
<h3>{L["gaps"]}</h3><ul>{items(explanation["gaps"])}</ul>
<h3>{L["improve"]}</h3><ul>{items(explanation["improve"])}</ul>
<h3>{L["pillars"]}</h3><table>{pillars}</table>
<p class="small">{L["disclaimer"]}</p>
<p class="small">{L["rules"]}: {e(s["rulesVersion"])} · ID {e(passport["id"])}</p>
</body></html>"""


def render_pdf(
    passport: dict[str, Any], explanation: dict[str, Any], verify_url: str, lang: str
) -> bytes:
    from weasyprint import HTML

    return bytes(HTML(string=render_html(passport, explanation, verify_url, lang)).write_pdf())
