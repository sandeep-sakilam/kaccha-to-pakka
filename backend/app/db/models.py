"""All tables from the SPEC Data model. Money is integer paise; timestamps are UTC.

Every derived fact points back to the evidence it came from (evidence_id / foreign keys), so any
line on a passport can be traced to a photo, a transaction or an attestation.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, new_id, utcnow
from app.db.crypto import EncryptedString

Json = JSON().with_variant(JSONB(), "postgresql")

DIRECTIONS = ("in", "out")


def _id() -> Mapped[str]:
    return mapped_column(String(36), primary_key=True, default=new_id)


class User(TimestampMixin, Base):
    """One person; may own or help several businesses."""

    __tablename__ = "users"
    id: Mapped[str] = _id()
    phone: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    pin_hash: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(200))
    language: Mapped[str] = mapped_column(String(8), default="hi")
    gender: Mapped[str | None] = mapped_column(String(16))
    kyc_status: Mapped[str] = mapped_column(String(16), default="none")
    device_ids: Mapped[list[str]] = mapped_column(Json, default=list)
    roles: Mapped[list[str]] = mapped_column(Json, default=lambda: ["owner"])
    status: Mapped[str] = mapped_column(String(16), default="active")
    pin_failures: Mapped[int] = mapped_column(Integer, default=0)
    pin_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Business(TimestampMixin, Base):
    """The passport subject."""

    __tablename__ = "businesses"
    id: Mapped[str] = _id()
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(64))
    started_on: Mapped[date | None] = mapped_column(Date)
    udyam: Mapped[str | None] = mapped_column(String(32))
    gstin: Mapped[str | None] = mapped_column(String(15))
    geo_home: Mapped[dict[str, Any] | None] = mapped_column(Json)
    address: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(String(100))
    sells: Mapped[str | None] = mapped_column(Text)
    women_owned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SahayakLink(Base):
    """Who may help whom."""

    __tablename__ = "sahayak_links"
    id: Mapped[str] = _id()
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    sahayak_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    permissions: Mapped[list[str]] = mapped_column(Json, default=list)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Consent(Base):
    """One row per purpose (build passport, share with lender X, monthly refresh)."""

    __tablename__ = "consents"
    id: Mapped[str] = _id()
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(48))
    scope: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvidenceItem(TimestampMixin, Base):
    """Photo, PDF, AA fetch, voice note, ledger export."""

    __tablename__ = "evidence_items"
    id: Mapped[str] = _id()
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(48))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    storage_key: Mapped[str | None] = mapped_column(String(255))
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geo: Mapped[dict[str, Any] | None] = mapped_column(Json)
    device_attestation: Mapped[dict[str, Any] | None] = mapped_column(Json)
    status: Mapped[str] = mapped_column(String(24), default="received")
    meta: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    sahayak_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class LedgerEntry(TimestampMixin, Base):
    """Extracted from a ledger photo, voice note or ledger-app export."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_nonneg"),
        CheckConstraint("direction in ('in','out')", name="direction"),
    )
    id: Mapped[str] = _id()
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    entry_date: Mapped[date | None] = mapped_column(Date)
    party_text: Mapped[str | None] = mapped_column(EncryptedString)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(3))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    field_confidence: Mapped[dict[str, float]] = mapped_column(Json, default=dict)
    confirmed_by_owner: Mapped[bool | None] = mapped_column(Boolean)
    page_no: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="extracted")


