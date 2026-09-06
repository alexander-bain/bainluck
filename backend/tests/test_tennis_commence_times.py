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

# What an unfixed row actually holds: Kalshi's +14d settlement backstop. Every
# assertion below states the market's own stored value because the driver's
# SELECT filters `commence_time IS NOT NULL` — there is no production row
# without one, and #3532 turned on which value that is.
CLOSE_SHAPED = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)


class TestTennisCommenceTarget:
    """The per-market decision: ticker date, linked kick-off, or leave alone."""

    def test_open_match_is_redated_off_the_ticker(self):
        """The production specimen: Osaka vs Rybakina, Sep 7, stamped Sep 21."""
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", None, market_commence=CLOSE_SHAPED
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
        got = _tennis_commence_target(ticker, None, market_commence=CLOSE_SHAPED)
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
        assert _tennis_commence_target(
            ticker, None, market_commence=CLOSE_SHAPED
        ) is None

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
        assert _tennis_commence_target(
            "KXATP1RANK-26DEC31", None, market_commence=CLOSE_SHAPED
        ) is None

    def test_a_match_ticker_needs_a_full_two_digit_day(self):
        """Belt to the allowlist's braces: even a MATCH series is refused when
        the day is not a full two digits followed by a player tail."""
        assert _tennis_commence_target(
            "KXATPMATCH-26SEP6", None, market_commence=CLOSE_SHAPED
        ) is None

    def test_linked_event_kickoff_beats_the_ticker_midnight(self):
        """The ticker knows the day; ESPN/odds_api know the hour."""
        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", kickoff, market_commence=CLOSE_SHAPED
        ) == kickoff

    def test_night_session_spilling_past_midnight_is_still_accepted(self):
        """A US Open night match ticketed SEP07 can genuinely start 01:00Z on
        the 8th — the window must not reject a true kick-off."""
        kickoff = datetime(2026, 9, 8, 1, 30, tzinfo=UTC)
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", kickoff, market_commence=CLOSE_SHAPED
        ) == kickoff

    def test_a_poisoned_event_date_is_never_copied_back(self):
        """This is the regression that would silently re-introduce the bug: an
        Event whose own commence_time came from the same +14d close_time. The
        ticker must win."""
        poisoned = datetime(2026, 9, 21, 15, 0, tzinfo=UTC)
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", poisoned, market_commence=CLOSE_SHAPED
        ) == datetime(2026, 9, 7, tzinfo=UTC)

    def test_agreement_window_boundary_rejects_beyond_36h(self):
        ticker_date = datetime(2026, 9, 7, tzinfo=UTC)
        inside = ticker_date + timedelta(hours=35)
        outside = ticker_date + timedelta(hours=37)
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", inside, market_commence=CLOSE_SHAPED
        ) == inside
        assert _tennis_commence_target(
            "KXWTAMATCH-26SEP07OSARYB", outside, market_commence=CLOSE_SHAPED
        ) == ticker_date

    def test_empty_ticker_is_survivable(self):
        assert _tennis_commence_target(
            "", None, market_commence=CLOSE_SHAPED
        ) is None
        assert _tennis_commence_target(
            None, None, market_commence=CLOSE_SHAPED
        ) is None


