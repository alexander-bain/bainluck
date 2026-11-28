"""Opening value quote-vs-trade validity (#13511 Item 3).

An opening value may be shown, or used to state a change, only when it came
from a trade or a real two-sided quote. The midpoint of an empty or wide
order book (or a one-sided quote with no trade) is not an opening value
(the class of #13485 and #8612).

This module holds ONE read-side validity rule shared by the event and futures
serve paths (``routes/events.py``, ``routes/futures.py``): it verifies each
stored prediction-market opening against its opening-capture snapshot (and
``market_metadata['unpriced_opening_ids']``) before serving it or computing
pregame/movement numbers from it, without mutating stored calibration rows.

Canonical thresholds are imported, never restated:
  * ``FEED_PHANTOM_MIN_SPREAD`` (`0.20`) — spread threshold separating a real
    two-sided quote from an untradeable/wide book (`app.utils.feed_market_quality`).
  * ``is_empty_book_midpoint`` / ``is_bidless_empty_book_midpoint`` — empty-book
    midpoint detection (`app.utils.feed_market_quality`).
  * ``book_refutes_price`` — trade refuted by a tighter live quote
    (`app.utils.kalshi_empty_book`).
  * ``unpriced_opening_ids`` — batch-refused opening ids flagged by A10
    (`app.utils.futures_market_snapshot`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import math
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import asc, select, text, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.feed_market_quality import (
    FEED_PHANTOM_MIN_SPREAD,
    is_bidless_empty_book_midpoint,
    is_empty_book_midpoint,
)
from app.utils.futures_market_snapshot import unpriced_opening_ids
from app.utils.kalshi_empty_book import book_refutes_price

_BOOK_DECIMALS = 4
_OPENING_MATCH_TOLERANCE = 0.01
_UNTIMED_PROVENANCE_TOLERANCE = 0.0051
_PREDICTION_MARKET_SOURCES = frozenset({"kalshi", "polymarket"})


def _to_finite_float(value: Any) -> Optional[float]:
    """Return finite ``float(value)`` for real numeric scalars, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    f = float(value)
    if not math.isfinite(f):
        return None
    return f


def _coerce_utc_dt(value: Any) -> Optional[datetime]:
    """Return an aware UTC datetime for real ``datetime`` objects, else ``None``."""
    if not isinstance(value, datetime):
        return None
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def is_real_two_sided_quote(yes_bid: Any, yes_ask: Any) -> bool:
    """True when ``yes_bid`` and ``yes_ask`` form a real, tight two-sided quote.

    Requires positive bid (`> 0`), non-ceiling ask (`< 1`), valid ordering
    (`bid < ask`), and spread strictly tighter than ``FEED_PHANTOM_MIN_SPREAD`` (`0.20`).
    """
    bid = _to_finite_float(yes_bid)
    ask = _to_finite_float(yes_ask)
    if bid is None or ask is None:
        return False
    if not (0.0 < bid < ask < 1.0):
        return False
    return round(ask - bid, _BOOK_DECIMALS) < FEED_PHANTOM_MIN_SPREAD


def is_valid_opening_trade(
    last_price: Any,
    yes_bid: Any = None,
    yes_ask: Any = None,
) -> bool:
    """True when a real trade exists (`0 < last_price < 1`) not refuted by the book."""
    lp = _to_finite_float(last_price)
    if lp is None or not (0.0 < lp < 1.0):
        return False
    bid = _to_finite_float(yes_bid)
    ask = _to_finite_float(yes_ask)
    return not book_refutes_price(bid, ask, lp)


def opening_capture_is_supported(
    yes_bid: Any,
    yes_ask: Any,
    last_price: Any,
    *,
    opening_probability: Any = None,
) -> bool:
    """Write/capture rule: True iff opening came from a trade or real two-sided quote.

    When ``opening_probability`` is supplied:
      * A real two-sided quote must bracket it (within ``_OPENING_MATCH_TOLERANCE``)
        and must not itself be an empty/bidless empty-book midpoint unless supported
        by an actual trade at that level.
      * A valid trade on a wide or one-sided book only supports an opening that
        reflects that trade (within ``_OPENING_MATCH_TOLERANCE``), preventing a
        wide-book midpoint from borrowing an unrelated earlier fill.
    """
    op = _to_finite_float(opening_probability) if opening_probability is not None else None
    bid = _to_finite_float(yes_bid)
    ask = _to_finite_float(yes_ask)
    lp = _to_finite_float(last_price)

    has_trade_match = is_valid_opening_trade(lp, bid, ask) and (
        op is None or round(abs(op - float(lp)), 6) <= _OPENING_MATCH_TOLERANCE
    )
    if op is not None and (
        is_empty_book_midpoint(op, bid, ask)
        or is_bidless_empty_book_midpoint(op, bid, ask)
    ):
        return has_trade_match

    if is_real_two_sided_quote(bid, ask):
        assert bid is not None and ask is not None
        if op is None:
            return True
        return (
            round(op - bid, 6) >= -_OPENING_MATCH_TOLERANCE
            and round(op - ask, 6) <= _OPENING_MATCH_TOLERANCE
        )

    return has_trade_match


