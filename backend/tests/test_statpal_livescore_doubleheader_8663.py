"""#8663 — the 30-second StatPal livescore writer picks THIS game's board row
when a doubleheader puts two rows under one team pair.

Production, 2026-09-25: Cubs @ Red Sox game 1 (15318549, anchor `366778`) was
live at 3-0 while the board also listed game 2 (`366748`, 'Not Started', 0-0).
The writer's lookup was keyed on the team pair alone and kept the later row, so
every minute it wrote 0-0 onto game 1. ESPN put 1-0 back 30 s later, and the
hero printed the stale 0-0 half the time.

The fixture file is the real board of that minute, trimmed to the two rows,
parsed by the real `_parse_fixtures`. The writer runs for real over a real
session (the `test_statpal_live_anchor_entrypoint_3094` harness).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.test_statpal_live_anchor_entrypoint_3094 import (
    MLB_KEY,
    _Fixture,
    _run_livescores,
)

BOARD = Path(__file__).parent / "fixtures" / "statpal_mlb_livescores_doubleheader_8663.json"
G1_ANCHOR = "366778"
G2_ANCHOR = "366748"


def _real_board_rows():
    from app.services.statpal_api import StatPalAPIService

    svc = StatPalAPIService.__new__(StatPalAPIService)
    rows = StatPalAPIService._parse_fixtures(svc, json.loads(BOARD.read_text()), "mlb")
    by_anchor = {r.odds_id: r for r in rows}
    assert set(by_anchor) == {G1_ANCHOR, G2_ANCHOR}, "fixture drifted"
    # The ORDER is the defect's trigger: game 2 after game 1.
    assert [r.odds_id for r in rows] == [G1_ANCHOR, G2_ANCHOR]
    return rows, by_anchor


def _shift_to_now(rows):
    """Re-date the real rows so game 1 started an hour ago, keeping the 4h25m gap
    (the harness dates the event `now - 1h`, and the premature guard reads it)."""
    now = datetime.now(timezone.utc)
    offset = (now - timedelta(hours=1)) - rows[0].start_time
    for r in rows:
        r.start_time = r.start_time + offset
    return rows


@pytest.mark.asyncio
async def test_real_board_game_two_no_longer_overwrites_live_game_one(monkeypatch):
    rows, by_anchor = _real_board_rows()
    _shift_to_now(rows)
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=rows,
        events=[("Boston Red Sox", "Chicago Cubs")],
        preset_anchor=G1_ANCHOR,
    )
    assert (event.home_score, event.away_score) == (0, 3), result
    assert event.period == "Top 2nd", result
    assert result["livescore_sibling_refused"] == 0


@pytest.mark.asyncio
async def test_strawman_last_row_wins_is_what_the_board_order_would_write(monkeypatch):
    """Control: the same board with game 1 ALONE writes 0-3, and with game 2 alone
    writes 0-0. That proves the two rows really disagree, so the test above is
    choosing one, not passing because the scores happen to match."""
    rows, by_anchor = _real_board_rows()
    _shift_to_now(rows)
    _, (alone_g2,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[by_anchor[G2_ANCHOR]],
        events=[("Boston Red Sox", "Chicago Cubs")],
        preset_anchor=G1_ANCHOR,
    )
    assert (alone_g2.home_score, alone_g2.away_score) == (0, 0)


@pytest.mark.asyncio
async def test_anchor_wins_over_board_order_both_ways(monkeypatch):
    rows, by_anchor = _real_board_rows()
    _shift_to_now(rows)
    _, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=list(reversed(rows)),
        events=[("Boston Red Sox", "Chicago Cubs")],
        preset_anchor=G1_ANCHOR,
    )
    assert (event.home_score, event.away_score) == (0, 3)


@pytest.mark.asyncio
async def test_an_anchor_matching_no_row_refuses_and_counts(monkeypatch):
    """Both rows carry ids and neither is ours: both are other games."""
    rows, _ = _real_board_rows()
    _shift_to_now(rows)
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=rows,
        events=[("Boston Red Sox", "Chicago Cubs")],
        preset_anchor="999999",
    )
    assert (event.home_score, event.away_score) == (None, None)
    assert result["livescore_sibling_refused"] == 1


@pytest.mark.asyncio
async def test_no_anchor_yet_takes_the_nearest_start_and_anchors_it(monkeypatch):
    rows, _ = _real_board_rows()
    _shift_to_now(rows)
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=rows,
        events=[("Boston Red Sox", "Chicago Cubs")],
    )
    assert (event.home_score, event.away_score) == (0, 3), result
    assert event.statpal_fixture_id == G1_ANCHOR


@pytest.mark.asyncio
async def test_id_less_rows_equally_near_refuse(monkeypatch):
    now = datetime.now(timezone.utc)
    # Same listed start: equally near whatever the event's clock reads.
    a = _Fixture(now - timedelta(hours=1), "Red Sox", "Cubs", home_score=0, away_score=3)
    b = _Fixture(now - timedelta(hours=1), "Red Sox", "Cubs", home_score=0, away_score=0)
    result, (event,) = await _run_livescores(
        monkeypatch, sport_key=MLB_KEY, fixtures=[a, b], events=[("Red Sox", "Cubs")],
    )
    assert (event.home_score, event.away_score) == (None, None)
    assert result["livescore_sibling_refused"] == 1


@pytest.mark.asyncio
async def test_id_less_row_without_a_start_refuses(monkeypatch):
    now = datetime.now(timezone.utc)
    a = _Fixture(now - timedelta(hours=1), "Red Sox", "Cubs", home_score=0, away_score=3)
    b = _Fixture(None, "Red Sox", "Cubs", home_score=0, away_score=0)
    result, (event,) = await _run_livescores(
        monkeypatch, sport_key=MLB_KEY, fixtures=[a, b], events=[("Red Sox", "Cubs")],
    )
    assert (event.home_score, event.away_score) == (None, None)
    assert result["livescore_sibling_refused"] == 1


@pytest.mark.asyncio
async def test_single_row_is_unchanged_and_counter_reads_zero(monkeypatch):
    """One row per pair (every non-doubleheader game): still written. The row's
    id differs from the event's anchor and it is written anyway, exactly as
    before this change, because there is nothing to choose between."""
    now = datetime.now(timezone.utc)
    a = _Fixture(now - timedelta(hours=1), "Red Sox", "Cubs", odds_id="111111")
    result, (event,) = await _run_livescores(
        monkeypatch,
        sport_key=MLB_KEY,
        fixtures=[a],
        events=[("Red Sox", "Cubs")],
        preset_anchor="222222",
    )
    assert (event.home_score, event.away_score) == (3, 1)
    assert result["livescore_sibling_refused"] == 0
