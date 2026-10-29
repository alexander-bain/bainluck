"""Bounded DNPL reservations; league membership comes only from highlights.

Bucket order: T1 active/upcoming, T2 active/upcoming, other active/upcoming.
No borrowed slots. Sizes are policy defaults, not measured sufficiency claims.
"""

from __future__ import annotations

import os
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

# Initial-bootstrap configuration only. Existing ledgers reject a changed
# allocation or league-map fingerprint, including across ordinary restarts.
RESERVATIONS_ENV = "LIVE_BLEND_PREVIEW_RESERVATIONS"
DEFAULT_LIMITS = (192, 64, 128, 64, 48, 16)
#: Ledger capacity per fingerprint version. v2 is v1's classification, status
#: and window semantics with a larger resident cap; it exists only for totals
#: above v1's, so every allocation has exactly one fingerprint and a v1-sized
#: policy keeps today's bytes. A v1 script parses no v2 fingerprint and refuses
#: it (`policy_mismatch`), so an old writer fails closed against a v2 ledger.
LEDGER_CAPS = {"v1": 512, "v2": 1024}
MAX_EVENTS = LEDGER_CAPS["v1"]
MAX_TOTAL = LEDGER_CAPS["v2"]
UPCOMING_WINDOW = timedelta(hours=6)


@dataclass(frozen=True)
class ReservationPolicy:
    limits: tuple[int, ...] = DEFAULT_LIMITS

    def __post_init__(self) -> None:
        if (
            len(self.limits) != 6
            or any(type(n) is not int or n < 0 for n in self.limits)
            or not 0 < sum(self.limits) <= MAX_TOTAL
        ):
            raise ValueError(
                f"preview reservations require six nonnegative integers totaling 1..{MAX_TOTAL}"
            )

    @property
    def total(self) -> int:
        return sum(self.limits)

    @property
    def version(self) -> str:
        return "v1" if self.total <= MAX_EVENTS else "v2"

    @property
    def cap(self) -> int:
        """The ledger's resident bound for this policy's fingerprint version."""
        return LEDGER_CAPS[self.version]

    @property
    def fingerprint(self) -> str:
        # Includes the classification/window version, not just allocation sizes.
        from app.utils.highlights import LEAGUE_TIERS

        # v1 pins fallback/status/window semantics; bump on ANY semantic change.
        # v2 = v1 semantics at the larger ledger cap (LEDGER_CAPS).
        # Mapping changes are independently fingerprinted across workers.
        mapping = hashlib.sha256(
            json.dumps(LEAGUE_TIERS, sort_keys=True).encode()
        ).hexdigest()[:16]
        return (self.version + "-six-hour-" + mapping + ":"
                + ",".join(str(n) for n in self.limits))

    @classmethod
    def configured(cls) -> ReservationPolicy:
        raw = os.environ.get(RESERVATIONS_ENV)
        if raw is None:
            return cls()
        values = raw.split(",")
        if len(values) != 6 or any(
            not v.isascii() or not v.isdecimal() for v in values
        ):
            raise ValueError(f"invalid {RESERVATIONS_ENV}")
        return cls(tuple(int(v) for v in values))


@dataclass(frozen=True)
class ReservationContext:
    bucket: int  # 0..5 eligible; 6 outside window/lifecycle, retained incumbents only
    clock_us: int
    revision: int


def reservation_context(event: Any, revision: Any) -> ReservationContext | None:
    """Only classify an explicitly materialized authoritative event graph.

    An explicit unknown sport_key is the other tier. A missing field/DB clock
    is missing proof, not an unknown league. Undated scheduled rows cannot
    obtain an active reservation merely because their start time is missing.
    """
    from app.utils.highlights import get_league_tier

    at = getattr(event, "preview_context_at", None)
    if (
        not hasattr(event, "sport_key")
        or not isinstance(at, datetime)
        or at.tzinfo is None
        or type(revision) is not int
        or revision < 0
    ):
        return None
    status = getattr(event, "status", None)
    start = getattr(event, "commence_time", None)
    tier = get_league_tier(event.sport_key)
    group = 0 if tier == 1 else 2 if tier == 2 else 4
    bucket = group
    if getattr(event, "completed_at", None) is not None or status not in (
        "live",
        "scheduled",
        "suspended",
    ):
        bucket = 6
    elif status == "scheduled":
        if not isinstance(start, datetime):
            bucket = 6
        elif start.tzinfo is None:
            return None
        elif start > at:
            bucket = group + 1 if start <= at + UPCOMING_WINDOW else 6
    clock_us = int(at.timestamp() * 1_000_000)
    if not 0 <= clock_us <= 9007199254740991 or revision > 9007199254740991:
        return None
    return ReservationContext(bucket, clock_us, revision)
