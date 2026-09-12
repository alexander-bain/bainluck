"""#5612 — a late-listed Kalshi prop gets a genuinely PREGAME "opened at".

## the reader's defect, and why the existing rail cannot fix it

A prop whose market we first saw after first pitch shows a blank where "opened
at" belongs, or an "opened at" that is itself an in-play price. #5509 stopped
the page fabricating a pregame number from a late pin and falls back to
``futures_outcomes.opening_probability`` — but for this population that column
is empty or is itself in-play.

``_backfill_kalshi_price_history`` already fetches candles and already writes an
opening, so "widen its WHERE" is the fix everyone would write. It cannot work:
that rail writes ``batch_values[0]``, **the earliest candle in a 90-day
window**. For a market first listed mid-game the earliest candle IS mid-game.
The rail's question is "what is the oldest price you have?"; the reader's
question is "what was the price at first pitch?".

So the ship is a different question asked of the same endpoint — a window
**closed at first pitch** whose LAST candle is the pregame closing line — and
these tests are built to fail on the plausible wrong answers rather than to
confirm the right one:

* :class:`TestTheWindowClosesAtFirstPitch` — an implementation that filters
  after fetching, instead of bounding ``end_ts``, still passes a naive "is the
  price pregame" assertion. It fails here.
* :class:`TestTheLastPregameCandleWins` — taking ``candles[0]`` (the sibling
  rail's rule, and the one a copy-paste would inherit) is the single most
  likely wrong implementation. It is asserted against directly.
* :class:`TestNothingIsWrittenWithoutAnHonestPrice` — the withdrawal half. A
  blank is the honest answer for a market the venue itself first listed
  mid-game, and 0.50 from an untraded 0.00/1.00 book is the lie #5509 exists
  to refuse.
* :class:`TestTheOverwriteIsBoundedByProvenance` — this rail may overwrite a
  non-null opening, which none of its siblings may. The clause that makes that
  safe is re-stated inside the UPDATE, and a guard that only checked the SELECT
  would pass a source-scan while leaving the race open.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

import app.tasks.kalshi as kalshi_tasks
from app.tasks.kalshi import (
    KALSHI_PREGAME_OPENING_SOURCE,
    _backfill_kalshi_pregame_openings,
)

#: First pitch for every specimen below.
COMMENCE = datetime(2026, 9, 12, 17, 5, tzinfo=timezone.utc)
OUTCOME_ID = 4242
TICKER = "KXMLBPLAYER-26SEP12-JUDGE-H1"


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def _candle(dt: datetime, price: float) -> dict:
    """One already-normalised candle, in `get_market_candlesticks`'s shape."""
    return {"t": _ts(dt), "yes_price": price}


class _Row:
    """One row of the candidate SELECT."""

    def __init__(self, existing_opening=None, existing_opening_at=None,
                 commence_time=COMMENCE):
        self.outcome_id = OUTCOME_ID
        self.ticker = TICKER
        self.commence_time = commence_time
        self.existing_opening = existing_opening
        self.existing_opening_at = existing_opening_at


