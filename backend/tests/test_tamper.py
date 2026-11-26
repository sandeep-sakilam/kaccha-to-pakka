from fastapi.testclient import TestClient

from app.modules.statements.parsers import parse_statement
from app.modules.statements.tamper import run_checks
from app.sandbox.statements import StatementTxn, bank_statement_pdf, upi_statement_pdf
from tests.conftest import setup_business
from tests.test_statements import txns


def codes(data: bytes) -> tuple[str, set[str]]:
    report = run_checks(data, parse_statement(data))
    return report.verdict, {s.code for s in report.signals}


def test_genuine_statements_are_clean() -> None:
    assert codes(bank_statement_pdf("A", "X1", 500000, txns()))[0] == "clean"
    assert codes(upi_statement_pdf("A", "+91", txns()))[0] == "clean"


def test_editing_tool_producer_holds() -> None:
    v, c = codes(bank_statement_pdf("A", "X1", 500000, txns(), producer="iLovePDF"))
    assert v == "hold" and "edited_with_tool" in c
    v, c = codes(bank_statement_pdf("A", "X1", 500000, txns(), producer="Microsoft® Word 2019"))
    assert "edited_with_tool" in c


def test_unknown_producer_only_warns() -> None:
    v, c = codes(bank_statement_pdf("A", "X1", 500000, txns(), producer="Some Bank Engine"))
    assert v == "warn" and c == {"unknown_producer"}


def test_inflated_balance_breaks_continuity() -> None:
    v, c = codes(bank_statement_pdf("A", "X1", 500000, txns(), break_balance_at=3))
    assert v == "hold" and {"balance_break", "closing_mismatch"} <= c


def test_one_row_in_another_font() -> None:
    v, c = codes(bank_statement_pdf("A", "X1", 500000, txns(30), alt_font_row=4))
    assert v == "hold" and "font_mismatch" in c


def test_bad_and_duplicate_utrs() -> None:
    t = txns()
    t[1] = StatementTxn(
        t[1].txn_date,
        t[1].description,
        t[1].amount_paise,
        t[1].direction,
        "ABC12",
        t[1].vpa,
        t[1].name,
    )
    t[2] = StatementTxn(
        t[2].txn_date,
        t[2].description,
        t[2].amount_paise,
        t[2].direction,
        t[0].ref,
        t[2].vpa,
        t[2].name,
    )
    _, c = codes(bank_statement_pdf("A", "X1", 500000, t))
    assert {"utr_format", "duplicate_utr"} <= c


def test_incremental_update_detected() -> None:
    data = bank_statement_pdf("A", "X1", 500000, txns())
    appended = data + b"\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
    report = run_checks(appended, parse_statement(data))
    assert "incremental_update" in {s.code for s in report.signals}


def test_upload_tampered_statement_goes_on_hold(client: TestClient) -> None:
    h, biz = setup_business(client)
    data = bank_statement_pdf("A", "X1", 500000, txns(), producer="Sejda PDF", break_balance_at=2)
    r = client.post(
        f"/businesses/{biz}/statements",
        headers={**h, "Idempotency-Key": "tamper-1"},
        files={"file": ("s.pdf", data, "application/pdf")},
    ).json()
    assert r["status"] == "on_hold"
    assert r["meta"]["tamper"]["verdict"] == "hold"
