"""Admin endpoints for prediction market matching, link rate, sawtooth, and matching review."""


import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from sqlalchemy import select, update, or_, not_, text, func, delete, case

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket, FuturesOutcome, MatchingOverride

from app.models.models import WinProbSnapshot

from app.services import get_db, get_db_rw

from app.utils.league_classification import is_valid_sport_league_pair

from app.utils.sport_keys import (
    KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_LINK_RATE_GAME_TICKER_PREFIXES,
)

from app.routes.admin_utils import _check_admin_secret


logger = logging.getLogger(__name__)

router = APIRouter()

# Queue #250 Item 3c: per-query statement_timeout for the link-rate compute.
# The full compute is ~25s and a runaway query under load would hang past the
# 30s Heroku router limit (H12 → 503). Bounding each query at 20s (below the
# limit) means a stuck query fails fast with a QueryCanceledError, which the
# route catches to serve the last cached snapshot instead of erroring.
_LINK_RATE_STMT_TIMEOUT_S = 20
# Wall-clock bound on the WHOLE inline compute (below the 30s router limit). The
# per-query statement_timeout above is necessary but NOT sufficient: the compute
# is several queries plus Python aggregation, so no single statement need hit 20s
# while the total still sails past 30s → H12/503 before Python can catch anything.
# asyncio.wait_for cancels the compute at this bound so the serve-stale-cache
# fallback actually fires and the endpoint returns 200 (marked stale) instead.
# Set well below 30s (not just under it): cancelling an in-flight asyncpg query
# is not instant — the driver round-trips a cancel to Postgres — so a 25s bound
# still crossed the H12 line on a slow prod run. 18s leaves ~12s of headroom for
# the cancel + response so the fallback reliably returns before the router limit.
# Trade-off: on a slow day ?bust=1 serves the (clearly-marked) stale snapshot
# rather than a fresh compute — acceptable, since the hourly precompute keeps the
# cache warm and "never 503" is the bar. (The durable fix is to move the compute
# fully off the request path; flagged for a follow-up queue.)
_LINK_RATE_WALLCLOCK_S = 18
# Redis cache key shared with the precompute_admin_link_rate beat + the route's
# cold-cache fallback. Keep in sync with app/tasks/precompute_admin_health.py.
_LINK_RATE_CACHE_KEY = "bainluck:admin:link_rate"


_CLOSED_GAME_STATUSES = {"closed", "completed", "final"}
_STALE_OPEN_GAME_MARKET_GRACE = timedelta(hours=36)
_LINK_RATE_SPORT_CATEGORIES = (
    "basketball", "football", "baseball", "hockey", "soccer",
    "golf", "tennis", "mma", "boxing", "cricket", "rugby",
    "lacrosse", "aussierules",
)
_LINK_RATE_NON_GAME_NAME_FRAGMENTS = (
    "win the nba championship",
    "win the wnba championship",
    "win the ncaa championship",
    "win the super bowl",
    "win the world series",
    "win the stanley cup",
    "championship winner",
    "super bowl winner",
    "world series winner",
    "stanley cup winner",
    "series winner",
    "division winner",
    "conference winner",
    "make playoffs",
    "make the playoffs",
    "regular season",
    " mvp",
    "cy young",
    "rookie of the year",
    "heisman",
    "award",
)

# Category values that represent season-level / non-game markets.
# Markets with these categories CANNOT be linked to individual game events
# and must be excluded from the link-rate denominator.
_LINK_RATE_NON_GAME_CATEGORIES = frozenset({
    "championship",
    "award",
    "season_win_total",
    "player_futures",
    "division",
    "conference",
    "series",
})


# #1230 / Queue #249 Item 3: Obscure upstream-coverage circuits that Bain Luck
# has NO schedule/roster source for — ITF minor tennis (below the ATP/WTA tours we
# ingest), Setka/TT-Cup table tennis, and minor cricket (European Cricket
# Series). A market on one of these circuits can NEVER be linked to an event,
# because the game/player entity does not exist on our side — so counting it in
# the link-rate denominator makes an UPSTREAM COVERAGE GAP masquerade as a
# name/ticker MATCHING bug (the #1230 diagnosis). These are dropped from the
# HONEST denominator, but the RAW (pre-exclusion) rate is still reported alongside
# so no data is hidden. Coverage would require a NEW schedule source, not a
# matching-engine fix.
_UPSTREAM_COVERAGE_GAP_NAME_RE = re.compile(
    r"\bitf\b"                                          # ITF minor tennis tour
    r"|\bsetka\b|\btt[\s.\-]?cup\b|\btable\s+tennis\b"  # Setka / TT-Cup table tennis
    r"|\becs\b",                                        # European Cricket Series
    re.I,
)


def _is_upstream_coverage_gap_market(name: str | None) -> bool:
    """True for obscure circuits we have no event coverage for (#1230).

    These markets cannot link to an event (no schedule/roster source covers them),
    so they belong out of the honest link-rate denominator. Applied only to
    UNLINKED markets — an already-linked market is always kept in the numerator.
    """
    if not name:
        return False
    return bool(_UPSTREAM_COVERAGE_GAP_NAME_RE.search(name))


def _is_obvious_non_game_market_name(name: str | None) -> bool:
    """Identify season-level markets that can look matchup-shaped."""
    if not name:
        return False
    name_lower = name.lower()
    return any(
        fragment in name_lower
        for fragment in _LINK_RATE_NON_GAME_NAME_FRAGMENTS
    )


def _link_rate_game_name_filter():
    non_game_name_filter = or_(
        *[
            FuturesMarket.name.ilike(f"%{fragment}%")
            for fragment in _LINK_RATE_NON_GAME_NAME_FRAGMENTS
        ]
    )
    return or_(
        FuturesMarket.name.is_(None),
        not_(non_game_name_filter),
    )


def _should_include_link_rate_bucket(
    sport_category: str | None,
    league: str | None,
) -> bool:
    """Keep only event-covered sports and internally consistent league buckets."""
    return (
        sport_category in _LINK_RATE_SPORT_CATEGORIES
        and is_valid_sport_league_pair(sport_category, league)
    )


def _is_closed_past_event_candidate(candidate: Any, now: datetime) -> bool:
    """Return True when a matched event row represents a finished past game."""
    status = (getattr(candidate, "status", None) or "").lower()
    if status not in _CLOSED_GAME_STATUSES:
        return False

    reference_time = getattr(candidate, "completed_at", None) or getattr(
        candidate, "commence_time", None
    )
    if reference_time is None:
        return True
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    return reference_time <= now


def _should_exclude_tier1_gap_for_closed_game(
    candidates: Sequence[Any], now: datetime
) -> bool:
    """Exclude settlement-open Kalshi markets when every matching event is already closed."""
    return bool(candidates) and all(
        _is_closed_past_event_candidate(candidate, now)
        for candidate in candidates
    )


def _should_exclude_stale_open_unlinked_game_market(
    *,
    source: str | None,
    external_id: str | None,
    status: str | None,
    event_id: int | None,
    now: datetime,
) -> bool:
    """Exclude old settlement-open game markets from headline link-rate denominators."""
    if (source or "").lower() != "kalshi" or event_id is not None:
        return False
    if (status or "").lower() != "open":
        return False

    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    game_time = extract_game_date_from_ticker(external_id or "")
    if game_time is None:
        return False
    if game_time.tzinfo is None:
        game_time = game_time.replace(tzinfo=timezone.utc)
    return game_time < now - _STALE_OPEN_GAME_MARKET_GRACE


def _is_polymarket_matcher_game_level(
    name: str | None,
    category: str | None,
    external_id: str | None,
) -> bool:
    """Use the matching task's Polymarket game-level predicate for diagnostics."""
    if not name:
        return False

    from app.utils.prediction_market_matching import is_game_level_market

    return is_game_level_market(name, category, external_id=external_id)


@router.post("/prediction-markets/match")
async def trigger_prediction_market_matching(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to scan"),
):
    """
    Trigger prediction market → event matching.

    Scans Kalshi and Polymarket game-level markets and links them to events.
    Also writes win_prob_snapshots for linked markets.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import match_prediction_markets

    try:
        task = match_prediction_markets.delay(limit=limit)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Prediction market matching task queued (limit={limit}). "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/prediction-markets/poll-live")
async def trigger_live_prediction_market_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Trigger a one-off live prediction market price poll.

    Fetches current prices from Kalshi and Polymarket ONLY for markets
    linked to events with status='live'. Much faster than full polls.
    Normally runs automatically every 2 minutes via beat schedule.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import poll_live_prediction_markets

    try:
        task = poll_live_prediction_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Live prediction market poll queued. "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/prediction-markets/backfill-history")
async def trigger_polymarket_win_prob_backfill(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket ID"),
    event_id: int = Query(..., description="Event ID"),
):
    """
    Backfill win_prob_snapshots from Polymarket CLOB price history.

    Fetches historical prices for the moneyline outcome and writes them
    as win_prob_snapshots for the event's OddsChart trend line.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import backfill_polymarket_win_prob

    try:
        task = backfill_polymarket_win_prob.delay(market_id, event_id)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Polymarket win_prob backfill queued for market={market_id} event={event_id}. "
                       f"Use /api/admin/prediction-markets/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/prediction-markets/task/{task_id}")
async def get_prediction_market_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of a prediction market matching task."""
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response


@router.get("/prediction-markets/status")
async def prediction_market_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Show prediction market → event linking status.

    Reports how many game-level markets are linked vs unlinked,
    and how many win_prob_snapshots exist per source.
    """
    _check_admin_secret(secret, request=request)

    from sqlalchemy import func, case
    from app.models.models import FuturesMarket, WinProbSnapshot

    # Count linked vs unlinked by source
    link_stats = await db.execute(
        select(
            FuturesMarket.source,
            func.count().label("total"),
            func.count(FuturesMarket.event_id).label("linked"),
        )
        .where(FuturesMarket.source.in_(["kalshi", "polymarket"]))
        .group_by(FuturesMarket.source)
    )
    links_by_source = {}
    for row in link_stats.all():
        links_by_source[row.source] = {
            "total_markets": row.total,
            "linked_to_events": row.linked,
            "unlinked": row.total - row.linked,
        }

    # Count win_prob_snapshots for prediction market sources
    wp_stats = await db.execute(
        select(
            WinProbSnapshot.source,
            func.count().label("snapshot_count"),
            func.count(func.distinct(WinProbSnapshot.event_id)).label("event_count"),
        )
        .where(WinProbSnapshot.source.in_(["kalshi", "polymarket"]))
        .group_by(WinProbSnapshot.source)
    )
    snapshots_by_source = {}
    for row in wp_stats.all():
        snapshots_by_source[row.source] = {
            "snapshot_count": row.snapshot_count,
            "event_count": row.event_count,
        }

    # Show some recently linked markets as examples
    recent_result = await db.execute(
        select(
            FuturesMarket.source,
            FuturesMarket.name,
            FuturesMarket.event_id,
        )
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(10)
    )
    recent_linked = [
        {"source": r.source, "name": r.name, "event_id": r.event_id}
        for r in recent_result.all()
    ]

    return {
        "links_by_source": links_by_source,
        "win_prob_snapshots": snapshots_by_source,
        "recent_linked": recent_linked,
    }



