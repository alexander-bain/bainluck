"""#8691 — a clinched rung on the Championship Path carries its verdict.

THE SPECIMEN, read on production 2026-09-26 01:08Z (Giants @ Dodgers, MLB):

    GET /api/playoffs/mlb
      Los Angeles Dodgers: make_playoffs {merged_probability: null, state: "won"}
                           division      {merged_probability: null, state: "won"}
                           pennant       {merged_probability: 0.415, state: "live"}
                           championship  {merged_probability: 0.302, state: "live"}

    GET /api/events/15318410/team-progression   (the SAME minute)
      away_team.stages: make_playoffs null · division null · pennant 0.415 ·
                        championship 0.302 — and no `state` on any of them

The grid knew the 97-62 Dodgers had clinched both; the event payload kept only
the float, so a clinched rung and an unpriced rung were the same `null`. The
iPhone drew that null as `<1%` (native's half, fixed client-side). This file is
the server half: the grid cell's `state` rides `TeamLeagueContext` →
`enrich_event_with_context` → each `/team-progression` stage as `"state"`.

Pair (notice 46): consumer = native `stages[].state` through the #7557 parser
(won/clinched → ✓ clinched), web twin = ux AdvancementPath `resolved`.
"""

import json
from types import SimpleNamespace

import pytest

from app.services.league_context import (
    LeagueContext,
    TeamLeagueContext,
    _compute_league_context,
    enrich_event_with_context,
)

EVENT_ID = 15318410


def _cell(prob, state):
    return {
        "merged_probability": prob,
        "sources": [{"source": "kalshi", "probability": prob}] if prob is not None else [],
        "trend_24h": None,
        "state": state,
    }


#: The production rows, verbatim in the fields this path reads. The Giants are
#: included because every one of their cells is `eliminated` — the row the
#: context has always skipped (`if not cells`), and still does (control).
PRODUCTION_GRID = {
    "teams": [
        {
            "name": "Los Angeles Dodgers",
            "team_id": 19,
            "short_name": "LAD",
            "record": "97-62",
            "cells": {
                "make_playoffs": _cell(None, "won"),
                "division": _cell(None, "won"),
                "pennant": _cell(0.415, "live"),
                "championship": _cell(0.302, "live"),
            },
        },
        {
            "name": "San Francisco Giants",
            "team_id": 26,
            "short_name": "SF",
            "cells": {
                "make_playoffs": _cell(None, "eliminated"),
                "division": _cell(None, "eliminated"),
                "pennant": _cell(None, "eliminated"),
                "championship": _cell(None, "eliminated"),
            },
        },
        {
            "name": "San Diego Padres",
            "team_id": 25,
            "short_name": "SD",
            "cells": {
                "make_playoffs": _cell(None, "won"),
                "division": _cell(None, "eliminated"),
                "pennant": _cell(0.0953, "live"),
                "championship": _cell(0.053, "live"),
            },
        },
    ]
}


async def _fake_grid(**_kwargs):
    return json.loads(json.dumps(PRODUCTION_GRID))


def _no_redis():
    raise ConnectionError("no redis in this rig")


@pytest.fixture
def grid(monkeypatch):
    monkeypatch.setattr("app.routes.playoffs.get_playoff_grid_cached", _fake_grid)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client", _no_redis)


class TestTheCarrierKeepsTheState:
    @pytest.mark.asyncio
    async def test_a_clinched_cell_reaches_the_context_as_won(self, grid):
        ctx = await _compute_league_context("mlb", db=object())
        lad = ctx.teams["los angeles dodgers"]

        assert lad.states == {
            "make_playoffs": "won",
            "division": "won",
            "pennant": "live",
            "championship": "live",
        }
        # The float map is unchanged: a graded cell still has no number.
        assert lad.cells == {"pennant": 0.415, "championship": 0.302}

    @pytest.mark.asyncio
    async def test_the_all_eliminated_row_is_still_skipped(self, grid):
        """Control: carrying the state does not widen which rows exist."""
        ctx = await _compute_league_context("mlb", db=object())
        assert "san francisco giants" not in ctx.teams
        assert ctx.teams["san diego padres"].states["division"] == "eliminated"

    @pytest.mark.asyncio
    async def test_the_team_sports_stages_shape_carries_it_too(self, monkeypatch):
        async def stages_grid(**_kwargs):
            return {
                "teams": [
                    {
                        "name": "Los Angeles Dodgers",
                        "stages": [
                            {"key": "division", "probability": None, "state": "won"},
                            {"key": "pennant", "probability": 0.415, "state": "live"},
                        ],
                    }
                ]
            }

        monkeypatch.setattr("app.routes.playoffs.get_playoff_grid_cached", stages_grid)
        ctx = await _compute_league_context("mlb", db=object())
        assert ctx.teams["los angeles dodgers"].states == {
            "division": "won",
            "pennant": "live",
        }

    def test_a_cache_entry_written_before_states_existed_still_decodes(self):
        legacy = json.dumps(
            {
                "league_slug": "mlb",
                "teams": {
                    "los angeles dodgers": {
                        "team_name": "Los Angeles Dodgers",
                        "cells": {"pennant": 0.415},
                    }
                },
            }
        )
        ctx = LeagueContext.from_json(legacy)
        assert ctx.teams["los angeles dodgers"].states == {}

    def test_states_round_trip_through_the_cache(self):
        ctx = LeagueContext(
            league_slug="mlb",
            teams={
                "los angeles dodgers": TeamLeagueContext(
                    team_name="Los Angeles Dodgers", states={"division": "won"}
                )
            },
        )
        restored = LeagueContext.from_json(ctx.to_json())
        assert restored.teams["los angeles dodgers"].states == {"division": "won"}