class _Result:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Records every statement, answers the SELECT, counts the UPDATE."""

    def __init__(self, rows, update_rowcount=1):
        self._rows = rows
        self._update_rowcount = update_rowcount
        self.executed: list[tuple[str, dict]] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append((sql, params or {}))
        if sql.lstrip().upper().startswith("SELECT") or "SELECT" in sql.split("\n")[1].upper():
            return _Result(rows=self._rows)
        return _Result(rowcount=self._update_rowcount)

    @property
    def updates(self) -> list[tuple[str, dict]]:
        return [(s, p) for s, p in self.executed if "UPDATE" in s.upper()]

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _session_cm(session):
    class _CM:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    return _CM()


class _FakeService:
    """A Kalshi client that records the window it was asked for."""

    def __init__(self, candles, ignore_end_ts=False):
        self._candles = candles
        self._ignore_end_ts = ignore_end_ts
        self.calls: list[dict] = []

    async def get_market_candlesticks(self, ticker, period_interval=60,
                                      start_ts=None, end_ts=None):
        self.calls.append(
            {"ticker": ticker, "period_interval": period_interval,
             "start_ts": start_ts, "end_ts": end_ts}
        )
        if self._ignore_end_ts:
            return list(self._candles)
        return [c for c in self._candles
                if start_ts <= c["t"] <= end_ts]

    async def close(self):
        return None


async def _run(rows, candles, *, ignore_end_ts=False, update_rowcount=1):
    session = _FakeSession(rows, update_rowcount=update_rowcount)
    service = _FakeService(candles, ignore_end_ts=ignore_end_ts)
    with patch.object(kalshi_tasks, "get_task_session", _session_cm(session)), \
            patch("app.services.kalshi_api.KalshiAPIService",
                  return_value=service):
        stats = await _backfill_kalshi_pregame_openings(limit=10)
    return stats, session, service


# --------------------------------------------------------------------------
# A market listed BEFORE first pitch, with a price that moves right up to it.
# --------------------------------------------------------------------------
PREGAME_CANDLES = [
    _candle(COMMENCE - timedelta(hours=6), 0.42),
    _candle(COMMENCE - timedelta(hours=2), 0.55),
    _candle(COMMENCE - timedelta(minutes=20), 0.61),   # ← the opening line
]
IN_PLAY_CANDLES = [
    _candle(COMMENCE + timedelta(minutes=45), 0.88),
    _candle(COMMENCE + timedelta(hours=2), 0.995),
]


class TestTheWindowClosesAtFirstPitch:
    """The bound is asked of the VENUE, not applied to its answer."""

    @pytest.mark.asyncio
    async def test_end_ts_is_first_pitch(self):
        _, _, service = await _run([_Row()], PREGAME_CANDLES)
        assert service.calls, "the venue was never asked"
        assert service.calls[0]["end_ts"] == _ts(COMMENCE)

    @pytest.mark.asyncio
    async def test_start_ts_precedes_end_ts_by_the_declared_lookback(self):
        _, _, service = await _run([_Row()], PREGAME_CANDLES)
        call = service.calls[0]
        assert call["start_ts"] == call["end_ts"] - (
            kalshi_tasks.PREGAME_LOOKBACK_DAYS * 86400
        )

    @pytest.mark.asyncio
    async def test_an_in_play_candle_is_refused_even_if_the_venue_ignores_the_bound(self):
        """The boundary is defended twice, and this is the second one.

        `end_ts` is a REQUEST. A venue that ignores it — or an endpoint whose
        range is inclusive of the period a timestamp closes — would hand back
        in-play candles, and the whole ship is the claim that the written
        timestamp precedes first pitch.
        """
        stats, session, _ = await _run(
            [_Row()], PREGAME_CANDLES + IN_PLAY_CANDLES, ignore_end_ts=True
        )
        assert stats["openings_written"] == 1
        (_, params), = session.updates
        assert params["ts"] <= COMMENCE
        assert float(params["prob"]) == pytest.approx(0.61)


class TestTheLastPregameCandleWins:
    """Not `candles[0]` — that is the sibling rail's rule and the wrong answer."""

    @pytest.mark.asyncio
    async def test_the_written_price_is_the_closing_line_not_the_listing_price(self):
        stats, session, _ = await _run([_Row()], PREGAME_CANDLES)
        assert stats["openings_written"] == 1
        (_, params), = session.updates
        assert float(params["prob"]) == pytest.approx(0.61), (
            "took a candle other than the last pregame one"
        )
        assert float(params["prob"]) != pytest.approx(0.42), (
            "took candles[0] — the earliest-candle rule this ship exists to replace"
        )

    @pytest.mark.asyncio
    async def test_the_written_timestamp_is_that_candles_own_time(self):
        _, session, _ = await _run([_Row()], PREGAME_CANDLES)
        (_, params), = session.updates
        assert params["ts"] == COMMENCE - timedelta(minutes=20)

    @pytest.mark.asyncio
    async def test_order_of_the_venue_response_does_not_decide_the_answer(self):
        """A venue is not contractually sorted; `max` by timestamp is."""
        _, session, _ = await _run([_Row()], list(reversed(PREGAME_CANDLES)))
        (_, params), = session.updates
        assert float(params["prob"]) == pytest.approx(0.61)

    @pytest.mark.asyncio
    async def test_the_opening_is_stamped_with_its_provenance(self):
        _, session, _ = await _run([_Row()], PREGAME_CANDLES)
        (_, params), = session.updates
        assert params["src"] == KALSHI_PREGAME_OPENING_SOURCE

    def test_the_provenance_constant_is_a_real_and_distinct_value(self):
        """Asserting `src == THE_CONSTANT` cannot see the constant go empty.

        That comparison is self-consistent: it passes for any value, including
        `""`, which would write a blank provenance and re-create the exact
        condition this ship was scoped against — production carried 45,842
        openings in one 7-day window with `opening_source IS NULL` and no way
        to attribute any of them to a writer. So the constant is pinned on its
        own terms, not against itself.
        """
        assert KALSHI_PREGAME_OPENING_SOURCE, "a blank provenance is no provenance"
        assert len(KALSHI_PREGAME_OPENING_SOURCE) <= 30, (
            "futures_outcomes.opening_source is String(30)"
        )
        # Distinct from the values already in the column, or a reader of the
        # column cannot tell this rail's openings from the ones it replaced.
        assert KALSHI_PREGAME_OPENING_SOURCE not in {
            "first_snapshot", "clob_history", "bid_ask_midpoint",
        }
        assert "kalshi" in KALSHI_PREGAME_OPENING_SOURCE
        assert "pregame" in KALSHI_PREGAME_OPENING_SOURCE


