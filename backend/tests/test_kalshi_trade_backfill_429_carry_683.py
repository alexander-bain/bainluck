"""#683 — a rate-limited Kalshi trade read is owed a retry, not skipped behind the cursor.

Production run 2026-10-12 11:15–11:19Z: 500 candidates, 475 API-empty, 25 HTTP
429, 0 pregame snapshots, 500 expiring soon. Before this fix the task saved the
Redis cursor at the HIGHEST of all 500 candidates before any HTTP, and a 429
slept a fixed 5 s and moved on. Those 25 outcomes were then behind the cursor
until the next wrap, inside a window Kalshi purges at 86 days.

Pinned here, against the real function with fakes only at the I/O edges
(session, Redis, Kalshi client, clock):
  * an interleaved 429 / success / empty run counts each outcome once and
    honestly — a 429 is never fetched, empty or no-pregame;
  * ``Retry-After`` is honored (both forms) and charged to the budget; a cooldown
    the run cannot wait out in place carries the candidate and ENDS the run, so
    nothing is re-asked before the provider's cooldown is over;
  * a still-refused candidate is carried and asked FIRST next run, through the
    same in-window predicate (an aged-out or tagged one does not come back);
  * the cursor never passes a candidate the run did not attempt (budget stop);
  * zero-yield accounting: 475-empty + 25-429 is still a FAILED run;
  * a full carry never drops an owed id: the run stops with the cursor before it;
  * any final 429 records the cooldown shared by both callers and ends the HTTP
    pass: no request for ANY outcome, in this run or the next, before it expires.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import patch

import httpx
import pytest

from app.tasks import kalshi
from app.tasks.kalshi import (
    _TRADE_BACKFILL_COOLDOWN_KEY,
    _TRADE_429_DEFAULT_WAIT_S,
    _TRADE_429_MAX_WAIT_S,
    _TRADE_BACKFILL_RETRY_KEY,
    _backfill_trade_history,
    _kalshi_trade_429_wait,
)

CURSOR_KEY = "bainluck:trade_backfill_cursor"
NOW = datetime.now(timezone.utc)
COMMENCE = NOW - timedelta(days=10)
SETTLED = NOW - timedelta(days=9)
PREGAME_TRADE = {
    "yes_price_dollars": "0.42",
    "created_time": (COMMENCE - timedelta(hours=2)).isoformat(),
}
POSTGAME_TRADE = {
    "yes_price_dollars": "0.80",
    "created_time": (COMMENCE + timedelta(hours=1)).isoformat(),
}


def _ticker(oid: int) -> str:
    return f"KXTEST-26OCT02-T{oid}"


def _http_429(retry_after: str | None = None) -> httpx.HTTPStatusError:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    req = httpx.Request("GET", "https://kalshi.test/markets/trades")
    resp = httpx.Response(429, headers=headers, request=req)
    return httpx.HTTPStatusError("Client error '429 Too Many Requests'", request=req, response=resp)


def _http_500() -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://kalshi.test/markets/trades")
    resp = httpx.Response(500, request=req)
    return httpx.HTTPStatusError("Server error '500'", request=req, response=resp)


class FakeRedis:
    def __init__(self, data: dict | None = None):
        self.data = dict(data or {})

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, _ttl, value):
        self.data[key] = value

    def delete(self, key):
        self.data.pop(key, None)

    def carry(self) -> list[int] | None:
        raw = self.data.get(_TRADE_BACKFILL_RETRY_KEY)
        return None if raw is None else json.loads(raw)

    def cooldown_until(self) -> float | None:
        raw = self.data.get(_TRADE_BACKFILL_COOLDOWN_KEY)
        return None if raw is None else float(raw)

    def cursor(self) -> int | None:
        raw = self.data.get(CURSOR_KEY)
        return None if raw is None else int(raw)


class FakeDB:
    """Answers the two candidate SELECTs from an eligible population; logs writes."""

    def __init__(self, eligible: list[int]):
        self.eligible = sorted(eligible)
        self.selects: list[dict] = []
        self.snapshot_oids: list[int] = []
        self.no_pregame_ids: list[int] = []
        self.null_cal_ids: list[int] = []

    def _row(self, oid):
        return (oid, _ticker(oid), COMMENCE, SETTLED)

    @asynccontextmanager
    async def session(self):
        db = self

        class _Result:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class _Session:
            async def execute(self, stmt, params=None):
                sql = str(stmt)
                params = params or {}
                if "SELECT fo.id, fo.external_id" in sql:
                    db.selects.append(dict(params))
                    if "retry_ids" in params:
                        ids = [i for i in db.eligible if i in set(params["retry_ids"])]
                    else:
                        ids = [i for i in db.eligible if i > params["last_id"]]
                    return _Result([db._row(i) for i in ids[: params["lim"]]])
                if "INSERT INTO futures_odds_snapshots" in sql:
                    db.snapshot_oids.append(params["oid"])
                elif "SET resolution_source = 'no_pregame_trading'" in sql:
                    db.no_pregame_ids.extend(params["ids"])
                elif "calibration_probability = NULL" in sql:
                    db.null_cal_ids.extend(params["ids"])
                return _Result([])

            async def commit(self):
                return None

        yield _Session()


WALL0 = 1_800_000_000.0


class FakeClock:
    """One clock: monotonic for the run budget, wall for the shared cooldown."""

    def __init__(self):
        self.t = 1000.0
        self.sleeps: list[float] = []
        self.call_walls: list[tuple[int, float]] = []

    def monotonic(self):
        return self.t

    def wall(self):
        return WALL0 + (self.t - 1000.0)

    async def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def _make_service(script: dict, calls: list, redis: FakeRedis, cursor_at_first_call: list,
                  clock: FakeClock, per_call_cost: float = 0.0):
    """``script[oid]`` is a list consumed per request: an exception, or a trade list."""

    class _Svc:
        async def get_market_trades(self, ticker, limit=100, cursor=None):
            if not cursor_at_first_call:
                cursor_at_first_call.append(redis.cursor())
            oid = int(ticker.rsplit("T", 1)[1])
            calls.append(oid)
            clock.call_walls.append((oid, clock.wall()))
            clock.t += per_call_cost
            step = script[oid].pop(0) if len(script[oid]) > 1 else script[oid][0]
            if isinstance(step, BaseException):
                raise step
            return list(step), None

        async def close(self):
            return None

    return _Svc


async def _run(db: FakeDB, redis: FakeRedis, script: dict, *, limit=500, deadline=None,
               clock: FakeClock | None = None, per_call_cost: float = 0.0):
    clock = clock or FakeClock()
    calls: list[int] = []
    first_cursor: list = []
    svc_cls = _make_service(script, calls, redis, first_cursor, clock, per_call_cost)
    with patch.object(kalshi, "get_task_session", db.session), \
            patch("app.tasks.redis_state.get_redis_client", lambda: redis), \
            patch("app.services.kalshi_api.KalshiAPIService", svc_cls), \
            patch.object(asyncio, "sleep", clock.sleep), \
            patch.object(time, "monotonic", clock.monotonic), \
            patch.object(kalshi, "_trade_cooldown_clock", clock.wall):
        stats = await _backfill_trade_history(limit=limit, deadline=deadline)
    return stats, calls, first_cursor, clock


# ---------------------------------------------------------------------------
# Retry-After parsing
# ---------------------------------------------------------------------------


class TestRetryAfter:
    def test_delta_seconds_is_honored(self):
        assert _kalshi_trade_429_wait(_http_429("2")) == 2.0

    def test_http_date_is_honored(self):
        when = datetime.now(timezone.utc) + timedelta(seconds=12)
        wait = _kalshi_trade_429_wait(_http_429(format_datetime(when, usegmt=True)))
        assert 9.0 <= wait <= 12.0

    def test_absent_header_keeps_the_old_fixed_wait(self):
        assert _kalshi_trade_429_wait(_http_429()) == _TRADE_429_DEFAULT_WAIT_S

    @pytest.mark.parametrize("raw", ["soon", "nan", "inf"])
    def test_garbage_or_non_finite_header_falls_back_to_the_fixed_wait(self, raw):
        assert _kalshi_trade_429_wait(_http_429(raw)) == _TRADE_429_DEFAULT_WAIT_S

    def test_long_cooldown_is_returned_unclamped_and_past_dates_are_zero(self):
        """Root HOLD on b9ffe0d023: clamping 120 to 30 re-asked 90 s early."""
        assert _kalshi_trade_429_wait(_http_429("120")) == 120.0
        assert _kalshi_trade_429_wait(_http_429("86400")) == 86400.0
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert _kalshi_trade_429_wait(_http_429(format_datetime(past, usegmt=True))) == 0.0

    def test_non_429_status_is_not_a_rate_limit(self):
        assert _kalshi_trade_429_wait(_http_500()) is None

    def test_responseless_error_keeps_the_old_string_test(self):
        assert _kalshi_trade_429_wait(RuntimeError("HTTP 429 from venue")) == _TRADE_429_DEFAULT_WAIT_S
        assert _kalshi_trade_429_wait(RuntimeError("connection reset")) is None


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


class TestInterleavedRun:
    """429 / success / empty / sibling error in one pass, each counted once.

    The double 429 is LAST among the asked ids: any final 429 ends the HTTP
    pass (root, 16:35Z), so 8 behind it must never be asked inside the cooldown.
    """

    def _script(self):
        return {
            1: [[PREGAME_TRADE]],                    # success with a pregame trade
            2: [_http_429("2"), [PREGAME_TRADE]],    # 429, waits Retry-After, succeeds
            3: [[]],                                 # venue-empty
            4: [[POSTGAME_TRADE]],                   # traded, but only after start
            5: [_http_500()],                        # unrelated sibling error
            6: [[]],
            7: [_http_429("1"), _http_429("1")],     # still refused: carried, pass ends
            8: [[PREGAME_TRADE]],                    # must not be asked this run
        }

    @pytest.mark.asyncio
    async def test_accounting(self):
        db, redis = FakeDB(list(range(1, 9))), FakeRedis()
        stats, calls, _, clock = await _run(db, redis, self._script())

        assert stats["candidates"] == 8
        assert stats["fetched"] == 5          # 1, 2, 3, 4, 6 — never 5 or 7
        assert stats["pregame_snaps"] == 2    # 1 and 2
        assert stats["api_empty"] == 2        # 3 and 6 — the 429 is NOT empty
        assert stats["no_pregame"] == 1       # 4 only — the 429 is NOT no-pregame
        assert stats["rate_limited"] == 1
        assert stats["rate_limit_waits"] == 2
        assert len(stats["errors"]) == 2      # the carried 429 and the 500
        assert stats["terminal"] == "partial"

        # The provider's Retry-After was what we waited, not a hardcoded 5 s.
        assert clock.sleeps == [2.0, 1.0]
        assert calls == [1, 2, 2, 3, 4, 5, 6, 7, 7]
        assert 8 not in calls

        assert sorted(db.snapshot_oids) == [1, 2]
        assert db.no_pregame_ids == [4]
        assert 7 not in db.no_pregame_ids and 7 not in db.null_cal_ids

    @pytest.mark.asyncio
    async def test_cursor_moves_after_http_and_the_429_is_carried(self):
        db, redis = FakeDB(list(range(1, 9))), FakeRedis({CURSOR_KEY: "0"})
        _, _, first_cursor, clock = await _run(db, redis, self._script())

        # Pre-fix the cursor was already at the batch maximum before the first
        # request; now it has not moved when the first request goes out.
        assert first_cursor == [0]
        assert redis.cursor() == 7            # 8 is still ahead: never passed
        assert redis.carry() == [7]
        assert 5 not in redis.carry()         # a non-429 error is not carried
        assert redis.cooldown_until() == pytest.approx(clock.wall() + 1.0)


class TestResume:
    @pytest.mark.asyncio
    async def test_carried_429_is_asked_first_next_run_and_cleared_on_answer(self):
        db = FakeDB([4, 8, 9])
        redis = FakeRedis({CURSOR_KEY: "7", _TRADE_BACKFILL_RETRY_KEY: json.dumps([4])})
        stats, calls, _, _ = await _run(db, redis, {4: [[PREGAME_TRADE]], 8: [[]], 9: [[]]})

        assert calls == [4, 8, 9]             # behind the cursor, yet asked first
        assert stats["retry_carried"] == 1
        assert stats["pregame_snaps"] == 1 and db.snapshot_oids == [4]
        assert redis.carry() is None          # answered: nothing owed
        assert redis.cursor() == 9

    @pytest.mark.asyncio
    async def test_carried_id_goes_through_the_same_in_window_predicate(self):
        """Aged past 86 days or tagged since: it is not a candidate, so not asked."""
        db = FakeDB([8])                      # 4 no longer passes the predicate
        redis = FakeRedis({CURSOR_KEY: "7", _TRADE_BACKFILL_RETRY_KEY: json.dumps([4])})
        stats, calls, _, _ = await _run(db, redis, {8: [[]]})

        retry_select = [s for s in db.selects if "retry_ids" in s]
        assert retry_select and retry_select[0]["retry_ids"] == [4]
        assert retry_select[0]["purge_days"] == kalshi_retention_days()
        assert calls == [8]
        assert stats["retry_carried"] == 0
        assert redis.carry() is None

    @pytest.mark.asyncio
    async def test_still_refused_on_the_retry_stays_carried_and_the_walk_waits(self):
        db = FakeDB([4, 8])
        redis = FakeRedis({CURSOR_KEY: "7", _TRADE_BACKFILL_RETRY_KEY: json.dumps([4])})
        stats, calls, _, _ = await _run(db, redis, {4: [_http_429("1")], 8: [[]]})
        assert stats["rate_limited"] == 1
        assert calls == [4, 4]                # waited 1 s once, refused again
        assert redis.carry() == [4]
        assert redis.cursor() == 7            # 8 not asked inside the cooldown

    @pytest.mark.asyncio
    async def test_carry_takes_at_most_half_the_batch_and_keeps_the_rest(self):
        carried = list(range(1, 11))
        db = FakeDB(carried + [20, 21, 22])
        redis = FakeRedis({CURSOR_KEY: "15", _TRADE_BACKFILL_RETRY_KEY: json.dumps(carried)})
        script = {i: [[]] for i in carried + [20, 21, 22]}
        stats, calls, _, _ = await _run(db, redis, script, limit=4)

        assert calls == [1, 2, 20, 21]        # 2 carried + 2 from the cursor walk
        assert stats["retry_carried"] == 2
        assert redis.carry() == list(range(3, 11))
        assert redis.cursor() == 21

    @pytest.mark.asyncio
    async def test_a_page_of_only_carried_ids_does_not_wrap_the_cursor(self):
        """After a wrap a carried id can sit ahead of the cursor too.

        limit=2 asks one carried id (5) and leaves one slot for the walk, whose
        single row is that same 5. The walk has NOT ended (6 is still ahead), so
        the cursor must hold at 4 rather than reset and re-walk the window.
        """
        db = FakeDB([5, 6])
        redis = FakeRedis({CURSOR_KEY: "4", _TRADE_BACKFILL_RETRY_KEY: json.dumps([5])})
        _, calls, _, _ = await _run(db, redis, {5: [[]], 6: [[]]}, limit=2)
        assert calls == [5]
        assert redis.cursor() == 4

    @pytest.mark.asyncio
    async def test_drained_window_wraps_and_is_complete(self):
        db, redis = FakeDB([]), FakeRedis({CURSOR_KEY: "99"})
        stats, calls, _, _ = await _run(db, redis, {})
        assert calls == [] and stats["terminal"] == "complete"
        assert redis.cursor() is None and redis.carry() is None

    @pytest.mark.asyncio
    async def test_both_callers_limits_keep_the_whole_carry(self):
        """The 500-limit task writes a carry the 100-limit Phase 0 then reads."""
        carried = list(range(1, 121))
        db = FakeDB(carried)
        redis = FakeRedis({CURSOR_KEY: "500", _TRADE_BACKFILL_RETRY_KEY: json.dumps(carried)})
        _, calls, _, _ = await _run(db, redis, {i: [[]] for i in carried}, limit=100)
        assert calls == list(range(1, 51))    # half of 100 asked
        assert redis.carry() == list(range(51, 121))  # all 70 others still owed


def kalshi_retention_days() -> int:
    from app.utils.kalshi_retention import PROVABLY_PURGED_AGE_DAYS

    return PROVABLY_PURGED_AGE_DAYS


class TestBudgetStop:
    @pytest.mark.asyncio
    async def test_cursor_never_passes_an_unattempted_candidate(self):
        clock = FakeClock()
        db, redis = FakeDB([1, 2, 3, 4, 5, 6]), FakeRedis({CURSOR_KEY: "0"})
        script = {i: [[]] for i in range(1, 7)}
        # Each request costs 10 s; the caller's deadline allows only two.
        stats, calls, _, _ = await _run(
            db, redis, script, deadline=clock.t + 15, clock=clock, per_call_cost=10.0
        )
        assert calls == [1, 2]
        assert redis.cursor() == 2            # pre-fix: 6, stranding 3..6
        assert stats["fetched"] == 2 and stats["terminal"] == "failed"

    @pytest.mark.asyncio
    async def test_retry_after_past_the_budget_is_carried_and_the_run_stops(self):
        clock = FakeClock()
        db, redis = FakeDB([1, 2]), FakeRedis()
        stats, calls, _, _ = await _run(
            db, redis, {1: [_http_429("20")], 2: [[PREGAME_TRADE]]},
            deadline=clock.t + 10, clock=clock,
        )
        assert stats["rate_limit_waits"] == 0 and clock.sleeps == []
        assert calls == [1]                   # nobody asked inside the cooldown
        assert redis.carry() == [1]
        assert redis.cursor() == 1            # 2 stays ahead of the cursor
        assert stats["stopped_on_cooldown_s"] == 20.0

    @pytest.mark.asyncio
    async def test_unattempted_carried_ids_stay_carried(self):
        clock = FakeClock()
        db = FakeDB([1, 2, 3, 9])
        redis = FakeRedis({CURSOR_KEY: "8", _TRADE_BACKFILL_RETRY_KEY: json.dumps([1, 2, 3])})
        await _run(db, redis, {i: [[]] for i in (1, 2, 3, 9)},
                   deadline=clock.t + 5, clock=clock, per_call_cost=10.0)
        assert redis.carry() == [2, 3]        # 1 attempted; 2 and 3 never reached
        assert redis.cursor() == 8            # the walk never started


class TestProviderCooldown:
    """The exact controls from root's HOLD on b9ffe0d023 and its 16:35Z extension."""

    @pytest.mark.asyncio
    async def test_a_120_second_cooldown_blocks_every_sibling_request(self):
        db, redis = FakeDB([1, 2, 3]), FakeRedis({CURSOR_KEY: "0"})
        script = {1: [_http_429("120"), [PREGAME_TRADE]], 2: [[PREGAME_TRADE]], 3: [[]]}
        stats, calls, _, clock = await _run(db, redis, script)

        assert calls == [1]                   # no 2nd trade request of ANY outcome
        assert clock.sleeps == []             # pre-repair: slept 30, then re-asked
        assert stats["rate_limit_waits"] == 0
        assert stats["rate_limited"] == 1
        assert stats["fetched"] == 0 and stats["api_empty"] == 0
        assert stats["stopped_on_cooldown_s"] == 120.0
        assert redis.carry() == [1]           # owed to the next run
        assert redis.cursor() == 1            # 2 and 3 untouched, still ahead
        assert redis.cooldown_until() == pytest.approx(WALL0 + 120.0)
        assert stats["terminal"] != "complete"

    @pytest.mark.asyncio
    async def test_a_second_429_after_a_short_wait_also_ends_the_pass(self):
        """First 429 says 1 s, the retry's 429 says 5 s: no sibling before +5 s."""
        db, redis = FakeDB([1, 2]), FakeRedis()
        script = {1: [_http_429("1"), _http_429("5")], 2: [[PREGAME_TRADE]]}
        stats, calls, _, clock = await _run(db, redis, script)

        assert calls == [1, 1]
        assert clock.sleeps == [1.0]
        assert stats["rate_limited"] == 1 and stats["stopped_on_cooldown_s"] == 5.0
        assert redis.carry() == [1] and redis.cursor() == 1
        assert redis.cooldown_until() == pytest.approx(clock.wall() + 5.0)

    @pytest.mark.asyncio
    async def test_a_short_cooldown_at_the_boundary_is_waited_in_place(self):
        db, redis = FakeDB([1, 2]), FakeRedis()
        script = {
            1: [_http_429(str(int(_TRADE_429_MAX_WAIT_S))), [PREGAME_TRADE]],
            2: [[]],
        }
        stats, calls, _, clock = await _run(db, redis, script)
        assert clock.sleeps[0] == _TRADE_429_MAX_WAIT_S
        assert calls == [1, 1, 2]
        # The re-ask went out no earlier than the provider's deadline.
        assert clock.call_walls[1][1] >= clock.call_walls[0][1] + _TRADE_429_MAX_WAIT_S
        assert stats["rate_limit_waits"] == 1 and stats["rate_limited"] == 0
        assert stats["pregame_snaps"] == 1
        assert redis.carry() is None and redis.cursor() == 2
        assert redis.cooldown_until() is None

    @pytest.mark.asyncio
    async def test_a_carried_id_refused_with_a_long_cooldown_stays_carried(self):
        db = FakeDB([4, 8])
        redis = FakeRedis({CURSOR_KEY: "7", _TRADE_BACKFILL_RETRY_KEY: json.dumps([4])})
        _, calls, _, _ = await _run(db, redis, {4: [_http_429("120")], 8: [[]]})
        assert calls == [4]
        assert redis.carry() == [4] and redis.cursor() == 7

    @pytest.mark.asyncio
    async def test_the_cooldown_holds_across_invocations_of_either_caller(self):
        """Run 1 gets Retry-After 86400. A run before expiry sends nothing at all."""
        clock = FakeClock()
        db, redis = FakeDB([1, 2]), FakeRedis({CURSOR_KEY: "0"})
        script = {1: [_http_429("86400"), [PREGAME_TRADE]], 2: [[]]}

        _, calls1, _, _ = await _run(db, redis, script, clock=clock)
        assert calls1 == [1]
        state = (redis.cursor(), redis.carry())

        # Six hours later (the next `backfill_kalshi_trades` beat), and the
        # backfill_winners Phase 0 shape (limit=100, deadline) right after it.
        clock.t += 6 * 3600
        stats2, calls2, _, _ = await _run(db, redis, script, clock=clock)
        stats3, calls3, _, _ = await _run(
            db, redis, script, limit=100, deadline=clock.t + 600, clock=clock
        )
        assert calls2 == [] and calls3 == []
        assert stats2["terminal"] == stats3["terminal"] == "partial"
        assert stats2["cooldown_remaining_s"] == pytest.approx(86400 - 6 * 3600, abs=1)
        assert (redis.cursor(), redis.carry()) == state   # untouched

        # After expiry the owed candidate is asked first and answered.
        clock.t += 86400
        stats4, calls4, _, _ = await _run(db, redis, script, clock=clock)
        assert calls4 == [1, 2]
        assert stats4["pregame_snaps"] == 1
        assert redis.carry() is None and redis.cursor() == 2


