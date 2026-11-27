"""Phone OTP, 4-digit PIN, sessions and device binding.

A family often shares one phone, so the PIN is per profile: proving the phone (OTP) is not
enough to open a passport. A device is bound after OTP; logins from a bound device need only the
PIN. A login from a new device is marked so the takeover freeze (F34) can hold shares.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.registry import get_adapters
from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import AuthSession, DeviceBinding, OtpChallenge, User
from app.modules.audit.service import record
from app.modules.identity import security

OTP_TTL = timedelta(minutes=5)
OTP_MAX_ATTEMPTS = 5
SESSION_TTL = timedelta(days=30)
PIN_MAX_FAILURES = 5
PIN_LOCK = timedelta(minutes=30)
PHONE_RE = re.compile(r"^\+91[6-9]\d{9}$")


class AuthError(DomainError):
    status_code = 401


def normalise_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        digits = "91" + digits
    out = "+" + digits
    if not PHONE_RE.match(out):
        raise AuthError("Enter a 10-digit Indian mobile number", "bad_phone")
    return out


@dataclass(frozen=True)
class OtpSent:
    challenge_id: str
    expires_at: datetime
    sandbox_code: str | None  # only when SMS is a mock, so the demo can proceed


def request_otp(db: Session, phone: str, language: str = "hi", ip: str | None = None) -> OtpSent:
    from app.modules.abuse.limits import hit

    phone = normalise_phone(phone)
    hit("otp_phone", phone)
    if ip:
        hit("otp_ip", ip)
    code = security.new_otp()
    ch = OtpChallenge(
        phone=phone, code_hash=security.hash_token(code), expires_at=utcnow() + OTP_TTL
    )
    db.add(ch)
    db.flush()
    sms = get_adapters().sms
    text = (
        f"Kaccha to Pakka OTP: {code}. Kisi ko na batayein."
        if language == "hi"
        else f"Kaccha to Pakka OTP: {code}. Do not share it."
    )
    sms.send(phone, text)
    record(db, "phone:" + phone[-4:], "auth.otp_requested", f"otp:{ch.id}")
    return OtpSent(ch.id, ch.expires_at, code if sms.sandbox else None)


@dataclass(frozen=True)
class LoginResult:
    token: str
    user: User
    stage: str
    has_pin: bool
    new_device: bool
    profiles: int = 1


def _issue_session(db: Session, user: User, device_id: str, stage: str, new_device: bool) -> str:
    token = security.new_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=security.hash_token(token),
            device_id=device_id,
            stage=stage,
            new_device=new_device,
            expires_at=utcnow() + SESSION_TTL,
        )
    )
    db.flush()
    return token


def _bind_device(db: Session, user: User, device_id: str) -> bool:
    """Bind the device; returns True if it was not bound before (a new device)."""
    existing = db.execute(
        select(DeviceBinding).where(
            DeviceBinding.user_id == user.id,
            DeviceBinding.device_id == device_id,
            DeviceBinding.revoked_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing:
        existing.last_seen_at = utcnow()
        return False
    had_devices = (
        db.execute(select(DeviceBinding.id).where(DeviceBinding.user_id == user.id)).first()
        is not None
    )
    db.add(DeviceBinding(user_id=user.id, device_id=device_id))
    user.device_ids = [*(user.device_ids or []), device_id]
    return had_devices


def verify_otp(
    db: Session, phone: str, code: str, device_id: str, language: str = "hi"
) -> LoginResult:
    phone = normalise_phone(phone)
    ch = db.execute(
        select(OtpChallenge)
        .where(OtpChallenge.phone == phone, OtpChallenge.consumed_at.is_(None))
        .order_by(OtpChallenge.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if ch is None or ch.expires_at < utcnow():
        raise AuthError("OTP expired. Ask for a new one.", "otp_expired")
    if ch.attempts >= OTP_MAX_ATTEMPTS:
        raise AuthError("Too many tries. Ask for a new OTP.", "otp_locked")
    ch.attempts += 1
    if security.hash_token(code.strip()) != ch.code_hash:
        db.flush()
        raise AuthError("Wrong OTP", "otp_wrong")
    ch.consumed_at = utcnow()
    profiles = profiles_for(db, phone)
    user = profiles[0] if profiles else None
    if user is None:
        user = User(phone=phone, language=language, roles=["owner"], device_ids=[])
        db.add(user)
        db.flush()
        record(db, f"user:{user.id}", "user.created", f"user:{user.id}")
    if user.status != "active":
        raise AuthError("This account is not active", "inactive")
    new_device = _bind_device(db, user, device_id)
    if new_device:
        from app.modules.notify import notify

        notify(
            db,
            user,
            "new_device",
            "नए फ़ोन से लॉग इन हुआ। सुरक्षा के लिए 24 घंटे शेयर रुके हैं। अगर यह आप नहीं थे, तो तुरंत "
            "PIN बदलें और हमें बताएँ।",
            "A new phone logged in. Sharing is paused for 24 hours for your safety. If this was "
            "not you, change your PIN and tell us.",
        )
    token = _issue_session(db, user, device_id, "otp", new_device)
    record(
        db,
        f"user:{user.id}",
        "auth.otp_verified",
        f"user:{user.id}",
        {"device": device_id[-6:], "new_device": new_device},
    )
    return LoginResult(
        token, user, "otp", user.pin_hash is not None, new_device, max(len(profiles), 1)
    )


def profiles_for(db: Session, phone: str) -> list[User]:
    """Active profiles on one phone number, oldest first."""
    return list(
        db.execute(
            select(User)
            .where(User.phone == phone, User.status == "active")
            .order_by(User.created_at, User.id)
        ).scalars()
    )


def primary_user(db: Session, phone: str) -> User | None:
    """The first profile on a phone (used where only the number is known, e.g. WhatsApp)."""
    found = profiles_for(db, phone)
    if found:
        return found[0]
    return (
        db.execute(select(User).where(User.phone == phone).order_by(User.created_at))
        .scalars()
        .first()
    )


def _pin_taken(db: Session, phone: str, pin: str, except_user: str | None = None) -> bool:
    return any(
        security.verify_pin(pin, u.pin_hash)
        for u in profiles_for(db, phone)
        if u.id != except_user and u.pin_hash
    )


def new_profile(db: Session, session: AuthSession, name: str, pin: str) -> User:
    """Another person on the same phone makes their own profile with their own PIN.
    The phone was proven by OTP in this session; no existing PIN is needed or revealed."""
    current = db.get(User, session.user_id)
    assert current is not None
    name = " ".join(name.split())[:60]
    if len(name) < 2:
        raise AuthError("Give a name for this profile", "bad_profile_name")
    if any(u.profile_name.lower() == name.lower() for u in profiles_for(db, current.phone)):
        raise AuthError("This phone already has a profile with that name", "profile_exists")
    problem = security.pin_problem(pin)
    if problem:
        raise AuthError(problem, "weak_pin")
    if _pin_taken(db, current.phone, pin):
        raise AuthError("Choose a different PIN from others on this phone", "pin_in_use")
    user = User(
        phone=current.phone,
        profile_name=name,
        language=current.language,
        roles=["owner"],
        device_ids=[],
        pin_hash=security.hash_pin(pin),
    )
    db.add(user)
    db.flush()
    _bind_device(db, user, session.device_id)
    session.user_id, session.stage = user.id, "full"
    record(db, f"user:{user.id}", "user.profile_created", f"user:{user.id}", {"shared_phone": True})
    return user


def session_for(db: Session, token: str) -> AuthSession | None:
    s = db.execute(
        select(AuthSession).where(AuthSession.token_hash == security.hash_token(token))
    ).scalar_one_or_none()
    if s is None or s.revoked_at is not None or s.expires_at < utcnow():
        return None
    return s


def set_pin(db: Session, session: AuthSession, pin: str) -> None:
    user = db.get(User, session.user_id)
    assert user is not None
    if user.pin_hash is not None and session.stage != "full":
        raise AuthError("Enter your current PIN first", "pin_exists")
    problem = security.pin_problem(pin)
    if problem:
        raise AuthError(problem, "weak_pin")
    if _pin_taken(db, user.phone, pin, except_user=user.id):
        raise AuthError("Choose a different PIN from others on this phone", "pin_in_use")
    user.pin_hash = security.hash_pin(pin)
    user.pin_failures = 0
    session.stage = "full"
    record(db, f"user:{user.id}", "auth.pin_set", f"user:{user.id}")


def _check_pin(db: Session, user: User, pin: str) -> None:
    now = utcnow()
    if user.pin_locked_until and user.pin_locked_until > now:
        raise AuthError("PIN locked for 30 minutes after too many tries", "pin_locked")
    if not security.verify_pin(pin, user.pin_hash):
        user.pin_failures += 1
        if user.pin_failures >= PIN_MAX_FAILURES:
            user.pin_locked_until = now + PIN_LOCK
            user.pin_failures = 0
            record(db, f"user:{user.id}", "auth.pin_locked", f"user:{user.id}")
        db.flush()
        raise AuthError("Wrong PIN", "pin_wrong")
    user.pin_failures = 0


def verify_pin(db: Session, session: AuthSession, pin: str) -> None:
    """On a shared phone the PIN says whose profile opens: each profile has its own PIN."""
    user = db.get(User, session.user_id)
    assert user is not None
    for other in profiles_for(db, user.phone):
        if other.id != user.id and other.pin_hash and security.verify_pin(pin, other.pin_hash):
            if other.pin_locked_until and other.pin_locked_until > utcnow():
                raise AuthError("PIN locked for 30 minutes after too many tries", "pin_locked")
            user = other
            session.user_id = other.id
            _bind_device(db, other, session.device_id)
            break
    else:
        _check_pin(db, user, pin)
    user.pin_failures = 0
    session.stage = "full"
    record(db, f"user:{user.id}", "auth.pin_verified", f"user:{user.id}")


def pin_login(db: Session, phone: str, pin: str, device_id: str) -> LoginResult:
    """Returning user on an already bound device: PIN only. Otherwise OTP is required."""
    phone = normalise_phone(phone)
    bound = [
        u
        for u in profiles_for(db, phone)
        if db.execute(
            select(DeviceBinding.id).where(
                DeviceBinding.user_id == u.id,
                DeviceBinding.device_id == device_id,
                DeviceBinding.revoked_at.is_(None),
            )
        ).first()
        is not None
    ]
    if not bound:
        raise AuthError("Verify your phone with an OTP on this device", "otp_required")
    user = next((u for u in bound if security.verify_pin(pin, u.pin_hash)), bound[0])
    _check_pin(db, user, pin)
    token = _issue_session(db, user, device_id, "full", False)
    record(db, f"user:{user.id}", "auth.pin_login", f"user:{user.id}")
    return LoginResult(token, user, "full", True, False)


def logout(db: Session, session: AuthSession) -> None:
    session.revoked_at = utcnow()
    record(db, f"user:{session.user_id}", "auth.logout", f"user:{session.user_id}")
