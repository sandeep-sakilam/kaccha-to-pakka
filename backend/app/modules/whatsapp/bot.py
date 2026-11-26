"""WhatsApp bot: join, voice interview, ledger photos and read-back confirmations by chat.

WhatsApp already proves the phone number, so no OTP is sent; a 4-digit PIN is still set because
families share phones, and the consent text is sent before anything is collected. Every answer
can be a tap on a button, a short text or a voice note.
"""

import base64
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.config import get_settings
from app.core.errors import DomainError
from app.db.base import utcnow
from app.db.models import Business, EvidenceItem, LedgerEntry, User, WaConversation
from app.modules.business import interview
from app.modules.business.service import ProfileIn
from app.modules.business.service import create as create_business
from app.modules.consent import service as consent
from app.modules.evidence.service import CaptureIn, ingest_capture
from app.modules.extraction.checks import confirm_entry, readback_prompt
from app.modules.identity import security

YES = {"haan", "ha", "han", "yes", "y", "हाँ", "हां", "ji", "sahi", "सही", "1", "ok", "theek"}
NO = {"nahi", "nahin", "no", "n", "नहीं", "galat", "गलत", "2"}

M = {
    "welcome": {
        "hi": "नमस्ते! कच्चा से पक्का में स्वागत है। भाषा चुनें।",
        "en": "Namaste! Welcome to Kaccha to Pakka. Choose your language.",
    },
    "pin": {
        "hi": "अपना 4 अंकों का PIN लिखें (जैसे 4826)। परिवार में फ़ोन साझा हो तो यह आपका पासपोर्ट सुरक्षित रखता है।",
        "en": "Type a 4-digit PIN (like 4826). It keeps your passport yours on a shared phone.",
    },
    "consent_ask": {"hi": "क्या आप सहमत हैं?", "en": "Do you agree?"},
    "consent_no": {
        "hi": "ठीक है। आपकी हाँ के बिना हम कुछ नहीं लेते। 'Hi' लिखकर कभी भी शुरू करें।",
        "en": "Okay. We collect nothing without your yes. Send 'Hi' any time.",
    },
    "q_name": {
        "hi": "आपकी दुकान का नाम क्या है? (लिखें या बोलकर भेजें)",
        "en": "What is your shop's name? (type or send a voice note)",
    },
    "q_category": {"hi": "आप क्या बेचते हैं?", "en": "What do you sell?"},
    "q_since": {
        "hi": "व्यापार किस साल से चल रहा है?",
        "en": "Since which year is the business running?",
    },
    "q_place": {"hi": "आपकी दुकान कहाँ है?", "en": "Where is your shop?"},
    "again": {
        "hi": "समझ नहीं आया, फिर से भेजिए।",
        "en": "I did not understand. Please send it again.",
    },
    "ready": {
        "hi": "आपकी प्रोफ़ाइल तैयार है! अब खाते के पन्ने की फ़ोटो भेजें। 'पासपोर्ट' लिखें तो आपका बैंड बताएँगे, 'जाँच' लिखें तो एंट्री जाँचें।",
        "en": "Your profile is ready! Now send a photo of a ledger page. Send 'passport' to hear your band, 'check' to confirm entries.",
    },
    "photo_ok": {"hi": "पन्ना मिल गया, {n} एंट्री पढ़ीं।", "en": "Page received, {n} entries read."},
    "photo_voice": {
        "hi": "यह पन्ना पढ़ा नहीं जा सका। ऐप में 'खाता बोलकर लिखवाएँ' से लिखवाएँ।",
        "en": "This page could not be read. Use 'Read ledger aloud' in the app.",
    },
    "photo_bad": {
        "hi": "फ़ोटो साफ़ नहीं है: {r}। फिर से भेजें।",
        "en": "Photo not clear: {r}. Please send again.",
    },
    "no_checks": {
        "hi": "जाँचने के लिए कोई एंट्री नहीं है। धन्यवाद!",
        "en": "No entries to check. Thank you!",
    },
    "saved": {"hi": "सेव हो गया।", "en": "Saved."},
    "no_passport": {
        "hi": "अभी पासपोर्ट नहीं बना। ऐप में 'मेरा पासपोर्ट बनाएँ' दबाएँ: {url}",
        "en": "No passport yet. Tap 'Make my passport' in the app: {url}",
    },
}
CONSENT_BUTTONS = {"hi": ["हाँ", "नहीं"], "en": ["Yes", "No"]}


def t(key: str, lang: str, **kw: object) -> str:
    return M[key]["hi" if lang == "hi" else "en"].format(**kw)


@dataclass
class Inbound:
    phone: str
    text: str | None = None
    button: str | None = None
    image: tuple[bytes, str] | None = None
    audio: bytes | None = None
    message_id: str | None = None


