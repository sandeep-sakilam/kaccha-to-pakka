"""Reconciliation: how much of the owner's own record is backed by real money. Rules only.

A ledger entry matches a bank/UPI transaction when the direction and the exact amount agree, the
dates are within ±3 days, and the names agree (across Hindi and English). When amount and date
agree but the names are unclear, the owner is asked once ("Is Sharma ji the same as RAKESH
SHARMA?") and the answer is remembered. Several ledger entries may match one payment
(many-to-one) when the same party's entries on one day add up to it.

Credit books (udhaar) work per customer instead. "Credit given" entries add to the customer's
balance; money from that customer (a bank or UPI payment from them, or a repayment written in the
ledger) clears the oldest dues first, up to 90 days after each due. A payment that exactly
clears whole dues ("September + October together") is a strong match; one that clears part of
them is a weaker one; one larger than everything owed is not a repayment. Cash entries are never
looked for in the bank.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import BankTransaction, EvidenceItem, LedgerEntry, NameAlias, ReconMatch
from app.modules.audit.service import record
from app.modules.reconciliation.names import normalise, similarity

DATE_WINDOW_DAYS = 3
CREDIT_WINDOW_DAYS = 90
NAME_SURE = 80.0
NAME_MAYBE = 45.0
COUNTABLE_LEDGER = {"extracted", "confirmed"}
EXCLUDED_MONEY_EVIDENCE = {"on_hold", "rejected"}


@dataclass
class CreditStats:
    """A credit book, per business. Amounts in paise."""

    entries: int = 0
    customers: int = 0
    repeat_customers: int = 0  # credit given in two or more different months
    given_paise: int = 0
    repaid_bank_exact_paise: int = 0  # payments that cleared whole dues
    repaid_bank_partial_paise: int = 0  # payments that cleared part of the dues
    repaid_cash_paise: int = 0  # repayments the owner wrote as cash
    repaid_written_paise: int = 0  # written repayments not found in the bank (not marked cash)
    outstanding_paise: int = 0
    days_to_repay: list[int] = field(default_factory=list)

    @property
    def repaid_bank_paise(self) -> int:
        return self.repaid_bank_exact_paise + self.repaid_bank_partial_paise

    @property
    def bank_repaid_rate(self) -> float:
        """Share of credit given that came back through the bank; partial clearing counts half."""
        if not self.given_paise:
            return 0.0
        backed = self.repaid_bank_exact_paise + self.repaid_bank_partial_paise / 2
        return backed / self.given_paise

    @property
    def median_days_to_repay(self) -> int | None:
        d = sorted(self.days_to_repay)
        return d[len(d) // 2] if d else None


@dataclass
class ReconStats:
    ledger_entries: int = 0
    ledger_value_paise: int = 0
    matched_entries: int = 0
    matched_value_paise: int = 0
    ambiguous: int = 0
    bank_txns: int = 0
    rules: dict[str, int] = field(default_factory=dict)
    cash_entries: int = 0  # written as cash: never looked for in the bank
    credit: CreditStats = field(default_factory=CreditStats)  # credit given to customers
    supplier_credit: CreditStats = field(default_factory=CreditStats)  # goods bought on credit

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


VPA_KEY = "vpa:"  # an owner's answer remembered by UPI ID: the son's phone, whatever its name


def owner_said(aliases: dict[tuple[str, str], bool], pk: str, t: BankTransaction) -> bool | None:
    """The owner's answer for this ledger name and this payer: by UPI ID first, then by name."""
    if t.counterparty_vpa:
        said = aliases.get((pk, VPA_KEY + t.counterparty_vpa.lower()))
        if said is not None:
            return said
    return aliases.get((pk, normalise(_cp_name(t))))


def _name_verdict(
    party: str | None, t: BankTransaction, aliases: dict[tuple[str, str], bool]
) -> tuple[str, float]:
    """One of:
    owner    the owner said this payer is this party
    no       the owner said it is not
    sure     the names agree
    maybe    the names share a word but differ ("Rakesh Sharma" / "AMIT SHARMA"): ask
    differs  both have names with no word in common: ask only if it is the one candidate
    unknown  one side has no name (a ledger line without one, a number-only UPI ID)
    """
    if not party:
        return "unknown", 0.0
    said = owner_said(aliases, normalise(party), t)
    if said is not None:
        return ("owner", 100.0) if said else ("no", 0.0)
    if not (normalise(t.counterparty_name) or normalise(t.counterparty_vpa)):
        return "unknown", 0.0  # e.g. 9826012345@ybl with no name: nothing to compare
    sim = max(similarity(party, t.counterparty_name), similarity(party, t.counterparty_vpa))
    if sim >= NAME_SURE:
        return "sure", sim
    if sim >= NAME_MAYBE:
        return "maybe", sim
    return "differs", sim


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
            if (
                n >= LEARN_MIN_PAIRS
                and owner_answers.get((pk, ck)) is not False
                and owner_answers.get((pk, VPA_KEY + ck)) is not False
            ):
                out.add((pk, ck))
    return out