@router.post("/prediction-markets/fix-sport-categories")
async def fix_sport_categories(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Bulk-fix llm_sport_category for Kalshi markets based on ticker prefix."""
    _check_admin_secret(secret, request=request)

    from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY, KALSHI_FUTURES_TICKER_TO_SPORT_KEY, SPORT_PREFIX_TO_LLM_CATEGORY

    all_tickers = {**KALSHI_TICKER_TO_SPORT_KEY, **KALSHI_FUTURES_TICKER_TO_SPORT_KEY}

    fixed_by_sport: dict[str, int] = {}
    total_fixed = 0

    for prefix, sport_key in all_tickers.items():
        sport_prefix = sport_key.split("_")[0]
        correct_category = SPORT_PREFIX_TO_LLM_CATEGORY.get(sport_prefix)
        if not correct_category:
            continue

        result = await db.execute(
            text(
                "UPDATE futures_markets "
                "SET llm_sport_category = :category "
                "WHERE source = 'kalshi' "
                "AND LOWER(external_id) LIKE :pattern "
                "AND (llm_sport_category IS NULL OR llm_sport_category != :category)"
            ),
            {"category": correct_category, "pattern": f"{prefix}%"},
        )
        if result.rowcount > 0:
            fixed_by_sport[correct_category] = fixed_by_sport.get(correct_category, 0) + result.rowcount
            total_fixed += result.rowcount

    await db.commit()

    return {
        "total_fixed": total_fixed,
        "by_sport": fixed_by_sport,
    }


async def _compute_link_rate(
    db: AsyncSession,
    stmt_timeout_s: Optional[int] = _LINK_RATE_STMT_TIMEOUT_S,
) -> dict:
    """Compute the game-level prediction-market link-rate payload.

    Filters to only markets that SHOULD be linked (game-level sports markets,
    excluding politics/crypto/weather) and reports what % are actually linked,
    broken down by sport.

    Extracted from the route (L2-90) so the precompute task and the route's
    cold-cache fallback share one implementation.

    ``stmt_timeout_s`` (Queue #250 Item 3c) sets a per-query Postgres
    ``statement_timeout`` so a runaway query fails fast (QueryCanceledError)
    instead of hanging past the 30s router limit. The route uses the default
    (20s, below the router limit); the background precompute passes a more
    generous bound since it runs off the request path. Pass ``None`` to skip.
    """
    if stmt_timeout_s:
        # SET LOCAL scopes the timeout to this session's current transaction
        # (same idiom as tier1_source_compliance below + the precompute tasks).
        await db.execute(
            text(f"SET LOCAL statement_timeout = '{int(stmt_timeout_s)}s'")
        )

    # Build game-level ticker filter for Kalshi.
    # Only count markets with game ticker prefixes — these are the markets
    # the matching task's Pass 1 scans. The old `event_id IS NOT NULL` clause
    # pulled in season futures (awards, Stanley Cup, etc.) that were
    # erroneously linked, inflating the denominator with unlinkable markets.
    _kalshi_ticker_conditions = [
        func.lower(FuturesMarket.external_id).like(f"{p}%")
        for p in KALSHI_LINK_RATE_GAME_TICKER_PREFIXES
    ]
    _kalshi_game_filter = or_(*_kalshi_ticker_conditions)
    _game_name_filter = _link_rate_game_name_filter()

    # Kalshi: game-level markets only (ticker prefix match). Aggregate in
    # Python so old settlement-open unlinked markets can be excluded using the
    # game date embedded in the ticker.
    #
    # Category filter: exclude season-level categories (championship, award,
    # season_win_total, player_futures, etc.) that cannot be linked to events.
    # Markets with game_prop category or already-linked (event_id IS NOT NULL)
    # always pass.
    kalshi_result = await db.execute(
        select(
            FuturesMarket.llm_sport_category.label("sport"),
            FuturesMarket.llm_league.label("league"),
            FuturesMarket.event_id,
            FuturesMarket.status,
            FuturesMarket.external_id,
            FuturesMarket.category,
            FuturesMarket.name,
        )
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.llm_sport_category.isnot(None),
            FuturesMarket.llm_sport_category.in_(_LINK_RATE_SPORT_CATEGORIES),
            _kalshi_game_filter,
            _game_name_filter,
        )
    )
    now = datetime.now(timezone.utc)
    kalshi_rows_by_bucket = {}
    excluded_stale_open_unlinked = 0
    kalshi_excluded_by_category: dict[str, int] = {}
    # #1230: upstream-coverage-gap exclusions (ITF/Setka-TT/minor cricket).
    kalshi_excluded_upstream_gap = 0
    kalshi_excluded_open_upstream_gap = 0
    for row in kalshi_result.all():
        if not _should_include_link_rate_bucket(row.sport, row.league):
            continue
        # Exclude season-level categories from denominator, but keep markets
        # that are already linked (event_id IS NOT NULL) or have game_prop
        # category since those are correctly game-level.
        cat = (row.category or "").lower()
        if cat in _LINK_RATE_NON_GAME_CATEGORIES and row.event_id is None:
            kalshi_excluded_by_category[cat] = (
                kalshi_excluded_by_category.get(cat, 0) + 1
            )
            continue
        # #1230: obscure upstream-coverage circuits (ITF/Setka-TT/minor cricket)
        # can never link — an upstream gap, not a matching bug. Drop unlinked ones
        # from the honest denominator; the raw rate below adds them back.
        if row.event_id is None and _is_upstream_coverage_gap_market(row.name):
            kalshi_excluded_upstream_gap += 1
            if (row.status or "").lower() == "open":
                kalshi_excluded_open_upstream_gap += 1
            continue
        if _should_exclude_stale_open_unlinked_game_market(
            source="kalshi",
            external_id=row.external_id,
            status=row.status,
            event_id=row.event_id,
            now=now,
        ):
            excluded_stale_open_unlinked += 1
            continue

        bucket = (row.sport, row.league)
        sport_data = kalshi_rows_by_bucket.setdefault(
            bucket,
            {
                "sport": row.sport,
                "league": row.league,
                "total": 0,
                "linked": 0,
                "open_total": 0,
                "open_linked": 0,
            },
        )
        sport_data["total"] += 1
        if row.event_id is not None:
            sport_data["linked"] += 1
        if (row.status or "").lower() == "open":
            sport_data["open_total"] += 1
            if row.event_id is not None:
                sport_data["open_linked"] += 1

    kalshi_by_sport = sorted(
        kalshi_rows_by_bucket.values(),
        key=lambda item: item["total"],
        reverse=True,
    )
    kalshi_totals = {"total": 0, "linked": 0, "open_total": 0, "open_linked": 0}
    for sport_data in kalshi_by_sport:
        sport_data["link_rate"] = (
            round(sport_data["open_linked"] / sport_data["open_total"] * 100, 1)
            if sport_data["open_total"] else 0
        )
        sport_data["link_rate_all"] = (
            round(sport_data["linked"] / sport_data["total"] * 100, 1)
            if sport_data["total"] else 0
        )
        for k in kalshi_totals:
            kalshi_totals[k] += sport_data[k]

    # Polymarket: start with the old broad SQL denominator, then apply the same
    # Python game-level predicate used by the matcher. The broad "vs"/"at"
    # filter catches many tournament labels that the matcher will never scan
    # (e.g. "World Championships: Team A vs Team B"), so counting them as
    # health gaps makes the headline rate noisy.
    poly_result = await db.execute(
        select(
            FuturesMarket.llm_sport_category.label("sport"),
            FuturesMarket.llm_league.label("league"),
            FuturesMarket.event_id,
            FuturesMarket.status,
            FuturesMarket.name,
            FuturesMarket.category,
            FuturesMarket.external_id,
        )
        .where(
            FuturesMarket.source == "polymarket",
            FuturesMarket.llm_sport_category.isnot(None),
            FuturesMarket.llm_sport_category.in_(_LINK_RATE_SPORT_CATEGORIES),
            or_(
                FuturesMarket.name.ilike("% vs.%"),
                FuturesMarket.name.ilike("% vs %"),
                FuturesMarket.name.ilike("% at %"),
            ),
            _game_name_filter,
        )
    )
    poly_rows_by_bucket = {}
    poly_totals = {"total": 0, "linked": 0, "open_total": 0, "open_linked": 0}
    poly_excluded_not_matcher_game_level = 0
    poly_excluded_open_not_matcher_game_level = 0
    poly_excluded_samples = []
    poly_excluded_by_category: dict[str, int] = {}
    # #1230: upstream-coverage-gap exclusions (ITF/Setka-TT/minor cricket).
    poly_excluded_upstream_gap = 0
    poly_excluded_open_upstream_gap = 0
    for row in poly_result.all():
        if not _should_include_link_rate_bucket(row.sport, row.league):
            continue
        # Exclude season-level categories from denominator (same logic as Kalshi).
        cat = (row.category or "").lower()
        if cat in _LINK_RATE_NON_GAME_CATEGORIES and row.event_id is None:
            poly_excluded_by_category[cat] = (
                poly_excluded_by_category.get(cat, 0) + 1
            )
            continue
        # #1230: obscure upstream-coverage circuits (ITF minor tennis, Setka/TT-Cup
        # table tennis, minor cricket) dominate the unlinked Polymarket residual and
        # can never link — an upstream gap, not a matching bug. Drop unlinked ones
        # from the honest denominator; the raw rate below adds them back.
        if row.event_id is None and _is_upstream_coverage_gap_market(row.name):
            poly_excluded_upstream_gap += 1
            if (row.status or "").lower() == "open":
                poly_excluded_open_upstream_gap += 1
            continue
        if not _is_polymarket_matcher_game_level(
            row.name,
            row.category,
            row.external_id,
        ):
            poly_excluded_not_matcher_game_level += 1
            if (row.status or "").lower() == "open":
                poly_excluded_open_not_matcher_game_level += 1
                if len(poly_excluded_samples) < 10:
                    poly_excluded_samples.append(
                        {
                            "sport": row.sport,
                            "league": row.league,
                            "name": row.name,
                            "category": row.category,
                            "external_id": row.external_id,
                        }
                    )
            continue

        bucket = (row.sport, row.league)
        sport_data = poly_rows_by_bucket.setdefault(
            bucket,
            {
                "sport": row.sport,
                "league": row.league,
                "total": 0,
                "linked": 0,
                "open_total": 0,
                "open_linked": 0,
            },
        )
        sport_data["total"] += 1
        if row.event_id is not None:
            sport_data["linked"] += 1
        if (row.status or "").lower() == "open":
            sport_data["open_total"] += 1
            if row.event_id is not None:
                sport_data["open_linked"] += 1

    poly_by_sport = sorted(
        poly_rows_by_bucket.values(),
        key=lambda item: item["total"],
        reverse=True,
    )
    for sport_data in poly_by_sport:
        sport_data["link_rate"] = (
            round(sport_data["open_linked"] / sport_data["open_total"] * 100, 1)
            if sport_data["open_total"] else 0
        )
        sport_data["link_rate_all"] = (
            round(sport_data["linked"] / sport_data["total"] * 100, 1)
            if sport_data["total"] else 0
        )
        for k in poly_totals:
            poly_totals[k] += sport_data[k]

    grand_total = kalshi_totals["total"] + poly_totals["total"]
    grand_linked = kalshi_totals["linked"] + poly_totals["linked"]
    grand_open_total = kalshi_totals["open_total"] + poly_totals["open_total"]
    grand_open_linked = kalshi_totals["open_linked"] + poly_totals["open_linked"]
    grand_excluded_by_category = sum(kalshi_excluded_by_category.values()) + sum(
        poly_excluded_by_category.values()
    )
    # #1230: upstream-coverage-gap totals. The honest denominator drops these;
    # the RAW rate adds them back (they are all unlinked) so we never hide data.
    grand_excluded_upstream_gap = (
        kalshi_excluded_upstream_gap + poly_excluded_upstream_gap
    )
    grand_excluded_open_upstream_gap = (
        kalshi_excluded_open_upstream_gap + poly_excluded_open_upstream_gap
    )

    def _raw_open_rate(open_linked: int, open_total: int, excluded_open: int) -> float:
        """Rate against the RAW pre-exclusion denominator (excluded rows are all
        unlinked, so they only inflate the denominator)."""
        raw_total = open_total + excluded_open
        return round(open_linked / raw_total * 100, 1) if raw_total else 0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": {
            "total_game_markets": grand_total,
            "linked": grand_linked,
            "link_rate_pct": round(grand_open_linked / grand_open_total * 100, 1) if grand_open_total else 0,
            "link_rate_all_pct": round(grand_linked / grand_total * 100, 1) if grand_total else 0,
            # #1230: raw rate keeps the upstream-coverage-gap markets in the
            # denominator so the honest vs. raw gap stays visible (no hidden data).
            "link_rate_raw_pct": _raw_open_rate(
                grand_open_linked, grand_open_total, grand_excluded_open_upstream_gap
            ),
            "open_total": grand_open_total,
            "open_linked": grand_open_linked,
            "denominator_note": "Headline rate uses open markets only. link_rate_all_pct includes all statuses. link_rate_raw_pct re-adds the #1230 upstream-coverage-gap exclusions (ITF/Setka-TT/minor cricket) so both the honest and raw denominators are visible.",
            "excluded_stale_open_unlinked": excluded_stale_open_unlinked,
            "excluded_non_game_category": grand_excluded_by_category,
            "excluded_upstream_coverage_gap": grand_excluded_upstream_gap,
            "excluded_open_upstream_coverage_gap": grand_excluded_open_upstream_gap,
        },
        "kalshi": {
            "totals": {
                **kalshi_totals,
                "link_rate_pct": round(kalshi_totals["open_linked"] / kalshi_totals["open_total"] * 100, 1) if kalshi_totals["open_total"] else 0,
                "link_rate_all_pct": round(kalshi_totals["linked"] / kalshi_totals["total"] * 100, 1) if kalshi_totals["total"] else 0,
                "link_rate_raw_pct": _raw_open_rate(
                    kalshi_totals["open_linked"], kalshi_totals["open_total"], kalshi_excluded_open_upstream_gap
                ),
                "excluded_stale_open_unlinked": excluded_stale_open_unlinked,
                "excluded_upstream_coverage_gap": kalshi_excluded_upstream_gap,
                "excluded_open_upstream_coverage_gap": kalshi_excluded_open_upstream_gap,
            },
            "by_sport": kalshi_by_sport,
            "excluded_from_denominator": {
                "note": "Markets excluded because their category is season-level (not game-level). Already-linked markets are kept even with non-game categories.",
                "total": sum(kalshi_excluded_by_category.values()),
                "by_category": kalshi_excluded_by_category,
            },
        },
        "polymarket": {
            "totals": {
                **poly_totals,
                "link_rate_pct": round(poly_totals["open_linked"] / poly_totals["open_total"] * 100, 1) if poly_totals["open_total"] else 0,
                "link_rate_all_pct": round(poly_totals["linked"] / poly_totals["total"] * 100, 1) if poly_totals["total"] else 0,
                "link_rate_raw_pct": _raw_open_rate(
                    poly_totals["open_linked"], poly_totals["open_total"], poly_excluded_open_upstream_gap
                ),
                "excluded_not_matcher_game_level": poly_excluded_not_matcher_game_level,
                "excluded_open_not_matcher_game_level": poly_excluded_open_not_matcher_game_level,
                "excluded_upstream_coverage_gap": poly_excluded_upstream_gap,
                "excluded_open_upstream_coverage_gap": poly_excluded_open_upstream_gap,
            },
            "by_sport": poly_by_sport,
            "excluded_from_denominator": {
                "note": "Markets excluded because their category is season-level (not game-level). Already-linked markets are kept even with non-game categories.",
                "total": sum(poly_excluded_by_category.values()),
                "by_category": poly_excluded_by_category,
            },
            "denominator_diagnostics": {
                "note": "Excluded rows match the old broad sport + vs/at SQL denominator but fail the matcher is_game_level_market() predicate.",
                "sample_excluded_open": poly_excluded_samples,
            },
        },
    }


# Derivative / prop sub-markets that carry BOTH team names but are NOT the
# game-WINNER (moneyline). The unlinked-held check's definition is "game-winner
# market", but the raw both-teams match leaks these in two ways: a "- First 5
# Innings Winner" suffix survives extract_matchup as a dirty team_b that still
# substring-matches, and "- Player Props" gets its suffix stripped so it looks
# identical to the moneyline. Excluding them keeps the metric honest to its
# definition and stops the Flow Sentinel filing cry-wolf issues for markets that
# are not blend-critical (their event_id, when wanted, comes from group_id
# propagation off the moneyline / the game-markets group fallback — NOT a
# name-match miss). #224.
_NON_GAME_WINNER_MARKET_RE = re.compile(
    r"\b("
    r"player\s+props|"
    r"first\s+\d+\s+innings|first\s+(five|three|seven)\s+innings|f5\b|"
    r"first\s+half|1st\s+half|second\s+half|2nd\s+half|"
    r"first\s+quarter|1st\s+quarter|first\s+period|1st\s+period|"
    r"total\s+(runs|points|goals|hits|bases|sets|games)|over/under|over\s+under|"
    r"run\s+line|puck\s+line|spread|handicap|"
    r"correct\s+score|winning\s+margin|margin\s+of\s+victory|"
    r"double\s+chance|both\s+teams\s+to\s+score|btts|"
    r"to\s+score|anytime|home\s+run|strikeouts|rbis?"
    r")\b",
    re.IGNORECASE,
)


def _is_non_game_winner_derivative(name: str) -> bool:
    """True for a matchup-named market that is a derivative/prop sub-market
    (First N Innings Winner, Player Props, halves/quarters, totals, run line,
    spread, etc.) rather than the full-game winner. Used to keep the
    unlinked-held check to its stated 'game-winner' definition."""
    return bool(_NON_GAME_WINNER_MARKET_RE.search(name or ""))


def _matchup_matches_event(matchup, home: str, away: str, external_id: str | None) -> bool:
    """True when a market matchup's BOTH teams correspond to an event's two teams
    (either orientation). Stricter than match_teams_to_event (which fires on one
    side) — requiring both sides present keeps the unlinked-held check high-precision
    so a filed miss is a real matcher failure, not a coincidental one-name overlap."""
    from app.utils.prediction_market_matching import (
        _fuzzy_team_match,
        extract_teams_from_ticker,
    )

    pairs: list[tuple[str, str]] = []
    a = getattr(matchup, "team_a", None)
    b = getattr(matchup, "team_b", None)
    if a and b:
        pairs.append((a, b))
    if external_id:
        tt = extract_teams_from_ticker(external_id)
        if tt:
            pairs.append(tt)
    for ta, tb in pairs:
        if (_fuzzy_team_match(ta, home) and _fuzzy_team_match(tb, away)) or (
            _fuzzy_team_match(ta, away) and _fuzzy_team_match(tb, home)
        ):
            return True
    return False


async def _compute_unlinked_held(db: AsyncSession) -> dict:
    """The STRONGER linkage check (Queue #223 Item 4, Alex's ruling): a game-winner
    market we HOLD in the DB (Kalshi/Polymarket, status open, event_id IS NULL) whose
    BOTH teams match an imminent event — i.e. the matcher had everything it needed and
    still missed the link. Distinct from blend-integrity (matured-linkage): that finds
    a blend source with no market; THIS finds a market with no link. Catchable today.

    Bounded + high-precision: scans only unlinked open Kalshi/Poly markets resolving
    near now, requires a game-level shape AND a both-teams match to an imminent event.
    Read-only."""
    from app.utils.prediction_market_matching import (
        extract_matchup,
        is_game_level_market,
    )

    await db.execute(text("SET LOCAL statement_timeout = '15s'"))
    # Imminent events (same window as matured-linkage).
    imm_rows = (
        await db.execute(
            text(
                """
                SELECT e.id, s.key AS sport_key,
                       e.home_team_name AS home, e.away_team_name AS away,
                       e.away_team_name || ' @ ' || e.home_team_name AS matchup,
                       e.commence_time
                FROM events e
                JOIN sports s ON s.id = e.sport_id
                WHERE e.status IN ('scheduled', 'live')
                  AND e.commence_time >= NOW() - INTERVAL '6 hours'
                  AND e.commence_time <= NOW() + INTERVAL '24 hours'
                  AND e.home_team_name IS NOT NULL
                  AND e.away_team_name IS NOT NULL
                """
            )
        )
    ).all()
    imm = [
        {
            "id": r.id,
            "sport": r.sport_key,
            "home": r.home,
            "away": r.away,
            "matchup": r.matchup,
            "commence_time": r.commence_time,
        }
        for r in imm_rows
    ]
    if not imm:
        return {
            "headline_unlinked_held": 0,
            "status": "insufficient_slate",
            "events_checked": 0,
            "candidates_scanned": 0,
            "misses": [],
            "by_source": {},
            "definition": (
                "Unlinked-but-held: a Kalshi/Polymarket game-winner market we hold "
                "(status open, event_id NULL) whose both teams match an imminent event "
                "— the matcher missed a link it could have made. 0 = clean."
            ),
        }

    # Bounded candidate pool: unlinked open Kalshi/Poly markets resolving near now.
    cand = (
        await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.name,
                FuturesMarket.external_id,
                FuturesMarket.source,
                FuturesMarket.llm_sport_category,
            ).where(
                FuturesMarket.event_id.is_(None),
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.status == "open",
                FuturesMarket.resolution_date.isnot(None),
                FuturesMarket.resolution_date >= datetime.now(timezone.utc) - timedelta(days=2),
                FuturesMarket.resolution_date <= datetime.now(timezone.utc) + timedelta(days=10),
            ).limit(2000)
        )
    ).all()

    misses: list[dict] = []
    seen: set[tuple] = set()
    derivatives_excluded = 0
    for m in cand:
        if not is_game_level_market(m.name or "", m.llm_sport_category, external_id=m.external_id):
            continue
        # Keep the metric to its "game-winner" definition: skip derivative/prop
        # sub-markets (First N Innings Winner, Player Props, halves, totals, run
        # line, ...) — they carry both team names but are not the moneyline, so
        # they are not a blend-critical name-match miss (#224).
        if _is_non_game_winner_derivative(m.name or ""):
            derivatives_excluded += 1
            continue
        matchup = extract_matchup(m.name or "", m.external_id)
        if matchup is None:
            continue
        for ev in imm:
            if _matchup_matches_event(matchup, ev["home"], ev["away"], m.external_id):
                key = (ev["id"], m.source, m.id)
                if key in seen:
                    break
                seen.add(key)
                misses.append(
                    {
                        "event_id": ev["id"],
                        "source": m.source,
                        "sport": ev["sport"],
                        "matchup": ev["matchup"],
                        "market_id": m.id,
                        "market_name": m.name,
                        "commence_time": ev["commence_time"].isoformat()
                        if ev["commence_time"]
                        else None,
                    }
                )
                break

    by_source: dict[str, int] = {}
    for miss in misses:
        by_source[miss["source"]] = by_source.get(miss["source"], 0) + 1

    return {
        "headline_unlinked_held": len(misses),
        "status": "ok",
        "events_checked": len(imm),
        "candidates_scanned": len(cand),
        "derivatives_excluded": derivatives_excluded,
        "misses": misses,
        "by_source": by_source,
        "definition": (
            "Unlinked-but-held: a Kalshi/Polymarket game-WINNER (moneyline) market "
            "we hold (status open, event_id NULL) whose both teams match an imminent "
            "event — the matcher missed a link it could have made. Derivative/prop "
            "sub-markets (First N Innings Winner, Player Props, halves, totals, run "
            "line, ...) are EXCLUDED (they are not blend-critical; their link comes "
            "from group_id propagation, not a name match). 0 = clean; >0 = real "
            "game-winner match-failures (distinct from blend-integrity phantoms)."
        ),
    }


async def _compute_matured_linkage(db: AsyncSession) -> dict:
    """Compute the matured-linkage metric (Queue #220/221 Item 2).

    Headline linkage number that MEANS something (Alex's ruling): for imminent
    events (scheduled/live, starting within NOW-6h..NOW+24h), every prediction-
    market source present in the event's blend (win_probability_sources) must be
    backed by a linked winner market. See app/utils/matured_linkage.py for the
    full rationale. One SQL over the imminent slate; below-100 = a real phantom."""
    from app.utils.matured_linkage import CHECKABLE_SOURCES, summarize_matured_linkage

    await db.execute(text("SET LOCAL statement_timeout = '15s'"))
    result = await db.execute(
        text(
            """
            WITH imm AS (
                SELECT e.id, s.key AS sport_key,
                       e.away_team_name || ' @ ' || e.home_team_name AS matchup,
                       e.commence_time, e.status,
                       e.win_probability_sources AS wps
                FROM events e
                JOIN sports s ON s.id = e.sport_id
                WHERE e.status IN ('scheduled', 'live')
                  AND e.commence_time >= NOW() - INTERVAL '6 hours'
                  AND e.commence_time <= NOW() + INTERVAL '24 hours'
                  AND e.win_probability_sources IS NOT NULL
            ),
            blend_pairs AS (
                SELECT imm.id, imm.sport_key, imm.matchup, imm.commence_time,
                       jsonb_object_keys(imm.wps) AS src
                FROM imm
            )
            SELECT bp.id AS event_id, bp.sport_key, bp.matchup, bp.commence_time,
                   bp.src AS source,
                   EXISTS (
                       SELECT 1 FROM futures_markets fm
                       WHERE fm.event_id = bp.id AND fm.source = bp.src
                   ) AS linked
            FROM blend_pairs bp
            WHERE bp.src = ANY(:checkable)
            """
        ),
        {"checkable": list(CHECKABLE_SOURCES)},
    )
    rows = [
        {
            "event_id": r.event_id,
            "sport": r.sport_key,
            "matchup": r.matchup,
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "source": r.source,
            "linked": bool(r.linked),
        }
        for r in result.all()
    ]
    payload = summarize_matured_linkage(rows)
    payload["window"] = "NOW-6h..NOW+24h"
    # Queue #223 Item 4: the stronger linkage class (unlinked-but-held) rides the
    # same payload/endpoint/Redis key so the cockpit + sentinel see both classes.
    try:
        payload["unlinked_held"] = await _compute_unlinked_held(db)
    except Exception as exc:
        payload["unlinked_held"] = {"status": "error", "error": str(exc)[:160]}
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


@router.get("/prediction-markets/matured-linkage")
async def prediction_market_matured_linkage(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    bust: int = Query(0, include_in_schema=False),
    db: AsyncSession = Depends(get_db),
):
    """Matured-linkage — the headline linkage metric where below-100 MEANS a real
    defect (Queue #220/221 Item 2). Served warm from Redis; ?bust=1 recomputes."""
    _check_admin_secret(secret, request=request)

    import json as _json

    if not bust:
        try:
            from app.tasks.redis_state import get_redis_client
            cached = get_redis_client().get("bainluck:admin:matured_linkage")
            if cached:
                return _json.loads(cached)
        except Exception:
            pass

    payload = await _compute_matured_linkage(db)
    try:
        from app.tasks.redis_state import get_redis_client
        get_redis_client().set(
            "bainluck:admin:matured_linkage", _json.dumps(payload), ex=3600
        )
    except Exception:
        pass
    return payload


@router.get("/prediction-markets/link-rate")
async def prediction_market_link_rate(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    bust: int = Query(0, include_in_schema=False),
    db: AsyncSession = Depends(get_db),
):
    """Game-level market link rate — served from the L2-90 async cache.

    The compute (~25s over the sports futures subset) was 503ing at the 30s
    router limit under load. The ``precompute_admin_link_rate`` beat keeps a
    Redis snapshot warm; a cold cache or ``?bust=1`` falls back to computing
    inline (same result as before) and rewarms the cache.

    Queue #250 Item 3c hardening — this endpoint must never 503:
    - the compute arms a per-query ``statement_timeout`` (below the 30s router
      limit) so a runaway query fails fast instead of hanging into an H12; and
    - if the fresh compute times out or errors, we serve the last cached
      snapshot (marked ``stale``) rather than propagating the error. With no
      cache at all we degrade to a clearly-marked empty payload.
    """
    _check_admin_secret(secret, request=request)

    import asyncio
    import json as _json

    if not bust:
        try:
            from app.tasks.redis_state import get_redis_client
            cached = get_redis_client().get(_LINK_RATE_CACHE_KEY)
            if cached:
                return _json.loads(cached)
        except Exception:
            logger.warning("link-rate: cache read failed, computing inline", exc_info=True)

    try:
        # Wall-clock bound below the 30s router limit — the primary 503 defense.
        # If the compute overruns, wait_for cancels it and raises TimeoutError,
        # which the handler below turns into a served-stale-cache 200.
        payload = await asyncio.wait_for(
            _compute_link_rate(db), timeout=_LINK_RATE_WALLCLOCK_S
        )
    except Exception as exc:
        # Serve-cache-on-timeout: the fresh compute (usually ?bust=1, which
        # bypasses the warm cache) can hit the wall-clock bound, the per-query
        # statement_timeout, or otherwise exceed the 30s router limit. Fall back
        # to the last cached snapshot so the endpoint never 503s. Log the timeout
        # distinctly (do NOT swallow it silently — a repeated timeout is itself a
        # signal worth seeing).
        is_timeout = (
            isinstance(exc, (asyncio.TimeoutError, TimeoutError))
            or "canceling statement" in str(exc).lower()
            or type(exc).__name__ in ("QueryCanceledError", "OperationalError")
        )
        logger.warning(
            "link-rate: fresh compute failed (%s: %s); serving cached snapshot",
            "statement_timeout" if is_timeout else type(exc).__name__,
            exc,
        )
        try:
            from app.tasks.redis_state import get_redis_client
            cached = get_redis_client().get(_LINK_RATE_CACHE_KEY)
            if cached:
                stale_payload = _json.loads(cached)
                stale_payload["stale"] = True
                stale_payload["stale_reason"] = (
                    "compute_timeout" if is_timeout else "compute_error"
                )
                return stale_payload
        except Exception:
            logger.warning("link-rate: stale-cache fallback read failed", exc_info=True)
        # No cache to fall back to — degrade gracefully rather than 503.
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "stale": True,
            "unavailable": True,
            "stale_reason": "compute_timeout" if is_timeout else "compute_error",
            "overall": {},
            "kalshi": {},
            "polymarket": {},
        }

    try:
        from app.tasks.redis_state import get_redis_client
        get_redis_client().set(
            _LINK_RATE_CACHE_KEY, _json.dumps(payload), ex=3600
        )
    except Exception:
        logger.warning("link-rate: cache write failed", exc_info=True)
    return payload


@router.get("/prediction-markets/tier1-compliance")
async def tier1_source_compliance(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Hill-climb metric: every Tier 1 event must have ALL sources linked.

    Tier 1 sports: MLB, NBA, NHL, NFL, PGA.
    Required sources: Odds API, ESPN, StatPal, Kalshi, Polymarket (+ DataGolf for PGA).
    Only counts scheduled/live events happening today (-6h to +12h).
    Target: 100% compliance for each sport × source cell. No excuses.
    """
    _check_admin_secret(secret, request=request)

    from sqlalchemy import text as _text
    await db.execute(_text("SET LOCAL statement_timeout = '15s'"))

    result = await db.execute(_text("""
        WITH tier1_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.home_team_name, e.away_team_name,
                   e.external_id AS odds_api_id,
                   e.espn_id,
                   e.statpal_fixture_id,
                   e.commence_time, e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl', 'americanfootball_nfl')
              AND e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
              AND e.commence_time <= NOW() + INTERVAL '12 hours'
        ),
        kalshi_links AS (
            SELECT DISTINCT fm.event_id
            FROM futures_markets fm
            WHERE fm.source = 'kalshi' AND fm.event_id IS NOT NULL
        ),
        poly_links AS (
            SELECT DISTINCT fm.event_id
            FROM futures_markets fm
            WHERE fm.source = 'polymarket' AND fm.event_id IS NOT NULL
        )
        SELECT
            te.sport_key,
            COUNT(*) AS total,
            COUNT(te.odds_api_id) AS has_odds_api,
            COUNT(te.espn_id) AS has_espn,
            COUNT(te.statpal_fixture_id) AS has_statpal,
            COUNT(kl.event_id) AS has_kalshi,
            COUNT(pl.event_id) AS has_polymarket,
            COUNT(CASE WHEN te.odds_api_id IS NOT NULL
                        AND te.espn_id IS NOT NULL
                        AND te.statpal_fixture_id IS NOT NULL
                        AND kl.event_id IS NOT NULL
                        AND pl.event_id IS NOT NULL
                       THEN 1 END) AS fully_compliant
        FROM tier1_events te
        LEFT JOIN kalshi_links kl ON kl.event_id = te.id
        LEFT JOIN poly_links pl ON pl.event_id = te.id
        GROUP BY te.sport_key
        ORDER BY te.sport_key
    """))

    by_sport = []
    totals = {"total": 0, "compliant": 0}
    for row in result.fetchall():
        t = row.total
        sport_data = {
            "sport": row.sport_key,
            "total": t,
            "odds_api": row.has_odds_api,
            "espn": row.has_espn,
            "statpal": row.has_statpal,
            "kalshi": row.has_kalshi,
            "polymarket": row.has_polymarket,
            "fully_compliant": row.fully_compliant,
            "compliance_pct": round(row.fully_compliant / max(t, 1) * 100, 1),
            "gaps": {
                "odds_api": t - row.has_odds_api,
                "espn": t - row.has_espn,
                "statpal": t - row.has_statpal,
                "kalshi": t - row.has_kalshi,
                "polymarket": t - row.has_polymarket,
            },
        }
        by_sport.append(sport_data)
        totals["total"] += t
        totals["compliant"] += row.fully_compliant

    # Per-event gaps for non-compliant events (show what's missing)
    gap_result = await db.execute(_text("""
        WITH tier1_events AS (
            SELECT e.id, s.key AS sport_key,
                   e.home_team_name, e.away_team_name,
                   e.external_id AS odds_api_id, e.espn_id, e.statpal_fixture_id,
                   e.commence_time, e.status
            FROM events e
            JOIN sports s ON e.sport_id = s.id
            WHERE s.key IN ('baseball_mlb', 'basketball_nba', 'icehockey_nhl', 'americanfootball_nfl')
              AND e.status IN ('scheduled', 'live')
              AND e.commence_time >= NOW() - INTERVAL '6 hours'
              AND e.commence_time <= NOW() + INTERVAL '12 hours'
        ),
        kalshi_links AS (
            SELECT DISTINCT fm.event_id FROM futures_markets fm
            WHERE fm.source = 'kalshi' AND fm.event_id IS NOT NULL
        ),
        poly_links AS (
            SELECT DISTINCT fm.event_id FROM futures_markets fm
            WHERE fm.source = 'polymarket' AND fm.event_id IS NOT NULL
        )
        SELECT te.id, te.sport_key,
               te.away_team_name || ' @ ' || te.home_team_name AS matchup,
               te.commence_time, te.status,
               te.odds_api_id IS NULL AS missing_odds_api,
               te.espn_id IS NULL AS missing_espn,
               te.statpal_fixture_id IS NULL AS missing_statpal,
               kl.event_id IS NULL AS missing_kalshi,
               pl.event_id IS NULL AS missing_polymarket
        FROM tier1_events te
        LEFT JOIN kalshi_links kl ON kl.event_id = te.id
        LEFT JOIN poly_links pl ON pl.event_id = te.id
        WHERE te.odds_api_id IS NULL
           OR te.espn_id IS NULL
           OR te.statpal_fixture_id IS NULL
           OR kl.event_id IS NULL
           OR pl.event_id IS NULL
        ORDER BY te.commence_time
        LIMIT 30
    """))
    gaps = []
    for row in gap_result.fetchall():
        missing = []
        if row.missing_odds_api: missing.append("odds_api")
        if row.missing_espn: missing.append("espn")
        if row.missing_statpal: missing.append("statpal")
        if row.missing_kalshi: missing.append("kalshi")
        if row.missing_polymarket: missing.append("polymarket")
        gaps.append({
            "id": row.id,
            "sport": row.sport_key,
            "matchup": row.matchup,
            "time": row.commence_time.isoformat() if row.commence_time else None,
            "status": row.status,
            "missing": missing,
        })

    return {
        "target": "100% — every Tier 1 event happening today has all 5 sources",
        "compliance_pct": round(totals["compliant"] / max(totals["total"], 1) * 100, 1),
        "total_events": totals["total"],
        "fully_compliant": totals["compliant"],
        "by_sport": by_sport,
        "non_compliant_events": gaps,
        "golf": await _golf_compliance(db),
    }


async def _golf_compliance(db: AsyncSession) -> dict:
    """PGA compliance: active PGA tournament must have all market types from all 3 sources."""
    from sqlalchemy import text as _text

    _REQUIRED_TYPES = ["win", "top_5", "top_10", "top_20", "make_cut"]
    _REQUIRED_SOURCES = ["datagolf", "kalshi", "polymarket"]

    try:
        # Find active PGA tournaments from DataGolf (tour = 'pga', status != 'resolved')
        result = await db.execute(_text("""
            SELECT DISTINCT
                fm.market_metadata->>'datagolf_event_id' AS event_id,
                SPLIT_PART(fm.name, ' - ', 1) AS tournament_name
            FROM futures_markets fm
            WHERE fm.source = 'datagolf'
              AND fm.status IN ('open', 'closed')
              AND COALESCE(fm.market_metadata->>'tour', '') = 'pga'
            ORDER BY tournament_name
        """))
        pga_tournaments = result.fetchall()

        tournaments = []
        for t in pga_tournaments:
            event_id = t.event_id
            name = t.tournament_name
            search_term = name.strip()[:30].lower()
            if not search_term:
                continue

            by_source = {}
            for source in _REQUIRED_SOURCES:
                if source == "datagolf":
                    type_result = await db.execute(_text(
                        "SELECT SPLIT_PART(external_id, ':', 4) AS mtype"
                        " FROM futures_markets"
                        " WHERE source = 'datagolf' AND status IN ('open', 'closed')"
                        "   AND market_metadata->>'datagolf_event_id' = :eid"
                    ), {"eid": event_id})
                else:
                    type_result = await db.execute(_text(
                        "SELECT CASE"
                        "   WHEN lower(name) LIKE :win THEN 'win'"
                        "   WHEN lower(name) LIKE :cut THEN 'make_cut'"
                        "   WHEN lower(name) LIKE :t5 THEN 'top_5'"
                        "   WHEN lower(name) LIKE :t10 THEN 'top_10'"
                        "   WHEN lower(name) LIKE :t20 THEN 'top_20'"
                        "   ELSE 'other' END AS mtype"
                        " FROM futures_markets"
                        " WHERE source = :source AND llm_sport_category = 'golf'"
                        "   AND status = 'open' AND lower(name) LIKE :pattern"
                    ), {
                        "source": source, "pattern": f"%{search_term}%",
                        "win": "%winner%", "cut": "%make%cut%",
                        "t5": "%top 5%", "t10": "%top 10%", "t20": "%top 20%",
                    })
                found_types = {row.mtype for row in type_result.fetchall()} - {"other"}
                by_source[source] = sorted(found_types)

            missing = {}
            for source in _REQUIRED_SOURCES:
                missing_types = [mt for mt in _REQUIRED_TYPES if mt not in by_source.get(source, [])]
                if missing_types:
                    missing[source] = missing_types

            tournaments.append({
                "tournament": name,
                "event_id": event_id,
                "by_source": by_source,
                "missing": missing,
                "compliant": not missing,
            })

        compliant_count = sum(1 for t in tournaments if t["compliant"])
        return {
            "total": len(tournaments),
            "compliant": compliant_count,
            "compliance_pct": round(compliant_count / max(len(tournaments), 1) * 100, 1),
            "required_types": _REQUIRED_TYPES,
            "required_sources": _REQUIRED_SOURCES,
            "tournaments": tournaments,
        }
    except Exception as e:
        return {"error": str(e), "total": 0, "compliant": 0, "compliance_pct": 0, "tournaments": []}


@router.get("/prediction-markets/game-diagnostics")
async def prediction_market_game_diagnostics(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport: str = Query(None, description="Filter to prefixes for a sport (e.g. 'mlb', 'nba')"),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose game-level prediction market matching for major sports.

    Shows counts of game-level markets by ticker prefix, their link status,
    and sample unlinked markets to identify matching failures.
    Pass ?sport=mlb to filter to MLB prefixes only.
    """
    _check_admin_secret(secret, request=request)

    from sqlalchemy import func, case, text as _text
    from app.models.models import FuturesMarket
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

    await db.execute(_text("SET LOCAL statement_timeout = '20s'"))

    results = {}

    prefixes = KALSHI_GAME_TICKER_PREFIXES
    if sport:
        prefixes = [p for p in prefixes if sport.lower() in p.lower()]

    for prefix in prefixes:
        pattern = f"{prefix}%"
        stats_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(FuturesMarket.event_id).label("linked"),
                func.count(case((FuturesMarket.status == "open", 1))).label("open"),
            )
            .where(
                FuturesMarket.source == "kalshi",
                func.lower(FuturesMarket.external_id).like(pattern),
            )
        )
        row = stats_result.one()
        if row.total > 0:
            # Get sample unlinked open markets
            sample_result = await db.execute(
                select(
                    FuturesMarket.id,
                    FuturesMarket.external_id,
                    FuturesMarket.name,
                    FuturesMarket.event_id,
                    FuturesMarket.status,
                    FuturesMarket.commence_time,
                )
                .where(
                    FuturesMarket.source == "kalshi",
                    func.lower(FuturesMarket.external_id).like(pattern),
                    FuturesMarket.event_id.is_(None),
                    FuturesMarket.status == "open",
                )
                .order_by(FuturesMarket.commence_time.desc())
                .limit(5)
            )
            samples = [
                {
                    "id": r.id, "external_id": r.external_id, "name": r.name,
                    "event_id": r.event_id, "status": r.status,
                    "commence_time": r.commence_time.isoformat() if r.commence_time else None,
                }
                for r in sample_result.all()
            ]
            results[prefix] = {
                "total": row.total, "linked": row.linked,
                "unlinked": row.total - row.linked, "open": row.open,
                "sample_unlinked": samples,
            }

    # Also check Polymarket game markets (name contains "vs.")
    for sport_label, name_pattern in [
        ("polymarket_vs", "% vs.%"), ("polymarket_vs_space", "% vs %"),
    ]:
        pm_result = await db.execute(
            select(
                func.count().label("total"),
                func.count(FuturesMarket.event_id).label("linked"),
                func.count(case((FuturesMarket.status == "open", 1))).label("open"),
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.name.ilike(name_pattern),
            )
        )
        pm_row = pm_result.one()
        # Sample unlinked
        pm_sample = await db.execute(
            select(
                FuturesMarket.id, FuturesMarket.external_id,
                FuturesMarket.name, FuturesMarket.event_id,
                FuturesMarket.status, FuturesMarket.commence_time,
                FuturesMarket.llm_sport_category,
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.name.ilike(name_pattern),
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesMarket.updated_at.desc())
            .limit(10)
        )
        results[sport_label] = {
            "total": pm_row.total, "linked": pm_row.linked,
            "unlinked": pm_row.total - pm_row.linked, "open": pm_row.open,
            "sample_unlinked": [
                {
                    "id": r.id, "name": r.name, "event_id": r.event_id,
                    "status": r.status, "sport": r.llm_sport_category,
                    "commence_time": r.commence_time.isoformat() if r.commence_time else None,
                }
                for r in pm_sample.all()
            ],
        }

    # Check NBA events without prediction market links
    # Link is via FuturesMarket.event_id → Event.id
    from app.models.models import Event, Sport
    from sqlalchemy.orm import aliased

    # Get NBA event IDs that DO have linked prediction markets
    linked_event_ids_subq = (
        select(FuturesMarket.event_id)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
        )
        .distinct()
        .scalar_subquery()
    )

    nba_no_links = await db.execute(
        select(
            Event.id, Event.home_team_name, Event.away_team_name,
            Event.commence_time, Event.status,
        )
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key == "basketball_nba",
            Event.status.in_(["scheduled", "live"]),
            ~Event.id.in_(linked_event_ids_subq),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    nba_missing = [
        {
            "event_id": r.id,
            "matchup": f"{r.home_team_name} vs {r.away_team_name}",
            "commence_time": r.commence_time.isoformat() if r.commence_time else None,
            "status": r.status,
        }
        for r in nba_no_links.all()
    ]

    return {
        "kalshi_game_ticker_stats": {k: v for k, v in results.items() if not k.startswith("polymarket")},
        "polymarket_game_stats": {k: v for k, v in results.items() if k.startswith("polymarket")},
        "nba_events_missing_prediction_markets": nba_missing,
    }


@router.get("/prediction-markets/debug")
async def prediction_market_debug(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    source: Optional[str] = Query(None, description="Filter by source (kalshi, polymarket)"),
    sample_size: int = Query(50, description="Number of unlinked markets to analyze"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug prediction market matching by analyzing sample unlinked markets.

    Shows the matching funnel: how many markets pass each stage
    (game-level detection → matchup extraction → event lookup).
    Includes sample market names at each stage for pattern analysis.
    """
    _check_admin_secret(secret, request=request)

    from sqlalchemy import func
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.prediction_market_matching import (
        is_game_level_market,
        extract_matchup,
    )

    # Fetch sample of unlinked markets
    query = (
        select(FuturesMarket)
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "open",
        )
        .order_by(FuturesMarket.updated_at.desc())
        .limit(sample_size)
    )
    if source:
        query = query.where(FuturesMarket.source == source)

    result = await db.execute(query)
    markets = result.scalars().all()

    # Analyze each market through the funnel
    funnel = {
        "total_analyzed": len(markets),
        "game_level": [],      # Passed is_game_level_market
        "not_game_level": [],   # Failed — most common bucket
        "matchup_extracted": [],
        "no_matchup": [],       # Passed game-level but no matchup extracted
    }

    for market in markets:
        entry = {
            "source": market.source,
            "name": market.name,
            "external_id": market.external_id,
            "category": market.category,
            "llm_sport_category": market.llm_sport_category,
        }

        if not is_game_level_market(
            market.name, market.category,
            external_id=market.external_id,
        ):
            funnel["not_game_level"].append(entry)
            continue

        matchup = extract_matchup(market.name, external_id=market.external_id)
        if not matchup:
            entry["note"] = "passed is_game_level but extract_matchup returned None"
            funnel["no_matchup"].append(entry)
            continue

        entry["team_a"] = matchup.team_a
        entry["team_b"] = matchup.team_b
        entry["format_type"] = matchup.format_type
        funnel["game_level"].append(entry)
        funnel["matchup_extracted"].append(entry)

    # Summary counts
    summary = {
        "total_analyzed": funnel["total_analyzed"],
        "not_game_level": len(funnel["not_game_level"]),
        "game_level_detected": len(funnel["game_level"]),
        "matchup_extracted": len(funnel["matchup_extracted"]),
        "no_matchup_after_detection": len(funnel["no_matchup"]),
    }

    return {
        "summary": summary,
        "sample_game_level": funnel["game_level"][:20],
        "sample_not_game_level": funnel["not_game_level"][:20],
        "sample_no_matchup": funnel["no_matchup"][:10],
    }


@router.get("/prediction-markets/tier1-gaps")
async def prediction_market_tier1_gaps(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose every unlinked open Tier 1 game market with failure reasons."""
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func, or_, text as _text
    from app.models.models import FuturesMarket, Event, Sport
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        extract_game_date_from_ticker,
    )
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

    await db.execute(_text("SET LOCAL statement_timeout = '45s'"))

    _TIER1_PREFIXES = [
        p for p in KALSHI_GAME_TICKER_PREFIXES
        if any(p.startswith(s) for s in ("kxnba", "kxnhl", "kxmlb", "kxnfl"))
    ]
    tier1_conditions = [
        func.lower(FuturesMarket.external_id).like(f"{p}%")
        for p in _TIER1_PREFIXES
    ]

    result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.event_id.is_(None),
            FuturesMarket.status == "open",
            or_(*tier1_conditions),
        )
        .order_by(FuturesMarket.commence_time.desc())
        .limit(50)
    )
    markets = result.scalars().all()

    now = datetime.now(timezone.utc)
    gaps = []
    excluded_closed_games = []

    for market in markets:
        entry = {
            "id": market.id,
            "external_id": market.external_id,
            "name": market.name,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
        }

        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )
        if not matchup:
            entry["failure"] = "matchup_extraction_failed"
            gaps.append(entry)
            continue

        entry["extracted_team_a"] = matchup.team_a
        entry["extracted_team_b"] = matchup.team_b
        entry["format_type"] = matchup.format_type

        ticker_date = extract_game_date_from_ticker(market.external_id)
        entry["ticker_date"] = ticker_date.isoformat() if ticker_date else None

        teams_to_search = [matchup.team_a]
        if matchup.team_b:
            teams_to_search.append(matchup.team_b)

        def _esc(s: str) -> str:
            return s.replace("%", r"\%").replace("_", r"\_")

        ilike_conditions = []
        for team in teams_to_search:
            pattern = f"%{_esc(team)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

        ref_time = ticker_date or market.commence_time or now
        time_delta = timedelta(hours=36) if ticker_date else timedelta(days=7)
        time_start = ref_time - time_delta
        time_end = ref_time + time_delta

        event_result = await db.execute(
            select(Event.id, Event.home_team_name, Event.away_team_name,
                   Event.commence_time, Event.status, Event.completed_at)
            .where(
                or_(*ilike_conditions),
                Event.commence_time.between(time_start, time_end),
            )
            .order_by(Event.commence_time)
            .limit(5)
        )
        candidates = event_result.all()

        if not candidates:
            event_any = await db.execute(
                select(Event.id, Event.home_team_name, Event.away_team_name,
                       Event.commence_time, Event.status, Event.completed_at)
                .where(or_(*ilike_conditions))
                .order_by(Event.commence_time.desc())
                .limit(3)
            )
            any_candidates = event_any.all()
            if any_candidates:
                entry["failure"] = "event_exists_but_outside_time_window"
                entry["nearest_events"] = [
                    {"id": c.id, "teams": f"{c.home_team_name} vs {c.away_team_name}",
                     "time": c.commence_time.isoformat() if c.commence_time else None,
                     "status": c.status}
                    for c in any_candidates
                ]
            else:
                entry["failure"] = "no_event_with_matching_teams"
                entry["search_terms"] = teams_to_search
        else:
            if _should_exclude_tier1_gap_for_closed_game(candidates, now):
                entry["excluded_reason"] = "closed_game_settlement_market"
                entry["candidates"] = [
                    {
                        "id": c.id,
                        "teams": f"{c.home_team_name} vs {c.away_team_name}",
                        "time": c.commence_time.isoformat() if c.commence_time else None,
                        "status": c.status,
                    }
                    for c in candidates
                ]
                excluded_closed_games.append(entry)
                continue

            entry["failure"] = "event_found_but_scoring_rejected"
            entry["candidates"] = [
                {"id": c.id, "teams": f"{c.home_team_name} vs {c.away_team_name}",
                 "time": c.commence_time.isoformat() if c.commence_time else None,
                 "status": c.status}
                for c in candidates
            ]

        gaps.append(entry)

    by_failure = {}
    for g in gaps:
        f = g.get("failure", "unknown")
        by_failure.setdefault(f, []).append(g)

    return {
        "total_tier1_gaps": len(gaps),
        "excluded_closed_game_markets": len(excluded_closed_games),
        "excluded_closed_game_samples": excluded_closed_games[:5],
        "by_failure": {k: {"count": len(v), "samples": v[:5]} for k, v in by_failure.items()},
        "all_gaps": gaps,
    }


@router.get("/prediction-markets/match-trace")
async def prediction_market_match_trace(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    external_id: str = Query(..., description="Kalshi external_id to trace"),
    db: AsyncSession = Depends(get_db),
):
    """Trace the matching logic for a specific unlinked market."""
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import or_
    from app.models.models import FuturesMarket, Event
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        extract_game_date_from_ticker,
    )
    from app.tasks.prediction_market_matching import (
        _expand_team_search_terms,
        _escape_like,
    )
    from app.utils.sport_keys import get_sport_key_from_ticker

    result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.external_id == external_id).limit(1)
    )
    market = result.scalars().first()
    if not market:
        raise HTTPException(status_code=404, detail=f"Market not found: {external_id}")

    trace = {
        "market": {
            "id": market.id, "external_id": market.external_id,
            "name": market.name, "source": market.source,
            "event_id": market.event_id, "status": market.status,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
        },
    }

    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)
    ticker_date = extract_game_date_from_ticker(market.external_id)
    sport_key = get_sport_key_from_ticker(market.external_id)

    trace["extraction"] = {
        "matchup": {"team_a": matchup.team_a, "team_b": matchup.team_b, "format": matchup.format_type} if matchup else None,
        "ticker_date": ticker_date.isoformat() if ticker_date else None,
        "sport_key": sport_key,
    }

    if not matchup:
        trace["result"] = "no_matchup"
        return trace

    now = datetime.now(timezone.utc)
    reference_time = ticker_date or market.commence_time or now
    if ticker_date:
        has_time = ticker_date.hour != 0 or ticker_date.minute != 0
        if has_time:
            time_start = reference_time - timedelta(hours=3)
            time_end = reference_time + timedelta(hours=3)
        else:
            time_start = reference_time - timedelta(hours=6)
            time_end = reference_time + timedelta(hours=30)
    elif market.source == "kalshi":
        time_start = reference_time - timedelta(days=7)
        time_end = reference_time + timedelta(days=7)
    else:
        time_start = reference_time - timedelta(hours=48)
        time_end = reference_time + timedelta(hours=48)

    trace["time_window"] = {
        "reference": reference_time.isoformat(),
        "has_time": ticker_date and (ticker_date.hour != 0 or ticker_date.minute != 0) if ticker_date else None,
        "start": time_start.isoformat(),
        "end": time_end.isoformat(),
    }

    teams_to_search = [matchup.team_a]
    if matchup.team_b:
        teams_to_search.append(matchup.team_b)

    expanded_terms = {}
    ilike_conditions = []
    for team in teams_to_search:
        terms = list(_expand_team_search_terms(team))
        expanded_terms[team] = terms
        for term in terms:
            pattern = f"%{_escape_like(term)}%"
            ilike_conditions.append(Event.home_team_name.ilike(pattern))
            ilike_conditions.append(Event.away_team_name.ilike(pattern))

    trace["search_terms"] = expanded_terms

    past_cutoff = now - timedelta(hours=6)

    event_result = await db.execute(
        select(Event.id, Event.home_team_name, Event.away_team_name,
               Event.commence_time, Event.status, Event.sport_id)
        .where(
            or_(*ilike_conditions),
            Event.commence_time.between(time_start, time_end),
            or_(
                Event.status.in_(["scheduled", "live"]),
                Event.commence_time >= past_cutoff,
            ),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    candidates = event_result.all()

    trace["candidates"] = [
        {
            "id": c.id,
            "teams": f"{c.home_team_name} vs {c.away_team_name}",
            "time": c.commence_time.isoformat() if c.commence_time else None,
            "status": c.status,
            "sport_id": c.sport_id,
        }
        for c in candidates
    ]

    if not candidates:
        no_filter_result = await db.execute(
            select(Event.id, Event.home_team_name, Event.away_team_name,
                   Event.commence_time, Event.status)
            .where(or_(*ilike_conditions))
            .order_by(Event.commence_time.desc())
            .limit(5)
        )
        trace["candidates_no_time_filter"] = [
            {
                "id": c.id,
                "teams": f"{c.home_team_name} vs {c.away_team_name}",
                "time": c.commence_time.isoformat() if c.commence_time else None,
                "status": c.status,
            }
            for c in no_filter_result.all()
        ]

    if candidates and matchup:
        from sqlalchemy.orm import joinedload as _jl
        from app.tasks.prediction_market_matching import (
            _score_candidates as score_fn,
            _check_duplicate_kalshi_linkage,
        )
        from app.models.models import Event as EventModel, Sport

        full_events = []
        for c in candidates:
            ev = await db.execute(
                select(EventModel).options(
                    _jl(EventModel.sport)
                ).where(EventModel.id == c.id)
            )
            e = ev.scalars().first()
            if e:
                full_events.append(e)

        scored = score_fn(full_events, matchup, market, now, ticker_date)
        trace["scoring"] = {
            "result": scored,
            "best_event_id": scored["event_id"] if scored else None,
            "score": scored["score"] if scored else None,
        }

        if scored:
            guard_ok = await _check_duplicate_kalshi_linkage(
                db, scored["event_id"], market, ticker_date,
            )
            trace["duplicate_guard"] = {
                "passed": guard_ok,
            }

    trace["result"] = f"found {len(candidates)} candidates"
    return trace


@router.get("/prediction-markets/backfill-link-status")
async def backfill_link_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Status of the historical link backfill: how many left, how many done."""
    _check_admin_secret(secret, request=request)

    from sqlalchemy import func as _func, text as _text
    from app.models.models import FuturesMarket
    from app.utils.sport_keys import KALSHI_GAME_TICKER_PREFIXES

    ticker_conditions = [
        _func.lower(FuturesMarket.external_id).like(f"{p}%")
        for p in KALSHI_GAME_TICKER_PREFIXES
    ]

    result = await db.execute(
        select(
            _func.count().label("total_unlinked"),
            _func.count().filter(
                FuturesMarket.market_metadata.has_key("backfill_link_failed")
            ).label("marked_failed"),
        )
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.event_id.is_(None),
            or_(*ticker_conditions),
        )
    )
    row = result.one()
    return {
        "total_unlinked_game_markets": row.total_unlinked,
        "marked_no_match": row.marked_failed,
        "remaining_to_try": row.total_unlinked - row.marked_failed,
        "note": "remaining_to_try shrinks each run. When it hits 0, backfill is complete.",
    }


@router.post("/prediction-markets/backfill-link-run")
async def backfill_link_run(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    batch_size: int = Query(50, description="Markets to process"),
):
    """Trigger a single run of the historical link backfill."""
    _check_admin_secret(secret, request=request)

    from app.tasks.prediction_market_matching import _backfill_historical_links

    result = await _backfill_historical_links(batch_size=batch_size)
    return result


@router.post("/prediction-markets/force-link")
async def prediction_market_force_link(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    external_id: str = Query(..., description="Market external_id to link"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Force-link a single unlinked market by running the full matching pipeline."""
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone
    from app.models.models import FuturesMarket
    from app.utils.prediction_market_matching import (
        extract_matchup_with_ticker_fallback,
        extract_game_date_from_ticker,
    )
    from app.tasks.prediction_market_matching import (
        _find_matching_event,
        _check_duplicate_kalshi_linkage,
    )

    result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.external_id == external_id).limit(1)
    )
    market = result.scalars().first()
    if not market:
        raise HTTPException(status_code=404, detail=f"Market not found: {external_id}")
    if market.event_id is not None:
        return {"status": "already_linked", "event_id": market.event_id}

    matchup = extract_matchup_with_ticker_fallback(market.name, external_id=market.external_id)
    ticker_date = extract_game_date_from_ticker(market.external_id)
    now = datetime.now(timezone.utc)

    if not matchup:
        return {"status": "no_matchup"}

    matched = await _find_matching_event(db, matchup, market, now, game_date_override=ticker_date)
    if not matched:
        return {"status": "no_event_found"}

    guard_ok = await _check_duplicate_kalshi_linkage(db, matched["event_id"], market, ticker_date)
    if not guard_ok:
        return {"status": "duplicate_guard_blocked", "event_id": matched["event_id"]}

    market.event_id = matched["event_id"]
    await db.commit()

    return {
        "status": "linked",
        "event_id": matched["event_id"],
        "home_team": matched["home_team"],
        "away_team": matched["away_team"],
        "score": matched["score"],
    }


