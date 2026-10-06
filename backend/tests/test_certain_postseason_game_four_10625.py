"""#10625 — Dodgers–Braves NLDS Game 4 (Wed 10/7) reads "Playoff game" the day before.

SHIP: tomorrow's Dodgers–Braves card on /sports reads "Playoff game", not a
regular-season records chip ("LAD 100-62 · ATL 94-68"). (Pillar: MATCHING.)

On 2026-10-06 17:14Z StatPal's row for the game (15324864, 10-07 22:00Z) had no
ESPN id and ``llm_importance='unknown'``. ESPN had listed it since Game 2 ended,
as 401908016, "NLDS - Game 4", series tied 1-1, best of 5. The #9216 pass reads
that board an hour at a time and refused the game ``if_necessary``: the rule
knew only "Game k at most the wins needed" (3) and "the next game" (3). At 1-1,
Game 3 makes the series 2-1 whoever wins, so Game 4 is always played — the
declining arm was the certainty rule, not the board, the attach or the dyno.

  Part A  the general arithmetic, and an exhaustive oracle: for every series
          length, standings and later game number, the rule says "certain"
          exactly when every way the games before it can go still plays it.
  Part B  the board's own shape: ESPN's 401908016 parses to a certain game, and
          its sibling "NLDS - Game 4 If Necessary" at 2-0 is still refused.
  Part C  the registry: the claim attaches to StatPal's 15324864 and never to
          Game 3's row a day earlier, bound to its own ESPN game.
  Part D  the pass claims the game and marks its row playoff (#9602).
"""

from __future__ import annotations

import copy
import itertools
from datetime import datetime, timedelta, timezone

import pytest

from app.services.espn_api import ESPNAPIService
from app.services.event_registry import (
    EventClaim,
    EventIdentity,
    _sport_id_cache,
    find_or_create_event,
)
from app.tasks import espn_certain_postseason as task
from app.utils.postseason_series import PlayoffSeries, certain_to_be_played
from app.models import Event
from tests.test_certain_postseason_games_9216 import PHI_ATL_G2, _board_event, _wire
from tests.test_event_registry import _FakeRegistrySession

G3_ESPN, G4_ESPN = "401908015", "401908016"
G3_ROW, G4_ROW = 15324742, 15324864
G3_TIME = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc)
G4_TIME = datetime(2026, 10, 7, 22, 0, tzinfo=timezone.utc)


def _row(id, commence_time, *, espn_id=None, source):
    return Event(
        id=id,
        sport_id=1,
        home_team_name="Atlanta Braves",
        away_team_name="Los Angeles Dodgers",
        commence_time=commence_time,
        commence_time_source=source,
        status="scheduled",
        espn_id=espn_id,
    )


def _series(game, total, wins=(0, 0), completed=False):
    return PlayoffSeries(game_number=game, total_games=total, wins=wins, completed=completed)


# ════════════════════════════════════════════════════════════════════════════
# Part A — the arithmetic
# ════════════════════════════════════════════════════════════════════════════


class TestLaterGames:
    @pytest.mark.parametrize(
        ("series", "certain", "reason"),
        [
            # The specimen: LDS Game 4 at 1-1. Game 3 cannot end it.
            (_series(4, 5, (1, 1)), True, "leader_cannot_clinch_before_it"),
            # ...at 2-0 Game 3 may end it (MIL-SD on the same board).
            (_series(4, 5, (2, 0)), False, "if_necessary"),
            # ...and Game 5 at 1-1 is two games out: 1 + 2 reaches 3.
            (_series(5, 5, (1, 1)), False, "if_necessary"),
            # Best of 7: Game 5 at 1-1 and 2-1, Game 6 at 2-2 are all certain.
            (_series(5, 7, (1, 1)), True, "leader_cannot_clinch_before_it"),
            (_series(5, 7, (2, 1)), True, "leader_cannot_clinch_before_it"),
            (_series(6, 7, (2, 2)), True, "leader_cannot_clinch_before_it"),
            (_series(6, 7, (2, 1)), False, "if_necessary"),
            # ...but Game 5 at 2-0 and Game 6 at 3-1 are not.
            (_series(5, 7, (2, 0)), False, "if_necessary"),
            (_series(6, 7, (3, 1)), False, "if_necessary"),
            (_series(7, 7, (2, 2)), False, "if_necessary"),
            # A number the standings already count as played is not vouched for.
            (_series(4, 7, (3, 2)), True, "within_wins_needed"),
            (_series(5, 7, (3, 2)), False, "if_necessary"),
        ],
    )
    def test_the_arithmetic(self, series, certain, reason):
        assert certain_to_be_played(series) == (certain, reason)

    @staticmethod
    def _always_played(total: int, wins: tuple[int, int], game: int) -> bool:
        """Brute force: is game ``game`` played however the games before it go?"""
        needed = total // 2 + 1
        before = game - 1 - sum(wins)
        for outcome in itertools.product((0, 1), repeat=before):
            a, b = wins
            for winner in outcome:
                if a >= needed or b >= needed:
                    break
                a, b = (a + 1, b) if winner == 0 else (a, b + 1)
            if a >= needed or b >= needed:
                return False
        return True

    @pytest.mark.parametrize("total", [3, 5, 7])
    def test_the_rule_agrees_with_every_continuation(self, total):
        """For every open standings and every game not yet played, the rule
        answers what enumerating the games before it answers — so no certain
        game is refused (this defect) and no uncertain one is created (#9216's
        hazard: a row for a game that never happens)."""
        needed = total // 2 + 1
        checked = 0
        for a, b in itertools.product(range(needed), repeat=2):
            if a + b >= total:
                continue
            for game in range(a + b + 1, total + 1):
                certain, _reason = certain_to_be_played(_series(game, total, (a, b)))
                assert certain is self._always_played(total, (a, b), game), (total, a, b, game)
                checked += 1
        assert checked > 0


