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
    def __init__(self, census_times_out: bool = True):
        self.order: list[str] = []
        self.timeouts: list[str] = []
        self.census_times_out = census_times_out

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "set_config('statement_timeout'" in sql:
            self.timeouts.append((params or {})["ms"])
            return _Scalar(None)
        from app.tasks.data_quality_watchdog import CHECKS

        name = next((c["name"] for c in CHECKS if c["query"] == sql), None)
        if name is None:
            self.order.append("SNAPSHOT")  # the post-loop link-rate / coverage reads
            raise RuntimeError("snapshot read not modelled")
        self.order.append(name)
        if self.census_times_out and "winner_coverage" in name:
            raise QueryCanceledError("canceling statement due to statement timeout")
        return _Scalar(1_000_000)  # passes every gte/lte threshold below

    async def rollback(self):
        self.order.append("ROLLBACK")

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
    checks = [n for n in session.order if n not in ("ROLLBACK", "SNAPSHOT")]
    assert checks[-2:] == census, session.order  # the census runs last
    assert len(checks) == len(wd.CHECKS)
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


# --- B-7: finished tournaments stop being upkept --------------------------


def test_the_us_open_upkeep_window_is_its_calendar_dates_plus_margins():
    from datetime import datetime, timezone

    from app.utils.majors_calendar import upkeep_window_open

    def at(day):
        return datetime.fromisoformat(f"{day}T12:00:00+00:00").astimezone(timezone.utc)

    slug = "us-open-tennis-2026"  # 2026-08-24 .. 2026-09-13 in the calendar
    assert not upkeep_window_open(slug, at("2026-08-16"))
    assert upkeep_window_open(slug, at("2026-08-17"))  # 7 days ahead
    assert upkeep_window_open(slug, at("2026-09-16"))  # 3 days after
    assert not upkeep_window_open(slug, at("2026-09-17"))
    assert not upkeep_window_open(slug, at("2026-11-06"))
    # Fails open: a slug the calendar does not know keeps running.
    assert upkeep_window_open("not-in-the-calendar", at("2026-11-06"))
    assert upkeep_window_open(None, at("2026-11-06"))


async def test_an_out_of_season_scheduled_run_refreshes_nothing(monkeypatch):
    from app.tasks import tournament_price_refresh as rail

    monkeypatch.setattr(rail, "in_season", lambda slug, now=None: False)
    stats = await rail._refresh_registered_tournament_prices()
    assert stats["terminal"] == "no_work"
    # An explicit list is never gated.
    seen = []
    import app.utils.tournament_register as reg

    monkeypatch.setattr(reg, "load_register", lambda t, s: seen.append((t, s)))
    await rail._refresh_registered_tournament_prices([("us-open", "2026")])
    assert seen == [("us-open", "2026")]


async def test_the_matchup_linker_skips_out_of_season_tournaments(monkeypatch):
    from app.tasks import tournament_matchup_linker as linker
    from app.tasks import tournament_price_refresh as rail

    monkeypatch.setattr(rail, "in_season", lambda slug, now=None: False)
    stats = await linker._link_tournament_matchups()
    assert stats["tournaments"] == 0


def test_the_tier1_coverage_beat_is_retired_but_the_task_stays():
    from app.tasks import celery_app

    assert "check-tier1-coverage" not in celery_app.conf.beat_schedule
    assert "app.tasks.check_tier1_coverage" in celery_app.tasks


# --- B-12: drained slow beats ------------------------------------------------


def test_the_openings_repair_runs_once_a_day_in_its_own_slot():
    from celery.schedules import crontab

    from app.tasks import celery_app

    entry = celery_app.conf.beat_schedule["repair-openings-from-first-snapshot"]
    assert entry["schedule"] == crontab(minute=48, hour=4)
    assert entry["options"]["queue"] == "background"


def test_the_kalshi_resolved_zero_beat_is_retired_and_the_cliff_drain_covers_it():
    from app.tasks import celery_app

    beats = celery_app.conf.beat_schedule
    assert "backfill-kalshi-price-history" not in beats
    # Its cohort is drained hourly by the watermarked rail; its other modes run.
    assert beats["kalshi-cliff-drain"]["task"] == "app.tasks.kalshi_cliff_drain"
    modes = sorted(
        (e.get("kwargs") or {}).get("mode", "resolved_zero")
        for e in beats.values()
        if e["task"] == "app.tasks.backfill_kalshi_history"
    )
    assert modes == ["open_sparse", "pregame_gap"]


