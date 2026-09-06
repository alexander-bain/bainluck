"""#3403: an in-play tennis match dated two weeks into the future.

Kalshi stamps a match market's ``commence_time`` with its ``close_time``
(gotcha #14). While the market is OPEN that close_time is a ~14-day settlement
backstop, not the match start — Kalshi's own API gives
``KXWTAMATCH-26SEP07OSARYB`` (a Sep-7 US Open match) a close_time of
2026-09-21T15:00Z. Measured against production on 2026-09-06: **408 of 408**
open Kalshi tennis markets carrying a ticker date were dated +14 or +15 days,
across every series (KXATPMATCH, KXWTAMATCH, the CHALLENGER/ITF/DOUBLES/
EXACTMATCH variants) with no exceptions.

The reason it survived so long is that it heals itself: on settlement Kalshi
collapses close_time to the real settlement instant, so a resolved row reads
back correct and only matches a user could actually watch were ever wrong.

Golf and hockey already have close_time fix-ups in ``tasks/kalshi.py``; tennis
had none. These tests cover the decision the fix-up makes per market — which is
where the bug lives — plus the driver loop's row selection and its wiring into
``poll_kalshi``.
"""

import ast
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks import kalshi as kalshi_task
from app.tasks.kalshi import _fix_tennis_commence_times, _tennis_commence_target


UTC = timezone.utc


