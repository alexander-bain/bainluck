"""Helper functions for the admin operations dashboard.

Each function builds one section of the ``/api/admin/dashboard`` response.
They are designed to be independently testable and to keep the route handler
thin.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

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

from sqlalchemy.ext.asyncio import AsyncSession


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
    """2a. Event-level source coverage (last 7 days to +2 days)."""
    coverage_q = await db.execute(text("""
        WITH recent_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.external_id, e.espn_id, e.statpal_fixture_id,
                   e.win_probability_sources,
                   e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE e.commence_time >= NOW() - INTERVAL '7 days'
              AND e.commence_time <= NOW() + INTERVAL '2 days'
        ),
        pm_links AS (
            SELECT DISTINCT fm.event_id, fm.source AS pm_source
            FROM futures_markets fm
            WHERE fm.event_id IS NOT NULL
              AND fm.source IN ('kalshi', 'polymarket')
        ),
        wp_sources AS (
            SELECT DISTINCT wp.event_id, wp.source AS wp_source
            FROM win_prob_snapshots wp
            WHERE wp.captured_at >= NOW() - INTERVAL '7 days'
        )
        SELECT
            re.sport_key,
            COUNT(*) AS total_events,
            COUNT(CASE WHEN re.status = 'live' THEN 1 END) AS live_events,
            COUNT(re.external_id) AS has_odds_api,
            COUNT(re.espn_id) AS has_espn,
            COUNT(re.statpal_fixture_id) AS has_statpal,
            COUNT(DISTINCT CASE WHEN wp.wp_source = 'espn' THEN re.id END) AS has_espn_wp,
            COUNT(DISTINCT CASE WHEN wp.wp_source = 'stat_model' THEN re.id END) AS has_model,
            COUNT(DISTINCT CASE WHEN wp.wp_source = 'mlb' THEN re.id END) AS has_mlb,
            COUNT(DISTINCT CASE WHEN wp.wp_source = 'kalshi' THEN re.id END) AS has_kalshi_wp,
            COUNT(DISTINCT CASE WHEN wp.wp_source = 'polymarket' THEN re.id END) AS has_polymarket_wp,
            COUNT(DISTINCT CASE WHEN pm.pm_source = 'kalshi' THEN re.id END) AS has_kalshi_pm,
            COUNT(DISTINCT CASE WHEN pm.pm_source = 'polymarket' THEN re.id END) AS has_polymarket_pm
        FROM recent_events re
        LEFT JOIN pm_links pm ON pm.event_id = re.id
        LEFT JOIN wp_sources wp ON wp.event_id = re.id
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
    wp_trend_q = await db.execute(
        text("""
            WITH wp AS (
                SELECT DISTINCT wp.event_id, wp.source
                FROM win_prob_snapshots wp
            ),
            pm AS (
                SELECT DISTINCT fm.event_id, fm.source
                FROM futures_markets fm
                WHERE fm.event_id IS NOT NULL
                  AND fm.source IN ('kalshi', 'polymarket')
            )
            SELECT
                DATE(e.commence_time) AS event_date,
                s.key AS sport_key,
                COUNT(DISTINCT e.id) AS total,
                COUNT(DISTINCT CASE WHEN wp.source = 'espn' THEN e.id END) AS espn_wp,
                COUNT(DISTINCT CASE WHEN wp.source = 'stat_model' THEN e.id END) AS model,
                GREATEST(
                    COUNT(DISTINCT CASE WHEN wp.source = 'kalshi' THEN e.id END),
                    COUNT(DISTINCT CASE WHEN pm.source = 'kalshi' THEN e.id END)
                ) AS kalshi,
                GREATEST(
                    COUNT(DISTINCT CASE WHEN wp.source = 'polymarket' THEN e.id END),
                    COUNT(DISTINCT CASE WHEN pm.source = 'polymarket' THEN e.id END)
                ) AS polymarket
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            LEFT JOIN wp ON wp.event_id = e.id
            LEFT JOIN pm ON pm.event_id = e.id
            WHERE s.key = ANY(:sports)
              AND e.commence_time >= NOW() - INTERVAL '14 days'
              AND e.commence_time <= NOW()
            GROUP BY DATE(e.commence_time), s.key
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


async def build_source_coverage_section(
    db: AsyncSession, now: datetime
) -> tuple[list[dict], list[dict], list[dict]]:
    """Build all source-coverage data.

    Returns ``(source_coverage, coverage_trend, futures_coverage)``.
    On error, returns lists with a single ``{"error": ...}`` entry.
    """
    try:
        await db.execute(text("SET LOCAL statement_timeout = '10s'"))

        source_coverage = await _query_event_source_coverage(db)
        sport_activity = await _query_sport_activity(db)

        # Attach snapshot counts to coverage rows
        for row in source_coverage:
            row["snapshots_24h"] = sport_activity.get(row["sport"], 0)

        coverage_trend = await _query_coverage_trend(db, now)
        futures_coverage = await _query_futures_coverage(db)

        return source_coverage, coverage_trend, futures_coverage
    except Exception as e:
        return [{"error": str(e)}], [], [{"error": str(e)}]


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
    """Build database health stats (sizes, growth, dead tuples, trends)."""
    try:
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
    except Exception as e:
        return {"error": str(e)}


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
    """Build game state indicator coverage by sport."""
    try:
        from app.utils.sport_keys import EXPECTED_GAME_STATE_INDICATORS

        # asyncpg cannot run "SET LOCAL ...; SELECT ..." as one prepared
        # statement (gotcha #45 class — #232) — it must be a separate execute in
        # the same transaction, or the whole tile errors out.
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
        await db.execute(text("SET LOCAL statement_timeout = '15s'"))
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
    except Exception as e:
        return [{"error": str(e)}]


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
