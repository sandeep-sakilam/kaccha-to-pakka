"""Counterparty selection: the system, not the owner, picks who is asked to confirm.

The top counterparties by value over the last 6 months of money data are listed with the UPI ID
or account and the payee name exactly as the bank shows them. The owner cannot add or swap names;
they only route each invite to a phone number.
"""

import secrets
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.core.errors import DomainError, NotFound
from app.db.base import utcnow
from app.db.models import (
    BankTransaction,
    Business,
    Counterparty,
    CounterpartyInvite,
    EvidenceItem,
    User,
)
from app.modules.audit.service import record
from app.modules.identity.service import normalise_phone

TOP_N = 5
WINDOW_DAYS = 183
INVITE_TTL = timedelta(days=14)


@dataclass(frozen=True)
class TopCounterparty:
    counterparty_id: str
    vpa_or_account: str
    registered_name: str | None
    relationship: str  # supplier (we pay them) or customer (they pay us)
    value_paise: int
    txns: int
    months_active: int


def mask_vpa(vpa: str) -> str:
    if "@" in vpa:
        handle, bank = vpa.split("@", 1)
        return (handle[:3] + "•" * max(len(handle) - 3, 2)) + "@" + bank
    return "•" * max(len(vpa) - 4, 2) + vpa[-4:]


def top_counterparties(
    db: Session, business_id: str, today: date | None = None
) -> list[TopCounterparty]:
    today = today or date.today()
    since = today - timedelta(days=WINDOW_DAYS)
    rows = db.execute(
        select(BankTransaction)
        .join(EvidenceItem)
        .where(
            EvidenceItem.business_id == business_id,
            EvidenceItem.status.notin_(["on_hold", "rejected"]),
            BankTransaction.txn_date >= since,
            BankTransaction.counterparty_vpa.is_not(None),
        )
    ).scalars()
    value: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    out_value: dict[str, int] = defaultdict(int)
    months: dict[str, set[tuple[int, int]]] = defaultdict(set)
    names: dict[str, str | None] = {}
    for t in rows:
        vpa = t.counterparty_vpa or ""
        value[vpa] += t.amount_paise
        count[vpa] += 1
        if t.direction == "out":
            out_value[vpa] += t.amount_paise
        months[vpa].add((t.txn_date.year, t.txn_date.month))
        names.setdefault(vpa, t.counterparty_name)
    ranked = sorted(value, key=lambda v: (-value[v], v))[:TOP_N]
    out = []
    for vpa in ranked:
        cp = db.execute(select(Counterparty).where(Counterparty.vpa_or_account == vpa)).scalar_one()
        out.append(
            TopCounterparty(
                cp.id,
                vpa,
                cp.registered_name or names.get(vpa),
                "supplier" if out_value[vpa] * 2 > value[vpa] else "customer",
                value[vpa],
                count[vpa],
                len(months[vpa]),
            )
        )
    return out


def invite(
    db: Session, user: User, biz: Business, counterparty_id: str, phone: str, language: str
) -> CounterpartyInvite:
    top = {c.counterparty_id: c for c in top_counterparties(db, biz.id)}
    if counterparty_id not in top:
        raise DomainError(
            "You can only invite the partners we picked from your payments", "not_selected", 403
        )
    phone = normalise_phone(phone)
    from app.modules.abuse.limits import hit

    hit("invites_business", biz.id)
    owner = db.get(User, biz.owner_user_id)
    flags: list[str] = []
    if owner is not None and phone == owner.phone:
        raise DomainError("Use your partner's number, not your own", "own_phone")
    existing = list(
        db.execute(
            select(CounterpartyInvite).where(
                CounterpartyInvite.business_id == biz.id,
                CounterpartyInvite.status.in_(["sent", "opened", "proven"]),
            )
        ).scalars()
    )
    if any(i.counterparty_id == counterparty_id for i in existing):
        raise DomainError("An invite for this partner is already open", "invite_open", 409)
    if any(i.phone == phone for i in existing):
        flags.append("same_phone_multiple_partners")  # one friend routed several partners
    cp = top[counterparty_id]
    inv = CounterpartyInvite(
        business_id=biz.id,
        counterparty_id=counterparty_id,
        phone=phone,
        language=language if language in {"hi", "en"} else "hi",
        token=secrets.token_urlsafe(24),
        relationship_hint=cp.relationship,
        flags=flags,
        expires_at=utcnow() + INVITE_TTL,
    )
    db.add(inv)
    db.flush()
    link = f"{get_settings().public_base_url}/confirm/{inv.token}"
    role_hi = "सप्लायर" if cp.relationship == "supplier" else "ग्राहक"
    text = (
        (
            f"नमस्ते! {biz.name} ने आपको अपने {role_hi} के रूप में पुष्टि करने को कहा है। "
            f"इसमें 1 मिनट लगेगा और ₹1 वापस मिल जाएगा: {link}"
        )
        if inv.language == "hi"
        else (
            f"Namaste! {biz.name} asked you to confirm you trade with them as their "
            f"{cp.relationship}. It takes 1 minute and the ₹1 is refunded: {link}"
        )
    )
    try:
        get_adapters().whatsapp.send(phone, text)
    except AdapterError:
        get_adapters().sms.send(phone, text)
    record(
        db,
        f"user:{user.id}",
        "invite.sent",
        f"business:{biz.id}",
        {"invite_id": inv.id, "counterparty_id": counterparty_id, "flags": flags},
    )
    return inv


def by_token(db: Session, token: str) -> CounterpartyInvite:
    inv = db.execute(
        select(CounterpartyInvite).where(CounterpartyInvite.token == token)
    ).scalar_one_or_none()
    if inv is None:
        raise NotFound("This link is not valid", "invite_not_found")
    if inv.expires_at < utcnow() and inv.status in {"sent", "opened"}:
        inv.status = "expired"
    return inv
