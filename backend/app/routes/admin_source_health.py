"""Source-level health dashboard — shows live status of every external data source."""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import get_db
from app.tasks.futures_price_refresh import (  # noqa: E402
    ELIGIBLE_POOL_SQL,
    HIGH_VALUE_SQL,
    UNPRICED_POOL_LIMIT,
    VALUE_POOL_LIMIT,
)
from app.utils.futures_liveness import (
    BASE_LIVENESS_SQL,
    LIVE_MARKET_SQL,
    SETTLED_EXCLUSION_REASON_SQL,
    SETTLED_ONLY_SQL,
    VENUE_SETTLED_CONFIRM_HOURS,
)

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

#: ONE SCAN, and the collapse is a cost decision with a correctness dividend.
#:
#: This was three statements over the same pool — the dark grouping, the worst-25
#: list, and the eligible denominator. Under the tier-1 fence that pool was 3,081
#: rows and each was fast. #3315's pool is 4,500, and each statement pays the
#: whole ~10s scan (measured on production 2026-09-05): three of them plus the
#: settled report is over 30s, which is the Heroku router's H12 boundary. A guard
#: that times out is not a stricter guard, it is no guard.
#:
#: So the darkness is a SELECT expression rather than a WHERE clause, every
#: eligible row comes back once, and the endpoint derives all three answers from
#: the one result. That the denominator and the numerator now come from the same
#: scan is the dividend: they cannot describe two different populations, which is
#: the failure mode this endpoint exists to make impossible one level up.
_PRICE_DARK_SQL = f"""
    {ELIGIBLE_POOL_SQL}
    SELECT fm.source, fm.external_id, fm.name, fm.volume, fm.market_tier,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
           NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :max_age_hours)
           ) AS is_dark
      FROM futures_markets fm
      JOIN pool ON pool.id = fm.id
     ORDER BY fm.volume DESC NULLS LAST
"""

#: How many of the worst dark markets the response names. A SAMPLE, and the
#: response says so — calling a truncated list `markets` is how a cap reads as
#: coverage.
_WORST_SAMPLE = 25

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
#: ONE SCAN, both answers, for the same reason :data:`_PRICE_DARK_SQL` is one
#: scan: the darkness is a SELECT expression, not a WHERE clause, so the
#: denominator and the numerator come back from a single evaluation of
#: ``LIVE_MARKET_SQL`` and cannot describe two different populations. It also
#: halves this arm's cost, which is not free: measured on production
#: 2026-09-06 the two statements this replaces cost 1.38s and 1.10s.
_REGISTERED_SQL = f"""
    SELECT fm.id, fm.source, fm.external_id, fm.name, fm.market_tier,
           COALESCE(fm.llm_sport_category, 'uncategorized') AS category,
           NOT EXISTS (
             SELECT 1 FROM futures_outcomes fo
               JOIN futures_odds_snapshots s ON s.outcome_id = fo.id
              WHERE fo.market_id = fm.id
                AND s.captured_at > NOW() - make_interval(hours => :max_age_hours)
           ) AS is_dark
      FROM futures_markets fm
     WHERE fm.id = ANY(:market_ids)
       AND {LIVE_MARKET_SQL}
     ORDER BY fm.id
"""

#: #2222 — the exclusion report, and the reason the guard is not allowed to
#: simply shrink its own denominator.
#:
#: Every market this endpoint rules out as settled would previously have been
#: counted dark. Dropping them silently would let the very task being measured
#: talk the alarm into green: the task writes the venue-settled stamp, and the
#: stamp is one of the two bounds. So the endpoint reports the excluded
#: population and WHY, next to its verdict. Green now reads "no live market is
#: dark, and here are the N I ruled not-live" — which is checkable — rather than
#: "no market is dark", which would not be.
_SETTLED_EXCLUDED_SQL = f"""
    SELECT {SETTLED_EXCLUSION_REASON_SQL} AS reason,
           fm.source, fm.external_id, fm.name, fm.volume
      FROM futures_markets fm
     WHERE {BASE_LIVENESS_SQL}
       AND {HIGH_VALUE_SQL}
       AND {SETTLED_ONLY_SQL}
     ORDER BY fm.volume DESC NULLS LAST
"""

