"""CAL-P086A item 1 — the Gamma recovery cursor must advance AFTER processing.

`C-WINNER-WRITER-1` (codex, 2026-08-21) verdict BLOCK, finding [P0]:

    max_id = max(row.id for row in markets)
    _rc.setex(_offset_key, 86400 * 7, str(max_id))
    # API processing starts below this point

The cursor moved past every SELECTED row before a single one had been checked.
Every way this task can stop early — a 429 storm tripping the circuit-breaker,
the caller's deadline, a transport error, a SIGKILL — therefore skipped the
whole page permanently. Codex's specimen: IDs 123 and 124 fed one per call with
a transient API failure each. Run 1 checked ZERO markets and moved the cursor to
123; run 2 selected 124, checked zero, moved it to 124. 123 comes back only
after a complete wraparound, and a continuously growing ID frontier — Polymarket
was creating 1,000-2,000 resolved markets a day — can prevent that wrap
indefinitely. That is how a four-times-a-day recovery task coexists with an
82.29% August Polymarket winner gap.

**Selection is not completion.** `limit=10_000` is how many rows the task was
allowed to LOOK at, and the cursor was being written from it as though it were
how many rows the task had FINISHED.

The fix copies the CLOB rail's already-shipped `_next_cursor_decision`
(`clob_resolve.py:453`, #989 item 1), transposed from its descending drain to
this ascending one: advance only past completed classifications, hold just
BELOW the lowest deferred id, and never wrap while work remains.

These tests EXECUTE the real function against recording doubles. They
deliberately do not use `inspect.getsource` — gotcha #152: a test that patches
the function under audit can only prove the stub, and the sibling failure here
is a test that only reads the function's text can only prove the text. Codex's
own coverage note on this file records that the three existing settlement-sync
tests "only inspect source strings; none executes the status-without-winner
boundary."
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

import app.tasks.backfill_winners as bw
import app.tasks.redis_state as redis_state
import app.services.polymarket_api as poly_api_mod


OFFSET_KEY = "bainluck:pm_winner_backfill_offset"


class _Row:
    """One row as the stuck-market SELECT returns it."""

    def __init__(self, id, external_id, group_type=None, poly_event_id=None):
        self.id = id
        self.external_id = external_id
        self.group_type = group_type
        self.poly_event_id = poly_event_id


class _Result:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return self._rows


class _FakeRedis:
    """Records what the task writes, so the cursor is observable."""

    def __init__(self, initial=None):
        self.store = dict(initial or {})
        self.sets = {}
        self.setex_calls = []
        self.deletes = []

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.setex_calls.append((key, value))
        self.store[key] = str(value)

    def delete(self, key):
        self.deletes.append(key)
        return 1 if self.store.pop(key, None) is not None else 0

    def sadd(self, key, *vals):
        self.sets.setdefault(key, set()).update(vals)

    def smembers(self, key):
        return set(self.sets.get(key, set()))

    def expire(self, key, ttl):
        return True

    # what the task's cursor currently reads as
    def cursor(self):
        v = self.store.get(OFFSET_KEY)
        return int(v) if v is not None else None


def _install(monkeypatch, universe, rc, *, raises=None, market_data=None):
    """Drive the REAL `_backfill_polymarket_winners_from_api`.

    `universe` is every eligible row in id order; the fake SELECT honours the
    task's own `last_id`/`limit` binds, so the cursor genuinely determines what
    the next run sees — which is the whole property under test.
    """
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: rc)

    seen_selects = []

    async def _execute(stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        if "FROM futures_markets fm" in sql:
            params = params or {}
            last_id = params.get("last_id") or 0
            limit = params.get("limit") or 0
            rows = [r for r in universe if r.id > last_id][:limit]
            seen_selects.append([r.id for r in rows])
            return _Result(rows)
        return MagicMock(rowcount=0)

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock()

    class _CM:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())

    class _Service:
        def __init__(self, *a, **k):
            self.condition_calls = []

        async def get_market_by_condition(self, cid):
            self.condition_calls.append(cid)
            if raises is not None:
                raise raises
            return (market_data or {}).get(cid)

        async def get_event_by_id(self, eid):
            return None

        async def close(self):
            return None

    monkeypatch.setattr(poly_api_mod, "PolymarketAPIService", _Service)
    return seen_selects


# ---------------------------------------------------------------------------
# The pure decision, mirroring clob_resolve._next_cursor_decision
# ---------------------------------------------------------------------------


class TestNextGammaCursorDecision:
    """The ascending transposition of the CLOB rail's shipped rule."""

    def test_nothing_selected_is_a_noop(self):
        assert bw._next_gamma_cursor_decision(
            selected_ids=[], completed_ids=[], limit=10
        ) == ("noop", None)

    def test_a_deferred_row_holds_the_cursor_just_below_it(self):
        # 123 deferred, 124 done. The cursor must land at 122 so that the next
        # run's `fm.id > :last_id` re-selects 123. Re-doing 124 is harmless: the
        # UPDATE is guarded by `resolution_source NOT IN (authoritative)`.
        assert bw._next_gamma_cursor_decision(
            selected_ids=[123, 124], completed_ids=[124], limit=10
        ) == ("set", 122)

    def test_the_lowest_deferred_id_wins_not_the_highest(self):
        # Holding above the highest failure would skip the lower ones — the
        # exact defect, one row narrower.
        assert bw._next_gamma_cursor_decision(
            selected_ids=[10, 20, 30], completed_ids=[20], limit=10
        ) == ("set", 9)

    def test_a_full_clean_page_advances_to_the_last_completed_id(self):
        assert bw._next_gamma_cursor_decision(
            selected_ids=[7, 8, 9], completed_ids=[7, 8, 9], limit=3
        ) == ("set", 9)

    def test_a_short_clean_page_wraps(self):
        # Fully drained: nothing above, nothing deferred. Reset to the start.
        assert bw._next_gamma_cursor_decision(
            selected_ids=[7, 8], completed_ids=[7, 8], limit=100
        ) == ("delete", None)

    def test_a_short_page_with_a_deferral_never_wraps(self):
        # "Never wraparound while errors remain" — the CLOB rule's load-bearing
        # half. A wrap here would declare the backlog drained while holding a
        # row it failed to check.
        assert bw._next_gamma_cursor_decision(
            selected_ids=[7, 8], completed_ids=[7], limit=100
        ) == ("set", 7)

    def test_the_cursor_never_moves_backwards_past_its_own_page(self):
        # Every selected id is > the previous cursor, so min(deferred) - 1 is
        # never below it. With the first row deferred the cursor is unchanged,
        # which is a stall, not a rewind.
        op, value = bw._next_gamma_cursor_decision(
            selected_ids=[501, 502], completed_ids=[], limit=10
        )
        assert (op, value) == ("set", 500)


