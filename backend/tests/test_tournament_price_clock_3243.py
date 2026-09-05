"""#3243 / #2898 — the tournament page's freshness clock, and why it is a MAX.

THE TWO MEASUREMENTS THIS FILE EXISTS BETWEEN
----------------------------------------------
`/tournaments/us-open` grades every price it renders with one age, and that age
has now been wrong in both directions, each time because one column was trusted
alone:

* **Day 1.** `futures_outcomes.last_updated` measured a MONTH stale on the
  Polymarket men's field while its snapshots ran current. The route was written
  to read `futures_odds_snapshots.captured_at` and its docstring said "never
  from `last_updated`".
* **2026-09-05, #3243.** The inverse, on the 18 Kalshi `duel` markets behind the
  Round-of-32 slate: `last_updated` moving every ~30 s while `captured_at` sat
  at 06:53:42Z — 8.9 h, identical to the microsecond on all 18, one batch write.
  The page rendered "⚠ Updates paused … these are the last probabilities we
  saw, not live ones" over a probability that had changed 40 seconds earlier,
  while the sibling event page said "live · 42s ago" in the same minute. #2898
  is the same field from the other side: its 0-4 h sawtooth, sampled at
  `16:49:00` and `20:49:00`, is exactly the 2-hourly `poll_kalshi_markets` beat
  — it was measuring the poll's cadence, never the price's age.

Both columns are LOWER BOUNDS stamped by a writer that had just read the venue,
so neither can be too new and the newer of the two is the honest answer. That is
the invariant here. The tests below drive both measured populations through the
real function, so a future collapse to either single column fails on the census
that motivated the other one.

WHY THE CLASS OF BUG IS "ONE QUESTION, TWO ANSWERS"
----------------------------------------------------
`_load_prices` is the single loader behind boards, grid, bracket, slate and
props, so this is not one banner: it is every freshness word the hub says. The
guard named after the invariant is `TestNeitherClockAlone`; it is deliberately
not named after the US Open.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.routes import tournaments


NOW = datetime(2026, 9, 5, 15, 53, 0, tzinfo=timezone.utc)


def observed(history_at=None, touched_at=None, probability=0.51):
    return tournaments._price_observed_at(
        history_at=history_at, touched_at=touched_at, probability=probability
    )


class TestNeitherClockAlone:
    """The invariant: freshness is the newer of the history and touch clocks."""

    def test_live_ws_price_beats_a_stale_snapshot(self):
        """#3243's population, to the minute it was measured.

        `kalshi_ws` flushes every 2 s and writes no snapshot row at all, so on
        an in-play match the history clock is the last time a POLL happened and
        says nothing about the price. Reading it alone is what put "not live
        ones" over a number 40 seconds old.
        """
        got = observed(
            history_at=datetime(2026, 9, 5, 6, 53, 42, 548928, tzinfo=timezone.utc),
            touched_at=datetime(2026, 9, 5, 15, 53, 0, 772827, tzinfo=timezone.utc),
        )
        assert got == datetime(2026, 9, 5, 15, 53, 0, 772827, tzinfo=timezone.utc)
        assert (NOW - got).total_seconds() < 60

    def test_current_snapshot_beats_a_month_stale_touch_stamp(self):
        """The Day-1 census, which is why this is a max and not a swap.

        A route that answered #3243 by simply switching columns would re-open
        the bug the original spelling was written for. Same function, opposite
        population, and it must still choose the snapshot.
        """
        current_snapshot = NOW - timedelta(minutes=9)
        got = observed(history_at=current_snapshot, touched_at=NOW - timedelta(days=31))
        assert got == current_snapshot

    def test_agreement_is_not_a_third_answer(self):
        """The polls write both stamps in one breath, so most rows tie."""
        assert observed(history_at=NOW, touched_at=NOW) == NOW

    @pytest.mark.parametrize(
        "history_at,touched_at",
        [
            (None, NOW - timedelta(hours=2)),
            (NOW - timedelta(hours=2), None),
        ],
    )
    def test_one_clock_present_is_still_an_observation(self, history_at, touched_at):
        """An outcome the other rail has never touched is not unobserved.

        A never-polled-but-streaming outcome has no snapshot row; a row whose
        history came from a candlestick backfill may predate any touch stamp we
        kept. Requiring both would turn either into `dark`, which reads on the
        page as "nobody quotes this match" — the loudest wrong answer available.
        """
        assert observed(history_at=history_at, touched_at=touched_at) == NOW - timedelta(
            hours=2
        )

    def test_no_clocks_is_absence_not_now(self):
        """`None` must survive to `price_state`, which reads it as `dark`."""
        assert observed(history_at=None, touched_at=None) is None


class TestTheTouchStampNeedsAPrice:
    """`last_updated` is NOT NULL with `server_default=func.now()` — so a
    freshly minted, never-priced outcome carries a stamp from its own INSERT."""

    def test_unpriced_outcome_does_not_report_a_fresh_reading(self):
        """The whole hazard of admitting the touch clock, in one row.

        Without this guard an outcome created a minute ago and never priced
        would grade `live` — a confident reading of a number that does not
        exist, which is worse than the stale banner this change removes.
        """
        assert observed(touched_at=NOW, probability=None) is None

    def test_unpriced_outcome_still_honours_a_real_snapshot(self):
        """A PRICED snapshot is its own evidence.

        `load_latest_observed_at` only returns ids that have a snapshot with a
        probability, so its presence means a price was once observed even if the
        outcome row has since been blanked. Suppressing that would throw away a
        real observation to guard against a fabricated one.
        """
        snap = NOW - timedelta(hours=3)
        assert observed(history_at=snap, probability=None) == snap

    def test_a_zero_probability_is_a_price(self):
        """`0.0` is falsy and is a real quote. The guard tests for `None`."""
        assert observed(touched_at=NOW, probability=0.0) == NOW


class TestNaiveStampsCannotEmptyThePage:
    """`max()` over a mixed naive/aware pair raises, and the raise would empty
    the whole price map rather than one cell (gotcha #42)."""

    @pytest.mark.parametrize("which", ["history", "touch", "both"])
    def test_mixed_awareness_compares_as_utc(self, which):
        naive = datetime(2026, 9, 5, 15, 53, 0)
        aware = datetime(2026, 9, 5, 6, 53, 42, tzinfo=timezone.utc)
        history = naive if which in ("history", "both") else aware
        touch = naive if which in ("touch", "both") else aware
        got = observed(history_at=history, touched_at=touch)
        assert got == datetime(2026, 9, 5, 15, 53, 0, tzinfo=timezone.utc)

    def test_naive_is_read_as_utc_not_shifted(self):
        """Reading a naive stamp as local time would move an age by the
        server's offset and either invent or suppress the banner."""
        naive = datetime(2026, 9, 5, 15, 53, 0)
        assert observed(touched_at=naive) == naive.replace(tzinfo=timezone.utc)


class _Row:
    """One `futures_outcomes` row as `_load_prices` reads it."""

    def __init__(self, *, id, probability, last_updated):
        self.id = id
        self.name = f"outcome-{id}"
        self.current_probability = probability
        self.opening_probability = 0.2
        self.current_yes_bid = None
        self.current_yes_ask = None
        self.volume_24h = None
        self.volume_updated_at = None
        self.last_updated = last_updated


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Session:
    """Returns the rows it was handed, and records what it was asked for.

    Deliberately NOT a query-blind fake: `_load_prices` must issue exactly one
    statement, and a fake that answered any number of them would hide the second
    round trip this change is explicitly avoiding.
    """

    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rows)