def _date_score(days: int) -> float:
    return 1.0 - days / (DATE_WINDOW_DAYS + 1)


def reconcile(db: Session, business_id: str, actor: str = "system") -> ReconStats:
    """Recompute all automatic matches. Idempotent; owner answers are kept as aliases."""
    countable = ledger_for(db, business_id)
    txns = money_for(db, business_id)
    entry_ids = [e.id for e in countable]
    credit_entries = [e for e in countable if e.kind == "credit_given"]
    supplier_dues = [e for e in countable if e.kind == "credit_taken"]
    cash = [e for e in countable if e.kind == "money" and e.paid_by == "cash"]
    # Only money that could be in the bank is looked for there.
    entries = [e for e in countable if e.kind == "money" and e.paid_by != "cash"]
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
        cash_entries=len(cash),
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
            if verdict in {"differs", "maybe"} and (normalise(e.party_text), _cp_key(t)) in learned:
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
        if verdict in {"maybe", "unknown", "differs"}:
            # Only auto-accept a nameless match when it is the single candidate both ways.
            # Names that differ are asked about only then; otherwise they are too weak to ask.
            same_e = [c for c in cands if c[2].id == e.id and c[3].id not in used_t]
            same_t = [c for c in cands if c[3].id == t.id and c[2].id not in used_e]
            unique = len(same_e) == 1 and len(same_t) == 1
            if verdict == "differs" and not unique:
                continue
            if verdict in {"maybe", "differs"} or not unique:
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
        elif verdict == "owner":
            rule = "owner_confirmed"  # rests on the owner's own answer: counted separately
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
                    if _name_verdict(combo[0].party_text, t, aliases)[0] not in {"sure", "owner"}:
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
                learned_ok = (
                    verdict in {"maybe", "differs"} and (normalise(e.party_text), ck) in learned
                )
                if verdict not in {"sure", "owner"} and not learned_ok:
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
    # 4. credit books: running balance per customer, oldest dues first
    stats.credit = _credit_book(
        db, credit_entries, entries + cash, txns, used_e, used_t, aliases, learned, stats.rules
    )
    # 5. the same for goods bought on credit: payments to the supplier clear the oldest dues
    stats.supplier_credit = _credit_book(
        db,
        supplier_dues,
        entries + cash,
        txns,
        used_e,
        used_t,
        aliases,
        learned,
        stats.rules,
        side="supplier",
    )
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
            "credit_entries": stats.credit.entries,
            "credit_repaid_bank_paise": stats.credit.repaid_bank_paise,
            "supplier_credit_entries": stats.supplier_credit.entries,
        },
    )
    return stats


