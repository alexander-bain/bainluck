"""#10090: heavy background scans stand down while production Postgres is busy.

Each deferred call site is pinned both ways: with ``BUSY_DB_DEFER_HEAVY_SCANS=1``
inside the busy window it skips its scan and logs one WARNING naming itself, and
with the switch off it reaches the scan exactly as before. "Reaches" is proven
by a sentinel raised from the first thing past the gate, never by the absence
of a skip.
"""

from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.utils import busy_db_defer

BUSY = datetime(2026, 10, 31, 16, 30, tzinfo=timezone.utc)   # 9:30 AM PT
QUIET = datetime(2026, 10, 31, 9, 30, tzinfo=timezone.utc)   # 2:30 AM PT


class _ReachedTheScan(Exception):
    pass


def _raise_reached(*_a, **_k):
    raise _ReachedTheScan()


@pytest.fixture
def switch_on(monkeypatch):
    monkeypatch.setenv(busy_db_defer.SWITCH_ENV, "1")
    monkeypatch.delenv(busy_db_defer.HOURS_ENV, raising=False)


@pytest.fixture
def switch_off(monkeypatch):
    monkeypatch.delenv(busy_db_defer.SWITCH_ENV, raising=False)
    monkeypatch.delenv(busy_db_defer.HOURS_ENV, raising=False)


@pytest.fixture
def always_busy(monkeypatch):
    """Task call sites read the wall clock; pin the window instead of the hour."""
    monkeypatch.setattr(busy_db_defer, "in_busy_window", lambda now=None: True)


# --- the predicate ----------------------------------------------------------


class TestThePredicate:
    def test_off_by_default_even_in_the_busy_window(self, switch_off):
        assert busy_db_defer.should_defer("x", BUSY) is False

    @pytest.mark.parametrize("value", ["0", "true", "yes", "", "on"])
    def test_only_the_literal_one_turns_it_on(self, monkeypatch, value):
        monkeypatch.setenv(busy_db_defer.SWITCH_ENV, value)
        assert busy_db_defer.should_defer("x", BUSY) is False

    def test_on_and_busy_defers_and_says_so(self, switch_on, caplog):
        with caplog.at_level(logging.WARNING, logger=busy_db_defer.__name__):
            assert busy_db_defer.should_defer("some_scan", BUSY) is True
        assert any(
            "some_scan" in r.getMessage() and "BUSY_DB_DEFER_HEAVY_SCANS=1" in r.getMessage()
            for r in caplog.records
        )

    def test_on_and_quiet_runs(self, switch_on, caplog):
        with caplog.at_level(logging.WARNING, logger=busy_db_defer.__name__):
            assert busy_db_defer.should_defer("some_scan", QUIET) is False
        assert not caplog.records

    @pytest.mark.parametrize(
        "hour,busy",
        [(14, False), (15, True), (23, True), (0, True), (4, True), (5, False), (10, False)],
    )
    def test_default_window_wraps_midnight_end_exclusive(self, switch_on, hour, busy):
        now = datetime(2026, 10, 31, hour, 0, tzinfo=timezone.utc)
        assert busy_db_defer.in_busy_window(now) is busy

    @pytest.mark.parametrize("hour,busy", [(8, False), (9, True), (16, True), (17, False)])
    def test_a_same_day_window(self, monkeypatch, hour, busy):
        monkeypatch.setenv(busy_db_defer.HOURS_ENV, "9-17")
        now = datetime(2026, 10, 31, hour, 0, tzinfo=timezone.utc)
        assert busy_db_defer.in_busy_window(now) is busy

    def test_equal_hours_is_an_empty_window(self, monkeypatch):
        monkeypatch.setenv(busy_db_defer.HOURS_ENV, "7-7")
        assert not any(
            busy_db_defer.in_busy_window(datetime(2026, 10, 31, h, tzinfo=timezone.utc))
            for h in range(24)
        )

    @pytest.mark.parametrize("raw", ["15", "a-b", "15-24", "-1-5", "15-05-01"])
    def test_a_malformed_window_falls_back_to_the_default(self, monkeypatch, caplog, raw):
        monkeypatch.setenv(busy_db_defer.HOURS_ENV, raw)
        with caplog.at_level(logging.WARNING, logger=busy_db_defer.__name__):
            assert busy_db_defer.busy_hours_utc() == busy_db_defer.DEFAULT_BUSY_HOURS_UTC
        assert caplog.records

    def test_the_window_reads_utc_not_the_offset_wall_clock(self, switch_on):
        # 08:30 PDT is 15:30 UTC: busy. Reading .hour off the aware value
        # without converting would say 8 and run the scan.
        from datetime import timedelta

        pdt = timezone(timedelta(hours=-7))
        assert busy_db_defer.in_busy_window(datetime(2026, 10, 31, 8, 30, tzinfo=pdt))

    def test_a_naive_now_is_utc(self, switch_on):
        assert busy_db_defer.in_busy_window(datetime(2026, 10, 31, 16, 30)) is True
        assert busy_db_defer.in_busy_window(datetime(2026, 10, 31, 9, 30)) is False

    def test_the_deferred_result_is_a_no_work_terminal(self):
        from app.utils.task_verdict import UNKNOWN, classify_summary

        verdict = classify_summary(busy_db_defer.deferred_result("x"))
        assert verdict.verdict == UNKNOWN and verdict.authoritative


