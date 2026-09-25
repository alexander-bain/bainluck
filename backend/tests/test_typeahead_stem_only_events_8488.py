"""#8488 — a team query stops offering GAMES that only share a word STEM with it.

Not a regression of #8447; the same stemmer fold on the event half of the dropdown.
Production 2026-09-24 23:35Z (`x-bainluck-origin: latency`), after #8447 went live:
`/typeahead?q=angels` served `Golden State Valkyries at Los Angeles Sparks` (event
15318172) and `San Diego Padres at Los Angeles Dodgers` (15317977) beneath the
Angels' own games. Postgres's english stemmer folds `angels`/`Angeles` to `angel`,
so the event FTS arm admits every Los Angeles fixture; neither row names the Angels.

The rows are real specimens. The controls are the substring and nickname rows the
dropdown must keep.
"""

import inspect

from app.routes.events import (
    _typeahead_stem_only_event,
    expand_search_terms,
    typeahead_search,
)
from app.utils.search_match_class import query_names_participant


def _exp(q: str):
    return expand_search_terms(q.split())


ANGELS = "Los Angeles Angels"
SPARKS = ("Los Angeles Sparks", "Golden State Valkyries")
DODGERS = ("Los Angeles Dodgers", "San Diego Padres")
ANGELS_GAME = ("Seattle Mariners", "Los Angeles Angels")


def _drops(participants, q, lead, names_participant=None):
    if names_participant is None:
        names_participant = query_names_participant(q, participants)
    return _typeahead_stem_only_event(participants, _exp(q), lead, names_participant)


class TestTheSpecimensAreDropped:
    def test_the_route_flag_does_not_already_save_them(self):
        # The fix is not redundant: the route's own participant test says these
        # rows do not name the query, and they still filled the empty slots.
        assert not query_names_participant("angels", SPARKS)
        assert not query_names_participant("angels", DODGERS)

    def test_sparks_and_dodgers_for_angels(self):
        assert _drops(SPARKS, "angels", ANGELS)
        assert _drops(DODGERS, "angels", ANGELS)


class TestTheTeamsOwnGamesAndSubstringRowsStay:
    def test_the_angels_own_game(self):
        assert not _drops(ANGELS_GAME, "angels", ANGELS)

    def test_a_row_the_route_flagged_is_never_touched(self):
        # Nickname admission or fetched by the lead team's id: the route's verdict wins.
        assert not _drops(SPARKS, "angels", ANGELS, names_participant=True)

    def test_a_substring_participant_stays(self):
        # `sox` resolves the Red Sox; the White Sox game carries the word.
        assert not _drops(
            ("Chicago White Sox", "Detroit Tigers"), "sox", "Boston Red Sox", False
        )

    def test_a_multi_word_city_query_keeps_the_city(self):
        # `los angeles` resolving the Angels must keep every Los Angeles game.
        assert not _drops(SPARKS, "los angeles", ANGELS, False)


class TestTheGateHoldsWhenNoTeamIsNamed:
    def test_no_lead_team_changes_nothing(self):
        assert not _drops(SPARKS, "angels", None, False)

    def test_a_lead_team_that_does_not_carry_the_typed_word_changes_nothing(self):
        # `pats` leads with the Patriots by nickname; the name lacks `pats`.
        assert not _drops(
            ("Seattle Seahawks", "New England Patriots"), "pats", "New England Patriots", False
        )

    def test_an_empty_query_changes_nothing(self):
        assert not _typeahead_stem_only_event(SPARKS, [], ANGELS, False)


class TestTheRouteCallsIt:
    """The helper is inert unless the dropdown asks it, after the collapse, before the cut."""

    def test_typeahead_filters_the_events_with_the_lead_team_and_the_route_flag(self):
        src = inspect.getsource(typeahead_search)
        call = "if not _typeahead_stem_only_event("
        assert call in src
        assert src.index("_ta_events, _ = collapse_duplicate_fixtures(_ta_rows)") < src.index(call)
        assert src.index(call) < src.index("for event in _ta_events[:_EVENT_POOL_SIZE]:")
        # The filter is armed by the lead team and REASSIGNS the list the loop reads.
        armed = "if _ta_lead_team is not None:\n        _ta_events = [\n            ev for ev in _ta_events\n            if not _typeahead_stem_only_event("
        assert armed in src
        block = src[src.index(call): src.index("for event in _ta_events[:_EVENT_POOL_SIZE]:")]
        assert '_ta_lead_team["text"]' in block
        assert "_ta_names_participant(ev) or ev.id in _ta_lead_team_row_ids" in block