def _credit_book(
    db: Session,
    dues_entries: list[LedgerEntry],
    money_entries: list[LedgerEntry],
    txns: list[BankTransaction],
    used_e: set[str],
    used_t: set[str],
    aliases: dict[tuple[str, str], bool],
    learned: set[tuple[str, str]],
    rules: dict[str, int],
    side: str = "customer",
) -> CreditStats:
    """Apply each customer's repayments to their dues, oldest first. Rules only. With
    side="supplier" the dues are goods bought on credit and the repayments are money paid out to
    that supplier."""
    money_dir = "in" if side == "customer" else "out"
    rule_exact, rule_part = (
        ("credit_repaid", "credit_repaid_partial")
        if side == "customer"
        else ("supplier_paid", "supplier_paid_partial")
    )
    cs = CreditStats(
        entries=len(dues_entries), given_paise=sum(e.amount_paise for e in dues_entries)
    )
    by_customer: dict[str, list[LedgerEntry]] = defaultdict(list)
    undated = 0
    for e in dues_entries:
        pk = normalise(e.party_text)
        if pk and e.entry_date is not None:
            by_customer[pk].append(e)
        else:
            undated += e.amount_paise  # no name or date: it can never be matched
    written: dict[str, list[LedgerEntry]] = defaultdict(list)
    for e in money_entries:
        pk = normalise(e.party_text)
        if e.direction == money_dir and e.entry_date is not None and pk in by_customer:
            written[pk].append(e)
    cs.customers = len(by_customer)
    cs.repeat_customers = sum(
        1
        for dues in by_customer.values()
        if len({(d.entry_date.year, d.entry_date.month) for d in dues if d.entry_date}) >= 2
    )
    outstanding = undated
    for pk, dues in sorted(by_customer.items()):
        dues.sort(key=lambda d: (d.entry_date, d.id))
        left = {d.id: d.amount_paise for d in dues}
        first = dues[0].entry_date
        assert first is not None
        # (date, order, amount, via, bank txn): written repayments first on a given day
        events: list[tuple[date, int, int, str, BankTransaction | None]] = []
        for w in written[pk]:
            assert w.entry_date is not None
            via = "bank" if w.id in used_e else "cash" if w.paid_by == "cash" else "written"
            events.append((w.entry_date, 0, w.amount_paise, via, None))
        for bt in txns:
            if bt.direction != money_dir or bt.id in used_t or bt.txn_date < first:
                continue
            if any(
                w.amount_paise == bt.amount_paise
                and w.entry_date is not None
                and abs((bt.txn_date - w.entry_date).days) <= DATE_WINDOW_DAYS
                for w in written[pk]
            ):
                continue  # the same repayment the owner already wrote (e.g. as cash): count once
            verdict, _ = _name_verdict(dues[0].party_text, bt, aliases)
            learned_ok = verdict in {"maybe", "differs"} and (pk, _cp_key(bt)) in learned
            if verdict in {"sure", "owner"} or learned_ok:
                events.append((bt.txn_date, 1, bt.amount_paise, "bank_txn", bt))
        ordered = sorted(events, key=lambda x: (x[0], x[1], x[2]))
        # Pass 1: written repayments and bank payments that clear whole dues exactly. Pass 2:
        # part payments against what is still owed. Doing exact ones first keeps one small
        # payment (perhaps a spot purchase) from spoiling the exact matches after it.
        for exact_pass in (True, False):
            for when, _, amount, via, t in ordered:
                if t is not None and t.id in used_t:
                    continue
                if via != "bank_txn" and not exact_pass:
                    continue  # written repayments were all applied in pass 1
                eligible = [
                    d
                    for d in dues
                    if left[d.id] > 0
                    and d.entry_date is not None
                    and 0 <= (when - d.entry_date).days <= CREDIT_WINDOW_DAYS
                ]
                open_total = sum(left[d.id] for d in eligible)
                if not eligible or (via == "bank_txn" and amount > open_total):
                    continue  # more than is owed: a purchase paid on the spot, not a repayment
                exact = False
                acc = 0
                for d in eligible:
                    acc += left[d.id]
                    if acc >= amount:
                        exact = acc == amount
                        break
                if via == "bank_txn" and exact != exact_pass:
                    continue
                remaining = amount
                for d in eligible:
                    if remaining == 0:
                        break
                    take = min(remaining, left[d.id])
                    left[d.id] -= take
                    remaining -= take
                    if via == "bank_txn" and t is not None:
                        rule = rule_exact if exact else rule_part
                        db.add(
                            ReconMatch(
                                ledger_entry_id=d.id,
                                bank_txn_id=t.id,
                                score=0.8 if exact else 0.6,
                                rule=rule,
                                status="matched",
                                amount_paise=take,
                            )
                        )
                        rules[rule] = rules.get(rule, 0) + 1
                    if via == "bank" or (via == "bank_txn" and exact):
                        cs.repaid_bank_exact_paise += take
                    elif via == "bank_txn":
                        cs.repaid_bank_partial_paise += take
                    elif via == "cash":
                        cs.repaid_cash_paise += take
                    else:
                        cs.repaid_written_paise += take
                    if left[d.id] == 0 and d.entry_date is not None:
                        cs.days_to_repay.append((when - d.entry_date).days)
                if t is not None:
                    used_t.add(t.id)
        outstanding += sum(left.values())
    cs.outstanding_paise = outstanding
    return cs


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
        # One question per name pair; a payer with no name is asked about per UPI ID.
        key = (normalise(party), normalise(cp) or (t.counterparty_vpa or "").lower())
        if key in seen:
            continue
        seen.add(key)
        shown = t.counterparty_name or _masked(t.counterparty_vpa or cp)
        out.append(
            Question(
                e.id,
                t.id,
                party,
                cp,
                f"क्या {party} और {shown} एक ही हैं?",
                f"Is {party} the same as {shown}?",
            )
        )
    return out


def _masked(vpa: str) -> str:
    """98••••2345@ybl: a phone number used as a UPI ID is not shown in full."""
    if "@" not in vpa:
        return vpa
    handle, bank = vpa.split("@", 1)
    if handle.isdigit() and len(handle) > 6:
        handle = handle[:2] + "•" * (len(handle) - 6) + handle[-4:]
    return f"{handle}@{bank}"


def _remember(db: Session, business_id: str, pk: str, ck: str, same: bool) -> None:
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


def answer(
    db: Session,
    business_id: str,
    party_text: str,
    counterparty_name: str,
    same: bool,
    actor: str,
    bank_txn_id: str | None = None,
) -> ReconStats:
    """Remember the owner's answer by name and, when the question came from a payment, by that
    payment's UPI ID too, so later payments from the same phone (a son's, say) are known even
    when its name differs or is missing."""
    pk, ck = normalise(party_text), normalise(counterparty_name)
    vpa = None
    if bank_txn_id:
        t = db.get(BankTransaction, bank_txn_id)
        ev = db.get(EvidenceItem, t.evidence_id) if t else None
        if t is not None and ev is not None and ev.business_id == business_id:
            vpa = (t.counterparty_vpa or "").lower() or None
    if ck:
        _remember(db, business_id, pk, ck, same)
    if vpa:
        _remember(db, business_id, pk, VPA_KEY + vpa, same)
    db.flush()
    record(
        db,
        actor,
        "recon.owner_answer",
        f"business:{business_id}",
        {"same": same, "party": pk[:40], "counterparty": ck[:40], "by_upi_id": bool(vpa)},
    )
    return reconcile(db, business_id, actor)
