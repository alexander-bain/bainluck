"""C-1 (worker audit 2026-11-06; Speed): cadence trims on `worker-background`.

Each section pins one trim and the reader-facing age it states.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.tasks import event_concept_warmer as concepts


# --- B-4: golf majors every 30 min, leaders still every 5 -------------------


def test_the_majors_ride_the_run_that_opens_each_half_hour():
    base = 1_762_473_600  # 2025-11-07 00:00:00Z, a whole hour
    due = [m for m in range(0, 60, 5) if concepts.majors_due(base + m * 60 + 7)]
    assert due == [0, 30]
    assert concepts.MAJORS_EVERY_MINUTES == 30
    assert concepts.BEAT_PERIOD_MINUTES == 5


def test_the_beat_the_slot_arithmetic_mirrors_is_still_every_5_minutes():
    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["warm-event-concepts"]
    assert entry["schedule"].minute == set(range(0, 60, concepts.BEAT_PERIOD_MINUTES))


@pytest.mark.parametrize("due", [True, False])
async def test_an_off_slot_run_warms_the_leaders_and_never_the_majors(due):
    from app.config.event_concept_warm_keys import WARM_CONCEPT_KEYS

    built: list[str] = []

    async def _population():
        return ("leader-a", "leader-b")

    async def _build(key, *, token, timeout=None):
        built.append(key)
        return {"key": key, "ok": True, "reason": "built", "seconds": 0.1}

    with patch.object(concepts, "majors_due", lambda now: due), \
         patch.object(concepts, "_leader_population", _population), \
         patch.object(concepts, "_build_one", _build), \
         patch("app.utils.event_concept_cache.get_client", lambda: object()), \
         patch("app.utils.event_concept_cache.acquire_refresh_lock", lambda rc, keys: "tok"):
        summary = await concepts._warm_event_concepts()

    majors = set(WARM_CONCEPT_KEYS)
    assert built[:2] == ["leader-a", "leader-b"]  # leaders first, every run
    assert bool(majors & set(built)) is due
    assert summary["majors_tier"] is due
    assert summary["total"] == 2 + (len(WARM_CONCEPT_KEYS) if due else 0)
    assert summary["terminal"] == "complete"


# --- B-8: the watchdog's checks are bounded one by one ----------------------


class QueryCanceledError(Exception):
    """Named as asyncpg names a statement_timeout cancellation."""


class _WatchdogSession:
    def __init__(self):
        self.order: list[str] = []
        self.timeouts: list[str] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "set_config('statement_timeout'" in sql:
            self.timeouts.append((params or {})["ms"])
            return _Scalar(None)
        from app.tasks.data_quality_watchdog import CHECKS

        name = next(c["name"] for c in CHECKS if c["query"] == sql)
        self.order.append(name)
        if "winner_coverage" in name:
            raise QueryCanceledError("canceling statement due to statement timeout")
        return _Scalar(1_000_000)  # passes every gte/lte threshold below

    async def rollback(self):
        pass

    async def commit(self):
        pass


class _Scalar:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


async def test_a_slow_census_times_out_alone_and_never_files(monkeypatch):
    from contextlib import asynccontextmanager

    from app.tasks import data_quality_watchdog as wd

    session = _WatchdogSession()

    @asynccontextmanager
    async def _ctx():
        yield session

    filed: list = []
    monkeypatch.setattr(wd, "get_task_session", _ctx)
    monkeypatch.setattr(wd, "passes_threshold", lambda value, check: True)
    monkeypatch.setattr(wd, "reconcile_alert_issue", lambda *a, **k: filed.append(a) or {})
    monkeypatch.setattr("app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: None)
    monkeypatch.setattr("app.utils.busy_db_defer.should_defer", lambda *_: False)
    monkeypatch.setattr(wd, "_check_redis_dedup", lambda *_: False)

    stats = await wd._run_data_quality_watchdog()

    census = ["kalshi_winner_coverage", "polymarket_winner_coverage"]
    assert session.order[-2:] == census, session.order  # the census runs last
    assert len(session.order) == len(wd.CHECKS)
    assert session.timeouts.count(f"{wd.WATCHDOG_COVERAGE_TIMEOUT_MS}ms") == 2
    assert session.timeouts.count(f"{wd.WATCHDOG_CHECK_TIMEOUT_MS}ms") == len(wd.CHECKS) - 2
    assert not filed
    assert stats["checks_timed_out"] == 2
    assert not [e for e in stats["errors"] if e["check"] in census]
    assert all(stats["results"][c]["timed_out"] for c in census)


def test_the_bounds_fit_inside_the_watchdogs_soft_limit():
    from app.tasks import celery_app
    from app.tasks import data_quality_watchdog as wd

    soft = celery_app.tasks["app.tasks.run_data_quality_watchdog"].soft_time_limit
    worst = sum(c.get("timeout_ms", wd.WATCHDOG_CHECK_TIMEOUT_MS) for c in wd.CHECKS) / 1000
    assert worst < soft, (worst, soft)
