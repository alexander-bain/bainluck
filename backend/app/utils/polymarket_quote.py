"""Current Polymarket quotes, never an undated trade (#12658).

Gamma's outcomePrices can be a midpoint on one poll and an old trade on the
next. A current open-market price comes from its usable book. An empty bid side
is bounded by zero and an empty ask side by one, so tight extremes still price.
The existing phantom-spread limit is shared with the reader; no new cutoff is set.
Settlement prices are handled separately by the callers.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD


def _book_bounds(bid: object, ask: object) -> tuple[Decimal, Decimal] | None:
    """Admit the current book, using the probability boundary for an empty side."""
    if isinstance(bid, bool) or isinstance(ask, bool):
        return None
    try:
        bid_value = Decimal(0) if bid is None else Decimal(str(bid))
        ask_value = Decimal(1) if ask is None else Decimal(str(ask))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not (bid_value.is_finite() and ask_value.is_finite()):
        return None
    if not 0 <= bid_value <= ask_value <= 1:
        return None
    if ask_value - bid_value >= Decimal(str(FEED_PHANTOM_MIN_SPREAD)):
        return None
    return bid_value, ask_value


def current_polymarket_quote(bid: object, ask: object) -> float | None:
    """Return the bounded book midpoint; empty or wide books still have no quote."""
    bounds = _book_bounds(bid, ask)
    return None if bounds is None else float(sum(bounds) / 2)


def quoted_price_change_value(old_probability, old_bid, old_ask, new_probability):
    """The ORM writer's counterpart to ``quoted_price_change`` below."""
    bounds = _book_bounds(old_bid, old_ask)
    if old_probability is None or bounds is None:
        return None
    try:
        previous = Decimal(str(old_probability))
        midpoint = sum(bounds) / 2
        if previous != midpoint:
            return None
        return float(Decimal(str(new_probability)) - previous)
    except (InvalidOperation, ValueError, TypeError):
        return None


def quoted_price_change(new_probability):
    """Compare supported quotes, never a quote and an old trade (#12658).

    Exact numeric equality declines an ambiguous prior basis. This is still the
    per-write field; the dated reader decides what a mover or alert may say.
    """
    from sqlalchemy import and_, case, func
    from app.models.models import FuturesOutcome

    bid = func.coalesce(FuturesOutcome.current_yes_bid, 0)
    ask = func.coalesce(FuturesOutcome.current_yes_ask, 1)
    return case(
        (
            and_(
                bid >= 0,
                ask <= 1,
                ask >= bid,
                ask - bid < FEED_PHANTOM_MIN_SPREAD,
                FuturesOutcome.current_probability == (bid + ask) / 2,
            ),
            new_probability - FuturesOutcome.current_probability,
        ),
        else_=None,
    )
