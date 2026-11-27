import pytest

from app.modules.trust.explain import explain

REASONS = {
    "positives": [
        {"code": "money_months", "params": {"months": 12, "source": "aa"}},
        {"code": "business_age", "params": {"years": 14}},
    ],
    "gaps": [
        {"code": "few_confirmations", "params": {"count": 0}},
        {"code": "no_ledger", "params": {}},
    ],
    "improve": [{"code": "ask_partners", "params": {"more": 3}}],
}
STRENGTHS = ["12 months of real payments", "running for 14 years", "12 महीने", "14 साल"]


@pytest.mark.parametrize("band", ["A", "B", "C"])
def test_strong_bands_explained_by_strengths(band: str) -> None:
    en = explain(band, "High", "final", REASONS, "en").headline
    assert en.startswith("Your passport is ") and " because 12 months of real payments" in en
    assert "क्योंकि" in explain(band, "High", "final", REASONS, "hi").headline


@pytest.mark.parametrize("band", ["D", "E", "U"])
def test_weak_bands_never_explained_by_strengths(band: str) -> None:
    for lang in ("en", "hi"):
        h = explain(band, "Low", "final", REASONS, lang).headline
        assert not any(s in h for s in STRENGTHS), h
        assert "because" not in h and "क्योंकि" not in h
    en = explain(band, "Low", "final", REASONS, "en").headline
    assert "only 0 trading partners have confirmed so far" in en
    assert "To raise it: ask 3 more suppliers" in en


def test_weak_band_exact_text() -> None:
    assert explain("D", "Medium", "final", REASONS, "en").headline == (
        "Your passport is weak: only 0 trading partners have confirmed so far. "
        "To raise it: ask 3 more suppliers or customers to confirm."
    )
    assert explain("U", "Low", "final", REASONS, "en").headline.startswith(
        "Your passport does not have enough evidence yet:"
    )


def test_weak_band_without_gaps_or_tips() -> None:
    assert explain("E", "Low", "final", {}, "en").headline == "Your passport is very weak."


def test_on_hold_wins() -> None:
    assert "on hold" in explain("A", "High", "on_hold", REASONS, "en").headline
