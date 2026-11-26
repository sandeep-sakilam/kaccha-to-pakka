"""Pure-rule tests: the band comes from fixed rules over a feature snapshot."""

from copy import deepcopy

from app.modules.trust.rules import (
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
    compute,
    freshness_factor,
    seasonal_stability,
)


def months(
    n: int, base: int = 30_000_000, season: dict[int, float] | None = None, start_year: int = 2025
) -> dict[str, int]:
    out = {}
    for i in range(n):
        y, m = start_year + (i // 12), i % 12 + 1
        out[f"{y}-{m:02d}"] = int(base * (season or {}).get(m, 1.0))
    return out


def strong() -> Features:
    return Features(
        as_of="2026-11-26",
        money=MoneyFeatures(
            source="aa",
            months_of_data=12,
            active_months=12,
            weekly_regularity=0.9,
            avg_monthly_inflow_paise=30_000_000,
            monthly_inflows=months(12),
            days_since_last_txn=5,
        ),
        records=RecordsFeatures(counted_entries=80, independent_entries=80, match_rate=0.82),
        network=NetworkFeatures(
            confirmations=[
                {"weight": 1.0, "status": "confirmed", "type": "penny_drop", "confirmer": f"c{i}"}
                for i in range(3)
            ]
        ),
        presence=PresenceFeatures(business_age_years=12, has_shop_front=True, checks_done=3),
    )


def test_strong_business_is_a_high() -> None:
    r = compute(strong())
    assert (r.band, r.confidence, r.status) == ("A", "High", "final")
    assert [x.code for x in r.positives][:1] == ["partners_confirmed"] or r.positives


def test_no_single_pillar_carries_the_band() -> None:
    f = strong()
    f.network = NetworkFeatures()
    f.records = RecordsFeatures()
    f.presence = PresenceFeatures()
    r = compute(f)
    assert r.band not in {"A", "B"}


def test_pdf_only_is_capped_at_c() -> None:
    f = strong()
    f.money.source = "pdf"
    r = compute(f)
    assert r.band == "C" and "no_consented_bank_data_max_c" in r.caps
    assert "link_bank" in [x.code for x in r.improve]


def test_self_reported_only_is_unverified() -> None:
    f = strong()
    f.money = MoneyFeatures(source="none")
    f.network = NetworkFeatures()
    r = compute(f)
    assert r.band == "U" and "self_reported_only" in r.caps


def test_under_three_months_is_low_confidence() -> None:
    f = strong()
    f.money.months_of_data = 2
    f.money.active_months = 2
    f.money.monthly_inflows = months(2)
    r = compute(f)
    assert r.confidence == "Low"


def test_red_flag_holds_and_does_not_subtract() -> None:
    f = strong()
    f.flags = [{"code": "tamper_signal", "severity": "hold", "detail": "x"}]
    r = compute(f)
    assert r.status == "on_hold" and r.band == compute(strong()).band
    assert r.gaps[0].code == "on_hold"


def test_seasonal_business_not_penalised() -> None:
    wedding = {11: 4.0, 12: 4.0, 1: 3.0, 2: 3.0, 6: 0.3, 7: 0.3}
    flat_cv_bad = months(12, season=wedding)
    yoy = months(24, season=wedding)
    assert seasonal_stability(yoy) == 1.0  # same pattern as last year
    assert seasonal_stability(flat_cv_bad) >= 0.8  # one year of seasons: not penalised
    erratic = {**months(12, base=1_000_000), "2025-05": 100_000_000}
    assert seasonal_stability(erratic) < 0.5
    swing = months(24, season=wedding)
    swing["2026-11"] = swing["2025-11"] // 5  # this Diwali far below last Diwali
    swing["2026-12"] = swing["2025-12"] // 5
    swing["2026-01"] = swing["2025-01"] // 5
    assert seasonal_stability(swing) < 1.0
    f = strong()
    f.money.monthly_inflows = yoy
    assert compute(f).band == "A"


def test_freshness_and_stale() -> None:
    assert freshness_factor(10) == 1.0 and freshness_factor(120) == 0.6
    assert 0.6 < freshness_factor(75) < 1.0
    f = strong()
    f.money.days_since_last_txn = 130
    r = compute(f)
    assert r.status == "stale" and r.valid_days == 0


def test_discrepancy_lowers_network() -> None:
    f = strong()
    g = deepcopy(f)
    g.network.confirmations[0]["status"] = "discrepancy"
    assert compute(g).pillars["network"] < compute(f).pillars["network"]


def test_deterministic() -> None:
    a, b = compute(strong()), compute(Features.from_dict(strong().as_dict()))
    assert a.band == b.band and a.pillars == b.pillars and a.combined == b.combined
