"""#13142: Matcher prefers the sportsbook row, and tagged duplicates keep their
prices on the Sports list (``routes/feed.py``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.models import Event, Sport
from app.routes import feed as feed_route
from app.tasks import prediction_market_matching as pmm
from app.utils.personalization import PersonalizationContext
from app.utils.prediction_market_matching import MatchupInfo
from app.utils.proven_duplicates import FoldedCardNumbers

FROZEN_NOW = datetime(2025, 5, 15, 22, 0, tzinfo=timezone.utc)


def _event(
    event_id: int,
    *,
    home: str = "Arizona Wildcats",
    away: str = "New Mexico St Aggies",
    external_id: str | None = "odds_api_abc123",
    status: str = "scheduled",
    commence_time: datetime | None = None,
    sport_key: str = "basketball_wncaab",
    event_tags: list[str] | None = None,
    win_probability_sources: dict | None = None,
    opening_home_probability: float | None = None,
    opening_away_probability: float | None = None,
):
    return SimpleNamespace(
        id=event_id,
        home_team_name=home,
        away_team_name=away,
        external_id=external_id,
        status=status,
        commence_time=commence_time or (FROZEN_NOW + timedelta(hours=2)),
        sport=SimpleNamespace(key=sport_key, name="Women's College Basketball"),
        sport_id=42,
        event_tags=event_tags,
        win_probability_sources=win_probability_sources,
        opening_home_probability=opening_home_probability,
        opening_away_probability=opening_away_probability,
    )


def _market(name: str = "New Mexico State vs Arizona", source: str = "polymarket"):
    return SimpleNamespace(
        id=9001,
        source=source,
        external_id="pm-cond-13142",
        name=name,
        llm_sport_category="basketball",
        commence_time=FROZEN_NOW,
        market_metadata={},
    )


def test_matcher_prefers_sportsbook_row_over_higher_scoring_idless_twin():
    """For the same fixture (within 4h, both open), the sportsbook row wins
    over an auto-created id-less twin even when the id-less row is live and
    closer to ref."""
    idless_twin = _event(
        15348230,
        away="New Mexico State Aggies",
        external_id=None,
        status="live",
        commence_time=FROZEN_NOW,
    )
    sportsbook_row = _event(
        15351654,
        away="New Mexico St Aggies",
        external_id="odds_api_wbb_15351654",
        status="scheduled",
        commence_time=FROZEN_NOW + timedelta(hours=3),
    )
    matchup = MatchupInfo(
        team_a="New Mexico State",
        team_b="Arizona",
        yes_team="New Mexico State",
        format_type="vs",
    )
    result = pmm._score_candidates(
        [idless_twin, sportsbook_row],
        matchup,
        _market(),
        FROZEN_NOW,
    )
    assert result is not None
    assert result["event_id"] == 15351654


def test_matcher_allows_wide_gap_only_for_placeholder_midnight_start():
    """An id-less row stamped at UTC midnight (placeholder) pairs with a
    same-day sportsbook row up to 16h away; missing start times never pair."""
    midnight = datetime(2025, 5, 15, 0, 0, 0, tzinfo=timezone.utc)
    placeholder_idless = _event(
        15348231,
        away="New Mexico State Aggies",
        external_id=None,
        status="scheduled",
        commence_time=midnight,
    )
    same_day_books = _event(
        15351655,
        away="New Mexico St Aggies",
        external_id="odds_api_wbb_15351655",
        status="scheduled",
        commence_time=midnight + timedelta(hours=14),
    )
    assert pmm._same_fixture_twin(placeholder_idless, same_day_books)

    no_time = _event(15348232, external_id=None, status="scheduled", commence_time=midnight)
    no_time.commence_time = None
    assert not pmm._same_fixture_twin(no_time, same_day_books)
    assert not pmm._same_fixture_twin(placeholder_idless, no_time)


def test_matcher_ignores_legacy_pm_external_id_as_sportsbook():
    """Legacy `pm_*` placeholder ids are not sportsbook anchors."""
    pm_placeholder = _event(
        2001,
        external_id="pm_legacy_123",
        status="live",
        commence_time=FROZEN_NOW,
    )
    sportsbook_row = _event(
        2002,
        external_id="odds_api_real_2002",
        status="scheduled",
        commence_time=FROZEN_NOW + timedelta(hours=2),
    )
    matchup = MatchupInfo(
        team_a="New Mexico State",
        team_b="Arizona",
        yes_team="New Mexico State",
        format_type="vs",
    )
    result = pmm._score_candidates(
        [pm_placeholder, sportsbook_row],
        matchup,
        _market(),
        FROZEN_NOW,
    )
    assert result is not None
    assert result["event_id"] == 2002
    assert not pmm._is_sportsbook_row(pm_placeholder)
    assert pmm._is_sportsbook_row(sportsbook_row)


def test_matcher_never_attaches_to_proven_duplicate():
    """A row tagged `provenance:duplicate-of:<id>` is skipped even if it is
    the only candidate or would otherwise outscore the canonical row."""
    tagged_dup = _event(
        15348230,
        away="New Mexico State Aggies",
        external_id="odds_api_fake_higher",
        status="live",
        commence_time=FROZEN_NOW,
        event_tags=["provenance:duplicate-of:15351654"],
    )
    canonical = _event(
        15351654,
        away="New Mexico St Aggies",
        external_id=None,
        status="scheduled",
        commence_time=FROZEN_NOW + timedelta(hours=4),
    )
    matchup = MatchupInfo(
        team_a="New Mexico State",
        team_b="Arizona",
        yes_team="New Mexico State",
        format_type="vs",
    )

    assert pmm._score_candidates([tagged_dup], matchup, _market(), FROZEN_NOW) is None

    result = pmm._score_candidates(
        [tagged_dup, canonical],
        matchup,
        _market(),
        FROZEN_NOW,
    )
    assert result is not None
    assert result["event_id"] == 15351654


def test_matcher_does_not_override_todays_game_with_next_weeks_sportsbook_game():
    """Separate dates in a multi-game series (>24h apart) stay distinct so a
    sportsbook row 4 days later never hijacks today's id-less fixture."""
    todays_idless = _event(
        3001,
        external_id=None,
        status="live",
        commence_time=FROZEN_NOW,
    )
    next_week_books = _event(
        3002,
        external_id="odds_api_series_game_2",
        status="scheduled",
        commence_time=FROZEN_NOW + timedelta(days=4),
    )
    matchup = MatchupInfo(
        team_a="New Mexico State",
        team_b="Arizona",
        yes_team="New Mexico State",
        format_type="vs",
    )
    result = pmm._score_candidates(
        [todays_idless, next_week_books],
        matchup,
        _market(),
        FROZEN_NOW,
    )
    assert result is not None
    assert result["event_id"] == 3001


