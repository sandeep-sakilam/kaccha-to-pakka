from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.modules.imports.csv_parsers import CSVFormatError, parse_export
from tests.conftest import setup_business

FIX = Path(__file__).parent / "fixtures"


def test_khatabook() -> None:
    src, rows = parse_export((FIX / "khatabook.csv").read_bytes())
    assert src == "khatabook"
    # A customer statement is a credit book: "You gave" is credit given.
    assert [(r.entry_date, r.party_text, r.amount_paise, r.direction, r.kind) for r in rows] == [
        (date(2026, 10, 12), "Rakesh Sharma", 400000, "in", "money"),
        (date(2026, 10, 13), "Gupta Traders", 250000, "out", "credit_given"),
        (date(2026, 10, 14), "Rakesh Sharma", 50000, "in", "money"),
        (date(2026, 10, 14), "Rakesh Sharma", 100000, "out", "credit_given"),
    ]


def test_khatabook_supplier_statement() -> None:
    """Goods bought on credit moved no money; the later payment did."""
    src, rows = parse_export((FIX / "khatabook_supplier.csv").read_bytes())
    assert src == "khatabook"
    assert [(r.party_text, r.amount_paise, r.direction, r.kind) for r in rows] == [
        ("Gupta Traders", 1200000, "out", "money")
    ]


def test_okcredit_and_vyapar() -> None:
    src, rows = parse_export((FIX / "okcredit.csv").read_bytes())
    assert src == "okcredit" and [(r.amount_paise, r.direction, r.kind) for r in rows] == [
        (400000, "in", "money"),
        (25050, "out", "credit_given"),
    ]
    src, rows = parse_export((FIX / "vyapar.csv").read_bytes())
    assert src == "vyapar" and [(r.amount_paise, r.direction) for r in rows] == [
        (400000, "in"),
        (250000, "out"),
    ]


def test_unknown_layout_refused() -> None:
    with pytest.raises(CSVFormatError):
        parse_export(b"a,b,c\n1,2,3\n")


def test_import_endpoint(client: TestClient) -> None:
    h, biz = setup_business(client)
    data = (FIX / "khatabook.csv").read_bytes()

    def post(key: str) -> dict[str, object]:
        r = client.post(
            f"/businesses/{biz}/imports/csv",
            headers={**h, "Idempotency-Key": key},
            files={"file": ("kb.csv", data, "text/csv")},
        )
        body: dict[str, object] = r.json()
        return body

    first = post("csv-import-1")
    assert first["source"] == "khatabook" and first["rows"] == 4 and first["created"]
    assert post("csv-import-1")["created"] is False
    assert post("csv-import-2")["code"] == "duplicate_file"
    ledger = client.get(f"/businesses/{biz}/ledger", headers=h).json()
    assert len(ledger) == 4 and all(e["confidence"] == 1.0 for e in ledger)
    assert client.get(f"/businesses/{biz}/readback", headers=h).json() == []
