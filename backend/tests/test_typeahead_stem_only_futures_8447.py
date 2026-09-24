"""#8447 — a team query stops offering futures that only share a word STEM with it.

Production 2026-09-24 (`x-bainluck-origin: latency`): `/typeahead?q=angels` served
`Los Angeles Mayor winner?`, `Los Angeles City Council District 13 winner election?`
and `Los Angeles County Sheriff winner?`; `q=nationals` served `Navajo Nation
presidential election winner?` and two College Football National Championship
markets. Postgres's english stemmer folds `angels`/`Angeles` to `angel` and
`nationals`/`Nation` to `nation`, so the FTS half of `_futures_name_arms` admits
them, and the reranker keeps them as "outcome-only" rows although no outcome names
the team.

The rows are real specimens. The controls are the reasons the FTS half exists and
the substring rows other gates already pin.
"""

import inspect
from types import SimpleNamespace

from app.routes.events import (
    _typeahead_stem_only_futures,
    expand_search_terms,
    typeahead_search,
)


def _market(name: str, *outcomes: str):
    return SimpleNamespace(
        name=name, outcomes=[SimpleNamespace(name=o) for o in outcomes]
    )


def _exp(q: str):
    return expand_search_terms(q.split())


ANGELS = "Los Angeles Angels"
NATIONALS = "Washington Nationals"


class TestTheSpecimensAreDropped:
    def test_los_angeles_city_races_for_angels(self):
        for name, legs in (
            ("Los Angeles Mayor winner?", ("Karen Bass", "Rick Caruso")),
            ("Los Angeles City Council District 13 winner election?", ("Hugo Soto-Martinez",)),
            ("Los Angeles County Sheriff winner?", ("Robert Luna", "Alex Villanueva")),
        ):
            assert _typeahead_stem_only_futures(_market(name, *legs), _exp("angels"), ANGELS), name

    def test_navajo_nation_and_the_national_championship_for_nationals(self):
        for name, legs in (
            ("Navajo Nation presidential election winner?", ("Buu Nygren",)),
            ("College Football National Championship Winner", ("Texas", "Ohio State")),
        ):
            assert _typeahead_stem_only_futures(
                _market(name, *legs), _exp("nationals"), NATIONALS
            ), name

    def test_the_full_team_name_typed_still_drops_the_mayor_race(self):
        m = _market("Los Angeles Mayor winner?", "Karen Bass")
        assert _typeahead_stem_only_futures(m, _exp("los angeles angels"), ANGELS)


class TestTheTeamsOwnMarketsStay:
    def test_a_name_that_contains_the_word(self):
        m = _market("Will the Anaheim Angels naming bill become law?", "Yes", "No")
        assert not _typeahead_stem_only_futures(m, _exp("angels"), ANGELS)

    def test_a_market_whose_outcome_names_the_team(self):
        m = _market("MLB World Series Champion 2026", "Los Angeles Dodgers", "Los Angeles Angels")
        assert not _typeahead_stem_only_futures(m, _exp("angels"), ANGELS)

    def test_a_game_market_named_for_the_team(self):
        m = _market("Los Angeles Angels vs. Seattle Mariners - First 5 Innings Winner", "Angels", "Mariners")
        assert not _typeahead_stem_only_futures(m, _exp("angels"), ANGELS)

    def test_an_interior_substring_row_is_never_touched(self):
        # #4723's control: reachable by `pats` by interior substring only.
        m = _market("Doubles: Huergo/Korpatsch vs Chan/Joint", "Huergo/Korpatsch")
        assert not _typeahead_stem_only_futures(m, _exp("pats"), "Korpatsch Pats")


class TestTheGateHoldsWhenNoTeamIsNamed:
    def test_no_lead_team_changes_nothing(self):
        m = _market("NBA Champion 2026", "Boston Celtics")
        assert not _typeahead_stem_only_futures(m, _exp("champions"), None)

    def test_a_lead_team_that_does_not_carry_the_typed_word_changes_nothing(self):
        # `champions` resolving some team into slot 0 by a fuzzy path must not
        # switch off the stem recall `_build_futures_name_filter` was built for.
        m = _market("NBA Champion 2026", "Boston Celtics")
        assert not _typeahead_stem_only_futures(m, _exp("champions"), "Champion Hill FC")

    def test_an_empty_query_changes_nothing(self):
        m = _market("Los Angeles Mayor winner?", "Karen Bass")
        assert not _typeahead_stem_only_futures(m, [], ANGELS)


class TestTheRouteCallsIt:
    """The helper is inert unless the dropdown asks it, after the rerank, before the cut."""

    def test_typeahead_filters_the_ranked_futures_with_the_lead_team(self):
        src = inspect.getsource(typeahead_search)
        call = '_typeahead_stem_only_futures(m, ta_expanded, _ta_lead_team["text"])'
        assert call in src
        assert src.index("ta_futures_ranked = _rerank_search_futures(") < src.index(call)
        assert src.index(call) < src.index("for market in ta_futures_ranked:")
