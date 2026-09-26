"""The start time an ESPN reading may WRITE (#8841).

ESPN lists a game before its start is announced with ``timeValid=false`` and a
date-only placeholder, ``T04:00Z`` — midnight Eastern, which is 9 PM Pacific the
evening BEFORE. ``ESPNEvent.date`` keeps that value, because the Eastern DATE is
right and matching and board-day reads need it. What may not happen is a rail
copying it onto ``events.commence_time``: espn outranks statpal in the start-time
ranking, so the copy moves a correct-date row onto the wrong evening and clears
the StatPal placeholder's TBD marker with it (the Wild Card specimen, BOS @ NYY
9/29 + 9/30, 2026-09-26).

Every rail that writes ESPN's clock reads :func:`espn_start_time`, never
``ee.date``. Imports nothing, so ``utils`` modules that only lazy-import
``services.espn_api`` can use it at module level.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


def espn_start_time(ee: Any) -> Optional[datetime]:
    """ESPN's start for ``ee``, or ``None`` when ESPN has not announced one.

    ``getattr`` because fakes and non-``ESPNEvent`` callers carry no
    ``time_valid``; for them the answer is ``ee.date``, exactly as before.
    """
    if getattr(ee, "time_valid", True) is False:
        return None
    return getattr(ee, "date", None)


def espn_announced_start(ee: Any) -> Optional[datetime]:
    """ESPN's start for ``ee`` only when ESPN said ``timeValid: true`` outright.

    Stricter than :func:`espn_start_time`: that one lets an absent flag through
    so no pre-#8841 payload changes behaviour; this one is for rails that treat
    ESPN's clock as a VOUCHER for a start already on the row (the equal-instant
    case — StatPal's 20:00Z placeholder turning out to be the real first pitch),
    where silence must vouch for nothing.
    """
    if getattr(ee, "time_announced", False) is not True:
        return None
    return espn_start_time(ee)
