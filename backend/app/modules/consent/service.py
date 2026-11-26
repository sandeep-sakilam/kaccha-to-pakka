"""Granular, revocable consent: one row per purpose, each with a scope and an expiry.

Nothing that needs consent may run without an active row; withdrawing is one call (one tap or
one voice command in the UI) and is logged.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, Forbidden, NotFound
from app.db.base import utcnow
from app.db.models import Consent, User
from app.modules.audit.service import record


@dataclass(frozen=True)
class Purpose:
    key: str
    default_days: int | None  # None = until revoked
    needs_business: bool
    why_en: str
    why_hi: str


PURPOSES: dict[str, Purpose] = {
    p.key: p
    for p in [
        Purpose(
            "build_passport",
            None,
            False,
            "To check your records and build your Trust Passport.",
            "आपके रिकॉर्ड जाँचकर आपका ट्रस्ट पासपोर्ट बनाने के लिए।",
        ),
        Purpose(
            "aa_fetch",
            365,
            True,
            "To read 12 months of your bank data through Account Aggregator.",
            "अकाउंट एग्रीगेटर से आपके बैंक के 12 महीने के लेन-देन पढ़ने के लिए।",
        ),
        Purpose(
            "monthly_refresh",
            365,
            True,
            "To refresh your bank data every month so your passport stays fresh.",
            "हर महीने बैंक डेटा नया करने के लिए, ताकि पासपोर्ट ताज़ा रहे।",
        ),
        Purpose(
            "share_lender",
            30,
            True,
            "To show your passport to one lender you choose, until the share expires.",
            "आपके चुने हुए एक ऋणदाता को पासपोर्ट दिखाने के लिए, तय समय तक।",
        ),
        Purpose(
            "keep_originals",
            None,
            True,
            "To keep your original photos and files instead of deleting them after reading.",
            "पढ़ने के बाद भी आपकी असली फ़ोटो और फ़ाइलें रखने के लिए।",
        ),
        Purpose(
            "presence_location",
            180,
            True,
            "To use your phone's location on shop photos as proof the shop exists.",
            "दुकान की फ़ोटो पर फ़ोन की लोकेशन, दुकान होने के सबूत के लिए।",
        ),
        Purpose(
            "sahayak_help",
            None,
            True,
            "To let a helper you chose add evidence for you. Every action is tagged with them.",
            "आपके चुने सहायक को आपके लिए सबूत जोड़ने देने के लिए। हर काम पर उनका नाम दर्ज होता है।",
        ),
        Purpose(
            "model_training",
            None,
            False,
            "Optional: to use your data to improve our reading of ledgers.",
            "वैकल्पिक: खाता पढ़ना बेहतर करने के लिए आपके डेटा का उपयोग।",
        ),
    ]
}

NOTICE = {
    "en": [
        "What we collect: your phone number, your business details, photos of your ledger and "
        "shop, and bank data only if you allow it.",
        "Why: to check that your business is real and build your Trust Passport.",
        "Who sees it: only you, and a lender only when you share it with them.",
        "How to delete: say 'delete my account' or tap Delete. We remove your data and stop "
        "all shares.",
        "What we never do: we never lend, never sell your data, never share without your yes.",
    ],
    "hi": [
        "हम क्या लेते हैं: आपका फ़ोन नंबर, आपके व्यापार की जानकारी, खाता-बही और दुकान की फ़ोटो, "
        "और बैंक डेटा केवल आपकी अनुमति से।",
        "क्यों: यह जाँचने के लिए कि आपका व्यापार असली है, और आपका ट्रस्ट पासपोर्ट बनाने के लिए।",
        "कौन देखता है: केवल आप, और ऋणदाता तभी जब आप उसे भेजें।",
        "कैसे मिटाएँ: 'मेरा खाता मिटाओ' बोलें या मिटाएँ दबाएँ। हम आपका डेटा हटा देंगे और सब शेयर बंद कर देंगे।",
        "हम कभी नहीं करते: हम कर्ज़ नहीं देते, आपका डेटा नहीं बेचते, आपकी हाँ के बिना किसी को नहीं दिखाते।",
    ],
}


def notice(language: str) -> list[str]:
    return NOTICE.get(language, NOTICE["en"])


def is_active(c: Consent, at: datetime | None = None) -> bool:
    at = at or utcnow()
    return c.revoked_at is None and (c.expires_at is None or c.expires_at > at)


def grant(
    db: Session,
    user: User,
    purpose: str,
    business_id: str | None = None,
    scope: dict[str, Any] | None = None,
    days: int | None = None,
) -> Consent:
    p = PURPOSES.get(purpose)
    if p is None:
        raise DomainError(f"Unknown purpose {purpose}", "bad_purpose")
    if p.needs_business and not business_id:
        raise DomainError("This consent needs a business", "business_required")
    days = days if days is not None else p.default_days
    c = Consent(
        user_id=user.id,
        business_id=business_id,
        purpose=purpose,
        scope=scope or {},
        expires_at=utcnow() + timedelta(days=days) if days else None,
    )
    db.add(c)
    db.flush()
    record(
        db,
        f"user:{user.id}",
        "consent.grant",
        f"consent:{c.id}",
        {"purpose": purpose, "business_id": business_id, "scope": scope or {}, "days": days},
    )
    return c


def revoke(db: Session, user: User, consent_id: str) -> Consent:
    c = db.get(Consent, consent_id)
    if c is None or c.user_id != user.id:
        raise NotFound("Consent not found", "consent_not_found")
    if c.revoked_at is None:
        c.revoked_at = utcnow()
        record(db, f"user:{user.id}", "consent.revoke", f"consent:{c.id}", {"purpose": c.purpose})
    return c


def revoke_purpose(db: Session, user: User, purpose: str, business_id: str | None = None) -> int:
    """Withdraw every active consent for a purpose (used by the voice command)."""
    n = 0
    for c in active(db, user.id, purpose, business_id):
        revoke(db, user, c.id)
        n += 1
    return n


def active(
    db: Session, user_id: str, purpose: str | None = None, business_id: str | None = None
) -> list[Consent]:
    q = select(Consent).where(Consent.user_id == user_id, Consent.revoked_at.is_(None))
    if purpose:
        q = q.where(Consent.purpose == purpose)
    if business_id:
        q = q.where(Consent.business_id == business_id)
    return [c for c in db.execute(q.order_by(Consent.granted_at)).scalars() if is_active(c)]


def has(db: Session, user_id: str, purpose: str, business_id: str | None = None) -> bool:
    if active(db, user_id, purpose, business_id):
        return True
    # A build_passport consent given before the business existed still covers it.
    return purpose == "build_passport" and bool(active(db, user_id, purpose))


def require(db: Session, user_id: str, purpose: str, business_id: str | None = None) -> None:
    if not has(db, user_id, purpose, business_id):
        why = PURPOSES[purpose].why_en if purpose in PURPOSES else purpose
        raise Forbidden(f"We need your permission first. {why}", f"consent_required:{purpose}")


def list_all(db: Session, user_id: str) -> list[Consent]:
    return list(
        db.execute(
            select(Consent).where(Consent.user_id == user_id).order_by(Consent.granted_at.desc())
        ).scalars()
    )