def opening_snapshot_supports_opening(
    opening_probability: Any,
    yes_bid: Any,
    yes_ask: Any,
    last_price: Any,
) -> bool:
    """Read-side check against an outcome's opening-capture snapshot.

    Non-order-book snapshots (all three quote/trade fields ``None``, e.g.
    traditional sportsbooks or pre-book historical captures) fail open (``True``),
    matching ``#8612`` A10's no-book arm. Any recorded order-book or trade
    evidence must satisfy :func:`opening_capture_is_supported`.
    """
    bid = _to_finite_float(yes_bid)
    ask = _to_finite_float(yes_ask)
    lp = _to_finite_float(last_price)
    if bid is None and ask is None and lp is None:
        return True
    return opening_capture_is_supported(
        bid,
        ask,
        lp,
        opening_probability=opening_probability,
    )


async def load_unsupported_opening_ids(
    db: AsyncSession,
    outcomes: Sequence[Any],
    market_map: Mapping[int, Any],
) -> set[int]:
    """Return outcome IDs whose stored ``opening_probability`` lacks quote/trade support.

    Combines A10 metadata (`unpriced_opening_ids`) with a single batched lookup
    against `futures_odds_snapshots` for prediction-market (`kalshi` /
    `polymarket`) outcomes carrying a numeric `opening_probability`.

    Fail-open on missing snapshots, mock DB sessions, or SQLite/unit harnesses
    without Postgres `LATERAL` support.
    """
    from app.models import FuturesOddsSnapshot, FuturesOutcome

    unsupported: set[int] = set()
    for market in market_map.values():
        unsupported |= unpriced_opening_ids(market)

    opening_by_id: dict[int, float] = {}
    timed_ids: list[int] = []
    untimed_ids: list[int] = []

    for outcome in outcomes:
        oid = getattr(outcome, "id", None)
        if isinstance(oid, bool) or not isinstance(oid, int):
            continue
        if oid in unsupported:
            continue
        mid = getattr(outcome, "market_id", None)
        market = market_map.get(mid) if not isinstance(mid, bool) and isinstance(mid, int) else None
        source = getattr(market, "source", None)
        if not isinstance(source, str) or source not in _PREDICTION_MARKET_SOURCES:
            continue
        op = _to_finite_float(getattr(outcome, "opening_probability", None))
        if op is None:
            continue

        cap_raw = getattr(outcome, "opening_captured_at", None)
        cap_dt = _coerce_utc_dt(cap_raw)
        if cap_dt is not None:
            opening_by_id[oid] = op
            timed_ids.append(oid)
        elif cap_raw is None:
            # Explicit NULL (never captured timestamp): only untimed outcomes are
            # checked against earliest snapshot when provenance matches. MagicMock
            # attributes are neither datetime nor None and are intentionally skipped.
            opening_by_id[oid] = op
            untimed_ids.append(oid)

    if not timed_ids and not untimed_ids:
        return unsupported

    dialect_name = "postgresql"
    bind = getattr(db, "bind", None)
    raw_name = getattr(getattr(bind, "dialect", None), "name", None)
    if isinstance(raw_name, str) and raw_name:
        dialect_name = raw_name

    if timed_ids:
        rows = await _fetch_timed_opening_snapshots(
            db, timed_ids, dialect_name=dialect_name, FuturesOddsSnapshot=FuturesOddsSnapshot, FuturesOutcome=FuturesOutcome
        )
        for row in rows:
            parsed = _unpack_snapshot_row(row)
            if parsed is None:
                continue
            oid, yes_bid, yes_ask, last_price, _ = parsed
            op = opening_by_id.get(oid)
            if op is None:
                continue
            if not opening_snapshot_supports_opening(op, yes_bid, yes_ask, last_price):
                unsupported.add(oid)

    if untimed_ids:
        rows = await _fetch_earliest_opening_snapshots(
            db, untimed_ids, dialect_name=dialect_name, FuturesOddsSnapshot=FuturesOddsSnapshot, FuturesOutcome=FuturesOutcome
        )
        for row in rows:
            parsed = _unpack_snapshot_row(row)
            if parsed is None:
                continue
            oid, yes_bid, yes_ask, last_price, snap_prob = parsed
            op = opening_by_id.get(oid)
            sp = _to_finite_float(snap_prob)
            if op is None or sp is None:
                continue
            # Provenance check: only apply the earliest snapshot to an untimed
            # outcome if that snapshot actually carries the same opening price.
            if abs(sp - op) > _UNTIMED_PROVENANCE_TOLERANCE:
                continue
            if not opening_snapshot_supports_opening(op, yes_bid, yes_ask, last_price):
                unsupported.add(oid)

    return unsupported