@pytest.mark.parametrize("gap_hours", [-24, -20, -18, 18, 20, 24])
@pytest.mark.parametrize("other_status", ["completed", "scheduled"])
@pytest.mark.parametrize("x_status", ["live", "scheduled"])
def test_back_to_back_series_games_are_never_treated_as_twins(
    gap_hours: int, other_status: str, x_status: str
):
    """Fable review on #13159: same two teams 18, 20, or 24 hours apart (in
    either order, whether the other game is finished or scheduled) are NEVER
    treated as twins of one game by `_same_fixture_twin`."""
    game_x = _event(
        4001,
        external_id=None,
        status=x_status,
        commence_time=FROZEN_NOW,
    )
    other_game = _event(
        4002,
        external_id="odds_api_other_game",
        status=other_status,
        commence_time=FROZEN_NOW + timedelta(hours=gap_hours),
    )
    assert not pmm._same_fixture_twin(game_x, other_game)


@pytest.mark.parametrize(
    ("x_status", "gap_hours", "other_status"),
    [
        ("live", 24, "scheduled"),
        ("live", -18, "completed"),
        ("live", -20, "completed"),
        ("scheduled", -24, "completed"),
        ("live", -24, "completed"),
        ("scheduled", 40, "scheduled"),
    ],
)
def test_matcher_keeps_todays_game_over_adjacent_day_sportsbook_game(
    x_status: str, gap_hours: int, other_status: str
):
    """Every cell where master picks tonight's game X (id-less) over an
    adjacent-day finished/scheduled sportsbook game still picks X."""
    game_x = _event(
        4101,
        external_id=None,
        status=x_status,
        commence_time=FROZEN_NOW,
    )
    other_game = _event(
        4102,
        external_id="odds_api_adjacent_day",
        status=other_status,
        commence_time=FROZEN_NOW + timedelta(hours=gap_hours),
    )
    matchup = MatchupInfo(
        team_a="New Mexico State",
        team_b="Arizona",
        yes_team="New Mexico State",
        format_type="vs",
    )
    result = pmm._score_candidates(
        [game_x, other_game],
        matchup,
        _market(),
        FROZEN_NOW,
    )
    assert result is not None
    assert result["event_id"] == 4101


