"""Ledger extraction accuracy on the golden set: field-level accuracy per provider and the exact
amount match rate. Golden pages live in eval/golden/<name>.(jpg|png) with <name>.json labels
(the LedgerExtraction schema). Until real pages are added, a sandbox set is generated."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.adapters.ai import AIProvider
from app.adapters.ai_schemas import LedgerExtraction
from app.adapters.errors import AdapterError
from app.adapters.sandbox_images import ledger_png

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "eval" / "golden"


@dataclass
class GoldenPage:
    name: str
    image: bytes
    mime: str
    label: LedgerExtraction
    synthetic: bool


def sandbox_golden(n: int = 10) -> list[GoldenPage]:
    pages = []
    for i in range(n):
        entries = [
            {
                "entry_date": f"2026-10-{(i + k) % 27 + 1:02d}",
                "party_text": ["Sharma ji", "Gupta", "राकेश", "Meena"][k % 4],
                "amount_paise": (500 + 137 * k + 61 * i) * 100,
                "direction": "in" if k % 3 else "out",
                "confidence": {"date": 0.9, "party": 0.9, "amount": 0.95, "direction": 0.9},
            }
            for k in range(6)
        ]
        label = {
            "entries": entries,
            "page_total_paise": None,
            "script": "devanagari",
            "page_confidence": 0.9,
        }
        pages.append(
            GoldenPage(
                f"sandbox-{i:02d}",
                ledger_png(label, noise=f"g{i}" * 20),
                "image/png",
                LedgerExtraction.model_validate(label),
                True,
            )
        )
    return pages


def load_golden() -> list[GoldenPage]:
    pages = []
    for label_file in sorted(GOLDEN_DIR.glob("*.json")):
        for ext, mime in ((".jpg", "image/jpeg"), (".jpeg", "image/jpeg"), (".png", "image/png")):
            img = label_file.with_suffix(ext)
            if img.exists():
                pages.append(
                    GoldenPage(
                        label_file.stem,
                        img.read_bytes(),
                        mime,
                        LedgerExtraction.model_validate(json.loads(label_file.read_text())),
                        False,
                    )
                )
                break
    return pages


@dataclass
class ExtractionScore:
    provider: str
    pages: int = 0
    failures: int = 0
    fields: dict[str, list[int]] = field(
        default_factory=lambda: {
            "date": [0, 0],
            "party": [0, 0],
            "amount": [0, 0],
            "direction": [0, 0],
        }
    )

    def accuracy(self) -> dict[str, float]:
        return {k: round(ok / n, 3) if n else 0.0 for k, (ok, n) in self.fields.items()}

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "pages": self.pages,
            "failures": self.failures,
            "field_accuracy": self.accuracy(),
            "exact_amount_match_rate": self.accuracy()["amount"],
        }


def _norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def score_provider(provider: AIProvider, pages: list[GoldenPage]) -> ExtractionScore:
    sc = ExtractionScore(provider.name)
    for p in pages:
        sc.pages += 1
        try:
            got = provider.extract_ledger(p.image, p.mime).entries
        except AdapterError:
            sc.failures += 1
            got = []
        for i, want in enumerate(p.label.entries):
            have = got[i] if i < len(got) else None
            checks = {
                "date": have is not None and have.entry_date == want.entry_date,
                "party": have is not None and _norm(have.party_text) == _norm(want.party_text),
                "amount": have is not None and have.amount_paise == want.amount_paise,
                "direction": have is not None and have.direction == want.direction,
            }
            for k, ok in checks.items():
                sc.fields[k][0] += int(ok)
                sc.fields[k][1] += 1
    return sc