class TestNothingIsWrittenWithoutAnHonestPrice:
    """A blank is honest; a fabricated number is the defect."""

    @pytest.mark.asyncio
    async def test_a_market_the_venue_first_listed_mid_game_is_left_blank(self):
        stats, session, _ = await _run([_Row()], IN_PLAY_CANDLES)
        assert stats["openings_written"] == 0
        assert stats["unrecoverable"] == 1
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_no_candles_at_all_writes_nothing_and_is_counted(self):
        stats, session, _ = await _run([_Row()], [])
        assert stats["openings_written"] == 0
        assert stats["unrecoverable"] == 1
        assert stats["api_empty"] == 1
        assert session.updates == []

    @pytest.mark.asyncio
    async def test_an_untraded_empty_book_writes_nothing(self):
        """The 0.00/1.00 shell reaches this rail as `yes_price=None`.

        `candle_yes_price` (inside `get_market_candlesticks`) already returns
        None for that book rather than its fabricated 0.50 midpoint. This rail
        must carry that None through as a blank, not coerce it.
        """
        shell = [{"t": _ts(COMMENCE - timedelta(hours=1)), "yes_price": None}]
        stats, session, _ = await _run([_Row()], shell)
        assert stats["openings_written"] == 0
        assert session.updates == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("boundary", [0.0, 1.0])
    async def test_a_boundary_price_is_not_a_probability(self, boundary):
        candles = [_candle(COMMENCE - timedelta(hours=1), boundary)]
        stats, session, _ = await _run([_Row()], candles)
        assert stats["openings_written"] == 0
        assert session.updates == []

    def test_this_rail_states_no_second_price_policy(self):
        """`kalshi_candle_price` warns that a price policy existing twice drifts.

        The reduction is inherited through `get_market_candlesticks`; this rail
        must not re-derive a price from bid/ask/trade itself.
        """
        src = inspect.getsource(_backfill_kalshi_pregame_openings)
        for forbidden in ("yes_bid", "yes_ask", "close_dollars", "WIDE_SPREAD"):
            assert forbidden not in src, (
                f"{forbidden!r} — this rail is re-deriving a price instead of "
                "inheriting candle_yes_price's policy"
            )


class TestTheOverwriteIsBoundedByProvenance:
    """This rail may overwrite; the clause that makes that safe is in the WRITE."""

    @pytest.mark.asyncio
    async def test_an_in_play_opening_is_replaced_and_counted_as_an_overwrite(self):
        row = _Row(
            existing_opening=0.995,
            existing_opening_at=COMMENCE + timedelta(hours=2),
        )
        stats, session, _ = await _run([row], PREGAME_CANDLES)
        assert stats["openings_written"] == 1
        assert stats["openings_overwritten"] == 1
        (_, params), = session.updates
        assert float(params["prob"]) == pytest.approx(0.61)

    @pytest.mark.asyncio
    async def test_a_row_that_stopped_qualifying_is_not_counted_as_written(self):
        """The UPDATE's own clause is the arbiter, not the SELECT's snapshot.

        A postponement that re-stamps `commence_time` between the two makes a
        previously-in-play opening genuinely pregame. The UPDATE then matches
        nothing, and the rail must believe the database rather than its plan.
        """
        row = _Row(
            existing_opening=0.995,
            existing_opening_at=COMMENCE + timedelta(hours=2),
        )
        stats, _, _ = await _run([row], PREGAME_CANDLES, update_rowcount=0)
        assert stats["openings_written"] == 0
        assert stats["openings_overwritten"] == 0

    @pytest.mark.asyncio
    async def test_the_update_restates_the_clause_it_selected_on(self):
        _, session, _ = await _run([_Row()], PREGAME_CANDLES)
        (sql, _), = session.updates
        assert "opening_captured_at > e.commence_time" in sql, (
            "the UPDATE trusts the SELECT's ids — a concurrent write to "
            "commence_time or opening_captured_at would be clobbered"
        )
        assert "fo.opening_probability IS NULL" in sql

    @pytest.mark.asyncio
    async def test_a_fresh_write_is_not_counted_as_an_overwrite(self):
        stats, _, _ = await _run([_Row(existing_opening=None)], PREGAME_CANDLES)
        assert stats["openings_written"] == 1
        assert stats["openings_overwritten"] == 0


