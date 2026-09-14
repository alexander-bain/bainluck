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
   0.00/1.00 shell a settled market leaves → that side. A lone ASK over
   :data:`~app.utils.kalshi_empty_book.ASK_ONLY_TRUSTED_MAX` is not a price and
   is refused here — see the paragraph below;
4. else ``None`` — there is no honest price in this candle. The caller stores
   nothing, which is the point: an absent row is a gap, a fabricated row is a
   lie a curve then grades.

RULE 3 HAD A HOLE ON THE ASK SIDE, AND THE VENUE'S DEFAULT BOOK DROVE A TRUCK
THROUGH IT (#6126, measured 2026-09-14). "A real price rather than the shell"
was read as "anything that is not exactly 1.00", so a lone ask at 0.99 was
published as a probability. Kalshi opens an untraded market at **bid 0.0000 /
ask 0.9900** — read at the venue, ``KXWTACHALLENGERMATCH-26SEP14ZELNAJ-NAJ``
candlesticks, ``yes_bid.open_dollars "0.0000"`` beside ``yes_ask.open_dollars
"0.9900"`` — so the first candle of every market nobody has traded yet reduces
to 0.99, and 0.99 is the number that reaches the reader.

What it cost, on production: three eliminated players printed **OPEN 99%** on
the settled US Open Men's Singles ladder (``/futures/34277822``), each stored at
exactly 0.99 from the same 18:00 candle. Alexander Bublik's next hourly candle
is 0.13 — the series refutes its own first point. That page is not alone:
**234 legs across 53 markets** carry this rail's fingerprint from the last 21
days, the newest 2026-09-11 20:00Z, so this was a live mint and not a
historical population.

The fingerprint is the TIMESTAMP, and it is worth stating because the obvious
count is wrong. A candle's ``end_period_ts`` lands exactly on the hour, where
the poller's ``now`` carries microseconds. Counting on value-and-source alone
(``opening_probability = 0.99 AND opening_source IS NULL``) returns 4,611 legs,
of which 4,275 are Kalshi legs written at poller-shaped instants and 123 are
Polymarket — populations this branch never wrote and this rule does not speak
about.

:mod:`app.utils.kalshi_empty_book` had already measured this exact shape and
priced it — a lone ask on an empty book grades at a 6.2% win rate against a
0.369 mean stored price — and the poller has refused it since 2026-07-13. The
bound is imported from there rather than restated: one capability question, one
constant. (That module's own docstring says the Kalshi half of its population is
historical, on a census that scored zero. It scored zero because the census
tests ``yes_bid``, and the candle rails store no book at all — the rows this
branch writes carry NULL bid/ask and are invisible to it.)
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.kalshi_empty_book import is_lone_ask_on_empty_book

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
        # An offer nobody took, on a book nobody is bidding into. Only the ask
        # side is refused, and only above the measured bound: a lone BID is a
        # real price (93.7% win rate) and stays.
        if is_lone_ask_on_empty_book(bid, ask, last):
            return None
        return ask
    if _usable(bid) and _usable(ask):
        return (bid + ask) / 2.0
    return None
