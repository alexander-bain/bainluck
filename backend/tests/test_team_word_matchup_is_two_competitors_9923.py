"""Two clubs that share only the word "Team" are two competitors — #9923.

## What a reader saw

Production, 2026-09-30 20:09Z, after #9823 went live on ``bainluck-heavy``:
BLAST Slam's BetBoom Team v Team Yandex (``KXDOTA2GAME-26OCT010900BBTY``) and
Cake Team v Rostik Team (``KXDOTA2GAME-26OCT030500CAKERT``) still had no match
page. Their receipts read ``no_candidate`` / ``auto_create: declined``, and they
were the only two open Kalshi esports game markets left in that state.

## Why

``_create_event_from_prediction_market``'s #175 degenerate guard asked
``names_match(team_a, team_b)``. Stage 3 of that predicate scores
``BetBoom Team`` / ``Team Yandex`` at 0.5 overlap on the one shared word, so
the guard read two clubs as one fighter, found no combat opponent, and minted
nothing. ``Team Spirit`` / ``Team Falcons`` reads the same way.

## The fix and its boundary

The guard now asks :func:`matchup_names_one_competitor`, which vetoes the
``names_match`` answer when ``shared_token_rivals`` says each side keeps a
distinctive word. ``names_match`` itself is untouched (#2046 owns it). A real
one-competitor matchup still hits the guard — the arms below pin both
directions.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.tasks.prediction_market_matching as task_module
import app.utils.prediction_market_matching as util_module
from app.tasks.prediction_market_matching import matchup_names_one_competitor
from app.utils.name_normalization import names_match
from app.utils.prediction_market_matching import extract_matchup_with_ticker_fallback

# Production specimens, verbatim (futures_markets.name / external_id, 2026-09-30).
BBTY = ("KXDOTA2GAME-26OCT010900BBTY", "BetBoom Team vs. Team Yandex")
CAKERT = ("KXDOTA2GAME-26OCT030500CAKERT", "Cake Team vs. Rostik Team")
LIQUIDAUR = ("KXDOTA2GAME-26OCT011200LIQUIDAUR", "Team Liquid vs. Aurora")


class TestThePredicate:
    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("BetBoom Team", "Team Yandex"),
            ("Cake Team", "Rostik Team"),
            ("Team Spirit", "Team Falcons"),
            ("Team Liquid", "Team Vitality"),
        ],
    )
    def test_two_clubs_sharing_only_team_are_two(self, team_a, team_b):
        # The premise, so this arm cannot pass because names_match changed.
        assert names_match(team_a, team_b) is True
        assert matchup_names_one_competitor(team_a, team_b) is False

    @pytest.mark.parametrize(
        "team_a,team_b",
        [
            ("Saint-Denis", "Saint-Denis"),
            ("Jones", "Jon Jones"),
            ("Team Liquid", "Team Liquid"),
            ("Boston Celtics", "Celtics"),
        ],
    )
    def test_one_competitor_is_still_one(self, team_a, team_b):
        assert matchup_names_one_competitor(team_a, team_b) is True

    def test_unrelated_names_are_two(self):
        assert matchup_names_one_competitor("Team Liquid", "Aurora") is False


class _PastTheGuard(Exception):
    """Raised by the first gate after the degenerate guard."""


def _market(external_id, name):
    return SimpleNamespace(
        id=1,
        source="kalshi",
        external_id=external_id,
        name=name,
        group_id=None,
        group_type=None,
        market_metadata={},
        llm_sport_category=None,
        commence_time=datetime.now(timezone.utc) + timedelta(hours=20),
        event_id=None,
    )


async def _run_create(monkeypatch, external_id, name):
    """Drive the real create path up to the gate after the guard.

    Returns (reached_past_guard, combat_resolver_calls).
    """
    calls = []

    async def _no_opponent(session, ext, team_a, sport_key):
        calls.append(team_a)
        return None

    def _stop(team_a, team_b):
        raise _PastTheGuard((team_a, team_b))

    monkeypatch.setattr(task_module, "_resolve_combat_opponent", _no_opponent)
    # Imported inside the function body at call time, so the module attribute is
    # the one the path reads.
    monkeypatch.setattr(util_module, "bracket_refusal_reason", _stop)

    matchup = extract_matchup_with_ticker_fallback(name, external_id=external_id)
    try:
        result = await task_module._create_event_from_prediction_market(
            None, matchup, _market(external_id, name), datetime.now(timezone.utc),
        )
    except _PastTheGuard:
        return True, calls
    assert result is None
    return False, calls


class TestTheCreatePath:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("specimen", [BBTY, CAKERT], ids=["BBTY", "CAKERT"])
    async def test_the_team_word_specimens_reach_past_the_guard(
        self, monkeypatch, specimen,
    ):
        reached, calls = await _run_create(monkeypatch, *specimen)
        assert reached, "the #175 guard refused two clubs as one competitor"
        assert calls == []

    @pytest.mark.asyncio
    async def test_the_linked_sibling_still_reaches_past_the_guard(self, monkeypatch):
        reached, calls = await _run_create(monkeypatch, *LIQUIDAUR)
        assert reached and calls == []

    @pytest.mark.asyncio
    async def test_a_one_fighter_matchup_still_stops_at_the_guard(self, monkeypatch):
        reached, calls = await _run_create(
            monkeypatch, "KXUFCFIGHT-26OCT03SAIN", "Saint-Denis vs Saint-Denis",
        )
        assert not reached
        assert calls, "the guard must ask for the combat opponent"

    def test_the_guard_calls_the_predicate(self):
        import inspect

        src = inspect.getsource(task_module._create_event_from_prediction_market)
        assert "not team_b or matchup_names_one_competitor(team_a, team_b)" in src