class Bot:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.wa = get_adapters().whatsapp

    def send(self, to: str, text: str, buttons: list[str] | None = None) -> None:
        try:
            self.wa.send(to, text, buttons)
        except AdapterError:
            get_adapters().sms.send(to, text)

    def convo(self, phone: str) -> WaConversation:
        c = self.db.execute(
            select(WaConversation).where(WaConversation.phone == phone)
        ).scalar_one_or_none()
        if c is None:
            c = WaConversation(phone=phone, state="new", data={})
            self.db.add(c)
            self.db.flush()
        return c

    def _text(self, m: Inbound, lang: str) -> str:
        if m.text:
            return m.text.strip()
        if m.button:
            return m.button.strip()
        if m.audio:
            try:
                return get_adapters().ai.transcribe(m.audio, lang).value.text
            except AdapterError:
                return ""
        return ""

    def handle(self, m: Inbound) -> None:
        c = self.convo(m.phone)
        if c.data.get("last_id") and c.data.get("last_id") == m.message_id:
            return  # WhatsApp retries webhooks; handle each message once
        c.data = {**c.data, "last_id": m.message_id}
        lang = c.data.get("lang", "hi")
        text = self._text(m, lang)
        low = text.lower()
        if low in {"hi", "hello", "namaste", "नमस्ते", "start"} and c.state in {"new", "declined"}:
            c.state = "lang"
            self.send(m.phone, t("welcome", "hi") + "\n" + t("welcome", "en"), ["हिन्दी", "English"])
            return
        handler = getattr(self, f"on_{c.state}", None)
        if handler is None:
            c.state = "lang"
            self.send(m.phone, t("welcome", "hi"), ["हिन्दी", "English"])
            return
        handler(c, m, text, lang)

    # -- onboarding
    def on_lang(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        lang = "en" if text.lower().startswith("eng") else "hi"
        c.data = {**c.data, "lang": lang}
        user = self.db.execute(select(User).where(User.phone == m.phone)).scalar_one_or_none()
        if user is not None and user.pin_hash:
            c.state = "ready" if self._business(user) else "q_name"
            self.send(m.phone, t("ready" if c.state == "ready" else "q_name", lang))
            return
        c.state = "pin"
        self.send(m.phone, t("pin", lang))

    def on_pin(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        problem = security.pin_problem(text)
        if problem:
            self.send(m.phone, problem)
            return
        user = self.db.execute(select(User).where(User.phone == m.phone)).scalar_one_or_none()
        if user is None:
            user = User(phone=m.phone, language=lang, roles=["owner"], device_ids=[])
            self.db.add(user)
            self.db.flush()
        user.pin_hash = security.hash_pin(text)
        user.language = lang
        c.state = "consent"
        notice = "\n".join(consent.notice(lang))
        self.send(m.phone, notice + "\n\n" + t("consent_ask", lang), CONSENT_BUTTONS[lang])

    def on_consent(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        user = self._user(m.phone)
        if text.lower() in YES:
            consent.grant(self.db, user, "build_passport", scope={"channel": "whatsapp"})
            c.state = "q_name"
            self.send(m.phone, t("q_name", lang))
        else:
            c.state = "declined"
            self.send(m.phone, t("consent_no", lang))

    def _ask(
        self, c: WaConversation, m: Inbound, text: str, lang: str, q: str, field: str, nxt: str
    ) -> None:
        pending = c.data.get("pending")
        if pending and pending.get("field") == field:
            if text.lower() in YES:
                c.data = {
                    **c.data,
                    "profile": {**c.data.get("profile", {}), field: pending["value"]},
                    "pending": None,
                }
                c.state = nxt
                if nxt == "done":
                    self._finish(c, m, lang)
                else:
                    self.send(m.phone, t(nxt, lang))
                return
            if text.lower() in NO:
                c.data = {**c.data, "pending": None}
                self.send(m.phone, t(c.state, lang))
                return
        r = interview.INTERPRETERS[q](text)
        if not r.understood or r.value is None:
            self.send(m.phone, t("again", lang))
            return
        c.data = {**c.data, "pending": {"field": field, "value": r.value}}
        self.send(m.phone, r.confirm_hi if lang == "hi" else r.confirm_en, CONSENT_BUTTONS[lang])

    def on_q_name(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        self._ask(c, m, text, lang, "name", "name", "q_category")

    def on_q_category(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        self._ask(c, m, text, lang, "category", "category", "q_since")

    def on_q_since(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        self._ask(c, m, text, lang, "since", "started_year", "q_place")

    def on_q_place(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        self._ask(c, m, text, lang, "place", "address", "done")

    def _finish(self, c: WaConversation, m: Inbound, lang: str) -> None:
        p = c.data.get("profile", {})
        user = self._user(m.phone)
        create_business(
            self.db,
            user,
            ProfileIn(
                name=str(p.get("name") or "My shop"),
                category=str(p.get("category") or "other"),
                started_year=p.get("started_year"),
                address=p.get("address"),
            ),
            actor="whatsapp",
        )
        c.state = "ready"
        self.send(m.phone, t("ready", lang))

    # -- after onboarding
    def on_ready(self, c: WaConversation, m: Inbound, text: str, lang: str) -> None:
        user = self._user(m.phone)
        biz = self._business(user)
        if biz is None:
            c.state = "q_name"
            self.send(m.phone, t("q_name", lang))
            return
        if m.image:
            self._photo(c, m, user, biz, lang)
            return
        low = text.lower()
        if (m.button and m.button.startswith(("yes:", "no:"))) or c.data.get("checking"):
            self._answer_check(c, m, user, biz, low, lang)
            return
        if low in {"check", "jaanch", "जाँच", "जांच"}:
            self._next_check(c, m, biz, lang)
            return
        if low in {"passport", "पासपोर्ट", "band", "बैंड", "status"}:
            self._passport(m, biz, lang)
            return
        self.send(m.phone, t("ready", lang))

    def _photo(self, c: WaConversation, m: Inbound, user: User, biz: Business, lang: str) -> None:
        assert m.image is not None
        data, mime = m.image
        try:
            ev, _ = ingest_capture(
                self.db,
                user,
                biz,
                CaptureIn(
                    kind="ledger_page",
                    mime=mime,
                    data=data,
                    captured_at=utcnow(),
                    idempotency_key=f"wa-{m.message_id or base64.b16encode(data[:8]).decode()}",
                    device_id=f"whatsapp:{m.phone[-4:]}",
                    geo=None,
                    client_quality={},
                    source="whatsapp",
                ),
                actor="whatsapp",
            )
        except DomainError as exc:
            self.send(m.phone, t("photo_bad", lang, r=exc.message))
            return
        if ev.status == "needs_voice":
            self.send(m.phone, t("photo_voice", lang))
            return
        n = len(
            self.db.execute(select(LedgerEntry.id).where(LedgerEntry.evidence_id == ev.id)).all()
        )
        self.send(m.phone, t("photo_ok", lang, n=n))
        self._next_check(c, m, biz, lang)

    def _queue(self, biz: Business) -> list[LedgerEntry]:
        return list(
            self.db.execute(
                select(LedgerEntry)
                .join(EvidenceItem)
                .where(
                    EvidenceItem.business_id == biz.id,
                    LedgerEntry.confirmed_by_owner.is_(None),
                    LedgerEntry.status.in_(["needs_readback", "on_review"]),
                )
                .order_by(LedgerEntry.entry_date, LedgerEntry.page_no)
            ).scalars()
        )

    def _next_check(self, c: WaConversation, m: Inbound, biz: Business, lang: str) -> None:
        q = self._queue(biz)
        if not q:
            c.data = {**c.data, "checking": None}
            self.send(m.phone, t("no_checks", lang))
            return
        e = q[0]
        c.data = {**c.data, "checking": e.id}
        self.send(m.phone, readback_prompt(e, lang), CONSENT_BUTTONS[lang])

    def _answer_check(
        self, c: WaConversation, m: Inbound, user: User, biz: Business, low: str, lang: str
    ) -> None:
        entry_id = c.data.get("checking")
        e = self.db.get(LedgerEntry, entry_id) if entry_id else None
        if e is None:
            self._next_check(c, m, biz, lang)
            return
        if low in YES:
            confirm_entry(self.db, e, f"user:{user.id}", True)
        elif low in NO:
            confirm_entry(self.db, e, f"user:{user.id}", False)
        else:
            self.send(m.phone, readback_prompt(e, lang), CONSENT_BUTTONS[lang])
            return
        self.send(m.phone, t("saved", lang))
        self._next_check(c, m, biz, lang)

    def _passport(self, m: Inbound, biz: Business, lang: str) -> None:
        from app.modules.passport import service as passports
        from app.modules.passport.credential import qr_token, verify_url

        p = passports.latest(self.db, biz.id)
        if p is None:
            self.send(m.phone, t("no_passport", lang, url=get_settings().public_base_url))
            return
        ex = passports.explanation_for(self.db, p, lang)
        lines = [
            f"{ex['band_label']} ({p.vc_json['credentialSubject']['band']})",
            ex["headline"],
            *[f"• {x}" for x in ex["improve"]],
            verify_url(p.id, qr_token(p.vc_json)),
        ]
        self.send(m.phone, "\n".join(lines))

    def _user(self, phone: str) -> User:
        user = self.db.execute(select(User).where(User.phone == phone)).scalar_one_or_none()
        if user is None:
            raise DomainError("unknown user", "unknown_user")
        return user

    def _business(self, user: User) -> Business | None:
        return (
            self.db.execute(
                select(Business)
                .where(Business.owner_user_id == user.id, Business.deleted_at.is_(None))
                .order_by(Business.created_at)
            )
            .scalars()
            .first()
        )


def idle_too_long(c: WaConversation) -> bool:
    return utcnow() - c.updated_at > timedelta(days=30)