class TestVenueOccurrenceSurvivesTheFixup:
    """#3532: this fix-up is the SECOND writer of commence_time in one beat.

    Since #3433 the main loop stores the venue's ``occurrence_datetime`` for
    game tickers, and every per-match tennis series is one. This fix-up then
    re-dated it to the ticker's midnight — which Eastern renders as 8:00 PM the
    previous evening, so both the hour and the DAY were wrong on the page.

    Venue read 2026-09-06 (``/markets?series_ticker=…&status=open``, the
    method notice 26 requires): KXWTADOUBLES 20/20, KXATPDOUBLES 32/32,
    KXWTAMATCH 16/16, KXATPMATCH 16/16, KXITFMATCH 140/140 carry an
    occurrence, and NOT ONE is at midnight UTC.
    """

    # KXWTADOUBLES-26SEP07SINTOWHUNKRA as the venue served it: occurrence
    # 18:00Z (Sep 7, 2:00 PM EDT) against a +14d close of Sep 21 15:00Z.
    SPECIMEN = "KXWTADOUBLES-26SEP07SINTOWHUNKRA"
    OCCURRENCE = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    TICKER_MIDNIGHT = datetime(2026, 9, 7, tzinfo=UTC)

    def test_the_venue_start_is_not_re_dated_to_midnight(self):
        """The whole bug in one assertion. Before #3532 this returned
        2026-09-07 00:00Z and the doubles page read "Sep 6, 8:00 PM EDT"."""
        assert _tennis_commence_target(
            self.SPECIMEN, None, market_commence=self.OCCURRENCE
        ) == self.OCCURRENCE

    def test_an_event_carrying_the_same_midnight_does_not_win(self):
        """The rows that actually render. 206 of the 426 clobbered markets are
        LINKED, and their Events were auto-created from the already-clobbered
        market — so the Event holds the identical midnight. Ordering the Event
        first without asking whether it knows the hour puts the bug straight
        back on exactly the population a reader sees."""
        assert _tennis_commence_target(
            self.SPECIMEN, self.TICKER_MIDNIGHT, market_commence=self.OCCURRENCE
        ) == self.OCCURRENCE

    def test_a_real_event_kickoff_still_outranks_the_market(self):
        """#3403's rule is not repealed: when ESPN/odds_api gave the Event a
        genuine kick-off, that still wins over the venue's own instant."""
        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        assert _tennis_commence_target(
            self.SPECIMEN, kickoff, market_commence=self.OCCURRENCE
        ) == kickoff

    def test_a_market_sitting_on_the_ticker_midnight_is_not_an_hour(self):
        """The equality arm of ``_knows_the_hour``. A candidate exactly on the
        ticker's midnight restates the ticker; preferring it would latch every
        already-clobbered row at the wrong time forever."""
        assert _tennis_commence_target(
            self.SPECIMEN, None, market_commence=self.TICKER_MIDNIGHT
        ) == self.TICKER_MIDNIGHT

    def test_a_night_match_spilling_into_the_next_utc_day_is_kept(self):
        """A 9pm ET start is 01:00Z on the ticker's NEXT day — 25h from the
        ticker midnight, inside the window, and a true start."""
        night = datetime(2026, 9, 8, 1, 0, tzinfo=UTC)
        assert _tennis_commence_target(
            self.SPECIMEN, None, market_commence=night
        ) == night

    @pytest.mark.parametrize(
        "ticker,market_commence",
        [
            # The +14d backstop this fix-up exists for, still re-dated.
            ("KXWTAMATCH-26SEP07OSARYB", CLOSE_SHAPED),
            # ITF is absent from KALSHI_TICKER_TO_DISPLAY_LABEL, so the main
            # loop never reads its occurrence and these rows arrive close-
            # shaped. 140 open at the venue — the fix-up is all they have.
            ("KXITFMATCH-26SEP06AHRNEC", datetime(2026, 9, 21, 2, 0, tzinfo=UTC)),
            ("KXITFWMATCH-26SEP06KURSID", datetime(2026, 9, 21, 2, 0, tzinfo=UTC)),
        ],
    )
    def test_close_shaped_rows_are_still_re_dated(self, ticker, market_commence):
        """The fix must not be a way of switching the fix-up off. Measured on
        production: every close-shaped tennis row sits 13d12h-15d3h from its
        ticker date, so none can reach the 36h window."""
        got = _tennis_commence_target(ticker, None, market_commence=market_commence)
        assert got is not None
        assert got.hour == 0 and got.minute == 0
        assert got != market_commence

    def test_the_two_writers_in_one_beat_agree(self):
        """The pair-wise guard, and the one that would have caught this.

        Neither writer is wrong alone — ``_kalshi_commence_time`` returns the
        venue instant and ``_tennis_commence_target`` returns the ticker day —
        so a test of either in isolation stays green while the beat as a whole
        stores the wrong time. Assert the COMPOSITION: what the main loop
        stores must survive the post-loop fix-up unchanged.
        """
        venue = [
            SimpleNamespace(
                close_time=datetime(2026, 9, 21, 15, 0, tzinfo=UTC),
                occurrence_datetime=self.OCCURRENCE,
            )
        ] * 2
        stored = kalshi_task._kalshi_commence_time(venue, is_game=True)
        assert stored == self.OCCURRENCE, "main loop no longer reads the venue"

        assert _tennis_commence_target(
            self.SPECIMEN, None, market_commence=stored
        ) == stored, (
            "the post-loop tennis fix-up overwrote what the main loop stored "
            "from the venue — #3532"
        )

    def test_the_specimen_really_is_a_game_ticker(self):
        """The composition above is only load-bearing if the main loop takes
        the occurrence branch for this series. If a future edit drops
        kxwtadoubles from KALSHI_TICKER_TO_DISPLAY_LABEL, is_game goes False,
        the main loop stores close_time again, and the guard above would pass
        for the wrong reason."""
        assert kalshi_task._is_kalshi_game_ticker(self.SPECIMEN) == "WTA"