#: 🔴 THE WALL, AND WHY THIS ENDPOINT OWNS ONE.
#:
#: Heroku's router kills a request at 30s with an HTML error page (H12), and an
#: HTML error page is the one answer this endpoint must never give: a reader
#: polling a guard cannot tell "the invariant holds" from "the guard fell over"
#: if the second arrives as a 503 with no body. Measured on production
#: 2026-09-06, hours after #3315 widened the pool from 872 markets to 4,916, the
#: four statements below cost 15.1s + 3.3s + 1.4s + 1.1s **in series** — 26.0s
#: end to end, and one read in two came back H12. The widening was right and the
#: serial shape was what made it fatal.
#:
#: So: each statement gets its own session and they run CONCURRENTLY (the bound
#: becomes the longest one, ~16s, not their sum), and each carries a server-side
#: ``statement_timeout`` **below** the router's, so a census that cannot finish
#: comes back as JSON saying so rather than as somebody else's error page.
_CENSUS_STATEMENT_TIMEOUT_MS = 22_000


async def _census_rows(sql: str, params: dict) -> list:
    """Run one census statement on its own session, under its own wall.

    Its own session because :func:`asyncio.gather` over a single
    ``AsyncSession`` is not concurrency — SQLAlchemy serialises it, and in
    asyncpg it is an error. The engine pool is 10 + 10 overflow per web
    process; this endpoint holds at most three of them, for at most the wall
    below.
    """
    from app.services.database import async_session_maker

    async with async_session_maker() as session:
        await session.execute(
            text(f"SET LOCAL statement_timeout = {_CENSUS_STATEMENT_TIMEOUT_MS}")
        )
        return (await session.execute(text(sql), params)).fetchall()


