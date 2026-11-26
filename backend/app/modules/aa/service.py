"""Account Aggregator: consented bank data straight from the bank (cannot be edited by anyone).

Our own consent row (purpose aa_fetch, scope holds the AA consent handle) is created first; the
owner then approves in their AA app. A monthly refresh runs while `monthly_refresh` is active.
"""

import contextlib
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.errors import DomainError, NotFound
from app.db.base import utcnow
from app.db.models import Business, Consent, EvidenceItem, User
from app.jobs import RetryableJobError, job
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.statements.money import MoneyTxn, store_transactions

MONTHS = 12
REFRESH_EVERY = timedelta(days=30)


def start(db: Session, user: User, biz: Business, monthly_refresh: bool = True) -> Consent:
    consent.require(db, biz.owner_user_id, "build_passport", biz.id)
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    try:
        handle = get_adapters().aa.create_consent(owner.phone, MONTHS, "Business Trust Passport")
    except AdapterError as exc:
        raise DomainError(
            "Bank linking is not working right now. You can add a statement PDF instead.",
            "aa_down",
            503,
        ) from exc
    c = consent.grant(
        db,
        owner,
        "aa_fetch",
        biz.id,
        {"aa_handle": handle.handle, "months": MONTHS, "provider": get_adapters().aa.name},
    )
    if monthly_refresh:
        consent.grant(db, owner, "monthly_refresh", biz.id, {"aa_handle": handle.handle})
    c.scope = {**c.scope, "redirect_url": handle.redirect_url}
    return c


def _aa_consent(db: Session, biz: Business, consent_id: str) -> Consent:
    c = db.get(Consent, consent_id)
    if c is None or c.business_id != biz.id or c.purpose != "aa_fetch":
        raise NotFound("Bank link not found", "aa_consent_not_found")
    return c


def fetch(db: Session, biz: Business, consent_id: str, actor: str) -> list[EvidenceItem]:
    c = _aa_consent(db, biz, consent_id)
    if not consent.is_active(c):
        raise DomainError("Bank link permission has ended", "consent_inactive", 403)
    aa = get_adapters().aa
    handle = str(c.scope["aa_handle"])
    try:
        status = aa.consent_status(handle).status
        if status != "ACTIVE":
            raise DomainError(
                "Please approve the request in your AA app first", f"aa_{status.lower()}", 409
            )
        accounts = aa.fetch(handle, int(c.scope.get("months", MONTHS)))
    except AdapterError as exc:
        raise RetryableJobError(str(exc)) from exc
    items = []
    for acc in accounts:
        ev = EvidenceItem(
            business_id=biz.id,
            type="aa_fetch",
            source=f"aa:{aa.name}",
            status="parsed",
            captured_at=utcnow(),
            meta={
                "holder_name": acc.holder_name,
                "account_ref": acc.masked_account,
                "bank": acc.bank,
                "consent_id": c.id,
                "sandbox": aa.sandbox,
                "first_date": str(min((t.txn_date for t in acc.transactions), default="")),
                "last_date": str(max((t.txn_date for t in acc.transactions), default="")),
            },
        )
        db.add(ev)
        db.flush()
        stored, skipped = store_transactions(
            db,
            biz.id,
            ev,
            [
                MoneyTxn(
                    t.txn_date,
                    t.amount_paise,
                    t.direction,
                    t.counterparty_vpa,
                    t.counterparty_name,
                    t.utr,
                    t.balance_after_paise,
                    t.narration,
                    acc.masked_account,
                )
                for t in acc.transactions
            ],
        )
        ev.meta = {**ev.meta, "txns": stored, "duplicates_skipped": skipped}
        items.append(ev)
    c.scope = {**c.scope, "last_fetch_at": utcnow().isoformat()}
    record(
        db,
        actor,
        "money.aa_fetch",
        f"business:{biz.id}",
        {
            "consent_id": c.id,
            "accounts": len(items),
            "txns": sum(int(e.meta["txns"]) for e in items),
            "sandbox": aa.sandbox,
        },
    )
    return items


def revoke(db: Session, user: User, biz: Business, consent_id: str) -> None:
    c = _aa_consent(db, biz, consent_id)
    handle = str(c.scope.get("aa_handle"))
    # Our consent is revoked regardless; the AA side is retried by the provider.
    with contextlib.suppress(AdapterError):
        get_adapters().aa.revoke(handle)
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    consent.revoke(db, owner, c.id)
    for r in consent.active(db, owner.id, "monthly_refresh", biz.id):
        if r.scope.get("aa_handle") == handle:
            consent.revoke(db, owner, r.id)


def due_for_refresh(db: Session) -> list[tuple[str, str]]:
    """(business_id, aa consent id) pairs whose monthly refresh is due."""
    out = []
    now = utcnow()
    for r in db.execute(
        select(Consent).where(Consent.purpose == "monthly_refresh", Consent.revoked_at.is_(None))
    ).scalars():
        if not consent.is_active(r) or not r.business_id:
            continue
        aa = (
            db.execute(
                select(Consent).where(
                    Consent.purpose == "aa_fetch",
                    Consent.business_id == r.business_id,
                    Consent.revoked_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for c in aa:
            if c.scope.get("aa_handle") != r.scope.get("aa_handle") or not consent.is_active(c):
                continue
            last = c.scope.get("last_fetch_at")
            if last and now - datetime.fromisoformat(last) < REFRESH_EVERY:
                continue
            out.append((r.business_id, c.id))
    return out


@job("aa_refresh")
def refresh_job(db: Session, business_id: str, consent_id: str) -> None:
    biz = db.get(Business, business_id)
    if biz is not None:
        fetch(db, biz, consent_id, "system:monthly_refresh")


@job("aa_refresh_due")
def refresh_due_job(db: Session) -> None:
    from app.jobs import enqueue

    for business_id, consent_id in due_for_refresh(db):
        enqueue(db, "aa_refresh", business_id, consent_id)