# ---------------------------------------------------------------------------
# The executing specimen — codex's 123/124, run against the real function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTransientFailureIsRetriedNotSkipped:
    async def test_a_transient_failure_does_not_advance_the_cursor(
        self, monkeypatch
    ):
        universe = [_Row(123, "555123"), _Row(124, "555124")]
        rc = _FakeRedis()
        _install(monkeypatch, universe, rc, raises=RuntimeError("connection reset"))

        stats = await bw._backfill_polymarket_winners_from_api(limit=1)

        # Nothing was classified, so nothing may be skipped.
        #
        # The invariant is NOT "the cursor is unchanged" — it is "the cursor
        # never passes a row this run did not finish". Landing at 122 with 123
        # deferred satisfies it and is what the shipped rule does: the selected
        # ids are the LOWEST eligible ids above the old cursor, so there is
        # nothing between the old cursor and 122 left to lose.
        assert stats["markets_checked"] == 0, stats
        assert rc.cursor() is None or rc.cursor() < 123, (
            f"cursor moved to {rc.cursor()} after checking zero markets — it is "
            f"at or past deferred id 123; setex calls={rc.setex_calls}"
        )

    async def test_the_failed_row_is_reselected_on_the_next_run(self, monkeypatch):
        """Codex's specimen end to end: run 1 fails, run 2 must see 123 AGAIN.

        Before the fix run 2 selected 124 and 123 was gone until a full wrap.
        """
        universe = [_Row(123, "555123"), _Row(124, "555124")]
        rc = _FakeRedis()
        selects = _install(
            monkeypatch, universe, rc, raises=RuntimeError("connection reset")
        )

        await bw._backfill_polymarket_winners_from_api(limit=1)
        await bw._backfill_polymarket_winners_from_api(limit=1)

        assert selects[0] == [123]
        assert selects[1] == [123], (
            f"run 2 selected {selects[1]} — id 123 was skipped by a cursor that "
            f"advanced before the work; setex calls={rc.setex_calls}"
        )

    async def test_a_clean_run_still_makes_progress(self, monkeypatch):
        """The falsifier. A cursor that never advances is not a fix, it is a
        stall — and it would pass every test above."""
        universe = [_Row(200, "555200"), _Row(201, "555201")]
        rc = _FakeRedis()
        selects = _install(
            monkeypatch,
            universe,
            rc,
            market_data={
                "555200": {"outcomePrices": ["0.99", "0.01"]},
                "555201": {"outcomePrices": ["0.99", "0.01"]},
            },
        )

        await bw._backfill_polymarket_winners_from_api(limit=1)
        assert rc.cursor() == 200, rc.setex_calls

        await bw._backfill_polymarket_winners_from_api(limit=1)
        assert selects[1] == [201], selects

    async def test_the_run_reports_selected_completed_and_deferred_separately(
        self, monkeypatch
    ):
        """Codex: "Report selected, attempted, completed, deferred, and
        cursor-held counts separately." A single `markets_checked` cannot
        distinguish a drained page from a skipped one (gotcha #53)."""
        universe = [_Row(300, "555300"), _Row(301, "555301")]
        rc = _FakeRedis()
        _install(monkeypatch, universe, rc, raises=RuntimeError("connection reset"))

        stats = await bw._backfill_polymarket_winners_from_api(limit=2)

        assert stats["selected"] == 2, stats
        assert stats["completed"] == 0, stats
        assert stats["deferred"] == 2, stats
        assert stats["cursor_held"] is True, stats
