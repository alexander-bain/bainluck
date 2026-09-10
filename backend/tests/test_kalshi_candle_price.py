"""CAL-P1084 (#4730): the candle reduction that feeds calibration.

Every candle in the REAL CANDLES table below was read from Kalshi's own
``/markets/candlesticks`` on 2026-09-10 for ``KXPGAR2TOP10-TOC26`` (Tour
Championship Round 2 Top 10, settled 2026-08-28) — the venue's payload, not a
mirror of ours (standing notice 26). They are the specimens that pay for the
change: the old reduction published a losing longshot at the ask of a
one-sided book and a winner at the midpoint of a 0.07/1.00 shell.

`artifacts-calibration-1084/candle-vs-stored-TOC26.tsv` is the full 511-candle
run these were taken from.
"""

import pytest

from app.tasks.event_chart_backfill import normalize_candle
from app.utils.kalshi_candle_price import WIDE_SPREAD_DOLLARS, candle_yes_price


def _candle(bid=None, ask=None, close=None, mean=None, previous=None):
    """A Kalshi candle. Kalshi publishes ONLY the ``*_dollars`` spellings."""
    out = {}
    if bid is not None:
        out["yes_bid"] = {"close_dollars": bid}
    if ask is not None:
        out["yes_ask"] = {"close_dollars": ask}
    price = {}
    if close is not None:
        price["close_dollars"] = close
    if mean is not None:
        price["mean_dollars"] = mean
    if previous is not None:
        price["previous_dollars"] = previous
    if price:
        out["price"] = price
    return out


#: (label, candle, expected). Values are the venue's, to the cent.
REAL_CANDLES = [
    # The headline: Sam Burns lost, and the book at this candle was
    # bid 0.00 / ask 0.88 with the last trade at 0.05. Old rule: 0.88.
    ("burns_lost_ask_only", _candle(bid="0.0000", ask="0.8800", previous="0.0500"), 0.05),
    # Same leg, one candle earlier — ask 0.99 against a 0.05 close.
    ("burns_lost_ask_099", _candle(bid="0.0000", ask="0.9900", close="0.0500"), 0.05),
    # Matt Fitzpatrick WON. bid 0.07 / ask 1.00 with a 0.95 trade. Old rule
    # midpointed the shell to 0.535 and understated the winner by 0.42.
    ("fitzpatrick_won_wide", _candle(bid="0.0700", ask="1.0000", close="0.9500"), 0.95),
    # Akshay Bhatia lost. A quoted bid, but a 0.77-wide book.
    ("bhatia_wide_book", _candle(bid="0.2300", ask="1.0000", previous="0.9500"), 0.95),
    ("bhatia_ask_only", _candle(bid="0.0000", ask="0.5700", close="0.1800"), 0.18),
    # Jacob Bridgeman lost. Tight two-sided book -> the mid is meaningful.
    ("bridgeman_tight", _candle(bid="0.0500", ask="0.0700", close="0.0600"), 0.06),
]


@pytest.mark.parametrize("label,candle,expected", REAL_CANDLES, ids=[c[0] for c in REAL_CANDLES])
def test_real_venue_candles_reduce_to_the_traded_price(label, candle, expected):
    got = candle_yes_price(candle)
    assert got == pytest.approx(expected, abs=0.005), label


def test_the_settled_shell_yields_no_price_at_all():
    """bid 0.00 / ask 1.00 with nothing traded is not a price.

    This is the shape a settled loser's book leaves behind, and storing the ask
    for it is what put 45 legs of one golf market on the curve at 0.97. An
    absent row is a gap; a fabricated row is a lie the curve then grades.
    """
    assert candle_yes_price(_candle(bid="0.0000", ask="1.0000")) is None


def test_a_one_sided_book_with_no_trade_falls_back_to_the_one_real_side():
    """Not every one-sided book is a shell — a 0.03 ask is a real quote."""
    assert candle_yes_price(_candle(bid="0.0000", ask="0.0300")) == pytest.approx(0.03)
    assert candle_yes_price(_candle(bid="0.9600")) == pytest.approx(0.96)


def test_a_bid_pinned_against_the_ceiling_is_a_tight_book_not_a_shell():
    """bid 0.96 / ask 1.00 reduces to 0.98, and that is deliberate.

    The 1.00 ask disqualifies a quote only when it is the ONLY side (the shell
    a settled loser leaves). Beside a 0.96 bid the gap is 4c, the book is tight
    by the spread rule, and the mid is the honest number — the near-certain
    winner really is quoted there. Asserted because the shell test above reads
    like it should also catch this one.
    """
    assert candle_yes_price(_candle(bid="0.9600", ask="1.0000")) == pytest.approx(0.98)


def test_a_tight_book_still_takes_the_midpoint_over_a_stale_trade():
    """The trade only wins once the book stops meaning anything.

    Priority matters: a live 0.44/0.46 book beats yesterday's 0.20 print.
    """
    candle = _candle(bid="0.4400", ask="0.4600", previous="0.2000")
    assert candle_yes_price(candle) == pytest.approx(0.45)


