"""Date parsing for exports and statements (Indian day-first formats)."""

from datetime import date, datetime

FORMATS = [
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d %b %Y",
    "%d-%b-%y",
    "%d %b %y",
    "%d %B %Y",
    "%d.%m.%Y",
    "%b %d, %Y",
    "%d/%b/%Y",
]


def parse_date(text: str) -> date:
    t = text.strip().split(" ")[0] if ":" in text and " " in text.strip() else text.strip()
    for fmt in FORMATS:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    for fmt in FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unknown date format: {text!r}")
