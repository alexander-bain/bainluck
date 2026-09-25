"""Did the book behind a published reading trade? (#8464, CERT-3408)

`evidence_status: "verified"` (CU-4, #5311) is QUESTION evidence: the market the
reading cites is an eligible full-event-winner question. It says nothing about
whether the PRICE could be traded. CERT-3408 measured two verified lone-Polymarket
readings on production parked at exactly 0.500 over books nobody trades inside:

    15314872  Galatasaray–Cayirova         0.06/0.95 + 0.05/0.94, no 24h volume
    15316031  Fraport Skyliners–RASTA      0.09/0.90 + 0.10/0.91, no 24h volume

Neither 0.500 is its book's midpoint (0.505 / 0.495), so the write-side guards
(`is_fabricated_midpoint`, `is_empty_book_midpoint`) let both through. The genuine
pick'em beside them, 15316415 Cubs @ Red Sox, sits over 0.49/0.51.

This module is the PRICE evidence the reader was missing, and it is read from
durable rows, never from the venue: the reading's own `updated_at` and each cited
market's stored `futures_outcomes` book. A reading proves a tradeable book when
EVERY market its eligibility record names (`contributing_market_ids` — a composite
reading is only as good as its worst leg) has an outcome whose book

  1. was stored in the SAME write as the reading (`last_updated == updated_at`) —
     the book the number was read off, not a later or earlier one. Measured
     2026-09-25 00:40Z over all 8 upcoming verified lone-Polymarket-0.500 events:
     8 of 8 match to the microsecond, because the Polymarket writer stamps both
     from one clock;
  2. is two-sided and tighter than ``FEED_PHANTOM_MIN_SPREAD`` — the one meaning
     of "untradeable" this codebase already has, imported rather than restated;
  3. brackets the reading or its complement (a one-outcome market can carry only
     the other side's price).

Anything else is ``UNPROVEN``. There is no "surviving trade" arm: `volume_24h`
is NULL on every one of those 8 events' outcomes, so a trade arm would be a
branch no production row can reach — fail closed until a stored trade exists.

READ-ONLY. No venue call, no write; one indexed lookup by market id.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.aggregation import parse_source_entry
from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD
from app.utils.probability_eligibility import contributing_market_ids, from_entry

TRADEABLE_BOOK = "tradeable_book"
UNPROVEN = "unproven"

# (market_id, yes_bid, yes_ask, last_updated) — one stored outcome book.
BookRow = tuple[int, Optional[float], Optional[float], Optional[datetime]]


def _book_supports(
    value: float,
    read_at: datetime,
    bid: Optional[float],
    ask: Optional[float],
    booked_at: Optional[datetime],
) -> bool:
    if bid is None or ask is None or booked_at is None:
        return False
    if booked_at.tzinfo is None:
        booked_at = booked_at.replace(tzinfo=timezone.utc)
    if booked_at != read_at:
        return False
    bid, ask = float(bid), float(ask)
    if ask - bid >= FEED_PHANTOM_MIN_SPREAD:
        return False
    return bid <= value <= ask or bid <= 1.0 - value <= ask


def classify_price_evidence(entry: Any, books: Iterable[BookRow]) -> str:
    """``TRADEABLE_BOOK`` or ``UNPROVEN`` for one stored source entry. Pure."""
    value, read_at = parse_source_entry(entry)
    market_ids = contributing_market_ids(from_entry(entry))
    if value is None or read_at is None or not market_ids:
        return UNPROVEN
    by_market: dict[int, list[BookRow]] = {}
    for row in books:
        by_market.setdefault(row[0], []).append(row)
    for market_id in market_ids:
        if not any(
            _book_supports(value, read_at, bid, ask, booked_at)
            for _, bid, ask, booked_at in by_market.get(market_id, ())
        ):
            return UNPROVEN
    return TRADEABLE_BOOK


async def load_price_evidence(db: AsyncSession, entry: Any) -> str:
    """Read the cited markets' stored books and classify ``entry``."""
    from app.models.models import FuturesOutcome

    market_ids: Sequence[int] = contributing_market_ids(from_entry(entry))
    if not market_ids:
        return UNPROVEN
    rows = (
        await db.execute(
            select(
                FuturesOutcome.market_id,
                FuturesOutcome.current_yes_bid,
                FuturesOutcome.current_yes_ask,
                FuturesOutcome.last_updated,
            ).where(FuturesOutcome.market_id.in_(list(market_ids)))
        )
    ).all()
    return classify_price_evidence(entry, [tuple(r) for r in rows])
