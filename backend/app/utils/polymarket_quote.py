"""Current Polymarket quotes, never an undated trade (#12658).

Gamma's outcomePrices can be a midpoint on one poll and an old trade on the
next. A current open-market price comes from its two-sided usable book. The
existing phantom-spread limit is shared with the reader; no new cutoff is set.
Settlement prices are handled separately by the callers.
"""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation

from app.utils.feed_market_quality import FEED_PHANTOM_MIN_SPREAD


def current_polymarket_quote(bid: object, ask: object) -> float | None:
    """Return the book's midpoint, or no quote when either offer is unusable."""
    if bid is None or ask is None or isinstance(bid, bool) or isinstance(ask, bool):
        return None
    try:
        bid_value, ask_value = float(bid), float(ask)
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(bid_value) and math.isfinite(ask_value)):
        return None
    if not 0 < bid_value <= ask_value < 1:
        return None
    if ask_value - bid_value >= FEED_PHANTOM_MIN_SPREAD:
        return None
    return (bid_value + ask_value) / 2


def quoted_price_change_value(old_probability, old_bid, old_ask, new_probability):
    """The ORM writer's counterpart to ``quoted_price_change`` below."""
    if old_probability is None or current_polymarket_quote(old_bid, old_ask) is None:
        return None
    try:
        previous = Decimal(str(old_probability))
        midpoint = (Decimal(str(old_bid)) + Decimal(str(old_ask))) / 2
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
    from sqlalchemy import and_, case
    from app.models.models import FuturesOutcome

    bid = FuturesOutcome.current_yes_bid
    ask = FuturesOutcome.current_yes_ask
    return case(
        (
            and_(
                bid > 0,
                ask < 1,
                ask >= bid,
                ask - bid < FEED_PHANTOM_MIN_SPREAD,
                FuturesOutcome.current_probability == (bid + ask) / 2,
            ),
            new_probability - FuturesOutcome.current_probability,
        ),
        else_=None,
    )
