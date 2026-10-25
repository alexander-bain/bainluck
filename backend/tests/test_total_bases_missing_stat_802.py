"""#802: a missing box-score count never grades a total-bases prop.

``_resolve_kalshi_total_bases_from_boxscore`` read ``player_stats.get("hits") or 0``
and ``player_stats.get("home runs") or 0``, so an ABSENT count became an OBSERVED
zero. The ESPN parser drops a dashed or non-finite stat instead of storing it
(``ESPNService._parse_stat_value``), so absence is a real shape. With ``{"hits": 1}``
the pass wrote "4+" as a certain LOSS, though the missing home-run count could
be 1 (one home run = 4 total bases). With ``{"home runs": 1}`` it wrote "4+" as a
LOSS for a player who hit a home run.

The verdict a pass may store is the one EVERY consistent completion of the
missing counts agrees on (home runs are a subset of hits). A count that is
present but not a count (negative, fractional, bool, string, non-finite, or
more home runs than hits) refuses the whole row: the box is not trusted to
bound anything. A refused row stays ``is_winner IS NULL`` and is counted.

Every test drives the real async resolver against a fake session that records
the UPDATEs, with a final (non-live) box and an ASCII name, so the only thing
varying is the stat line.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

import app.tasks.backfill_winners as bw


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _outcome(outcome_id, name, players):
    row = MagicMock()
    row.outcome_id = outcome_id
    row.outcome_name = name
    row.box_score_data = {"source": "espn", "players": players}
    return row


def _run(monkeypatch, outcomes):
    writes = {"winner_ids": None, "loser_ids": None, "commits": 0}
    session = AsyncMock()

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "SELECT id FROM events WHERE box_score_data IS NOT NULL" in sql:
            return _Result([])
        if "FROM futures_outcomes" in sql:
            return _Result(outcomes)
        if "is_winner = true" in sql:
            assert "box_score_bound" in sql
            writes["winner_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(writes["winner_ids"] or []))
        if "is_winner = false" in sql:
            assert "box_score_bound" in sql
            writes["loser_ids"] = (params or {}).get("ids")
            return MagicMock(rowcount=len(writes["loser_ids"] or []))
        raise AssertionError(f"unexpected SQL: {sql}")

    async def _commit():
        writes["commits"] += 1

    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock(side_effect=_commit)

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    return writes


async def _resolve_one(monkeypatch, line, threshold):
    outcome = _outcome(802001, f"Manny Machado: {threshold}+", {"Manny Machado": line})
    writes = _run(monkeypatch, [outcome])
    stats = await bw._resolve_kalshi_total_bases_from_boxscore()
    assert stats["errors"] == [], stats
    return writes, stats


def _verdict_written(writes):
    if writes["winner_ids"] == [802001]:
        return True
    if writes["loser_ids"] == [802001]:
        return False
    assert writes["winner_ids"] is None and writes["loser_ids"] is None, writes
    return None


# ---------------------------------------------------------------------------
# Absent counts: refused unless every completion agrees.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, threshold",
    [
        # Root's specimen: TB is anywhere in [1, 4]; 4+ is undecided.
        ({"hits": 1}, 4),
        ({"hits": 1.0}, 4),
        ({"hits": 1, "home runs": None}, 4),
        # No hits count: TB has no ceiling, and 0 HR gives no floor.
        ({"home runs": 0}, 4),
        ({"home runs": 0.0}, 1),
        # No batting line at all.
        ({}, 1),
        ({"hits": None, "home runs": None}, 1),
        ({"pitching strikeouts": 6.0, "innings pitched": 5.0}, 1),
    ],
)
async def test_an_absent_count_that_leaves_the_outcome_open_writes_nothing(
    monkeypatch, line, threshold
):
    writes, stats = await _resolve_one(monkeypatch, line, threshold)
    assert _verdict_written(writes) is None
    assert stats["resolved"] == 0
    assert stats["incomplete_stats"] == 1
    assert stats["indeterminate"] == 0 and stats["invalid_stats"] == 0
    # The pass still ends cleanly; a refused row is not an error.
    assert writes["commits"] == 1


async def test_a_home_run_with_no_hits_count_is_a_winner_not_a_loss(monkeypatch):
    """The old pass read hits as 0 and wrote this 4+ as a certain LOSS.
    One home run is four total bases, whatever the missing hits count is."""
    writes, stats = await _resolve_one(monkeypatch, {"home runs": 1}, 4)
    assert _verdict_written(writes) is True
    assert stats["resolved"] == 1 and stats["incomplete_stats"] == 0


async def test_a_home_run_with_no_hits_count_never_decides_above_its_floor(monkeypatch):
    # TB >= 4 is all one HR proves; 5+ stays open (no ceiling without hits).
    writes, stats = await _resolve_one(monkeypatch, {"home runs": 1}, 5)
    assert _verdict_written(writes) is None
    assert stats["incomplete_stats"] == 1


@pytest.mark.parametrize(
    "line, threshold, expected",
    [
        # HR is a subset of hits: 0 hits means 0 HR, so TB = 0.
        ({"hits": 0}, 1, False),
        ({"hits": 0.0}, 3, False),
        # 1 hit, HR unknown: TB <= 4, so 5+ is out of reach.
        ({"hits": 1}, 5, False),
        # 2 hits, HR unknown: TB >= 2.
        ({"hits": 2}, 2, True),
    ],
)
async def test_an_absent_home_run_count_still_decides_what_every_completion_agrees_on(
    monkeypatch, line, threshold, expected
):
    writes, stats = await _resolve_one(monkeypatch, line, threshold)
    assert _verdict_written(writes) is expected
    assert stats["resolved"] == 1 and stats["incomplete_stats"] == 0


# ---------------------------------------------------------------------------
# Invalid counts: the row is refused even where the other count would decide.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, threshold",
    [
        ({"hits": 0, "home runs": -1}, 1),  # old pass: TB_max -1 < 1 -> LOSS
        ({"hits": 0, "home runs": 0.5}, 1),  # old pass: TB_max 0.5 < 1 -> LOSS
        ({"hits": True, "home runs": 0}, 4),  # old pass: True == 1 -> LOSS
        ({"hits": 1, "home runs": 2}, 4),  # more HR than hits; old pass: WIN
        ({"hits": -1}, 1),
        ({"hits": "1", "home runs": 0}, 4),  # old pass: TypeError, whole pass lost
        ({"hits": float("nan"), "home runs": 0}, 1),
        ({"hits": float("inf"), "home runs": 0}, 1),
        ({"hits": 0, "home runs": [0]}, 1),
    ],
)
async def test_a_count_outside_the_count_domain_refuses_the_row(
    monkeypatch, line, threshold
):
    writes, stats = await _resolve_one(monkeypatch, line, threshold)
    assert _verdict_written(writes) is None
    assert stats["resolved"] == 0
    assert stats["invalid_stats"] == 1
    assert stats["incomplete_stats"] == 0 and stats["indeterminate"] == 0


# ---------------------------------------------------------------------------
# Controls: complete, valid lines keep their exact pre-#802 verdicts.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line, threshold, expected",
    [
        ({"hits": 0, "home runs": 0}, 1, False),  # an OBSERVED zero still grades
        ({"hits": 0.0, "home runs": 0.0}, 4, False),
        ({"hits": 1, "home runs": 1}, 4, True),
        ({"hits": 1.0, "home runs": 1.0}, 4, True),
        ({"hits": 1, "home runs": 0}, 4, False),
        ({"hits": 2, "home runs": 1}, 5, True),
        ({"hits": 2, "home runs": 2}, 9, False),
    ],
)
async def test_a_complete_line_grades_exactly_as_before(
    monkeypatch, line, threshold, expected
):
    writes, stats = await _resolve_one(monkeypatch, line, threshold)
    assert _verdict_written(writes) is expected
    assert stats["resolved"] == 1
    assert stats["incomplete_stats"] == 0 and stats["invalid_stats"] == 0


async def test_a_complete_line_between_the_bounds_stays_indeterminate(monkeypatch):
    writes, stats = await _resolve_one(monkeypatch, {"hits": 2, "home runs": 0}, 4)
    assert _verdict_written(writes) is None
    assert stats["indeterminate"] == 1
    assert stats["incomplete_stats"] == 0 and stats["invalid_stats"] == 0


async def test_refused_rows_do_not_cost_their_healthy_siblings(monkeypatch):
    players = {
        "Manny Machado": {"hits": 1},  # refused: incomplete
        "Fernando Tatis": {"hits": 1, "home runs": 2},  # refused: invalid
        "Jackson Merrill": {"hits": 1, "home runs": 1},  # winner
        "Xander Bogaerts": {"hits": 0, "home runs": 0},  # loser
    }
    outcomes = [
        _outcome(1, "Manny Machado: 4+", players),
        _outcome(2, "Fernando Tatis: 4+", players),
        _outcome(3, "Jackson Merrill: 4+", players),
        _outcome(4, "Xander Bogaerts: 1+", players),
    ]
    writes = _run(monkeypatch, outcomes)
    stats = await bw._resolve_kalshi_total_bases_from_boxscore()
    assert writes["winner_ids"] == [3]
    assert writes["loser_ids"] == [4]
    assert stats["resolved"] == 2
    assert stats["incomplete_stats"] == 1 and stats["invalid_stats"] == 1
    assert stats["errors"] == []


# ---------------------------------------------------------------------------
# The pure bound, with absent counts.
# ---------------------------------------------------------------------------


class TestTotalBasesVerdictWithAbsentCounts:
    def _v(self, hits, hr, threshold):
        return bw._total_bases_verdict(hits, hr, threshold)

    def test_both_absent_never_decides(self):
        for threshold in (0, 1, 4):
            assert self._v(None, None, threshold) is None

    def test_absent_home_runs_bounds_tb_between_hits_and_four_times_hits(self):
        assert self._v(1, None, 1) is True
        assert self._v(1, None, 2) is None
        assert self._v(1, None, 4) is None
        assert self._v(1, None, 5) is False
        assert self._v(0, None, 1) is False

    def test_absent_hits_gives_a_floor_of_four_per_home_run_and_no_ceiling(self):
        assert self._v(None, 1, 4) is True
        assert self._v(None, 2, 8) is True
        assert self._v(None, 1, 5) is None
        assert self._v(None, 0, 1) is None

    def test_more_home_runs_than_hits_never_decides(self):
        assert self._v(1, 2, 4) is None
        assert self._v(0, 1, 1) is None
