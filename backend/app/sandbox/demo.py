"""Demo data: three fictional Indore businesses and one scripted fraud attempt (Sandbox).

All people, phone numbers, UPI IDs and businesses here are fictional. Phones use the
+91 90000 000xx range and every business is marked is_sandbox.
"""

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.payments import MockPaymentGateway
from app.adapters.sandbox_images import ledger_png
from app.db.base import utcnow
from app.db.models import Business, EvidenceItem, PresenceRequest, User
from app.modules.attestations import claims, penny_drop, selection
from app.modules.audit.service import record
from app.modules.consent import service as consent
from app.modules.evidence.service import CaptureIn, ingest_capture
from app.modules.identity.security import hash_pin
from app.modules.passport.service import issue
from app.modules.statements.money import MoneyTxn, store_transactions
from app.modules.statements.service import ingest_statement
from app.sandbox.statements import StatementTxn, upi_statement_pdf

DEMO_PIN = "4826"
INDORE = {
    "rajwada": (22.7186, 75.8553),
    "sanyogitaganj": (22.7239, 75.8701),
    "khajrana": (22.7330, 75.9010),
    "bhawarkua": (22.6926, 75.8670),
}


@dataclass
class Partner:
    vpa: str
    name: str
    phone: str
    direction: str  # out = supplier we pay, in = customer who pays us
    every_days: int
    amount_rupees: tuple[int, int]


@dataclass
class DemoBusiness:
    key: str
    owner_name: str
    phone: str
    name: str
    category: str
    area: str
    started_year: int
    women_owned: bool
    money: str  # aa | upi_pdf
    months: int
    season: dict[int, float]
    partners: list[Partner]
    customers: int = 25
    daily_sales: tuple[int, int] = (200, 2500)
    confirm: int = 0  # how many partners confirm
    ledger_pages: int = 3
    presence_done: int = 3
    notes: list[str] = field(default_factory=list)


BUSINESSES = [
    DemoBusiness(
        "kirana",
        "Ramesh Sharma",
        "+919000000001",
        "Sharma Kirana Store",
        "kirana",
        "rajwada",
        2009,
        False,
        "aa",
        14,
        {10: 1.3, 11: 1.4},
        [
            Partner(
                "gupta.traders@oksbi", "GUPTA TRADERS", "+919000000011", "out", 7, (14000, 22000)
            ),
            Partner(
                "malwa.oilmills@okhdfc",
                "MALWA OIL MILLS",
                "+919000000012",
                "out",
                14,
                (18000, 26000),
            ),
            Partner(
                "indore.besan@okicici",
                "INDORE BESAN BHANDAR",
                "+919000000013",
                "out",
                10,
                (9000, 15000),
            ),
        ],
        confirm=3,
        notes=["Strong: bank linked, ledger matches, 3 suppliers confirmed"],
    ),
    DemoBusiness(
        "namkeen",
        "Meena Devi Yadav",
        "+919000000002",
        "Meena Namkeen Udyog",
        "namkeen",
        "sanyogitaganj",
        2016,
        True,
        "aa",
        24,
        {10: 3.0, 11: 3.5, 3: 1.4, 4: 0.6, 7: 0.6},
        [
            Partner(
                "sethi.sev.traders@oksbi",
                "SETHI SEV TRADERS",
                "+919000000021",
                "in",
                6,
                (8000, 16000),
            ),
            Partner(
                "annapurna.besan@okaxis",
                "ANNAPURNA BESAN MILL",
                "+919000000022",
                "out",
                9,
                (12000, 20000),
            ),
            Partner(
                "malwa.oilmills@okhdfc",
                "MALWA OIL MILLS",
                "+919000000012",
                "out",
                15,
                (10000, 16000),
            ),
        ],
        confirm=2,
        ledger_pages=2,
        notes=["Diwali-seasonal: compared with last Diwali, not a flat average"],
    ),
    DemoBusiness(
        "tailor",
        "Salim Ansari",
        "+919000000003",
        "Ansari Tailors",
        "tailor",
        "khajrana",
        2014,
        False,
        "upi_pdf",
        8,
        {11: 2.2, 12: 2.4, 1: 2.0, 2: 1.8, 6: 0.5},
        [
            Partner(
                "jain.cloth.house@okhdfc",
                "JAIN CLOTH HOUSE",
                "+919000000031",
                "out",
                12,
                (6000, 11000),
            ),
            Partner(
                "raymond.dealer.indore@oksbi",
                "SHREE FABRICS",
                "+919000000032",
                "out",
                20,
                (4000, 8000),
            ),
        ],
        customers=18,
        daily_sales=(300, 3000),
        confirm=1,
        ledger_pages=1,
        presence_done=2,
        notes=["UPI statement PDF only, so the band is capped at C"],
    ),
]