@router.get("/prediction-markets/event-debug")
async def prediction_market_event_debug(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    event_id: int = Query(..., description="Event ID to debug"),
    db: AsyncSession = Depends(get_db),
):
    """
    Debug prediction market matching for a specific event.

    Shows:
    - Event details (teams, status, commence_time)
    - Any linked FuturesMarkets (with source, name, external_id)
    - Outcomes for each linked market (name, probability, bid/ask)
    - Any win_prob_snapshots written for this event (by source)
    - Potential unlinked markets that SHOULD match (searches by team name)
    """
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone, timedelta
    from sqlalchemy import or_
    from app.models.models import (
        FuturesMarket, FuturesOutcome, WinProbSnapshot,
    )
    from app.utils.prediction_market_matching import (
        is_game_level_market, extract_matchup, extract_matchup_with_ticker_fallback,
        extract_teams_from_ticker, extract_game_date_from_ticker,
        match_teams_to_event, find_moneyline_outcome, _fuzzy_team_match,
    )

    # Load event
    event_result = await db.execute(select(Event).where(Event.id == event_id))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    result = {
        "event": {
            "id": event.id,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "status": event.status,
            "commence_time": event.commence_time.isoformat() if event.commence_time else None,
            "sport_id": event.sport_id,
        },
        "linked_markets": [],
        "win_prob_snapshots": {},
        "potential_unlinked_matches": [],
        "diagnosis": [],
    }

    # 1. Find linked markets
    linked_result = await db.execute(
        select(FuturesMarket)
        .where(
            FuturesMarket.event_id == event_id,
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
        )
    )
    linked_markets = linked_result.scalars().all()

    for market in linked_markets:
        # Get outcomes
        outcome_result = await db.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        outcomes = outcome_result.scalars().all()

        # Try matchup extraction
        matchup = extract_matchup_with_ticker_fallback(
            market.name, external_id=market.external_id,
        )

        # Try find_moneyline_outcome
        ml_result = None
        ml_diagnosis = "no matchup extracted"
        if matchup:
            ml_result = find_moneyline_outcome(
                outcomes, matchup,
                event.home_team_name, event.away_team_name,
            )
            if ml_result:
                ml_diagnosis = f"found: outcome='{ml_result[0].name}', yes_is_home={ml_result[1]}, prob={float(ml_result[0].current_probability)}"
            else:
                ml_diagnosis = f"find_moneyline_outcome returned None (matchup: {matchup.team_a} vs {matchup.team_b}, format={matchup.format_type})"

        market_info = {
            "id": market.id,
            "source": market.source,
            "name": market.name,
            "external_id": market.external_id,
            "status": market.status,
            "commence_time": market.commence_time.isoformat() if market.commence_time else None,
            "matchup": {
                "team_a": matchup.team_a if matchup else None,
                "team_b": matchup.team_b if matchup else None,
                "format_type": matchup.format_type if matchup else None,
            } if matchup else None,
            "moneyline_diagnosis": ml_diagnosis,
            "outcomes": [
                {
                    "id": o.id,
                    "name": o.name,
                    "external_id": o.external_id,
                    "probability": float(o.current_probability) if o.current_probability is not None else None,
                    "yes_bid": float(o.current_yes_bid) if o.current_yes_bid is not None else None,
                    "yes_ask": float(o.current_yes_ask) if o.current_yes_ask is not None else None,
                    "fuzzy_matches_home": _fuzzy_team_match(o.name or "", event.home_team_name),
                    "fuzzy_matches_away": _fuzzy_team_match(o.name or "", event.away_team_name),
                }
                for o in outcomes
            ],
        }
        result["linked_markets"].append(market_info)

    # 2. Check win_prob_snapshots for this event
    wp_result = await db.execute(
        select(WinProbSnapshot)
        .where(WinProbSnapshot.event_id == event_id)
        .order_by(WinProbSnapshot.captured_at.desc())
        .limit(50)
    )
    wp_snapshots = wp_result.scalars().all()

    sources_seen = {}
    for snap in wp_snapshots:
        if snap.source not in sources_seen:
            sources_seen[snap.source] = {
                "count": 0,
                "latest": None,
                "latest_home_prob": None,
            }
        sources_seen[snap.source]["count"] += 1
        if sources_seen[snap.source]["latest"] is None:
            sources_seen[snap.source]["latest"] = snap.captured_at.isoformat()
            sources_seen[snap.source]["latest_home_prob"] = float(snap.home_win_probability) if snap.home_win_probability else None
    result["win_prob_snapshots"] = sources_seen

    # 3. Search for potential unlinked markets that should match this event
    # Search by team names in market name or external_id
    home_short = event.home_team_name.split()[-1] if event.home_team_name else ""
    away_short = event.away_team_name.split()[-1] if event.away_team_name else ""

    search_conditions = []
    for team in [event.home_team_name, event.away_team_name, home_short, away_short]:
        if team and len(team) >= 3:
            pattern = f"%{team}%"
            search_conditions.append(FuturesMarket.name.ilike(pattern))
            search_conditions.append(FuturesMarket.external_id.ilike(pattern))

    # Also find Polymarket markets linked to a DIFFERENT event (mislinked)
    result["mislinked_polymarket"] = []
    if search_conditions:
        mislinked_result = await db.execute(
            select(
                FuturesMarket.id, FuturesMarket.name, FuturesMarket.event_id,
                FuturesMarket.group_id, FuturesMarket.group_type,
                FuturesMarket.llm_sport_category, FuturesMarket.status,
            )
            .where(
                FuturesMarket.source == "polymarket",
                FuturesMarket.event_id.isnot(None),
                FuturesMarket.event_id != event_id,
                or_(*search_conditions),
            )
            .limit(10)
        )
        for r in mislinked_result.all():
            result["mislinked_polymarket"].append({
                "id": r.id, "name": r.name, "event_id": r.event_id,
                "group_id": r.group_id, "group_type": r.group_type,
                "sport_cat": r.llm_sport_category, "status": r.status,
            })

    if search_conditions:
        potential_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.is_(None),
                or_(*search_conditions),
            )
            .limit(20)
        )
        potential_markets = potential_result.scalars().all()

        for market in potential_markets:
            ticker_date = extract_game_date_from_ticker(market.external_id)
            ticker_teams = extract_teams_from_ticker(market.external_id)
            is_game = is_game_level_market(
                market.name, market.category,
                external_id=market.external_id,
            )
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )

            result["potential_unlinked_matches"].append({
                "id": market.id,
                "source": market.source,
                "name": market.name,
                "external_id": market.external_id,
                "status": market.status,
                "commence_time": market.commence_time.isoformat() if market.commence_time else None,
                "is_game_level": is_game,
                "ticker_game_date": ticker_date.isoformat() if ticker_date else None,
                "ticker_teams": list(ticker_teams) if ticker_teams else None,
                "matchup_extracted": {
                    "team_a": matchup.team_a,
                    "team_b": matchup.team_b,
                    "format_type": matchup.format_type,
                } if matchup else None,
            })

    # 4. Search for MISLINKED markets — markets that match team names but
    #    are linked to a DIFFERENT event. This catches the common case where
    #    the time-window search matched a market to the wrong game.
    result["mislinked_markets"] = []
    if search_conditions:
        mislinked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.source.in_(["kalshi", "polymarket"]),
                FuturesMarket.event_id.isnot(None),
                FuturesMarket.event_id != event_id,
                or_(*search_conditions),
            )
            .limit(20)
        )
        mislinked_markets = mislinked_result.scalars().all()

        for market in mislinked_markets:
            # Check if this market's name actually matches BOTH teams
            matchup = extract_matchup_with_ticker_fallback(
                market.name, external_id=market.external_id,
            )
            both_match = False
            if matchup and matchup.team_b:
                a_matches = (
                    _fuzzy_team_match(matchup.team_a, event.home_team_name)
                    or _fuzzy_team_match(matchup.team_a, event.away_team_name)
                )
                b_matches = (
                    _fuzzy_team_match(matchup.team_b, event.home_team_name)
                    or _fuzzy_team_match(matchup.team_b, event.away_team_name)
                )
                both_match = a_matches and b_matches

            # Load the event it's linked to
            linked_event_result = await db.execute(
                select(Event).where(Event.id == market.event_id)
            )
            linked_event = linked_event_result.scalar_one_or_none()

            result["mislinked_markets"].append({
                "market_id": market.id,
                "source": market.source,
                "name": market.name,
                "external_id": market.external_id,
                "both_teams_match_this_event": both_match,
                "currently_linked_to_event": {
                    "id": linked_event.id if linked_event else None,
                    "teams": f"{linked_event.away_team_name} at {linked_event.home_team_name}" if linked_event else None,
                    "status": linked_event.status if linked_event else None,
                    "commence_time": linked_event.commence_time.isoformat() if linked_event and linked_event.commence_time else None,
                } if linked_event else None,
                "matchup": {
                    "team_a": matchup.team_a,
                    "team_b": matchup.team_b,
                } if matchup else None,
            })

    # 5. Generate diagnosis
    if not linked_markets and not result["potential_unlinked_matches"] and not result["mislinked_markets"]:
        result["diagnosis"].append("No linked, potential, or mislinked markets found. Kalshi/Polymarket may not have a market for this game, or it hasn't been polled yet.")
    elif not linked_markets and result["mislinked_markets"]:
        mislinked_both = [m for m in result["mislinked_markets"] if m["both_teams_match_this_event"]]
        if mislinked_both:
            result["diagnosis"].append(
                f"MISLINKED: {len(mislinked_both)} market(s) match BOTH teams but are linked to a different event. "
                f"These need to be unlinked and re-matched. Use POST /api/admin/prediction-markets/link to fix manually, "
                f"or POST /api/admin/prediction-markets/unlink?market_id=X to unlink."
            )
    elif not linked_markets and result["potential_unlinked_matches"]:
        result["diagnosis"].append(f"Found {len(result['potential_unlinked_matches'])} potential markets but none are linked. The matching task may not have run, or time window / team name matching is failing.")
    elif linked_markets and not sources_seen:
        result["diagnosis"].append("Markets are linked but no win_prob_snapshots exist. Check find_moneyline_outcome — outcome names may not match team names, or probability values may be NULL/0/1.")
    elif linked_markets and sources_seen:
        for src, info in sources_seen.items():
            result["diagnosis"].append(f"Source '{src}': {info['count']} snapshots, latest at {info['latest']} (home_prob={info['latest_home_prob']})")

    return result