# --- the call sites ---------------------------------------------------------


@pytest.mark.asyncio
async def test_opening_repair_defers_without_touching_its_cursor(switch_on, always_busy, monkeypatch):
    from app.tasks import redis_state

    backfill_winners = importlib.import_module("app.tasks.backfill_winners")

    monkeypatch.setattr(redis_state, "get_redis_client", _raise_reached)
    out = await backfill_winners._repair_openings_from_first_snapshot(scan=10)
    assert out["terminal"] == "skipped"
    assert out["reason"] == busy_db_defer.DEFERRED_REASON


@pytest.mark.asyncio
async def test_opening_repair_runs_when_the_switch_is_off(switch_off, monkeypatch):
    from app.tasks import redis_state

    backfill_winners = importlib.import_module("app.tasks.backfill_winners")

    monkeypatch.setattr(redis_state, "get_redis_client", _raise_reached)
    with pytest.raises(_ReachedTheScan):
        await backfill_winners._repair_openings_from_first_snapshot(scan=10)


@pytest.mark.asyncio
async def test_calibration_main_runs_when_the_switch_is_off(switch_off, monkeypatch):
    from app.tasks import precompute_calibration

    monkeypatch.setattr(precompute_calibration, "_main_input_fingerprint", _raise_reached)
    with pytest.raises(_ReachedTheScan):
        await precompute_calibration._precompute_calibration_main()


@pytest.mark.asyncio
async def test_matching_reconciliation_defers_and_files_nothing(switch_on, always_busy, monkeypatch):
    mr = importlib.import_module("app.tasks.matching_reconciliation")

    monkeypatch.setattr(mr, "get_task_session", _raise_reached)
    monkeypatch.setattr(mr, "file_findings", _raise_reached)
    out = await mr._run_matching_reconciliation(file_issues=True)
    assert out["terminal"] == "skipped"
    assert out["reason"] == busy_db_defer.DEFERRED_REASON


@pytest.mark.asyncio
async def test_matching_reconciliation_runs_when_the_switch_is_off(switch_off, monkeypatch):
    mr = importlib.import_module("app.tasks.matching_reconciliation")

    monkeypatch.setattr(mr, "get_task_session", _raise_reached)
    with pytest.raises(_ReachedTheScan):
        await mr._run_matching_reconciliation(file_issues=False)


@pytest.mark.asyncio
async def test_theme_assembly_defers(switch_on, monkeypatch):
    from app.tasks import base, theme_assembly

    monkeypatch.setattr(theme_assembly, "theme_assembly_enabled", lambda: True)
    monkeypatch.setattr(base, "get_task_session", _raise_reached)
    out = await theme_assembly._run_assemble_theme_collections(now=BUSY)
    assert out["terminal"] == "skipped"
    assert out["reason"] == busy_db_defer.DEFERRED_REASON


