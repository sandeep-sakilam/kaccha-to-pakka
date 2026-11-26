import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.adapters.ai import MockAI
from app.adapters.gateway import AIGateway
from app.modules.statements.parsers import StatementError, parse_statement
from app.sandbox.statements import StatementTxn, bank_statement_pdf, upi_statement_pdf
from tests.conftest import setup_business


def txns(n: int = 6, start: date = date(2026, 9, 1), seed: int = 0) -> list[StatementTxn]:
    out = []
    for i in range(n):
        inflow = i % 3 != 2
        vpa = f"cust{i % 4}@oksbi" if inflow else "gupta.traders@okhdfc"
        name = f"CUSTOMER {i % 4}" if inflow else "GUPTA TRADERS"
        out.append(
            StatementTxn(
                start + timedelta(days=i * 3),
                f"UPI/{vpa}/{name}",
                (1500 + 250 * i) * 100,
                "in" if inflow else "out",
                f"6{seed:02d}{i:09d}",
                vpa,
                name,
            )
        )
    return out


def test_parse_bank_and_upi() -> None:
    bank = parse_statement(bank_statement_pdf("MEENA DEVI", "XXXX1234", 500000, txns()))
    assert bank.layout == "bank:sandbox-sbi" and len(bank.txns) == 6
    assert (
        bank.txns[2].direction == "out" and bank.txns[2].counterparty_vpa == "gupta.traders@okhdfc"
    )
    upi = parse_statement(upi_statement_pdf("MEENA DEVI", "+919800000001", txns()))
    assert upi.layout == "upi:sandbox-phonepe" and upi.txns[0].counterparty_name == "CUSTOMER 0"


def test_many_pages() -> None:
    st = parse_statement(bank_statement_pdf("A", "X1", 10_000_000, txns(120)))
    assert len(st.txns) == 120 and int(st.metadata["pages"]) >= 2


def test_unknown_layout_llm_must_balance() -> None:
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(40, 800, "Some Other Bank statement with a layout nobody has seen before.")
    c.drawString(40, 780, "01-09-2026  Opening 5000.00 ... credit 1500.00 balance 6500.00")
    c.save()
    with pytest.raises(StatementError):
        parse_statement(buf.getvalue(), AIGateway(MockAI()))  # mock LLM returns no JSON

    class LLM(MockAI):
        def __init__(self, balance: str) -> None:
            super().__init__()
            self.balance = balance

        def generate(self, system: str, prompt: str, language: str) -> str:
            return json.dumps(
                {
                    "opening_balance": "5000.00",
                    "txns": [
                        {
                            "date": "01/09/2026",
                            "description": "UPI/a@ok/A",
                            "debit": "0",
                            "credit": "1500.00",
                            "balance": self.balance,
                            "ref": "1",
                        }
                    ],
                }
            )

    ok = parse_statement(buf.getvalue(), AIGateway(LLM("6500.00")))
    assert ok.parsed_by == "llm" and ok.txns[0].amount_paise == 150000
    with pytest.raises(StatementError, match="do not add up"):
        parse_statement(buf.getvalue(), AIGateway(LLM("9500.00")))


def test_scanned_pdf_rejected() -> None:
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    canvas.Canvas(buf).save()
    with pytest.raises(StatementError, match="scanned"):
        parse_statement(buf.getvalue())


def test_upload_and_overlap_dedup(client: TestClient) -> None:
    h, biz = setup_business(client)
    first = bank_statement_pdf("SHARMA", "XXXX1", 500000, txns(6))
    overlap = bank_statement_pdf("SHARMA", "XXXX1", 500000, txns(9))  # first 6 rows repeat

    def post(data: bytes, key: str) -> dict[str, object]:
        r = client.post(
            f"/businesses/{biz}/statements",
            headers={**h, "Idempotency-Key": key},
            files={"file": ("s.pdf", data, "application/pdf")},
        )
        body: dict[str, object] = r.json()
        return body

    a = post(first, "stmt-key-1")
    assert a["status"] == "parsed" and a["meta"]["txns"] == 6  # type: ignore[index]
    assert post(first, "stmt-key-2")["code"] == "duplicate_file"
    b = post(overlap, "stmt-key-3")
    assert b["meta"]["txns"] == 3 and b["meta"]["duplicates_skipped"] == 6  # type: ignore[index]
    assert len(client.get(f"/businesses/{biz}/transactions", headers=h).json()) == 9
    assert post(b"hello", "stmt-key-4")["code"] == "not_pdf"