@router.get("/futures-price-freshness")
async def futures_price_freshness(
    request: Request,
    secret: str = Query(None),
    max_age_hours: int = Query(24, ge=1, le=720),
):
    """#2199: high-value tier-1 open futures markets with no recent price capture.

    `status: "red"` means the invariant is breached — the boards are printing
    stale numbers as if they were live. Zero is the only passing value; a floor
    that tolerates "a few dark markets" is how this went unnoticed for a month.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.futures_price_refresh import HIGH_VALUE_VOLUME_FLOOR

    # #3315: the pool bounds are the task's own, imported rather than restated.
    # This endpoint's whole job is to assert over the set the task refreshes, so
    # a bound it chose for itself would be a second definition of eligibility —
    # and the reader of a green verdict would have no way to know which one it
    # meant.
    pool_params = {
        "volume_floor": HIGH_VALUE_VOLUME_FLOOR,
        "value_pool_limit": VALUE_POOL_LIMIT,
        "unpriced_pool_limit": UNPRICED_POOL_LIMIT,
    }
    params = {**pool_params, "max_age_hours": max_age_hours}

    # The curated half. Every market a committed register renders, at any tier.
    from app.utils.tournament_register import registered_market_ids

    registered_ids = sorted(registered_market_ids())
    registered_params = {
        "market_ids": registered_ids,
        "max_age_hours": max_age_hours,
    }

    # CONCURRENTLY, and the reason is `_CENSUS_STATEMENT_TIMEOUT_MS` above: in
    # series these three cost 26s against a 30s router wall.
    async def _registered_rows() -> list:
        return (
            await _census_rows(_REGISTERED_SQL, registered_params)
            if registered_ids
            else []
        )

    try:
        eligible, settled, registered_all = await asyncio.gather(
            _census_rows(_PRICE_DARK_SQL, params),
            _census_rows(
                _SETTLED_EXCLUDED_SQL, {"volume_floor": HIGH_VALUE_VOLUME_FLOOR}
            ),
            _registered_rows(),
        )
    except DBAPIError as exc:
        # A CENSUS THAT DID NOT FINISH IS NOT A GREEN ONE, and it is not an
        # HTML error page either. `status: "unknown"` is the third state this
        # endpoint has always needed and never had: every caller that branches
        # on `status == "red"` would otherwise read a failed census as a
        # passing one (gotcha #53 — an absence and a clean bill arriving in the
        # same shape).
        logger.warning("futures-price-freshness census did not finish: %s", exc)
        return {
            "status": "unknown",
            "status_all": "unknown",
            "reason": "census_timeout",
            "detail": (
                "the freshness census exceeded its "
                f"{_CENSUS_STATEMENT_TIMEOUT_MS // 1000}s wall and reports "
                "nothing rather than reporting green"
            ),
            "max_age_hours": max_age_hours,
            "volume_floor": HIGH_VALUE_VOLUME_FLOOR,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # One scan, three answers. Ordered by volume DESC in SQL, so `worst` is a
    # slice rather than a second sort with a second chance to disagree.
    total_eligible = len(eligible)
    dark = [r for r in eligible if r[6]]
    dark_total = len(dark)
    worst = dark[:_WORST_SAMPLE]

    by_category: dict = {}
    for r in dark:
        cat = by_category.setdefault(r[5], {})
        cat[r[0]] = cat.get(r[0], 0) + 1

    # Same one-scan shape as the class half: `is_dark` is column 6, the
    # denominator is the row count, and neither can drift from the other.
    registered_dark = [r for r in registered_all if r[6]]
    registered_eligible = len(registered_all)

    return {
        "invariant": (
            f"an open market with volume >= {HIGH_VALUE_VOLUME_FLOOR}, at ANY "
            f"tier, or a tier-1 one with no recorded volume, and a future "
            f"resolution date, must have a price capture within {max_age_hours}h, "
            f"in every category"
        ),
        # #3315 WIDENED THIS DENOMINATOR AND THE WORDING ABOVE SAYS SO. It used
        # to read "a tier-1 open market with volume >= N". That sentence was
        # true of what was measured and false of what a reader took it to mean:
        # the front page is tier 2, so `status: green` was compatible with every
        # card on it being 46 days stale. A guard's invariant string is the only
        # place its blind spots are visible, so widening the set without
        # rewriting the sentence would have been the worse half of the fix.
        # Expect `red` while the sweep works through the newly-admitted backlog.
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
        # #2222. NEVER drop a population silently: these markets used to be
        # counted dark and are now ruled not-live, so the verdict only means
        # something if the reader can see what left and why.
        "settled_excluded": {
            "why": (
                "a market with a graded winner, or one a source has positively "
                f"reported as over for more than {VENUE_SETTLED_CONFIRM_HOURS}h, "
                "cannot be re-priced and is not counted dark"
            ),
            "count": len(settled),
            "by_reason": {
                reason: sum(1 for r in settled if r[0] == reason)
                for reason in sorted({r[0] for r in settled})
            },
            # A SAMPLE, and named one: `count` is the whole population, this
            # list is the 25 most valuable. Calling a truncated list `markets`
            # is how a cap reads as coverage.
            "sample_limit": 25,
            "sample_markets": [
                {
                    "reason": r[0],
                    "source": r[1],
                    "external_id": r[2],
                    "name": r[3],
                    "volume": int(r[4]) if r[4] is not None else None,
                }
                for r in settled[:25]
            ],
        },
        "by_category": by_category,
        # #3315: `market_tier` is reported because the tier fence is exactly
        # what this endpoint could not see. A reader looking at a dark market
        # needs to know it is tier 2 without going to the database to find out.
        "worst_offenders": [
            {
                "source": r[0],
                "external_id": r[1],
                "name": r[2],
                "volume": int(r[3]) if r[3] is not None else None,
                "market_tier": r[4],
                "category": r[5],
            }
            for r in worst
        ],
        "worst_offenders_sample_limit": _WORST_SAMPLE,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
