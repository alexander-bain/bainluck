"""The playoff-grid league prefilter, driven through the PRODUCTION builder.

Two arms, deliberately:

1. ``_build_league_name_conditions`` is the real function ``get_playoff_grid``
   calls. Compiling its output and matching real production market names
   against it proves the SQL the grid actually issues can see those rows. A
   pure-converter test alone would stay green if the builder stopped calling
   the converter.

2. ``_market_passes_league_filter`` is the authoritative Python decision. The
   SQL fix widened the candidate pool, which un-masked over-broad league
   patterns that had never been reachable before — a foreign "Premier League",
   a stadium-host market, a reach-the-final market. Those assertions live here
   because an empty grid and a contaminated grid are both failures.

Every market name below was read from production on 2026-08-29.
"""

import re

import pytest
from sqlalchemy.dialects import postgresql

from app.config.league_configs import get_league_config
from app.routes.playoffs import (
    _build_league_name_conditions,
    _market_passes_league_filter,
)


def _ilike_bodies(slug: str) -> list[str]:
    """Compile the production builder's output and extract its ILIKE bodies."""
    conditions = _build_league_name_conditions(get_league_config(slug))
    bodies: list[str] = []
    for cond in conditions:
        sql = str(
            cond.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        # literal_binds doubles `%` for the DBAPI; undo that before reading.
        bodies.extend(re.findall(r"ILIKE '(.*?)'", sql.replace("%%", "%")))
    return bodies


def _any_body_matches(bodies: list[str], name: str) -> bool:
    for body in bodies:
        parts = [re.escape(p.replace(r"\_", "_")) for p in body.split("%")]
        if re.search(".*".join(parts), name, re.IGNORECASE):
            return True
    return False


class TestTheGridCanSeeMarketsThatExist:
    """The ship: these markets are open, tier-1 and priced, and the grid
    served ``teams: []`` over them."""

    @pytest.mark.parametrize(
        "slug,market_name",
        [
            # /playoffs/la-liga rendered "No championship odds available yet".
            ("la-liga", "La Liga Champion"),
            ("la-liga", "La Liga Winner"),
            ("la-liga", "La Liga Relegation"),
            ("la-liga", "La Liga Top 4 Finishers"),
            # /playoffs/champions-league, same empty state.
            ("champions-league", "Champions League Winner"),
            ("champions-league", "Champions League: League of Champion"),
            ("champions-league", "Champions League Quarterfinals Qualifiers"),
            ("champions-league", "Champions League Semifinals Qualifiers"),
            # /playoffs/epl rendered, but with no Champion column at all.
            ("epl", "English Premier League Champion"),
            ("epl", "English Premier League Winner?"),
            # NFL had no Division column.
            ("nfl", "Pro Football: AFC East Champion"),
            ("nfl", "Pro Football: NFC West Champion"),
        ],
    )
    def test_production_builder_emits_sql_that_matches_the_market(self, slug, market_name):
        bodies = _ilike_bodies(slug)
        assert _any_body_matches(bodies, market_name), (
            f"{slug}: none of {bodies} can match {market_name!r} — the grid's "
            f"own SQL cannot see a market that exists"
        )

    def test_the_market_also_passes_the_authoritative_python_filter(self):
        """SQL visibility is worthless if the Python gate then rejects it."""
        cases = [
            ("la-liga", "La Liga Champion", "KXLALIGA-27"),
            ("champions-league", "Champions League Winner", "KXUCL-27"),
            ("epl", "English Premier League Champion", "KXPREMIERLEAGUE-27"),
        ]
        for slug, name, eid in cases:
            cfg = get_league_config(slug)
            assert _market_passes_league_filter(name, eid, cfg), f"{slug}: {name}"


class TestTheFixDoesNotContaminateAGrid:
    """Widening the prefilter exposed patterns that were over-broad all along.

    An empty grid is a bug; a grid showing another competition is a worse one.
    """

    @pytest.mark.parametrize(
        "name,external_id",
        [
            ("Caribbean Premier League Champion", "KXCPL-26"),
            ("Kazakhstan Premier League: 2026 Winner", "836155"),
            ("Kazakhstan Premier League: Teams relegated (2026)", "917806"),
            ("Lanka Premier League Champion", "KXLPL-26"),
        ],
    )
    def test_a_foreign_premier_league_stays_out_of_the_english_grid(self, name, external_id):
        cfg = get_league_config("epl")
        assert not _market_passes_league_filter(name, external_id, cfg), (
            f"{name!r} would appear on /playoffs/epl"
        )

    def test_the_english_premier_league_itself_is_not_caught_by_those_exclusions(self):
        """The control: tightening must not throw out the league it protects."""
        cfg = get_league_config("epl")
        for name, eid in [
            ("English Premier League Champion", "KXPREMIERLEAGUE-27"),
            ("English Premier League Winner?", "KXPREMIERLEAGUE-26"),
        ]:
            assert _market_passes_league_filter(name, eid, cfg), name

    def test_the_super_bowl_host_market_is_not_an_nfl_title_market(self):
        cfg = get_league_config("nfl")
        assert not _market_passes_league_filter(
            "Who will host the 2031 Pro Football Championship?", "KXSBHOST-2031", cfg
        )

    def test_a_world_series_matchup_market_is_not_a_champion_market(self):
        cfg = get_league_config("mlb")
        assert not _market_passes_league_filter(
            "Pro Baseball Championship Series Matchup", "KXTEAMSINWS-26", cfg
        )

    def test_a_first_time_winner_prop_is_not_a_golfer(self):
        cfg = get_league_config("golf")
        assert not _market_passes_league_filter(
            "U.S. Open: First Time Winner?", "602824", cfg
        )

    @pytest.mark.parametrize(
        "name",
        [
            "College Football SEC Championship Winner",
            "College Football Big Ten Championship Winner",
            "College Football ACC Championship Game Qualifiers",
            "College Football FCS National Championship Winner",
        ],
    )
    def test_a_conference_title_does_not_sit_in_the_national_champion_column(self, name):
        # This grid has make_playoffs / semifinal / championship and no
        # conference column, so the stage fallback files these under
        # `championship` beside national-title odds.
        cfg = get_league_config("ncaa-football")
        assert not _market_passes_league_filter(name, "KXNCAAFSEC-26", cfg), name

    def test_reaching_the_final_is_not_winning_it(self):
        cfg = get_league_config("ncaa-football")
        assert not _market_passes_league_filter(
            "Will Alabama Make the 2027 College Football Playoff National Championship",
            "0x198ceb80",
            cfg,
        )

    @pytest.mark.parametrize(
        "name",
        [
            "College Football National Championship Qualifiers",
            "College Football National Championship Game Qualifiers",
        ],
    )
    def test_kalshis_finalist_series_is_not_winning_it(self, name):
        # #8885: KXNCAAFFINALIST-27 asks who REACHES the title game (Georgia
        # 32.5%, Ohio St. 28%). Filed under `championship` it merged with the
        # Winner market by team name, and the Champion chart drew a 12%<->30%
        # sawtooth that ended on "Ohio St. 28%" beside a table reading 10%.
        cfg = get_league_config("ncaa-football")
        assert not _market_passes_league_filter(name, "KXNCAAFFINALIST-27", cfg), name

    def test_the_real_national_championship_markets_still_pass(self):
        """Control for the exclusions above."""
        cfg = get_league_config("ncaa-football")
        for name, eid in [
            ("College Football National Championship Winner", "KXNCAAF-27"),
            ("NCAAF Championship Winner", "americanfootball_ncaaf_championship_winner"),
        ]:
            assert _market_passes_league_filter(name, eid, cfg), name

    def test_the_champion_column_holds_only_the_winner_markets(self):
        """#8885, end to end: the three production markets the Champion stage
        served on 2026-09-26 go through the same two gates the route runs, and
        only the two that ask who WINS reach the column."""
        from types import SimpleNamespace

        from app.routes.playoffs import _match_market_to_column

        cfg = get_league_config("ncaa-football")
        served = [
            (181, "KXNCAAF-27", "College Football National Championship Winner"),
            (182, "KXNCAAFFINALIST-27", "College Football National Championship Qualifiers"),
            (6601311, "americanfootball_ncaaf_championship_winner", "NCAAF Championship Winner"),
        ]
        champion = [
            mid
            for mid, eid, name in served
            if _market_passes_league_filter(name, eid, cfg)
            and _match_market_to_column(
                SimpleNamespace(id=mid, external_id=eid, market_tier=1, name=name), cfg
            )
            == "championship"
        ]
        assert champion == [181, 6601311]



# #8893: the #8885 defect on five more Stage charts. Each tuple is a market the
# column's `market_ids` served on 2026-09-26 (id, external_id, name, tier), read
# from production; `True` means it asks the stage's own question and must stay.
_STAGE_SPECIMENS = {
    ("mlb", "pennant"): [
        (270, "KXMLBNL-26", "National League Champion", 2, True),
        (274, "KXMLBAL-26", "American League Champion", 2, True),
        (199045, "215866", "MLB: 2026 American League Champion", 2, True),
        (199050, "215871", "MLB: 2026 National League Champion", 2, True),
        (62383707, "KXMLBNLCSQUAL-26", "Pro Baseball NLCS Qualifiers", 5, False),
        (62383708, "KXMLBALCSQUAL-26", "Pro Baseball ALCS Qualifiers", 5, False),
    ],
    ("nfl", "conference"): [
        (31615, "KXNFLNFCCHAMP-27", "NFC Championship Winner", 2, True),
        (31616, "KXNFLAFCCHAMP-27", "AFC Championship Winner", 2, True),
        (129171, "203716", "Pro Football: 2027 NFC Champion ", 2, True),
        (129172, "203722", "Pro Football: 2027 AFC Champion ", 2, True),
        (60473181, "KXNFLROUNDQUAL-27CONF", "NFL Conference Championship Qualifiers", 2, False),
    ],
    ("nba", "conference"): [
        (52755681, "KXNBAWEST-27", "Pro Basketball Western Conference Champion", 2, True),
        (52755687, "KXNBAEAST-27", "Pro Basketball Eastern Conference Champion", 2, True),
        (52755664, "KXNBACONF-27", "Conference to Win Pro Basketball Finals", 2, False),
        (55686462, "KXNBANEXTTEAMCONF-26LJAMES23", "LeBron James' Next Conference", 2, False),
        (61461612, "KXNBAWCFQUAL-27", "Pro Basketball Western Conference Finals Qualifiers", 2, False),
    ],
    ("wnba", "championship"): [
        (9413479, "350828", "WNBA: 2026 Champion", 1, True),
        (12046267, "KXWNBA-26", "Women's Pro Basketball Champion", 1, True),
        (56945896, "KXWNBA3PTROUND-26FINAL", "3-Point Contest Championship Round Qualifiers", 1, False),
    ],
    ("champions-league", "championship"): [
        (31834253, "KXUCL-27", "Champions League Winner", 1, True),
        (60607786, "994204", "UEFA Champions League: League Phase Winner", 1, False),
    ],
}


class TestAStageColumnHoldsOnlyItsOwnQuestion:
    """#8893, end to end through the two gates the route runs, like #8885's
    Champion test above. The `True` rows are the control: an exclusion that
    swallowed the real stage markets would empty the chart instead."""

    @pytest.mark.parametrize("slug,column", sorted(_STAGE_SPECIMENS))
    def test_only_the_stages_own_markets_reach_its_column(self, slug, column):
        from types import SimpleNamespace

        from app.routes.playoffs import _match_market_to_column

        cfg = get_league_config(slug)
        reached = [
            mid
            for mid, eid, name, tier, _ in _STAGE_SPECIMENS[(slug, column)]
            if _market_passes_league_filter(name, eid, cfg)
            and _match_market_to_column(
                SimpleNamespace(id=mid, external_id=eid, market_tier=tier, name=name), cfg
            )
            == column
        ]
        expected = [mid for mid, *_, keep in _STAGE_SPECIMENS[(slug, column)] if keep]
        assert reached == expected

    @pytest.mark.parametrize(
        "slug,eid,name",
        [
            ("nba", "KXNBAECFQUAL-27", "Pro Basketball Eastern Conference Finals Qualifiers"),
            ("champions-league", "KXUCLTOP8-27", "League Phase Top 8 Finishers"),
            ("champions-league", "1024892", "UEFA Champions League: Team to Finish 9th-24th in League Phase"),
        ],
    )
    def test_the_open_siblings_are_refused_too(self, slug, eid, name):
        # Open on production 2026-09-26 but not (yet) in a column: the same
        # questions under their other names.
        assert not _market_passes_league_filter(name, eid, get_league_config(slug)), name


class TestPrefilterNeverNarrows:
    def test_an_unpushable_pattern_widens_to_the_whole_category(self):
        """A pattern with no literal text must not silently drop rows.

        The config deliberately mixes a pushable pattern with an unpushable
        one. With only the unpushable pattern, "skip it" and "widen" both end
        up at the no-conditions fallback and the assertion cannot tell them
        apart — so skipping would pass a test it should fail.
        """

        class _Cfg:
            sport_category = "soccer"
            league_name_patterns = [r"\bLa\s+Liga\b", r"\b\w+\b"]

        conditions = _build_league_name_conditions(_Cfg())
        assert len(conditions) == 1, (
            "an unpushable pattern must collapse the whole filter to the "
            "category, not leave the pushable siblings behind as a narrower "
            "filter than the regexes"
        )
        sql = str(
            conditions[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "ILIKE" not in sql, "an unpushable pattern must widen, not filter"
        assert "llm_sport_category" in sql

    def test_a_league_with_no_patterns_falls_back_to_the_category(self):
        class _Cfg:
            sport_category = "hockey"
            league_name_patterns = []

        conditions = _build_league_name_conditions(_Cfg())
        assert len(conditions) == 1
        sql = str(
            conditions[0].compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        assert "ILIKE" not in sql