FRAUD = DemoBusiness(
    "fraud",
    "Raju Verma",
    "+919000000004",
    "Raju General Store",
    "kirana",
    "bhawarkua",
    2021,
    False,
    "aa",
    6,
    {},
    [
        Partner(
            "agrawal.wholesale@okhdfc",
            "AGRAWAL WHOLESALE",
            "+919000000041",
            "out",
            8,
            (9000, 14000),
        )
    ],
    customers=12,
    daily_sales=(150, 1200),
    confirm=0,
    ledger_pages=0,
    presence_done=1,
    notes=["Scripted fraud: the owner sends the supplier invite to a friend"],
)
FRIEND_PHONE = "+919000000099"
FRIEND_VPA = "pappu.friend@okaxis"
FRIEND_NAME = "PAPPU KUMAR"


def _user(db: Session, d: DemoBusiness) -> User:
    u = User(
        phone=d.phone,
        name=d.owner_name,
        language="hi",
        roles=["owner"],
        gender="female" if d.women_owned else "male",
        pin_hash=hash_pin(DEMO_PIN),
        kyc_status="verified_sandbox",
        device_ids=[],
    )
    db.add(u)
    db.flush()
    return u


def _money_rows(d: DemoBusiness, rng: random.Random, today: date) -> list[MoneyTxn]:
    rows: list[MoneyTxn] = []
    start = today - timedelta(days=30 * d.months)
    day = start
    n = 0
    while day <= today - timedelta(days=2):
        boost = d.season.get(day.month, 1.0)
        for _ in range(rng.randint(2, 5)):
            c = rng.randint(1, d.customers)
            amt = int(rng.randint(*d.daily_sales) * boost) * 100
            n += 1
            rows.append(
                MoneyTxn(
                    day,
                    amt,
                    "in",
                    f"cust{c:02d}.{d.key}@okaxis",
                    f"CUSTOMER {c:02d}",
                    f"6{n:011d}",
                    None,
                    "UPI",
                    None,
                )
            )
        for p in d.partners:
            if (day - start).days % p.every_days == 0:
                amt = int(rng.randint(*p.amount_rupees) * boost) * 100
                n += 1
                rows.append(
                    MoneyTxn(
                        day,
                        amt,
                        p.direction,
                        p.vpa,
                        p.name,
                        f"6{n:011d}",
                        None,
                        f"UPI/{p.vpa}",
                        None,
                    )
                )
        day += timedelta(days=1)
    return rows


