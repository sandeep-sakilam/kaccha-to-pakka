"""Trust engine rules: fixed, versioned, deterministic. No AI.

`compute(features)` is a pure function of a feature snapshot, so any past assessment can be
recomputed from its stored features and explained. Changing a rule means a new RULES_VERSION and
new assessments; old ones are never rewritten.
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

RULES_VERSION = "2026.11-r6"  # r6: Udyam / GSTIN checked against the register

PILLAR_WEIGHTS = {"money": 0.40, "records": 0.20, "network": 0.25, "presence": 0.15}
BANDS = [(80, "A"), (65, "B"), (50, "C"), (35, "D"), (0, "E")]
UNVERIFIED = "U"  # self-reported only / insufficient evidence
STALE_AFTER_DAYS = 120
VALID_FOR_DAYS = 60


@dataclass
class MoneyFeatures:
    source: str  # aa | pdf | none
    months_of_data: int = 0
    active_months: int = 0  # months with at least one inflow, last 12
    weekly_regularity: float = 0.0  # share of weeks with an inflow across the active span
    avg_monthly_inflow_paise: int = 0
    monthly_inflows: dict[str, int] = field(default_factory=dict)  # "YYYY-MM" -> paise
    days_since_last_txn: int | None = None
    netted_round_trip_paise: int = 0
    cash_deposit_paise: int = 0  # cash paid in at the bank, last 12 months (counted at half)
    cash_deposit_months: int = 0


@dataclass
class RecordsFeatures:
    counted_entries: int = 0
    independent_entries: int = 0
    match_rate: float = 0.0  # by value, independent ledgers only
    mirrored_ledgers: int = 0  # typed from the bank statement: counted once (as money)
    pending_confirmation: int = 0  # entries on added pages still waiting for the owner's yes
    cash_entries: int = 0  # written as cash: not checkable against the bank
    credit_entries: int = 0  # goods given on credit (udhaar)
    credit_customers: int = 0
    repeat_credit_customers: int = 0  # credit given in two or more different months
    credit_given_paise: int = 0
    credit_repaid_bank_paise: int = 0
    credit_repaid_cash_paise: int = 0  # as the owner wrote it
    credit_outstanding_paise: int = 0
    credit_bank_repaid_rate: float = 0.0  # repaid through the bank; partial clearing counts half
    median_days_to_repay: int | None = None
    owner_confirmed_share: float = 0.0  # of matched value, how much rests on the owner's answers
    daily_sales_days: int = 0  # days the owner told the day's sales, last 90 days
    daily_sales_months_checked: int = 0  # months with enough days told and bank data to compare
    daily_sales_months_agree: int = 0
    daily_sales_months_below_bank: int = 0
    daily_sales_months_far_above_bank: int = 0


@dataclass
class NetworkFeatures:
    confirmations: list[dict[str, Any]] = field(default_factory=list)  # weight, status, type
    rejected_confirmations: int = 0


@dataclass
class PresenceFeatures:
    business_age_years: float | None = None
    has_shop_front: bool = False
    checks_done: int = 0
    checks_failed: int = 0
    checks_missed: int = 0
    in_person_visits: int = 0
    registration: str = "none"  # none | verified | name_mismatch | cancelled | not_found | failed
    registration_source: str | None = None  # udyam | gstin


@dataclass
class Features:
    as_of: str
    money: MoneyFeatures
    records: RecordsFeatures
    network: NetworkFeatures
    presence: PresenceFeatures
    flags: list[dict[str, str]] = field(default_factory=list)  # code, severity, detail

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Features":
        return Features(
            as_of=d["as_of"],
            money=MoneyFeatures(**d["money"]),
            records=RecordsFeatures(**d["records"]),
            network=NetworkFeatures(**d["network"]),
            presence=PresenceFeatures(**d["presence"]),
            flags=list(d["flags"]),
        )


@dataclass
class Reason:
    code: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Result:
    band: str
    confidence: str
    status: str  # final | on_hold | stale
    combined: float
    pillars: dict[str, float]
    positives: list[Reason]
    gaps: list[Reason]
    improve: list[Reason]
    caps: list[str]
    flags: list[dict[str, str]]
    valid_days: int

    def reasons_dict(self) -> dict[str, Any]:
        return {
            "positives": [asdict(r) for r in self.positives],
            "gaps": [asdict(r) for r in self.gaps],
            "improve": [asdict(r) for r in self.improve],
            "caps": self.caps,
        }


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def freshness_factor(days: int | None) -> float:
    """Old evidence counts for less: full weight for 30 days, falling to 0.6 at 120 days."""
    if days is None:
        return 0.0
    if days <= 30:
        return 1.0
    if days >= STALE_AFTER_DAYS:
        return 0.6
    return round(1.0 - 0.4 * (days - 30) / (STALE_AFTER_DAYS - 30), 3)


def seasonal_stability(monthly: dict[str, int]) -> float:
    """0..1. With 13+ months, compare each month with the same month last year (a Diwali sweet
    shop is judged against last Diwali, not a flat average). With less history, only extreme
    swings count against it."""
    if not monthly:
        return 0.0
    pairs = []
    for ym, v in monthly.items():
        y, m = ym.split("-")
        prev = monthly.get(f"{int(y) - 1}-{m}")
        if prev:
            pairs.append(v / prev)
    if len(pairs) >= 3:
        return sum(1 for p in pairs if 0.5 <= p <= 2.0) / len(pairs)
    values = list(monthly.values())
    mean = sum(values) / len(values)
    if mean == 0:
        return 0.0
    cv = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values)) / mean
    return _clamp(1 - max(0.0, cv - 0.8) / 1.2, 0, 1)


def money_pillar(m: MoneyFeatures) -> float:
    if m.source == "none" or m.months_of_data == 0:
        return 0.0
    months = 40 * min(m.active_months, 12) / 12
    regular = 20 * _clamp(m.weekly_regularity, 0, 1)
    rupees = max(m.avg_monthly_inflow_paise / 100, 1)
    volume = 20 * _clamp((math.log10(rupees) - 4) / (math.log10(500_000) - 4), 0, 1)
    stable = 20 * seasonal_stability(m.monthly_inflows)
    return round(
        _clamp(months + regular + volume + stable) * freshness_factor(m.days_since_last_txn), 1
    )


RECORDS_CASH_CAP = 40.0
DAILY_SALES_BONUS = 5.0
DAILY_SALES_MIN_MONTHS = 2


def daily_sales_agree(r: RecordsFeatures) -> bool:
    """The owner's own daily totals agreed with the bank month after month, and never failed."""
    return (
        r.daily_sales_months_agree >= DAILY_SALES_MIN_MONTHS
        and r.daily_sales_months_below_bank == 0
        and r.daily_sales_months_far_above_bank == 0
    )