def _unpack_snapshot_row(
    row: Any,
) -> Optional[tuple[int, Optional[float], Optional[float], Optional[float], Optional[float]]]:
    try:
        oid, yes_bid, yes_ask, last_price, snap_prob = row
    except (TypeError, ValueError):
        return None
    if isinstance(oid, bool) or not isinstance(oid, int):
        return None
    return (
        oid,
        _to_finite_float(yes_bid),
        _to_finite_float(yes_ask),
        _to_finite_float(last_price),
        _to_finite_float(snap_prob),
    )


async def _fetch_timed_opening_snapshots(
    db: AsyncSession,
    outcome_ids: list[int],
    *,
    dialect_name: str,
    FuturesOddsSnapshot: Any,
    FuturesOutcome: Any,
) -> list[Any]:
    if dialect_name == "postgresql":
        snap_lateral = (
            select(
                FuturesOddsSnapshot.yes_bid,
                FuturesOddsSnapshot.yes_ask,
                FuturesOddsSnapshot.last_price,
                FuturesOddsSnapshot.probability,
            )
            .where(
                FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
                FuturesOddsSnapshot.captured_at
                >= FuturesOutcome.opening_captured_at - text("INTERVAL '1 second'"),
                FuturesOddsSnapshot.captured_at
                < FuturesOutcome.opening_captured_at + text("INTERVAL '2 seconds'"),
            )
            .order_by(asc(FuturesOddsSnapshot.captured_at))
            .limit(1)
            .lateral("opening_snap")
        )
        stmt = (
            select(
                FuturesOutcome.id,
                snap_lateral.c.yes_bid,
                snap_lateral.c.yes_ask,
                snap_lateral.c.last_price,
                snap_lateral.c.probability,
            )
            .select_from(FuturesOutcome)
            .join(snap_lateral, true())
            .where(FuturesOutcome.id.in_(outcome_ids))
        )
        return list((await db.execute(stmt)).all())

    # Portable Python-matched fallback for non-PostgreSQL backends (e.g. SQLite tests).
    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.captured_at,
            FuturesOddsSnapshot.yes_bid,
            FuturesOddsSnapshot.yes_ask,
            FuturesOddsSnapshot.last_price,
            FuturesOddsSnapshot.probability,
        )
        .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
        .order_by(asc(FuturesOddsSnapshot.captured_at))
    )
    snaps = list((await db.execute(stmt)).all())
    out_rows = list(
        (
            await db.execute(
                select(FuturesOutcome.id, FuturesOutcome.opening_captured_at).where(
                    FuturesOutcome.id.in_(outcome_ids)
                )
            )
        ).all()
    )
    target_by_id: dict[int, datetime] = {}
    for oid, cap_dt in out_rows:
        dt = _coerce_utc_dt(cap_dt)
        if dt is not None:
            target_by_id[oid] = dt

    matched: list[tuple[int, Any, Any, Any, Any]] = []
    seen: set[int] = set()
    for row in snaps:
        try:
            oid, cap_at, yes_bid, yes_ask, last_price, prob = row
        except (TypeError, ValueError):
            continue
        if oid in seen:
            continue
        target = target_by_id.get(oid)
        dt = _coerce_utc_dt(cap_at)
        if target is None or dt is None:
            continue
        if (target - timedelta(seconds=1)) <= dt < (target + timedelta(seconds=2)):
            seen.add(oid)
            matched.append((oid, yes_bid, yes_ask, last_price, prob))
    return matched


async def _fetch_earliest_opening_snapshots(
    db: AsyncSession,
    outcome_ids: list[int],
    *,
    dialect_name: str,
    FuturesOddsSnapshot: Any,
    FuturesOutcome: Any,
) -> list[Any]:
    if dialect_name == "postgresql":
        snap_lateral = (
            select(
                FuturesOddsSnapshot.yes_bid,
                FuturesOddsSnapshot.yes_ask,
                FuturesOddsSnapshot.last_price,
                FuturesOddsSnapshot.probability,
            )
            .where(FuturesOddsSnapshot.outcome_id == FuturesOutcome.id)
            .order_by(asc(FuturesOddsSnapshot.captured_at))
            .limit(1)
            .lateral("earliest_snap")
        )
        stmt = (
            select(
                FuturesOutcome.id,
                snap_lateral.c.yes_bid,
                snap_lateral.c.yes_ask,
                snap_lateral.c.last_price,
                snap_lateral.c.probability,
            )
            .select_from(FuturesOutcome)
            .join(snap_lateral, true())
            .where(FuturesOutcome.id.in_(outcome_ids))
        )
        return list((await db.execute(stmt)).all())

    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.yes_bid,
            FuturesOddsSnapshot.yes_ask,
            FuturesOddsSnapshot.last_price,
            FuturesOddsSnapshot.probability,
        )
        .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
        .order_by(asc(FuturesOddsSnapshot.captured_at))
    )
    matched: list[tuple[int, Any, Any, Any, Any]] = []
    seen: set[int] = set()
    for row in (await db.execute(stmt)).all():
        parsed = _unpack_snapshot_row(row)
        if parsed is None or parsed[0] in seen:
            continue
        seen.add(parsed[0])
        matched.append(parsed)
    return matched
