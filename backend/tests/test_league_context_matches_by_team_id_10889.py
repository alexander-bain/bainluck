"""#10889 — Season outcomes left the Blues column blank on Blues–Blue Jackets.

The event row spells the home club `St Louis Blues`; the NHL grid spells it
`St. Louis Blues`. `normalize_name` keeps the period, so the name lookup in
`enrich_event_with_context` compared `'st louis blues'` with
`'st. louis blues'` — no equality, no substring — and `league_context` carried
only `away_team`. Both rows already share `teams.id` 3705; the lookup now tries
it first.
"""

from types import SimpleNamespace

import pytest

from app.services import league_context as league_context_service
from app.services.league_context import (
    LeagueContext,
    TeamLeagueContext,
    enrich_event_with_context,
)
from app.utils.name_normalization import normalize_name


class _FakeScalarResult:
    def scalar(self):
        return "icehockey_nhl"


class _FakeDB:
    async def execute(self, statement):
        return _FakeScalarResult()


def _nhl_context() -> LeagueContext:
    blues = TeamLeagueContext(
        team_name="St. Louis Blues",
        team_id=3705,
        short_name="STL",
        league_slug="nhl",
        cells={"playoffs": 0.375, "championship": 0.01},
    )
    jackets = TeamLeagueContext(
        team_name="Columbus Blue Jackets",
        team_id=6182,
        short_name="CBJ",
        league_slug="nhl",
        cells={"playoffs": 0.42, "championship": 0.012},
    )
    return LeagueContext(
        league_slug="nhl",
        teams={
            normalize_name(blues.team_name): blues,
            normalize_name(jackets.team_name): jackets,
        },
    )


@pytest.fixture
def nhl_grid(monkeypatch):
    async def fake_league_context(league_slug, db):
        assert league_slug == "nhl"
        return _nhl_context()

    monkeypatch.setattr(league_context_service, "get_league_context", fake_league_context)


def _event(**ids):
    return SimpleNamespace(
        sport_id=4,
        home_team_name="St Louis Blues",
        away_team_name="Columbus Blue Jackets",
        **ids,
    )


def test_the_specimen_names_really_do_not_match():
    """The fixture is the defect: the two spellings fail both name arms."""
    event_norm = normalize_name("St Louis Blues")
    grid_norm = normalize_name("St. Louis Blues")
    assert event_norm != grid_norm
    assert event_norm not in grid_norm and grid_norm not in event_norm


@pytest.mark.asyncio
async def test_both_sides_are_present_when_the_names_differ_only_by_a_period(nhl_grid):
    result = await enrich_event_with_context(
        _event(home_team_id=3705, away_team_id=6182), _FakeDB()
    )

    assert result is not None
    assert result["home_team"]["team_id"] == 3705
    assert result["home_team"]["cells"] == {"playoffs": 0.375, "championship": 0.01}
    assert result["away_team"]["team_id"] == 6182


@pytest.mark.asyncio
async def test_without_ids_the_name_arm_still_misses_the_home_side(nhl_grid):
    """Control: the id is what finds the Blues, not a change to name matching.

    An event with no team ids falls back to names, and the period still
    defeats them — so the test above passes on the id arm alone.
    """
    result = await enrich_event_with_context(_event(), _FakeDB())

    assert result is not None
    assert "home_team" not in result
    assert result["away_team"]["team_id"] == 6182


@pytest.mark.asyncio
async def test_the_id_wins_over_a_name_that_points_at_another_club(nhl_grid):
    """When id and name disagree the id decides; the name is only a fallback."""
    event = SimpleNamespace(
        sport_id=4,
        home_team_name="Columbus Blue Jackets",
        away_team_name="Columbus Blue Jackets",
        home_team_id=3705,
        away_team_id=6182,
    )

    result = await enrich_event_with_context(event, _FakeDB())

    assert result["home_team"]["team_id"] == 3705
    assert result["away_team"]["team_id"] == 6182


@pytest.mark.asyncio
async def test_an_id_with_no_grid_row_falls_back_to_the_name(nhl_grid):
    result = await enrich_event_with_context(
        _event(home_team_id=999999, away_team_id=999998), _FakeDB()
    )

    assert "home_team" not in result
    assert result["away_team"]["team_id"] == 6182
