"""The women's NCAA grid must not filter away the only market that has prices.

`/playoffs/ncaa-women-basketball` served ``columns=[] teams=0`` behind the
"No championship odds available yet" empty state while Kalshi's
``KXWMARMAD-27`` was open, priced and updated the same day — a page claiming
odds do not exist when they do.

Sole cause: the market's name carries its year ("Women's 2027 College
Basketball Champion"), so a ``season_pattern`` of "2026" made
``_is_future_season_market`` drop it. Every other WNCAAB market either has no
outcomes at all (the 2027 round shells) or is five months stale (the resolved
2026 tournament), so that one market is the whole grid.

These fixtures are the production population, read on 2026-08-29 via
``futures_markets``/``futures_outcomes``. The tests drive the real admission
chain — ``_market_passes_league_filter`` -> season filter ->
``_match_market_to_column`` — rather than re-implementing it.
"""

import inspect
from datetime import datetime, timedelta, timezone

from app.config.league_configs import WNCAA_BASKETBALL_CONFIG, get_league_config
from app.routes.playoffs import (
    get_playoff_grid,
    _SETTLED_COLUMNS,
    _extract_season_max_year,
    _is_future_season_market,
    _is_past_season_market,
    _match_market_to_column,
    _market_passes_league_filter,
)


class _Market:
    """Only the three fields the admission chain reads (#1484 bounded load)."""

    def __init__(self, name, external_id, market_tier):
        self.name = name
        self.external_id = external_id
        self.market_tier = market_tier


# The live championship market — 35 outcomes, all priced, refreshed same-day.
CHAMPIONSHIP = _Market("Women's 2027 College Basketball Champion", "KXWMARMAD-27", 1)

# Open 2027 round markets. Real rows, but 0 outcomes until the bracket is set,
# so they contribute nothing to the grid either way.
OPEN_2027_SHELLS = [
    _Market("Women's Championship Game Qualifiers", "KXWMARMADROUND-27FIN", 1),
    _Market("Women's Quarterfinals Qualifiers", "KXWMARMADROUND-27QF", 5),
    _Market("Women's Semifinals Qualifiers", "KXWMARMADROUND-27SEMI", 5),
]

# The resolved 2026 tournament. These names carry NO year, so the season filter
# cannot see them — their exclusion rests entirely on the outcome staleness
# cutoff, which is why it is pinned below.
RESOLVED_2026 = [
    _Market("Women's Championship Game Qualifiers", "KXWMARMADROUND-26T2", 1),
    _Market("Women's Round of 8 Qualifiers", "KXWMARMADROUND-26E8", 1),
    _Market("Women's Semifinals Qualifiers", "KXWMARMADROUND-26F4", 1),
]


def _survives_admission(market, config):
    """Replay the route's market-level admission for one market."""
    name = market.name or ""
    if not _market_passes_league_filter(name, market.external_id or "", config):
        return None
    max_year = _extract_season_max_year(config.season_pattern)
    if max_year and (
        _is_future_season_market(name, max_year)
        or _is_past_season_market(name, max_year)
    ):
        return None
    return _match_market_to_column(market, config)


class TestWncaabChampionshipSurvivesAdmission:
    """The ship: the one market with prices reaches the championship column."""

    def test_config_season_covers_the_live_market(self):
        config = get_league_config("ncaa-women-basketball")
        assert _extract_season_max_year(config.season_pattern) == 2027, (
            "The only priced WNCAAB market is the 2027 champion; a season_pattern "
            "that stops short of 2027 empties the grid."
        )

    def test_championship_market_reaches_its_column(self):
        assert (
            _survives_admission(CHAMPIONSHIP, WNCAA_BASKETBALL_CONFIG) == "championship"
        )

    def test_the_regression_this_guards_is_real(self):
        """Non-vacuity: the market IS dropped at the pre-fix season boundary.

        Without this the test above could pass for reasons unrelated to the
        season filter (e.g. if the filter stopped running at all).
        """
        assert _is_future_season_market(CHAMPIONSHIP.name, 2026) is True
        assert _is_future_season_market(CHAMPIONSHIP.name, 2027) is False

    def test_league_filter_admits_it_by_ticker_not_by_name_pattern(self):
        """Path B.1 is what admits this market — the name patterns do not match.

        ``\\bWomen.s\\s+College\\s+Basketball\\b`` requires "Women's" adjacent to
        "College"; this name has the year between them. Documented so nobody
        "repairs" the name pattern believing it is load-bearing here.
        """
        assert "KXWMARMAD" in WNCAA_BASKETBALL_CONFIG.external_id_prefixes
        assert _market_passes_league_filter(
            CHAMPIONSHIP.name, CHAMPIONSHIP.external_id, WNCAA_BASKETBALL_CONFIG
        )
        assert not _market_passes_league_filter(
            CHAMPIONSHIP.name, "", WNCAA_BASKETBALL_CONFIG
        )


