"""Source-level health dashboard — shows live status of every external data source."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/source-health", tags=["admin-source-health"])


from app.routes.admin_utils import _check_admin_secret  # noqa

# Map each source to its primary task names for Redis metric lookups
_SOURCE_TASKS = {
    "odds_api": ["poll_all_odds", "discover_events"],
    "espn": ["espn_sync"],
    "statpal": ["statpal_livescores", "statpal_schedules"],
    "datagolf": ["datagolf_live", "poll_datagolf"],
    "kalshi": ["poll_kalshi"],
    "polymarket": ["poll_polymarket"],
    "mlb": ["mlb_sync"],
    "pexels": ["enrich_images"],
    "openai": ["enrich_hooks", "enrich_discover_llm"],
}

# DB queries to check freshness per source
_SOURCE_FRESHNESS_QUERIES = {
    "odds_api": "SELECT COUNT(*) FROM events WHERE updated_at > NOW() - INTERVAL '6 hours'",
    "espn": "SELECT COUNT(*) FROM events WHERE espn_id IS NOT NULL AND updated_at > NOW() - INTERVAL '6 hours'",
    "statpal": "SELECT COUNT(*) FROM events WHERE statpal_fixture_id IS NOT NULL AND updated_at > NOW() - INTERVAL '6 hours'",
    "kalshi": "SELECT COUNT(*) FROM futures_markets WHERE source = 'kalshi' AND updated_at > NOW() - INTERVAL '6 hours'",
    "polymarket": "SELECT COUNT(*) FROM futures_markets WHERE source = 'polymarket' AND updated_at > NOW() - INTERVAL '6 hours'",
    "datagolf": "SELECT COUNT(*) FROM futures_markets WHERE source = 'datagolf' AND updated_at > NOW() - INTERVAL '12 hours'",
}


@router.get("")
async def source_health(
    request: Request, secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Live health status for every external data source."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_task_metrics, get_redis_client

    sources = {}
    alerts = []

    for source_name, task_names in _SOURCE_TASKS.items():
        task_metrics = []
        worst_health = "healthy"
        last_success = None
        total_failures_24h = 0
        max_consecutive = 0

        for tn in task_names:
            m = get_task_metrics(tn)
            task_metrics.append(m)

            health = m.get("health", "no_data")
            if health == "critical":
                worst_health = "critical"
            elif health == "degraded" and worst_health != "critical":
                worst_health = "degraded"
            elif health == "no_data" and worst_health == "healthy":
                worst_health = "no_data"

            ls = m.get("last_success_at")
            if ls and (last_success is None or ls > last_success):
                last_success = ls

            total_failures_24h += int(m.get("failures_24h", 0))
            max_consecutive = max(max_consecutive, int(m.get("consecutive_failures", 0)))

        # DB freshness check
        freshness_count = None
        if source_name in _SOURCE_FRESHNESS_QUERIES:
            try:
                result = await db.execute(text(_SOURCE_FRESHNESS_QUERIES[source_name]))
                freshness_count = result.scalar()
                if freshness_count == 0 and worst_health != "critical":
                    worst_health = "stale"
            except Exception:
                pass

        source_data = {
            "status": worst_health,
            "last_success_at": last_success,
            "failures_24h": total_failures_24h,
            "consecutive_failures": max_consecutive,
        }
        if freshness_count is not None:
            source_data["items_updated_6h"] = freshness_count

        if worst_health in ("critical", "stale"):
            alerts.append(f"{source_name}: {worst_health} (consecutive_failures={max_consecutive}, items_6h={freshness_count})")

        sources[source_name] = source_data

    # Quota info for Odds API
    try:
        rc = get_redis_client()
        remaining = rc.get("bainluck:odds_api_remaining")
        if remaining:
            sources["odds_api"]["quota_remaining"] = int(remaining.decode() if isinstance(remaining, bytes) else remaining)
        mode = rc.get("bainluck:circuit_breaker_mode")
        if mode:
            sources["odds_api"]["circuit_breaker"] = mode.decode() if isinstance(mode, bytes) else mode
    except Exception:
        pass

    overall = "healthy"
    if any(s["status"] == "critical" for s in sources.values()):
        overall = "critical"
    elif any(s["status"] in ("degraded", "stale") for s in sources.values()):
        overall = "degraded"

    return {
        "overall": overall,
        "sources": sources,
        "alerts": alerts,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


# --- #2199: the high-value futures price-freshness invariant -----------------
#
# The invariant, stated once so the fix and the guard cannot drift apart: a
# tier-1 `open` market above the volume floor, with a resolution date still in
# the future, MUST NOT go 24h without a price capture — in ANY category.
#
# It is written as its own endpoint rather than folded into `source_health`
# above because that dashboard's freshness queries all read
# `futures_markets.updated_at`, and `updated_at` is exactly what made this class
# invisible: the discovery polls kept stamping rows they re-read while capturing
# no prices for the ones they could not reach. 900 of 907 high-value fields were
# dark for up to 32 days behind a green source-health row. Only
# `futures_odds_snapshots.captured_at` answers "was a price actually captured".
#
# `NOT EXISTS` with a time bound, not `MAX(captured_at)`: the aggregate form
# times out against the 179M-row snapshot table; this rides
# `idx_fos_outcome_captured` and stops at the first row inside the window.

_PRICE_DARK_SQL = """
    SELECT fm.source,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
           COUNT(*) AS dark
      FROM futures_markets fm
     WHERE fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND fm.market_tier = 1
       AND fm.volume >= :volume_floor
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
       AND NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :max_age_hours)
           )
     GROUP BY 1, 2
     ORDER BY 3 DESC
