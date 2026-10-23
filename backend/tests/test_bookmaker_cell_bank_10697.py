"""#10697 — the bookmaker sweep keeps the cells it landed, so a slow walk converges.

From 10/08 21:16Z every `precompute_bookmaker_calibration` run stopped at its
1,620 s traversal budget with 92 chunks landed, threw them all away, and started
the next run at `americanfootball_*` again. No run could finish, the key's 24 h
TTL lapsed, and `/api/calibration` froze for 33 h behind
`bookmaker_curve_key_absent`. These tests drive the REAL writer against a
stubbed session, a fake clock that advances only per chunk query, and an
in-memory Redis that keeps the bank between runs.
"""
from __future__ import annotations

import asyncio
import json
import time as _real_time
from datetime import datetime, timedelta, timezone

import pytest

import app.tasks.backfill_winners as bw

SETTLED = [datetime(2025, m, 1, tzinfo=timezone.utc) for m in range(1, 7)]


def _open_month() -> datetime:
    # Offset-free: the current month has not ended, so it is open whatever the
    # clock reads (gotcha #44 — no branch on the clock).
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


class _Cell:
    def __init__(self, category, bucket_start):
        self.category = category
        self.bucket_start = bucket_start


class _Row:
    def __init__(self, idx, category, n, winners, sum_prob, sum_sq_err):
        self.bucket_idx = idx
        self.category = category
        self.n = n
        self.winners = winners
        self.sum_prob = sum_prob
        self.sum_sq_err = sum_sq_err