class TestTheRouteItselfChoosesTheNewerClock:
    """`_price_observed_at` is right and unreachable is the bug with a green
    unit test, so these drive `_load_prices` and read the dict it returns.

    #3243 shipped as exactly this shape: both clocks were available to the
    function and one of them was never asked for.
    """

    @pytest.fixture
    def stale_history(self, monkeypatch):
        """06:53:42Z on every outcome — the measured production state."""
        captured = datetime(2026, 9, 5, 6, 53, 42, 548928, tzinfo=timezone.utc)

        async def fake_loader(session, outcome_ids):
            return {oid: captured for oid in outcome_ids}

        monkeypatch.setattr(tournaments, "load_latest_observed_at", fake_loader)
        return captured

    async def test_in_play_row_reports_the_live_touch_stamp(self, stale_history):
        live = datetime(2026, 9, 5, 15, 53, 0, 772827, tzinfo=timezone.utc)
        session = _Session([_Row(id=224269748, probability=0.51, last_updated=live)])

        loaded = await tournaments._load_prices(session, [224269748], now=NOW)

        assert loaded[224269748]["observed_at"] == live
        assert loaded[224269748]["observed_at"] != stale_history

    async def test_a_row_nobody_has_re_quoted_still_reads_stale(self, stale_history):
        """The same response must not flatter the rows that ARE stale.

        Fifteen of the eighteen measured markets had not started; their touch
        stamp was 06:54Z too. If the fix made those read live it would have
        replaced a false "paused" with a false "current", which is worse.
        """
        untouched = datetime(2026, 9, 5, 6, 54, 24, 963511, tzinfo=timezone.utc)
        session = _Session([_Row(id=224583459, probability=0.16, last_updated=untouched)])

        loaded = await tournaments._load_prices(session, [224583459], now=NOW)

        assert loaded[224583459]["observed_at"] == untouched
        assert (NOW - loaded[224583459]["observed_at"]).total_seconds() > 8 * 3600

    async def test_one_response_grades_both_kinds_of_row(self, stale_history):
        """Live and stale in the same payload, which is the real slate."""
        live = datetime(2026, 9, 5, 15, 53, 0, tzinfo=timezone.utc)
        old = datetime(2026, 9, 5, 6, 54, 24, tzinfo=timezone.utc)
        session = _Session(
            [
                _Row(id=1, probability=0.51, last_updated=live),
                _Row(id=2, probability=0.16, last_updated=old),
            ]
        )

        loaded = await tournaments._load_prices(session, [1, 2], now=NOW)

        assert loaded[1]["observed_at"] == live
        assert loaded[2]["observed_at"] == old

    async def test_day_one_population_still_reads_its_snapshot(self, monkeypatch):
        """The other census, driven through the route rather than the composer.

        Without this the whole class could stay green while `observed_at` was
        quietly swapped to `row.last_updated` — the Day-1 bug, re-shipped as the
        cure for #3243. Every row above happens to have the touch stamp newer,
        which is exactly the blind spot.
        """
        current_snapshot = NOW - timedelta(minutes=9)

        async def fake_loader(session, outcome_ids):
            return {oid: current_snapshot for oid in outcome_ids}

        monkeypatch.setattr(tournaments, "load_latest_observed_at", fake_loader)
        month_stale = NOW - timedelta(days=31)
        session = _Session([_Row(id=9, probability=0.44, last_updated=month_stale)])

        loaded = await tournaments._load_prices(session, [9], now=NOW)

        assert loaded[9]["observed_at"] == current_snapshot

    async def test_the_touch_stamp_costs_no_second_round_trip(self, stale_history):
        session = _Session([_Row(id=1, probability=0.51, last_updated=NOW)])
        await tournaments._load_prices(session, [1], now=NOW)
        assert len(session.statements) == 1

    async def test_no_ids_asks_nothing(self, stale_history):
        session = _Session([])
        assert await tournaments._load_prices(session, [], now=NOW) == {}
        assert session.statements == []


