"""Owner notifications: WhatsApp first, SMS when WhatsApp is down. Every message is stored."""

import logging

from sqlalchemy.orm import Session

from app.adapters.errors import AdapterError
from app.adapters.registry import get_adapters
from app.db.models import Notification, User

log = logging.getLogger(__name__)


def notify(db: Session, user: User, kind: str, text_hi: str, text_en: str) -> Notification:
    text = text_hi if user.language == "hi" else text_en
    adapters = get_adapters()
    channel = "whatsapp"
    try:
        adapters.whatsapp.send(user.phone, text)
    except AdapterError:
        channel = "sms"
        try:
            adapters.sms.send(user.phone, text)
        except AdapterError:
            channel = "app"
            log.warning("could not message user %s; kept in app", user.id)
    n = Notification(user_id=user.id, channel=channel, text=text, kind=kind)
    db.add(n)
    db.flush()
    return n