class _FakeDB:
    """Answers the two reads on this path: the Event row and its Sport key."""

    def __init__(self, event):
        self._event = event

    async def execute(self, _stmt):
        return SimpleNamespace(
            scalar_one_or_none=lambda: self._event,
            scalar=lambda: "baseball_mlb",
        )


def _event():
    return SimpleNamespace(
        id=EVENT_ID,
        sport_id=3,
        sport=SimpleNamespace(key="baseball_mlb"),
        home_team_name="San Francisco Giants",
        away_team_name="Los Angeles Dodgers",
    )


class TestTheRouteServesTheState:
    """The line the reader actually hit, driven end to end."""

    @pytest.fixture
    def served(self, grid, monkeypatch):
        import app.routes.events as events_mod

        async def fake_resolve(_db, event, requested_id):
            return SimpleNamespace(
                event=event,
                event_id=requested_id,
                resolved_elsewhere=False,
                cache_ids=[requested_id],
            )

        monkeypatch.setattr(events_mod, "resolve_served_event", fake_resolve)

        async def call():
            return await events_mod.get_team_progression(
                EVENT_ID, db=_FakeDB(_event())
            )

        return call

    @pytest.mark.asyncio
    async def test_the_dodgers_clinched_rungs_serve_state_won(self, served):
        payload = await served()
        stages = {s["key"]: s for s in payload["away_team"]["stages"]}

        assert stages["make_playoffs"]["state"] == "won"
        assert stages["division"]["state"] == "won"
        # Settled means settled: the verdict, never a number beside it.
        assert stages["make_playoffs"]["probability"] is None
        assert stages["division"]["probability"] is None

    @pytest.mark.asyncio
    async def test_a_trading_rung_serves_live_and_its_number(self, served):
        payload = await served()
        stages = {s["key"]: s for s in payload["away_team"]["stages"]}

        assert stages["pennant"] == {
            "key": "pennant",
            "label": stages["pennant"]["label"],
            "probability": 0.415,
            "trend_24h": None,
            "sources": [{"source": "kalshi", "probability": 0.415}],
            "state": "live",
        }

    @pytest.mark.asyncio
    async def test_every_stage_carries_the_key(self, served):
        payload = await served()
        assert all("state" in s for s in payload["away_team"]["stages"])
        # Unchanged: the all-eliminated home row is still not served.
        assert payload["home_team"] is None

    @pytest.mark.asyncio
    async def test_a_cell_the_grid_did_not_carry_serves_state_none(
        self, served, monkeypatch
    ):
        """`None` — "the number decides" to the #7557 parser — never a guess."""

        async def partial_grid(**_kwargs):
            g = json.loads(json.dumps(PRODUCTION_GRID))
            del g["teams"][0]["cells"]["division"]
            return g

        monkeypatch.setattr("app.routes.playoffs.get_playoff_grid_cached", partial_grid)
        payload = await served()
        stages = {s["key"]: s for s in payload["away_team"]["stages"]}
        assert stages["division"]["state"] is None
        assert stages["make_playoffs"]["state"] == "won"


@pytest.mark.asyncio
async def test_the_event_detail_league_context_carries_states(grid):
    """`enrich_event_with_context` is also the detail route's `league_context`."""
    enriched = await enrich_event_with_context(_event(), db=_FakeDB(_event()))
    assert enriched["away_team"]["states"]["division"] == "won"
    assert "home_team" not in enriched