@pytest.mark.asyncio
async def test_apply_proven_duplicate_folds_keeps_tagged_twin_prices_on_sports_list():
    """Tagged duplicate rows (`provenance:duplicate-of:<id>`) dropped in SQL
    still contribute their Polymarket/Kalshi prices and opening line to the
    canonical sportsbook row before Sports list scoring/formatting."""
    canonical = _event(
        15351654,
        win_probability_sources={"stat_model": {"home": 0.49, "away": 0.51}},
        opening_home_probability=None,
        opening_away_probability=None,
    )
    folded_result = {
        15351654: FoldedCardNumbers(
            win_probability_sources={
                "stat_model": {"home": 0.49, "away": 0.51},
                "polymarket": {"home": 0.62, "away": 0.38},
            },
            opening=(0.55, 0.45),
            absorbed_ids=(15348230,),
        )
    }

    with patch(
        "app.utils.proven_duplicates.folded_card_numbers_batch",
        new=AsyncMock(return_value=folded_result),
    ):
        absorbed = await feed_route._apply_proven_duplicate_folds(
            db=AsyncMock(),
            events=[canonical],
        )

    assert absorbed == {15351654: (15348230,)}
    assert "polymarket" in canonical.win_probability_sources
    assert canonical.win_probability_sources["polymarket"]["home"] == 0.62
    assert canonical.opening_home_probability == 0.55
    assert canonical.opening_away_probability == 0.45


@pytest.mark.asyncio
async def test_apply_proven_duplicate_folds_does_not_overwrite_canonical_opening():
    """Canonical's own sportsbook opening line stays untouched while the twin's
    prediction-market source merges into `win_probability_sources`."""
    canonical = _event(
        15351654,
        win_probability_sources={"betting": {"home": 0.52, "away": 0.48}},
        opening_home_probability=0.52,
        opening_away_probability=0.48,
    )
    folded_result = {
        15351654: FoldedCardNumbers(
            win_probability_sources={
                "betting": {"home": 0.52, "away": 0.48},
                "polymarket": {"home": 0.60, "away": 0.40},
            },
            opening=(0.52, 0.48),
            absorbed_ids=(15348230,),
        )
    }

    with patch(
        "app.utils.proven_duplicates.folded_card_numbers_batch",
        new=AsyncMock(return_value=folded_result),
    ):
        absorbed = await feed_route._apply_proven_duplicate_folds(
            db=AsyncMock(),
            events=[canonical],
        )

    assert absorbed == {15351654: (15348230,)}
    assert canonical.win_probability_sources["polymarket"]["home"] == 0.60
    assert canonical.opening_home_probability == 0.52
    assert canonical.opening_away_probability == 0.48


@pytest.mark.asyncio
async def test_score_events_sports_list_keeps_tagged_duplicate_prices_on_real_orm_event():
    """End-to-end Sports list guard (#13142): when SQL drops the tagged duplicate
    `15348230` (`provenance:duplicate-of:15351654`), `_score_events(sports_mode=True)`
    folds its Polymarket price onto canonical `15351654` via `set_committed_value`
    so the served card carries both sportsbook and Polymarket prices."""
    wbb = Sport(
        id=42,
        key="basketball_wncaab",
        name="Women's College Basketball",
        group="Basketball",
        active=True,
    )
    canonical = Event(
        id=15351654,
        sport_id=wbb.id,
        home_team_name="Arizona Wildcats",
        away_team_name="New Mexico St Aggies",
        commence_time=FROZEN_NOW - timedelta(hours=1),
        status="live",
        home_score=49,
        away_score=44,
        external_id="odds_api_wbb_15351654",
        win_probability_sources={"betting": 0.487},
        opening_home_probability=0.51,
        opening_away_probability=0.49,
    )
    canonical.sport = wbb

    db = AsyncMock()

    def _make_res(rows):
        r = MagicMock()
        r.scalars.return_value.all.return_value = rows
        r.all.return_value = []
        return r

    async def _execute(stmt, *a, **k):
        s = str(stmt).lower()
        if "win_prob_snapshots" in s:
            return _make_res([])
        if "events" in s:
            return _make_res([canonical])
        return _make_res([])

    db.execute = AsyncMock(side_effect=_execute)

    folded_result = {
        15351654: FoldedCardNumbers(
            win_probability_sources={"betting": 0.487, "polymarket": 0.68},
            opening=(0.51, 0.49),
            absorbed_ids=(15348230,),
        )
    }

    with (
        patch(
            "app.routes.feed._get_championship_probabilities",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "app.utils.proven_duplicates.folded_card_numbers_batch",
            new=AsyncMock(return_value=folded_result),
        ),
    ):
        items = await feed_route._score_events(
            db,
            FROZEN_NOW,
            None,
            PersonalizationContext(),
            sports_mode=True,
        )

    cards = [i for i in items if i["type"] == "event"]
    assert len(cards) == 1
    data = cards[0]["data"]
    assert data["id"] == 15351654
    assert data["win_probability_sources"]["betting"] == 0.487
    assert data["win_probability_sources"]["polymarket"] == 0.68
    # Blended probability moved up from 0.487 toward Polymarket's 0.68
    assert data["hero_probability"] > 0.50