@pytest.mark.asyncio
async def test_theme_assembly_runs_outside_the_window(switch_on, monkeypatch):
    from app.tasks import base, theme_assembly

    monkeypatch.setattr(theme_assembly, "theme_assembly_enabled", lambda: True)
    monkeypatch.setattr(base, "get_task_session", _raise_reached)
    with pytest.raises(_ReachedTheScan):
        await theme_assembly._run_assemble_theme_collections(now=QUIET)


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value

    def fetchall(self):
        return []

    def all(self):
        return []

    def first(self):
        return None

    def fetchone(self):
        return None


async def _run_watchdog(monkeypatch):
    """Run the watchdog against a session that answers every check at threshold."""
    from app.tasks import data_quality_watchdog as dq
    from app.tasks import redis_state, sentinel_filing

    by_query = {c["query"]: c["threshold"] for c in dq.CHECKS}
    executed: list[str] = []

    class _Session:
        async def execute(self, stmt, *_a, **_k):
            sql = str(stmt)
            executed.append(sql)
            return _Result(by_query.get(sql, 0))

        async def commit(self):
            return None

        async def rollback(self):
            return None

    @asynccontextmanager
    async def _session():
        yield _Session()

    monkeypatch.setattr(dq, "get_task_session", _session)
    monkeypatch.setattr(sentinel_filing, "fetch_open_alert_issues", lambda: [])
    monkeypatch.setattr(dq, "_check_redis_dedup", lambda *_a, **_k: True)
    monkeypatch.setattr(dq, "_has_open_canonical", lambda *_a, **_k: True)
    monkeypatch.setattr(dq, "_set_redis_dedup", lambda *_a, **_k: None)
    monkeypatch.setattr(dq, "reconcile_alert_issue", lambda *_a, **_k: {})
    redis = MagicMock()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *_a, **_k: redis)
    stats = await dq._run_data_quality_watchdog()
    return dq, stats, executed, redis


def _coverage_checks(dq):
    names = {c["name"] for c in dq.CHECKS if c.get("busy_db_deferrable")}
    assert names == {"kalshi_winner_coverage", "polymarket_winner_coverage"}
    return names


@pytest.mark.asyncio
async def test_watchdog_defers_only_the_winner_coverage_census(switch_on, always_busy, monkeypatch):
    dq, stats, executed, redis = await _run_watchdog(monkeypatch)
    deferred = _coverage_checks(dq)
    coverage_sql = {c["query"] for c in dq.CHECKS if c["name"] in deferred}
    assert not coverage_sql & set(executed), "a deferred census must not be read"
    assert stats["checks_deferred"] == 2
    for name in deferred:
        assert stats["results"][name]["deferred"] == busy_db_defer.DEFERRED_REASON
        assert "passed" not in stats["results"][name], "not run is not passed"
    others = [c for c in dq.CHECKS if c["name"] not in deferred]
    assert stats["checks_run"] == len(others), "every other check still runs"
    # The published summary does not count a deferred P1 as failing.
    import json

    summaries = [
        json.loads(call.args[2]) for call in redis.setex.call_args_list
        if call.args[0] == "bainluck:data_quality_watchdog:last"
    ]
    assert summaries, "the watchdog summary was not published"
    assert all(not ({f["name"] for f in s["failing"]} & deferred) for s in summaries)
    assert all(s["checks_deferred"] == 2 for s in summaries)


@pytest.mark.asyncio
async def test_watchdog_runs_the_census_when_the_switch_is_off(switch_off, monkeypatch):
    dq, stats, executed, _ = await _run_watchdog(monkeypatch)
    coverage_sql = {c["query"] for c in dq.CHECKS if c["name"] in _coverage_checks(dq)}
    assert coverage_sql <= set(executed)
    assert stats["checks_deferred"] == 0
    assert stats["checks_run"] == len(dq.CHECKS)
