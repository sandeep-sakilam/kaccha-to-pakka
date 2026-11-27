"""Evaluation harness: runs every benchmark and writes eval/report.md and eval/report.json.
The deck's Performance slide is filled from this report, never from estimates."""

import json
import random
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.db.models import ReconMatch
from app.evaluation import builders as b
from app.evaluation import extraction_eval, redteam
from app.evaluation.metrics import PrecisionRecall, wer
from app.modules.reconciliation.engine import questions as engine_questions
from app.modules.reconciliation.engine import reconcile
from app.modules.trust import service as trust

OUT_DIR = Path(__file__).resolve().parents[2] / "eval"
AI_COST_RUPEES = {"vision": 1.20, "stt": 0.30, "tts": 0.15, "llm": 0.25}  # per call, estimate
TODAY = date.today()


def reconciliation_eval(db: Session, businesses: int = 10, seed: int = 7) -> dict[str, Any]:
    """Synthetic statements with matching ledgers (incl. Hindi names, ±3-day dates, cash
    entries and decoys). Ground truth is known, so precision and recall are exact."""
    rng = random.Random(seed)  # noqa: S311
    pr = PrecisionRecall()
    questions = 0
    names = [
        ("Sharma ji", "RAKESH SHARMA"),
        ("गुप्ता", "GUPTA TRADERS"),
        ("Meena", "MEENA DEVI"),
        ("Pappu", "PRADEEP KUMAR"),
        ("Jain sa", "JAIN CLOTH HOUSE"),
    ]
    for n in range(businesses):
        biz = b.business(db, f"Recon Eval {n}")
        bank = b.evidence(db, biz, "aa_fetch", "aa:mock")
        led = b.evidence(db, biz, "ledger_page", "camera", "extracted")
        truth: dict[str, int] = {}
        money_rows, ledger_rows = [], []
        for k in range(30):
            day = TODAY - timedelta(days=rng.randint(5, 150))
            amt = rng.randint(500, 9000) * 100 + rng.choice([0, 50])
            party, bank_name = rng.choice(names)
            d = rng.choice(["in", "out"])
            money_rows.append((day, amt, d, f"vpa{k}@ok", bank_name))
            if k % 5 != 0:  # most payments are in the ledger
                ledger_rows.append((day + timedelta(days=rng.randint(-2, 2)), party, amt, d))
                truth[f"{len(ledger_rows) - 1}"] = k
        for _ in range(6):  # cash entries with no bank match
            ledger_rows.append(
                (
                    TODAY - timedelta(days=rng.randint(5, 150)),
                    "Nagad",
                    rng.randint(50, 400) * 100,
                    "in",
                )
            )
        b.money(db, bank, money_rows)
        entries = b.ledger(db, led, ledger_rows)
        reconcile(db, biz.id)
        matched = {
            m.ledger_entry_id: m.bank_txn_id
            for m in db.execute(
                select(ReconMatch).where(
                    ReconMatch.ledger_entry_id.in_([e.id for e in entries]),
                    ReconMatch.status == "matched",
                )
            ).scalars()
        }
        vpa_of = {t.id: t.counterparty_vpa for t in bank_txns(db, bank.id)}
        for idx, e in enumerate(entries):
            want = truth.get(str(idx))
            got = matched.get(e.id)
            got_k = int(str(vpa_of[got])[3:].split("@")[0]) if got else None
            if want is not None and got_k == want:
                pr.tp += 1
            elif got is not None:
                pr.fp += 1
                if want is not None:
                    pr.fn += 1
            elif want is not None:
                pr.fn += 1
        questions += len(engine_questions(db, biz.id))
    return {
        "businesses": businesses,
        "precision": round(pr.precision, 3),
        "recall": round(pr.recall, 3),
        "tp": pr.tp,
        "fp": pr.fp,
        "fn": pr.fn,
        "owner_questions": questions,
        "note": "unmatched pairs with unclear names become owner questions, not guesses",
    }