class TestTennisEventNeedsTheHour:
    """#3532 / CERT-2070: the half a reader actually sees.

    Fixing `futures_markets.commence_time` does not move the page.
    `GET /api/events/{id}` serialises `event.commence_time`, and the header and
    "Starts in" countdown read that field — so the market row can carry 18:00Z
    while `/events/15305555` keeps rendering midnight. These Events were
    auto-created FROM the clobbered market and nothing else re-times them.
    """

    TICKER_MIDNIGHT = datetime(2026, 9, 7, tzinfo=UTC)
    OCCURRENCE = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
    DERIVED = "pm_kalshi_KXWTADOUBLES-26SEP07SINTOWHUNKRA"

    def _call(self, **kw):
        kw.setdefault("event_external_id", self.DERIVED)
        kw.setdefault("event_commence", self.TICKER_MIDNIGHT)
        kw.setdefault("ticker_date", self.TICKER_MIDNIGHT)
        kw.setdefault("target", self.OCCURRENCE)
        return kalshi_task._tennis_event_needs_the_hour(**kw)

    def test_a_market_born_event_on_the_ticker_midnight_is_repaired(self):
        """The named specimen: event 15305555, `/events/15305555`."""
        assert self._call() is True

    @pytest.mark.parametrize(
        "external_id",
        [
            "espn_401745231",          # ESPN
            "odds_api_9f2c",           # Odds API
            "pm_polymarket_0xabc",     # another venue's derived row
            None,                      # no provenance at all
            "",
        ],
    )
    def test_an_event_we_did_not_mint_is_never_re_timed(self, external_id):
        """The control the CERT-2070 block requires. An authoritative start is
        never overwritten from a ticker, even when it happens to sit on the
        ticker's midnight — provenance decides, not the value."""
        assert self._call(event_external_id=external_id) is False

    def test_an_authoritative_hour_is_not_overwritten(self):
        """The other direction: a real kick-off is not the ticker midnight, so
        the equality guard alone already refuses it."""
        kickoff = datetime(2026, 9, 7, 15, 0, tzinfo=UTC)
        assert self._call(event_commence=kickoff, target=kickoff) is False

    def test_a_market_born_event_still_on_the_close_time_is_left_alone(self):
        """Out of the repair named in the block. Re-dating a +14d close is a
        different decision from restoring an hour to the right day, and doing
        it here would move an Event two weeks with no venue instant behind it."""
        assert self._call(event_commence=CLOSE_SHAPED) is False

    def test_nothing_happens_when_there_is_no_hour_to_give(self):
        """`target` back at the bare ticker midnight means the venue told us
        nothing the Event does not already have — writing would be churn."""
        assert self._call(target=self.TICKER_MIDNIGHT) is False

    @pytest.mark.parametrize("field", ["event_commence", "ticker_date", "target"])
    def test_a_missing_input_refuses(self, field):
        assert self._call(**{field: None}) is False

    def test_the_repaired_hour_still_links_to_its_own_ticker(self):
        """The thing that would break silently. The Kalshi linkage guard
        compares the ticker date to the EVENT's commence_time, and moving an
        Event off midnight is exactly the sort of change that can push it out
        of tolerance and unlink every market on it.

        It does not, because a date-only ticker is compared by EASTERN CALENDAR
        DAY (`_EVENT_DATE_MAX_DIFF_DAYS = 2`), not the ±3h
        `_EVENT_DATE_MAX_DIFF_HOURS` window. Asserted against the real
        predicate rather than reasoned about — I predicted the opposite.
        """
        from app.tasks.prediction_market_matching import auto_create_self_refutes

        market = SimpleNamespace(
            source="kalshi",
            external_id="KXWTADOUBLES-26SEP07SINTOWHUNKRA",
            commence_time=self.OCCURRENCE,
        )
        assert auto_create_self_refutes(market, self.TICKER_MIDNIGHT) is False
        assert auto_create_self_refutes(market, self.OCCURRENCE) is False, (
            "moving the Event to the venue hour put it outside the ticker-date "
            "linkage tolerance — every market on it would stop linking"
        )


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


_UPDATE_RE = __import__("re").compile(
    r"UPDATE\s+(\w+)\s+SET\s+(.*?)\s+WHERE", __import__("re").S | __import__("re").I
)