def _ledger_pages(
    db: Session, u: User, biz: Business, d: DemoBusiness, rows: list[MoneyTxn], rng: random.Random
) -> None:
    supplier_rows = [r for r in rows if r.counterparty_vpa in {p.vpa for p in d.partners}]
    recent = sorted(supplier_rows, key=lambda r: r.txn_date)[-8 * d.ledger_pages :]
    for page in range(d.ledger_pages):
        chunk = recent[page * 8 : (page + 1) * 8]
        entries: list[dict[str, Any]] = []
        for r in chunk:
            party = next(p.name for p in d.partners if p.vpa == r.counterparty_vpa)
            short = party.split()[0].title() + (" ji" if r.direction == "out" else "")
            entries.append(
                {
                    "entry_date": str(r.txn_date + timedelta(days=rng.choice([0, 0, 1]))),
                    "party_text": short,
                    "amount_paise": r.amount_paise,
                    "direction": r.direction,
                    "confidence": {"date": 0.92, "party": 0.9, "amount": 0.95, "direction": 0.97},
                }
            )
        cash_day = chunk[-1].txn_date if chunk else date.today()
        entries.append(
            {
                "entry_date": str(cash_day),
                "party_text": "Nagad bikri",
                "amount_paise": rng.randint(20, 60) * 10000,
                "direction": "in",
                "confidence": {"date": 0.9, "party": 0.9, "amount": 0.9, "direction": 0.95},
            }
        )
        out_total = sum(e["amount_paise"] for e in entries if e["direction"] == "out")
        in_total = sum(e["amount_paise"] for e in entries if e["direction"] == "in")
        img = ledger_png(
            {
                "entries": entries,
                "page_total_paise": in_total - out_total if in_total >= out_total else None,
                "page_total_direction": "net" if in_total >= out_total else None,
                "script": "devanagari",
                "page_confidence": 0.9,
            },
            title=f"{biz.name} - Bahi Khata page {page + 1}",
            noise=f"{d.key}-{page}" * 8,
        )
        ingest_capture(
            db,
            u,
            biz,
            CaptureIn(
                kind="ledger_page",
                mime="image/png",
                data=img,
                captured_at=utcnow(),
                idempotency_key=f"demo-{d.key}-ledger-{page}",
                device_id=f"demo-{d.key}",
                geo=None,
                client_quality={"blur": 400},
            ),
            actor="seed",
        )


def _shop(db: Session, u: User, biz: Business, d: DemoBusiness) -> None:
    lat, lng = INDORE[d.area]
    img = ledger_png(
        {"entries": [], "page_confidence": 0.9},
        title=f"{biz.name} (shop front)",
        noise=f"shop-{d.key}" * 10,
    )
    ingest_capture(
        db,
        u,
        biz,
        CaptureIn(
            kind="shop_front",
            mime="image/png",
            data=img,
            captured_at=utcnow(),
            idempotency_key=f"demo-{d.key}-shop",
            device_id=f"demo-{d.key}",
            geo={"lat": lat, "lng": lng, "accuracy_m": 12},
            client_quality={},
        ),
        actor="seed",
    )
    now = utcnow()
    for i in range(d.presence_done):
        at = now - timedelta(days=6 * (i + 1), hours=3)
        db.add(
            PresenceRequest(
                business_id=biz.id,
                requested_at=at,
                due_by=at + timedelta(hours=24),
                status="done",
                result={"reasons": [], "distance_m": 18.0 + i},
            )
        )
    db.flush()


def _confirmations(db: Session, u: User, biz: Business, d: DemoBusiness) -> None:
    top = selection.top_counterparties(db, biz.id)
    by_vpa = {t.vpa_or_account: t for t in top}
    gw = penny_drop.gateway_for(db, biz.id)
    for p in d.partners[: d.confirm]:
        cp = by_vpa.get(p.vpa)
        if cp is None:
            continue
        inv = selection.invite(db, u, biz, cp.counterparty_id, p.phone, "hi")
        penny_drop.start(db, inv)
        assert isinstance(gw, MockPaymentGateway), "demo seed needs the simulated gateway"
        gw.simulate_payment(inv.penny_ref or "", p.vpa, p.name)
        penny_drop.check(db, inv)
        mm = claims.money_match(
            db, biz.id, p.vpa, claims.ClaimIn("supplier", "5+", "0-10k", "on_time")
        )
        claims.submit(
            db,
            inv,
            claims.ClaimIn(
                relationship=mm.actual_relationship,
                years_trading="5+",
                monthly_value=mm.actual_bucket,
                payment_behaviour="on_time",
                business_name=p.name.title(),
            ),
            p.name,
        )