def bank_txns(db: Session, evidence_id: str) -> list[Any]:
    from app.db.models import BankTransaction

    return list(
        db.execute(
            select(BankTransaction)
            .where(BankTransaction.evidence_id == evidence_id)
            .order_by(BankTransaction.created_at, BankTransaction.id)
        ).scalars()
    )


def band_distribution(db: Session) -> dict[str, Any]:
    """Synthetic businesses across type, season and owner gender; same evidence strength, so a
    fair engine gives similar bands."""
    profiles = [
        ("kirana", {}, "male"),
        ("kirana", {}, "female"),
        ("namkeen", {10: 3.0, 11: 3.5, 4: 0.6}, "female"),
        ("tailor", {11: 2.2, 12: 2.4, 6: 0.5}, "male"),
        ("tailor", {11: 2.2, 12: 2.4, 6: 0.5}, "female"),
        ("vegetables", {}, "male"),
    ]
    out: dict[str, Counter[str]] = defaultdict(Counter)
    for i, (cat, season, gender) in enumerate(profiles * 2):
        biz = b.business(db, f"Fair {i}", category=cat, gender=gender, started=date(2016, 1, 1))
        ev = b.evidence(db, biz, "aa_fetch", "aa:mock")
        rows = []
        for d in range(2, 395, 2):
            day = TODAY - timedelta(days=d)
            rows.append(
                (
                    day,
                    int(200_000 * season.get(day.month, 1.0)),
                    "in",
                    f"c{d % 11}@ok",
                    f"C{d % 11}",
                )
            )
        b.money(db, ev, rows)
        a = trust.assess(db, biz)
        out[f"category:{cat}"][a.band] += 1
        out[f"gender:{gender}"][a.band] += 1
        out[f"seasonal:{bool(season)}"][a.band] += 1
    return {k: dict(v) for k, v in out.items()}


def ai_cost_per_passport(pages: int = 6, voice_answers: int = 4) -> dict[str, Any]:
    calls = {"vision": pages, "stt": voice_answers + 2, "tts": 8, "llm": 2}
    cost = sum(AI_COST_RUPEES[k] * v for k, v in calls.items())
    return {
        "calls": calls,
        "rupees_per_passport": round(cost, 2),
        "note": "per-call prices are estimates in AI_COST_RUPEES; replace with invoice data",
    }


def stt_wer() -> dict[str, Any]:
    path = OUT_DIR / "golden" / "transcripts.json"
    if not path.exists():
        return {"status": "not run: add eval/golden/transcripts.json with audio files"}
    items = json.loads(path.read_text())
    ai = get_adapters().ai
    scores = []
    for it in items:
        audio = (OUT_DIR / "golden" / it["audio"]).read_bytes()
        hyp = ai.transcribe(audio, it.get("language", "hi")).value.text
        scores.append(wer(it["text"], hyp))
    return {"items": len(scores), "wer": round(sum(scores) / len(scores), 3) if scores else None}


