"""One Kalshi candle → the YES price, for the rails that FEED CALIBRATION.

WHY THIS FILE EXISTS. ``KalshiAPIService.get_market_candlesticks`` reduced a
candle to ``(bid+ask)/2``, falling back to whichever side was non-zero and
never looking at the trade price sitting in the same object. Its own docstring
named the flaw in September 2026 and named this file's two consumers —
``_backfill_kalshi_price_history`` and ``kalshi_cliff`` — as the reason it was
left alone: they "fill calibration buckets whose behaviour is not this queue's
to change". This is the calibration lane changing it.

WHAT IT COST, measured at the venue on ``KXPGAR2TOP10-TOC26`` (Tour Championship
Round 2 Top 10, 2026-08-28), Kalshi's own hourly candlesticks, 511 candles:

    leg                        book at the candle   traded   old      this
    Sam Burns (lost)           bid 0.00 / ask 0.88   0.05    0.88     0.05
    Akshay Bhatia (lost)       bid 0.00 / ask 0.82   0.44    0.82     0.44
    Matt Fitzpatrick (WON)     bid 0.07 / ask 1.00   0.95    0.535    0.95

Both directions: a losing longshot is published near-certain, and a winner
whose book has one side quoted is published near a coin flip. 83 of the 511
candles moved, 31 of them by 0.20 or more, mean move 0.223 over the ones that
move.

THE POLICY IS NOT NEW AND IS NOT THIS FILE'S INVENTION. It is
``event_chart_backfill.normalize_candle``, shipped for user-facing curves after
the same defect drew a losing tennis player at 1.0, and it is gotcha #19's rule
("wide spread → last trade") already learned at Polymarket. Deliberately no
third variant: a price policy that exists twice drifts, so
``tests/test_kalshi_candle_price.py`` asserts the two agree candle for candle,
and collapsing them into one call site is the follow-up this file wants.
``get_market_candlesticks_batch`` was that third variant — the old rule,
verbatim, 100 lines below the method that was fixed and uncalled by anything,
so no test would have found it — and it now calls this function too.

The rule, in order:

1. a book tight enough for a mid to mean something (both sides quoted, gap
   ≤ :data:`WIDE_SPREAD_DOLLARS`) → the midpoint;
2. else the candle's own trade price → that;
3. else one side quoted, and only when it is a real price rather than the
   0.00/1.00 shell a settled market leaves → that side;
4. else ``None`` — there is no honest price in this candle. The caller stores
   nothing, which is the point: an absent row is a gap, a fabricated row is a
   lie a curve then grades.
"""

from __future__ import annotations

from typing import Any, Optional

#: Above this bid/ask gap the mid stops meaning anything and the trade is the
#: honest number. Same value, and the same reasoning, as
#: ``event_chart_backfill.WIDE_SPREAD_DOLLARS``; the drift test binds them.
WIDE_SPREAD_DOLLARS = 0.10


def _dollars(container: Any, *keys: str) -> Optional[float]:
    """First parseable ``*_dollars`` value among ``keys``, or None.

    Kalshi publishes candle prices ONLY in the ``*_dollars`` fields — the cents
    spellings are absent on this payload — and they arrive as strings.
    """
    if not isinstance(container, dict):
        return None
    for key in keys:
        raw = container.get(key)
        if raw is None or raw == "":
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


def _usable(value: Optional[float]) -> bool:
    """A quote that is a price, not a boundary of the range it lives in."""
    return value is not None and 0.0 < value < 1.0


def candle_yes_price(candle: Any) -> Optional[float]:
    """The YES probability this candle supports, or None to store nothing."""
    if not isinstance(candle, dict):
        return None

    bid = _dollars(candle.get("yes_bid"), "close_dollars")
    ask = _dollars(candle.get("yes_ask"), "close_dollars")
    last = _dollars(
        candle.get("price"), "close_dollars", "mean_dollars", "previous_dollars"
    )

    if (
        bid is not None
        and ask is not None
        and bid > 0
        and ask > 0
        and ask >= bid
        and (ask - bid) <= WIDE_SPREAD_DOLLARS
    ):
        return (bid + ask) / 2.0

    if _usable(last):
        return last

    if _usable(bid) and not _usable(ask):
        return bid
    if _usable(ask) and not _usable(bid):
        return ask
    if _usable(bid) and _usable(ask):
        return (bid + ask) / 2.0
    return None