def seed_business(db: Session, d: DemoBusiness, today: date | None = None) -> Business:
    today = today or date.today()
    rng = random.Random(d.key)  # noqa: S311  (deterministic demo data)
    u = _user(db, d)
    for purpose in ("build_passport",):
        consent.grant(db, u, purpose)
    lat, lng = INDORE[d.area]
    biz = Business(
        owner_user_id=u.id,
        name=d.name,
        category=d.category,
        started_on=date(d.started_year, 4, 1),
        address=d.area.title(),
        city="Indore",
        sells=d.category,
        women_owned=d.women_owned,
        is_sandbox=True,
        geo_home={"lat": lat, "lng": lng, "source": "seed"},
    )
    db.add(biz)
    db.flush()
    for purpose in ("aa_fetch", "monthly_refresh", "presence_location"):
        consent.grant(db, u, purpose, biz.id, {"sandbox": True})
    rows = _money_rows(d, rng, today)
    if d.money == "aa":
        ev = EvidenceItem(
            business_id=biz.id,
            type="aa_fetch",
            source="aa:mock-aa",
            status="parsed",
            captured_at=utcnow(),
            meta={
                "holder_name": d.owner_name.upper(),
                "bank": "Sandbox Bank",
                "account_ref": "XXXX" + d.phone[-4:],
                "sandbox": True,
            },
        )
        db.add(ev)
        db.flush()
        store_transactions(db, biz.id, ev, rows)
    else:
        pdf = upi_statement_pdf(
            d.owner_name.upper(),
            d.phone,
            [
                StatementTxn(
                    r.txn_date,
                    r.narration or "",
                    r.amount_paise,
                    r.direction,
                    r.utr or "",
                    r.counterparty_vpa,
                    r.counterparty_name,
                )
                for r in rows
            ],
        )
        ingest_statement(db, u, biz, pdf, "upi-statement.pdf", f"demo-{d.key}-upi-pdf")
    _shop(db, u, biz, d)
    if d.ledger_pages:
        _ledger_pages(db, u, biz, d, rows, rng)
    _confirmations(db, u, biz, d)
    record(db, "seed", "demo.seeded", f"business:{biz.id}", {"key": d.key})
    return biz


@dataclass
class FraudSetup:
    business: Business
    invite_token: str


def seed_fraud(db: Session, today: date | None = None) -> FraudSetup:
    biz = seed_business(db, FRAUD, today)
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    supplier = next(
        t
        for t in selection.top_counterparties(db, biz.id)
        if t.vpa_or_account == FRAUD.partners[0].vpa
    )
    # The owner routes the real supplier's invite to a friend's phone.
    inv = selection.invite(db, owner, biz, supplier.counterparty_id, FRIEND_PHONE, "hi")
    return FraudSetup(biz, inv.token)


def play_fraud(db: Session, token: str) -> str:
    """The friend opens the link and pays ₹1 from their own UPI account."""
    inv = selection.by_token(db, token)
    req = penny_drop.start(db, inv)
    gw = penny_drop.gateway_for(db, inv.business_id)
    assert isinstance(gw, MockPaymentGateway)
    gw.simulate_payment(req.ref, FRIEND_VPA, FRIEND_NAME)
    return penny_drop.check(db, inv).status


def seed_all(db: Session, today: date | None = None) -> dict[str, object]:
    out: dict[str, object] = {}
    for d in BUSINESSES:
        biz = seed_business(db, d, today)
        p = issue(db, biz, "seed")
        out[d.key] = {
            "business_id": biz.id,
            "name": d.name,
            "phone": d.phone,
            "band": p.vc_json["credentialSubject"]["band"],
            "status": p.status,
        }
    fraud = seed_fraud(db, today)
    # The friend's attempt is played once, then Raju's passport is issued: it is on hold.
    first_attempt = play_fraud(db, fraud.invite_token)
    raju = issue(db, fraud.business, "seed")
    # A second invite to the same friend, left open, so the video can show the attempt live.
    replay = replay_invite(db, fraud.business)
    out["fraud"] = {
        "business_id": fraud.business.id,
        "name": FRAUD.name,
        "phone": FRAUD.phone,
        "first_attempt": first_attempt,
        "passport_status": raju.status,
        "band": raju.vc_json["credentialSubject"]["band"],
        "replay_invite_token": replay,
        "friend_vpa": FRIEND_VPA,
        "friend_name": FRIEND_NAME,
    }
    return out


def replay_invite(db: Session, biz: Business) -> str:
    owner = db.get(User, biz.owner_user_id)
    assert owner is not None
    supplier = next(
        t
        for t in selection.top_counterparties(db, biz.id)
        if t.vpa_or_account == FRAUD.partners[0].vpa
    )
    return selection.invite(db, owner, biz, supplier.counterparty_id, FRIEND_PHONE, "hi").token


def now_ist() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="minutes")
