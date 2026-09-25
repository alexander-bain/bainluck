"""#5082 — a team query stops offering other-sport futures above the team's own.

Production 2026-09-25 05:25Z (`x-bainluck-origin: agent-latency`):

    /typeahead?q=pats   5-7  TX-04 / NC-10 / NY-18 House election: Pat ... vote percent
    /typeahead?q=dodg   2    Will Dodge release a new Challenger Hellcat before 2027?

Two mechanisms, one defect a reader sees:

* `pats` is a curated nickname (`_TEAM_NICKNAME_EXPANSIONS`) and is NOT inside
  "New England Patriots", so #8447's stem-only gate never opened, and the
  stemmer's `pats` -> `pat` fold reached the dropdown as three House races.
* `dodg` IS inside "Dodge", so the Hellcat row is a real substring hit. It is
  kept, and ranked below the Dodgers' rows by the wrong-sport demotion (#7259),
  which the typeahead now arms with the sport its resolved teams agree on.

Nothing here touches `/search`: both rows stay reachable there.
"""

from types import SimpleNamespace

from app.routes.events import (
    _rerank_search_futures,
    _typeahead_stem_only_futures,
    _typeahead_team_sport_category,
    expand_search_terms,
)


def _market(name: str, *outcomes: str, category: str | None = None, tier: int = 1):
    return SimpleNamespace(
        name=name,
        outcomes=[SimpleNamespace(name=o) for o in outcomes],
        llm_sport_category=category,
        market_tier=tier,
        volume_24h=0,
        volume=0,
    )


def _exp(q: str):
    return expand_search_terms(q.split())


PATRIOTS = "New England Patriots"


class TestTheNicknameOpensTheStemGate:
    def test_the_three_house_races_are_dropped_for_pats(self):
        for name in (
            "TX-04 House election: Pat Fallon vote percent",
            "NC-10 House election: Pat Harrigan vote percent",
            "NY-18 House election: Pat Ryan vote percent",
        ):
            m = _market(name, "Above 60%", "Above 65%", category="politics")
            assert _typeahead_stem_only_futures(m, _exp("pats"), PATRIOTS), name

    def test_the_patriots_own_markets_stay(self):
        for m in (
            _market("Will the New England Patriots make the 2027 NFL Playoffs?", "Yes", "No"),
            _market("PIT Steelers vs NE Patriots", "Pittsburgh", "New England"),
            _market("Pro Football Champion 2027", "Kansas City Chiefs", "New England Patriots"),
        ):
            assert not _typeahead_stem_only_futures(m, _exp("pats"), PATRIOTS), m.name

    def test_an_interior_substring_row_is_still_never_touched(self):
        # #4723 / this issue's original specimen: Korpatsch contains `pats`, so
        # clause 2 keeps it here; the sport demotion below is what ranks it.
        m = _market("Set 1 Winner: Huergo/Korpatsch vs Chan/Joint", "Huergo/Korpatsch")
        assert not _typeahead_stem_only_futures(m, _exp("pats"), PATRIOTS)

    def test_the_nickname_must_name_THIS_team(self):
        # A lead team the nickname does not belong to leaves the gate shut.
        m = _market("TX-04 House election: Pat Fallon vote percent", "Above 60%")
        assert not _typeahead_stem_only_futures(m, _exp("pats"), "Patriot League All-Stars FC")
        assert not _typeahead_stem_only_futures(m, _exp("pats"), "Boston Red Sox")

    def test_a_multi_word_query_does_not_take_the_nickname_path(self):
        m = _market("TX-04 House election: Pat Fallon vote percent", "Above 60%")
        assert not _typeahead_stem_only_futures(m, _exp("pats fallon"), PATRIOTS)


class TestTheTeamPoolNamesOneSport:
    def test_one_team_resolves_its_sport(self):
        assert _typeahead_team_sport_category([{"sport_key": "baseball_mlb"}]) == "baseball"

    def test_the_prefix_is_translated_not_compared(self):
        # `americanfootball` is stored as `football`; comparing the raw prefix
        # would call every NFL market wrong-sport.
        assert (
            _typeahead_team_sport_category([{"sport_key": "americanfootball_nfl"}])
            == "football"
        )

    def test_teams_that_disagree_resolve_nothing(self):
        giants = [{"sport_key": "baseball_mlb"}, {"sport_key": "americanfootball_nfl"}]
        assert _typeahead_team_sport_category(giants) is None

    def test_no_team_and_no_sport_key_resolve_nothing(self):
        assert _typeahead_team_sport_category([]) is None
        assert _typeahead_team_sport_category([{"sport_key": None}]) is None


class TestTheHellcatRanksBelowTheDodgers:
    def test_dodg_orders_the_dodgers_rows_first(self):
        hellcat = _market(
            "Will Dodge release a new Challenger Hellcat before 2027?", "Yes", "No",
            category="auto", tier=5,
        )
        game = _market(
            "Los Angeles Dodgers vs. San Francisco Giants", "Dodgers", "Giants",
            category="baseball",
        )
        inning = _market(
            "Los Angeles Dodgers vs. San Francisco Giants - 2nd Inning Winner",
            "Dodgers", "Giants", category="baseball",
        )
        pool = [hellcat, game, inning]
        sport = _typeahead_team_sport_category([{"sport_key": "baseball_mlb"}])
        ranked = _rerank_search_futures(pool, _exp("dodg"), sport)
        assert ranked[-1] is hellcat
        assert ranked.index(game) < ranked.index(hellcat)

    def test_without_a_resolved_sport_the_order_is_the_old_one(self):
        # The strawman: the same pool with no category keeps what production served.
        hellcat = _market("Will Dodge release a new Challenger Hellcat before 2027?", category="auto")
        game = _market("Los Angeles Dodgers vs. San Francisco Giants", category="baseball")
        assert _rerank_search_futures([hellcat, game], _exp("dodg")) == _rerank_search_futures(
            [hellcat, game], _exp("dodg"), None
        )