class BankTransaction(TimestampMixin, Base):
    """From Account Aggregator or a statement PDF."""

    __tablename__ = "bank_transactions"
    __table_args__ = (
        CheckConstraint("amount_paise >= 0", name="amount_nonneg"),
        CheckConstraint("direction in ('in','out')", name="direction"),
    )
    id: Mapped[str] = _id()
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence_items.id"), index=True)
    txn_date: Mapped[date] = mapped_column(Date, index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    direction: Mapped[str] = mapped_column(String(3))
    counterparty_vpa: Mapped[str | None] = mapped_column(String(128), index=True)
    counterparty_name: Mapped[str | None] = mapped_column(EncryptedString)
    utr: Mapped[str | None] = mapped_column(String(32))
    balance_after_paise: Mapped[int | None] = mapped_column(BigInteger)
    narration: Mapped[str | None] = mapped_column(EncryptedString)
    account_ref: Mapped[str | None] = mapped_column(EncryptedString)


class Counterparty(TimestampMixin, Base):
    """Graph nodes: a UPI ID or account seen in money data."""

    __tablename__ = "counterparties"
    id: Mapped[str] = _id()
    vpa_or_account: Mapped[str] = mapped_column(String(128), unique=True)
    registered_name: Mapped[str | None] = mapped_column(EncryptedString)
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id"), index=True)


class ReconMatch(TimestampMixin, Base):
    """Ledger entry to bank transaction. Many-to-one is allowed."""

    __tablename__ = "recon_matches"
    __table_args__ = (UniqueConstraint("ledger_entry_id", "bank_txn_id", name="pair"),)
    id: Mapped[str] = _id()
    ledger_entry_id: Mapped[str] = mapped_column(ForeignKey("ledger_entries.id"), index=True)
    bank_txn_id: Mapped[str] = mapped_column(ForeignKey("bank_transactions.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    rule: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), default="matched")


class Attestation(TimestampMixin, Base):
    """Signed confirmation from a counterparty."""

    __tablename__ = "attestations"
    id: Mapped[str] = _id()
    subject_business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    confirmer_business_id: Mapped[str | None] = mapped_column(
        ForeignKey("businesses.id"), index=True
    )
    counterparty_id: Mapped[str | None] = mapped_column(ForeignKey("counterparties.id"))
    evidence_type: Mapped[str] = mapped_column(String(24), default="penny_drop")
    claim: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    proof_txn_ref: Mapped[str | None] = mapped_column(String(64))
    money_match: Mapped[bool | None] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    weight: Mapped[float] = mapped_column(Float, default=0.0)
    signature: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Assessment(Base):
    """Immutable; one per scoring run. Stores rules and model versions so it can be recomputed."""

    __tablename__ = "assessments"
    id: Mapped[str] = _id()
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    rules_version: Mapped[str] = mapped_column(String(32))
    model_versions: Mapped[dict[str, str]] = mapped_column(Json, default=dict)
    pillar_scores: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    band: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[str] = mapped_column(String(16))
    reasons: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    flags: Mapped[list[dict[str, Any]]] = mapped_column(Json, default=list)
    status: Mapped[str] = mapped_column(String(16), default="final")
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Passport(TimestampMixin, Base):
    """Issued W3C Verifiable Credential."""

    __tablename__ = "passports"
    id: Mapped[str] = _id()
    business_id: Mapped[str] = mapped_column(ForeignKey("businesses.id"), index=True)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id"))
    vc_json: Mapped[dict[str, Any]] = mapped_column(Json)
    signature: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="valid")


class Share(TimestampMixin, Base):
    """One per lender: scoped, expiring, revocable."""

    __tablename__ = "shares"
    id: Mapped[str] = _id()
    passport_id: Mapped[str] = mapped_column(ForeignKey("passports.id"), index=True)
    lender_org: Mapped[str] = mapped_column(String(200))
    scope: Mapped[str] = mapped_column(String(24), default="summary")
    token: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessLog(Base):
    """Every lender view, shown back to the owner."""

    __tablename__ = "access_logs"
    id: Mapped[str] = _id()
    share_id: Mapped[str] = mapped_column(ForeignKey("shares.id"), index=True)
    viewer: Mapped[str] = mapped_column(String(200))
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ip: Mapped[str | None] = mapped_column(String(64))


class Dispute(TimestampMixin, Base):
    """Reviewer queue."""

    __tablename__ = "disputes"
    id: Mapped[str] = _id()
    target_type: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[str] = mapped_column(String(36))
    business_id: Mapped[str | None] = mapped_column(ForeignKey("businesses.id"), index=True)
    raised_by: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    """Hash-chained, append-only."""

    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    object: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict[str, Any]] = mapped_column(Json, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OtpChallenge(TimestampMixin, Base):
    """One-time code sent to a phone. Only a hash of the code is stored."""

    __tablename__ = "otp_challenges"
    id: Mapped[str] = _id()
    phone: Mapped[str] = mapped_column(String(16), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(TimestampMixin, Base):
    """A login on one device. stage: 'otp' (phone proven, PIN still needed) or 'full'."""

    __tablename__ = "auth_sessions"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    device_id: Mapped[str] = mapped_column(String(128))
    stage: Mapped[str] = mapped_column(String(8), default="otp")
    new_device: Mapped[bool] = mapped_column(Boolean, default=False)
    acting_as_sahayak: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeviceBinding(TimestampMixin, Base):
    """A device bound to a user after OTP. A new device triggers the account-takeover freeze."""

    __tablename__ = "device_bindings"
    __table_args__ = (UniqueConstraint("user_id", "device_id", name="user_device"),)
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(128))
    label: Mapped[str | None] = mapped_column(String(100))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobFailure(TimestampMixin, Base):
    """Dead-letter queue: a job that failed all its retries, kept with its error for review."""

    __tablename__ = "job_failures"
    id: Mapped[str] = _id()
    job: Mapped[str] = mapped_column(String(64))
    args: Mapped[list[Any]] = mapped_column(Json, default=list)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(TimestampMixin, Base):
    """Every message we send an owner, kept so the app can show it too."""

    __tablename__ = "notifications"
    id: Mapped[str] = _id()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(48))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