"""

_PRICE_DARK_WORST_SQL = """
    SELECT fm.source, fm.external_id, fm.name, fm.volume,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS category
      FROM futures_markets fm
     WHERE fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND fm.market_tier = 1
       AND fm.volume >= :volume_floor
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
       AND NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :max_age_hours)
           )
     ORDER BY fm.volume DESC
     LIMIT 25
"""

#: The registered-coverage half, and the reason it is a separate query.
#:
#: The two queries above are value-bounded, so they are structurally incapable of
#: reporting the failure that emptied the US Open "More predictions" section:
#: every market behind it was tier 5, which means it was never in the
#: denominator. `price_dark` read 19 and `status` read green-ish while a curated
#: page showed nothing. A guard that cannot see a population cannot report on it,
#: and reporting only what it can see is how this stayed invisible (gotcha #53).
#:
#: No tier or volume bound, same liveness bounds, same snapshot-derived freshness
#: — the register decides membership and the market decides nothing.
_REGISTERED_DARK_SQL = """
    SELECT fm.id, fm.source, fm.external_id, fm.name, fm.market_tier,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS category
      FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
       AND NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :max_age_hours)
           )
     ORDER BY fm.id
"""

_REGISTERED_ELIGIBLE_SQL = """
    SELECT COUNT(*) FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND fm.status = 'open'
       AND fm.source IN ('kalshi', 'polymarket')
       AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
"""


@router.get("/futures-price-freshness")
async def futures_price_freshness(
    request: Request,
    secret: str = Query(None),
    max_age_hours: int = Query(24, ge=1, le=720),
    db: AsyncSession = Depends(get_db),
):
    """#2199: high-value tier-1 open futures markets with no recent price capture.

    `status: "red"` means the invariant is breached — the boards are printing
    stale numbers as if they were live. Zero is the only passing value; a floor
    that tolerates "a few dark markets" is how this went unnoticed for a month.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.futures_price_refresh import HIGH_VALUE_VOLUME_FLOOR

    params = {
        "volume_floor": HIGH_VALUE_VOLUME_FLOOR,
        "max_age_hours": max_age_hours,
    }
    rows = (await db.execute(text(_PRICE_DARK_SQL), params)).fetchall()
    worst = (await db.execute(text(_PRICE_DARK_WORST_SQL), params)).fetchall()

    total_eligible = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) FROM futures_markets fm
                 WHERE fm.status = 'open'
                   AND fm.source IN ('kalshi', 'polymarket')
                   AND fm.market_tier = 1
                   AND fm.volume >= :volume_floor
                   AND (fm.resolution_date IS NULL OR fm.resolution_date > NOW())
                """
            ),
            {"volume_floor": HIGH_VALUE_VOLUME_FLOOR},
        )
    ).scalar() or 0

    by_category: dict = {}
    dark_total = 0
    for source, category, dark in rows:
        by_category.setdefault(category, {})[source] = int(dark)
        dark_total += int(dark)

    # The curated half. Every market a committed register renders, at any tier.
    from app.utils.tournament_register import registered_market_ids

    registered_ids = sorted(registered_market_ids())
    registered_params = {
        "market_ids": registered_ids,
        "max_age_hours": max_age_hours,
    }
    registered_dark = (
        (await db.execute(text(_REGISTERED_DARK_SQL), registered_params)).fetchall()
        if registered_ids
        else []
    )
    registered_eligible = (
        (
            await db.execute(
                text(_REGISTERED_ELIGIBLE_SQL), {"market_ids": registered_ids}
            )
        ).scalar()
        or 0
        if registered_ids
        else 0
    )

    return {
        "invariant": (
            f"a tier-1 open market with volume >= {HIGH_VALUE_VOLUME_FLOOR} and a "
            f"future resolution date must have a price capture within "
            f"{max_age_hours}h, in every category"
        ),
        # UNCHANGED SEMANTICS: this is the tier-1 value class only, because
        # CERT-404 G5 and the existing dashboards read it. Read `status_all` for
        # "is anything price-dark".
        "status": "green" if dark_total == 0 else "red",
        "status_all": (
            "green" if dark_total == 0 and not registered_dark else "red"
        ),
        "registered": {
            "invariant": (
                "a market any committed tournament register renders must have a "
                f"price capture within {max_age_hours}h, at ANY tier and ANY volume"
            ),
            "status": "green" if not registered_dark else "red",
            "eligible_markets": int(registered_eligible),
            "price_dark": len(registered_dark),
            "dark_markets": [
                {
                    "market_id": r[0],
                    "source": r[1],
                    "external_id": r[2],
                    "name": r[3],
                    "market_tier": r[4],
                    "category": r[5],
                }
                for r in registered_dark
            ],
        },
        "max_age_hours": max_age_hours,
        "volume_floor": HIGH_VALUE_VOLUME_FLOOR,
        "eligible_markets": int(total_eligible),
        "price_dark": dark_total,
        "by_category": by_category,
        "worst_offenders": [
            {
                "source": r[0],
                "external_id": r[1],
                "name": r[2],
                "volume": int(r[3]) if r[3] is not None else None,
                "category": r[4],
            }
            for r in worst
        ],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
