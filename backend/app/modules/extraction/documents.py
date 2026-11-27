"""Address proof: an electricity, water, gas or phone bill, or a shop licence, photographed with
the live camera. AI reads the fields; rules decide whether it counts:

- the name on it is the business's, the owner's or the registered name (a bill in the
  landlord's name is common, so a different name is not counted but is not a fraud signal),
- the address is the shop's (its area or street), or at least its city when no address is known,
- a bill is recent (within 90 days of the photo); a licence has not expired.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.adapters.ai_schemas import DocumentExtraction
from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.core.dates import today_ist
from app.db.models import Business, EvidenceItem, User
from app.jobs import RetryableJobError
from app.modules.audit.service import record
from app.modules.extraction.service import _discard_original
from app.modules.notify import notify
from app.modules.reconciliation.names import similarity

BILLS = {"electricity_bill", "water_bill", "gas_bill", "phone_bill"}
LICENCES = {"shop_licence", "fssai_licence", "trade_licence"}
BILL_FRESH_DAYS = 90
NAME_MATCH = 60.0
PLACE_MATCH = 70.0
MIN_CONFIDENCE = 0.6

WHY = {
    "unreadable": (
        "दस्तावेज़ पढ़ा नहीं जा सका। साफ़ रोशनी में फिर फ़ोटो लें।",
        "We could not read the document. Take the photo again in good light.",
    ),
    "not_a_proof": (
        "यह बिल या दुकान का लाइसेंस नहीं लगता।",
        "This does not look like a bill or a shop licence.",
    ),
    "name": (
        "इस पर किसी और का नाम है (अक्सर मकान मालिक का)। आपके या दुकान के नाम वाला काग़ज़ लगाएँ।",
        "It is in someone else's name (often the landlord's). Add one in your or the shop's name.",
    ),
    "place": ("इस पर दुकान का पता नहीं है।", "The address on it is not the shop's."),
    "old": (
        "बिल 3 महीने से पुराना है। नया बिल लगाएँ।",
        "The bill is older than 3 months. Add a recent one.",
    ),
    "expired": ("लाइसेंस की तारीख निकल चुकी है।", "The licence has expired."),
}


@dataclass(frozen=True)
class DocumentCheck:
    accepted: bool
    reason: str | None  # a key of WHY when not accepted


def check(doc: DocumentExtraction, biz: Business, owner: User | None, today: date) -> DocumentCheck:
    if doc.confidence < MIN_CONFIDENCE:
        return DocumentCheck(False, "unreadable")
    if doc.doc_type not in BILLS | LICENCES:
        return DocumentCheck(False, "not_a_proof")
    names = [biz.name, biz.registration_name, owner.name if owner else None]
    if not doc.holder_name or not any(
        similarity(doc.holder_name, n) >= NAME_MATCH for n in names if n
    ):
        return DocumentCheck(False, "name")
    place = biz.address or biz.city
    if not doc.address or not place or similarity(place, doc.address) < PLACE_MATCH:
        return DocumentCheck(False, "place")
    if doc.doc_type in BILLS:
        if not doc.issue_date or not (
            today - timedelta(days=BILL_FRESH_DAYS) <= doc.issue_date <= today
        ):
            return DocumentCheck(False, "old")
    elif doc.valid_until and doc.valid_until < today:
        return DocumentCheck(False, "expired")
    return DocumentCheck(True, None)


def extract_document(db: Session, evidence_id: str, today: date | None = None) -> DocumentCheck:
    today = today or today_ist()
    ev = db.get(EvidenceItem, evidence_id)
    if ev is None:
        raise ValueError(f"no evidence {evidence_id}")
    if "document" in ev.meta:  # idempotent: already read
        d = ev.meta["document"]
        return DocumentCheck(bool(d.get("accepted")), d.get("reason"))
    biz = db.get(Business, ev.business_id)
    assert biz is not None
    if not ev.storage_key:
        return DocumentCheck(False, "unreadable")
    image = get_adapters().storage.get(ev.storage_key)
    try:
        result = get_adapters().ai.extract_document(image, ev.meta.get("mime", "image/jpeg"))
    except AdapterError as exc:
        ev.status = "extraction_failed"
        db.flush()
        raise RetryableJobError(str(exc)) from exc
    doc = result.value
    owner = db.get(User, biz.owner_user_id)
    outcome = check(doc, biz, owner, today)
    ev.status = "extracted" if outcome.accepted else "rejected"
    ev.meta = {
        **ev.meta,
        "document": {
            "doc_type": doc.doc_type,
            "issue_date": doc.issue_date.isoformat() if doc.issue_date else None,
            "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
            "confidence": doc.confidence,
            "accepted": outcome.accepted,
            "reason": outcome.reason,
            "provider": result.provider,
            "model": result.model,
            "sandbox": result.sandbox,
        },
    }
    _discard_original(db, ev, biz)
    record(
        db,
        "system",
        "evidence.document_checked",
        f"business:{biz.id}",
        {
            "evidence_id": ev.id,
            "doc_type": doc.doc_type,
            "accepted": outcome.accepted,
            "reason": outcome.reason,
        },
    )
    if owner is not None:
        if outcome.accepted:
            notify(
                db,
                owner,
                "address_proof",
                "पते का सबूत मान लिया गया। धन्यवाद!",
                "Your address proof was accepted. Thank you!",
            )
        elif outcome.reason:
            hi, en = WHY[outcome.reason]
            notify(
                db,
                owner,
                "address_proof",
                f"पते का सबूत नहीं माना गया: {hi}",
                f"Address proof not accepted: {en}",
            )
    return outcome
