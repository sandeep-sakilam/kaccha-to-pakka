"""Gather a trust feature snapshot from the database. Evidence from the same origin counts once:
a ledger typed from the bank statement is money data, not an independent record."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.models import (
    Attestation,
    BankTransaction,
    Business,
    CounterpartyInvite,
    Dispute,
    EvidenceItem,
    LedgerEntry,
    PresenceRequest,
    ReconMatch,
    User,
)
from app.modules.fraud.graph import active_flags, confirmer_standing
from app.modules.reconciliation.engine import COUNTABLE_LEDGER, reconcile
from app.modules.reconciliation.names import similarity
from app.modules.sales import service as sales
from app.modules.statements.money import is_cash_deposit
from app.modules.trust.rules import (
    Features,
    MoneyFeatures,
    NetworkFeatures,
    PresenceFeatures,
    RecordsFeatures,
)

MONEY_TYPES = {"aa_fetch", "bank_statement", "upi_statement"}
ROUND_TRIP_DAYS = 7
ROUND_TRIP_TOLERANCE = 0.02
MIRROR_THRESHOLD = 0.95
MIRROR_MIN_ENTRIES = 10


def _ym(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def round_trips(txns: list[BankTransaction]) -> tuple[int, int, set[str]]:
    """Money sent out and back (A→B→A) within days. Returns (pairs, netted paise, txn ids)."""
    by_cp: dict[str, list[BankTransaction]] = defaultdict(list)
    for t in txns:
        if t.counterparty_vpa:
            by_cp[t.counterparty_vpa].append(t)
    pairs = netted = 0
    used: set[str] = set()
    for rows in by_cp.values():
        rows.sort(key=lambda t: t.txn_date)
        for i, a in enumerate(rows):
            if a.id in used:
                continue
            for b in rows[i + 1 :]:
                if (b.txn_date - a.txn_date).days > ROUND_TRIP_DAYS:
                    break
                if b.id in used or b.direction == a.direction:
                    continue
                if abs(a.amount_paise - b.amount_paise) <= a.amount_paise * ROUND_TRIP_TOLERANCE:
                    used |= {a.id, b.id}
                    pairs += 1
                    netted += min(a.amount_paise, b.amount_paise)
                    break
    return pairs, netted, used


def gather(db: Session, biz: Business, today: date | None = None) -> Features:
    today = today or date.today()
    flags: list[dict[str, str]] = []
    evidence = list(
        db.execute(select(EvidenceItem).where(EvidenceItem.business_id == biz.id)).scalars()
    )

    # ---- money
    money_ev = [e for e in evidence if e.type in MONEY_TYPES]
    good_money = {e.id: e for e in money_ev if e.status not in {"on_hold", "rejected"}}
    for e in money_ev:
        if e.status == "on_hold":
            flags.append(
                {
                    "code": "tamper_signal",
                    "severity": "hold",
                    "detail": f"statement {e.id[:8]} failed tamper checks",
                }
            )
    txns = list(
        db.execute(
            select(BankTransaction).where(BankTransaction.evidence_id.in_(list(good_money) or [""]))
        ).scalars()
    )
    source = "none"
    if any(e.type == "aa_fetch" for e in good_money.values()):
        source = "aa"
    elif good_money:
        source = "pdf"
    pairs, netted, rt_ids = round_trips(txns)
    if pairs >= 3:
        flags.append(
            {
                "code": "round_tripping",
                "severity": "hold",
                "detail": f"{pairs} payments sent out and back within a week",
            }
        )
    since12 = today - timedelta(days=365)
    since24 = today - timedelta(days=730)
    inflows = [t for t in txns if t.direction == "in" and t.id not in rt_ids]
    # Cash deposited at the bank counts as sales, at half weight: where the cash came from is
    # not known (it could be borrowed and deposited to look bigger).
    cash_ids = {t.id for t in inflows if is_cash_deposit(t)}

    def weighted(t: BankTransaction) -> int:
        return t.amount_paise // 2 if t.id in cash_ids else t.amount_paise

    monthly: dict[str, int] = defaultdict(int)
    for t in inflows:
        if t.txn_date >= since24:
            monthly[_ym(t.txn_date)] += weighted(t)
    recent = [t for t in inflows if t.txn_date >= since12]
    active_months = len({_ym(t.txn_date) for t in recent})
    all_recent = [t for t in txns if t.txn_date >= since24]
    months_of_data = 0
    weekly = 0.0
    if all_recent:
        first = min(t.txn_date for t in all_recent)
        last = max(t.txn_date for t in all_recent)
        months_of_data = min(24, (last.year - first.year) * 12 + last.month - first.month + 1)
        weeks_span = max(1, ((last - max(first, since12)).days // 7) + 1)
        weeks = {(t.txn_date.isocalendar()[0], t.txn_date.isocalendar()[1]) for t in recent}
        weekly = min(1.0, len(weeks) / weeks_span)
    last_txn = max((t.txn_date for t in txns), default=None)
    money = MoneyFeatures(
        source=source,
        months_of_data=months_of_data,
        active_months=active_months,
        weekly_regularity=round(weekly, 3),
        avg_monthly_inflow_paise=sum(weighted(t) for t in recent) // max(active_months, 1),
        monthly_inflows=dict(sorted(monthly.items())),
        days_since_last_txn=(today - last_txn).days if last_txn else None,
        netted_round_trip_paise=netted,
        cash_deposit_paise=sum(t.amount_paise for t in recent if t.id in cash_ids),
        cash_deposit_months=len({_ym(t.txn_date) for t in recent if t.id in cash_ids}),
    )

    owner = db.get(User, biz.owner_user_id)
    if biz.registration_status == "name_mismatch":
        flags.append(
            {
                "code": "registration_name_mismatch",
                "severity": "hold",
                "detail": "the Udyam / GST number is registered to a different business",
            }
        )
    elif biz.registration_status == "cancelled":
        flags.append(
            {
                "code": "registration_cancelled",
                "severity": "warn",
                "detail": "the Udyam / GST registration is cancelled",
            }
        )
    if owner is not None and owner.kyc_status == "name_mismatch":
        flags.append(
            {
                "code": "kyc_name_mismatch",
                "severity": "hold",
                "detail": "the PAN belongs to a different name than the owner gave",
            }
        )
    if owner is not None and owner.name:
        for e in good_money.values():
            holder = e.meta.get("holder_name")
            if (
                e.type == "aa_fetch"
                and holder
                and holder != "SANDBOX HOLDER"
                and similarity(holder, owner.name) < 60
            ):
                flags.append(
                    {
                        "code": "holder_name_mismatch",
                        "severity": "hold",
                        "detail": "bank account holder name differs from the owner",
                    }
                )
                break

    # ---- records (reconcile first, deterministic)
    stats = reconcile(db, biz.id)
    ledger_ev = [
        e for e in evidence if e.type in {"ledger_page", "bill", "voice_entry", "ledger_export"}
    ]
    mirrored: set[str] = set()
    for e in ledger_ev:
        rows = db.execute(
            select(LedgerEntry, ReconMatch, BankTransaction)
            .outerjoin(
                ReconMatch,
                (ReconMatch.ledger_entry_id == LedgerEntry.id) & (ReconMatch.status == "matched"),
            )
            .outerjoin(BankTransaction, ReconMatch.bank_txn_id == BankTransaction.id)
            .where(
                LedgerEntry.evidence_id == e.id,
                LedgerEntry.status.in_(COUNTABLE_LEDGER),
                LedgerEntry.kind == "money",
            )
        ).all()
        if len(rows) < MIRROR_MIN_ENTRIES:
            continue
        same_day = sum(1 for le, _, bt in rows if bt is not None and bt.txn_date == le.entry_date)
        if same_day / len(rows) >= MIRROR_THRESHOLD:
            mirrored.add(e.id)
    independent = list(
        db.execute(
            select(LedgerEntry).where(
                LedgerEntry.evidence_id.in_(
                    [e.id for e in ledger_ev if e.id not in mirrored] or [""]
                ),
                LedgerEntry.status.in_(COUNTABLE_LEDGER),
                # Only money the bank could show: credit given moved no money; cash is not banked.
                LedgerEntry.kind == "money",
                (LedgerEntry.paid_by.is_(None)) | (LedgerEntry.paid_by != "cash"),
            )
        ).scalars()
    )
    ind_ids = {le.id for le in independent}
    match_rules = {
        lid: rule
        for lid, rule in db.execute(
            select(ReconMatch.ledger_entry_id, ReconMatch.rule).where(
                ReconMatch.ledger_entry_id.in_(ind_ids or {""}), ReconMatch.status == "matched"
            )
        ).all()
    }
    matched_ids = set(match_rules)
    ind_value = sum(le.amount_paise for le in independent)
    matched_value = sum(le.amount_paise for le in independent if le.id in matched_ids)
    owner_value = sum(
        le.amount_paise for le in independent if match_rules.get(le.id) == "owner_confirmed"
    )
    credit = stats.credit
    told = sales.check(db, biz.id, inflows, today)
    records = RecordsFeatures(
        counted_entries=stats.ledger_entries + stats.cash_entries + credit.entries,
        independent_entries=len(independent),
        match_rate=round(matched_value / ind_value, 4) if ind_value else 0,
        mirrored_ledgers=len(mirrored),
        owner_confirmed_share=round(owner_value / matched_value, 4) if matched_value else 0.0,
        pending_confirmation=len(
            db.execute(
                select(LedgerEntry.id).where(
                    LedgerEntry.evidence_id.in_([e.id for e in ledger_ev] or [""]),
                    LedgerEntry.confirmed_by_owner.is_(None),
                    LedgerEntry.status.in_(["needs_readback", "on_review"]),
                )
            ).all()
        ),
        cash_entries=stats.cash_entries,
        credit_entries=credit.entries,
        credit_customers=credit.customers,
        repeat_credit_customers=credit.repeat_customers,
        credit_given_paise=credit.given_paise,
        credit_repaid_bank_paise=credit.repaid_bank_paise,
        credit_repaid_cash_paise=credit.repaid_cash_paise,
        credit_outstanding_paise=credit.outstanding_paise,
        credit_bank_repaid_rate=round(credit.bank_repaid_rate, 4),
        median_days_to_repay=credit.median_days_to_repay,
        daily_sales_days=told.days_told,
        daily_sales_months_checked=told.months_checked,
        daily_sales_months_agree=told.months_agree,
        daily_sales_months_below_bank=told.months_below_bank,
        daily_sales_months_far_above_bank=told.months_far_above_bank,
    )

    # ---- network
    now = utcnow()
    confirmations = []
    for a in db.execute(
        select(Attestation).where(Attestation.subject_business_id == biz.id)
    ).scalars():
        if a.expires_at and a.expires_at < now:
            continue
        if a.status not in {"confirmed", "discrepancy"}:
            continue
        standing = confirmer_standing(db, a.confirmer_business_id)
        confirmations.append(
            {
                "weight": round(a.weight * standing, 3),
                "standing": standing,
                "status": a.status,
                "type": a.evidence_type,
                "confirmer": a.confirmer_business_id or "in_person",
            }
        )
    rejected = list(
        db.execute(
            select(CounterpartyInvite).where(
                CounterpartyInvite.business_id == biz.id, CounterpartyInvite.status == "rejected"
            )
        ).scalars()
    )
    cleared = {
        d.target_id
        for d in db.execute(
            select(Dispute).where(
                Dispute.business_id == biz.id,
                Dispute.target_type == "invite",
                Dispute.status == "resolved",
                Dispute.resolution == "cleared",
            )
        ).scalars()
    }
    open_rejections = [i for i in rejected if i.id not in cleared]
    if open_rejections:
        flags.append(
            {
                "code": "failed_confirmation",
                "severity": "hold",
                "detail": f"{len(open_rejections)} confirmation(s) came from the wrong account",
            }
        )
    if any(
        "same_phone_multiple_partners" in (i.flags or [])
        for i in db.execute(
            select(CounterpartyInvite).where(CounterpartyInvite.business_id == biz.id)
        ).scalars()
    ):
        flags.append(
            {
                "code": "same_phone_multiple_partners",
                "severity": "warn",
                "detail": "one phone number was given for several partners",
            }
        )
    for gf in active_flags(db, biz.id):
        detail = (
            "money went round in a circle between businesses"
            if gf.code == "payment_cycle"
            else "new businesses confirming only each other"
        )
        flags.append({"code": gf.code, "severity": "hold", "detail": detail})
    network = NetworkFeatures(confirmations=confirmations, rejected_confirmations=len(rejected))

    # ---- shop location vs UPI merchant location (where a provider supplies it)
    if biz.geo_home and biz.merchant_geo:
        from app.modules.presence.service import MERCHANT_FAR_M, MERCHANT_NEAR_M, haversine_m

        apart = haversine_m(biz.geo_home, biz.merchant_geo)
        if apart > MERCHANT_FAR_M:
            flags.append(
                {
                    "code": "shop_far_from_merchant_location",
                    "severity": "hold",
                    "detail": f"shop photos are {apart / 1000:.1f} km from the UPI "
                    "merchant location",
                }
            )
        elif apart > MERCHANT_NEAR_M:
            flags.append(
                {
                    "code": "shop_near_but_not_at_merchant_location",
                    "severity": "warn",
                    "detail": f"shop photos are {apart:.0f} m from the UPI merchant location",
                }
            )

    # ---- presence
    reqs = list(
        db.execute(select(PresenceRequest).where(PresenceRequest.business_id == biz.id)).scalars()
    )
    age = None
    if biz.started_on:
        age = round((today - biz.started_on).days / 365.25, 1)
    presence = PresenceFeatures(
        business_age_years=age,
        has_shop_front=any(e.type == "shop_front" and e.status != "duplicate" for e in evidence),
        checks_done=sum(1 for r in reqs if r.status == "done"),
        checks_failed=sum(1 for r in reqs if r.status == "failed"),
        checks_missed=sum(1 for r in reqs if r.status == "missed"),
        in_person_visits=sum(1 for c in confirmations if c["type"] == "in_person"),
        registration=biz.registration_status or "none",
        registration_source=biz.registration_source,
    )
    return Features(
        as_of=today.isoformat(),
        money=money,
        records=records,
        network=network,
        presence=presence,
        flags=flags,
    )


def model_versions(db: Session, biz: Business) -> dict[str, str]:
    versions: dict[str, str] = {}
    for e in db.execute(select(EvidenceItem).where(EvidenceItem.business_id == biz.id)).scalars():
        ex = e.meta.get("extraction") or {}
        if ex.get("provider") and ex.get("model"):
            versions[f"extraction:{ex['provider']}"] = str(ex["model"])
    return dict(sorted(versions.items()))