# ════════════════════════════════════════════════════════════════════════════
# Part B — the board's own shape
# ════════════════════════════════════════════════════════════════════════════


def _lad_atl_g4(headline="NLDS - Game 4", wins=(1, 1)):
    """ESPN baseball/mlb/scoreboard?dates=20261007, event 401908016, read
    2026-10-06 17:2xZ (summary "Series tied 1-1"), trimmed to the parser's keys."""
    p = copy.deepcopy(PHI_ATL_G2)
    p.update(
        id=G4_ESPN,
        name="Los Angeles Dodgers at Atlanta Braves",
        shortName="LAD @ ATL",
        date="2026-10-07T22:00Z",
    )
    comp = p["competitions"][0]
    comp["notes"] = [{"type": "event", "headline": headline}]
    comp["series"] = {
        "type": "playoff", "title": "Playoff Series", "summary": "Series tied 1-1",
        "completed": False, "totalCompetitions": 5,
        "competitors": [{"id": "15", "wins": wins[0]}, {"id": "19", "wins": wins[1]}],
    }
    comp["competitors"] = [
        {"id": "15", "homeAway": "home", "team": {"id": "15", "displayName": "Atlanta Braves", "name": "Braves", "abbreviation": "ATL"}},
        {"id": "19", "homeAway": "away", "team": {"id": "19", "displayName": "Los Angeles Dodgers", "name": "Dodgers", "abbreviation": "LAD"}},
    ]
    return p


class TestTheBoard:
    def test_the_specimen_is_certain(self):
        ee = ESPNAPIService()._parse_event(_lad_atl_g4())
        assert ee.espn_id == G4_ESPN and ee.season_type == 3
        assert ee.playoff_series == PlayoffSeries(4, 5, (1, 1), False)
        assert certain_to_be_played(ee.playoff_series) == (True, "leader_cannot_clinch_before_it")
        assert task.select_certain_games([ee], stats := {}) == [ee]
        assert stats == {}

    def test_the_if_necessary_sibling_at_two_nil_is_still_refused(self):
        ee = ESPNAPIService()._parse_event(_lad_atl_g4("NLDS - Game 4 If Necessary", (2, 0)))
        stats: dict = {}
        assert task.select_certain_games([ee], stats) == []
        assert stats == {"refused_if_necessary": 1}


# ════════════════════════════════════════════════════════════════════════════
# Part C — the registry lands it on StatPal's row
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_claim_attaches_to_statpals_row_not_game_three():
    g3 = _row(G3_ROW, G3_TIME, espn_id=G3_ESPN, source="espn")
    g4 = _row(G4_ROW, G4_TIME, source="statpal")
    session = _FakeRegistrySession(structured_candidates=[g3, g4])
    _sport_id_cache.clear()

    event, created = await find_or_create_event(
        session,
        EventIdentity(
            sport_key="baseball_mlb",
            home_team_name="Atlanta Braves",
            away_team_name="Los Angeles Dodgers",
            commence_time=G4_TIME,
            claim=EventClaim("espn", G4_ESPN, schedule_derived=True),
            commence_time_source="espn",
            status="scheduled",
            same_game_only=True,
        ),
    )

    assert event is g4 and created is False
    assert g4.espn_id == G4_ESPN
    assert session.added == []
    assert g3.espn_id == G3_ESPN and g3.commence_time == G3_TIME


# ════════════════════════════════════════════════════════════════════════════
# Part D — the pass
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_pass_claims_game_four_and_marks_it_playoff(monkeypatch):
    # The pass's NOW is 9/28 05:30Z; the boards are keyed to its lookahead.
    boards = {
        ("baseball_mlb", "20260929"): [
            _board_event(G4_ESPN, 4, total=5, wins=(1, 1), date=G4_TIME,
                         home="Atlanta Braves", away="Los Angeles Dodgers"),
            _board_event("401908005", 4, total=5, wins=(2, 0), date=G4_TIME + timedelta(hours=4),
                         home="San Diego Padres", away="Milwaukee Brewers"),
        ],
    }
    session, _reads, claims = _wire(monkeypatch, boards, unmarked={G4_ESPN})

    stats = await task._run_create_certain_postseason_games(apply=True)

    assert [c.claim.source_id for c in claims] == [G4_ESPN]
    assert claims[0].same_game_only is True
    assert stats["refused_if_necessary"] == 1
    assert session.marks == [("baseball_mlb", [G4_ESPN], True)]
    assert stats["marked_playoff"] == 1
    assert stats["status"] == "complete"
