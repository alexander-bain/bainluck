"""#8871 — the high-value price refresher carries the resolution window forward.

**The reader-visible defect.** ``bainluck.com/futures/109082`` "Maine Senate
winner?" read **Resolves Nov 3, 2027** on 2026-09-26, five weeks before the
election. Kalshi's ``SENATEME-26`` sends ``close_time == expiration_time ==
2027-11-03`` (a one-year backstop) and ``expected_expiration_time = 2027-01-04``;
the discovery poll's :func:`derive_resolution_window` turns that into
2027-01-04, but the poll has not upserted any ``SENATE*``/``HOUSE*``/
``GOVPARTY*`` row since 2026-09-10 (scan verdict ``starved``). The refresher
read the same payload at 14:54Z that day and dropped the dates.

These guards pin three things:

1. :func:`_kalshi_window_to_write` yields the poll's date for a future, and
   NOTHING for a single contest, a no-close event, or a past date.
2. ``_fetch_kalshi_prices`` fills ``windows`` from the payload it already read,
   and only on the list return.
3. The write statement moves a backstop row and nothing else, run against a
   real SQLite table (the fences are data-level, so they are proved on rows).
   ``tests/integration/test_futures_price_refresh_writes_pg.py`` runs the same
   statement on Postgres.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timezone

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks import futures_price_refresh as fpr

# A fixed clock, well before every date below (gotcha #44).
NOW = datetime(2026, 9, 26, 17, 0, tzinfo=timezone.utc)
BACKSTOP = "2027-11-03T15:00:00Z"
EXPECTED = "2027-01-04T15:00:00Z"


def _leg(ticker, **over):
    leg = {
        "ticker": ticker,
        "status": "active",
        "result": "",
        "yes_bid_dollars": "0.3600",
        "yes_ask_dollars": "0.3700",
        "last_price_dollars": "0.3650",
        "close_time": BACKSTOP,
        "expiration_time": BACKSTOP,
        "expected_expiration_time": EXPECTED,
    }
    leg.update(over)
    return leg


def _senateme():
    """``SENATEME-26`` exactly as Kalshi served it on 2026-09-26 (dates + status)."""
    return {
        "event_ticker": "SENATEME-26",
        "title": "Maine Senate winner?",
        "markets": [_leg("SENATEME-26-D"), _leg("SENATEME-26-R")],
    }


def _parsed_markets(raw):
    return KalshiAPIService(api_key=None)._parse_event(raw).markets


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# --- 1. what may be written -------------------------------------------------


class TestTheWindowToWrite:
    def test_a_backstopped_future_takes_the_venues_estimate(self):
        got = fpr._kalshi_window_to_write(
            "SENATEME-26", _parsed_markets(_senateme()), NOW
        )
        assert got == (_dt(EXPECTED), _dt(BACKSTOP))

    def test_a_single_contest_is_never_written(self):
        # #8586: for a match the estimate is the START. The poll's own
        # derivation would keep the pad here; this task writes nothing at all.
        # The start is in the FUTURE on purpose, so the only fence that can
        # refuse it is the single-contest one, not the past-date one.
        ticker = "KXATPMATCH-26SEP28MEDROY"
        raw = {
            "event_ticker": ticker,
            "title": "Medvedev vs Royer",
            "markets": [
                _leg(
                    f"{ticker}-MED",
                    close_time="2026-10-12T05:00:00Z",
                    expiration_time="2026-10-12T05:00:00Z",
                    expected_expiration_time="2026-09-28T08:00:00Z",
                )
            ],
        }
        markets = _parsed_markets(raw)
        # Control: without the contest fence this row WOULD be written.
        unfenced = fpr.derive_resolution_window(markets)
        assert unfenced.resolution_date == _dt("2026-09-28T08:00:00Z") > NOW
        assert fpr._kalshi_window_to_write(ticker, markets, NOW) is None

    def test_a_past_date_is_never_written(self):
        # The estimate has passed while the venue still lists the market
        # active. Writing it would hand `mark_resolved_futures` a trading market.
        raw = _senateme()
        for m in raw["markets"]:
            m["expected_expiration_time"] = "2026-09-20T00:00:00Z"
        assert (
            fpr._kalshi_window_to_write("SENATEME-26", _parsed_markets(raw), NOW)
            is None
        )

    def test_an_event_with_no_close_time_writes_nothing(self):
        raw = _senateme()
        for m in raw["markets"]:
            m.pop("close_time")
        assert (
            fpr._kalshi_window_to_write("SENATEME-26", _parsed_markets(raw), NOW)
            is None
        )

    def test_it_is_the_polls_derivation_not_a_second_one(self):
        # A future with a REAL close (earlier than the backstop, no pad): the
        # poll takes the close, so this does too.
        raw = _senateme()
        for m in raw["markets"]:
            m["close_time"] = "2027-02-01T00:00:00Z"
        markets = _parsed_markets(raw)
        want = fpr.derive_resolution_window(markets)
        got = fpr._kalshi_window_to_write("SENATEME-26", markets, NOW)
        assert got == (want.resolution_date, want.expiration_time)
        assert got[0] == _dt("2027-02-01T00:00:00Z")

    def test_no_ticker_or_no_markets_is_nothing(self):
        assert (
            fpr._kalshi_window_to_write(None, _parsed_markets(_senateme()), NOW) is None
        )
        assert fpr._kalshi_window_to_write("SENATEME-26", [], NOW) is None


# --- 2. the fetch fills it from the payload it already read -----------------


class _Venue:
    """`get_event` over a fixed payload; the PARSER is the real one."""

    def __init__(self, raw):
        self._raw = raw
        self.calls = 0
        self._svc = KalshiAPIService(api_key=None)

    async def get_event(self, ticker, with_nested_markets=True):
        self.calls += 1
        return self._raw

    def _parse_event(self, raw):
        return self._svc._parse_event(raw)


class TestTheFetchFillsTheWindow:
    def test_filled_on_a_live_book_with_no_extra_call(self):
        venue = _Venue(_senateme())
        windows: dict = {}
        priced = asyncio.run(
            fpr._fetch_kalshi_prices(venue, "SENATEME-26", windows=windows)
        )
        assert isinstance(priced, list) and priced
        assert windows == {"SENATEME-26": (_dt(EXPECTED), _dt(BACKSTOP))}
        assert venue.calls == 1

    def test_without_windows_the_return_is_unchanged(self):
        with_w = asyncio.run(
            fpr._fetch_kalshi_prices(_Venue(_senateme()), "SENATEME-26", windows={})
        )
        without = asyncio.run(
            fpr._fetch_kalshi_prices(_Venue(_senateme()), "SENATEME-26")
        )
        assert with_w == without

    def test_a_settled_event_fills_nothing(self):
        raw = _senateme()
        for m in raw["markets"]:
            m.update(status="finalized", result="yes")
        windows: dict = {}
        got = asyncio.run(
            fpr._fetch_kalshi_prices(_Venue(raw), "SENATEME-26", windows=windows)
        )
        assert got is fpr.VENUE_SETTLED
        assert windows == {}

    def test_a_derivation_failure_costs_the_date_not_the_prices(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("derivation broke")

        monkeypatch.setattr(fpr, "_kalshi_window_to_write", _boom)
        windows: dict = {}
        priced = asyncio.run(
            fpr._fetch_kalshi_prices(
                _Venue(_senateme()), "SENATEME-26", windows=windows
            )
        )
        assert isinstance(priced, list) and priced
        assert windows == {}


# --- 3. the statement moves a backstop row and nothing else -----------------


def _table():
    con = sqlite3.connect(":memory:")
    con.execute(
        """CREATE TABLE futures_markets (
               id INTEGER PRIMARY KEY, source TEXT, status TEXT,
               resolution_date TEXT, expiration_time TEXT)"""
    )
    return con


def _write(con, mid, rd, exp):
    return con.execute(
        str(fpr._KALSHI_WINDOW_WRITE_SQL),
        {"mid": mid, "resolution_date": rd, "expiration_time": exp},
    ).rowcount


def _row(con, mid):
    return con.execute(
        "SELECT resolution_date, expiration_time FROM futures_markets WHERE id = ?",
        (mid,),
    ).fetchone()


B = "2027-11-03 15:00:00+00:00"
E = "2027-01-04 15:00:00+00:00"


class TestTheWriteFences:
    def test_the_specimen_moves(self):
        con = _table()
        con.execute(
            "INSERT INTO futures_markets VALUES (109082,'kalshi','open',?,?)", (B, B)
        )
        assert _write(con, 109082, E, B) == 1
        assert _row(con, 109082) == (E, B)

    def test_a_row_already_on_its_derived_date_is_zero_writes(self):
        con = _table()
        con.execute(
            "INSERT INTO futures_markets VALUES (1,'kalshi','open',?,?)", (B, B)
        )
        # The derivation says the pad (no earlier estimate): nothing to do.
        assert _write(con, 1, B, B) == 0

    def test_a_real_close_is_the_polls_to_keep(self):
        con = _table()
        real = "2027-02-01 00:00:00+00:00"
        con.execute(
            "INSERT INTO futures_markets VALUES (2,'kalshi','open',?,?)", (real, B)
        )
        assert _write(con, 2, E, B) == 0
        assert _row(con, 2) == (real, B)

    def test_a_resolved_row_is_untouched(self):
        con = _table()
        con.execute(
            "INSERT INTO futures_markets VALUES (3,'kalshi','resolved',?,?)", (B, B)
        )
        assert _write(con, 3, E, B) == 0

    def test_another_source_is_untouched(self):
        con = _table()
        con.execute(
            "INSERT INTO futures_markets VALUES (4,'polymarket','open',?,?)", (B, B)
        )
        assert _write(con, 4, E, B) == 0

    def test_a_missing_expiration_never_blanks_the_backstop(self):
        con = _table()
        con.execute(
            "INSERT INTO futures_markets VALUES (5,'kalshi','open',?,?)", (B, B)
        )
        assert _write(con, 5, E, None) == 1
        assert _row(con, 5) == (E, B)

    def test_it_never_writes_status_or_a_grade(self):
        sql = str(fpr._KALSHI_WINDOW_WRITE_SQL)
        set_clause = sql.split("SET", 1)[1].split("WHERE", 1)[0]
        assert "status" not in set_clause
        assert "is_winner" not in sql


# --- 4. the wiring: consumed after the price commit, in its own transaction --

from tests.test_futures_price_refresh import _RunHarness  # noqa: E402

SPECIMEN_ROW = (109082, "kalshi", "SENATEME-26", 608_384, None, None)


class _WindowHarness(_RunHarness):
    """The real entry point with one Kalshi class row, the Maine Senate market.

    Only the venue and the price writer are faked; the loop, its transaction
    boundaries and the stats are the task's own.
    """

    def __init__(self, *, filled, fail_window=False):
        from app.utils.feed_served_markets import SERVED_EMPTY

        signal = type(
            "Sig",
            (),
            {
                "ids": [],
                "state": SERVED_EMPTY,
                "green_allowed": True,
                "shapes": 0,
                "stale_shapes": 0,
                "unreadable_shapes": 0,
            },
        )()
        super().__init__(signal=signal, class_rows=[SPECIMEN_ROW + (0, 1)])
        self.filled = filled
        self.fail_window = fail_window
        self.log: list[str] = []

    class _Session(_RunHarness._Session):
        async def execute(self, statement, params=None):
            if statement is fpr._KALSHI_WINDOW_WRITE_SQL:
                self.outer.log.append(
                    f"window:{params['mid']}:{params['resolution_date'].date()}"
                )
                if self.outer.fail_window:
                    raise RuntimeError("window write failed")
                return _RunHarness._Result(rows=[(params["mid"],)])
            return await super().execute(statement, params)

        async def commit(self):
            self.outer.log.append("commit")

        async def rollback(self):
            self.outer.log.append("rollback")

    async def run(self, monkeypatch):
        outer = self

        async def _fetch(service, external_id, *, windows=None):
            outer.log.append(f"fetch:{external_id}")
            if windows is not None and outer.filled is not None:
                windows[external_id] = outer.filled
            return [{"external_id": "SENATEME-26-D", "probability": 0.365}]

        async def _write_prices(session, mid, source, priced, stats):
            outer.log.append(f"prices:{mid}")
            return 1

        async def _nothing(*a, **k):
            return {}

        class _KService:
            async def close(self):
                return None

        monkeypatch.setenv("KALSHI_API_KEY", "test-only")
        monkeypatch.setattr(fpr, "_fetch_kalshi_prices", _fetch)
        monkeypatch.setattr(fpr, "_write_prices", _write_prices)
        monkeypatch.setattr(fpr, "_scan_kalshi_frozen_certain", _nothing)
        monkeypatch.setattr(fpr, "_kalshi_reach_arm", _nothing)
        monkeypatch.setattr(
            "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: _KService()
        )
        return await super().run(monkeypatch)


def _after_fetch(log):
    return log[log.index("fetch:SENATEME-26") + 1 :]


class TestTheLoopWritesTheWindow:
    @pytest.mark.asyncio
    async def test_written_after_the_price_commit_and_counted(self, monkeypatch):
        h = _WindowHarness(filled=(_dt(EXPECTED), _dt(BACKSTOP)))
        stats = await h.run(monkeypatch)
        tail = _after_fetch(h.log)
        # prices, their commit, THEN the window in its own commit.
        assert tail[:4] == [
            "prices:109082",
            "commit",
            "window:109082:2027-01-04",
            "commit",
        ], tail
        assert stats["resolution_windows_rederived"] == 1

    @pytest.mark.asyncio
    async def test_nothing_derived_is_nothing_written_and_reads_zero(self, monkeypatch):
        h = _WindowHarness(filled=None)
        stats = await h.run(monkeypatch)
        assert not [e for e in h.log if e.startswith("window:")]
        # Reported as zero, not absent: zero and "never asked" must differ.
        assert stats["resolution_windows_rederived"] == 0

    @pytest.mark.asyncio
    async def test_a_failed_window_write_keeps_the_prices(self, monkeypatch):
        h = _WindowHarness(filled=(_dt(EXPECTED), _dt(BACKSTOP)), fail_window=True)
        stats = await h.run(monkeypatch)
        tail = _after_fetch(h.log)
        # The price commit landed BEFORE the window write was attempted, so the
        # window's rollback cannot take the prices with it.
        assert tail[:4] == [
            "prices:109082",
            "commit",
            "window:109082:2027-01-04",
            "rollback",
        ], tail
        assert stats["resolution_windows_rederived"] == 0
        assert stats["markets_priced"] == 1
        assert any("kalshi window SENATEME-26" in e for e in stats["errors"])