def credit_book_eval(db: Session, businesses: int = 10, seed: int = 11) -> dict[str, Any]:
    """Synthetic credit books (udhaar). Each customer gets monthly credit and pays back in one of
    the ways real customers do: on time, two months together and late, part payment, in cash
    (written, never in the bank) or not at all. Decoys: a larger spot purchase paid by UPI by the
    same customer, and an unrelated payer sending the exact amount. Ground truth is known, so
    precision and recall of repayments found in the bank are exact."""
    rng = random.Random(seed)  # noqa: S311
    pr = PrecisionRecall()
    patterns: Counter[str] = Counter()
    customers = [
        ("Sharma ji", "RAKESH SHARMA"),
        ("गुप्ता जी", "RAJESH GUPTA"),
        ("Meena ben", "MEENA PATEL"),
        ("Jain sa", "ANIL JAIN"),
        ("Verma ji", "SURESH VERMA"),
        ("Khan bhai", "IMRAN KHAN"),
    ]
    for n in range(businesses):
        biz = b.business(db, f"Credit Eval {n}")
        bank = b.evidence(db, biz, "aa_fetch", "aa:mock")
        led = b.evidence(db, biz, "ledger_page", "camera", "extracted")
        ledger_rows: list[tuple[Any, ...]] = []
        money_rows: list[tuple[Any, ...]] = []
        truth: set[str] = set()  # VPAs of real repayments
        start = TODAY - timedelta(days=150)
        for c, (party, bank_name) in enumerate(customers):
            pattern = rng.choice(["on_time", "two_together", "partial", "cash", "unpaid"])
            patterns[pattern] += 1
            dues = []
            for month in range(3):
                day = start + timedelta(days=30 * month + rng.randint(0, 5))
                amt = rng.randint(3, 20) * 10_000
                dues.append((day, amt))
                ledger_rows.append((day, party, amt, "credit"))
            vpa = f"cust{n}x{c}"
            if pattern == "on_time":
                for k, (day, amt) in enumerate(dues):
                    money_rows.append(
                        (day + timedelta(days=30), amt, "in", f"{vpa}r{k}@ybl", bank_name)
                    )
                    truth.add(f"{vpa}r{k}@ybl")
            elif pattern == "two_together":
                (d1, a1), (_, a2), (d3, a3) = dues
                money_rows.append(
                    (d1 + timedelta(days=62), a1 + a2, "in", f"{vpa}r0@ybl", bank_name)
                )
                money_rows.append((d3 + timedelta(days=40), a3, "in", f"{vpa}r1@ybl", bank_name))
                truth |= {f"{vpa}r0@ybl", f"{vpa}r1@ybl"}
            elif pattern == "partial":
                d1, a1 = dues[0]
                money_rows.append(
                    (d1 + timedelta(days=25), a1 // 2, "in", f"{vpa}r0@ybl", bank_name)
                )
                truth.add(f"{vpa}r0@ybl")
            elif pattern == "cash":
                for day, amt in dues:
                    ledger_rows.append((day + timedelta(days=28), party, amt, "in", "cash"))
            # decoy: a spot purchase by UPI, larger than everything the customer owes
            big = sum(a for _, a in dues) + 50_000
            money_rows.append((start + timedelta(days=70), big, "in", f"{vpa}spot@ybl", bank_name))
            # decoy: an unrelated payer sends the exact amount of a due
            money_rows.append(
                (dues[1][0] + timedelta(days=20), dues[1][1], "in", f"{vpa}x@okaxis", "MOHAN DAS")
            )
            # hard decoy, every third customer: a small spot purchase by UPI while still owing.
            # The rules cannot tell it from a part payment, so it shows up as a false positive.
            if c % 3 == 0:
                money_rows.append(
                    (dues[0][0] + timedelta(days=3), 5_000, "in", f"{vpa}small@ybl", bank_name)
                )
        b.money(db, bank, money_rows)
        entries = b.ledger(db, led, ledger_rows)
        reconcile(db, biz.id)
        vpa_of = {t.id: t.counterparty_vpa for t in bank_txns(db, bank.id)}
        found = {
            str(vpa_of[m.bank_txn_id])
            for m in db.execute(
                select(ReconMatch).where(
                    ReconMatch.ledger_entry_id.in_([e.id for e in entries]),
                    ReconMatch.rule.in_(["credit_repaid", "credit_repaid_partial"]),
                )
            ).scalars()
        }
        pr.tp += len(found & truth)
        pr.fp += len(found - truth)
        pr.fn += len(truth - found)
    return {
        "businesses": businesses,
        "customers": businesses * len(customers),
        "patterns": dict(sorted(patterns.items())),
        "precision": round(pr.precision, 3),
        "recall": round(pr.recall, 3),
        "tp": pr.tp,
        "fp": pr.fp,
        "fn": pr.fn,
        "note": "repayments found in the bank; cash repayments are counted as written, not found",
    }


def run(db: Session) -> dict[str, Any]:
    golden = extraction_eval.load_golden()
    real = bool(golden)
    pages = golden or extraction_eval.sandbox_golden()
    ai = get_adapters().ai
    providers = [p for p in (ai.primary, ai.fallback) if p is not None]
    extraction = [extraction_eval.score_provider(p, pages).as_dict() for p in providers]
    red = redteam.run(db)
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sandbox": ai.sandbox,
        "golden_set": {"pages": len(pages), "real_pages": real},
        "extraction": extraction,
        "reconciliation": reconciliation_eval(db),
        "credit_book": credit_book_eval(db),
        "red_team": {
            "cases": len(red),
            "caught": sum(r.caught for r in red),
            "catch_rate": round(sum(r.caught for r in red) / len(red), 3),
            "results": [asdict(r) for r in red],
        },
        "stt": stt_wer(),
        "ai_cost": ai_cost_per_passport(),
        "band_distribution": band_distribution(db),
        "not_measured_here": [
            "time from first message to first passport (needs field sessions)",
            "unaided completion with 5 shopkeepers",
        ],
    }
    return report


