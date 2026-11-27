"""Ledger-app exports (Khatabook, OkCredit, Vyapar). The layout is detected from the header row;
an unknown layout is refused with a reason rather than guessed."""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from app.core.dates import parse_date
from app.core.money import to_paise


class CSVFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ExportRow:
    entry_date: date
    party_text: str | None
    amount_paise: int
    direction: str
    note: str | None = None
    kind: str = "money"  # credit_given for "You gave" / "Credit" rows in credit-book apps


def _norm(h: str) -> str:
    return "".join(ch for ch in h.lower() if ch.isalnum())


def _amount(v: str | None) -> int:
    v = (v or "").strip()
    return to_paise(v) if v and v not in {"-", "0", "0.00"} else 0


def _khatabook(rows: list[dict[str, str]], title: str = "") -> list[ExportRow]:
    """A customer statement is a credit book: "You gave" is credit given, "You got" is money
    received. In a supplier statement "You gave" is money paid, and "You got" is goods bought
    on credit (no money moved; cleared later by the payments)."""
    supplier = "supplier" in title.lower() or any("suppliername" in r for r in rows[:1])
    out = []
    for r in rows:
        got, gave = _amount(r.get("yougot")), _amount(r.get("yougave"))
        party = (
            r.get("customername") or r.get("suppliername") or r.get("name") or r.get("partyname")
        )
        d = parse_date(r["date"])
        if supplier:
            if got:
                out.append(ExportRow(d, party, got, "in", r.get("details"), "credit_taken"))
            if gave:
                out.append(ExportRow(d, party, gave, "out", r.get("details")))
            continue
        if got:
            out.append(ExportRow(d, party, got, "in", r.get("details")))
        if gave:
            out.append(ExportRow(d, party, gave, "out", r.get("details"), "credit_given"))
    return out


def _okcredit(rows: list[dict[str, str]], title: str = "") -> list[ExportRow]:
    out = []
    for r in rows:
        kind = (r.get("type") or r.get("transactiontype") or "").strip().lower()
        amt = _amount(r.get("amount"))
        if not amt:
            continue
        direction = "in" if kind.startswith("pay") or kind in {"received", "got"} else "out"
        out.append(
            ExportRow(
                parse_date(r["date"]),
                r.get("name") or r.get("customer"),
                amt,
                direction,
                r.get("note") or r.get("notes"),
                # OkCredit is a credit book: a "credit" row is credit given to the customer.
                "credit_given" if direction == "out" else "money",
            )
        )
    return out


VYAPAR_IN = {"sale", "paymentin", "receivedpayment", "saleorder"}
VYAPAR_OUT = {"purchase", "paymentout", "expense", "paidpayment"}


def _vyapar(rows: list[dict[str, str]], title: str = "") -> list[ExportRow]:
    out = []
    for r in rows:
        kind = _norm(r.get("type") or r.get("transactiontype") or "")
        moved = _amount(r.get("receivedpaid") or r.get("receivedorpaid") or r.get("paidamount"))
        if not moved:
            continue
        if kind in VYAPAR_IN:
            direction = "in"
        elif kind in VYAPAR_OUT:
            direction = "out"
        else:
            continue
        out.append(
            ExportRow(
                parse_date(r["date"]),
                r.get("partyname") or r.get("name"),
                moved,
                direction,
                r.get("refno"),
            )
        )
    return out


Parser = Callable[[list[dict[str, str]], str], list[ExportRow]]
FORMATS: dict[str, tuple[set[str], Parser]] = {
    "khatabook": ({"date", "yougave", "yougot"}, _khatabook),
    "vyapar": ({"date", "partyname", "type", "receivedpaid"}, _vyapar),
    "okcredit": ({"date", "name", "type", "amount"}, _okcredit),
}

MAX_ROWS = 20_000


def parse_export(data: bytes) -> tuple[str, list[ExportRow]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVFormatError("File is not UTF-8 text") from exc
    lines = text.splitlines()
    # Apps put a title or shop name above the header; find the first row that matches a format.
    for start in range(min(len(lines), 15)):
        reader = csv.reader([lines[start]])
        header = [_norm(h) for h in next(reader, [])]
        for name, (required, parser) in FORMATS.items():
            if required <= set(header):
                body = list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))
                if len(body) > MAX_ROWS:
                    raise CSVFormatError("Too many rows")
                rows = [
                    {_norm(k): (v or "") for k, v in r.items() if k}
                    for r in body
                    if any((v or "").strip() for v in r.values())
                ]
                try:
                    return name, parser(rows, "\n".join(lines[:start]))
                except (KeyError, ValueError) as exc:
                    raise CSVFormatError(f"Could not read a row: {exc}") from exc
    raise CSVFormatError("Unknown file layout. Export from Khatabook, OkCredit or Vyapar.")
