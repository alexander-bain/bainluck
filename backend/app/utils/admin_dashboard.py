"""Helper functions for the admin operations dashboard.

Each function builds one section of the ``/api/admin/dashboard`` response.
They are designed to be independently testable and to keep the route handler
thin.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Per-panel Postgres statement timeout. This bounds an ADMIN MEASUREMENT query
# only — it is NOT a request deadline on a user-facing route (LAT-P002 was
# reverted for adding one of those, and this queue's guardrails forbid it).
_PANEL_STATEMENT_TIMEOUT = "10s"
_GAME_STATE_STATEMENT_TIMEOUT = "15s"


def _expected_sources_for_sport(sport_key: str) -> dict[str, bool]:
    """Which data sources are expected to have coverage for this sport?"""
    from app.utils.sport_keys import ESPN_SPORT_MAPPING, STATPAL_SPORT_MAPPING

    return {
        "odds_api": True,
        "espn": sport_key in ESPN_SPORT_MAPPING,
        "statpal": sport_key in STATPAL_SPORT_MAPPING,
        "espn_wp": sport_key in ESPN_SPORT_MAPPING,
        "model": sport_key in ESPN_SPORT_MAPPING,
        "mlb": sport_key.startswith("baseball_mlb"),
        "kalshi": True,
        "polymarket": True,
    }



# ---------------------------------------------------------------------------
# 1. Odds API Quota
# ---------------------------------------------------------------------------

def build_quota_section(now: datetime) -> dict[str, Any]:
    """Build the Odds API quota section from Redis data.

    This is synchronous because all data comes from Redis (via helpers that
    use a sync Redis client).
    """
    import calendar as cal_mod

    from app.tasks.redis_state import (
        get_odds_api_quota,
        get_odds_api_quota_history,
        get_odds_api_task_breakdown,
        get_odds_api_sport_breakdown,
    )

    quota = get_odds_api_quota()
    history = get_odds_api_quota_history(hours=720)  # 30 days
    task_breakdown = get_odds_api_task_breakdown(hours=720)
    sport_breakdown_24h = get_odds_api_sport_breakdown(hours=24)
    sport_breakdown_7d = get_odds_api_sport_breakdown(hours=168)

    # Compute daily usage deltas — only include current month (UTC)
    current_month_prefix = now.strftime("%Y-%m-")
    daily_map: dict[str, dict] = {}
    for entry in history:
        day = entry["hour"][:10]
        if not day.startswith(current_month_prefix):
            continue  # skip previous month's data
        daily_map[day] = entry

    daily_usage: list[dict[str, Any]] = []
    sorted_days = sorted(daily_map.keys())
    for i, day in enumerate(sorted_days):
        used = daily_map[day]["used"]
        prev_used = daily_map[sorted_days[i - 1]]["used"] if i > 0 else 0
        delta = used - prev_used
        if delta < 0:
            delta = used  # month rollover
        daily_usage.append({"date": day, "daily_requests": delta, "cumulative": used})

    # Budget projection
    total_budget = 5_000_000
    today = now.date()
    days_in_month = cal_mod.monthrange(today.year, today.month)[1]
    day_of_month = today.day
    days_remaining = days_in_month - day_of_month

    # 48h pace: average daily burn over last 2 COMPLETE days (exclude today's partial)
    today_str = today.isoformat()
    complete_days = [d for d in daily_usage if d["daily_requests"] > 0 and d["date"] != today_str]
    recent_daily = (
        complete_days[-2:]
        if len(complete_days) >= 2
        else complete_days[-1:]
        if complete_days
        else []
    )
    pace_48h = sum(d["daily_requests"] for d in recent_daily) / max(len(recent_daily), 1)
    projected_eom = (quota.get("used", 0) or 0) + int(pace_48h * days_remaining)

    linear_daily_budget = total_budget / days_in_month

    return {
        "current": quota,
        "daily_usage": daily_usage,
        "daily_by_task": task_breakdown,
        "by_sport_24h": sport_breakdown_24h,
        "by_sport_7d": sport_breakdown_7d,
        "hourly_history": history[-168:],  # last 7 days
        "budget": {
            "total": total_budget,
            "days_in_month": days_in_month,
            "day_of_month": day_of_month,
            "days_remaining": days_remaining,
            "linear_daily_budget": round(linear_daily_budget),
            "pace_48h_daily": round(pace_48h),
            "projected_eom": projected_eom,
            "projected_surplus": total_budget - projected_eom,
        },
    }


# ---------------------------------------------------------------------------
# 2. Source Coverage
# ---------------------------------------------------------------------------

_TIER1_SPORTS = [
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "baseball_mlb",
    "basketball_ncaab",
    "golf_pga",
]


async def _query_event_source_coverage(db: AsyncSession) -> list[dict[str, Any]]:
    """2a. Event-level source coverage (last 7 days to +2 days).

    LAT-P017 (#1608): this query used to time out at the section's 10s bound,
    which darkened four dashboard panels. Three shape defects, each measured
    against production before and after:

    1. ``wp_sources`` carried ``captured_at >= NOW() - 7 days``. That column is
       NOT in ``ix_winprob_event_source (event_id, source)``, so the predicate
       broke the index-only scan and forced a heap fetch per candidate row
       against a visibility map last vacuumed days earlier. Dropping it took the
       win-prob arm from 7,927ms to 549ms on an identical 1-day window.
       SEMANTIC CHANGE, deliberate: a source that recorded a win-prob snapshot
       for an in-window event now counts as covering it regardless of when the
       snapshot was taken. The old filter silently under-counted pre-game
       coverage of upcoming events. Measured blast radius on a 1-day window: one
       cell moved (boxing_boxing kalshi 4 -> 5).
    2. The two ``LEFT JOIN``s were row-multiplying (one row per event x source),
       so ``COUNT(*) AS total_events`` counted JOINED ROWS, not events, and
       every ``COUNT(DISTINCT ...)`` paid to de-duplicate the explosion. The
       source sets are now pre-aggregated to one row per event, which makes the
       joins 1:1 and ``COUNT(*)`` a true event count.
    3. ``recent_events`` selected ``win_probability_sources`` (a large JSONB)
       that no output field reads.

    Measured on production: >10,300ms (statement timeout, panel dark) -> 1,307ms
    for the full 7-day window.
    """
    coverage_q = await db.execute(text("""
        WITH recent_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.external_id, e.espn_id, e.statpal_fixture_id,
                   e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE e.commence_time >= NOW() - INTERVAL '7 days'
              AND e.commence_time <= NOW() + INTERVAL '2 days'
        ),
        wp_pairs AS (
            SELECT DISTINCT wp.event_id, wp.source
            FROM win_prob_snapshots wp
            JOIN recent_events re ON re.id = wp.event_id
        ),
        wp AS (
            SELECT event_id,
                   bool_or(source = 'espn') AS espn,
                   bool_or(source = 'stat_model') AS model,
                   bool_or(source = 'mlb') AS mlb,
                   bool_or(source = 'kalshi') AS kalshi,
                   bool_or(source = 'polymarket') AS poly
            FROM wp_pairs GROUP BY event_id
        ),
        pm_pairs AS (
            SELECT DISTINCT fm.event_id, fm.source
            FROM futures_markets fm
            JOIN recent_events re ON re.id = fm.event_id
            WHERE fm.source IN ('kalshi', 'polymarket')
        ),
        pm AS (
            SELECT event_id,
                   bool_or(source = 'kalshi') AS kalshi,
                   bool_or(source = 'polymarket') AS poly
            FROM pm_pairs GROUP BY event_id
        )
        SELECT
            re.sport_key,
            COUNT(*) AS total_events,
            COUNT(*) FILTER (WHERE re.status = 'live') AS live_events,
            COUNT(re.external_id) AS has_odds_api,
            COUNT(re.espn_id) AS has_espn,
            COUNT(re.statpal_fixture_id) AS has_statpal,
            COUNT(*) FILTER (WHERE wp.espn) AS has_espn_wp,
            COUNT(*) FILTER (WHERE wp.model) AS has_model,
            COUNT(*) FILTER (WHERE wp.mlb) AS has_mlb,
            COUNT(*) FILTER (WHERE wp.kalshi) AS has_kalshi_wp,
            COUNT(*) FILTER (WHERE wp.poly) AS has_polymarket_wp,
            COUNT(*) FILTER (WHERE pm.kalshi) AS has_kalshi_pm,
            COUNT(*) FILTER (WHERE pm.poly) AS has_polymarket_pm
        FROM recent_events re
        LEFT JOIN wp ON wp.event_id = re.id
        LEFT JOIN pm ON pm.event_id = re.id
        GROUP BY re.sport_key
        ORDER BY COUNT(*) DESC
    """))
    return [
        {
            "sport": r.sport_key,
            "total": r.total_events,
            "live": r.live_events,
            "odds_api": r.has_odds_api,
            "espn": r.has_espn,
            "statpal": r.has_statpal,
            "espn_wp": r.has_espn_wp,
            "model": r.has_model,
            "mlb": r.has_mlb,
            "kalshi": max(r.has_kalshi_wp, r.has_kalshi_pm),
            "polymarket": max(r.has_polymarket_wp, r.has_polymarket_pm),
            "expected_sources": _expected_sources_for_sport(r.sport_key),
        }
        for r in coverage_q.all()
    ]


async def _query_sport_activity(db: AsyncSession) -> dict[str, int]:
    """2a-ii. Per-sport snapshot counts (proxy for API activity)."""
    sport_activity_q = await db.execute(text("""
        SELECT s.key AS sport_key,
               COUNT(*) AS snapshots_24h
        FROM odds_snapshots os
        JOIN events e ON os.event_id = e.id
        JOIN sports s ON e.sport_id = s.id
        WHERE os.captured_at >= NOW() - INTERVAL '24 hours'
        GROUP BY s.key
        ORDER BY COUNT(*) DESC
    """))
    return {r.sport_key: r.snapshots_24h for r in sport_activity_q.all()}


async def _query_coverage_trend(
    db: AsyncSession, now: datetime
) -> list[dict[str, Any]]:
    """2a-iii. Trended coverage for top-tier sports (daily %)."""
    trend_q = await db.execute(
        text("""
            WITH daily_events AS (
                SELECT
                    DATE(e.commence_time) AS event_date,
                    s.key AS sport_key,
                    COUNT(*) AS total,
                    COUNT(e.external_id) AS has_odds_api,
                    COUNT(e.espn_id) AS has_espn,
                    COUNT(e.statpal_fixture_id) AS has_statpal
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                WHERE s.key = ANY(:sports)
                  AND e.commence_time >= NOW() - INTERVAL '14 days'
                  AND e.commence_time <= NOW() + INTERVAL '30 days'
                GROUP BY DATE(e.commence_time), s.key
                HAVING COUNT(*) >= 1
            )
            SELECT * FROM daily_events
            ORDER BY sport_key, event_date
        """),
        {"sports": _TIER1_SPORTS},
    )
    coverage_trend_raw = trend_q.all()

    # Win-prob source coverage per day for past events.
    # Include prediction market links (event_id IS NOT NULL) alongside
    # win_prob_snapshots so Kalshi/Polymarket coverage reflects game-market
    # linking, not just live win-probability polling.
    # LAT-P017 (#1608): the ``wp`` CTE was a DISTINCT over the ENTIRE
    # win_prob_snapshots table (1.9M rows, no predicate at all) and ``pm`` over
    # every linked futures market, to answer a question about a 14-day event
    # window. Cost scaled with table volume instead of with the size of the
    # answer, so this was the section's SECOND independent timeout — reachable
    # only once the first was fixed. Both source sets are now scoped to the
    # windowed events and pre-aggregated to one row per event, so the joins are
    # 1:1 rather than row-multiplying.
    # Measured on production: >10,248ms (statement timeout) -> 1,598ms.
    wp_trend_q = await db.execute(
        text("""
            WITH ev AS (
                SELECT e.id,
                       DATE(e.commence_time) AS event_date,
                       s.key AS sport_key
                FROM events e
                JOIN sports s ON e.sport_id = s.id
                WHERE s.key = ANY(:sports)
                  AND e.commence_time >= NOW() - INTERVAL '14 days'
                  AND e.commence_time <= NOW()
            ),
            wp_pairs AS (
                SELECT DISTINCT wp.event_id, wp.source
                FROM win_prob_snapshots wp
                JOIN ev ON ev.id = wp.event_id
            ),
            pm_pairs AS (
                SELECT DISTINCT fm.event_id, fm.source
                FROM futures_markets fm
                JOIN ev ON ev.id = fm.event_id
                WHERE fm.source IN ('kalshi', 'polymarket')
            ),
            wp AS (
                SELECT event_id,
                       bool_or(source = 'espn') AS espn,
                       bool_or(source = 'stat_model') AS model,
                       bool_or(source = 'kalshi') AS kalshi,
                       bool_or(source = 'polymarket') AS poly
                FROM wp_pairs GROUP BY event_id
            ),
            pm AS (
                SELECT event_id,
                       bool_or(source = 'kalshi') AS kalshi,
                       bool_or(source = 'polymarket') AS poly
                FROM pm_pairs GROUP BY event_id
            )
            SELECT
                ev.event_date,
                ev.sport_key,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE wp.espn) AS espn_wp,
                COUNT(*) FILTER (WHERE wp.model) AS model,
                GREATEST(
                    COUNT(*) FILTER (WHERE wp.kalshi),
                    COUNT(*) FILTER (WHERE pm.kalshi)
                ) AS kalshi,
                GREATEST(
                    COUNT(*) FILTER (WHERE wp.poly),
                    COUNT(*) FILTER (WHERE pm.poly)
                ) AS polymarket
            FROM ev
            LEFT JOIN wp ON wp.event_id = ev.id
            LEFT JOIN pm ON pm.event_id = ev.id
            GROUP BY ev.event_date, ev.sport_key
        """),
        {"sports": _TIER1_SPORTS},
    )
    wp_trend_raw = {
        (r.event_date.isoformat(), r.sport_key): r for r in wp_trend_q.all()
    }

    coverage_trend: list[dict[str, Any]] = []
    for r in coverage_trend_raw:
        entry: dict[str, Any] = {
            "date": r.event_date.isoformat(),
            "sport": r.sport_key,
            "total": r.total,
            "odds_api_pct": round(r.has_odds_api / r.total * 100) if r.total else 0,
            "espn_pct": round(r.has_espn / r.total * 100) if r.total else 0,
            "statpal_pct": round(r.has_statpal / r.total * 100) if r.total else 0,
            "is_future": r.event_date > now.date(),
        }
        wp_key = (r.event_date.isoformat(), r.sport_key)
        if wp_key in wp_trend_raw:
            wp = wp_trend_raw[wp_key]
            entry["espn_wp_pct"] = round(wp.espn_wp / wp.total * 100) if wp.total else 0
            entry["model_pct"] = round(wp.model / wp.total * 100) if wp.total else 0
            entry["kalshi_pct"] = round(wp.kalshi / wp.total * 100) if wp.total else 0
            entry["polymarket_pct"] = round(wp.polymarket / wp.total * 100) if wp.total else 0
        coverage_trend.append(entry)

    return coverage_trend


async def _query_futures_coverage(db: AsyncSession) -> list[dict[str, Any]]:
    """2b. Futures-level source coverage (by sport category)."""
    futures_q = await db.execute(text("""
        SELECT
            COALESCE(s.key, fm.llm_sport_category, 'unknown') AS sport_key,
            COUNT(DISTINCT fm.id) AS total_markets,
            COUNT(DISTINCT CASE WHEN fm.source = 'odds_api' THEN fm.id END) AS odds_api,
            COUNT(DISTINCT CASE WHEN fm.source = 'kalshi' THEN fm.id END) AS kalshi,
            COUNT(DISTINCT CASE WHEN fm.source = 'polymarket' THEN fm.id END) AS polymarket,
            COUNT(DISTINCT CASE WHEN fm.source = 'datagolf' THEN fm.id END) AS datagolf
        FROM futures_markets fm
        LEFT JOIN sports s ON fm.sport_id = s.id
        WHERE (fm.market_type IS NULL OR fm.market_type != 'game')
          AND fm.event_id IS NULL
        GROUP BY COALESCE(s.key, fm.llm_sport_category, 'unknown')
        ORDER BY COUNT(DISTINCT fm.id) DESC
    """))
    return [
        {
            "sport": r.sport_key,
            "total_markets": r.total_markets,
            "odds_api": r.odds_api,
            "kalshi": r.kalshi,
            "polymarket": r.polymarket,
            "datagolf": r.datagolf,
        }
        for r in futures_q.all()
    ]


async def run_db_panel(
    db: AsyncSession,
    panel: str,
    build: Callable[[], Awaitable[Any]],
    *,
    on_error: Callable[[str], Any],
    statement_timeout: str | None = None,
) -> Any:
    """Run one dashboard panel in its own transaction scope.

    LAT-P017 (#1608) — THE CASCADE FIX, which is a separate defect from any
    single slow query and outlives fixing one.

    Every DB-backed panel shares one ``Depends(get_db)`` session. When a panel
    caught a ``QueryCanceledError`` it swallowed it and returned an error
    marker, but never rolled back, so the session was left holding an ABORTED
    transaction. Every later panel then died on
    ``InFailedSQLTransactionError`` — measured in production 2026-08-09: one
    timeout in ``source_coverage`` darkened ``database`` and
    ``game_state_coverage``, neither of which was slow.

    Rolling back on BOTH paths also scopes ``SET LOCAL statement_timeout`` to
    the panel that set it, instead of leaking one panel's bound onto the next.
    Read-only work, so a rollback discards nothing.

    ``statement_timeout`` is applied INSIDE this panel's own transaction.
    ``SET LOCAL`` is transaction-scoped, so a bound set before the isolation
    boundary would be discarded by the first rollback and silently stop
    applying to every later panel.
    """
    try:
        if statement_timeout:
            # asyncpg cannot run "SET LOCAL ...; SELECT ..." as one prepared
            # statement (gotcha #45 class — #232): separate execute, same txn.
            await db.execute(text(f"SET LOCAL statement_timeout = '{statement_timeout}'"))
        result = await build()
    except Exception as e:
        await db.rollback()
        return on_error(str(e))
    await db.rollback()
    return result


async def build_source_coverage_section(
    db: AsyncSession, now: datetime
) -> tuple[list[dict], list[dict], list[dict]]:
    """Build all source-coverage data.

    Returns ``(source_coverage, coverage_trend, futures_coverage)``.

    LAT-P017 (#1608): these three outputs are now isolated from each other.
    Previously ONE try wrapped all of them, so a single timeout produced
    ``[{"error": e}], [], [{"error": e}]`` — meaning (a) ``futures_coverage``
    reported a failure it never actually suffered, its error string a copy of a
    neighbour's, and (b) ``coverage_trend`` degraded to a BARE EMPTY LIST with
    no marker at all, indistinguishable from "there is genuinely no trend data".
    That silent one is gotcha #53 exactly, and it is the reason this class went
    unnoticed: the endpoint returned HTTP 200 and the panel just looked empty.
    Each query now fails on its own behalf or not at all, and no failure can
    present as absence.
    """
    source_coverage = await run_db_panel(
        db, "source_coverage",
        lambda: _query_event_source_coverage(db),
        on_error=lambda e: [{"error": e}],
        statement_timeout=_PANEL_STATEMENT_TIMEOUT,
    )
    if source_coverage and "error" not in source_coverage[0]:
        sport_activity = await run_db_panel(
            db, "sport_activity",
            lambda: _query_sport_activity(db),
            on_error=lambda e: {},
            statement_timeout=_PANEL_STATEMENT_TIMEOUT,
        )
        for row in source_coverage:
            row["snapshots_24h"] = sport_activity.get(row["sport"], 0)

    coverage_trend = await run_db_panel(
        db, "coverage_trend",
        lambda: _query_coverage_trend(db, now),
        # NEVER a bare [] on failure: an empty trend is a legitimate answer, so
        # a failure that returned one would be silently indistinguishable from
        # it. The marker is what makes the difference visible.
        on_error=lambda e: [{"error": e}],
        statement_timeout=_PANEL_STATEMENT_TIMEOUT,
    )
    futures_coverage = await run_db_panel(
        db, "futures_coverage",
        lambda: _query_futures_coverage(db),
        on_error=lambda e: [{"error": e}],
        statement_timeout=_PANEL_STATEMENT_TIMEOUT,
    )

    return source_coverage, coverage_trend, futures_coverage


# ---------------------------------------------------------------------------
# 3. Worker Task Metrics
# ---------------------------------------------------------------------------

_ESSENTIAL_TASKS = {
    "poll_odds",
    "espn_sync",
    "statpal_livescores",
    "statpal_schedules",
    "prediction_market_match",
    "prediction_market_live",
    "mlb_sync",
    "discover_events",
    "transition_statuses",
}


def build_worker_section(now: datetime) -> dict[str, Any]:
    """Build worker health and task metrics from Redis."""
    from app.tasks.redis_state import get_all_task_metrics, get_redis_client

    tasks = get_all_task_metrics()

    # Worker heartbeat
    try:
        r = get_redis_client()
        heartbeat = r.get("bainluck:heartbeat")
        if heartbeat:
            heartbeat_time = datetime.fromisoformat(heartbeat.decode())
            heartbeat_age = (now - heartbeat_time).total_seconds()
            worker_status = "healthy" if heartbeat_age < 180 else "unhealthy"
        else:
            heartbeat_age = None
            worker_status = "unknown"
    except Exception:
        heartbeat_age = None
        worker_status = "error"

    critical_tasks = [t for t in tasks if t.get("health") == "critical"]
    degraded_tasks = [t for t in tasks if t.get("health") == "degraded"]
    essential_critical = [t for t in critical_tasks if t.get("task") in _ESSENTIAL_TASKS]

    return {
        "worker_status": worker_status,
        "heartbeat_age_seconds": round(heartbeat_age) if heartbeat_age else None,
        "overall_health": (
            "worker_down"
            if worker_status != "healthy"
            else "critical"
            if essential_critical
            else "degraded"
            if critical_tasks or degraded_tasks
            else "healthy"
            if tasks
            else "no_data"
        ),
        "critical_tasks": [t["task"] for t in critical_tasks],
        "degraded_tasks": [t["task"] for t in degraded_tasks],
        "tasks": tasks,
    }


# ---------------------------------------------------------------------------
# 4. Database Health
# ---------------------------------------------------------------------------

async def build_database_section(db: AsyncSession) -> dict[str, Any]:
    """Build database health stats (sizes, growth, dead tuples, trends).

    LAT-P017 (#1608): no longer swallows its own exceptions. Error handling is
    centralised in :func:`run_db_panel`, which ALSO rolls the session back — a
    local ``except: return {"error": ...}`` here could not do that, so a caught
    failure left the shared transaction aborted and took out every panel after
    it. A handler that hides the error from the isolator defeats the isolation.
    """
    db_q = await db.execute(text("""
        SELECT
            (SELECT COUNT(*) FROM events WHERE status IN ('live', 'scheduled')
             AND commence_time >= NOW() - INTERVAL '1 day') AS active_events,
            (SELECT COUNT(*) FROM events WHERE status = 'live') AS live_events,
            (SELECT COUNT(*) FROM odds_snapshots
             WHERE captured_at >= NOW() - INTERVAL '1 hour') AS snapshots_last_hour,
            (SELECT COUNT(*) FROM win_prob_snapshots
             WHERE captured_at >= NOW() - INTERVAL '1 hour') AS winprob_last_hour,
            (SELECT pg_database_size(current_database())) AS db_size_bytes,
            (SELECT MIN(captured_at) FROM odds_snapshots
             WHERE captured_at >= NOW() - INTERVAL '7 days') AS oldest_snapshot_7d
    """))
    db_row = db_q.one()

    db_size_mb = db_row.db_size_bytes / 1024 / 1024
    db_size_gb = db_row.db_size_bytes / (1024**3)

    growth_rate_mb_per_day, days_until_full = await _compute_growth_rate(
        db, db_size_gb
    )

    table_sizes = await _query_table_sizes(db)
    dead_tuples = await _query_dead_tuples(db)

    total_live = sum(d["live_tuples"] for d in dead_tuples)
    total_dead = sum(d["dead_tuples"] for d in dead_tuples)

    # Record DB size for trending and fetch history
    from app.tasks.redis_state import record_db_size, get_db_size_history

    record_db_size(db_size_mb)
    db_size_trend = get_db_size_history(days=90)

    return {
        "active_events": db_row.active_events,
        "live_events": db_row.live_events,
        "snapshots_last_hour": db_row.snapshots_last_hour,
        "winprob_last_hour": db_row.winprob_last_hour,
        "db_size_mb": round(db_size_mb, 1),
        "growth_rate_mb_per_day": growth_rate_mb_per_day,
        "days_until_full": days_until_full,
        "table_sizes": table_sizes,
        "dead_tuples": dead_tuples,
        "total_live_tuples": total_live,
        "total_dead_tuples": total_dead,
        "dead_tuple_pct": round(
            total_dead / max(total_live + total_dead, 1) * 100, 1
        ),
        "size_trend": db_size_trend,
        "plan": {
            "name": "standard-0",
            "storage_limit_gb": 64,
            "storage_used_gb": round(db_size_gb, 2),
            "storage_pct": round(db_size_gb / 64 * 100, 1),
            "connections_limit": 200,
        },
    }


async def _compute_growth_rate(
    db: AsyncSession, db_size_gb: float
) -> tuple[float | None, int | None]:
    """Estimate daily DB growth from snapshot row counts."""
    try:
        growth_q = await db.execute(text("""
            SELECT
                COALESCE((SELECT COUNT(*) FROM odds_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS odds_rows_24h,
                COALESCE((SELECT COUNT(*) FROM win_prob_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS wp_rows_24h,
                COALESCE((SELECT COUNT(*) FROM futures_odds_snapshots
                 WHERE captured_at >= NOW() - INTERVAL '24 hours'), 0) AS futures_rows_24h
        """))
        g = growth_q.one()
        # Rough estimate: odds ~500B/row, winprob ~300B/row, futures ~400B/row
        daily_bytes = (
            (g.odds_rows_24h * 500)
            + (g.wp_rows_24h * 300)
            + (g.futures_rows_24h * 400)
        )
        growth_rate_mb_per_day = round(daily_bytes / 1024 / 1024, 1)
        storage_limit_gb = 64  # standard-0 plan
        remaining_gb = storage_limit_gb - db_size_gb
        days_until_full: int | None = None
        if growth_rate_mb_per_day > 0:
            days_until_full = round((remaining_gb * 1024) / growth_rate_mb_per_day)
        return growth_rate_mb_per_day, days_until_full
    except Exception:
        return None, None


async def _query_table_sizes(db: AsyncSession) -> list[dict[str, Any]]:
    """Get all table sizes, sorted largest first."""
    table_q = await db.execute(text("""
        SELECT
            tablename,
            pg_total_relation_size('public.' || tablename) AS size_bytes
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY pg_total_relation_size('public.' || tablename) DESC
    """))
    return [
        {"table": r.tablename, "size_mb": round(r.size_bytes / 1024 / 1024, 1)}
        for r in table_q.all()
    ]


async def _query_dead_tuples(db: AsyncSession) -> list[dict[str, Any]]:
    """Dead tuple stats from ``pg_stat_user_tables``."""
    dead_tuple_q = await db.execute(text("""
        SELECT relname, n_live_tup, n_dead_tup,
               last_autovacuum, last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = 'public'
          AND n_live_tup + n_dead_tup > 1000
        ORDER BY n_dead_tup DESC
    """))
    return [
        {
            "table": r.relname,
            "live_tuples": r.n_live_tup,
            "dead_tuples": r.n_dead_tup,
            "dead_pct": round(
                r.n_dead_tup / max(r.n_live_tup + r.n_dead_tup, 1) * 100, 1
            ),
            "last_autovacuum": (
                r.last_autovacuum.isoformat() if r.last_autovacuum else None
            ),
        }
        for r in dead_tuple_q.all()
    ]


# ---------------------------------------------------------------------------
# 5. Matching Metrics
# ---------------------------------------------------------------------------

def build_matching_metrics() -> list[dict]:
    """Fetch matching metrics history from Redis."""
    try:
        from app.tasks.matching_audit import get_matching_metrics_history

        return get_matching_metrics_history(days=90)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# 6. Game State Indicators
# ---------------------------------------------------------------------------

_INDICATORS_BASE_SQL = """
    WITH completed_events AS (
        SELECT e.id AS event_id, s.key AS sport_key
        FROM events e
        JOIN sports s ON s.id = e.sport_id
        WHERE e.status IN ('completed', 'closed')
          AND e.commence_time >= NOW() - INTERVAL '14 days'
          AND e.espn_id IS NOT NULL
    ),
    indicators AS (
        SELECT ce.event_id, ce.sport_key, sp.period AS indicator
        FROM completed_events ce
        JOIN scoring_plays sp ON sp.event_id = ce.event_id
        WHERE sp.period IS NOT NULL
        UNION
        SELECT ce.event_id, ce.sport_key, es.period AS indicator
        FROM completed_events ce
        JOIN espn_snapshots es ON es.event_id = ce.event_id
        WHERE es.period IS NOT NULL
        UNION
        SELECT ce.event_id, ce.sport_key,
               wp.game_state->>'period' AS indicator
        FROM completed_events ce
        JOIN win_prob_snapshots wp ON wp.event_id = ce.event_id
        WHERE wp.game_state->>'period' IS NOT NULL
    ),
    per_event AS (
        SELECT event_id, sport_key,
               COUNT(DISTINCT indicator) AS indicator_count
        FROM indicators
        GROUP BY event_id, sport_key
    )
"""


async def build_game_state_section(db: AsyncSession) -> list[dict[str, Any]]:
    """Build game state indicator coverage by sport.

    LAT-P017 (#1608): error handling centralised in :func:`run_db_panel` so a
    failure rolls the shared session back instead of aborting later panels.
    This panel was a CASCADE VICTIM in production, not a slow query — it failed
    with InFailedSQLTransactionError because source_coverage timed out first.
    """
    from app.utils.sport_keys import EXPECTED_GAME_STATE_INDICATORS

    # The 15s bound now comes from run_db_panel, which issues its SET LOCAL
    # inside this panel's own transaction. asyncpg cannot run
    # "SET LOCAL ...; SELECT ..." as one prepared statement (gotcha #45 class —
    # #232), so it stays a separate execute in the same transaction.
    gs_sql = text(
        _INDICATORS_BASE_SQL
        + """
        SELECT sport_key,
               COUNT(*) AS total_events,
               MIN(indicator_count) AS min_indicators,
               MAX(indicator_count) AS max_indicators,
               ROUND(AVG(indicator_count), 1) AS avg_indicators,
               COUNT(*) FILTER (WHERE indicator_count = 0) AS zero_count
        FROM per_event
        GROUP BY sport_key
        ORDER BY total_events DESC
    """
    )
    gs_result = await db.execute(gs_sql)
    gs_rows = gs_result.fetchall()

    game_state_section: list[dict[str, Any]] = []
    for row in gs_rows:
        sport_key = row[0]
        total = int(row[1])
        min_ind = int(row[2])
        max_ind = int(row[3])
        avg_ind = float(row[4])
        zero_count = int(row[5])
        expected = EXPECTED_GAME_STATE_INDICATORS.get(sport_key)

        entry: dict[str, Any] = {
            "sport_key": sport_key,
            "total_events": total,
            "min_indicators": min_ind,
            "max_indicators": max_ind,
            "avg_indicators": avg_ind,
            "zero_count": zero_count,
            "expected": expected,
            "type": "fixed" if expected is not None else "variable",
        }
        game_state_section.append(entry)

    # Second pass for fixed sports: get actual bucket counts
    if any(e["type"] == "fixed" for e in game_state_section):
        await _fill_fixed_sport_buckets(db, game_state_section)

    return game_state_section


async def _fill_fixed_sport_buckets(
    db: AsyncSession,
    game_state_section: list[dict[str, Any]],
) -> None:
    """For fixed-period sports, add met/under/over bucket counts in place."""
    # Separate SET LOCAL from the CTE query — asyncpg rejects multi-command
    # prepared statements (gotcha #45 class — #232).
    bucket_sql = text(
        _INDICATORS_BASE_SQL
        + """
        SELECT sport_key, indicator_count, COUNT(*) AS cnt
        FROM per_event
        GROUP BY sport_key, indicator_count
        ORDER BY sport_key, indicator_count
    """
    )
    await db.execute(text("SET LOCAL statement_timeout = '15s'"))
    bucket_result = await db.execute(bucket_sql)
    bucket_rows = bucket_result.fetchall()

    # Build lookup: sport_key -> {indicator_count: count}
    buckets: dict[str, dict[int, int]] = {}
    for brow in bucket_rows:
        sk = brow[0]
        ic = int(brow[1])
        cnt = int(brow[2])
        buckets.setdefault(sk, {})[ic] = cnt

    for entry in game_state_section:
        if entry["type"] != "fixed":
            continue
        sk = entry["sport_key"]
        expected = entry["expected"]
        sport_buckets = buckets.get(sk, {})
        met = 0
        under = 0
        over = 0
        for ic, cnt in sport_buckets.items():
            if ic == expected:
                met += cnt
            elif ic < expected:
                under += cnt
            else:
                over += cnt
        entry["met"] = met
        entry["under"] = under
        entry["over"] = over
        entry["pct_met"] = round(met / max(entry["total_events"], 1) * 100, 1)