@router.post("/prediction-markets/unlink")
async def unlink_prediction_market(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket.id to unlink"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Unlink a prediction market from its event. Sets event_id to NULL so the
    matching task can re-link it to the correct event on next run.
    """
    _check_admin_secret(secret, request=request)

    from app.models.models import FuturesMarket
    market_result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.id == market_id)
    )
    market = market_result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail=f"FuturesMarket {market_id} not found")

    old_event_id = market.event_id
    snapshots_deleted = 0

    # Delete orphaned win_prob_snapshots for the old event
    if old_event_id:
        from sqlalchemy import delete as sql_delete
        from app.models.models import WinProbSnapshot
        del_result = await db.execute(
            sql_delete(WinProbSnapshot).where(
                WinProbSnapshot.event_id == old_event_id,
                WinProbSnapshot.source == market.source,
            )
        )
        snapshots_deleted = del_result.rowcount

    market.event_id = None
    await db.commit()

    return {
        "status": "unlinked",
        "market_id": market_id,
        "market_name": market.name,
        "old_event_id": old_event_id,
        "snapshots_deleted": snapshots_deleted,
    }


@router.post("/prediction-markets/fix-inversions")
async def fix_inverted_prediction_market_snapshots(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    event_id: int = Query(..., description="Event.id to fix inversions for"),
    source: Optional[str] = Query(None, description="Source to fix (kalshi/polymarket). If omitted, fixes both."),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Fix inverted win_prob_snapshots for a specific event.

    Compares prediction market snapshots against the sportsbook consensus
    (from odds_snapshots) and flips any that appear inverted.
    """
    _check_admin_secret(secret, request=request)

    from app.models.models import Event, WinProbSnapshot, OddsSnapshot
    import statistics

    # Load event for consensus
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Get sportsbook consensus: latest odds snapshot or opening odds
    consensus = None
    latest_snap = await db.execute(
        select(OddsSnapshot.home_win_probability)
        .where(
            OddsSnapshot.event_id == event_id,
            OddsSnapshot.home_win_probability.isnot(None),
        )
        .order_by(OddsSnapshot.captured_at.desc())
        .limit(1)
    )
    snap_prob = latest_snap.scalar_one_or_none()
    if snap_prob is not None:
        consensus = float(snap_prob)
    elif event.opening_home_probability is not None:
        consensus = float(event.opening_home_probability)

    if consensus is None:
        raise HTTPException(
            status_code=400,
            detail="No sportsbook consensus available for this event",
        )

    # Query prediction market snapshots
    sources_filter = [source] if source else ["kalshi", "polymarket"]
    result = await db.execute(
        select(WinProbSnapshot)
        .where(
            WinProbSnapshot.event_id == event_id,
            WinProbSnapshot.source.in_(sources_filter),
        )
        .order_by(WinProbSnapshot.captured_at)
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return {
            "status": "no_snapshots",
            "event_id": event_id,
            "message": "No prediction market snapshots found for this event",
        }

    # Check if snapshots are inverted: compare median snapshot against consensus
    probs = [float(s.home_win_probability) for s in snapshots if s.home_win_probability is not None]
    if not probs:
        return {"status": "no_valid_probs", "event_id": event_id}

    median_prob = statistics.median(probs)
    raw_diff = abs(median_prob - consensus)
    flipped_diff = abs((1.0 - median_prob) - consensus)

    if raw_diff <= 0.25 or flipped_diff >= raw_diff:
        return {
            "status": "not_inverted",
            "event_id": event_id,
            "consensus": round(consensus, 4),
            "median_pm_prob": round(median_prob, 4),
            "raw_diff": round(raw_diff, 4),
            "flipped_diff": round(flipped_diff, 4),
            "snapshot_count": len(snapshots),
            "message": "Snapshots appear correct (not inverted)",
        }

    # Flip all snapshots
    flipped_count = 0
    for snap in snapshots:
        if snap.home_win_probability is not None:
            old_home = float(snap.home_win_probability)
            snap.home_win_probability = round(1.0 - old_home, 4)
            snap.away_win_probability = round(old_home, 4)
            flipped_count += 1

    await db.commit()

    return {
        "status": "fixed",
        "event_id": event_id,
        "sources": sources_filter,
        "consensus": round(consensus, 4),
        "median_before_flip": round(median_prob, 4),
        "median_after_flip": round(1.0 - median_prob, 4),
        "raw_diff": round(raw_diff, 4),
        "flipped_diff": round(flipped_diff, 4),
        "snapshots_flipped": flipped_count,
        "total_snapshots": len(snapshots),
    }


@router.post("/prediction-markets/link")
async def manual_link_prediction_market(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    market_id: int = Query(..., description="FuturesMarket.id to link"),
    event_id: int = Query(..., description="Event.id to link to"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Manually link a prediction market to an event.

    Sets FuturesMarket.event_id and immediately writes a win_prob_snapshot.
    Use when auto-matching fails (e.g., name patterns don't match, or the game
    is already completed and the market is resolved).
    """
    _check_admin_secret(secret, request=request)

    from datetime import datetime, timezone
    from app.models.models import FuturesMarket, FuturesOutcome, WinProbSnapshot
    from app.utils.prediction_market_matching import (
        extract_matchup, match_teams_to_event, find_moneyline_outcome,
    )
    from app.tasks.snapshots import _create_or_update_win_prob_snapshot

    # Load market
    market_result = await db.execute(
        select(FuturesMarket).where(FuturesMarket.id == market_id)
    )
    market = market_result.scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail=f"FuturesMarket {market_id} not found")

    # Load event
    event_result = await db.execute(
        select(Event).where(Event.id == event_id)
    )
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    # Link the market
    market.event_id = event_id

    # Try to write a snapshot immediately
    snapshot_result = None
    matchup = extract_matchup(market.name, external_id=market.external_id)
    if matchup:
        # Load outcomes
        outcome_result = await db.execute(
            select(FuturesOutcome)
            .where(FuturesOutcome.market_id == market.id)
            .order_by(FuturesOutcome.rank)
        )
        outcomes = outcome_result.scalars().all()

        ml_result = find_moneyline_outcome(
            outcomes, matchup,
            event.home_team_name, event.away_team_name,
        )
        if ml_result:
            outcome, yes_is_home = ml_result
            yes_prob = float(outcome.current_probability)
            home_prob = yes_prob if yes_is_home else (1.0 - yes_prob)
            away_prob = 1.0 - home_prob

            snapshot, is_new = await _create_or_update_win_prob_snapshot(
                db,
                event_id=event_id,
                source=market.source,
                home_win_probability=round(home_prob, 4),
                away_win_probability=round(away_prob, 4),
                game_state={
                    "market_name": market.name,
                    "market_id": market.id,
                    "outcome_name": outcome.name,
                    "yes_probability": yes_prob,
                    "manual_link": True,
                },
            )
            if is_new:
                db.add(snapshot)
            snapshot_result = {
                "home_prob": round(home_prob, 4),
                "away_prob": round(away_prob, 4),
                "source": market.source,
                "is_new": is_new,
            }

    await db.commit()

    return {
        "status": "linked",
        "market_id": market_id,
        "event_id": event_id,
        "market_name": market.name,
        "market_source": market.source,
        "event_teams": f"{event.home_team_name} vs {event.away_team_name}",
        "snapshot": snapshot_result,
    }


# =============================================================================
# MLB Win Probability Admin Endpoints
# =============================================================================


@router.post("/audit/canonical-keys")
async def trigger_audit_canonical_keys(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(50, description="Number of groups/markets to sample"),
):
    """Trigger canonical key dedup audit (runs as background Celery task)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import audit_canonical_keys
    task = audit_canonical_keys.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Canonical key audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.post("/audit/prediction-market-links")
async def trigger_audit_prediction_market_links(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(50, description="Number of links/markets to sample"),
):
    """Trigger prediction market → event link audit (background task)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import audit_prediction_market_links
    task = audit_prediction_market_links.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Prediction market link audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.post("/audit/related-futures")
async def trigger_audit_related_futures(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(30, description="Number of events/outcomes to sample"),
):
    """Trigger related futures coverage audit (background task)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import audit_related_futures
    task = audit_related_futures.delay(limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Related futures audit queued. Use /api/admin/audit/task/{task_id} to check status.",
    }


@router.post("/entity-registry/seed")
async def trigger_entity_registry_seed(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    persons_only: bool = Query(
        True,
        description="Only run the person fold-in (skip teams/competitions already seeded)",
    ),
):
    """#171/#1020 — Trigger the A1 entity-registry seed as a background task.

    Removes the ``heroku run`` requirement (EPERM from the sandboxed crank).
    Idempotent: already-folded rows are skipped, so a re-trigger resumes. Counts
    land in the task result (poll ``/api/admin/audit/task/{task_id}``) AND in a
    ``seed_diag:persons`` marker row readable via ``/api/admin/db-query``.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import seed_entity_registry
    task = seed_entity_registry.delay(persons_only)
    return {
        "status": "queued",
        "task_id": task.id,
        "persons_only": persons_only,
        "message": (
            "Entity-registry seed queued. Poll /api/admin/audit/task/{task_id}; "
            "counts also land in seed_diag:persons (db-query)."
        ),
    }


@router.post("/entity-registry/canonicalize")
async def trigger_entity_registry_canonicalize(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    dry_run: bool = Query(
        False,
        description="Count what WOULD merge without writing (census-only)",
    ),
):
    """#175 Item 1 — collapse same-family duplicate entities as a background task.

    Merges edition-multiplied person/team dups (e.g. "Alexandra Eala" ×15 across
    tennis tournament sport_keys) into one canonical entity, aliases repointed.
    Census-gated (cross-family homonyms left apart), additive-first, idempotent.
    Counts land in the task result AND in a ``seed_diag:canonicalize`` marker row.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import canonicalize_entities_task
    task = canonicalize_entities_task.delay(dry_run)
    return {
        "status": "queued",
        "task_id": task.id,
        "dry_run": dry_run,
        "message": (
            "Entity canonicalization queued. Poll /api/admin/audit/task/{task_id}; "
            "counts also land in seed_diag:canonicalize (db-query)."
        ),
    }


@router.post("/events/merge-degenerate-combat")
async def trigger_merge_degenerate_combat_events(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    dry_run: bool = Query(True, description="Count pairs without writing (verify-first)"),
    limit: int = Query(500, description="Max degenerate events to scan per run"),
):
    """#175 Item 3 — merge degenerate home==away fight events into their real event.

    The "15132461 class": pre-Item-2, a fight-winner market that parsed to a
    single competitor auto-created a degenerate event and orphaned its Kalshi
    markets there. This repoints those markets/snapshots onto the real
    odds-registry event and deletes the degenerate. Verify-first (``dry_run=True``
    default). Counts land in the task result.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import merge_degenerate_combat_events_task
    task = merge_degenerate_combat_events_task.delay(dry_run, limit)
    return {
        "status": "queued",
        "task_id": task.id,
        "dry_run": dry_run,
        "limit": limit,
        "message": "Degenerate combat-event merge queued. Poll /api/admin/audit/task/{task_id}.",
    }


@router.post("/prediction-markets/backfill-combat-wps")
async def trigger_backfill_combat_wps(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    dry_run: bool = Query(True, description="Count blends without writing (verify-first)"),
    limit: int = Query(500, description="Max settled combat events to scan per run"),
):
    """#178 follow-up — oldest-first combat WPS backfill for the settled-fight tail.

    The newest-first `/prediction-markets/backfill-wps` endpoint cannot reach the
    ~178 older settled combat fights whose Kalshi line was linked but never folded
    into the event blend. This queues the oldest-first, combat-filtered task
    (`KXUFCFIGHT*`/`KXBOXING*` on completed/closed/resolved events missing the
    kalshi blend). Verify-first (``dry_run=True`` default); counts land in the task
    result. Also runs daily on the beat.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import backfill_combat_wps
    task = backfill_combat_wps.delay(limit, dry_run)
    return {
        "status": "queued",
        "task_id": task.id,
        "dry_run": dry_run,
        "limit": limit,
        "message": "Combat WPS backfill queued. Poll /api/admin/audit/task/{task_id}.",
    }


@router.post("/polymarket/backfill-matchups")
async def trigger_polymarket_backfill_matchups(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    all_groups: bool = Query(
        False,
        description="Also backfill unlinked poly game groups (default: linked only)",
    ),
):
    """#171/#1021 — Trigger the A2 poly matchup_title backfill as a background task.

    Recovers the "A vs. B" matchup onto Polymarket game sub-markets so the
    resolution engine reads both participants (closes the poly ``market_event``
    shadow gap). Idempotent: only writes where ``matchup_title`` is missing. Counts
    land in the task result AND in a ``seed_diag:poly_matchups`` marker row.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import backfill_polymarket_matchups
    task = backfill_polymarket_matchups.delay(all_groups)
    return {
        "status": "queued",
        "task_id": task.id,
        "all_groups": all_groups,
        "message": (
            "Poly matchup backfill queued. Poll /api/admin/audit/task/{task_id}; "
            "counts also land in seed_diag:poly_matchups (db-query)."
        ),
    }


@router.get("/audit/task/{task_id}")
async def get_audit_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of an audit task."""
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app as _celery

    result = _celery.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        try:
            response["result"] = result.result
        except Exception as e:
            response["error"] = str(e)

    return response


@router.get("/audit/canonical-keys")
async def get_audit_canonical_keys(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest canonical key audit results."""
    _check_admin_secret(secret, request=request)

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_canonical")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No canonical key audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/prediction-market-links")
async def get_audit_prediction_market_links(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest prediction market link audit results."""
    _check_admin_secret(secret, request=request)

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_pred_market")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No prediction market link audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/related-futures")
async def get_audit_related_futures(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Get latest related futures audit results."""
    _check_admin_secret(secret, request=request)

    from app.models import LineMovementAnalysis

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(LineMovementAnalysis.analysis_type == "audit_related_fut")
        .order_by(LineMovementAnalysis.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"status": "no_data", "message": "No related futures audit has been run yet."}

    return {
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "summary": row.explanation,
        **row.movement_data,
    }


@router.get("/audit/patterns")
async def get_audit_patterns(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate pattern_category across recent audit findings.

    Shows recurring issues ranked by frequency, with suggested deterministic
    rules to prevent them. When a pattern appears 3+ times, it's a strong
    signal to add a deterministic rule.
    """
    _check_admin_secret(secret, request=request)

    from app.models import LineMovementAnalysis

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(LineMovementAnalysis)
        .where(
            LineMovementAnalysis.analysis_type.in_([
                "audit_canonical", "audit_pred_market", "audit_related_fut",
            ]),
            LineMovementAnalysis.created_at >= cutoff,
        )
        .order_by(LineMovementAnalysis.created_at.desc())
    )
    audit_rows = result.scalars().all()

    # Aggregate patterns
    pattern_counts: dict[str, dict] = {}
    for row in audit_rows:
        data = row.movement_data or {}
        for finding in data.get("findings", []):
            cat = finding.get("pattern_category")
            if not cat or cat == "null":
                continue
            if cat not in pattern_counts:
                pattern_counts[cat] = {
                    "category": cat,
                    "count": 0,
                    "latest_suggestion": None,
                    "audit_types": set(),
                    "finding_types": set(),
                }
            pattern_counts[cat]["count"] += 1
            rule = finding.get("suggested_rule")
            if rule and rule != "null":
                pattern_counts[cat]["latest_suggestion"] = rule
            pattern_counts[cat]["audit_types"].add(data.get("audit_type", ""))
            pattern_counts[cat]["finding_types"].add(finding.get("type", ""))

    # Convert sets to lists for JSON and sort by count
    patterns = sorted(pattern_counts.values(), key=lambda p: p["count"], reverse=True)
    for p in patterns:
        p["audit_types"] = sorted(p["audit_types"])
        p["finding_types"] = sorted(p["finding_types"])

    return {
        "days": days,
        "total_audit_runs": len(audit_rows),
        "unique_patterns": len(patterns),
        "patterns": patterns[:50],
    }


@router.get("/matching/metrics")
async def get_matching_metrics(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Get current matching coverage metrics and history for trending."""
    _check_admin_secret(secret, request=request)

    from app.tasks.matching_audit import _compute_matching_metrics_impl, get_matching_metrics_history
    from app.tasks.base import run_async as _run_async

    metrics = await _compute_matching_metrics_impl()
    history = get_matching_metrics_history(days=90)

    return {
        "current": metrics,
        "history": history,
    }


@router.post("/matching/metrics/compute")
async def trigger_matching_metrics(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Trigger matching metrics computation as a Celery task."""
    _check_admin_secret(secret, request=request)

    from app.tasks import compute_matching_metrics
    result = compute_matching_metrics.delay()
    return {"status": "dispatched", "task_id": result.id}


# =============================================================================
# StatPal Integration
# =============================================================================


@router.get("/matching-review/{league_slug}")
async def get_matching_review(
    request: Request,
    league_slug: str,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Get current matching issues and overrides for a league grid.

    Surfaces:
    - Cross-source divergences (>15% between sources for same team+column)
    - Existing overrides (team aliases, exclusions, etc.)
    """
    _check_admin_secret(secret, request=request)

    from app.config.league_configs import get_league_config
    from app.routes.playoffs import (
        _normalize_team_name,
        _merge_probabilities,
    )
    from collections import defaultdict
    import statistics

    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # 1. Fetch existing overrides
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug
    )
    result = await db.execute(stmt)
    overrides = result.scalars().all()

    override_list = []
    for o in overrides:
        override_list.append({
            "id": o.id,
            "type": o.override_type,
            "source_name": o.source_name,
            "target_name": o.target_name,
            "decision": o.decision,
            "context": o.context,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })

    # 2. Fetch current grid data to find issues
    # Get all matching markets
    conditions = []
    if config.league_name_patterns:
        import re
        for pat in config.league_name_patterns:
            conditions.append(FuturesMarket.name.op("~*")(pat))

    sport_cat = config.sport_category
    if conditions:
        market_filter = or_(
            FuturesMarket.llm_sport_category == sport_cat,
            *conditions,
        )
    else:
        market_filter = FuturesMarket.llm_sport_category == sport_cat

    stmt = (
        select(FuturesMarket)
        .where(market_filter, FuturesMarket.status != "resolved")
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    markets = result.scalars().all()

    # Build grid_raw to detect issues — apply same filters as the grid builder
    grid_raw = defaultdict(lambda: defaultdict(list))
    from app.routes.playoffs import (
        _match_market_to_column,
        _NON_PLAYOFF_MARKET_RE,
    )

    # Apply league_name_patterns filter in Python (same as grid builder step 1)
    league_patterns = config.league_name_patterns or []
    filtered_markets = []
    for market in markets:
        if league_patterns:
            name_lower = (market.name or "").lower()
            if not any(re.search(pat, name_lower) for pat in league_patterns):
                continue
        filtered_markets.append(market)

    for market in filtered_markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue
        for outcome in (market.outcomes or []):
            prob = outcome.current_probability
            if prob is None:
                # Fallback: compute from bid/ask when current_probability
                # wasn't written (e.g. during API format migrations).
                if (outcome.current_yes_bid is not None
                        and outcome.current_yes_ask is not None
                        and float(outcome.current_yes_ask) > 0):
                    prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
                else:
                    continue
            if prob <= 0 or prob >= 1.0:
                continue
            oname = outcome.name or ""
            # Skip non-team outcomes (same filters as grid builder)
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            # Skip prediction market 0.5 noise, but allow outcomes
            # with real trading activity (bid > 0).
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue
            norm = _normalize_team_name(oname)
            grid_raw[norm][col_key].append({
                "source": market.source,
                "probability": float(prob),
                "market_name": market.name,
                "market_id": market.id,
                "outcome_name": oname,
            })

    # Dedup within same source per team+column (keep lowest prob — same as grid builder)
    for norm_name in grid_raw:
        for col_key in grid_raw[norm_name]:
            entries = grid_raw[norm_name][col_key]
            if len(entries) <= 1:
                continue
            by_source: dict[str, list] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            deduped = []
            for source, source_entries in by_source.items():
                best = min(source_entries, key=lambda e: e["probability"])
                deduped.append(best)
            grid_raw[norm_name][col_key] = deduped

    # 3. Find cross-source divergences
    divergences = []
    col_keys = [c.key for c in config.columns]
    for norm_name, col_map in grid_raw.items():
        for col_key in col_keys:
            entries = col_map.get(col_key, [])
            if len(entries) < 2:
                continue
            # Group by source
            by_source = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            if len(by_source) < 2:
                continue
            source_probs = {s: es[0]["probability"] for s, es in by_source.items()}
            vals = list(source_probs.values())
            spread = max(vals) - min(vals)
            if spread > 0.15:
                # Include market details so the admin can see exactly which markets diverge
                source_details = {}
                for s, es in by_source.items():
                    source_details[s] = {
                        "probability": round(es[0]["probability"], 4),
                        "market_name": es[0]["market_name"],
                        "market_id": es[0].get("market_id"),
                    }
                divergences.append({
                    "team": norm_name,
                    "column": col_key,
                    "spread": round(spread, 3),
                    "sources": {s: round(source_probs[s], 4) for s in source_probs},
                    "source_details": source_details,
                    "status": "needs_review",
                })

    # Sort by spread descending
    divergences.sort(key=lambda d: d["spread"], reverse=True)

    # 4. Find teams with sparse data (have championship but missing most rounds)
    sparse_teams = []
    for norm_name, col_map in grid_raw.items():
        filled = sum(1 for ck in col_keys if col_map.get(ck))
        if filled <= 2 and len(col_keys) >= 4:
            champ_prob = 0
            champ_entries = col_map.get(col_keys[-1], [])
            if champ_entries:
                champ_prob = statistics.median([e["probability"] for e in champ_entries])
            sparse_teams.append({
                "team": norm_name,
                "filled_columns": filled,
                "total_columns": len(col_keys),
                "championship_prob": round(champ_prob, 4),
                "status": "needs_review",
            })
    sparse_teams.sort(key=lambda t: t["championship_prob"])

    return {
        "league": league_slug,
        "total_teams": len(grid_raw),
        "total_columns": len(col_keys),
        "columns": col_keys,
        "overrides": override_list,
        "divergences": divergences[:30],  # Top 30
        "divergence_count": len(divergences),
        "sparse_teams": sparse_teams[:20],  # Top 20
        "sparse_count": len(sparse_teams),
    }


@router.post("/matching-review/{league_slug}/override")
async def add_matching_override(
    league_slug: str,
    override_type: str = Query(..., description="team_alias, team_exclude, team_include, market_column, source_trust, dismiss"),
    source_name: str = Query(..., description="The name/id to override"),
    target_name: Optional[str] = Query(default=None, description="Target for aliases/columns"),
    decision: str = Query(default="approved", description="approved or rejected"),
    reason: Optional[str] = Query(default=None, description="Why this decision was made"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db_rw),
):
    """Add or update a matching override. Accepts JSON body or query params.

    Override types:
    - team_alias: source_name is an alias for target_name (merge them)
    - team_exclude: source_name should be excluded from the grid
    - team_include: source_name must appear in the grid
    - market_column: source_name is a market name/id, target_name is column key
    - source_trust: source_name is "source:column", marks trust level
    - dismiss: mark a divergence as reviewed/acceptable (no grid effect)
    """
    _check_admin_secret(secret, request=request)
    from app.config.league_configs import get_league_config
    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    valid_types = {"team_alias", "team_exclude", "team_include", "market_column", "source_trust", "dismiss"}
    if override_type not in valid_types:
        raise HTTPException(400, f"Invalid override_type. Must be one of: {valid_types}")

    context: dict = {}
    if reason:
        context["reason"] = reason
    context["decided_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug,
        MatchingOverride.override_type == override_type,
        MatchingOverride.source_name == source_name,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.target_name = target_name
        existing.decision = decision
        existing.context = context
    else:
        override = MatchingOverride(
            league_slug=league_slug,
            override_type=override_type,
            source_name=source_name,
            target_name=target_name,
            decision=decision,
            context=context,
        )
        db.add(override)

    await db.commit()

    return {
        "status": "saved",
        "league": league_slug,
        "type": override_type,
        "source_name": source_name,
        "target_name": target_name,
        "decision": decision,
    }


@router.delete("/matching-review/{league_slug}/override/{override_id}")
async def delete_matching_override(
    request: Request,
    league_slug: str,
    override_id: int,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db_rw),
):
    """Delete a matching override."""
    _check_admin_secret(secret, request=request)
    stmt = select(MatchingOverride).where(
        MatchingOverride.id == override_id,
        MatchingOverride.league_slug == league_slug,
    )
    result = await db.execute(stmt)
    override = result.scalar_one_or_none()
    if not override:
        raise HTTPException(404, "Override not found")

    await db.delete(override)
    await db.commit()
    return {"status": "deleted", "id": override_id}


# ── Eval Decisions (persisted, cross-device) ─────────────────────────────────


@router.get("/eval/decisions")
async def get_eval_decisions(
    request: Request,
    category: Optional[str] = Query(default=None, description="Filter by category: grid, futures"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Get all eval decisions. Used by frontend to check 'already seen' across devices."""
    _check_admin_secret(secret, request=request)
    stmt = select(MatchingOverride).where(
        MatchingOverride.override_type.in_(["eval_grid", "eval_futures"])
    )
    if category == "grid":
        stmt = stmt.where(MatchingOverride.override_type == "eval_grid")
    elif category == "futures":
        stmt = stmt.where(MatchingOverride.override_type == "eval_futures")
    stmt = stmt.order_by(MatchingOverride.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "decisions": [
            {
                "id": r.id,
                "source_name": r.source_name,
                "decision": r.decision,
                "context": r.context,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "count": len(rows),
    }


@router.post("/eval/decision")
async def save_eval_decision(
    request: Request,
    source_name: str = Query(..., description="Unique key: 'league:team:column' for grid, 'futures:market_id' for futures"),
    decision: str = Query(..., description="correct, wrong, interesting, skip, never"),
    category: str = Query(default="grid", description="grid or futures"),
    reason: Optional[str] = Query(default=None, description="Context about the decision"),
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db_rw),
):
    """Save an eval decision to the database. Replaces localStorage persistence."""
    _check_admin_secret(secret, request=request)
    valid_decisions = {"correct", "wrong", "interesting", "skip", "never"}
    if decision not in valid_decisions:
        raise HTTPException(400, f"Invalid decision. Must be one of: {valid_decisions}")

    override_type = "eval_grid" if category == "grid" else "eval_futures"

    context: dict = {}
    if reason:
        context["reason"] = reason
    context["decided_at"] = datetime.now(timezone.utc).isoformat()

    # Upsert by source_name + override_type
    stmt = select(MatchingOverride).where(
        MatchingOverride.override_type == override_type,
        MatchingOverride.source_name == source_name,
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        existing.decision = decision
        existing.context = context
    else:
        override = MatchingOverride(
            league_slug="_eval",
            override_type=override_type,
            source_name=source_name,
            decision=decision,
            context=context,
        )
        db.add(override)

    await db.commit()
    return {"status": "saved", "source_name": source_name, "decision": decision}


@router.get("/matching-review/{league_slug}/playoffstatus")
async def get_playoffstatus_comparison(
    request: Request,
    league_slug: str,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Compare our grid against playoffstatus.com reference data.

    Fetches the current team list and probabilities from playoffstatus.com
    and compares against our grid data. Returns:
    - Teams in playoffstatus but missing from our grid
    - Teams in our grid but not on playoffstatus
    - Probability divergences between our data and theirs
    """
    _check_admin_secret(secret, request=request)

    # For now, return the stored reference data if available
    # (populated by the scraper task)
    from app.config.league_configs import get_league_config
    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # Check for stored reference overrides of type "team_include"
    stmt = select(MatchingOverride).where(
        MatchingOverride.league_slug == league_slug,
        MatchingOverride.override_type.in_(["team_include", "team_exclude"]),
    )
    result = await db.execute(stmt)
    overrides = result.scalars().all()

    includes = [o.source_name for o in overrides if o.override_type == "team_include" and o.decision == "approved"]
    excludes = [o.source_name for o in overrides if o.override_type == "team_exclude" and o.decision == "approved"]

    return {
        "league": league_slug,
        "reference_includes": includes,
        "reference_excludes": excludes,
        "note": "Use POST /admin/matching-review/{league}/scrape-playoffstatus to fetch fresh reference data",
    }


@router.post("/matching-review/{league_slug}/scrape-playoffstatus")
async def scrape_playoffstatus(
    request: Request,
    league_slug: str,
    secret: str = Query(default=""),
    db: AsyncSession = Depends(get_db_rw),
):
    """Scrape playoffstatus.com for reference team list and probabilities."""
    _check_admin_secret(secret, request=request)
    import httpx
    import re
    from app.config.league_configs import get_league_config

    config = get_league_config(league_slug)
    if not config:
        raise HTTPException(404, f"Unknown league: {league_slug}")

    # Map league slugs to playoffstatus URLs
    url_map = {
        "nba": [
            "https://www.playoffstatus.com/nba/easternstandings.html",
            "https://www.playoffstatus.com/nba/westernstandings.html",
        ],
        "nhl": [
            "https://www.playoffstatus.com/nhl/easternstandings.html",
            "https://www.playoffstatus.com/nhl/westernstandings.html",
        ],
        "ncaa-basketball": [
            "https://www.playoffstatus.com/ncaabasketball/ncaabasketball.html",
        ],
    }

    urls = url_map.get(league_slug, [])
    if not urls:
        return {"status": "unsupported", "message": f"No playoffstatus URL mapping for {league_slug}"}

    teams_found = []
    errors = []

    async with httpx.AsyncClient(timeout=30) as client:
        for url in urls:
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                html = resp.text

                # Parse team names from HTML tables
                # Playoffstatus uses table rows with team names in specific patterns
                # Extract team names from table cells with class patterns
                # The HTML structure varies by sport but team names appear in
                # <td> tags often with links

                # Generic team name extraction from HTML
                # Look for patterns like team names in table rows
                team_pattern = re.findall(
                    r'<a[^>]*>([A-Z][a-zA-Z\s&\'\.\-]+(?:ers|ics|ets|ons|ies|ors|ins|awks|eat|urs|ols|ers|lts|nes|ings|oos|ies|gers|ks|ns|rs|ts|es|gs|ds|cs|bs|ps|ves|zes))</a>',
                    html,
                )
                # Also try simpler team name patterns
                if not team_pattern:
                    team_pattern = re.findall(
                        r'>(\w[\w\s\'\.]+(?:76ers|Heat|Jazz|Suns|Magic|Nets|Bucks|Bulls|Hawks|Knicks|Spurs|Kings|Celtics|Lakers|Pistons|Rockets|Thunder|Raptors|Hornets|Pacers|Wizards|Nuggets|Grizzlies|Pelicans|Warriors|Clippers|Cavaliers|Mavericks|Timberwolves))<',
                        html,
                    )

                # Extract probabilities if present
                prob_pattern = re.findall(r'(\d+(?:\.\d+)?)\s*%', html)

                for team_name in team_pattern:
                    team_name = team_name.strip()
                    if len(team_name) > 3 and team_name not in teams_found:
                        teams_found.append(team_name)

            except Exception as e:
                errors.append({"url": url, "error": str(e)})

    # Store as team_include overrides
    created = 0
    for team_name in teams_found:
        norm = team_name.lower().strip()
        stmt = select(MatchingOverride).where(
            MatchingOverride.league_slug == league_slug,
            MatchingOverride.override_type == "team_include",
            MatchingOverride.source_name == norm,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        if not existing:
            override = MatchingOverride(
                league_slug=league_slug,
                override_type="team_include",
                source_name=norm,
                target_name=team_name,
                decision="approved",
                context={"source": "playoffstatus.com", "scraped_at": datetime.now(timezone.utc).isoformat()},
            )
            db.add(override)
            created += 1

    if created:
        await db.commit()

    return {
        "status": "scraped",
        "league": league_slug,
        "teams_found": len(teams_found),
        "teams_created": created,
        "teams": teams_found,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Consolidated Operations Dashboard
# ---------------------------------------------------------------------------


@router.get("/sawtooth-audit")
async def sawtooth_audit(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as a big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag as affected"),
    limit: int = Query(10, description="Number of worst offenders to return"),
    db: AsyncSession = Depends(get_db),
):
    """Detect Kalshi dual-market sawtooth oscillation in win_prob_snapshots.

    The bug: Phase 2 and the live poller picked different dual markets for
    the same event, causing home_win_probability to oscillate between two
    values (e.g., 60% and 58%) on consecutive snapshots.

    Returns affected event counts, snapshot totals, worst offenders, and a
    post-fix stability check on snapshots from the last 2 hours.
    """
    _check_admin_secret(secret, request=request)

    # ── Historical sawtooth detection via window functions ──
    historical_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            j.event_id,
            e.home_team_name,
            e.away_team_name,
            e.status,
            j.total_snaps,
            j.big_jumps,
            ROUND((j.big_jumps::numeric / NULLIF(j.total_snaps, 0)), 4) AS jump_rate
        FROM jumps j
        JOIN events e ON e.id = j.event_id
        WHERE j.total_snaps >= 4
          AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        ORDER BY j.big_jumps DESC, jump_rate DESC
        LIMIT :lim
    """)

    worst_result = await db.execute(
        historical_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold, "lim": limit},
    )
    worst_offenders = worst_result.fetchall()

    # ── Aggregate counts (affected events + total affected snapshots) ──
    counts_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            COUNT(*) AS affected_events,
            COALESCE(SUM(total_snaps), 0) AS affected_snapshots,
            COALESCE(SUM(big_jumps), 0) AS total_big_jumps
        FROM jumps
        WHERE jumps.total_snaps >= 4
          AND jumps.big_jumps::float / NULLIF(jumps.total_snaps, 0) > :rate_threshold
    """)

    counts_result = await db.execute(
        counts_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
    )
    counts = counts_result.fetchone()

    # ── Post-fix check: last 2 hours of Kalshi snapshots ──
    postfix_sql = text("""
        WITH recent AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
              AND captured_at > NOW() - INTERVAL '2 hours'
        ),
        recent_jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM recent
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            COUNT(*) AS events_checked,
            COALESCE(SUM(total_snaps), 0) AS snapshots_checked,
            COUNT(*) FILTER (
                WHERE total_snaps >= 2
                  AND big_jumps::float / NULLIF(total_snaps, 0) > :rate_threshold
            ) AS still_affected
        FROM recent_jumps
    """)

    postfix_result = await db.execute(
        postfix_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
    )
    postfix = postfix_result.fetchone()

    return {
        "historical": {
            "affected_events": int(counts.affected_events) if counts else 0,
            "affected_snapshots": int(counts.affected_snapshots) if counts else 0,
            "total_big_jumps": int(counts.total_big_jumps) if counts else 0,
            "thresholds": {
                "jump_threshold": jump_threshold,
                "rate_threshold": rate_threshold,
                "min_snapshots": 4,
            },
            "worst_offenders": [
                {
                    "event_id": row.event_id,
                    "home_team": row.home_team_name,
                    "away_team": row.away_team_name,
                    "status": row.status,
                    "snapshot_count": int(row.total_snaps),
                    "jump_count": int(row.big_jumps),
                    "jump_rate": float(row.jump_rate),
                }
                for row in worst_offenders
            ],
        },
        "post_fix_check": {
            "window": "last 2 hours",
            "events_checked": int(postfix.events_checked) if postfix else 0,
            "snapshots_checked": int(postfix.snapshots_checked) if postfix else 0,
            "still_affected": int(postfix.still_affected) if postfix else 0,
            "fix_working": (postfix.still_affected == 0) if postfix else True,
        },
    }


@router.get("/sawtooth-diagnosis")
async def sawtooth_diagnosis(
    request: Request,
    secret: str = Query(None, description="Admin secret"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as a big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag"),
    limit: int = Query(52, description="Max events to diagnose"),
    db: AsyncSession = Depends(get_db),
):
    """Diagnose root cause of sawtooth oscillation for each affected event.

    For each event with sawtooth Kalshi snapshots, returns:
    - Currently linked Kalshi futures_markets (event_id FK)
    - Distinct market_ids referenced in win_prob_snapshot game_state
    - Classification: multi_game (Type A), dual_market (Type B), or other (Type C)
    """
    _check_admin_secret(secret, request=request)

    # Step 1: Find affected events (same query as sawtooth-audit)
    affected_sql = text("""
        WITH consecutive AS (
            SELECT
                event_id,
                home_win_probability,
                LAG(home_win_probability) OVER (
                    PARTITION BY event_id ORDER BY captured_at
                ) AS prev_prob
            FROM win_prob_snapshots
            WHERE source = 'kalshi'
        ),
        jumps AS (
            SELECT
                event_id,
                COUNT(*) AS total_snaps,
                COUNT(*) FILTER (
                    WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                ) AS big_jumps
            FROM consecutive
            WHERE prev_prob IS NOT NULL
            GROUP BY event_id
        )
        SELECT
            j.event_id,
            e.home_team_name,
            e.away_team_name,
            e.status,
            e.commence_time,
            j.total_snaps,
            j.big_jumps,
            ROUND((j.big_jumps::numeric / NULLIF(j.total_snaps, 0)), 4) AS jump_rate
        FROM jumps j
        JOIN events e ON e.id = j.event_id
        WHERE j.total_snaps >= 4
          AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        ORDER BY j.big_jumps DESC, jump_rate DESC
        LIMIT :lim
    """)

    affected_result = await db.execute(
        affected_sql,
        {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold, "lim": limit},
    )
    affected_events = affected_result.fetchall()

    diagnoses = []
    for row in affected_events:
        event_id = row.event_id

        # Get currently linked Kalshi futures_markets
        linked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.event_id == event_id,
                FuturesMarket.source == "kalshi",
            )
        )
        linked_markets = linked_result.scalars().all()

        # Get distinct market_ids from win_prob_snapshot game_state
        # game_state->'market_id' tells us which market generated each snapshot
        snapshot_markets_sql = text("""
            SELECT
                DISTINCT game_state->>'market_id' AS market_id,
                game_state->>'market_name' AS market_name,
                COUNT(*) AS snapshot_count,
                MIN(captured_at) AS first_snap,
                MAX(captured_at) AS last_snap,
                MIN(home_win_probability) AS min_prob,
                MAX(home_win_probability) AS max_prob,
                AVG(home_win_probability) AS avg_prob
            FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND game_state IS NOT NULL
              AND game_state->>'market_id' IS NOT NULL
            GROUP BY game_state->>'market_id', game_state->>'market_name'
            ORDER BY snapshot_count DESC
        """)
        snap_markets_result = await db.execute(
            snapshot_markets_sql, {"event_id": event_id}
        )
        snap_market_rows = snap_markets_result.fetchall()

        # Also get snapshots WITHOUT game_state (legacy snapshots)
        legacy_count_result = await db.execute(text("""
            SELECT COUNT(*) FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND (game_state IS NULL OR game_state->>'market_id' IS NULL)
        """), {"event_id": event_id})
        legacy_count = legacy_count_result.scalar() or 0

        # Classify the root cause
        distinct_market_ids = set()
        market_avg_probs = {}
        for srow in snap_market_rows:
            mid = srow.market_id
            if mid:
                distinct_market_ids.add(mid)
                market_avg_probs[mid] = float(srow.avg_prob) if srow.avg_prob else None

        # Check if linked markets have different tickers (different games)
        linked_tickers = {}
        for m in linked_markets:
            # Extract ticker prefix + date to identify unique games
            ticker = m.external_id or ""
            linked_tickers[str(m.id)] = {
                "ticker": ticker,
                "name": m.name,
                "status": m.status,
            }

        # Classification logic
        if len(distinct_market_ids) >= 2:
            # Multiple markets wrote snapshots — check if they're different games
            # Type A: different game tickers (multi-game)
            # Type B: same game, dual market (Team A win? + Team B win?)
            avg_probs = list(market_avg_probs.values())
            avg_probs = [p for p in avg_probs if p is not None]

            if len(avg_probs) >= 2:
                # If average probs are roughly complementary (~sum to 1), it's dual market
                avg_probs.sort()
                prob_sum = avg_probs[0] + avg_probs[-1]
                if 0.85 < prob_sum < 1.15:
                    cause_type = "B_dual_market"
                else:
                    cause_type = "A_multi_game"
            else:
                cause_type = "A_multi_game"
        elif len(linked_markets) >= 2 and len(distinct_market_ids) <= 1:
            cause_type = "B_dual_market_linked"
        else:
            cause_type = "C_other"

        diagnoses.append({
            "event_id": event_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "status": row.status,
            "commence_time": row.commence_time.isoformat() if row.commence_time else None,
            "snapshot_count": int(row.total_snaps),
            "jump_count": int(row.big_jumps),
            "jump_rate": float(row.jump_rate),
            "cause_type": cause_type,
            "linked_kalshi_markets": [
                {
                    "market_id": m.id,
                    "external_id": m.external_id,
                    "name": m.name,
                    "status": m.status,
                    "commence_time": m.commence_time.isoformat() if m.commence_time else None,
                }
                for m in linked_markets
            ],
            "snapshot_source_markets": [
                {
                    "market_id": srow.market_id,
                    "market_name": srow.market_name,
                    "snapshot_count": int(srow.snapshot_count),
                    "first_snap": srow.first_snap.isoformat() if srow.first_snap else None,
                    "last_snap": srow.last_snap.isoformat() if srow.last_snap else None,
                    "min_prob": round(float(srow.min_prob), 4) if srow.min_prob is not None else None,
                    "max_prob": round(float(srow.max_prob), 4) if srow.max_prob is not None else None,
                    "avg_prob": round(float(srow.avg_prob), 4) if srow.avg_prob is not None else None,
                }
                for srow in snap_market_rows
            ],
            "legacy_snapshots_no_market_id": legacy_count,
        })

    # Summary stats
    type_counts = {}
    for d in diagnoses:
        t = d["cause_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "total_diagnosed": len(diagnoses),
        "cause_type_summary": type_counts,
        "diagnoses": diagnoses,
    }


@router.post("/sawtooth-fix")
async def sawtooth_fix(
    secret: str = Query(None, description="Admin secret"),
    event_id: Optional[int] = Query(None, description="Fix a single event (or all if omitted)"),
    dry_run: bool = Query(True, description="Preview changes without applying"),
    jump_threshold: float = Query(0.03, description="Min |delta| to count as big jump"),
    rate_threshold: float = Query(0.30, description="Min jump_rate to flag"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Fix sawtooth oscillation by unlinking wrong markets and deleting bad snapshots.

    For each affected event:
    - Type A (multi-game): Identifies which market is the outlier (by avg probability
      distance from sportsbook consensus) and unlinks it + deletes its snapshots.
    - Type B (dual-market): Keeps all linked markets but deletes ALL historical
      snapshots (the devig averaging fix handles future writes correctly).
    - Type C (other): Deletes all Kalshi snapshots for the event (nuclear option
      for events with no linked markets or unparseable patterns).

    Use dry_run=true (default) to preview, then dry_run=false to apply.
    """
    _check_admin_secret(secret, request=request)

    # Find affected events
    if event_id:
        affected_sql = text("""
            WITH consecutive AS (
                SELECT
                    event_id,
                    home_win_probability,
                    LAG(home_win_probability) OVER (
                        PARTITION BY event_id ORDER BY captured_at
                    ) AS prev_prob
                FROM win_prob_snapshots
                WHERE source = 'kalshi'
                  AND event_id = :event_id
            ),
            jumps AS (
                SELECT
                    event_id,
                    COUNT(*) AS total_snaps,
                    COUNT(*) FILTER (
                        WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                    ) AS big_jumps
                FROM consecutive
                WHERE prev_prob IS NOT NULL
                GROUP BY event_id
            )
            SELECT j.event_id, j.total_snaps, j.big_jumps,
                   e.home_team_name, e.away_team_name, e.status
            FROM jumps j
            JOIN events e ON e.id = j.event_id
            WHERE j.total_snaps >= 4
        """)
        affected_result = await db.execute(
            affected_sql,
            {"event_id": event_id, "jump_threshold": jump_threshold},
        )
    else:
        affected_sql = text("""
            WITH consecutive AS (
                SELECT
                    event_id,
                    home_win_probability,
                    LAG(home_win_probability) OVER (
                        PARTITION BY event_id ORDER BY captured_at
                    ) AS prev_prob
                FROM win_prob_snapshots
                WHERE source = 'kalshi'
            ),
            jumps AS (
                SELECT
                    event_id,
                    COUNT(*) AS total_snaps,
                    COUNT(*) FILTER (
                        WHERE ABS(home_win_probability - prev_prob) > :jump_threshold
                    ) AS big_jumps
                FROM consecutive
                WHERE prev_prob IS NOT NULL
                GROUP BY event_id
            )
            SELECT j.event_id, j.total_snaps, j.big_jumps,
                   e.home_team_name, e.away_team_name, e.status
            FROM jumps j
            JOIN events e ON e.id = j.event_id
            WHERE j.total_snaps >= 4
              AND j.big_jumps::float / NULLIF(j.total_snaps, 0) > :rate_threshold
        """)
        affected_result = await db.execute(
            affected_sql,
            {"jump_threshold": jump_threshold, "rate_threshold": rate_threshold},
        )

    affected_rows = affected_result.fetchall()

    results = []
    total_markets_unlinked = 0
    total_snapshots_deleted = 0

    for row in affected_rows:
        eid = row.event_id
        fix_detail = {
            "event_id": eid,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "status": row.status,
            "snapshot_count": int(row.total_snaps),
            "actions": [],
        }

        # Get currently linked Kalshi markets
        linked_result = await db.execute(
            select(FuturesMarket)
            .where(
                FuturesMarket.event_id == eid,
                FuturesMarket.source == "kalshi",
            )
        )
        linked_markets = linked_result.scalars().all()

        # Get snapshot source breakdown by market_id
        snap_markets_result = await db.execute(text("""
            SELECT
                game_state->>'market_id' AS market_id,
                game_state->>'market_name' AS market_name,
                COUNT(*) AS snap_count,
                AVG(home_win_probability) AS avg_prob
            FROM win_prob_snapshots
            WHERE event_id = :event_id
              AND source = 'kalshi'
              AND game_state IS NOT NULL
              AND game_state->>'market_id' IS NOT NULL
            GROUP BY game_state->>'market_id', game_state->>'market_name'
            ORDER BY snap_count DESC
        """), {"event_id": eid})
        snap_sources = snap_markets_result.fetchall()

        distinct_market_ids = {s.market_id for s in snap_sources if s.market_id}
        market_avgs = {
            s.market_id: float(s.avg_prob) for s in snap_sources
            if s.market_id and s.avg_prob is not None
        }

        # Get sportsbook consensus for this event
        consensus_result = await db.execute(text("""
            SELECT home_win_probability FROM odds_snapshots
            WHERE event_id = :event_id
              AND home_win_probability IS NOT NULL
            ORDER BY captured_at DESC
            LIMIT 1
        """), {"event_id": eid})
        consensus_row = consensus_result.fetchone()

        # Also try opening odds as fallback
        if not consensus_row:
            consensus_result2 = await db.execute(text("""
                SELECT opening_home_probability FROM events WHERE id = :event_id
            """), {"event_id": eid})
            consensus_row = consensus_result2.fetchone()

        consensus = None
        if consensus_row and consensus_row[0] is not None:
            consensus = float(consensus_row[0])

        # Classify and decide fix action
        if len(distinct_market_ids) >= 2 and market_avgs:
            avg_probs = list(market_avgs.values())
            avg_probs_sorted = sorted(avg_probs)

            # Check if dual-market (complementary probs sum ~1)
            if len(avg_probs_sorted) == 2:
                prob_sum = avg_probs_sorted[0] + avg_probs_sorted[1]
                if 0.85 < prob_sum < 1.15:
                    # Type B: dual-market inversion — delete ALL Kalshi snapshots
                    # The devig averaging in Phase 2 handles future writes correctly
                    fix_detail["cause_type"] = "B_dual_market"

                    snap_count_result = await db.execute(text("""
                        SELECT COUNT(*) FROM win_prob_snapshots
                        WHERE event_id = :event_id AND source = 'kalshi'
                    """), {"event_id": eid})
                    to_delete = snap_count_result.scalar() or 0

                    fix_detail["actions"].append({
                        "action": "delete_all_kalshi_snapshots",
                        "reason": "dual-market complementary probs cause oscillation; devig fix handles future writes",
                        "snapshots_to_delete": to_delete,
                    })

                    if not dry_run:
                        del_result = await db.execute(
                            delete(WinProbSnapshot).where(
                                WinProbSnapshot.event_id == eid,
                                WinProbSnapshot.source == "kalshi",
                            )
                        )
                        total_snapshots_deleted += del_result.rowcount
                        fix_detail["actions"][-1]["snapshots_deleted"] = del_result.rowcount
                    else:
                        total_snapshots_deleted += to_delete
                else:
                    # Type A: multi-game linkage
                    fix_detail["cause_type"] = "A_multi_game"

                    # Find the outlier market — the one whose avg prob is furthest
                    # from consensus (if available), or the one with fewer snapshots
                    if consensus is not None:
                        # Pick the market closest to consensus as "correct"
                        best_mid = min(market_avgs, key=lambda mid: abs(market_avgs[mid] - consensus))
                        outlier_mids = [mid for mid in distinct_market_ids if mid != best_mid]
                    else:
                        # No consensus — keep the market with more snapshots
                        snap_counts = {s.market_id: int(s.snap_count) for s in snap_sources}
                        best_mid = max(snap_counts, key=lambda mid: snap_counts.get(mid, 0))
                        outlier_mids = [mid for mid in distinct_market_ids if mid != best_mid]

                    for omid in outlier_mids:
                        # Delete snapshots from the outlier market
                        snap_del_count_result = await db.execute(text("""
                            SELECT COUNT(*) FROM win_prob_snapshots
                            WHERE event_id = :event_id
                              AND source = 'kalshi'
                              AND game_state->>'market_id' = :market_id
                        """), {"event_id": eid, "market_id": str(omid)})
                        to_delete = snap_del_count_result.scalar() or 0

                        # Find the market name for this outlier
                        outlier_name = next(
                            (s.market_name for s in snap_sources if s.market_id == omid),
                            "unknown"
                        )

                        fix_detail["actions"].append({
                            "action": "delete_outlier_snapshots",
                            "outlier_market_id": omid,
                            "outlier_market_name": outlier_name,
                            "outlier_avg_prob": round(market_avgs.get(omid, 0), 4),
                            "kept_market_id": best_mid,
                            "consensus": round(consensus, 4) if consensus else None,
                            "reason": f"market avg={market_avgs.get(omid, 0):.3f} is far from consensus={consensus:.3f}" if consensus else "market has fewer snapshots",
                            "snapshots_to_delete": to_delete,
                        })

                        if not dry_run:
                            del_result = await db.execute(text("""
                                DELETE FROM win_prob_snapshots
                                WHERE event_id = :event_id
                                  AND source = 'kalshi'
                                  AND game_state->>'market_id' = :market_id
                            """), {"event_id": eid, "market_id": str(omid)})
                            total_snapshots_deleted += del_result.rowcount
                            fix_detail["actions"][-1]["snapshots_deleted"] = del_result.rowcount

                        # Unlink the outlier market if it's still linked
                        omid_int = int(omid) if omid and omid.isdigit() else None
                        if omid_int:
                            for m in linked_markets:
                                if m.id == omid_int:
                                    fix_detail["actions"].append({
                                        "action": "unlink_market",
                                        "market_id": m.id,
                                        "market_name": m.name,
                                        "external_id": m.external_id,
                                        "reason": "wrong game linked to this event",
                                    })
                                    if not dry_run:
                                        m.event_id = None
                                        total_markets_unlinked += 1
            else:
                # 3+ distinct markets — nuclear: delete all, keep the majority
                fix_detail["cause_type"] = "A_multi_game_complex"

                snap_counts = {s.market_id: int(s.snap_count) for s in snap_sources}
                best_mid = max(snap_counts, key=lambda mid: snap_counts.get(mid, 0)) if snap_counts else None

                # Delete snapshots from all outlier markets
                for omid in distinct_market_ids:
                    if omid == best_mid:
                        continue
                    snap_del_count_result = await db.execute(text("""
                        SELECT COUNT(*) FROM win_prob_snapshots
                        WHERE event_id = :event_id
                          AND source = 'kalshi'
                          AND game_state->>'market_id' = :market_id
                    """), {"event_id": eid, "market_id": str(omid)})
                    to_delete = snap_del_count_result.scalar() or 0

                    fix_detail["actions"].append({
                        "action": "delete_outlier_snapshots",
                        "outlier_market_id": omid,
                        "kept_market_id": best_mid,
                        "snapshots_to_delete": to_delete,
                    })

                    if not dry_run:
                        del_result = await db.execute(text("""
                            DELETE FROM win_prob_snapshots
                            WHERE event_id = :event_id
                              AND source = 'kalshi'
                              AND game_state->>'market_id' = :market_id
                        """), {"event_id": eid, "market_id": str(omid)})
                        total_snapshots_deleted += del_result.rowcount

                    omid_int = int(omid) if omid and omid.isdigit() else None
                    if omid_int:
                        for m in linked_markets:
                            if m.id == omid_int:
                                fix_detail["actions"].append({
                                    "action": "unlink_market",
                                    "market_id": m.id,
                                    "external_id": m.external_id,
                                })
                                if not dry_run:
                                    m.event_id = None
                                    total_markets_unlinked += 1

        elif len(distinct_market_ids) == 0:
            # No game_state market_ids — legacy snapshots. Delete all.
            fix_detail["cause_type"] = "C_legacy_no_market_id"
            snap_count_result = await db.execute(text("""
                SELECT COUNT(*) FROM win_prob_snapshots
                WHERE event_id = :event_id AND source = 'kalshi'
            """), {"event_id": eid})
            to_delete = snap_count_result.scalar() or 0

            fix_detail["actions"].append({
                "action": "delete_all_kalshi_snapshots",
                "reason": "legacy snapshots without market_id; cannot attribute to specific market",
                "snapshots_to_delete": to_delete,
            })

            if not dry_run:
                del_result = await db.execute(
                    delete(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == eid,
                        WinProbSnapshot.source == "kalshi",
                    )
                )
                total_snapshots_deleted += del_result.rowcount

        else:
            # Single market_id but still sawtooth — must be inversion within
            # one market. Delete all Kalshi snapshots.
            fix_detail["cause_type"] = "C_single_market_oscillation"
            snap_count_result = await db.execute(text("""
                SELECT COUNT(*) FROM win_prob_snapshots
                WHERE event_id = :event_id AND source = 'kalshi'
            """), {"event_id": eid})
            to_delete = snap_count_result.scalar() or 0

            fix_detail["actions"].append({
                "action": "delete_all_kalshi_snapshots",
                "reason": "single market oscillating; likely yes_is_home flip-flop",
                "snapshots_to_delete": to_delete,
            })

            if not dry_run:
                del_result = await db.execute(
                    delete(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == eid,
                        WinProbSnapshot.source == "kalshi",
                    )
                )
                total_snapshots_deleted += del_result.rowcount

        # Also clear kalshi from win_probability_sources on the event
        if not dry_run and fix_detail["actions"]:
            wps_result = await db.execute(
                select(Event.win_probability_sources).where(Event.id == eid)
            )
            wps = wps_result.scalar_one_or_none() or {}
            if "kalshi" in wps:
                del wps["kalshi"]
                await db.execute(
                    update(Event)
                    .where(Event.id == eid)
                    .values(win_probability_sources=wps)
                )
                fix_detail["actions"].append({
                    "action": "clear_kalshi_from_win_prob_sources",
                })

        results.append(fix_detail)

    if not dry_run:
        await db.commit()

    return {
        "dry_run": dry_run,
        "events_processed": len(results),
        "total_markets_unlinked": total_markets_unlinked,
        "total_snapshots_deleted": total_snapshots_deleted,
        "results": results,
    }


@router.post("/prediction-markets/backfill-wps")
async def backfill_win_probability_sources(
    request: Request, secret: str = Query(None),
    limit: int = Query(500),
    event_id: int = Query(
        None,
        description="Restrict the backfill to a single event (targeted repair, "
        "e.g. after a degenerate-combat merge repoints a Kalshi market).",
    ),
    db: AsyncSession = Depends(get_db_rw),
):
    """Backfill win_probability_sources for linked moneyline game markets.

    Orders newest-first so a bounded run reaches the most recently linked
    markets (post-merge repoints land at the top). Pass ``event_id`` to blend
    exactly one event — the reliable path to verify a freshly merged fight
    (e.g. the 15132461→14627580 SAIPIM fold-in) carries kalshi into the blend.
    """
    _check_admin_secret(secret, request=request)

    import re as _re

    from app.utils.prediction_market_matching import (
        find_moneyline_outcome,
        extract_matchup_with_ticker_fallback,
        feeds_win_prob_blend,
    )

    stats = {"processed": 0, "written": 0, "skipped": 0, "errors": 0}

    # Only fetch GAME (moneyline) markets — much smaller than ALL linked markets
    query = (
        select(FuturesMarket, Event)
        .join(Event, FuturesMarket.event_id == Event.id)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.source.in_(["kalshi", "polymarket"]),
            FuturesMarket.event_id.isnot(None),
            or_(
                FuturesMarket.external_id.ilike("%game%"),
                FuturesMarket.name.ilike("% vs.%"),
                FuturesMarket.name.ilike("% vs %"),
            ),
        )
    )
    if event_id is not None:
        query = query.where(FuturesMarket.event_id == event_id)
    # Newest markets first: a limited run then covers recent links/merges
    # instead of an arbitrary slice of the 170K+ candidate pool.
    query = query.order_by(FuturesMarket.id.desc()).limit(limit)
    result = await db.execute(query)
    rows = result.unique().all()

    by_event_source = {}
    for market, event in rows:
        key = (event.id, market.source)
        # Prefer the blend-eligible winner line (team-sport …game OR combat
        # fight winner) over any prop sibling fetched for the same event.
        if key not in by_event_source or feeds_win_prob_blend(market.external_id):
            by_event_source[key] = (market, event)

    for (event_id, source), (market, event) in by_event_source.items():
        stats["processed"] += 1
        wps = event.win_probability_sources or {}
        if source in wps:
            stats["skipped"] += 1
            continue

        if market.source == "kalshi":
            if not feeds_win_prob_blend(market.external_id):
                stats["skipped"] += 1
                continue

        try:
            # Combat fight-winner names carry a leading sport_id prefix
            # ("329: Saint-Denis vs Pimblett") that breaks the anchored matchup
            # regex — strip it. Use the ticker-fallback extractor so this path
            # matches the live Phase-2 matching task (recovers the matchup from
            # the Kalshi ticker when the name alone is insufficient).
            clean_name = _re.sub(r"^\s*\d+:\s*", "", market.name or "")
            matchup = extract_matchup_with_ticker_fallback(
                clean_name, external_id=market.external_id,
            )
            if not matchup:
                stats["skipped"] += 1
                continue

            ml = find_moneyline_outcome(
                list(market.outcomes), matchup,
                event.home_team_name, event.away_team_name,
            )
            if not ml:
                stats["skipped"] += 1
                continue

            outcome, yes_is_home = ml
            prob = float(outcome.current_probability or 0)
            home_prob = prob if yes_is_home else 1.0 - prob

            new_wps = dict(wps)
            new_wps[source] = round(home_prob, 4)
            await db.execute(
                update(Event)
                .where(Event.id == event_id)
                .values(win_probability_sources=new_wps)
            )
            stats["written"] += 1
        except Exception as e:
            stats["errors"] += 1

    await db.commit()
    return stats


@router.get("/prediction-markets/game-market-counts")
async def game_market_counts(
    request: Request, secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Debug: count game-winner markets by series prefix."""
    _check_admin_secret(secret, request=request)
    results = {}
    for prefix in ["KXMLBGAME", "KXNBAGAME", "KXNHLGAME", "KXNFLGAME"]:
        r = await db.execute(
            text(
                "SELECT COUNT(*), COUNT(event_id) FROM futures_markets "
                "WHERE source='kalshi' AND external_id LIKE :p"
            ),
            {"p": f"{prefix}%"},
        )
        total, linked = r.one()
        results[prefix] = {"total": total, "linked": linked}
    r = await db.execute(
        text("SELECT COUNT(*) FROM futures_markets WHERE source='kalshi'")
    )
    results["total_kalshi"] = r.scalar()
    # Check 7-day window coverage
    r7 = await db.execute(
        text("""
            WITH re AS (
                SELECT e.id, s.key AS sk FROM events e JOIN sports s ON e.sport_id = s.id
                WHERE e.commence_time >= NOW() - INTERVAL '7 days'
                  AND e.commence_time <= NOW() + INTERVAL '2 days'
                  AND s.key = 'baseball_mlb'
            ),
            kl AS (
                SELECT DISTINCT event_id FROM futures_markets
                WHERE event_id IS NOT NULL AND source = 'kalshi'
                  AND external_id LIKE 'KXMLBGAME%'
            )
            SELECT COUNT(*) AS total, COUNT(kl.event_id) AS covered
            FROM re LEFT JOIN kl ON kl.event_id = re.id
        """)
    )
    row = r7.one()
    results["mlb_7day"] = {"total_events": row[0], "kalshi_game_covered": row[1]}
    return results