class TestBothClocksAreActuallyWired:
    """Behaviour above proves the RULE; this proves the route still feeds it.

    A correct `_price_observed_at` that nothing calls with the touch stamp is
    the bug with a passing unit test, so these follow the wiring — and they name
    the columns rather than the SQL spelling, because the spelling has already
    moved once (LAT-P147 replaced a `GROUP BY` with a top-1 probe) and a guard
    pinned to it would red-light the next such fix.
    """

    def test_load_prices_selects_the_touch_stamp(self):
        source = inspect.getsource(tournaments._load_prices)
        assert "FuturesOutcome.last_updated" in source

    def test_load_prices_still_delegates_the_history_clock(self):
        source = inspect.getsource(tournaments._load_prices)
        assert "load_latest_observed_at" in source

        from app.utils import latest_observation

        loader = inspect.getsource(latest_observation.latest_observed_at_subquery)
        assert "FuturesOddsSnapshot.captured_at" in loader

    def test_observed_at_is_composed_and_not_either_column_raw(self):
        """The one line that could regress silently.

        Both clocks can be loaded and one of them quietly dropped at the point
        the dict is built; that is what the shipped bug looked like from here.
        """
        source = inspect.getsource(tournaments._load_prices)
        assert '"observed_at": _price_observed_at(' in source

    def test_the_touch_stamp_rides_the_existing_select(self):
        """No second round trip. `futures_market_snapshot.py` measured the
        alternative at 423 ms — 72% of that route's whole market_load stage —
        for the same column over the same ids."""
        source = inspect.getsource(tournaments._load_prices)
        before_execute = source.split("await session.execute")[0]
        after = source.split("await session.execute")[1]
        assert "FuturesOutcome.last_updated" in after.split(").all()")[0]
        assert "FuturesOutcome.last_updated" not in before_execute
        assert source.count("await session.execute") == 1