RECORDS_OWNER_CAP = 60.0
OWNER_SHARE_LIMIT = 0.5


def mostly_owner_confirmed(r: RecordsFeatures) -> bool:
    """Most of the matched value links ledger names to payers only because the owner said so."""
    return r.owner_confirmed_share > OWNER_SHARE_LIMIT


def mostly_cash(r: RecordsFeatures) -> bool:
    """More entries written as cash than entries the bank can check."""
    return r.cash_entries > r.independent_entries + r.credit_entries


def records_pillar(r: RecordsFeatures) -> float:
    """Cash-book entries found in the bank, and credit given that came back through the bank,
    weighted by how many entries each has. Cash cannot be checked, so a ledger that is mostly
    cash stays capped until more of it is backed by the bank."""
    parts: list[tuple[int, float]] = []
    if r.independent_entries:
        depth = min(1.0, r.independent_entries / 30)
        parts.append((r.independent_entries, 100 * r.match_rate * (0.5 + 0.5 * depth)))
    if r.credit_entries:
        depth = min(1.0, r.credit_entries / 30)
        parts.append((r.credit_entries, 100 * r.credit_bank_repaid_rate * (0.5 + 0.5 * depth)))
    if not parts and not daily_sales_agree(r):
        return 0.0
    score = sum(n * s for n, s in parts) / sum(n for n, _ in parts) if parts else 0.0
    if daily_sales_agree(r):
        score += DAILY_SALES_BONUS  # self-reported: a small, capped addition only
    if mostly_cash(r):
        score = min(score, RECORDS_CASH_CAP)
    if mostly_owner_confirmed(r):
        score = min(score, RECORDS_OWNER_CAP)
    return round(_clamp(score), 1)


def network_pillar(n: NetworkFeatures) -> float:
    good = sum(c["weight"] for c in n.confirmations if c["status"] == "confirmed")
    discrepancies = sum(1 for c in n.confirmations if c["status"] == "discrepancy")
    return round(_clamp(100 * good / 3 - 15 * discrepancies), 1)


