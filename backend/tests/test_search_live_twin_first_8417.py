"""#8417 — search must not answer this season's question with last season's market.

`bainluck.com/search?q=premier league` and `?q=arsenal` (390px, 2026-09-24 ~18:00Z)
led with `English Premier League Winner?` at Arsenal >99%: Kalshi
KXPREMIERLEAGUE-26 (399), settled in May, no price since 2026-07-17, still stored
open. This season's `English Premier League Champion` (31834301, Arsenal 47.5%,
priced that morning) is the same question to the search key and lost both doors
on lifetime volume. Fixture values are the production rows (id, source, name,
market_tier, volume, the Arsenal leg); stamps are offsets from now, so no test
branches on the clock.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.routes import events as events_route
from app.utils.search_headline_contender import promote_headline_contenders

NOW = datetime.now(timezone.utc)
FROZEN = NOW - timedelta(days=69)  # 2026-07-17 against 2026-09-24
LIVE = NOW - timedelta(hours=5)


class _Outcome:
    def __init__(self, id, name, p, last_updated):
        self.id = id
        self.name = name
        self.current_probability = p
        self.last_updated = last_updated


class _Market:
    def __init__(self, id, name, volume, outcomes, source="kalshi", market_tier=1):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.volume = volume
        self.outcomes = outcomes
        self.canonical_market_key = None
        self.external_id = None
        self.llm_sport_category = "soccer"
        self.sport = None


def _pl_2026(stamp=FROZEN):
    return _Market(399, "English Premier League Winner?", 17268534,
                   [_Outcome(1, "Arsenal", 0.995, stamp)])


def _pl_2027(stamp=LIVE):
    return _Market(31834301, "English Premier League Champion", 3433374,
                   [_Outcome(2, "Arsenal", 0.475, stamp)])


def _scorer(stamp=LIVE):
    return _Market(59156924, "English Premier League: Top Goalscorer 2026-27", 145275,
                   [_Outcome(3, "Haaland", 0.4, stamp)], market_tier=5)


PL_QUERY = [("premier", None), ("league", None)]


def _page(rows):
    """The route's own per-row dedup decision, in order."""
    seen: set = set()
    kept: dict = {}
    return [m.id for m in rows if events_route._admit_search_future(m, seen, kept, [])]


def test_precondition_one_question_and_the_frozen_row_has_the_volume():
    # Without both of these the specimen cannot fail on the old rule.
    a, b = _pl_2026(), _pl_2027()
    assert events_route._search_question_identity(a) == events_route._search_question_identity(b)
    assert _page([a, b]) == [399]
    assert a.volume > b.volume


def test_premier_league_window_keeps_this_seasons_market():
    ranked = events_route._rerank_search_futures([_pl_2026(), _scorer(), _pl_2027()], PL_QUERY)
    assert _page(ranked) == [31834301, 59156924]


def test_arsenal_headline_slot_goes_to_the_live_market():
    # Contenders arrive volume-desc from `_headline_contender_statement`.
    contenders = events_route._live_twin_first([_pl_2026(), _pl_2027()])
    rows, promoted = promote_headline_contenders(
        [], contenders, dedup_key=events_route._normalize_futures_dedup_key
    )
    assert promoted == 1 and [m.id for m in rows] == [31834301]


def test_positions_outside_the_question_do_not_move():
    rows = [_pl_2026(), _scorer(), _pl_2027()]
    out = events_route._live_twin_first(rows)
    assert [m.id for m in out] == [31834301, 59156924, 399]


def test_both_live_is_untouched():
    rows = [_pl_2026(stamp=LIVE), _pl_2027()]
    assert events_route._live_twin_first(rows) is rows


def test_both_frozen_is_untouched():
    rows = [_pl_2026(), _pl_2027(stamp=FROZEN)]
    assert events_route._live_twin_first(rows) is rows


def test_an_undatable_twin_is_not_treated_as_live():
    rows = [_pl_2026(), _pl_2027(stamp=None)]
    assert events_route._live_twin_first(rows) is rows


def test_a_fresh_dash_leg_does_not_make_a_frozen_row_live():
    # A priceless leg renders `—`; it may not date the row (outcome_prints_a_price).
    stale = _pl_2026()
    stale.outcomes.append(_Outcome(9, "Other", None, LIVE))
    rows = [stale, _pl_2027(stamp=FROZEN)]
    assert events_route._live_twin_first(rows) is rows


def test_a_frozen_row_with_no_twin_keeps_its_place():
    rows = [_pl_2026(), _scorer()]
    assert [m.id for m in events_route._live_twin_first(rows)] == [399, 59156924]


def test_the_boundary_is_fourteen_days():
    just_live = NOW - timedelta(days=13)
    rows = [_pl_2026(), _pl_2027(stamp=just_live)]
    out = events_route._live_twin_first(rows, now=NOW)
    assert [m.id for m in out] == [31834301, 399]
    rows = [_pl_2026(), _pl_2027(stamp=NOW - timedelta(days=15))]
    assert events_route._live_twin_first(rows, now=NOW) is rows


def test_both_headline_lanes_and_the_reranker_apply_the_rule():
    # /search and /typeahead each hand `promote_headline_contenders` their own
    # contender list; the unit tests above cannot see either call site.
    from pathlib import Path

    src = Path(events_route.__file__).read_text()
    assert src.count("_live_twin_first(_headline_rows)") == 1
    assert src.count("_live_twin_first(_ta_headline_rows)") == 1
    assert src.count("return _live_twin_first(ordered)") == 1
