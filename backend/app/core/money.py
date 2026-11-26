"""Money helpers. Amounts are integer paise everywhere; floats are never used for money."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_CLEAN = re.compile(r"[,\s₹]|Rs\.?|INR", re.I)


def to_paise(rupees: str | int | Decimal) -> int:
    """'1,23,456.50' -> 12345650. Raises ValueError on anything that is not a number."""
    if isinstance(rupees, int):
        return rupees * 100
    text = _CLEAN.sub("", str(rupees)) if not isinstance(rupees, Decimal) else str(rupees)
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {rupees!r}") from exc
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_inr(paise: int) -> str:
    """12345650 -> '₹1,23,456.50' (Indian digit grouping)."""
    neg = paise < 0
    rupees, p = divmod(abs(paise), 100)
    s = str(rupees)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join([*groups, tail])
    out = f"₹{s}" + (f".{p:02d}" if p else "")
    return f"-{out}" if neg else out
