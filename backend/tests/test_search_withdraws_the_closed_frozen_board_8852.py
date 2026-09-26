"""#8852 — search must not print a closed board's settled legs as a live answer.

`bainluck.com/search?q=recession` (390px, 2026-09-26 15:48Z) served "What will
Truist Financial say during their next earnings call?" with four `>99%` rows,
stamped Apr 17: market 8665864, `KXEARNINGSMENTIONTFC-26APR17`, no price written
since 2026-04-17 (162 days), still stored `open`. Kalshi's event reads "On Apr 17,
2026" with `markets: []`. The `>99%` rows are April's settled YES legs.

Fixture values are the production row (id, source, name, the served legs); the
ticker date and every stamp are offsets from now, so no test branches on the
clock (gotcha #44).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.routes import events as events_route

NOW = datetime.now(timezone.utc)
FROZEN = NOW - timedelta(days=162)
LIVE = NOW - timedelta(hours=2)


def _ticker_date(delta_days: int) -> str:
    return (NOW + timedelta(days=delta_days)).strftime("%y%b%d").upper()


PAST = _ticker_date(-162)
FUTURE = _ticker_date(30)


class _Outcome:
    def __init__(self, id, name, p, last_updated):
        self.id = id
        self.name = name
        self.current_probability = p
        self.last_updated = last_updated
        self.opening_probability = None
        self.volume = None
        self.is_winner = None
        self.current_yes_bid = p
        self.current_yes_ask = p


class _Market:
    def __init__(self, external_id, stamp, source="kalshi", id=8665864):
        self.id = id
        self.source = source
        self.external_id = external_id
        self.name = "What will Truist Financial say during their next earnings call?"
        self.mutually_exclusive = False
        self.market_tier = 5
        self.outcomes = [
            _Outcome(1, "M&A / Merger", 0.995, stamp),
            _Outcome(2, "Middle Market", 0.995, stamp),
            _Outcome(3, "AI / Artificial Intelligence", 0.995, stamp),
            _Outcome(4, "Real Estate", 0.995, stamp),
            _Outcome(5, "Tailwind", 0.47, stamp),
        ]


def _truist(stamp=FROZEN, date=PAST, source="kalshi"):
    return _Market(f"KXEARNINGSMENTIONTFC-{date}", stamp, source=source)


def test_the_truist_specimen_is_withdrawn():
    assert events_route._search_market_is_past_and_frozen(_truist(), now=NOW)
    assert events_route._futures_card_has_no_answer(_truist())


def test_the_specimen_fails_no_older_arm():
    # Precondition: without the new arm the union answered False, so this is the
    # arm that withdraws it (otherwise the tests above prove nothing new).
    m = _truist()
    assert not events_route._futures_market_has_no_outcome_rows(m)
    assert not events_route._futures_market_is_wholly_unpriced(m)
    assert not events_route._futures_market_prices_only_empty_books(m)
    assert not events_route._futures_board_is_mostly_unserved(m)
    assert not events_route._futures_market_prices_all_withheld(m, None)


def test_a_past_dated_board_still_being_priced_stays():
    assert not events_route._search_market_is_past_and_frozen(_truist(stamp=LIVE), now=NOW)
    assert not events_route._futures_card_has_no_answer(_truist(stamp=LIVE))


def test_a_frozen_board_with_a_future_ticker_date_stays():
    assert not events_route._search_market_is_past_and_frozen(_truist(date=FUTURE), now=NOW)


def test_a_frozen_season_board_with_no_dated_ticker_stays():
    # #8417's KXPREMIERLEAGUE-26: frozen, undated — twin ordering, not withdrawal.
    m = _Market("KXPREMIERLEAGUE-26", FROZEN, id=399)
    assert not events_route._search_market_is_past_and_frozen(m, now=NOW)


def test_a_board_with_no_printable_stamp_is_not_judged_frozen():
    assert not events_route._search_market_is_past_and_frozen(_truist(stamp=None), now=NOW)


def test_only_kalshi_tickers_are_read_as_dates():
    assert not events_route._search_market_is_past_and_frozen(
        _truist(source="polymarket"), now=NOW
    )


def test_the_frozen_bound_is_the_twin_bound():
    inside = NOW - events_route._SEARCH_TWIN_FROZEN_AFTER + timedelta(hours=1)
    outside = NOW - events_route._SEARCH_TWIN_FROZEN_AFTER - timedelta(hours=1)
    assert not events_route._search_market_is_past_and_frozen(_truist(stamp=inside), now=NOW)
    assert events_route._search_market_is_past_and_frozen(_truist(stamp=outside), now=NOW)


def test_every_search_surface_asks_the_predicate():
    # The flat list and the families both ask `_futures_card_has_no_answer`
    # (pinned by #3412/#6327's tests); the promoted-headline filter and the
    # typeahead pool do not, so each carries the predicate by name.
    src = Path(events_route.__file__).read_text()
    union = src[src.index("def _futures_card_has_no_answer("):]
    union = union[: union.index("\ndef ")]
    assert "or _search_market_is_past_and_frozen(market)" in union
    assert "and not _search_market_is_past_and_frozen(m)\n" in src
    typeahead = src[src.index("for market in ta_futures_ranked:"):]
    head = typeahead[: typeahead.index("dedup_key = _normalize_futures_dedup_key(market)")]
    assert "if _search_market_is_past_and_frozen(market):\n            continue" in head
    assert src.count("_search_market_is_past_and_frozen(") == 4  # def + 3 call sites
