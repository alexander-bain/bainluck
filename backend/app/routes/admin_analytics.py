"""Admin analytics endpoints powered by GA4 Data API.

All endpoints require the admin secret and cache responses in Redis
to avoid hammering the GA4 API on repeated loads.
"""

from datetime import date, datetime, timezone
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from app.routes.admin_utils import _check_admin_secret

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Redis cache helpers
# ---------------------------------------------------------------------------

_CACHE_PREFIX = "bainluck:analytics"


def _safe_cache_key_for_log(key: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ":_-" else "_" for ch in str(key or ""))


async def _cache_get(key: str) -> dict | list | None:
    """Read a JSON-serialised value from Redis."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        raw = await rc.get(f"{_CACHE_PREFIX}:{key}")
        await rc.aclose()
        if raw:
            return json.loads(raw)
    except Exception:
        logger.debug("Redis cache miss/error for %s", _safe_cache_key_for_log(key))
    return None


async def _cache_set(key: str, data: Any, ttl_seconds: int) -> None:
    """Write a JSON-serialised value to Redis with a TTL."""
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        await rc.setex(f"{_CACHE_PREFIX}:{key}", ttl_seconds, json.dumps(data, default=str))
        await rc.aclose()
    except Exception:
        logger.debug("Redis cache write error for %s", _safe_cache_key_for_log(key))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

CACHE_TTL_STANDARD = 3600  # 1 hour
CACHE_TTL_REALTIME = 300   # 5 minutes

# ---------------------------------------------------------------------------
# Shared classification & period helpers (#13261 Row 1)
# ---------------------------------------------------------------------------

_PERIOD_START_MAP: dict[str, str] = {
    "7d": "7daysAgo",
    "14d": "14daysAgo",
    "30d": "30daysAgo",
    "90d": "90daysAgo",
}

_DISCOVER_EVENT_NAMES: frozenset[str] = frozenset({
    # Live event names (#13261)
    "feed_card_action",
    "feed_card_impression",
    "prediction_submit",
    "prediction_make",
    "session_open",
    "return_visit",
    "shared_link_open",
    "scroll_depth",
    "search",
    "search_result_click",
    # Legacy names preserved for historical continuity
    "page_view",
    "scroll",
    "feed_card_click",
    "feed_card_view",
    "higher_lower_play",
    "higher_lower_result",
    "discover_swipe",
    "discover_card_click",
    "discover_scroll_depth",
    "engagement_time",
    "session_start",
    "first_visit",
})

_FUNNEL_VISIT_EVENTS: frozenset[str] = frozenset({
    "session_start",
    "first_visit",
    "page_view",
    "session_open",
    "screen_view",
})
_FUNNEL_INTERACT_EVENTS: frozenset[str] = frozenset({
    "feed_card_action",
    "feed_card_impression",
    "discover_swipe",
    "discover_card_click",
    "feed_card_click",
    "feed_card_view",
    "discover_scroll_depth",
    "scroll_depth",
    "search",
    "search_result_click",
    "shared_link_open",
})
_FUNNEL_GUESS_EVENTS: frozenset[str] = frozenset({
    "prediction_submit",
    "prediction_make",
    "higher_lower_play",
    "higher_lower_result",
})
_FUNNEL_SIGNUP_EVENTS: frozenset[str] = frozenset({"sign_up", "login"})


_CANONICAL_PERIODS: dict[str, str] = {
    "7d": "7d",
    "14d": "14d",
    "30d": "30d",
    "90d": "90d",
}


def _normalize_period(period: str, *, default: str = "30d") -> str:
    norm = str(period or "").strip().lower()
    return _CANONICAL_PERIODS.get(norm, default)


def _period_to_start_date(period: str, *, default: str = "30daysAgo") -> str:
    return _PERIOD_START_MAP.get(str(period or "").strip().lower(), default)


def _is_discover_event(event_name: str) -> bool:
    name = str(event_name or "").strip()
    return (
        name in _DISCOVER_EVENT_NAMES
        or name.startswith(("discover_", "higher_lower_", "feed_", "prediction_"))
    )


def _classify_funnel_stage(event_name: str) -> str | None:
    name = str(event_name or "").strip()
    if name in _FUNNEL_VISIT_EVENTS:
        return "visit"
    if name in _FUNNEL_INTERACT_EVENTS or name.startswith(("discover_", "feed_card_")):
        return "interact"
    if name in _FUNNEL_GUESS_EVENTS or name.startswith(("higher_lower_", "prediction_")):
        return "guess"
    if name in _FUNNEL_SIGNUP_EVENTS:
        return "signup"
    return None


def _normalize_analytics_platform(raw_platform: str | None, event_name: str = "") -> str:
    """Split GA4 platform into canonical buckets: web, ios, watch, or other."""
    if str(event_name or "").strip().lower().startswith("watch_"):
        return "watch"
    plat = str(raw_platform or "").strip().lower()
    if plat == "web":
        return "web"
    if plat in {"ios", "iphone", "ipad"}:
        return "ios"
    if plat in {"watch", "watchos"}:
        return "watch"
    if plat == "android":
        return "android"
    return "other"


def _classify_page_section(path: str) -> str:
    """Sort URL paths into reader-facing product sections (#13261 Row 1)."""
    p = str(path or "").strip()
    if not p or p == "(not set)":
        return "app_screen"
    if p in ("/", "/discover") or p.startswith("/discover/"):
        return "discover"
    if p == "/events" or p.startswith("/events/") or p.startswith("/event/"):
        return "events"
    if p == "/search" or p.startswith("/search/"):
        return "search"
    if p == "/collections" or p.startswith("/collections/"):
        return "collections"
    if p == "/my-stuff" or p.startswith("/my-stuff/"):
        return "my_stuff"
    if p.startswith("/sports") or p.startswith("/sport/"):
        return "sports"
    if p.startswith("/weather"):
        return "weather"
    if p.startswith("/politics"):
        return "politics"
    if p.startswith("/entertainment"):
        return "entertainment"
    if p.startswith("/economics"):
        return "economics"
    if p.startswith("/calibration"):
        return "calibration"
    if p.startswith("/admin"):
        return "admin"
    if p.startswith("/futures") or p.startswith("/market/"):
        return "futures"
    if p.startswith("/team"):
        return "teams"
    return "other"


def _clean_landing_path(raw: str | None) -> str:
    """Strip query strings and fragments so no tokens or UTM noise leak into admin tables."""
    p = str(raw or "").strip()
    if not p or p == "(not set)":
        return "(not set)"
    p = p.split("#", 1)[0].split("?", 1)[0].strip()
    if not p:
        return "/"
    if not p.startswith("/") and p != "(not set)":
        p = "/" + p
    return p


def _split_source_medium(raw: str | None) -> tuple[str, str]:
    """Split GA4 sessionSourceMedium ('google / organic') into (source, medium)."""
    val = str(raw or "").strip()
    if not val:
        return ("(direct)", "(none)")
    if " / " in val:
        src, med = val.split(" / ", 1)
        return (src.strip() or "(direct)", med.strip() or "(none)")
    if "/" in val:
        src, med = val.split("/", 1)
        return (src.strip() or "(direct)", med.strip() or "(none)")
    return (val, "(none)")


def _parse_cohort_date(raw: str | None) -> date | None:
    s = str(raw or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _parse_nth_day(raw: str | None) -> int | None:
    s = str(raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _summarize_cohort_retention(
    cohort_rows: list[dict[str, Any]],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """Aggregate GA4 CohortSpec rows into Day-2 (+1d) and Day-7 (+6d) cohort retention (#13261 Row 3).

    Only cohorts old enough to have reached Day 2 (age >= 1 day) contribute to the
    Day-2 denominator, and only cohorts old enough to have reached Day 7 (age >= 6 days)
    contribute to the Day-7 denominator.
    """
    anchor = today or datetime.now(timezone.utc).date()
    by_cohort: dict[str, dict[str, Any]] = {}

    for row in cohort_rows:
        cohort_name = str(row.get("cohort", "")).strip()
        if not cohort_name:
            continue
        nth_day = _parse_nth_day(row.get("cohortNthDay"))
        if nth_day is None:
            continue
        active = int(row.get("cohortActiveUsers", 0) or 0)
        total = int(row.get("cohortTotalUsers", 0) or 0)

        entry = by_cohort.setdefault(
            cohort_name,
            {
                "cohortDate": cohort_name,
                "cohortSize": 0,
                "day2Users": 0,
                "day7Users": 0,
            },
        )
        if total > entry["cohortSize"]:
            entry["cohortSize"] = total
        if nth_day == 0 and active > entry["cohortSize"]:
            entry["cohortSize"] = active
        elif nth_day == 1:
            entry["day2Users"] = active
        elif nth_day == 6:
            entry["day7Users"] = active

    cohorts_out: list[dict[str, Any]] = []
    day2_users_sum = 0
    day2_base_sum = 0
    day7_users_sum = 0
    day7_base_sum = 0

    for cohort_name in sorted(by_cohort.keys()):
        entry = by_cohort[cohort_name]
        c_date = _parse_cohort_date(cohort_name)
        age_days = (anchor - c_date).days if c_date is not None else 7
        size = int(entry["cohortSize"])
        d2_eligible = age_days >= 1 and size > 0
        d7_eligible = age_days >= 6 and size > 0

        d2_users = int(entry["day2Users"]) if d2_eligible else 0
        d7_users = int(entry["day7Users"]) if d7_eligible else 0
        d2_rate = round(d2_users / size * 100, 1) if d2_eligible else None
        d7_rate = round(d7_users / size * 100, 1) if d7_eligible else None

        if d2_eligible:
            day2_users_sum += d2_users
            day2_base_sum += size
        if d7_eligible:
            day7_users_sum += d7_users
            day7_base_sum += size

        cohorts_out.append(
            {
                "cohortDate": cohort_name,
                "cohortSize": size,
                "day2Users": d2_users,
                "day2Rate": d2_rate,
                "day2Eligible": d2_eligible,
                "day7Users": d7_users,
                "day7Rate": d7_rate,
                "day7Eligible": d7_eligible,
            }
        )

    return {
        "day2RetentionRate": round(day2_users_sum / day2_base_sum * 100, 1)
        if day2_base_sum > 0
        else None,
        "day7RetentionRate": round(day7_users_sum / day7_base_sum * 100, 1)
        if day7_base_sum > 0
        else None,
        "day2Users": day2_users_sum,
        "day2CohortBase": day2_base_sum,
        "day7Users": day7_users_sum,
        "day7CohortBase": day7_base_sum,
        "cohorts": cohorts_out,
    }


@router.get("/analytics/overview")
async def analytics_overview(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("7d", description="Period: 7d, 14d, or 30d"),
):
    """Key site metrics: DAU, sessions, avg session duration, bounce rate, top pages."""
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="30d")
    cache_key = f"overview:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_engagement_metrics, get_top_pages

    start_date = _period_to_start_date(period, default="30daysAgo")

    try:
        engagement = get_engagement_metrics(start_date=start_date, end_date="today")
        top_pages = get_top_pages(start_date=start_date, end_date="today", limit=25)
    except Exception as exc:
        logger.error("GA4 overview query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    result = {
        "period": period,
        "engagement": engagement,
        "topPages": top_pages,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/discover")
async def analytics_discover(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("7d", description="Period: 7d, 14d, or 30d"),
):
    """Discover-specific metrics: feed loads, card events, scroll depth, predictions."""
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="30d")
    cache_key = f"discover:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import run_report

    start_date = _period_to_start_date(period, default="30daysAgo")

    try:
        # Discover page views
        discover_pages = run_report(
            dimensions=["pagePath"],
            metrics=["screenPageViews", "activeUsers", "averageSessionDuration"],
            start_date=start_date,
            end_date="today",
            limit=50,
            order_by_metric="screenPageViews",
        )
        # Filter to Discover-related paths
        discover_paths = [
            r for r in discover_pages
            if any(p in r.get("pagePath", "") for p in ["/discover", "/", "/sports"])
        ]

        # Custom events: live feed_card_action / feed_card_impression / prediction_submit + legacy
        events_data = run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=100,
            order_by_metric="eventCount",
        )
        discover_events = [
            r for r in events_data
            if _is_discover_event(r.get("eventName", ""))
        ]

        # Platform breakdown (web vs iOS vs Watch)
        platform_events = run_report(
            dimensions=["platform", "eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=200,
            order_by_metric="eventCount",
        )
        by_platform: dict[str, dict[str, Any]] = {}
        for row in platform_events:
            ev = row.get("eventName", "")
            if not _is_discover_event(ev):
                continue
            plat = _normalize_analytics_platform(row.get("platform"), ev)
            bucket = by_platform.setdefault(
                plat, {"platform": plat, "events": 0, "users": 0}
            )
            bucket["events"] += int(row.get("eventCount", 0))
            bucket["users"] = max(bucket["users"], int(row.get("totalUsers", 0)))

        # Daily trend for feed loads
        daily_feed = run_report(
            dimensions=["date"],
            metrics=["screenPageViews", "activeUsers"],
            start_date=start_date,
            end_date="today",
            limit=90,
        )
    except Exception as exc:
        logger.error("GA4 Discover query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    result = {
        "period": period,
        "discoverPages": discover_paths,
        "discoverEvents": discover_events,
        "byPlatform": sorted(by_platform.values(), key=lambda r: -r["events"]),
        "dailyTrend": daily_feed,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/realtime")
async def analytics_realtime(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
):
    """Current active users and top active pages."""
    _check_admin_secret(secret, request=request)

    cache_key = "realtime"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_realtime

    try:
        result = get_realtime()
    except Exception as exc:
        logger.error("GA4 realtime query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    await _cache_set(cache_key, result, CACHE_TTL_REALTIME)
    return result


@router.get("/analytics/retention")
async def analytics_retention(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("30d", description="Period: 7d, 14d, 30d, or 90d"),
):
    """Daily/weekly retention cohorts: new vs returning users + Day-2 / Day-7 cohorts (#13261 Row 3)."""
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="30d")
    cache_key = f"retention:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import get_cohort_retention, get_user_retention, run_report

    start_date = _period_to_start_date(period, default="30daysAgo")

    try:
        raw_data = get_user_retention(start_date=start_date, end_date="today")
    except Exception as exc:
        logger.error("GA4 retention query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    # True Day-2 / Day-7 cohort retention from GA4 CohortSpec (graceful fallback if unavailable)
    cohort_days = 7 if period == "7d" else 14
    cohort_rows: list[dict[str, Any]] = []
    try:
        cohort_rows = get_cohort_retention(days=cohort_days, max_offset=7)
    except Exception as exc:
        logger.warning("GA4 cohort retention query unavailable: %s", exc)
    cohort_summary = _summarize_cohort_retention(cohort_rows)

    # Consented return_visit event totals (web + iOS)
    return_visit_events = 0
    return_visit_users = 0
    try:
        ev_rows = run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=100,
            order_by_metric="eventCount",
        )
        for row in ev_rows:
            if row.get("eventName") == "return_visit":
                return_visit_events = int(row.get("eventCount", 0) or 0)
                return_visit_users = int(row.get("totalUsers", 0) or 0)
                break
    except Exception as exc:
        logger.warning("GA4 return_visit query unavailable: %s", exc)

    # Reshape into daily buckets with new/returning split
    daily: dict[str, dict[str, Any]] = {}
    for row in raw_data:
        day = row.get("date", "")
        segment = row.get("newVsReturning", "unknown")
        users = int(row.get("activeUsers", 0))
        sessions = int(row.get("sessions", 0))

        if day not in daily:
            daily[day] = {"date": day, "new": 0, "returning": 0, "newSessions": 0, "returningSessions": 0}
        if segment == "new":
            daily[day]["new"] = users
            daily[day]["newSessions"] = sessions
        elif segment == "returning":
            daily[day]["returning"] = users
            daily[day]["returningSessions"] = sessions

    sorted_daily = sorted(daily.values(), key=lambda d: d["date"])

    # Compute summary
    total_new = sum(d["new"] for d in sorted_daily)
    total_returning = sum(d["returning"] for d in sorted_daily)
    total_all = total_new + total_returning
    retention_rate = round(total_returning / total_all * 100, 1) if total_all else 0

    result = {
        "period": period,
        "summary": {
            "totalNewUsers": total_new,
            "totalReturningUsers": total_returning,
            "retentionRate": retention_rate,
            "day2RetentionRate": cohort_summary["day2RetentionRate"],
            "day7RetentionRate": cohort_summary["day7RetentionRate"],
            "day2Users": cohort_summary["day2Users"],
            "day2CohortBase": cohort_summary["day2CohortBase"],
            "day7Users": cohort_summary["day7Users"],
            "day7CohortBase": cohort_summary["day7CohortBase"],
            "returnVisitEvents": return_visit_events,
            "returnVisitUsers": return_visit_users,
        },
        "cohorts": cohort_summary["cohorts"],
        "daily": sorted_daily,
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/acquisition")
async def analytics_acquisition(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("14d", description="Period: 7d, 14d, 30d, or 90d"),
):
    """Acquisition sources (sessionSourceMedium + shared_link_open) and first-visit landing paths (#13261 Row 3).

    Reads consented GA4 data only (181-C); query parameters are stripped from landing paths.
    """
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="14d")
    cache_key = f"acquisition:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import run_report

    start_date = _period_to_start_date(period, default="14daysAgo")

    try:
        source_rows = run_report(
            dimensions=["sessionSourceMedium"],
            metrics=["newUsers", "activeUsers", "sessions", "engagedSessions"],
            start_date=start_date,
            end_date="today",
            limit=50,
            order_by_metric="sessions",
        )

        shared_rows = run_report(
            dimensions=["eventName", "sessionSourceMedium"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=100,
            order_by_metric="eventCount",
        )

        landing_rows = run_report(
            dimensions=["landingPagePlusQueryString", "newVsReturning"],
            metrics=["sessions", "activeUsers", "engagedSessions"],
            start_date=start_date,
            end_date="today",
            limit=150,
            order_by_metric="sessions",
        )

        first_visit_rows = run_report(
            dimensions=["pagePath", "eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=150,
            order_by_metric="eventCount",
        )
    except Exception as exc:
        logger.error("GA4 acquisition query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    sources: list[dict[str, Any]] = []
    total_new_users = 0
    total_sessions = 0
    for row in source_rows:
        sm = str(row.get("sessionSourceMedium") or "(direct) / (none)").strip()
        src, med = _split_source_medium(sm)
        new_u = int(row.get("newUsers", 0) or 0)
        act_u = int(row.get("activeUsers", 0) or 0)
        sess = int(row.get("sessions", 0) or 0)
        eng = int(row.get("engagedSessions", 0) or 0)
        total_new_users += new_u
        total_sessions += sess
        sources.append(
            {
                "sourceMedium": sm,
                "source": src,
                "medium": med,
                "newUsers": new_u,
                "activeUsers": act_u,
                "sessions": sess,
                "engagedSessions": eng,
            }
        )

    shared_by_source: list[dict[str, Any]] = []
    shared_total_events = 0
    shared_total_users = 0
    for row in shared_rows:
        if row.get("eventName") != "shared_link_open":
            continue
        sm = str(row.get("sessionSourceMedium") or "(direct) / (none)").strip()
        src, med = _split_source_medium(sm)
        cnt = int(row.get("eventCount", 0) or 0)
        usr = int(row.get("totalUsers", 0) or 0)
        shared_total_events += cnt
        shared_total_users += usr
        shared_by_source.append(
            {
                "sourceMedium": sm,
                "source": src,
                "medium": med,
                "events": cnt,
                "users": usr,
            }
        )

    # First-visit landing paths (new users only, query strings stripped)
    landing_by_path: dict[str, dict[str, Any]] = {}
    section_totals: dict[str, dict[str, int]] = {}
    for row in landing_rows:
        if str(row.get("newVsReturning") or "").strip().lower() != "new":
            continue
        clean_path = _clean_landing_path(row.get("landingPagePlusQueryString"))
        section = _classify_page_section(clean_path)
        sess = int(row.get("sessions", 0) or 0)
        usr = int(row.get("activeUsers", 0) or 0)
        eng = int(row.get("engagedSessions", 0) or 0)

        entry = landing_by_path.setdefault(
            clean_path,
            {
                "path": clean_path,
                "section": section,
                "sessions": 0,
                "users": 0,
                "engagedSessions": 0,
            },
        )
        entry["sessions"] += sess
        entry["users"] += usr
        entry["engagedSessions"] += eng

        sec = section_totals.setdefault(
            section, {"section": section, "sessions": 0, "users": 0, "engagedSessions": 0}
        )
        sec["sessions"] += sess
        sec["users"] += usr
        sec["engagedSessions"] += eng

    first_visit_events: list[dict[str, Any]] = []
    for row in first_visit_rows:
        ev = str(row.get("eventName") or "").strip()
        if ev not in {"first_visit", "session_open"}:
            continue
        clean_path = _clean_landing_path(row.get("pagePath"))
        first_visit_events.append(
            {
                "eventName": ev,
                "path": clean_path,
                "section": _classify_page_section(clean_path),
                "events": int(row.get("eventCount", 0) or 0),
                "users": int(row.get("totalUsers", 0) or 0),
            }
        )

    result = {
        "period": period,
        "summary": {
            "totalNewUsers": total_new_users,
            "totalSessions": total_sessions,
            "sourceCount": len(sources),
            "sharedLinkOpens": shared_total_events,
            "sharedLinkUsers": shared_total_users,
        },
        "sources": sorted(sources, key=lambda r: (-r["newUsers"], -r["sessions"])),
        "sharedLinks": {
            "totalEvents": shared_total_events,
            "totalUsers": shared_total_users,
            "bySourceMedium": sorted(shared_by_source, key=lambda r: -r["events"]),
        },
        "firstVisitLandingPaths": sorted(
            landing_by_path.values(), key=lambda r: (-r["sessions"], -r["users"])
        )[:50],
        "firstLandingBySection": sorted(
            section_totals.values(), key=lambda r: (-r["sessions"], -r["users"])
        ),
        "firstVisitEvents": sorted(first_visit_events, key=lambda r: -r["events"])[:50],
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/funnel")
async def analytics_funnel(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("7d", description="Period: 7d, 14d, or 30d"),
):
    """Discover conversion funnel: visit -> swipe/interact -> guess -> sign-up."""
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="30d")
    cache_key = f"funnel:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import run_report

    start_date = _period_to_start_date(period, default="30daysAgo")

    try:
        # Get event counts for funnel stages
        events_data = run_report(
            dimensions=["eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=200,
            order_by_metric="eventCount",
        )

        # Get daily breakdown for funnel trend
        daily_events = run_report(
            dimensions=["date", "eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=1000,
        )

        # Get device category breakdown
        device_events = run_report(
            dimensions=["deviceCategory", "eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=200,
        )

        # Get platform breakdown (web vs iOS vs Watch)
        platform_events = run_report(
            dimensions=["platform", "eventName"],
            metrics=["eventCount", "totalUsers"],
            start_date=start_date,
            end_date="today",
            limit=200,
        )
    except Exception as exc:
        logger.error("GA4 funnel query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    # Build funnel totals
    stage_totals: dict[str, dict[str, int]] = {
        "visit": {"events": 0, "users": 0},
        "interact": {"events": 0, "users": 0},
        "guess": {"events": 0, "users": 0},
        "signup": {"events": 0, "users": 0},
    }
    event_breakdown: list[dict[str, Any]] = []

    for row in events_data:
        event_name = row.get("eventName", "")
        count = int(row.get("eventCount", 0))
        users = int(row.get("totalUsers", 0))
        stage = _classify_funnel_stage(event_name)
        if stage:
            stage_totals[stage]["events"] += count
            stage_totals[stage]["users"] = max(stage_totals[stage]["users"], users)
            event_breakdown.append({
                "eventName": event_name,
                "stage": stage,
                "eventCount": count,
                "totalUsers": users,
            })

    # Build funnel steps with conversion rates
    stages_ordered = ["visit", "interact", "guess", "signup"]
    funnel_steps: list[dict[str, Any]] = []
    for i, stage in enumerate(stages_ordered):
        step: dict[str, Any] = {
            "stage": stage,
            "events": stage_totals[stage]["events"],
            "users": stage_totals[stage]["users"],
        }
        if i > 0:
            prev_users = stage_totals[stages_ordered[i - 1]]["users"]
            step["conversionRate"] = (
                round(stage_totals[stage]["users"] / prev_users * 100, 1)
                if prev_users > 0 else 0
            )
        else:
            step["conversionRate"] = 100.0
        funnel_steps.append(step)

    # Daily funnel trend
    daily_funnel: dict[str, dict[str, int]] = {}
    for row in daily_events:
        date = row.get("date", "")
        event_name = row.get("eventName", "")
        users = int(row.get("totalUsers", 0))
        stage = _classify_funnel_stage(event_name)
        if not stage:
            continue
        if date not in daily_funnel:
            daily_funnel[date] = {"date": date, "visit": 0, "interact": 0, "guess": 0, "signup": 0}
        daily_funnel[date][stage] = max(daily_funnel[date].get(stage, 0), users)

    sorted_daily = sorted(daily_funnel.values(), key=lambda d: d["date"])

    # Device breakdown
    device_funnel: dict[str, dict[str, int]] = {}
    for row in device_events:
        device = row.get("deviceCategory", "unknown")
        event_name = row.get("eventName", "")
        users = int(row.get("totalUsers", 0))
        stage = _classify_funnel_stage(event_name)
        if not stage:
            continue
        if device not in device_funnel:
            device_funnel[device] = {"device": device, "visit": 0, "interact": 0, "guess": 0, "signup": 0}
        device_funnel[device][stage] = max(device_funnel[device].get(stage, 0), users)

    # Platform breakdown (web vs iOS vs Watch)
    platform_funnel: dict[str, dict[str, Any]] = {}
    for row in platform_events:
        event_name = row.get("eventName", "")
        stage = _classify_funnel_stage(event_name)
        if not stage:
            continue
        plat = _normalize_analytics_platform(row.get("platform"), event_name)
        users = int(row.get("totalUsers", 0))
        if plat not in platform_funnel:
            platform_funnel[plat] = {
                "platform": plat,
                "visit": 0,
                "interact": 0,
                "guess": 0,
                "signup": 0,
            }
        platform_funnel[plat][stage] = max(platform_funnel[plat].get(stage, 0), users)

    result = {
        "period": period,
        "funnel": funnel_steps,
        "eventBreakdown": sorted(event_breakdown, key=lambda e: -e["eventCount"]),
        "dailyTrend": sorted_daily,
        "byDevice": list(device_funnel.values()),
        "byPlatform": sorted(
            platform_funnel.values(), key=lambda r: -int(r.get("visit", 0))
        ),
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result


@router.get("/analytics/pages")
async def analytics_pages(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    period: str = Query("7d", description="Period: 7d, 14d, or 30d"),
):
    """Page-level engagement: views, users, duration, grouped by section."""
    _check_admin_secret(secret, request=request)

    period = _normalize_period(period, default="30d")
    cache_key = f"pages:{period}"
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    from app.services.ga4_api import run_report

    start_date = _period_to_start_date(period, default="30daysAgo")

    try:
        pages_data = run_report(
            dimensions=["pagePath"],
            metrics=[
                "screenPageViews", "activeUsers",
                "averageSessionDuration", "bounceRate",
                "engagedSessions",
            ],
            start_date=start_date,
            end_date="today",
            limit=100,
            order_by_metric="screenPageViews",
        )

        # Daily page views trend
        daily_pages = run_report(
            dimensions=["date", "pagePath"],
            metrics=["screenPageViews", "activeUsers"],
            start_date=start_date,
            end_date="today",
            limit=500,
            order_by_metric="screenPageViews",
        )
    except Exception as exc:
        logger.error("GA4 pages query failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"GA4 API error: {exc}")

    # Build page rows
    page_rows: list[dict[str, Any]] = []
    section_totals: dict[str, dict[str, float]] = {}

    for row in pages_data:
        path = row.get("pagePath", "")
        views = int(row.get("screenPageViews", 0))
        users = int(row.get("activeUsers", 0))
        duration = float(row.get("averageSessionDuration", 0))
        bounce = float(row.get("bounceRate", 0))
        engaged = int(row.get("engagedSessions", 0))
        section = _classify_page_section(path)

        page_rows.append({
            "path": path,
            "section": section,
            "views": views,
            "users": users,
            "avgDuration": round(duration, 1),
            "bounceRate": round(bounce * 100, 1),
            "engagedSessions": engaged,
        })

        if section not in section_totals:
            section_totals[section] = {"views": 0, "users": 0, "engaged": 0}
        section_totals[section]["views"] += views
        section_totals[section]["users"] += users
        section_totals[section]["engaged"] += engaged

    # Build section summaries
    sections = []
    for section, totals in sorted(
        section_totals.items(), key=lambda x: -x[1]["views"]
    ):
        sections.append({
            "section": section,
            "views": int(totals["views"]),
            "users": int(totals["users"]),
            "engagedSessions": int(totals["engaged"]),
            "pageCount": sum(1 for p in page_rows if p["section"] == section),
        })

    # Daily trend by section
    daily_by_section: dict[str, dict[str, int]] = {}
    for row in daily_pages:
        date = row.get("date", "")
        path = row.get("pagePath", "")
        views = int(row.get("screenPageViews", 0))
        section = _classify_page_section(path)
        if date not in daily_by_section:
            daily_by_section[date] = {"date": date}
        daily_by_section[date][section] = (
            daily_by_section[date].get(section, 0) + views
        )

    result = {
        "period": period,
        "pages": page_rows,
        "sections": sections,
        "dailyBySection": sorted(daily_by_section.values(), key=lambda d: d["date"]),
    }

    await _cache_set(cache_key, result, CACHE_TTL_STANDARD)
    return result