def _rows_for(category, lo, version=0):
    """Distinct, cell-specific rows so a carried cell is distinguishable."""
    n = 10 + lo.month + version * 1000
    return [_Row(lo.month % 10, category, n, n // 2, n * 0.5, n * 0.2)]


class _BankRedis:
    """Enough Redis for the writer: the curve key and the cell-bank hash."""

    def __init__(self):
        self.curve = None
        self.hashes: dict[str, dict[str, str]] = {}
        self.expiry: dict[str, int] = {}

    def setex(self, key, ttl, value):
        self.curve = (key, ttl, value)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def expire(self, key, ttl):
        self.expiry[key] = ttl


def _run(monkeypatch, grid, redis, *, seconds_per_chunk=1.0, budget_chunks=None,
         version=0):
    """One real writer run. Returns (summary, chunk calls as (category, lo))."""
    clock = {"t": 1_000_000.0}
    monkeypatch.setattr(_real_time, "monotonic", lambda: clock["t"])
    if budget_chunks is not None:
        monkeypatch.setattr(bw, "_TRAVERSAL_BUDGET_S",
                            seconds_per_chunk * budget_chunks)
    calls: list = []

    class _Result:
        def __init__(self, payload):
            self._payload = payload

        def first(self):
            return None

        def all(self):
            return self._payload

    class _Session:
        async def execute(self, statement, params=None, *a, **k):
            sql = str(statement)
            if "SET LOCAL statement_timeout" in sql:
                return _Result([])
            # #1479: the per-transaction session tag, not a chunk.
            if "set_config('application_name'" in sql:
                return _Result([])
            if "date_trunc('month'" in sql:
                return _Result(list(grid))
            clock["t"] += seconds_per_chunk
            calls.append((params["category"], params["lo"]))
            return _Result(_rows_for(params["category"], params["lo"], version))

        async def rollback(self):
            return None

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    async def _publish(envelope):
        return {"status": "ok", "identity": envelope.identity,
                "generation": envelope.generation}

    monkeypatch.setattr(
        "app.services.durable_snapshots.publish_snapshot_standalone", _publish)
    session = _Session()
    monkeypatch.setattr(bw, "get_task_session", lambda: session)
    monkeypatch.setattr("app.tasks.redis_state.get_redis_client",
                        lambda *a, **k: redis)
    summary = asyncio.run(bw._precompute_bookmaker_calibration())
    return summary, calls


def _grid(n_categories=4):
    return [_Cell(f"sport_{i:02d}", lo)
            for i in range(n_categories) for lo in SETTLED]


def test_a_walk_too_slow_for_one_run_converges_across_runs(monkeypatch):
    """THE 10/08-10/11 SHAPE: the budget fits 7 of 24 cells per run.

    Before the bank every run landed the same first 7 cells and published
    nothing, forever. With it, run 4 covers the last cells and publishes.
    """
    grid = _grid()
    redis = _BankRedis()
    summaries = []
    for _ in range(6):
        summary, _calls = _run(monkeypatch, grid, redis, budget_chunks=7)
        summaries.append(summary)
        if summary["published"]:
            break

    assert [s["published"] for s in summaries[:3]] == [False, False, False]
    assert all(s["terminal"] == "failed" and s["budget_exhausted"]
               for s in summaries[:3])
    assert redis.curve is not None, (
        f"no run published after {len(summaries)} runs: the walk still restarts "
        f"from the top — {[s['bank'] for s in summaries]}")
    assert summaries[-1]["terminal"] == "complete"
    assert len(summaries) == 4
    assert summaries[-1]["bank"]["carried"] == 21


def test_a_bank_assisted_curve_is_byte_identical_to_one_full_walk(monkeypatch):
    """Carrying cells must not move a published number."""
    grid = _grid()
    full = _BankRedis()
    _run(monkeypatch, grid, full)  # unbounded wall: one full walk
    assert full.curve is not None

    banked = _BankRedis()
    for _ in range(6):
        summary, _ = _run(monkeypatch, grid, banked, budget_chunks=7)
        if summary["published"]:
            break
    assert banked.curve is not None
    assert json.loads(banked.curve[2]) == json.loads(full.curve[2])


def test_a_run_that_does_not_cover_every_cell_still_writes_nothing(monkeypatch):
    """Fail closed is unchanged: banked progress is not a licence to publish."""
    redis = _BankRedis()
    summary, _ = _run(monkeypatch, _grid(), redis, budget_chunks=7)
    assert summary["published"] is False
    assert redis.curve is None
    assert summary["bank"]["banked"] == 7
    blob = " ".join(summary["errors"])
    assert "7 cell(s) banked for the next run" in blob, blob


def test_missing_settled_cells_are_walked_before_open_months(monkeypatch):
    """Open months are never carried, so walking them first could starve the
    settled backlog forever; missing cells go first so every run makes progress."""
    open_lo = _open_month()
    grid = [_Cell("aaa_open", open_lo), _Cell("zzz_settled", SETTLED[0])]
    _, calls = _run(monkeypatch, grid, _BankRedis(), budget_chunks=1)
    assert calls == [("zzz_settled", SETTLED[0])]


def test_an_open_month_is_read_fresh_even_when_banked(monkeypatch):
    open_lo = _open_month()
    grid = [_Cell("sport_00", open_lo), _Cell("sport_00", SETTLED[0])]
    redis = _BankRedis()
    _run(monkeypatch, grid, redis)
    summary, calls = _run(monkeypatch, grid, redis, version=1)

    assert ("sport_00", open_lo) in calls, "an open month was answered from the bank"
    assert ("sport_00", SETTLED[0]) not in calls, "a fresh settled cell was re-read"
    assert summary["bank"]["carried"] == 1
    published = json.loads(redis.curve[2])
    open_n = _rows_for("sport_00", open_lo, version=1)[0].n
    assert any(b["n"] == open_n for b in published), (
        "the open month's fresh read did not reach the curve")


def test_a_bank_entry_past_its_age_bound_is_re_read(monkeypatch):
    grid = [_Cell("sport_00", SETTLED[0])]
    redis = _BankRedis()
    key = bw._bookmaker_cell_key("sport_00", SETTLED[0])
    stale_at = _real_time.time() - bw._BOOKMAKER_BANK_MAX_AGE_S - 60
    redis.hset(bw._BOOKMAKER_BANK_KEY, key, json.dumps(
        {"banked_at": stale_at, "rows": [[0, "sport_00", 1, 1, 0.5, 0.1]]}))

    summary, calls = _run(monkeypatch, grid, redis)
    assert calls == [("sport_00", SETTLED[0])]
    assert summary["bank"]["carried"] == 0
    assert summary["published"] is True


def test_spare_wall_refreshes_only_cells_older_than_the_refresh_age(monkeypatch):
    old, young = SETTLED[0], SETTLED[1]
    grid = [_Cell("sport_00", old), _Cell("sport_00", young)]
    redis = _BankRedis()
    now = _real_time.time()
    for lo, age in ((old, bw._BOOKMAKER_BANK_REFRESH_AFTER_S + 60), (young, 60)):
        redis.hset(bw._BOOKMAKER_BANK_KEY, bw._bookmaker_cell_key("sport_00", lo),
                   json.dumps({"banked_at": now - age,
                               "rows": [[lo.month, "sport_00", 1, 1, 0.5, 0.1]]}))

    summary, calls = _run(monkeypatch, grid, redis, version=1)
    assert calls == [("sport_00", old)]
    assert summary["bank"]["refreshed"] == 1
    assert summary["bank"]["carried"] == 2
    published = {b["bucket_idx"]: b["n"] for b in json.loads(redis.curve[2])}
    assert published[old.month % 10] == _rows_for("sport_00", old, 1)[0].n
    assert published[young.month] == 1, "a young carried cell was replaced"


def test_an_unreadable_bank_falls_back_to_the_full_walk(monkeypatch):
    class _NoHash(_BankRedis):
        def hgetall(self, key):
            raise ConnectionError("redis down")

        def hset(self, key, field, value):
            raise ConnectionError("redis down")

    redis = _NoHash()
    summary, calls = _run(monkeypatch, _grid(1), redis)
    assert len(calls) == len(SETTLED)
    assert summary["published"] is True and summary["terminal"] == "complete"
    assert summary["bank"]["read"].startswith("error")
    assert summary["bank"]["write_errors"] == len(SETTLED)


def test_malformed_and_future_dated_entries_are_dropped():
    redis = _BankRedis()
    now = _real_time.time()
    good = json.dumps({"banked_at": now - 10, "rows": [[1, "a", 1, 1, 0.5, 0.1]]})
    redis.hset(bw._BOOKMAKER_BANK_KEY, "good", good)
    redis.hset(bw._BOOKMAKER_BANK_KEY, "junk", "{not json")
    redis.hset(bw._BOOKMAKER_BANK_KEY, "short", json.dumps(
        {"banked_at": now, "rows": [[1, "a", 1]]}))
    redis.hset(bw._BOOKMAKER_BANK_KEY, "future", json.dumps(
        {"banked_at": now + 3600, "rows": [[1, "a", 1, 1, 0.5, 0.1]]}))
    assert set(bw._read_bookmaker_bank(redis, now)) == {"good"}


def test_the_bank_key_is_bound_to_the_chunk_statement():
    """A changed statement must never be answered from the old one's rows."""
    import hashlib

    digest = hashlib.sha1(bw._BOOKMAKER_CHUNK_SQL.encode()).hexdigest()[:12]
    assert bw._BOOKMAKER_BANK_KEY.endswith(digest)
    assert bw._BOOKMAKER_BANK_KEY != "bainluck:bookmaker_calibration", (
        "the bank would overwrite the curve key the reader serves")


@pytest.mark.parametrize("lo,settled", [
    (datetime(2026, 9, 1, tzinfo=timezone.utc), False),  # ends 10/01, +14 d = 10/15
    (datetime(2026, 8, 1, tzinfo=timezone.utc), True),
])
def test_a_month_settles_fourteen_days_after_it_ends(lo, settled):
    as_of = datetime(2026, 10, 11, 17, 0, tzinfo=timezone.utc).timestamp()
    assert bw._bookmaker_cell_settled(lo, as_of) is settled


def test_the_age_bounds_are_ordered():
    assert (bw._BOOKMAKER_BANK_REFRESH_AFTER_S < bw._BOOKMAKER_BANK_MAX_AGE_S
            < bw._BOOKMAKER_BANK_TTL_S)
    # The curve key's own TTL is 24 h; a carried cell may be older than the
    # curve it feeds only by the documented 48 h bound.
    assert bw._BOOKMAKER_BANK_MAX_AGE_S == timedelta(hours=48).total_seconds()
