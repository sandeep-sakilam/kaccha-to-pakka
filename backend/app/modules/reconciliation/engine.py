"""Reconciliation: how much of the owner's own record is backed by real money. Rules only.

A ledger entry matches a bank/UPI transaction when the direction and the exact amount agree, the
dates are within ±3 days, and the names agree (across Hindi and English). When amount and date
agree but the names are unclear, the owner is asked once ("Is Sharma ji the same as RAKESH
SHARMA?") and the answer is remembered. Several ledger entries may match one payment
(many-to-one) when the same party's entries on one day add up to it.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import BankTransaction, EvidenceItem, LedgerEntry, NameAlias, ReconMatch
from app.modules.audit.service import record
from app.modules.reconciliation.names import normalise, similarity

DATE_WINDOW_DAYS = 3
NAME_SURE = 80.0
NAME_MAYBE = 45.0
COUNTABLE_LEDGER = {"extracted", "confirmed"}
EXCLUDED_MONEY_EVIDENCE = {"on_hold", "rejected"}


@dataclass
class ReconStats:
    ledger_entries: int = 0
    ledger_value_paise: int = 0
    matched_entries: int = 0
    matched_value_paise: int = 0
    ambiguous: int = 0
    bank_txns: int = 0
    rules: dict[str, int] = field(default_factory=dict)

    @property
    def match_rate(self) -> float:
        return (
            self.matched_value_paise / self.ledger_value_paise if self.ledger_value_paise else 0.0
        )


def ledger_for(db: Session, business_id: str) -> list[LedgerEntry]:
    return list(
        db.execute(
            select(LedgerEntry)
            .join(EvidenceItem)
            .where(
                EvidenceItem.business_id == business_id, LedgerEntry.status.in_(COUNTABLE_LEDGER)
            )
        ).scalars()
    )


def money_for(db: Session, business_id: str) -> list[BankTransaction]:
    return list(
        db.execute(
            select(BankTransaction)
            .join(EvidenceItem)
            .where(
                EvidenceItem.business_id == business_id,
                EvidenceItem.status.notin_(EXCLUDED_MONEY_EVIDENCE),
            )
        ).scalars()
    )


def _cp_name(t: BankTransaction) -> str:
    return t.counterparty_name or t.counterparty_vpa or ""


def _aliases(db: Session, business_id: str) -> dict[tuple[str, str], bool]:
    rows = db.execute(select(NameAlias).where(NameAlias.business_id == business_id)).scalars()
    return {(a.party_key, a.counterparty_key): a.same for a in rows}


def _name_verdict(
    party: str | None, t: BankTransaction, aliases: dict[tuple[str, str], bool]
) -> tuple[str, float]:
    """('sure' | 'maybe' | 'no' | 'unknown', similarity)."""
    if not party:
        return "unknown", 0.0
    pk, ck = normalise(party), normalise(_cp_name(t))
    if (pk, ck) in aliases:
        return ("sure" if aliases[(pk, ck)] else "no"), 100.0 if aliases[(pk, ck)] else 0.0
    sim = max(similarity(party, t.counterparty_name), similarity(party, t.counterparty_vpa))
    if sim >= NAME_SURE:
        return "sure", sim
    if sim >= NAME_MAYBE:
        return "maybe", sim
    return "no", sim


LEARN_MIN_PAIRS = 3


def _cp_key(t: BankTransaction) -> str:
    return (t.counterparty_vpa or normalise(_cp_name(t))).lower()


def learn_aliases(
    entries: list[LedgerEntry],
    by_key: dict[tuple[str, int], list[BankTransaction]],
    owner_answers: dict[tuple[str, str], bool],
) -> set[tuple[str, str]]:
    """(party_key, counterparty_key) pairs seen together on >= 3 unique exact-amount matches,
    always with the same payer and never contradicted by the owner."""
    ledger_by_key: dict[tuple[str, int], list[LedgerEntry]] = defaultdict(list)
    for e in entries:
        if e.entry_date is not None:
            ledger_by_key[(e.direction, e.amount_paise)].append(e)
    seen: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        pk = normalise(e.party_text)
        if not pk or e.entry_date is None:
            continue
        cands = [
            t
            for t in by_key.get((e.direction, e.amount_paise), [])
            if abs((t.txn_date - e.entry_date).days) <= DATE_WINDOW_DAYS
        ]
        if len(cands) != 1:
            continue
        t = cands[0]
        back = [
            x
            for x in ledger_by_key[(t.direction, t.amount_paise)]
            if x.entry_date and abs((t.txn_date - x.entry_date).days) <= DATE_WINDOW_DAYS
        ]
        if len(back) == 1:
            seen[pk][_cp_key(t)] += 1
    out = set()
    for pk, per_cp in seen.items():
        if len(per_cp) == 1:
            ck, n = next(iter(per_cp.items()))
            if n >= LEARN_MIN_PAIRS and owner_answers.get((pk, ck)) is not False:
                out.add((pk, ck))
    return out


def _date_score(days: int) -> float:
    return 1.0 - days / (DATE_WINDOW_DAYS + 1)


def reconcile(db: Session, business_id: str, actor: str = "system") -> ReconStats:
    """Recompute all automatic matches. Idempotent; owner answers are kept as aliases."""
    entries = ledger_for(db, business_id)
    txns = money_for(db, business_id)
    entry_ids = [e.id for e in entries]
    all_entry_ids = [
        eid
        for (eid,) in db.execute(
            select(LedgerEntry.id).join(EvidenceItem).where(EvidenceItem.business_id == business_id)
        ).all()
    ]
    if all_entry_ids:
        db.execute(delete(ReconMatch).where(ReconMatch.ledger_entry_id.in_(all_entry_ids)))
    aliases = _aliases(db, business_id)
    stats = ReconStats(
        ledger_entries=len(entries),
        ledger_value_paise=sum(e.amount_paise for e in entries),
        bank_txns=len(txns),
    )
    by_key: dict[tuple[str, int], list[BankTransaction]] = defaultdict(list)
    for t in txns:
        by_key[(t.direction, t.amount_paise)].append(t)

    # 0. aliases learned from the owner's own history: when the same ledger name keeps meeting
    # the same payer on exact amounts and dates, with no other candidate either way, it is the
    # same party ("Pappu" is PRADEEP KUMAR). Exact amounts rarely coincide three times.
    learned = learn_aliases(entries, by_key, aliases)

    # 1. one-to-one candidates
    cands: list[tuple[float, str, LedgerEntry, BankTransaction]] = []
    for e in entries:
        if e.entry_date is None:
            continue
        for t in by_key.get((e.direction, e.amount_paise), []):
            days = abs((t.txn_date - e.entry_date).days)
            if days > DATE_WINDOW_DAYS:
                continue
            verdict, sim = _name_verdict(e.party_text, t, aliases)
            owner_said = (normalise(e.party_text), normalise(_cp_name(t))) in aliases
            if (
                verdict in {"no", "maybe"}
                and not owner_said
                and (normalise(e.party_text), _cp_key(t)) in learned
            ):
                verdict, sim = "learned", 100.0
            if verdict == "no":
                continue
            score = round(0.6 + 0.25 * _date_score(days) + 0.15 * sim / 100, 3)
            cands.append((score, verdict, e, t))
    cands.sort(key=lambda c: -c[0])
    used_e: set[str] = set()
    used_t: set[str] = set()
    ambiguous_e: set[str] = set()
    for score, verdict, e, t in cands:
        if e.id in used_e or t.id in used_t:
            continue
        if verdict in {"maybe", "unknown"}:
            # Only auto-accept a nameless match when it is the single candidate both ways.
            same_e = [c for c in cands if c[2].id == e.id and c[3].id not in used_t]
            same_t = [c for c in cands if c[3].id == t.id and c[2].id not in used_e]
            if verdict == "maybe" or len(same_e) > 1 or len(same_t) > 1:
                if e.id not in ambiguous_e:
                    db.add(
                        ReconMatch(
                            ledger_entry_id=e.id,
                            bank_txn_id=t.id,
                            score=score,
                            rule="needs_owner",
                            status="ambiguous",
                        )
                    )
                    ambiguous_e.add(e.id)
                continue
            rule = "amount_date_only"
            score = round(score - 0.15, 3)
        elif verdict == "learned":
            rule = "learned_alias"
        else:
            rule = "amount_date_name"
        db.add(
            ReconMatch(
                ledger_entry_id=e.id, bank_txn_id=t.id, score=score, rule=rule, status="matched"
            )
        )
        used_e.add(e.id)
        used_t.add(t.id)
        stats.matched_entries += 1
        stats.matched_value_paise += e.amount_paise
        stats.rules[rule] = stats.rules.get(rule, 0) + 1

    # 2. many-to-one: a party's entries on nearby days that add up to one payment
    left = [e for e in entries if e.id not in used_e and e.id not in ambiguous_e and e.entry_date]
    groups: dict[tuple[str, str], list[LedgerEntry]] = defaultdict(list)
    for e in left:
        groups[(normalise(e.party_text), e.direction)].append(e)
    for (pk, direction), group in groups.items():
        if not pk or len(group) < 2:
            continue
        for size in (2, 3):
            for combo in combinations(group, size):
                if any(c.id in used_e for c in combo):
                    continue
                total = sum(c.amount_paise for c in combo)
                dates = [c.entry_date for c in combo if c.entry_date]
                for t in by_key.get((direction, total), []):
                    if t.id in used_t or not dates:
                        continue
                    if max(abs((t.txn_date - d).days) for d in dates) > DATE_WINDOW_DAYS:
                        continue
                    if _name_verdict(combo[0].party_text, t, aliases)[0] != "sure":
                        continue
                    for c in combo:
                        db.add(
                            ReconMatch(
                                ledger_entry_id=c.id,
                                bank_txn_id=t.id,
                                score=0.75,
                                rule="many_to_one",
                                status="matched",
                            )
                        )
                        used_e.add(c.id)
                        stats.matched_entries += 1
                        stats.matched_value_paise += c.amount_paise
                    used_t.add(t.id)
                    stats.rules["many_to_one"] = stats.rules.get("many_to_one", 0) + 1
                    break
    # 3. one-to-many (partial payments): one ledger entry paid in two instalments by the same
    # payer inside the window ("Sharma ji 10,000" = 6,000 + 4,000 by UPI).
    by_cp: dict[tuple[str, str], list[BankTransaction]] = defaultdict(list)
    for t in txns:
        if t.id not in used_t:
            by_cp[(t.direction, _cp_key(t))].append(t)
    for e in entries:
        if e.id in used_e or e.id in ambiguous_e or e.entry_date is None:
            continue
        found = False
        for (direction, ck), pool in by_cp.items():
            if direction != e.direction or found:
                continue
            near = [
                t
                for t in pool
                if t.id not in used_t and abs((t.txn_date - e.entry_date).days) <= DATE_WINDOW_DAYS
            ]
            for a, b in combinations(near, 2):
                if a.amount_paise + b.amount_paise != e.amount_paise:
                    continue
                verdict, _ = _name_verdict(e.party_text, a, aliases)
                owner_said = (normalise(e.party_text), normalise(_cp_name(a))) in aliases
                if verdict != "sure" and (
                    owner_said or (normalise(e.party_text), ck) not in learned
                ):
                    continue
                for t in (a, b):
                    db.add(
                        ReconMatch(
                            ledger_entry_id=e.id,
                            bank_txn_id=t.id,
                            score=0.7,
                            rule="one_to_many",
                            status="matched",
                        )
                    )
                    used_t.add(t.id)
                used_e.add(e.id)
                stats.matched_entries += 1
                stats.matched_value_paise += e.amount_paise
                stats.rules["one_to_many"] = stats.rules.get("one_to_many", 0) + 1
                found = True
                break
    stats.ambiguous = len(ambiguous_e - used_e)
    db.flush()
    record(
        db,
        actor,
        "recon.run",
        f"business:{business_id}",
        {
            "entries": stats.ledger_entries,
            "matched": stats.matched_entries,
            "ambiguous": stats.ambiguous,
            "match_rate": round(stats.match_rate, 3),
            "ledger_considered": len(entry_ids),
        },
    )
    return stats


@dataclass(frozen=True)
class Question:
    ledger_entry_id: str
    bank_txn_id: str
    party_text: str
    counterparty_name: str
    prompt_hi: str
    prompt_en: str


def questions(db: Session, business_id: str) -> list[Question]:
    rows = db.execute(
        select(ReconMatch, LedgerEntry, BankTransaction)
        .join(LedgerEntry, ReconMatch.ledger_entry_id == LedgerEntry.id)
        .join(BankTransaction, ReconMatch.bank_txn_id == BankTransaction.id)
        .join(EvidenceItem, LedgerEntry.evidence_id == EvidenceItem.id)
        .where(EvidenceItem.business_id == business_id, ReconMatch.status == "ambiguous")
    ).all()
    seen: set[tuple[str, str]] = set()
    out = []
    for _, e, t in rows:
        party = e.party_text or "?"
        cp = _cp_name(t)
        key = (normalise(party), normalise(cp))
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Question(
                e.id,
                t.id,
                party,
                cp,
                f"क्या {party} और {cp} एक ही हैं?",
                f"Is {party} the same as {cp}?",
            )
        )
    return out


def answer(
    db: Session, business_id: str, party_text: str, counterparty_name: str, same: bool, actor: str
) -> ReconStats:
    pk, ck = normalise(party_text), normalise(counterparty_name)
    existing = db.execute(
        select(NameAlias).where(
            NameAlias.business_id == business_id,
            NameAlias.party_key == pk,
            NameAlias.counterparty_key == ck,
        )
    ).scalar_one_or_none()
    if existing:
        existing.same = same
    else:
        db.add(NameAlias(business_id=business_id, party_key=pk, counterparty_key=ck, same=same))
    db.flush()
    record(
        db,
        actor,
        "recon.owner_answer",
        f"business:{business_id}",
        {"same": same, "party": pk[:40], "counterparty": ck[:40]},
    )
    return reconcile(db, business_id, actor)