class TestCarryCapacity:
    @pytest.mark.asyncio
    async def test_a_full_carry_stops_the_run_instead_of_dropping_an_owed_id(self):
        """Start already full: 51 is owed and not asked (limit=2 asks only 50)."""
        db = FakeDB([50, 51, 61, 62])
        redis = FakeRedis({CURSOR_KEY: "60", _TRADE_BACKFILL_RETRY_KEY: json.dumps([50, 51])})
        script = {50: [[]], 51: [[]], 61: [_http_429("120")], 62: [[]]}
        with patch.object(kalshi, "_TRADE_BACKFILL_RETRY_MAX", 1):
            stats, calls, _, _ = await _run(db, redis, script, limit=2)
        assert calls == [50, 61]
        assert stats["retry_carry_full"] is True
        assert redis.carry() == [51]          # nothing owed was dropped
        assert redis.cursor() == 60           # held BEFORE 61: 61 is still owed


class TestZeroYieldAccounting:
    @pytest.mark.asyncio
    async def test_the_measured_production_shape_is_still_a_failure(self):
        """475 empty + 25 rate-limited, 0 snapshots: the 11:19Z run, scaled."""
        empties = list(range(1, 20))
        limited = [20]
        db, redis = FakeDB(empties + limited), FakeRedis()
        script = {i: [[]] for i in empties}
        script[20] = [_http_429()]
        stats, _, _, _ = await _run(db, redis, script)
        assert stats["api_empty"] == 19 and stats["fetched"] == 19
        assert stats["rate_limited"] == 1 and stats["pregame_snaps"] == 0
        assert stats["terminal"] == "failed"

    @pytest.mark.asyncio
    async def test_a_rate_limited_run_is_never_green_and_the_sibling_stays_owed(self):
        db, redis = FakeDB([1, 2]), FakeRedis({CURSOR_KEY: "0"})
        stats, calls, _, clock = await _run(db, redis, {1: [_http_429()], 2: [_http_429()]})
        assert calls == [1, 1]                # default 5 s wait once, then refused
        assert clock.sleeps == [_TRADE_429_DEFAULT_WAIT_S]
        assert stats["fetched"] == 0 and stats["api_empty"] == 0
        assert stats["rate_limited"] == 1
        assert stats["terminal"] != "complete"
        assert redis.carry() == [1]
        assert redis.cursor() == 1            # 2 untouched, still ahead of the cursor
