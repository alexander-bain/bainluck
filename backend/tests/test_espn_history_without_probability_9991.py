"""#9991 — a live ESPN reading with no win probability still records score + period.

Production, BOS@NYY 15321907 at 03:11Z: the hero said Top 9th, the age chip
"25m ago" and the readout "Bottom 7th · 9–2 · 7:46 PM". ESPN's scoreboard had
dropped `situation.lastPlay.probability` (the game was decided), and both
`espn_snapshots` writers appended only inside their probability branch, so the
history stopped at 02:46Z. The page dates the score from the newest history row.

The REAL loop runs here (the #9020 rig: `_process_live_sport`, the real matcher,
field writer, ESPN writer and stat model, against SQLite), and the rows are read
back as `/history` serves them. Every arm that writes has a twin that refuses
(gotcha #43).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tests.test_priorless_stat_model_defers_to_market_8522 import (
    _portable_probability_writer,  # noqa: F401 - shared recording/SQLite write seam
)
from tests.test_refused_clock_stays_off_the_chart_9020 import (
    END_Q3,
    REAL_Q4,
    ROLLOVER,
    _board_reading,
    _one_live_pass,
    _served_espn_history,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TestTheDecidedGameKeepsItsHistory:
    @pytest.mark.asyncio
    async def test_a_reading_without_probability_records_score_and_period(self):
        """The specimen: ESPN sends the score and the position, no probability."""
        row, espn_rows, wp_rows, stats = await _one_live_pass(
            _board_reading(*REAL_Q4, home_score=28, away_score=10, prob=None)
        )
        served = _served_espn_history(espn_rows)
        assert len(served) == 4, served  # 3 seeded + this pass
        newest = served[-1]
        assert (newest["period"], newest["game_clock"]) == REAL_Q4
        assert (newest["home_score"], newest["away_score"]) == (28, 10)
        assert newest["home_probability"] is None
        assert newest["away_probability"] is None
        assert stats.get("espn_history_without_probability") == 1, stats
        # The row is current too, so the history and the hero now agree.
        assert (row.period, row.home_score) == (REAL_Q4[0], 28)

    @pytest.mark.asyncio
    async def test_no_probability_is_invented_anywhere(self):
        """Absent means absent: no ESPN blend source, no ESPN chart series."""
        row, _espn_rows, wp_rows, _stats = await _one_live_pass(
            _board_reading(*REAL_Q4, prob=None)
        )
        assert [r for r in wp_rows if r.source == "espn"] == []
        assert "espn" not in (row.win_probability_sources or {})
        assert row.espn_win_prob_home is None

    @pytest.mark.asyncio
    async def test_twin_a_reading_with_probability_is_unchanged(self):
        row, espn_rows, wp_rows, stats = await _one_live_pass(
            _board_reading(*REAL_Q4, prob=0.91)
        )
        newest = _served_espn_history(espn_rows)[-1]
        assert newest["home_probability"] == pytest.approx(0.91)
        assert (newest["period"], newest["game_clock"]) == REAL_Q4
        assert stats.get("espn_history_without_probability", 0) == 0, stats
        assert [r for r in wp_rows if r.source == "espn"]

    @pytest.mark.asyncio
    async def test_a_refused_position_stays_withheld_without_probability_too(self):
        """#9020's refusal binds this row exactly as it binds the probability one."""
        row, espn_rows, _wp_rows, stats = await _one_live_pass(
            _board_reading(*ROLLOVER, away_score=17, prob=None)
        )
        assert stats["live_clock_outran_wall_refused"] == 1, stats
        assert (row.period, row.game_clock) == END_Q3
        newest = _served_espn_history(espn_rows)[-1]
        assert (newest["period"], newest["game_clock"]) == (None, None)
        assert (newest["home_score"], newest["away_score"]) == (21, 17)


class TestTheRowBuilderRefusesWhatTheProbabilityArmRefuses:
    """Unit arms of `espn_history_row_without_probability`, one refusal each."""

    @staticmethod
    def _event(status="live", started_ago=3 * 3600):
        return SimpleNamespace(
            id=7, status=status, commence_time=_now() - timedelta(seconds=started_ago),
        )

    @staticmethod
    def _reading(status="in", **kw):
        base = dict(
            status=status, status_detail="Top 9th", clock="0:00",
            home_score=9, away_score=2, home_win_probability=None,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def _build(self, event, ee):
        from app.utils.espn_helpers import espn_history_row_without_probability

        return espn_history_row_without_probability(event, ee, _now())

    def test_live_reading_on_a_started_live_row_is_recorded(self):
        snap = self._build(self._event(), self._reading())
        assert snap is not None
        assert (snap.event_id, snap.home_score, snap.away_score) == (7, 9, 2)
        assert snap.period == "Top 9th"
        assert snap.home_win_probability is None and snap.away_win_probability is None

    @pytest.mark.parametrize("espn_status", ["pre", "post", "final"])
    def test_only_live_readings(self, espn_status):
        assert self._build(self._event(), self._reading(status=espn_status)) is None

    @pytest.mark.parametrize("row_status", ["completed", "closed"])
    def test_never_on_a_row_we_resolved_finished(self, row_status):
        """#922: post-final re-process cycles must not grow a stale tail."""
        assert self._build(self._event(status=row_status), self._reading()) is None

    def test_never_before_the_start(self):
        """#1207: ESPN can report 'in' before first pitch."""
        assert self._build(self._event(started_ago=-3600), self._reading()) is None

    def test_a_refused_position_is_withheld_but_the_score_lands(self):
        snap = self._build(self._event(), self._reading(position_outran_wall=True))
        assert (snap.period, snap.game_clock) == (None, None)
        assert (snap.home_score, snap.away_score) == (9, 2)


def test_the_create_path_writes_the_same_row_when_probability_is_absent():
    """`create_events_from_unmatched_espn` had the identical gate (~2575)."""
    from app.utils import espn_helpers

    src = inspect.getsource(espn_helpers.create_events_from_unmatched_espn)
    branch = src.split("elif ee.home_win_probability is None:", 1)
    assert len(branch) == 2, "the create path lost its no-probability branch"
    assert "espn_history_row_without_probability(event, ee, _now)" in branch[1].split(
        "if ee.status in", 1
    )[0]