def _assert_columns_exist(sql):
    """Every column an UPDATE names must exist on the real table.

    A fake session answers any SQL you hand it, so a driver test proves the
    decision and nothing about the schema. #3532's first cut wrote
    `UPDATE events SET commence_time = :dt, updated_at = NOW()` — and `events`
    has `created_at` and NO `updated_at`, unlike `futures_markets`. Postgres
    raises UndefinedColumn, `_poll_kalshi_markets` swallows it, and the fix-up
    silently loses BOTH halves on every beat. Only the real-Postgres arm caught
    it; this makes the five cheap driver tests catch the class too, off the ORM
    metadata and with no database.
    """
    import app.models.models  # noqa: F401 — registers every table
    from app.services.database import Base

    for table, assignments in _UPDATE_RE.findall(sql):
        cols = Base.metadata.tables[table].columns.keys()
        for assignment in assignments.split(","):
            name = assignment.split("=")[0].strip()
            assert name in cols, (
                f"UPDATE {table} SET {name} = ... names a column that does not "
                f"exist. Postgres would raise UndefinedColumn and the poll's "
                f"except would swallow it. Columns: {sorted(cols)}"
            )


class _FakeSession:
    """Captures the statements the driver issues, in order."""

    def __init__(self, rows):
        self._rows = rows
        self.updates = []          # (id, commence_time) pairs
        self.event_updates = []    # (event_id, commence_time) pairs — #3532
        self.calibration_resets = []
        self.committed = False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        _assert_columns_exist(sql)
        if "SELECT" in sql and "futures_markets fm" in sql:
            return _FakeResult(self._rows)
        if "UPDATE futures_markets" in sql:
            self.updates.append((params["id"], params["dt"]))
            return _FakeResult([])
        if "UPDATE events" in sql:
            self.event_updates.append((params["id"], params["dt"]))
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


def _row(
    id,
    external_id,
    commence_time,
    event_commence=None,
    *,
    event_id=None,
    event_external_id=None,
):
    """One row of the driver's SELECT.

    `event_external_id` defaults to the market-born shape the auto-create
    produces (`pm_kalshi_<ticker>`) whenever the row has a linked Event, so a
    case that says nothing about provenance describes the majority population
    rather than an unlinked one.
    """
    linked = event_commence is not None
    return SimpleNamespace(
        id=id,
        external_id=external_id,
        commence_time=commence_time,
        event_commence=event_commence,
        event_id=event_id if event_id is not None else (id if linked else None),
        event_external_id=(
            event_external_id
            if event_external_id is not None
            else (f"pm_kalshi_{external_id}" if linked else None)
        ),
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

        assert fixed["markets"] == 1
        assert session.updates == [(1, datetime(2026, 9, 7, tzinfo=UTC))]

    @pytest.mark.asyncio
    async def test_outright_is_never_rewritten(self, monkeypatch):
        """An outright's far-future close_time looks exactly like the bug. It
        is not the bug, and the driver must not touch it."""
        rows = [_row(9, "KXWTA-26USO", datetime(2026, 9, 21, 15, 0, tzinfo=UTC))]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == {
            "markets": 0, "events": 0, "scanned": 1,
        }
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

        assert (await _fix_tennis_commence_times())["markets"] == 1
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
    async def test_the_market_is_left_alone_and_the_event_gets_the_hour(
        self, monkeypatch
    ):
        """#3532 end to end through the driver, both halves at once.

        The steady state after the main loop has run: the market already holds
        the venue's 18:00Z and its linked Event still carries the old midnight.

        The market must get NO UPDATE — not even one writing the same value,
        which would still reset `calibration_probability` on every outcome
        every beat. The EVENT must get one, because `event.commence_time` is
        the field `GET /api/events/{id}` serialises and the page header and
        "Starts in" countdown render.
        """
        occurrence = datetime(2026, 9, 7, 18, 0, tzinfo=UTC)
        rows = [
            _row(
                7,
                "KXWTADOUBLES-26SEP07SINTOWHUNKRA",
                occurrence,
                event_commence=datetime(2026, 9, 7, tzinfo=UTC),
                event_id=15305555,
            )
        ]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == {
            "markets": 0, "events": 1, "scanned": 1,
        }
        assert session.updates == []
        assert session.calibration_resets == []
        assert session.event_updates == [(15305555, occurrence)]
        assert session.committed is True

    @pytest.mark.asyncio
    async def test_nothing_to_fix_commits_nothing(self, monkeypatch):
        rows = [_row(2, "KXATPMATCH-26SEP06PAUALC", datetime(2026, 9, 6, tzinfo=UTC))]
        session = _install_fake_session(monkeypatch, rows)

        assert await _fix_tennis_commence_times() == {
            "markets": 0, "events": 0, "scanned": 1,
        }
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
