"""Forensic checks on statement PDFs. Deterministic; no AI judgement.

A "hold" signal puts the passport on hold for a reviewer (red flags pause, they don't subtract);
a "warn" signal is recorded and shown to the reviewer but does not hold on its own.
"""

import re
from dataclasses import asdict, dataclass
from datetime import datetime

from app.modules.statements.parsers import ParsedStatement, balance_breaks

EDITORS = [
    "ilovepdf",
    "smallpdf",
    "sejda",
    "pdfescape",
    "acrobat pro",
    "microsoft word",
    "microsoft® word",
    "libreoffice",
    "openoffice",
    "canva",
    "phantompdf",
    "pdf-xchange",
    "nitro",
    "foxit",
    "google docs",
    "pdffiller",
    "docusign",
    "inkscape",
    "photoshop",
    "chatgpt",
    "wps",
    "pdf24",
    "pdfelement",
    "soda pdf",
    "word",
]
KNOWN_PRODUCERS = [
    "sandbox bank cbs",
    "sandbox upi app",
    "finacle",
    "bancs",
    "flexcube",
    "jasperreports",
    "itext",
    "oracle bi publisher",
    "crystal reports",
    "phonepe",
    "paytm",
    "google pay",
    "bhim",
]
UTR_PATTERNS = [
    re.compile(p)
    for p in (r"^\d{12}$", r"^[A-Z]{4}[A-Z0-9]{12}$", r"^[A-Z]{4}R\d{11}$", r"^\d{6,10}$")
]


@dataclass(frozen=True)
class Signal:
    code: str
    severity: str  # hold | warn
    detail: str


@dataclass(frozen=True)
class TamperReport:
    verdict: str  # clean | warn | hold
    signals: list[Signal]

    def as_dict(self) -> dict[str, object]:
        return {"verdict": self.verdict, "signals": [asdict(s) for s in self.signals]}


def _pdf_date(v: str | None) -> datetime | None:
    if not v:
        return None
    m = re.match(r"D:(\d{14})", v)
    return datetime.strptime(m.group(1), "%Y%m%d%H%M%S") if m else None


def check_metadata(meta: dict[str, object]) -> list[Signal]:
    out: list[Signal] = []
    producer = f"{meta.get('Producer') or ''} {meta.get('Creator') or ''}".strip().lower()
    if any(re.search(rf"(?<![a-z]){re.escape(e)}(?![a-z])", producer) for e in EDITORS):
        out.append(
            Signal(
                "edited_with_tool", "hold", f"Made or saved with an editing tool: {producer[:80]}"
            )
        )
    elif not any(k in producer for k in KNOWN_PRODUCERS):
        out.append(Signal("unknown_producer", "warn", f"Unknown PDF producer: {producer[:80]}"))
    created, modified = (
        _pdf_date(str(meta.get("CreationDate") or "")),
        _pdf_date(str(meta.get("ModDate") or "")),
    )
    if created and modified and (modified - created).total_seconds() > 60:
        out.append(
            Signal(
                "modified_after_creation", "warn", f"Modified {modified} after creation {created}"
            )
        )
    return out


def check_incremental(data: bytes) -> list[Signal]:
    if data.count(b"%%EOF") > 1:
        return [
            Signal("incremental_update", "hold", "The file was changed after it was first saved")
        ]
    return []


def check_fonts(fonts: dict[str, int]) -> list[Signal]:
    total = sum(fonts.values())
    if total == 0 or len(fonts) < 2:
        return []
    main = max(fonts.values())
    minor = {f: n for f, n in fonts.items() if n < main}
    stray = {f: n for f, n in minor.items() if n / total < 0.05}
    if stray:
        return [
            Signal(
                "font_mismatch",
                "hold",
                "A few characters use a different font: "
                + ", ".join(f"{f} ({n})" for f, n in stray.items()),
            )
        ]
    return []


def check_utrs(st: ParsedStatement) -> list[Signal]:
    refs = [t.utr for t in st.txns if t.utr]
    bad = [r for r in refs if not any(p.match(r) for p in UTR_PATTERNS)]
    out = []
    if bad:
        out.append(
            Signal(
                "utr_format", "hold", f"{len(bad)} reference numbers are not valid UTRs: {bad[:3]}"
            )
        )
    dups = {r for r in refs if refs.count(r) > 1}
    if dups:
        out.append(Signal("duplicate_utr", "hold", f"Same UTR used twice: {sorted(dups)[:3]}"))
    return out


def check_balances(st: ParsedStatement) -> list[Signal]:
    out = []
    breaks = balance_breaks(st)
    if breaks:
        out.append(
            Signal(
                "balance_break",
                "hold",
                f"Running balance does not add up at {len(breaks)} rows "
                f"(first at row {breaks[0] + 1})",
            )
        )
    if (
        st.closing_balance_paise is not None
        and st.txns
        and st.txns[-1].balance_after_paise is not None
        and st.txns[-1].balance_after_paise != st.closing_balance_paise
    ):
        out.append(Signal("closing_mismatch", "hold", "Closing balance does not match last row"))
    dates = [t.txn_date for t in st.txns]
    if dates != sorted(dates):
        out.append(Signal("dates_out_of_order", "warn", "Transactions are not in date order"))
    return out


def run_checks(data: bytes, st: ParsedStatement) -> TamperReport:
    signals = (
        check_metadata(st.metadata)
        + check_incremental(data)
        + check_fonts(st.fonts)
        + check_utrs(st)
        + check_balances(st)
    )
    verdict = (
        "hold" if any(s.severity == "hold" for s in signals) else ("warn" if signals else "clean")
    )
    return TamperReport(verdict, signals)
