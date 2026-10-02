"""#10230 — a name match nobody trades yields to a traded market where the typed word is a contender.

Production 2026-10-02 19:58Z, `q=judge` at 390px: the dropdown was the House
impeachment question and four Texas county-judge races; nothing about Aaron Judge.
The futures pool held his markets, and `_rerank_search_futures` put every NAME match
ahead of every outcome-only row whatever either traded. Fixture values are the
production rows (id, name, tier, volume, the Judge leg's price).
"""

from __future__ import annotations

from app.routes import events as events_route
from app.utils.search_headline_contender import (
    MIN_CONTENDER_VOLUME,
    is_traded_contender_market,
)


class _Outcome:
    def __init__(self, name, p):
        self.name = name
        self.current_probability = p


class _Market:
    def __init__(self, id, name, volume, legs, market_tier=1, category="politics"):
        self.id = id
        self.source = "kalshi"
        self.name = name
        self.market_tier = market_tier
        self.volume = volume
        self.outcomes = [_Outcome(n, p) for n, p in legs]
        self.canonical_market_key = None
        self.external_id = None
        self.llm_sport_category = category
        self.sport = None


def _judge_pool():
    county = [
        _Market(60481098, "Harris County Judge winner?", 4005,
                [("Letitia Plummer", 0.86), ("Other", 0.14)]),
        *[
            _Market(mid, f"{c} County Judge winner?", None, [("A", 0.7), ("B", 0.3)])
            for mid, c in [
                (63135151, "Bexar"), (63135150, "Collin"), (63135142, "Tarrant"),
                (63135147, "Fort Bend"), (63135148, "El Paso"),
            ]
        ],
    ]
    impeach = _Market(112810, "Will the House impeach a federal judge this year?",
                      8056, [("Yes", 0.0905)], market_tier=5, category="legal")
    show_cover = _Market(24014885, "MLB The Show 27: Cover Athlete", 21820,
                         [("Cal Raleigh", 0.40), ("Aaron Judge", 0.085)],
                         market_tier=5, category="baseball")
    al_mvp = _Market(216, "AL MVP Winner?", 5055009,
                     [("Cal Raleigh", 0.95), ("Aaron Judge", 0.01)],
                     market_tier=3, category="baseball")
    alcs_mvp = _Market(62952891, "ALCS MVP Winner", None,
                       [("Aaron Judge", 0.064)], market_tier=3, category="baseball")
    return county, impeach, show_cover, al_mvp, alcs_mvp


JUDGE = [("judge", None)]


def _ids(rows):
    return [m.id for m in rows]


def test_precondition_every_judge_name_match_is_thin_and_the_old_rule_buries_the_contender():
    county, impeach, show_cover, _al_mvp, _alcs = _judge_pool()
    for m in [*county, impeach]:
        assert events_route._query_name_match(m, JUDGE)
        assert (m.volume or 0) < MIN_CONTENDER_VOLUME
    assert not events_route._query_name_match(show_cover, JUDGE)
    assert show_cover.volume >= MIN_CONTENDER_VOLUME


def test_judge_dropdown_reaches_an_aaron_judge_market_in_its_first_five():
    county, impeach, show_cover, al_mvp, alcs_mvp = _judge_pool()
    ranked = events_route._rerank_search_futures(
        [*county, impeach, al_mvp, alcs_mvp, show_cover], JUDGE
    )
    assert ranked[0] is show_cover
    assert show_cover in ranked[:5]


def test_a_one_percent_leg_is_not_a_contender_even_in_a_five_million_market():
    _c, _i, _s, al_mvp, alcs_mvp = _judge_pool()
    # AL MVP prices Judge at 1%: the longshot shape the lane refuses for LeBron.
    assert not is_traded_contender_market(al_mvp, JUDGE)
    # ALCS MVP prices him at 6.4% with no recorded volume: not a traded market.
    assert not is_traded_contender_market(alcs_mvp, JUDGE)


def test_lebron_keeps_his_name_matches_over_fields_that_list_him_at_a_twentieth_of_a_percent():
    q = [("lebron", None)]
    retire = _Market(276, "LeBron James to Announce his Retirement Before the 2026-27 Season",
                     3252780, [("Yes", 0.3)], category="basketball")
    run = _Market(58336022, "Will LeBron James announce a Presidential run before 2028?",
                  None, [("Yes", 0.02)], category="politics")
    nominee = _Market(112895, "Democratic Presidential Nominee 2028", 1286967999,
                      [("Gavin Newsom", 0.3), ("LeBron James", 0.0005)])
    ranked = events_route._rerank_search_futures([nominee, run, retire], q)
    assert _ids(ranked) == [276, 58336022, 112895]


def test_a_traded_name_match_still_leads_the_contender():
    q = [("mahomes", None)]
    traded_name = _Market(1, "Patrick Mahomes 4,500+ passing yards?", 50000, [("Yes", 0.55)],
                          category="football")
    thin_name = _Market(63405382, "Patrick Mahomes: Passing Touchdowns O/U 3.5", None,
                        [("Over", 0.5)], category="football")
    mvp = _Market(40532, "MVP Winner?", 24003316,
                  [("Josh Allen", 0.2), ("Patrick Mahomes", 0.085)], category="football")
    ranked = events_route._rerank_search_futures([thin_name, mvp, traded_name], q)
    assert _ids(ranked) == [1, 40532, 63405382]


def test_a_partial_word_is_not_a_contender_so_keystrokes_before_the_word_is_whole_are_unchanged():
    county, impeach, show_cover, _a, _b = _judge_pool()
    q = [("jud", None)]
    assert not is_traded_contender_market(show_cover, q)
    rows = [*county, impeach, show_cover]
    ranked = events_route._rerank_search_futures(rows, q)
    assert ranked[-1] is show_cover


def test_multi_word_query_needs_every_word_in_one_outcome():
    _c, _i, show_cover, _a, _b = _judge_pool()
    assert is_traded_contender_market(show_cover, [("aaron", None), ("judge", None)])
    assert not is_traded_contender_market(show_cover, [("aaron", None), ("raleigh", None)])


def test_an_unpriced_leg_or_a_market_without_outcomes_is_never_a_contender():
    no_price = _Market(9, "X", 50000, [("Aaron Judge", None)])
    assert not is_traded_contender_market(no_price, JUDGE)
    bare = _Market(10, "X", 50000, [])
    del bare.outcomes
    assert not is_traded_contender_market(bare, JUDGE)
