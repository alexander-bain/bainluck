"""Tests for women's college basketball auto-create orientation and `(W)` stripping."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tasks.prediction_market_matching import (
    _create_event_from_prediction_market,
    orient_auto_created_matchup,
    strip_womens_suffix,
)
from app.utils.prediction_market_matching import extract_matchup, match_teams_to_event
from app.utils.venue_competition import (
    POLYMARKET_EVENT_SLUG_KEY as SLUG_FIELD,
    venue_named_league,
    venue_named_sport_family,
)


def test_strip_womens_suffix_removes_trailing_marker_only():
    assert strip_womens_suffix("Notre Dame Fighting Irish (W)") == (
        "Notre Dame Fighting Irish",
        True,
    )
    assert strip_womens_suffix("North Carolina Tar Heels (w) ") == (
        "North Carolina Tar Heels",
        True,
    )
    assert strip_womens_suffix("Southern Jaguars") == ("Southern Jaguars", False)


def test_cwbb_polymarket_slug_resolves_to_basketball_wncaab():
    meta = {SLUG_FIELD: "cwbb-sou-nd-2026-11-18"}
    assert venue_named_sport_family(meta) == "basketball"
    assert venue_named_league("polymarket", "12345", meta) == "basketball_wncaab"


@pytest.mark.parametrize(
    "market_name,sport_key,has_w,meta,expected_home,expected_away",
    [
        # Real production specimens: Polymarket "<Away> vs. <Home> (W)"
        (
            "Southern Jaguars vs. Notre Dame Fighting Irish (W)",
            "basketball_wncaab",
            True,
            {SLUG_FIELD: "cwbb-sou-nd-2026-11-18"},
            "Notre Dame Fighting Irish",
            "Southern Jaguars",
        ),
        (
            "Texas Tech Red Raiders vs. North Carolina Tar Heels (W)",
            "basketball_other",
            True,
            None,
            "North Carolina Tar Heels",
            "Texas Tech Red Raiders",
        ),
        # Non-(W) Polymarket WBB market with cwbb slug
        (
            "George Washington Revolutionaries vs. UAB Blazers",
            "basketball_wncaab",
            False,
            {SLUG_FIELD: "cwbb-gwu-uab-2026-11-20"},
            "UAB Blazers",
            "George Washington Revolutionaries",
        ),
        # Kalshi KXNCAAWBGAME "<Away> at <Home>"
        (
            "Kansas Jayhawks at Minnesota Golden Gophers",
            "basketball_wncaab",
            False,
            None,
            "Minnesota Golden Gophers",
            "Kansas Jayhawks",
        ),
        (
            "Kansas Jayhawks at Minnesota Golden Gophers: Winner",
            "basketball_wncaab",
            False,
            None,
            "Minnesota Golden Gophers",
            "Kansas Jayhawks",
        ),
        # Explicit US "at" wording even outside WBB
        (
            "Duke Blue Devils at Virginia Cavaliers",
            "basketball_other",
            False,
            None,
            "Virginia Cavaliers",
            "Duke Blue Devils",
        ),
        # Non-WBB international / soccer control stays home-first (team_a, team_b)
        (
            "Arsenal vs. Chelsea",
            "soccer_epl",
            False,
            {SLUG_FIELD: "epl-ars-che-2026-11-22"},
            "Arsenal",
            "Chelsea",
        ),
        (
            "Real Madrid vs. Barcelona",
            "basketball_euroleague",
            False,
            None,
            "Real Madrid",
            "Barcelona",
        ),
    ],
)
def test_orient_auto_created_matchup(
    market_name, sport_key, has_w, meta, expected_home, expected_away
):
    matchup = extract_matchup(market_name)
    assert matchup is not None
    team_a, _ = strip_womens_suffix(matchup.team_a)
    team_b, _ = strip_womens_suffix(matchup.team_b)
    home, away = orient_auto_created_matchup(
        team_a,
        team_b,
        sport_key=sport_key,
        market_name=market_name,
        has_womens_suffix=has_w,
        market_metadata=meta,
    )
    assert (home, away) == (expected_home, expected_away)


def test_orient_prefers_existing_schedule_row_when_present():
    home, away = orient_auto_created_matchup(
        "Kansas Jayhawks",
        "Minnesota Golden Gophers",
        sport_key="basketball_wncaab",
        market_name="Kansas Jayhawks vs. Minnesota Golden Gophers (W)",
        has_womens_suffix=True,
        existing_home="Kansas Jayhawks",
        existing_away="Minnesota Golden Gophers",
    )
    assert (home, away) == ("Kansas Jayhawks", "Minnesota Golden Gophers")


def test_yes_is_home_maps_correctly_after_wbb_orientation():
    market_name = "Southern Jaguars vs. Notre Dame Fighting Irish (W)"
    matchup = extract_matchup(market_name)
    assert matchup is not None
    assert matchup.yes_team == "Southern Jaguars"
    team_a, had_a = strip_womens_suffix(matchup.team_a)
    team_b, had_b = strip_womens_suffix(matchup.team_b)
    home, away = orient_auto_created_matchup(
        team_a, team_b, sport_key="basketball_wncaab", has_womens_suffix=(had_a or had_b)
    )
    assert (home, away) == ("Notre Dame Fighting Irish", "Southern Jaguars")
    tm = match_teams_to_event(matchup, home, away)
    assert tm is not None
    # Yes = Southern Jaguars (away), so yes_is_home must be False.
    assert tm["yes_is_home"] is False


@pytest.mark.asyncio
async def test_create_event_from_prediction_market_orients_wbb_and_strips_w(monkeypatch):
    import app.services.event_registry as registry
    import app.tasks.prediction_market_matching as mod

    captured = {}

    async def fake_find_or_create(session, identity):
        captured["identity"] = identity
        return SimpleNamespace(id=99001), True

    monkeypatch.setattr(mod, "_polymarket_container_sibling_event_id", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "_polymarket_group_sibling_event_id", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "covered_league_for_matchup", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "venue_placed_league", AsyncMock(return_value="basketball_wncaab"))
    monkeypatch.setattr(mod, "_lookup_existing_wbb_orientation", AsyncMock(return_value=None))
    monkeypatch.setattr(registry, "find_or_create_event", fake_find_or_create)

    now = datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)
    market_name = "Texas Tech Red Raiders vs. North Carolina Tar Heels (W)"
    matchup = extract_matchup(market_name)
    assert matchup is not None
    market = SimpleNamespace(
        source="polymarket",
        external_id="poly-wbb-1",
        name=market_name,
        llm_sport_category="basketball",
        commence_time=datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc),
        market_metadata={SLUG_FIELD: "cwbb-ttu-unc-2026-11-19"},
    )

    out = await _create_event_from_prediction_market(object(), matchup, market, now)
    assert out is not None
    ident = captured["identity"]
    assert ident.sport_key == "basketball_wncaab"
    assert ident.home_team_name == "North Carolina Tar Heels"
    assert ident.away_team_name == "Texas Tech Red Raiders"
    assert "(W)" not in ident.home_team_name and "(W)" not in ident.away_team_name
    assert out["home_team"] == "North Carolina Tar Heels"
    assert out["away_team"] == "Texas Tech Red Raiders"
    assert out["yes_is_home"] is False
