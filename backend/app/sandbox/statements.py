"""Sandbox statement PDFs in two layouts the parsers know: a bank statement (SBI-style columns)
and a UPI app statement (PhonePe-style). Used for seed data, tests and the red-team set."""

import io
from dataclasses import dataclass
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.money import format_inr


@dataclass(frozen=True)
class StatementTxn:
    txn_date: date
    description: str
    amount_paise: int
    direction: str  # in / out
    ref: str
    vpa: str | None = None
    name: str | None = None


def _amt(paise: int) -> str:
    return format_inr(paise).replace("₹", "") + ("" if paise % 100 else ".00")


def bank_statement_pdf(
    holder: str,
    account: str,
    opening_paise: int,
    txns: list[StatementTxn],
    producer: str = "Sandbox Bank CBS Statement",
    bank: str = "SANDBOX BANK OF INDIA",
    break_balance_at: int | None = None,
    font: str = "Helvetica",
    alt_font_row: int | None = None,
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    c.setProducer(producer)
    c.setCreator(producer)
    c.setTitle("Account Statement")
    _, h = A4
    y = h - 50

    def header() -> float:
        c.setFont(font, 12)
        c.drawString(40, h - 40, bank)
        c.setFont(font, 9)
        c.drawString(40, h - 58, f"Account Name : {holder}")
        c.drawString(40, h - 70, f"Account Number : {account}")
        c.drawString(40, h - 82, f"Opening Balance : {_amt(opening_paise)}")
        c.drawString(40, h - 104, "Txn Date | Description | Ref No | Debit | Credit | Balance")
        return float(h - 120)

    y = header()
    bal = opening_paise
    for i, t in enumerate(txns):
        bal += t.amount_paise if t.direction == "in" else -t.amount_paise
        shown = bal + (100_000 if break_balance_at is not None and i >= break_balance_at else 0)
        debit = _amt(t.amount_paise) if t.direction == "out" else "-"
        credit = _amt(t.amount_paise) if t.direction == "in" else "-"
        desc = t.description[:48]
        c.setFont("Courier" if alt_font_row == i else font, 8)
        c.drawString(
            40,
            y,
            f"{t.txn_date.strftime('%d/%m/%Y')} | {desc} | {t.ref} | {debit} | "
            f"{credit} | {_amt(shown)}",
        )
        y -= 13
        if y < 60:
            c.showPage()
            y = header()
    c.setFont(font, 9)
    c.drawString(40, max(y - 20, 30), f"Closing Balance : {_amt(bal)}")
    c.save()
    return buf.getvalue()


def upi_statement_pdf(
    holder: str,
    phone: str,
    txns: list[StatementTxn],
    producer: str = "Sandbox UPI App Statement Generator",
) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    c.setProducer(producer)
    c.setCreator(producer)
    c.setTitle("Transaction Statement")
    _, h = A4

    def header() -> float:
        c.setFont("Helvetica", 12)
        c.drawString(40, h - 40, f"Transaction Statement for {phone}")
        c.setFont("Helvetica", 9)
        c.drawString(40, h - 58, f"Name : {holder}")
        c.drawString(40, h - 80, "Date | Transaction Details | Type | Amount")
        return float(h - 96)

    y = header()
    for t in txns:
        kind = "CREDIT" if t.direction == "in" else "DEBIT"
        who = ("Received from " if t.direction == "in" else "Paid to ") + (t.name or t.vpa or "")
        c.setFont("Helvetica", 8)
        c.drawString(
            40,
            y,
            f"{t.txn_date.strftime('%b %d, %Y')} | {who} | {kind} | INR {_amt(t.amount_paise)}",
        )
        c.drawString(60, y - 11, f"UTR No. {t.ref} | UPI ID {t.vpa or '-'}")
        y -= 26
        if y < 60:
            c.showPage()
            y = header()
    c.save()
    return buf.getvalue()