async def test_the_results_sync_keeps_a_finished_hub_alive_out_of_season(monkeypatch):
    """Fable, Nov 6: the results rail is the only writer of the hub's results key
    and its last-good copy, so it must NOT be calendar-gated: out of season it
    still asks for the default hub, or the decided draw lapses to `unavailable`."""
    import app.services.espn_tennis as espn
    from app.tasks import tournament_price_refresh as rail

    monkeypatch.setattr(rail, "in_season", lambda slug, now=None: False)
    asked = []

    async def _fetch(event_name, *a, **k):
        asked.append(event_name)
        raise RuntimeError("stop here")  # reported, the loop moves on

    monkeypatch.setattr(espn, "fetch_tournament_results", _fetch)
    stats = await rail._sync_tournament_results()
    assert asked == [name for _, name in rail.DEFAULT_RESULT_TARGETS]
    assert stats["errors"]


def test_a_timed_out_census_is_not_red_on_the_cockpit_and_keeps_its_last_verdict():
    """Fable, Nov 6 (item 2): `timed_out` is not a failure. The cockpit leaves it
    out of `failing` and carries the previous verdict, the way `deferred` does."""
    import asyncio
    import json
    from contextlib import asynccontextmanager

    from app.tasks import data_quality_watchdog as wd

    class _Redis:
        def __init__(self, prev):
            self.store = {"bainluck:data_quality_watchdog:last": json.dumps(prev)}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.store[key] = value

    def _run(prev):
        session = _WatchdogSession()

        @asynccontextmanager
        async def _ctx():
            yield session

        redis = _Redis(prev)
        mp = pytest.MonkeyPatch()
        try:
            mp.setattr(wd, "get_task_session", _ctx)
            mp.setattr(wd, "passes_threshold", lambda value, check: True)
            mp.setattr(wd, "reconcile_alert_issue", lambda *a, **k: {})
            mp.setattr("app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: None)
            mp.setattr("app.utils.busy_db_defer.should_defer", lambda *_: False)
            mp.setattr(wd, "_check_redis_dedup", lambda *_: False)
            mp.setattr("app.tasks.redis_state.get_redis_client", lambda: redis)
            asyncio.run(wd._run_data_quality_watchdog())
        finally:
            mp.undo()
        return json.loads(redis.store["bainluck:data_quality_watchdog:last"])

    clean = _run({})
    assert clean["status"] != "red" and clean["failing"] == [], clean
    carried = _run(
        {
            "computed_at": "2026-11-06T00:00:00+00:00",
            "failing": [{"name": "kalshi_winner_coverage", "severity": "P1"}],
        }
    )
    assert [f["name"] for f in carried["failing"]] == ["kalshi_winner_coverage"]
    assert carried["failing"][0]["carried_from"] == "2026-11-06T00:00:00+00:00"


async def test_the_last_checks_bound_ends_before_the_snapshot_reads(monkeypatch):
    """Fable, Nov 6 (item 3): every check passes, so no in-loop rollback runs, and
    the transaction carrying the last check's bound must still end before the
    link-rate / coverage snapshot reads."""
    from contextlib import asynccontextmanager

    from app.tasks import data_quality_watchdog as wd

    session = _WatchdogSession(census_times_out=False)

    @asynccontextmanager
    async def _ctx():
        yield session

    monkeypatch.setattr(wd, "get_task_session", _ctx)
    monkeypatch.setattr(wd, "passes_threshold", lambda value, check: True)
    monkeypatch.setattr(wd, "reconcile_alert_issue", lambda *a, **k: {})
    monkeypatch.setattr("app.tasks.sentinel_filing.fetch_open_alert_issues", lambda: None)
    monkeypatch.setattr("app.utils.busy_db_defer.should_defer", lambda *_: False)
    monkeypatch.setattr(wd, "_check_redis_dedup", lambda *_: False)

    await wd._run_data_quality_watchdog()

    names = {c["name"] for c in wd.CHECKS}
    last_check = max(i for i, n in enumerate(session.order) if n in names)
    first_snapshot = session.order.index("SNAPSHOT")
    assert "ROLLBACK" in session.order[last_check + 1 : first_snapshot], session.order