def test_the_spread_boundary_is_inclusive_and_one_cent_past_it_flips():
    """The gap that separates the two branches, asserted at LITERAL cents.

    Deliberately not written as ``0.40 + WIDE_SPREAD_DOLLARS``: a boundary case
    computed from the constant it is meant to pin moves with it, and the
    mutation battery proved it — widening the constant to 0.25 left the whole
    file green (`tools/cal-1084-mutations.py`, M4). The numbers below are the
    policy; the assertion under them is the constant.
    """
    assert WIDE_SPREAD_DOLLARS == 0.10
    at_the_line = _candle(bid="0.4000", ask="0.5000", previous="0.9000")
    one_cent_past = _candle(bid="0.4000", ask="0.5100", previous="0.9000")
    assert candle_yes_price(at_the_line) == pytest.approx(0.45)
    assert candle_yes_price(one_cent_past) == pytest.approx(0.90)


def test_the_two_reducers_agree_about_how_wide_is_too_wide():
    """The constant, not just the behaviour, is bound to the chart reducer."""
    from app.tasks.event_chart_backfill import WIDE_SPREAD_DOLLARS as chart_wide

    assert WIDE_SPREAD_DOLLARS == chart_wide


def test_an_empty_or_malformed_candle_is_none_not_zero():
    for junk in ({}, None, [], {"yes_bid": None, "yes_ask": None}, _candle(bid="x", ask="y")):
        assert candle_yes_price(junk) is None


def test_the_policy_does_not_drift_from_the_chart_reducer():
    """One policy, two call sites — bound here until they are one.

    `event_chart_backfill.normalize_candle` is where this rule was first
    shipped (live/035, for user-facing curves). If either moves without the
    other, a calibration bucket and the chart above it disagree about what the
    same candle was worth, and nothing else in the suite would notice.
    """
    corpus = [c for _, c, _ in REAL_CANDLES] + [
        _candle(bid="0.0000", ask="1.0000"),
        _candle(bid="0.0000", ask="0.0300"),
        _candle(bid="0.4400", ask="0.4600", previous="0.2000"),
        _candle(bid="0.9900", ask="1.0000", close="0.9900"),
        _candle(previous="0.5000"),
        _candle(),
    ]
    for candle in corpus:
        assert candle_yes_price(candle) == normalize_candle(candle), candle


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_the_service_drops_the_candles_that_have_no_honest_price():
    """The reduction is wired into the method the calibration rails call.

    `_backfill_kalshi_price_history` and `kalshi_cliff` both consume
    `get_market_candlesticks`, and both write straight into
    `futures_odds_snapshots` — so a candle this refuses must never reach them.
    """
    from app.services import kalshi_api as mod

    service = mod.KalshiAPIService(api_key="test")
    payload = {
        "markets": [
            {
                "candlesticks": [
                    # a settled shell: refused outright
                    {"end_period_ts": 1, **_candle(bid="0.0000", ask="1.0000")},
                    # Sam Burns' real candle: the trade, not the ask
                    {"end_period_ts": 2, **_candle(bid="0.0000", ask="0.8800", previous="0.0500")},
                    # no timestamp: refused for a different reason
                    {**_candle(bid="0.4400", ask="0.4600")},
                ]
            }
        ]
    }

    async def _fake_get(url, params=None):
        return _FakeResponse(payload)

    service.client.get = _fake_get
    try:
        out = await service.get_market_candlesticks("KXPGAR2TOP10-TOC26-SBUR")
    finally:
        await service.close()

    assert out == [{"t": 2, "yes_price": pytest.approx(0.05)}]


@pytest.mark.asyncio
async def test_the_batch_method_reduces_by_the_same_policy_as_the_singular_one():
    """The copy of the old rule that the fix to its twin would not have found.

    `get_market_candlesticks_batch` carried `(bid+ask)/2`-or-either-side
    verbatim, 100 lines below the method CAL-P1084 repaired, and NOTHING calls
    it — so no existing test, and no caller, would have noticed it disagreeing
    with the policy. It is a trap for the next caller (a rail batching tickers
    to save quota is the obvious one), and this is the guard that shuts it.
    """
    from app.services import kalshi_api as mod

    service = mod.KalshiAPIService(api_key="test")
    payload = {
        "markets": [
            {
                "market_ticker": "KXPGAR2TOP10-TOC26-SBUR",
                "candlesticks": [
                    # Sam Burns' real candle: the old rule said 0.88, the ask.
                    {"end_period_ts": 2, **_candle(bid="0.0000", ask="0.8800", previous="0.0500")},
                    # the settled shell: the old rule said 1.00
                    {"end_period_ts": 3, **_candle(bid="0.0000", ask="1.0000")},
                ],
            },
            {
                "market_ticker": "KXPGAR2TOP10-TOC26-MFIT",
                # Fitzpatrick WON: the old rule midpointed the shell to 0.535.
                "candlesticks": [
                    {"end_period_ts": 2, **_candle(bid="0.0700", ask="1.0000", close="0.9500")}
                ],
            },
        ]
    }

    async def _fake_get(url, params=None):
        return _FakeResponse(payload)

    service.client.get = _fake_get
    try:
        out = await service.get_market_candlesticks_batch(
            ["KXPGAR2TOP10-TOC26-SBUR", "KXPGAR2TOP10-TOC26-MFIT"]
        )
    finally:
        await service.close()

    assert out == {
        "KXPGAR2TOP10-TOC26-SBUR": [{"t": 2, "yes_price": pytest.approx(0.05)}],
        "KXPGAR2TOP10-TOC26-MFIT": [{"t": 2, "yes_price": pytest.approx(0.95)}],
    }
