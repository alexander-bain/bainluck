"""Tests for the register-backed grid reader (Queue 295, Item 1).

Two things must hold at the same time:

* With a register, the grid resolves cells by pinned identity ONLY — no name
  matching, no "closest market wins", and an identity that has gone away
  produces an honest missing cell rather than a substituted one.
* Without a register, nothing changes. The cutover is per-league and reversible
  by deleting a file, so every league that has no register keeps its exact
  current behaviour.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.playoffs import _build_register_column_data
from app.utils.grid_register import GridRegister
from app.utils.playoff_grid import (
    enforce_monotonicity,
    normalize_column_sums,
    sort_teams_by_championship,
)

NOW = "2026-08-01T00:00:00+00:00"


def _entry(**over) -> dict:
    base = {
        "stage": "championship",
        "entity_key": "oklahoma city thunder",
        "entity_name": "Oklahoma City Thunder",
        "source": "kalshi",
        "status": "live",
        "market_id": 101,
        "outcome_id": 5001,
        "external_id": "KXNBA-27",
        "evidence": {"kind": "ticker_exact", "observed_at": NOW},
    }
    base.update(over)
    return base


def _register(entries) -> GridRegister:
    return GridRegister({
        "schema_version": "grid-register/v1",
        "league": "nba",
        "season": "2026-27",
        "version": 3,
        "generated_at": NOW,
        "entries": entries,
    })


def _market(mid=101, source="kalshi"):
    return SimpleNamespace(
        id=mid, source=source, name="Pro Basketball Champion",
        external_id="KXNBA-27", volume_24h=1000,
    )


def _outcome(oid=5001, mid=101, prob=0.31, name="Oklahoma City"):
    return SimpleNamespace(
        id=oid, market_id=mid, name=name, current_probability=prob,
        current_yes_bid=0.30, current_yes_ask=0.32, last_updated=None, is_winner=None,
    )


def _session(markets, outcomes):
    """A session whose two SELECTs return outcomes then markets, in call order."""
    session = MagicMock()
    outcome_result = MagicMock()
    outcome_result.scalars.return_value.all.return_value = outcomes
    market_result = MagicMock()
    market_result.scalars.return_value.unique.return_value.all.return_value = markets
    session.execute = AsyncMock(side_effect=[outcome_result, market_result])
    return session


# ---------------------------------------------------------------------------
# Live cells
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_live_entry_resolves_to_its_pinned_identity():
    register = _register([_entry()])
    session = _session([_market()], [_outcome()])

    column_data, entities, stats = await _build_register_column_data(session, register)

    assert list(column_data) == ["championship"]
    market, outcome = column_data["championship"][0]
    assert (market.id, outcome.id) == (101, 5001)
    assert stats == {"registered": 1, "live": 1, "settled": 0, "missing": 0, "unresolved": 0}


@pytest.mark.asyncio
async def test_entity_key_comes_from_the_register_not_the_outcome_text():
    """The outcome says "OKC"; the register says which team that is."""
    register = _register([_entry()])
    session = _session([_market()], [_outcome(name="OKC")])

    _, entities, _ = await _build_register_column_data(session, register)

    assert entities[5001] == ("oklahoma city thunder", "Oklahoma City Thunder")


@pytest.mark.asyncio
async def test_unrelated_outcomes_on_the_same_market_are_ignored():
    """Only the pinned outcome enters the grid, even from a registered market."""
    register = _register([_entry()])
    session = _session(
        [_market()],
        [_outcome(), _outcome(oid=5002, name="Denver Nuggets", prob=0.2)],
    )

    column_data, entities, stats = await _build_register_column_data(session, register)

    assert len(column_data["championship"]) == 1
    assert 5002 not in entities
    assert stats["live"] == 1


@pytest.mark.asyncio
async def test_multiple_stages_and_sources_are_kept_distinct():
    register = _register([
        _entry(),
        _entry(stage="conference", market_id=102, outcome_id=5002),
        _entry(source="odds_api", market_id=103, outcome_id=5003),
    ])
    session = _session(
        [_market(), _market(102), _market(103, source="odds_api")],
        [_outcome(), _outcome(5002, 102, 0.55), _outcome(5003, 103, 0.29)],
    )

    column_data, _, stats = await _build_register_column_data(session, register)

    assert len(column_data["championship"]) == 2  # two sources, one cell
    assert len(column_data["conference"]) == 1
    assert stats["live"] == 3


# ---------------------------------------------------------------------------
# Honest absence — the whole point
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_entry_produces_no_cell_and_is_counted():
    register = _register([_entry(status="missing", market_id=None, outcome_id=None)])
    session = _session([], [])

    column_data, entities, stats = await _build_register_column_data(session, register)

    assert column_data == {}
    assert entities == {}
    assert stats["missing"] == 1 and stats["live"] == 0


@pytest.mark.asyncio
async def test_settled_entry_is_not_blended():
    """A settled cell carries a result, not a probability, so it never enters
    the blend — it is attached after the math."""
    register = _register([_entry(status="settled", terminal_result="won")])
    session = _session([_market()], [_outcome()])

    column_data, _, stats = await _build_register_column_data(session, register)

    assert column_data == {}
    assert stats["settled"] == 1 and stats["live"] == 0


@pytest.mark.asyncio
async def test_vanished_identity_is_unresolved_never_substituted():
    """The DB no longer has the pinned outcome. Nothing else may take its place."""
    register = _register([_entry()])
    session = _session([_market()], [_outcome(oid=9999)])  # different outcome id

    column_data, entities, stats = await _build_register_column_data(session, register)

    assert column_data == {}
    assert entities == {}
    assert stats["unresolved"] == 1


@pytest.mark.asyncio
async def test_absent_market_is_unresolved():
    register = _register([_entry()])
    session = _session([], [_outcome()])

    _, _, stats = await _build_register_column_data(session, register)
    assert stats["unresolved"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prob", [None, 0.0, 1.0, -0.1, 1.5])
async def test_out_of_range_probabilities_are_unresolved_not_clamped(prob):
    """A degenerate probability must not become a rendered number."""
    register = _register([_entry()])
    session = _session([_market()], [_outcome(prob=prob)])

    column_data, _, stats = await _build_register_column_data(session, register)

    assert column_data == {}
    assert stats["unresolved"] == 1


@pytest.mark.asyncio
async def test_empty_register_touches_no_market():
    register = _register([])
    session = MagicMock()
    session.execute = AsyncMock()

    column_data, entities, stats = await _build_register_column_data(session, register)

    assert (column_data, entities) == ({}, {})
    assert stats["registered"] == 0
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Downstream math must tolerate probability-free cells
# ---------------------------------------------------------------------------

def _team(name, **cells):
    return {"name": name, "short_name": name, "team_id": None, "cells": cells}


def _live(p):
    return {"merged_probability": p, "sources": [{"source": "kalshi", "probability": p}],
            "trend_24h": None, "state": "live"}


def _settled(state):
    return {"merged_probability": None, "sources": [], "trend_24h": None, "state": state}


COLUMNS = [
    SimpleNamespace(key="conference", label="Conference", order=1, sequential=True),
    SimpleNamespace(key="championship", label="Champion", order=2, sequential=True),
]


def test_normalize_skips_probability_free_cells():
    """A settled cell must not be counted in the column sum it never joined."""
    teams = [
        _team("A", championship=_live(0.30)),
        _team("B", championship=_live(0.20)),
        _team("C", championship=_settled("eliminated")),
    ]
    normalize_column_sums(teams, COLUMNS, "nba")

    # 0.50 undershoots 1.0, so the two live cells scale up by 2x; the settled
    # cell is untouched and still carries no probability.
    assert teams[0]["cells"]["championship"]["merged_probability"] == 0.6
    assert teams[1]["cells"]["championship"]["merged_probability"] == 0.4
    assert teams[2]["cells"]["championship"]["merged_probability"] is None


def test_monotonicity_skips_probability_free_cells():
    teams = [
        _team("A", conference=_settled("won"), championship=_live(0.40)),
        _team("B", conference=_live(0.30), championship=_settled("eliminated")),
        _team("C", conference=_live(0.20), championship=_live(0.50)),
    ]
    fixed = enforce_monotonicity(teams, COLUMNS)

    # Only C is comparable, and it violates (0.50 > 0.20).
    assert fixed == 1
    assert teams[2]["cells"]["championship"]["merged_probability"] == 0.20
    assert teams[0]["cells"]["championship"]["merged_probability"] == 0.40
    assert teams[1]["cells"]["championship"]["merged_probability"] is None


def test_sort_places_a_confirmed_champion_first():
    teams = [
        _team("Also-ran", championship=_live(0.40)),
        _team("Champion", championship=_settled("won")),
        _team("Eliminated", championship=_settled("eliminated")),
    ]
    ordered = sort_teams_by_championship(teams, "championship", 10)

    assert [t["name"] for t in ordered] == ["Champion", "Also-ran", "Eliminated"]


def test_sort_unchanged_for_all_live_grids():
    teams = [_team("A", championship=_live(0.1)), _team("B", championship=_live(0.9))]
    assert [t["name"] for t in sort_teams_by_championship(teams, "championship", 10)] == ["B", "A"]


def test_sort_handles_a_team_with_no_championship_cell():
    teams = [_team("A", championship=_live(0.1)), _team("B")]
    assert [t["name"] for t in sort_teams_by_championship(teams, "championship", 10)] == ["A", "B"]