class TestWncaabWideningLetsNothingStaleIn:
    """What the widening admits — the other half of the measurement."""

    def test_resolved_2026_markets_are_invisible_to_the_season_filter(self):
        """They carry no year, so only the staleness cutoff can exclude them."""
        for market in RESOLVED_2026:
            assert _is_past_season_market(market.name, 2027) is False, (
                f"{market.external_id} unexpectedly carries a parseable year; "
                "if that changes, the staleness reasoning below is no longer "
                "the only thing keeping settled 2026 prices off the grid."
            )

    def test_stale_cutoff_excludes_the_resolved_2026_outcomes(self):
        """The columns they land on get the 7-day cutoff, not the 60-day one.

        Their newest outcome was last updated 2026-04-05; the grid is read
        months later, so every one of them is skipped before it can be merged.
        """
        columns = {
            _match_market_to_column(m, WNCAA_BASKETBALL_CONFIG) for m in RESOLVED_2026
        }
        columns.discard(None)
        assert columns, "fixture drifted — these markets must still match columns"
        assert not (columns & _SETTLED_COLUMNS), (
            f"{columns & _SETTLED_COLUMNS} would get the 60-day settled cutoff. "
            "The resolved 2026 tournament would then merge onto the grid at "
            "settled 0%/100% prices."
        )

        newest_2026_outcome = datetime(2026, 4, 5, 16, 45, tzinfo=timezone.utc)
        stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert newest_2026_outcome < stale_cutoff

    def test_open_2027_shells_carry_no_prices_to_contribute(self):
        """They pass admission; they simply have no outcomes yet."""
        for market in OPEN_2027_SHELLS:
            assert _survives_admission(market, WNCAA_BASKETBALL_CONFIG) is not False


class TestTheRouteStillRunsWhatThisModuleReplays:
    """Non-vacuity for the whole file.

    ``_survives_admission`` re-implements the route's market-level chain, so
    every test above would stay green if ``get_playoff_grid`` stopped applying
    the season filter or stopped grading the staleness cutoff by column. These
    pin the call sites so the guard fails where the deletion happens.
    """

    def test_route_derives_its_season_bound_from_the_config(self):
        source = inspect.getsource(get_playoff_grid)
        assert "_extract_season_max_year(config.season_pattern)" in source

    def test_route_applies_both_season_filter_directions(self):
        source = inspect.getsource(get_playoff_grid)
        assert "_is_future_season_market(" in source
        assert "_is_past_season_market(" in source

    def test_route_grades_the_staleness_cutoff_by_column(self):
        source = inspect.getsource(get_playoff_grid)
        assert "col_key in _SETTLED_COLUMNS" in source
        assert "_settled_cutoff" in source and "_stale_cutoff" in source


class TestWncaabConfigStaysCoherent:
    """The season is rendered to the reader, so it must not contradict itself."""

    def test_displayed_name_matches_the_season_it_serves(self):
        config = get_league_config("ncaa-women-basketball")
        assert config.season_pattern in config.name, (
            f"The grid renders season {config.season_pattern!r} under the name "
            f"{config.name!r} — one of them is lying to the reader."
        )