class TestTheCandidateScopeIsBoundedAtBothEnds:
    """gotcha #41: an expiring population needs a floor AND a sort."""

    def test_the_floor_is_the_shared_retention_constant(self):
        src = inspect.getsource(_backfill_kalshi_pregame_openings)
        assert "PROVABLY_PURGED_AGE_DAYS" in src
        assert "make_interval(days => :purge_days)" in src

    def test_the_sort_reaches_the_expiring_edge_first(self):
        src = inspect.getsource(_backfill_kalshi_pregame_openings)
        assert "ORDER BY e.commence_time ASC" in src

    def test_the_gap_is_only_claimed_after_first_pitch(self):
        """Before commence, an absent opening is an unpolled market, not a miss."""
        src = inspect.getsource(_backfill_kalshi_pregame_openings)
        assert "e.commence_time < NOW()" in src


class TestTheModeIsReachableAndIsolated:
    """The two calibration modes must not be able to fall into this one."""

    @pytest.mark.asyncio
    async def test_the_mode_string_dispatches_here(self):
        sentinel = {"mode": "pregame_gap", "sentinel": True}
        with patch.object(
            kalshi_tasks, "_backfill_kalshi_pregame_openings",
            AsyncMock(return_value=sentinel),
        ) as m:
            out = await kalshi_tasks._backfill_kalshi_price_history(
                limit=7, mode="pregame_gap"
            )
        assert out == sentinel
        m.assert_awaited_once_with(limit=7)

    def test_a_beat_actually_invokes_the_mode(self):
        """The whole ship is unreachable without this.

        The rail is a third `mode` on a task whose two beats both pass their
        own mode explicitly, and whose admin trigger dropped `mode` entirely.
        Adding the branch without a caller would pass every behavioural test
        above and change nothing a reader sees — the failure this repo calls
        an unguarded serving path, in reverse.
        """
        from app.tasks import celery_app

        entries = [
            v for v in celery_app.conf.beat_schedule.values()
            if v.get("task") == "app.tasks.backfill_kalshi_history"
            and (v.get("kwargs") or {}).get("mode") == "pregame_gap"
        ]
        assert entries, (
            "no beat passes mode='pregame_gap' — the rail can never run"
        )
        assert len(entries) == 1, "two beats would double-spend the API budget"
        # It must not land on the heavy lane: this task is deliberately in
        # _HEAVY_KEEP_ON_BACKGROUND, and a heavy-queued beat would both starve
        # the calibration lane and make the ship wait on an attended
        # bainluck-heavy redeploy it does not otherwise need.
        assert entries[0]["options"]["queue"] == "background"

    def test_the_admin_trigger_forwards_the_mode(self):
        """It hardcoded the default, so the endpoint could not reach this rail."""
        import inspect as _inspect

        from app.routes import admin_data_quality as adq

        src = _inspect.getsource(adq.trigger_backfill_kalshi_history)
        assert "mode=mode" in src, "the endpoint drops `mode` and runs the default"
        sig = _inspect.signature(adq.trigger_backfill_kalshi_history)
        assert "mode" in sig.parameters

    def test_this_task_is_not_heavy_so_the_ship_needs_no_heavy_release(self):
        """Notice 48 is per-TASK and asymmetric — this one is read, not assumed.

        #5612's own body says "this lands in a task, so it is a bainluck-heavy
        ship". That is wrong for THIS task: `backfill_kalshi_history` is listed
        in `_HEAVY_KEEP_ON_BACKGROUND`, deliberately kept off the heavy lane so
        the big backfills cannot fill its two slots. The ship therefore goes
        live on an ordinary main-app release, and this pins that so the claim
        in the cert body cannot quietly go stale.
        """
        from app.tasks import HEAVY_TASKS

        assert "app.tasks.backfill_kalshi_history" not in HEAVY_TASKS

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["resolved_zero", "open_sparse"])
    async def test_the_existing_modes_do_not_reach_this_rail(self, mode):
        with patch.object(
            kalshi_tasks, "_backfill_kalshi_pregame_openings",
            AsyncMock(return_value={"sentinel": True}),
        ) as m, patch.object(
            kalshi_tasks, "get_task_session", _session_cm(_FakeSession([]))
        ):
            await kalshi_tasks._backfill_kalshi_price_history(limit=1, mode=mode)
        m.assert_not_awaited()