class TestTennisCommenceTarget:
    """The per-market decision: ticker date, linked kick-off, or leave alone."""

    def test_open_match_is_redated_off_the_ticker(self):
        """The production specimen: Osaka vs Rybakina, Sep 7, stamped Sep 21."""
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", None
        ) == datetime(2026, 9, 7, tzinfo=UTC)

    @pytest.mark.parametrize(
        "ticker,expected_day",
        [
            ("KXATPMATCH-26SEP06PAUALC", (2026, 9, 6)),
            ("KXWTAMATCH-26SEP05JOVEAL", (2026, 9, 5)),
            ("KXATPCHALLENGERMATCH-26SEP06NAKLIU", (2026, 9, 6)),
            ("KXWTACHALLENGERMATCH-26SEP06ZAATSY", (2026, 9, 6)),
            ("KXITFMATCH-26SEP05JONDEL", (2026, 9, 5)),
            ("KXITFWMATCH-26SEP06MORGAL", (2026, 9, 6)),
            ("KXATPDOUBLES-26SEP04KRAPUTFARWAL", (2026, 9, 4)),
            ("KXWTADOUBLES-26SEP03MUHSTOPARSHY", (2026, 9, 3)),
            ("KXITFDOUBLES-26SEP04CESMENAGUDEL", (2026, 9, 4)),
            ("KXATPEXACTMATCH-26SEP06SHETSI", (2026, 9, 6)),
        ],
    )
    def test_every_dated_series_resolves_to_its_ticker_day(self, ticker, expected_day):
        """Real open tickers sampled from production, one per affected series."""
        got = _tennis_commence_target(ticker, None)
        assert got is not None, f"{ticker} carries a date and must be re-dated"
        assert (got.year, got.month, got.day) == expected_day

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXWTA-26USO",           # tournament outright
            "KXATPWTA-26USO",        # cross-tour outright
            "KXWTASERENA-26",        # season-long outright
            "KXATPADVANCE-26USOSEMI",  # round-advance outright
            "KXWMARMADROUND-27QF",   # no date in the ticker at all
            "KXATPGRANDSLAM-26",
            "KXATPFINALSQUAL-26NIT",
            "KXATPNATSTAGE-26QF",
            "KXATPRETIRE-27DJO",
        ],
    )
    def test_outrights_are_left_alone(self, ticker):
        """A futures market's close_time IS its horizon — re-dating it to a
        match day would be a second bug, not a fix."""
        assert _tennis_commence_target(ticker, None) is None

    def test_a_dateless_outright_is_not_backtracked_into_a_date(self):
        """`KXATP1RANK-26DEC31` is "who is ATP #1 on Dec 31". It has no team
        tail, so the shared ticker parser backtracks its 1-2 digit day and
        reads "26DEC3" + rest "1" — re-dating a year-end outright to Dec 3.
        Caught in the production dry-run; the series allowlist is what stops
        it, and a shape-only check would not have."""
        from app.utils.prediction_market_matching import (
            extract_game_date_from_ticker,
        )

        # The shared parser really does produce the wrong date ...
        assert extract_game_date_from_ticker("KXATP1RANK-26DEC31") == datetime(
            2026, 12, 3, tzinfo=UTC
        )
        # ... and the fix-up must still refuse to act on it.
        assert _tennis_commence_target("KXATP1RANK-26DEC31", None) is None

    def test_a_match_ticker_needs_a_full_two_digit_day(self):
        """Belt to the allowlist's braces: even a MATCH series is refused when
        the day is not a full two digits followed by a player tail."""
        assert _tennis_commence_target("KXATPMATCH-26SEP6", None) is None

    def test_linked_event_kickoff_beats_the_ticker_midnight(self):
        """The ticker knows the day; ESPN/odds_api know the hour."""
        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        assert (
            _tennis_commence_target("KXWTAMATCH-26SEP07OSARYB", kickoff) == kickoff
        )

    def test_night_session_spilling_past_midnight_is_still_accepted(self):
        """A US Open night match ticketed SEP07 can genuinely start 01:00Z on
        the 8th — the window must not reject a true kick-off."""
        kickoff = datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
        assert (
            _tennis_commence_target("KXWTAMATCH-26SEP07OSARYB", kickoff) == kickoff
        )

    def test_a_poisoned_event_date_is_never_copied_back(self):
        """This is the regression that would silently re-introduce the bug: an
        Event whose own commence_time came from the same +14d close_time. The
        ticker must win."""
        poisoned = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", poisoned
        ) == datetime(2026, 9, 7, tzinfo=UTC)

    def test_agreement_window_boundary_rejects_beyond_36h(self):
        ticker_date = datetime(2026, 9, 7, tzinfo=UTC)
        inside = ticker_date + timedelta(hours=35)
        outside = ticker_date + timedelta(hours=37)
        assert _tennis_commence_target("KXWTAMATCH-26SEP07OSARYB", inside) == inside
        assert _tennis_commence_target("KXWTAMATCH-26SEP07OSARYB", outside) == ticker_date

    def test_empty_ticker_is_survivable(self):
        assert _tennis_commence_target("", None) is None
        assert _tennis_commence_target(None, None) is None


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Captures the statements the driver issues, in order."""

    def __init__(self, rows):
        self._rows = rows
        self.updates = []          # (id, commence_time) pairs
        self.calibration_resets = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SELECT" in sql and "futures_markets fm" in sql:
            return _FakeResult(self._rows)
        if "UPDATE futures_markets" in sql:
            self.updates.append((params["id"], params["dt"]))
            return _FakeResult([])
        if "futures_outcomes" in sql:
            self.calibration_resets.append(params["ids"])
            return _FakeResult([])
        raise AssertionError(f"unexpected statement: {sql[:120]}")

    async def commit(self):
        self.committed = True


def _install_fake_session(monkeypatch, rows):
    session = _FakeSession(rows)

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(kalshi_task, "get_task_session", lambda: _Ctx())
    return session


def _row(id, external_id, commence_time, event_commence=None):
    return SimpleNamespace(
        id=id,
        external_id=external_id,
        commence_time=commence_time,
        event_commence=event_commence,
    )


class TestFixTennisCommenceTimesDriver:
    @pytest.mark.asyncio
    async def test_shifted_market_is_updated_and_correct_one_is_not(self, monkeypatch):
        rows = [
            # +14d — the bug
            _row(1, "KXWTAMATCH-26SEP07OSARYB", datetime(2026, 9, 21, 15, 0, tzinfo=UTC)),
            # already right — must not be written
            _row(2, "KXATPMATCH-26SEP06PAUALC", datetime(2026, 9, 6, tzinfo=UTC)),
        ]
        session = _install_fake_session(monkeypatch, rows)

        fixed = await _fix_tennis_commence_times()

        assert fixed == 1
        assert session.updates == [(1, datetime(2026, 9, 7, tzinfo=UTC))]

    @pytest.mark.asyncio
    async def test_outright_is_never_rewritten(self, monkeypatch):
        """An outright's far-future close_time looks exactly like the bug. It
        is not the bug, and the driver must not touch it."""
        rows = [_row(9, "KXWTA-26USO", datetime(2026, 9, 21, 15, 0, tzinfo=UTC))]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == 0
        assert session.updates == []
        assert session.committed is False

    @pytest.mark.asyncio
    async def test_linked_kickoff_is_written_when_it_agrees(self, monkeypatch):
        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        rows = [
            _row(
                3,
                "KXWTAMATCH-26SEP07JOVGAU",
                datetime(2026, 9, 21, 15, 0, tzinfo=UTC),
                event_commence=kickoff,
            )
        ]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == 1
        assert session.updates == [(3, kickoff)]

    @pytest.mark.asyncio
    async def test_calibration_is_reset_only_for_rows_that_moved(self, monkeypatch):
        rows = [
            _row(1, "KXWTAMATCH-26SEP07OSARYB", datetime(2026, 9, 21, 15, 0, tzinfo=UTC)),
            _row(2, "KXATPMATCH-26SEP06PAUALC", datetime(2026, 9, 6, tzinfo=UTC)),
            _row(9, "KXWTA-26USO", datetime(2026, 9, 21, 15, 0, tzinfo=UTC)),
        ]
        session = _install_fake_session(monkeypatch, rows)

        await _fix_tennis_commence_times()

        assert session.calibration_resets == [[1]]
        assert session.committed is True

    @pytest.mark.asyncio
    async def test_nothing_to_fix_commits_nothing(self, monkeypatch):
        rows = [_row(2, "KXATPMATCH-26SEP06PAUALC", datetime(2026, 9, 6, tzinfo=UTC))]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == 0
        assert session.calibration_resets == []
        assert session.committed is False


class TestWiredIntoPoll:
    """A fix-up nobody calls is not a fix. Asserted with AST, not a substring:
    a `grep` for the name matches its own definition and survives a comment."""

    def _poller_body(self):
        tree = ast.parse(inspect.getsource(kalshi_task))
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "_poll_kalshi_markets"
            ):
                return node
        raise AssertionError("_poll_kalshi_markets not found")

    def _calls_in(self, node):
        return {
            n.func.id
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }

    def test_poll_kalshi_calls_the_tennis_fixup(self):
        """Scoped to the poller's own body — a call anywhere else in the
        module (or in a test helper) would not run on the beat."""
        called = self._calls_in(self._poller_body())
        assert "_fix_tennis_commence_times" in called, (
            "_fix_tennis_commence_times is defined but never called by "
            "_poll_kalshi_markets — the open tennis markets stay two weeks "
            "in the future"
        )

    def test_it_runs_with_the_other_close_time_fixups(self):
        called = self._calls_in(self._poller_body())
        assert {
            "_fix_golf_commence_times",
            "_fix_hockey_commence_times",
            "_fix_tennis_commence_times",
        } <= called

    def test_it_sits_beside_the_other_close_time_fixups(self):
        """Golf and hockey fix the same class; tennis must run in the same
        deadline-guarded post-loop block, not somewhere it can be skipped."""
        src = inspect.getsource(kalshi_task)
        hockey = src.index("hockey_commence_fixed")
        tennis = src.index("tennis_commence_fixed")
        deadline = src.index("post_loop_skipped_deadline")
        assert hockey < tennis < deadline