REGISTRATION_POINTS = 10.0


def presence_pillar(p: PresenceFeatures) -> float:
    age = p.business_age_years
    score = 0.0 if age is None else 30 if age >= 5 else 22 if age >= 3 else 15 if age >= 1 else 5
    score += 15 if p.has_shop_front else 0
    answered = p.checks_done + p.checks_failed + p.checks_missed
    if answered:
        score += 40 * p.checks_done / answered
    score += 15 if p.in_person_visits else 0
    score += REGISTRATION_POINTS if p.registration == "verified" else 0
    return round(_clamp(score), 1)


def band_for(score: float) -> str:
    return next(b for threshold, b in BANDS if score >= threshold)


def _cap(band: str, best: str) -> str:
    order = "ABCDE"
    return band if order.index(band) >= order.index(best) else best


def compute(f: Features) -> Result:
    pillars = {
        "money": money_pillar(f.money),
        "records": records_pillar(f.records),
        "network": network_pillar(f.network),
        "presence": presence_pillar(f.presence),
    }
    combined = round(sum(pillars[k] * w for k, w in PILLAR_WEIGHTS.items()), 1)
    band = band_for(combined)
    caps: list[str] = []
    # No single pillar can carry the band.
    strong = sum(1 for v in pillars.values() if v >= 50)
    if band == "A" and strong < 4:
        band, caps = "B", [*caps, "a_needs_all_pillars"]
    if band in {"A", "B"} and strong < 3:
        band, caps = "C", [*caps, "b_needs_three_pillars"]
    if f.money.source != "aa":
        if _cap(band, "C") != band:
            caps.append("no_consented_bank_data_max_c")
        band = _cap(band, "C")
    verified_inputs = f.money.source != "none" or any(
        c["status"] == "confirmed" for c in f.network.confirmations
    )
    if not verified_inputs:
        band, caps = UNVERIFIED, [*caps, "self_reported_only"]

    if (
        f.money.months_of_data >= 9
        and f.money.source == "aa"
        and sum(1 for c in f.network.confirmations if c["status"] == "confirmed") >= 2
    ):
        confidence = "High"
    elif f.money.months_of_data >= 3:
        confidence = "Medium"
    else:
        confidence = "Low"
    if f.money.months_of_data < 3 and "under_3_months_low_confidence" not in caps:
        caps.append("under_3_months_low_confidence")

    status = "final"
    if any(fl["severity"] == "hold" for fl in f.flags):
        status = "on_hold"  # red flags pause, they don't subtract
    days = f.money.days_since_last_txn
    if f.money.source != "none" and days is not None and days >= STALE_AFTER_DAYS:
        status = "stale" if status == "final" else status
    valid_days = 0 if status == "stale" else VALID_FOR_DAYS
    if days is not None and status == "final":
        valid_days = max(0, min(VALID_FOR_DAYS, STALE_AFTER_DAYS - days))

    positives, gaps, improve = _reasons(f, pillars)
    return Result(
        band,
        confidence,
        status,
        combined,
        pillars,
        positives[:3],
        gaps[:3],
        improve[:3],
        caps,
        f.flags,
        valid_days,
    )


