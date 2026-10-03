"""A live row whose reported start is still ahead, with no play, goes back to scheduled. #10300

PILLAR: TRUTH.  SHIP: a game with a verified reported start still in the future
and no play evidence stays out of the live list until play begins.

The specimen, from the Flow Sentinel and Shopper's public read at 08:08Z
2026-10-03: Ässät v Lukko (15320706, ``icehockey_liiga``) was in
``GET /api/events?status=live`` with a 14:00Z start, 6.5h ahead, served as
``scheduled`` with no score and no ``completed_at``. The row went live at a
start that had passed, and a later start-time write moved the start forward
without un-starting it. Which writer moved it is not established and nothing
here depends on it.

This file drives the real ``_transition_event_statuses_impl`` against a fake
session that hands the new arm the rows each case chooses. It proves the
decision on every clause. It cannot prove currentness — that the decision is
taken on the row the write lands on — because a fake has no concurrent
writer; ``tests/integration/test_future_unplayed_live_row_returns_to_scheduled_10300_pg.py``
proves that on Postgres with two sessions.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

NOW = datetime(2026, 10, 3, 7, 30, tzinfo=timezone.utc)
SPECIMEN_START = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


class _Row:
    def __init__(
        self,
        id=15320706,
        *,
        status="live",
        commence_time=SPECIMEN_START,
        commence_time_source="odds_api",
        home_score=None,
        away_score=None,
        period=None,
        game_clock=None,
        completed_at=None,
    ):
        self.id = id
        self.status = status
        self.commence_time = commence_time
        self.commence_time_source = commence_time_source
        self.home_score = home_score
        self.away_score = away_score
        self.period = period
        self.game_clock = game_clock
        self.completed_at = completed_at
        self.win_probability_sources = {"kalshi": {"home": 0.55}}
        self.espn_id = None
        self.statpal_fixture_id = None
        self.home_team_name = "Ässät"
        self.away_team_name = "Lukko"
        self.sport = type("S", (), {"key": "icehockey_liiga"})()


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return self

    @property
    def rowcount(self):
        return 0


class _Session:
    """Every read answers empty except the #10300 arm's locked read.

    Keyed on the statement's LOCK, not on its position in the pass: a fake
    that answers by order silently hands one arm's rows to another when a
    read is added above it."""

    def __init__(self, future_live):
        self._future_live = future_live
        self.locked_reads = []

    async def execute(self, stmt, params=None):
        lock = getattr(stmt, "_for_update_arg", None)
        if lock is not None and "events" in str(stmt) and lock.skip_locked:
            self.locked_reads.append(stmt)
            return _Result(self._future_live)
        return _Result([])

    async def commit(self):
        pass


async def _run(rows, now=NOW):
    session = _Session(rows)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        stats = await mod._transition_event_statuses_impl()
    return stats, session


class TestTheSpecimenGoesBack:
    @pytest.mark.asyncio
    async def test_the_specimen_shape_is_unstarted(self):
        """THE SHIP. RED before #10300: no arm reads a live row whose start
        is ahead, so it stays in the live list until the start arrives."""
        row = _Row()
        stats, _ = await _run([row])
        assert row.status == "scheduled"
        assert stats["unstarted_future_live"] == 1

    @pytest.mark.asyncio
    async def test_only_the_status_moves(self):
        """No start, probability, provenance or completion is written."""
        row = _Row()
        before = dict(vars(row))
        await _run([row])
        after = dict(vars(row))
        assert after.pop("status") == "scheduled"
        before.pop("status")
        assert after == before

    @pytest.mark.asyncio
    async def test_a_sibling_with_play_survives_in_the_same_pass(self):
        """Per-row decision (gotcha #42): the refused row beside the eligible
        one is left exactly as it was."""
        eligible = _Row(1)
        played = _Row(2, home_score=1, away_score=0)
        stats, _ = await _run([eligible, played])
        assert (eligible.status, played.status) == ("scheduled", "live")
        assert stats["unstarted_future_live"] == 1


class TestPlayEvidenceRefuses:
    @pytest.mark.parametrize(
        "evidence",
        [
            {"home_score": 0},
            {"away_score": 0},
            {"home_score": 0, "away_score": 0},
            {"home_score": 2, "away_score": 1},
            {"period": "1st"},
            {"game_clock": "12:31"},
            {"completed_at": NOW - timedelta(minutes=5)},
        ],
        ids=["home-0", "away-0", "nil-nil", "scored", "period", "clock", "completed"],
    )
    @pytest.mark.asyncio
    async def test_any_report_on_the_game_keeps_it_live(self, evidence):
        """0 is evidence here, unlike `play_evidence`: the registry's own
        un-start refuses a reported 0-0, and this arm asks that predicate."""
        row = _Row(**evidence)
        stats, _ = await _run([row])
        assert row.status == "live"
        assert stats["unstarted_future_live"] == 0


class TestTheStartMustBeReportedAndAhead:
    @pytest.mark.asyncio
    async def test_a_derived_start_is_refused(self):
        row = _Row(commence_time_source="kalshi_ticker")
        stats, _ = await _run([row])
        assert row.status == "live"
        assert stats["held_future_live_unreported_start"] == 1

    @pytest.mark.asyncio
    async def test_an_unknown_provenance_is_refused(self):
        """Tighter than `commence_time_is_a_reported_start`, which admits
        NULL for the promotion path."""
        row = _Row(commence_time_source=None)
        stats, _ = await _run([row])
        assert row.status == "live"
        assert stats["held_future_live_unreported_start"] == 1

    @pytest.mark.parametrize("source", ["kalshi", "kalshi_occurrence"])
    @pytest.mark.asyncio
    async def test_a_kalshi_expected_expiration_hour_is_refused(self, source):
        """That hour sits ~3h after kick-off (#5905): "still ahead" on it can
        be a game in progress with no score to say so."""
        row = _Row(commence_time_source=source)
        stats, _ = await _run([row])
        assert row.status == "live"
        assert stats["held_future_live_unreported_start"] == 1

    @pytest.mark.parametrize(
        "source", ["odds_api", "espn", "statpal", "kalshi_ticker_time"]
    )
    @pytest.mark.asyncio
    async def test_reported_sources_are_admitted(self, source):
        """The kill control for the two refusals above: a rule that refused
        every source passes them and fails here."""
        row = _Row(commence_time_source=source)
        await _run([row])
        assert row.status == "scheduled"

    @pytest.mark.asyncio
    async def test_a_start_exactly_now_is_refused(self):
        row = _Row(commence_time=NOW)
        await _run([row])
        assert row.status == "live"

    @pytest.mark.asyncio
    async def test_a_past_start_is_refused(self):
        row = _Row(commence_time=NOW - timedelta(minutes=1))
        await _run([row])
        assert row.status == "live"

    @pytest.mark.asyncio
    async def test_one_second_ahead_is_admitted(self):
        row = _Row(commence_time=NOW + timedelta(seconds=1))
        await _run([row])
        assert row.status == "scheduled"


class TestOnlyLive:
    @pytest.mark.parametrize(
        "status", ["suspended", "scheduled", "completed", "closed", "postponed"]
    )
    @pytest.mark.asyncio
    async def test_other_statuses_are_untouched(self, status):
        """The fake hands the arm a row its WHERE would not have selected;
        the loop still refuses it, so a widened read cannot widen the write."""
        row = _Row(status=status)
        stats, _ = await _run([row])
        assert row.status == status
        assert stats["unstarted_future_live"] == 0


class TestTheReadIsLocked:
    @pytest.mark.asyncio
    async def test_the_read_locks_skips_locked_and_refreshes(self):
        """The shape the Postgres file's race cases depend on. Asserted here
        too so a change to it fails in the fast band, not only in CI's
        Postgres step."""
        _, session = await _run([])
        (stmt,) = session.locked_reads
        assert stmt._for_update_arg.skip_locked is True
        assert stmt.get_execution_options().get("populate_existing") is True