def to_markdown(r: dict[str, Any]) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Generated {r['generated_at']}"
        + (
            " · **Sandbox models**: numbers show the harness works, not real accuracy."
            if r["sandbox"]
            else ""
        ),
        "",
    ]
    g = r["golden_set"]
    lines += [
        "## Ledger extraction",
        "",
        f"Golden set: {g['pages']} pages ({'real' if g['real_pages'] else 'synthetic sandbox'})",
        "",
        "| Provider | Date | Party | Amount (exact) | Direction | Failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for e in r["extraction"]:
        a = e["field_accuracy"]
        lines.append(
            f"| {e['provider']} | {a['date']} | {a['party']} | {a['amount']} | "
            f"{a['direction']} | {e['failures']} |"
        )
    rc = r["reconciliation"]
    lines += [
        "",
        "## Reconciliation",
        "",
        f"Precision {rc['precision']}, recall "
        f"{rc['recall']} over {rc['businesses']} synthetic businesses "
        f"(tp {rc['tp']}, fp {rc['fp']}, fn {rc['fn']}); {rc.get('owner_questions', 0)} "
        "unclear names sent to the owner as questions.",
        "",
        "## Credit books (udhaar)",
        "",
        f"Repayments found in the bank: precision {r['credit_book']['precision']}, recall "
        f"{r['credit_book']['recall']} over {r['credit_book']['customers']} synthetic customers "
        f"(tp {r['credit_book']['tp']}, fp {r['credit_book']['fp']}, fn "
        f"{r['credit_book']['fn']}). Patterns: "
        + ", ".join(f"{k} {v}" for k, v in r["credit_book"]["patterns"].items())
        + ".",
        "",
        "## Red-team",
        "",
        f"Catch rate **{r['red_team']['caught']}/{r['red_team']['cases']}** "
        f"({r['red_team']['catch_rate']:.0%})",
        "",
        "| Attack | Defence | Caught |",
        "| --- | --- | --- |",
    ]
    for c in r["red_team"]["results"]:
        lines.append(f"| {c['attack']} | {c['defence']} | {'yes' if c['caught'] else 'NO'} |")
    lines += [
        "",
        "## Speech to text",
        "",
        str(r["stt"]),
        "",
        "## AI cost per passport",
        "",
        f"₹{r['ai_cost']['rupees_per_passport']} ({r['ai_cost']['note']})",
        "",
        "## Band distribution (same evidence strength)",
        "",
    ]
    for k, v in sorted(r["band_distribution"].items()):
        lines.append(f"- {k}: {v}")
    lines += ["", "Not measured by the harness: " + "; ".join(r["not_measured_here"]), ""]
    return "\n".join(lines)


def write(report: dict[str, Any]) -> tuple[Path, Path]:
    OUT_DIR.mkdir(exist_ok=True)
    j, m = OUT_DIR / "report.json", OUT_DIR / "report.md"
    j.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    m.write_text(to_markdown(report))
    return j, m
