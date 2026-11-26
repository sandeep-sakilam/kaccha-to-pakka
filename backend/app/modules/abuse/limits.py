"""Rate and abuse limits (fixed windows). Redis in production; in-process when Redis is not
reachable (tests), so a missing Redis never blocks the app but limits still apply per process."""

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from app.core.config import get_settings
from app.core.errors import DomainError


class TooMany(DomainError):
    status_code = 429


@dataclass(frozen=True)
class Limit:
    name: str
    max: int
    window_s: int
    message: str


LIMITS = {
    "otp_phone": Limit("otp_phone", 5, 3600, "Too many OTP requests. Try again in an hour."),
    "otp_ip": Limit("otp_ip", 30, 3600, "Too many OTP requests from this network."),
    "capture_device": Limit("capture_device", 200, 86400, "Daily photo limit reached."),
    "sahayak_actions": Limit("sahayak_actions", 300, 86400, "Daily Sahayak limit reached."),
    "invites_business": Limit("invites_business", 10, 86400, "Daily invite limit reached."),
    "penny_drop_invite": Limit("penny_drop_invite", 3, 86400, "Too many ₹1 attempts."),
    "confirmer_month": Limit(
        "confirmer_month",
        10,
        30 * 86400,
        "This confirmer has confirmed too many businesses this month.",
    ),
    "lender_views": Limit("lender_views", 60, 3600, "Too many views of this link."),
}


class Counter(Protocol):
    def incr(self, key: str, window_s: int) -> int: ...


class MemoryCounter:
    def __init__(self) -> None:
        self.data: dict[str, tuple[int, float]] = {}

    def incr(self, key: str, window_s: int) -> int:
        now = time.time()
        n, exp = self.data.get(key, (0, now + window_s))
        if now > exp:
            n, exp = 0, now + window_s
        self.data[key] = (n + 1, exp)
        return n + 1


class RedisCounter:
    def __init__(self, url: str) -> None:
        from redis import Redis

        self.r = Redis.from_url(url, socket_timeout=1)
        self.r.ping()

    def incr(self, key: str, window_s: int) -> int:
        pipe = self.r.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        n, _ = pipe.execute()
        return int(n)


@lru_cache
def counter() -> Counter:
    s = get_settings()
    if s.app_env != "test":
        try:
            return RedisCounter(s.redis_url)
        except Exception as exc:
            logging.getLogger(__name__).warning("rate limits in-process only: %s", exc)
    return MemoryCounter()


def hit(limit: str, key: str) -> int:
    lim = LIMITS[limit]
    n = counter().incr(f"ktp:limit:{lim.name}:{key}", lim.window_s)
    if n > lim.max:
        raise TooMany(lim.message, f"rate_limited:{lim.name}")
    return n


def count_distinct(limit: str, key: str, member: str) -> None:
    """Limit the number of distinct members (e.g. businesses a confirmer attests) per window."""
    lim = LIMITS[limit]
    c = counter()
    seen_key = f"ktp:seen:{lim.name}:{key}:{member}"
    if isinstance(c, MemoryCounter):
        first = seen_key not in c.data or time.time() > c.data[seen_key][1]
        c.incr(seen_key, lim.window_s)
    else:
        assert isinstance(c, RedisCounter)
        first = bool(c.r.set(seen_key, 1, ex=lim.window_s, nx=True))
    if first:
        hit(limit, key)