def _reasons(f: Features, p: dict[str, float]) -> tuple[list[Reason], list[Reason], list[Reason]]:
    pos: list[tuple[float, Reason]] = []
    gaps: list[tuple[float, Reason]] = []
    imp: list[tuple[float, Reason]] = []
    m, r, n, pr = f.money, f.records, f.network, f.presence
    confirmed = [c for c in n.confirmations if c["status"] == "confirmed"]
    if m.source != "none":
        pos.append(
            (p["money"], Reason("money_months", {"months": m.active_months, "source": m.source}))
        )
    else:
        gaps.append((100, Reason("no_money_data")))
        imp.append((100, Reason("link_bank")))
    if m.cash_deposit_months >= 3:
        pos.append(
            (p["money"] - 10, Reason("cash_sales_deposited", {"months": m.cash_deposit_months}))
        )
    if m.source == "pdf":
        gaps.append((60, Reason("pdf_only_capped")))
        imp.append((90, Reason("link_bank")))
    if r.independent_entries:
        reason = Reason("ledger_matches", {"percent": round(r.match_rate * 100)})
        (pos if r.match_rate >= 0.6 else gaps).append((p["records"], reason))
        if r.match_rate < 0.6:
            imp.append((50, Reason("record_payments_in_ledger")))
    elif r.pending_confirmation:
        gaps.append((40, Reason("ledger_unconfirmed")))
    elif not r.credit_entries:
        gaps.append((40, Reason("no_ledger")))
        imp.append((45, Reason("add_ledger")))
    if r.credit_entries:
        rate = r.credit_bank_repaid_rate
        reason = Reason(
            "credit_repaid_bank", {"percent": round(rate * 100), "customers": r.credit_customers}
        )
        (pos if rate >= 0.5 else gaps).append((p["records"], reason))
        if rate < 0.5:
            imp.append((50, Reason("ask_customers_upi")))
    if mostly_cash(r):
        gaps.append((45, Reason("mostly_cash_entries", {"count": r.cash_entries})))
        imp.append((55, Reason("ask_customers_upi")))
    if daily_sales_agree(r):
        pos.append((30, Reason("daily_sales_agree", {"months": r.daily_sales_months_agree})))
    if r.daily_sales_months_below_bank:
        gaps.append(
            (38, Reason("daily_sales_below_bank", {"months": r.daily_sales_months_below_bank}))
        )
    if r.daily_sales_months_far_above_bank:
        gaps.append(
            (
                38,
                Reason(
                    "daily_sales_far_above_bank", {"months": r.daily_sales_months_far_above_bank}
                ),
            )
        )
    if mostly_owner_confirmed(r):
        gaps.append(
            (
                42,
                Reason("matches_rest_on_owner", {"percent": round(r.owner_confirmed_share * 100)}),
            )
        )
        imp.append((48, Reason("write_full_names")))
    if r.pending_confirmation:
        imp.append((70, Reason("confirm_ledger_entries")))
    if r.mirrored_ledgers:
        gaps.append((30, Reason("ledger_copied_from_bank", {"count": r.mirrored_ledgers})))
    if confirmed:
        pos.append((p["network"], Reason("partners_confirmed", {"count": len(confirmed)})))
    if len(confirmed) < 3:
        gaps.append((55, Reason("few_confirmations", {"count": len(confirmed)})))
        imp.append((80 - 10 * len(confirmed), Reason("ask_partners", {"more": 3 - len(confirmed)})))
    if any(c["status"] == "discrepancy" for c in n.confirmations):
        gaps.append((50, Reason("confirmation_discrepancy")))
    if pr.business_age_years and pr.business_age_years >= 3:
        pos.append((p["presence"], Reason("business_age", {"years": int(pr.business_age_years)})))
    if pr.checks_done:
        pos.append((p["presence"] - 5, Reason("presence_checks", {"count": pr.checks_done})))
    if not pr.has_shop_front:
        imp.append((40, Reason("shop_photo")))
    source = {"udyam": "Udyam", "gstin": "GST"}.get(pr.registration_source or "", "")
    if pr.registration == "verified":
        pos.append((p["presence"] - 8, Reason("registration_verified", {"source": source})))
    elif pr.registration in {"not_found", "cancelled"}:
        gaps.append((36, Reason("registration_not_active", {"source": source})))
    elif pr.registration == "none":
        imp.append((25, Reason("add_registration")))
    if pr.checks_missed + pr.checks_failed:
        gaps.append((35, Reason("presence_missed", {"count": pr.checks_missed + pr.checks_failed})))
    if m.months_of_data and m.months_of_data < 3:
        gaps.append((70, Reason("under_3_months", {"months": m.months_of_data})))
    if m.days_since_last_txn is not None and m.days_since_last_txn > 30:
        gaps.append((45, Reason("money_data_old", {"days": m.days_since_last_txn})))
        imp.append((60, Reason("refresh_bank_data")))
    for fl in f.flags:
        if fl["severity"] == "hold":
            gaps.insert(0, (1000, Reason("on_hold", {"flag": fl["code"]})))

    def top(items: list[tuple[float, Reason]]) -> list[Reason]:
        seen: set[str] = set()
        out = []
        for _, reason in sorted(items, key=lambda x: -x[0]):
            if reason.code not in seen:
                seen.add(reason.code)
                out.append(reason)
        return out

    return top(pos), top(gaps), top(imp)


def as_of_date(f: Features) -> date:
    return date.fromisoformat(f.as_of)
