"""Admin endpoints for external provider polling, debug, and status.

Covers: Kalshi, Polymarket, Odds API futures, ESPN, StatPal, DataGolf, MLB,
rosters, and quota monitoring.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket, FuturesOutcome, FuturesOddsSnapshot
from app.services import get_db, get_db_rw
from app.utils import probability_to_american
from app.utils.espn_candidate_selection import select_authorized_espn_candidate
from app.routes.admin_utils import _check_admin_destructive, _check_admin_secret

router = APIRouter()


# =============================================================================
# Kalshi
# =============================================================================


@router.get("/kalshi/scan-report")
async def kalshi_scan_report(
    request: Request,
    history: int = Query(24, ge=1, le=48, description="Recent runs to summarize"),
):
    """Main-scan telemetry for ``poll_kalshi_markets`` (#1586 / #1845).

    Answers, from measurement rather than hypothesis: where the cursor walk
    starts, where it ends, what it drops, why it stops — and how many EXISTING
    (i.e. already-displayed) events the upsert loop never reached because the
    per-event deadline fired after the NEW ones.

    Read the ``summary`` block first. A single beat cannot distinguish "this run
    was slow" from "the walk never advances"; ``cursor_appears_stuck`` and
    ``never_wrapped`` are the two readings that can only be taken across runs.
    """
    # `request` MUST go through the keyword. The signature is
    # `_check_admin_secret(secret=None, *, request=None)`, so a positional call
    # binds the Request object to `secret` and leaves `request=None` — the
    # header is then read off None, nothing matches, and the endpoint answers
    # 403 to a perfectly valid token, forever. Shipped that way in q350 and
    # caught by INT-067 on the first real read: this is the ONE call site out of
    # 47 in this file that did not pass `request=request`.
    _check_admin_secret(request=request)

    from app.utils.kalshi_scan_report import (
        load_scan_history,
        load_scan_report,
        summarize_history,
    )

    last = load_scan_report()
    rows = load_scan_history(history)
    return {
        "last": last,
        "summary": summarize_history(rows),
        "history": rows,
        "note": (
            "No report yet means poll_kalshi_markets has not completed a beat "
            "since this instrumentation deployed (2h schedule). An empty read "
            "is not a healthy read — gotcha #53. "
            "Check summary.arithmetic_ok BEFORE reading any verdict: beats "
            "written before queue 355 counted events_fetched over the main scan "
            "only while events_new/events_existing covered main scan PLUS the "
            "supplementary rescue, so they could not be a partition and are "
            "reported as runs_unknown_reconciliation. summary.readable_beats is "
            "the count that satisfies the >=3-beat gate."
        ),
    }


@router.get("/kalshi/cliff-drain")
async def kalshi_cliff_drain_progress(request: Request):
    """Progress of the fetch-now-or-never Kalshi price-history drain (#1586).

    Read ``remaining`` against ``cohort.at_risk``: the drain runs oldest-first
    inside the 86-day retention floor, so the at-risk band is what it is
    currently working through, and ``cohort.past_cliff`` is what no rail can
    ever recover. ``watermark.checkpoint_written`` is the one field that says
    whether the run before this one is actually resumable.
    """
    _check_admin_secret(request=request)

    from app.tasks.kalshi_cliff import cliff_drain_progress

    return await cliff_drain_progress()


@router.post("/kalshi/cliff-drain/run")
async def trigger_kalshi_cliff_drain(
    request: Request,
    limit: int = Query(400, ge=1, le=5000),
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Queue one cliff-drain pass now (it also runs hourly on the beat)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import kalshi_cliff_drain as _task

    result = _task.delay(limit=limit)
    return {
        "status": "queued",
        "task_id": result.id,
        "limit": limit,
        "note": (
            "Resumes from the persisted watermark — this does not restart the "
            "sweep. Poll GET /api/admin/kalshi/cliff-drain for fetched/remaining."
        ),
    }


@router.post("/kalshi/cliff-drain/reset")
async def reset_kalshi_cliff_drain(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Rewind the drain watermark to the start of the retention window.

    Only useful after a backfill changes what the cohort contains; a normal
    re-run should NOT reset, or the sweep re-grinds ground it already covered.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.kalshi_cliff import reset_state

    return {"status": "reset", "state": reset_state()}


@router.post("/kalshi/poll")
async def trigger_kalshi_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Manually trigger Kalshi market polling.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - check Celery logs for results.
    Requires KALSHI_API_KEY to be configured.
    """
    _check_admin_secret(secret, request=request)

    kalshi_key = os.getenv("KALSHI_API_KEY")
    if not kalshi_key:
        raise HTTPException(
            status_code=400,
            detail="KALSHI_API_KEY not configured. Add it to your environment variables."
        )

    # Queue the task to run in background (avoids Heroku's 30s timeout)
    from app.tasks import poll_kalshi_markets

    try:
        task = poll_kalshi_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Kalshi polling task queued. Check Celery worker logs for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/kalshi/task/{task_id}")
async def get_kalshi_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Check the status of a Kalshi polling task.

    Returns the task state and result (if complete).
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/kalshi/debug-discovery")
async def debug_kalshi_discovery(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    search: Optional[str] = Query(None, description="Search term to filter series (e.g., 'olympic')"),
):
    """
    Debug Kalshi series discovery: shows what series each category returns,
    and optionally searches all series for a keyword.
    """
    _check_admin_secret(secret, request=request)

    kalshi_key = os.getenv("KALSHI_API_KEY")
    if not kalshi_key:
        raise HTTPException(status_code=400, detail="KALSHI_API_KEY not configured")

    import asyncio
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService()
    try:
        # Step 1: Discover tags by categories (reveals subcategories like Olympics)
        tags_by_category = None
        try:
            tags_by_category = await service.get_tags_by_categories()
        except Exception as e:
            tags_by_category = {"error": str(e)}

        await asyncio.sleep(0.3)

        # Step 2: Check each category
        categories = service.SPORTS_CATEGORIES
        category_results = {}

        for category in categories:
            await asyncio.sleep(0.3)
            try:
                series_list, _ = await service.get_series(category=category)
                tickers = [s.get("ticker") for s in series_list if s.get("ticker")]
                titles = [s.get("title", s.get("ticker", "?")) for s in series_list]
                tags_seen = set()
                for s in series_list:
                    for tag in (s.get("tags") or []):
                        tags_seen.add(tag)
                category_results[category] = {
                    "count": len(tickers),
                    "tickers": sorted(tickers)[:30],
                    "titles": titles[:30],
                    "tags_on_series": sorted(tags_seen),
                }
            except Exception as e:
                category_results[category] = {"error": str(e)}

        # Step 3: Try tag-based discovery for Olympics specifically
        olympics_tag_results = {}
        for tag in ["Olympics", "olympics", "Winter Olympics", "winter-olympics"]:
            await asyncio.sleep(0.3)
            try:
                series_list, _ = await service.get_series(category="Sports", tags=tag)
                tickers = [s.get("ticker") for s in series_list if s.get("ticker")]
                titles = [s.get("title", s.get("ticker", "?")) for s in series_list]
                olympics_tag_results[tag] = {
                    "count": len(tickers),
                    "tickers": sorted(tickers)[:20],
                    "titles": titles[:20],
                }
            except Exception as e:
                olympics_tag_results[tag] = {"error": str(e)}

        # Step 4: If search term provided, scan ALL series for keyword
        search_results = None
        if search:
            search_lower = search.lower()
            all_series = []
            cursor = None
            for page in range(10):  # Up to 10 pages
                await asyncio.sleep(0.3)
                page_series, cursor = await service.get_series(cursor=cursor)
                all_series.extend(page_series)
                if not cursor:
                    break

            matches = []
            for s in all_series:
                ticker = s.get("ticker", "")
                title = s.get("title", "")
                cat = s.get("category", "")
                tags = s.get("tags") or []
                tags_str = ",".join(tags).lower()
                if (search_lower in ticker.lower()
                    or search_lower in title.lower()
                    or search_lower in cat.lower()
                    or search_lower in tags_str):
                    matches.append({
                        "ticker": ticker,
                        "title": title,
                        "category": cat,
                        "tags": tags,
                    })

            search_results = {
                "query": search,
                "total_series_scanned": len(all_series),
                "matches": matches,
            }

        return {
            "tags_by_category": tags_by_category,
            "categories_checked": category_results,
            "olympics_tag_search": olympics_tag_results,
            "search_results": search_results,
        }

    finally:
        await service.close()


# =============================================================================
# Polymarket
# =============================================================================


@router.post("/polymarket/poll")
async def trigger_polymarket_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Manually trigger Polymarket polling.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - check Celery logs for results.
    No API key required (Polymarket is fully public).
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import poll_polymarket_markets

    try:
        task = poll_polymarket_markets.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Polymarket polling task queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/polymarket/task/{task_id}")
async def get_polymarket_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Check the status of a Polymarket polling/backfill task.

    Returns the task state and result (if complete).
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.post("/polymarket/backfill-history")
async def trigger_polymarket_history_backfill(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(50, description="Max outcomes to process per run"),
    fidelity: int = Query(60, description="Price granularity in minutes (60=hourly, 1440=daily)"),
    interval: str = Query("max", description="Time range: 1h, 6h, 1d, 1w, max"),
):
    """
    Backfill historical price data from Polymarket's CLOB API.

    Fetches /prices-history for Polymarket outcomes that have sparse
    snapshot data. Prioritizes outcomes with the fewest existing snapshots.
    Uses ON CONFLICT DO NOTHING to avoid duplicate inserts.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import backfill_polymarket_history

    try:
        task = backfill_polymarket_history.delay(limit, fidelity, interval)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Polymarket history backfill queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/polymarket/fix-outcome-names")
async def fix_polymarket_outcome_names(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Fix Polymarket outcome names using groupItemTitle from Gamma API.

    Finds FuturesMarket records (source='polymarket') where multiple outcomes
    share the same name, re-fetches the event from Polymarket's Gamma API,
    and updates outcome names using the groupItemTitle field.

    Runs as a background Celery task to avoid Heroku's 30-second HTTP timeout.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import fix_outcome_names

    try:
        task = fix_outcome_names.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Outcome names fix queued. Use /api/admin/polymarket/task/{task_id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


# =============================================================================
# Futures (Odds API)
# =============================================================================


@router.post("/futures/poll")
async def trigger_futures_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Manually trigger futures/outrights polling from The Odds API.

    Queues the polling task to run in the background via Celery.
    Returns immediately with task ID - use /futures/task/{id} to check status.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import poll_futures_odds

    try:
        task = poll_futures_odds.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Futures polling task queued. Check Celery worker logs for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/futures/task/{task_id}")
async def get_futures_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Check the status of a futures polling task.

    Returns the task state and result (if complete).
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.get("/futures/sports")
async def get_sports_with_outrights(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Debug endpoint: Get list of sports that have outrights/futures available.

    This calls The Odds API to see which sports have has_outrights=True.
    Useful for debugging why certain futures aren't appearing.
    """
    _check_admin_secret(secret, request=request)

    from app.services.odds_api import OddsAPIService

    try:
        service = OddsAPIService()
        outright_sports = await service.get_sports_with_outrights()
        return {
            "status": "success",
            "count": len(outright_sports),
            "sports": outright_sports,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch sports: {str(e)}")


@router.post("/futures/normalize-probabilities")
async def normalize_futures_probabilities(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    dry_run: bool = Query(False, description="Preview changes without saving"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Normalize historical Odds API futures probabilities to remove vig/overround.

    Raw implied probabilities from American odds sum to >100% per bookmaker
    (typically 130-150% for markets with many outcomes). This endpoint:

    1. Normalizes all futures_odds_snapshots for odds_api markets
    2. Recalculates current_probability on futures_outcomes
    3. Recalculates opening_probability on futures_outcomes
    4. Recalculates American odds from normalized probabilities
    """
    _check_admin_secret(secret, request=request)

    from collections import defaultdict
    from statistics import mean

    stats = {
        "markets_processed": 0,
        "snapshots_normalized": 0,
        "outcomes_updated": 0,
        "sample_changes": [],
    }

    # Get all Odds API futures markets with their outcomes
    result = await db.execute(
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(FuturesMarket.source == "odds_api")
    )
    markets = result.scalars().all()

    for market in markets:
        outcome_ids = [o.id for o in market.outcomes]
        if not outcome_ids:
            continue

        # Fetch all snapshots for this market's outcomes
        snap_result = await db.execute(
            select(FuturesOddsSnapshot)
            .where(FuturesOddsSnapshot.outcome_id.in_(outcome_ids))
            .order_by(FuturesOddsSnapshot.captured_at)
        )
        snapshots = snap_result.scalars().all()

        if not snapshots:
            continue

        stats["markets_processed"] += 1

        # Group snapshots by (bookmaker, captured_at) to find normalization factor
        # Key: (bookmaker, captured_at) -> list of (snapshot, probability)
        groups: dict[tuple, list] = defaultdict(list)
        for snap in snapshots:
            if snap.probability is not None:
                groups[(snap.bookmaker, snap.captured_at)].append(snap)

        # Normalize each group
        for (bookmaker, captured_at), group_snaps in groups.items():
            total_prob = sum(float(s.probability) for s in group_snaps)
            if total_prob <= 0 or abs(total_prob - 1.0) < 0.01:
                # Already normalized or invalid, skip
                continue

            for snap in group_snaps:
                old_prob = float(snap.probability)
                new_prob = old_prob / total_prob
                new_american = probability_to_american(new_prob) if new_prob > 0 else None

                if not dry_run:
                    snap.probability = new_prob
                    snap.american_odds = new_american

                stats["snapshots_normalized"] += 1

                # Capture a few examples
                if len(stats["sample_changes"]) < 10:
                    outcome_name = next(
                        (o.name for o in market.outcomes if o.id == snap.outcome_id),
                        "?"
                    )
                    stats["sample_changes"].append({
                        "market": market.name,
                        "outcome": outcome_name,
                        "bookmaker": bookmaker,
                        "old_prob": round(old_prob, 6),
                        "new_prob": round(new_prob, 6),
                        "normalization_factor": round(total_prob, 4),
                    })

        # Now recalculate current_probability and opening_probability
        # on each outcome using normalized snapshots
        for outcome in market.outcomes:
            outcome_snaps = [s for s in snapshots if s.outcome_id == outcome.id]
            if not outcome_snaps:
                continue

            # Current probability: average of most recent snapshot per bookmaker
            latest_by_bm: dict[str, FuturesOddsSnapshot] = {}
            for snap in outcome_snaps:
                bm = snap.bookmaker
                if bm not in latest_by_bm or snap.captured_at > latest_by_bm[bm].captured_at:
                    latest_by_bm[bm] = snap

            if latest_by_bm:
                avg_current = mean(
                    float(s.probability) for s in latest_by_bm.values()
                    if s.probability is not None
                )
                new_american = probability_to_american(avg_current) if avg_current > 0 else None
                if not dry_run:
                    outcome.current_probability = avg_current
                    outcome.current_american_odds = new_american

            # Opening probability: average of earliest snapshot per bookmaker
            earliest_by_bm: dict[str, FuturesOddsSnapshot] = {}
            for snap in outcome_snaps:
                bm = snap.bookmaker
                if bm not in earliest_by_bm or snap.captured_at < earliest_by_bm[bm].captured_at:
                    earliest_by_bm[bm] = snap

            if earliest_by_bm:
                avg_opening = mean(
                    float(s.probability) for s in earliest_by_bm.values()
                    if s.probability is not None
                )
                opening_american = probability_to_american(avg_opening) if avg_opening > 0 else None
                if not dry_run:
                    outcome.opening_probability = avg_opening
                    outcome.opening_american_odds = opening_american

            stats["outcomes_updated"] += 1

    if not dry_run:
        await db.commit()

    return {
        "status": "dry_run" if dry_run else "completed",
        "stats": stats,
    }


@router.post("/futures/retier")
async def retier_futures_markets(
    request: Request, secret: str = Query(None),
    limit: int = Query(1000),
    db: AsyncSession = Depends(get_db_rw),
):
    """Re-compute market_tier for all futures markets using current patterns."""
    _check_admin_secret(secret, request=request)

    from app.utils.market_label_normalization import compute_market_tier

    result = await db.execute(
        select(FuturesMarket).limit(limit)
    )
    markets = result.scalars().all()
    changed = 0
    for market in markets:
        new_tier = compute_market_tier(
            market.name, market.category,
            sport_category=market.llm_sport_category,
        )
        if market.market_tier != new_tier:
            market.market_tier = new_tier
            changed += 1

    await db.commit()
    return {"scanned": len(markets), "changed": changed}


# =============================================================================
# ESPN
# =============================================================================


@router.post("/espn/sync-teams")
async def sync_espn_teams(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key to sync (e.g., basketball_nba)"),
    dry_run: bool = Query(False, description="Preview sync without saving"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Sync team data from ESPN (colors, logos, abbreviations).

    Fetches teams from ESPN API and updates matching teams in our database.
    Uses LLM for fuzzy name matching when direct match fails.
    """
    _check_admin_secret(secret, request=request)

    from app.services import get_espn_service, llm
    from app.models import Team, Sport

    espn = get_espn_service()

    # Get our teams for this sport
    sport_result = await db.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = sport_result.scalar_one_or_none()
    if not sport:
        raise HTTPException(status_code=404, detail=f"Sport not found: {sport_key}")

    teams_result = await db.execute(
        select(Team).where(Team.sport_id == sport.id)
    )
    our_teams = teams_result.scalars().all()

    if not our_teams:
        return {"status": "no_teams", "message": f"No teams found for {sport_key}"}

    # Fetch ESPN teams
    espn_teams = await espn.get_teams(sport_key)
    if espn_teams is None:
        return {
            "status": "authority_dark",
            "message": "ESPN did not answer — no team list was received. This is "
                       "NOT 'the league has no teams'; nothing was matched.",
        }
    if not espn_teams:
        return {"status": "espn_error", "message": "Could not fetch teams from ESPN"}

    # Build lookup by name variations
    espn_lookup = {}
    for et in espn_teams:
        for name in [et.name, et.display_name, et.short_name, et.nickname, et.abbreviation]:
            if name:
                espn_lookup[name.lower()] = et

    matched = []
    unmatched = []
    updated = []

    for team in our_teams:
        espn_team = None
        match_type = None

        # Try exact match first
        name_lower = team.name.lower()
        if name_lower in espn_lookup:
            espn_team = espn_lookup[name_lower]
            match_type = "exact"
        else:
            # Try partial matching
            for key, et in espn_lookup.items():
                if key in name_lower or name_lower in key:
                    espn_team = et
                    match_type = "partial"
                    break

        # If still no match, try LLM
        if not espn_team and llm.is_available():
            best_score = 0
            for et in espn_teams:
                score = llm.match_team_names_cached(team.name, et.display_name or et.name, sport_key)
                if score > best_score and score >= 0.8:
                    best_score = score
                    espn_team = et
                    match_type = f"llm_{score:.2f}"

        if espn_team:
            matched.append({
                "our_team": team.name,
                "espn_team": espn_team.display_name or espn_team.name,
                "espn_id": espn_team.espn_id,
                "match_type": match_type,
                "primary_color": espn_team.primary_color,
                "secondary_color": espn_team.secondary_color,
                "logo": espn_team.logo_url,
            })

            if not dry_run:
                # Update team with ESPN data
                changed = False
                if espn_team.espn_id and team.espn_id != espn_team.espn_id:
                    team.espn_id = espn_team.espn_id
                    changed = True
                if espn_team.primary_color and team.primary_color != espn_team.primary_color:
                    team.primary_color = espn_team.primary_color
                    changed = True
                if espn_team.secondary_color and team.secondary_color != espn_team.secondary_color:
                    team.secondary_color = espn_team.secondary_color
                    changed = True
                if espn_team.logo_url and team.logo_url_small != espn_team.logo_url:
                    team.logo_url_small = espn_team.logo_url
                    team.logo_url_large = espn_team.logo_url
                    changed = True
                if espn_team.abbreviation and team.abbreviation != espn_team.abbreviation:
                    team.abbreviation = espn_team.abbreviation
                    changed = True
                if espn_team.record and team.current_record != espn_team.record:
                    team.current_record = espn_team.record
                    changed = True

                # Build alternate names
                alt_names = [espn_team.name, espn_team.display_name, espn_team.short_name, espn_team.nickname]
                alt_names = [n for n in alt_names if n and n != team.name]
                if alt_names:
                    team.alternate_names = alt_names
                    changed = True

                if changed:
                    updated.append(team.name)
        else:
            unmatched.append(team.name)

    if not dry_run:
        await db.commit()

    return {
        "status": "success",
        "dry_run": dry_run,
        "sport_key": sport_key,
        "our_teams": len(our_teams),
        "espn_teams": len(espn_teams),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "updated": len(updated) if not dry_run else 0,
        "matches": matched[:20],  # Preview first 20
        "unmatched_teams": unmatched[:10] if unmatched else None,
    }


@router.get("/espn/teams-status")
async def espn_teams_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN team enrichment.

    Shows how many teams have ESPN data (colors, logos).
    """
    _check_admin_secret(secret, request=request)

    from app.models import Team

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Team.espn_id.isnot(None)).label("with_espn_id"),
            func.count().filter(Team.primary_color.isnot(None)).label("with_color"),
            func.count().filter(Team.logo_url_small.isnot(None)).label("with_logo"),
            func.count().filter(Team.alternate_names.isnot(None)).label("with_alt_names"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_espn_id": row.with_espn_id,
        "with_color": row.with_color,
        "with_logo": row.with_logo,
        "with_alt_names": row.with_alt_names,
        "enrichment_pct": round(row.with_espn_id / row.total * 100, 1) if row.total > 0 else 0,
    }


@router.post("/espn/sync-live-events")
async def sync_espn_live_events(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key to sync"),
    dry_run: bool = Query(False, description="Preview sync without saving"),
    skip_llm: bool = Query(False, description="Skip LLM matching (faster, avoids timeout)"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Sync live event data from ESPN (scores, clock, period, venue, broadcast).

    Matches ESPN events to our events and updates game state.
    Use skip_llm=true to avoid timeouts when LLM matching is slow.
    """
    _check_admin_secret(secret, request=request)

    from app.services import get_espn_service, llm
    from app.models import Venue
    from app.utils.espn_id_stamp import REFUSED, STAMPED, stamp_espn_id_if_unheld

    espn = get_espn_service()

    # Get ESPN scoreboard
    espn_events = await espn.get_scoreboard(sport_key)
    if espn_events is None:
        return {
            "status": "authority_dark",
            "message": "ESPN did not answer — the scoreboard was never received, "
                       "which is not the same as an empty slate.",
        }
    if not espn_events:
        return {"status": "no_events", "message": "No events from ESPN scoreboard"}

    # Get our live/upcoming events for this sport
    events_result = await db.execute(
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.sport.has(key=sport_key),
            Event.status.in_(["scheduled", "live"]),
        )
    )
    our_events = events_result.scalars().all()

    matched = []
    updated = []
    llm_matched = []
    #: #2049 / gotcha #53 — a name hit the same-game gate REFUSED is a different
    #: fact from no name hit at all, and an operator reading only "matched: 0"
    #: cannot tell a coverage gap from a suppressed manufacture.
    refused: list[dict] = []
    #: #2693 CERT-784 — the OTHER refusal, and it is a different fact again: the
    #: pair was authorized and the id is already worn by another row. Counted
    #: separately because it names a collision this rail declined to recreate,
    #: which is the number that says the step-2 repair is holding.
    id_refusals: list[dict] = []

    def names_match(our_names: list, espn_name: str) -> bool:
        """Check if any of our name variations match the ESPN name."""
        espn_lower = (espn_name or "").lower()
        for name in our_names:
            name_lower = name.lower()
            if name_lower in espn_lower or espn_lower in name_lower:
                return True
        return False

    for event in our_events:
        # Build list of name variations for matching
        home_names = [event.home_team_name]
        away_names = [event.away_team_name]

        # Add normalized name if available
        if event.home_team_normalized:
            home_names.append(event.home_team_normalized)
        if event.away_team_normalized:
            away_names.append(event.away_team_normalized)

        # Add alternate names if available
        if event.home_team_alt_names:
            home_names.extend(event.home_team_alt_names)
        if event.away_team_alt_names:
            away_names.extend(event.away_team_alt_names)

        # Try to match by team names.
        # #2049: this rail took the first substring/LLM name hit among ALL
        # scheduled/live rows and then OVERWROTE an existing espn_id, with no
        # time gate whatsoever — the most permissive of the five siblings codex
        # censused. Both arms now select the nearest candidate and stamp only
        # if the same-game gate authorizes it.
        espn_event = None
        match_method = None

        espn_event, _name_reason = select_authorized_espn_candidate(
            espn_events,
            event.commence_time,
            is_name_match=lambda ee: (
                names_match(home_names, ee.home_team.display_name or ee.home_team.name or "")
                and names_match(away_names, ee.away_team.display_name or ee.away_team.name or "")
            ),
            # FF1/#2058: this rail OVERWRITES an existing espn_id, so the id it
            # already holds is the one piece of identity evidence in the room.
            anchor_espn_id=getattr(event, "espn_id", None),
        )
        if espn_event is not None:
            match_method = "name_match"
        elif _name_reason != "no-name-match":
            refused.append({
                "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                "reason": _name_reason,
                "arm": "name_match",
            })

        # LLM fallback for unmatched events (skip if skip_llm=true to avoid timeout)
        if not espn_event and not skip_llm and llm.is_available():
            def _llm_match(ee) -> bool:
                espn_home = ee.home_team.display_name or ee.home_team.name or ""
                espn_away = ee.away_team.display_name or ee.away_team.name or ""
                home_conf = llm.match_team_names_cached(event.home_team_name, espn_home, sport_key)
                away_conf = llm.match_team_names_cached(event.away_team_name, espn_away, sport_key)
                return home_conf >= 0.8 and away_conf >= 0.8

            espn_event, _llm_reason = select_authorized_espn_candidate(
                espn_events, event.commence_time, is_name_match=_llm_match,
                anchor_espn_id=getattr(event, "espn_id", None),
            )
            if espn_event is not None:
                match_method = "llm"
                _espn_home = espn_event.home_team.display_name or espn_event.home_team.name or ""
                _espn_away = espn_event.away_team.display_name or espn_event.away_team.name or ""
                llm_matched.append({
                    "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                    "espn_event": f"{_espn_away} @ {_espn_home}",
                    "home_confidence": llm.match_team_names_cached(
                        event.home_team_name, _espn_home, sport_key
                    ),
                    "away_confidence": llm.match_team_names_cached(
                        event.away_team_name, _espn_away, sport_key
                    ),
                })
            elif _llm_reason != "no-name-match":
                refused.append({
                    "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                    "reason": _llm_reason,
                    "arm": "llm",
                })

        if espn_event:
            matched.append({
                "our_event": f"{event.away_team_name} @ {event.home_team_name}",
                "espn_event": espn_event.short_name,
                "espn_id": espn_event.espn_id,
                "status": espn_event.status,
                "clock": espn_event.clock,
                "period": espn_event.status_detail,
                "home_score": espn_event.home_score,
                "away_score": espn_event.away_score,
                "broadcasts": espn_event.broadcasts,
                "win_prob": espn_event.home_win_probability,
            })

            if not dry_run:
                changed = False

                # Update ESPN ID.
                #
                # #2693 CERT-784: through the #2017 holder check, not raw. The
                # pair is authorized (same game, time-gated) but that says
                # nothing about whether ANOTHER row already wears this id, and
                # an admin sync that recreates a collision undoes the step-2
                # repair as surely as a scheduled one does.
                verdict, holder_id = await stamp_espn_id_if_unheld(
                    db, event, espn_event.espn_id, context="admin sync-espn-live",
                )
                if verdict == STAMPED:
                    changed = True
                elif verdict == REFUSED:
                    id_refusals.append(
                        {"event_id": event.id, "espn_id": espn_event.espn_id,
                         "holder_event_id": holder_id}
                    )

                # Update game clock
                if espn_event.clock and event.game_clock != espn_event.clock:
                    event.game_clock = espn_event.clock
                    changed = True

                # Update period
                if espn_event.status_detail and event.period != espn_event.status_detail:
                    event.period = espn_event.status_detail
                    changed = True

                # Update broadcast info
                if espn_event.broadcasts:
                    broadcast_str = ", ".join(espn_event.broadcasts[:3])
                    if event.broadcast_info != broadcast_str:
                        event.broadcast_info = broadcast_str
                        changed = True

                # Update ESPN win probability
                if espn_event.home_win_probability is not None:
                    event.espn_win_prob_home = espn_event.home_win_probability
                    # Also update win_probability_sources (#1829: stamped like
                    # every other writer). NOTE the pre-existing gotcha #4 here:
                    # this is ORM attribute assignment on a JSONB column, which
                    # can silently fail to flush. Left as-is — changing the
                    # write mechanism on an admin repair path is not this
                    # queue's change — but do not copy this shape.
                    from app.utils.aggregation import stamp_source_reading
                    event.win_probability_sources = stamp_source_reading(
                        event.win_probability_sources,
                        "espn",
                        espn_event.home_win_probability,
                    )
                    changed = True

                # Handle venue
                if espn_event.venue and not event.venue_id:
                    # Check if venue exists
                    venue_result = await db.execute(
                        select(Venue).where(Venue.espn_id == espn_event.venue.espn_id)
                    )
                    venue = venue_result.scalar_one_or_none()

                    if not venue:
                        # Create new venue
                        venue = Venue(
                            name=espn_event.venue.name,
                            city=espn_event.venue.city,
                            state=espn_event.venue.state,
                            country=espn_event.venue.country,
                            capacity=espn_event.venue.capacity,
                            espn_id=espn_event.venue.espn_id,
                        )
                        db.add(venue)
                        await db.flush()

                    event.venue_id = venue.id
                    changed = True

                if changed:
                    updated.append(event.id)

    if not dry_run:
        await db.commit()

    return {
        "status": "success",
        "dry_run": dry_run,
        "sport_key": sport_key,
        "espn_events": len(espn_events),
        "our_events": len(our_events),
        "matched": len(matched),
        "llm_matched_count": len(llm_matched),
        "updated": len(updated) if not dry_run else 0,
        "matches": matched[:15],
        "llm_matches": llm_matched[:10] if llm_matched else [],
        "refused_count": len(refused),
        "refused": refused[:10],
        "espn_id_held_count": len(id_refusals),
        "espn_id_held": id_refusals[:10],
    }


@router.get("/espn/events-status")
async def espn_events_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of ESPN event enrichment.

    Shows how many events have ESPN data (clock, period, venue, win prob).
    """
    _check_admin_secret(secret, request=request)

    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Event.espn_id.isnot(None)).label("with_espn_id"),
            func.count().filter(Event.game_clock.isnot(None)).label("with_clock"),
            func.count().filter(Event.period.isnot(None)).label("with_period"),
            func.count().filter(Event.venue_id.isnot(None)).label("with_venue"),
            func.count().filter(Event.broadcast_info.isnot(None)).label("with_broadcast"),
            func.count().filter(Event.espn_win_prob_home.isnot(None)).label("with_win_prob"),
        )
    )
    row = result.one()

    return {
        "total": row.total,
        "with_espn_id": row.with_espn_id,
        "with_clock": row.with_clock,
        "with_period": row.with_period,
        "with_venue": row.with_venue,
        "with_broadcast": row.with_broadcast,
        "with_win_prob": row.with_win_prob,
    }


@router.post("/espn/match-teams")
async def match_espn_teams(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    our_team_name: str = Query(..., description="Our team name"),
    sport_key: str = Query(..., description="Sport key"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Debug endpoint: Try to match a team name using ESPN + LLM.

    Useful for testing entity resolution before bulk sync.
    """
    _check_admin_secret(secret, request=request)

    from app.services import get_espn_service, llm

    espn = get_espn_service()
    espn_teams = await espn.get_teams(sport_key)

    if espn_teams is None:
        return {
            "status": "authority_dark",
            "message": "ESPN did not answer — no candidates could be scored.",
        }
    if not espn_teams:
        return {"status": "error", "message": "Could not fetch ESPN teams"}

    results = []
    for et in espn_teams:
        espn_name = et.display_name or et.name
        score = llm.match_team_names_cached(our_team_name, espn_name, sport_key) if llm.is_available() else 0.0

        if score >= 0.5:  # Only show likely matches
            results.append({
                "espn_name": espn_name,
                "espn_id": et.espn_id,
                "abbreviation": et.abbreviation,
                "confidence": score,
                "primary_color": et.primary_color,
            })

    # Sort by confidence
    results.sort(key=lambda x: x["confidence"], reverse=True)

    return {
        "query": our_team_name,
        "sport_key": sport_key,
        "espn_teams_searched": len(espn_teams),
        "llm_available": llm.is_available(),
        "matches": results[:10],
    }


@router.get("/espn/task/{task_id}")
async def get_espn_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of an ESPN correction task."""
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


@router.post("/espn/cleanup-bad-matches")
async def cleanup_bad_espn_matches(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Validate existing ESPN ID assignments and clear bad matches.

    Fetches ESPN teams for each sport, compares team names using token-overlap
    scoring, and clears ESPN data (ID, logos, colors) for teams below the
    match threshold. Returns task_id for status checking.
    """
    _check_admin_destructive(secret, request=request)

    from app.tasks import cleanup_bad_espn_matches as task

    result = task.delay()
    return {
        "status": "queued",
        "task_id": result.id,
        "message": "Cleanup task queued. Check status at /api/admin/espn/task/{task_id}",
    }


@router.post("/espn/backfill-boxscores")
async def backfill_box_scores(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    limit: int = Query(100, description="Max events to process"),
    priority: str = Query("recent", description="'recent' (default) or 'calibration' (events with Kalshi props)"),
):
    """
    Backfill ESPN box score data for completed events.

    priority=calibration targets events with Kalshi player prop markets
    needing is_winner resolution first.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import backfill_box_scores as task

    result = task.delay(limit=limit, priority_calibration=(priority == "calibration"))
    return {
        "status": "queued",
        "task_id": result.id,
        "message": f"Box score backfill queued (limit={limit}). Check status at /api/admin/espn/task/{{task_id}}",
    }


@router.post("/espn/clear-unavailable")
async def clear_espn_unavailable(
    request: Request, secret: str = Query(None),
    sport: str = Query(..., description="Sport key prefix to clear (e.g., 'icehockey')"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Clear 'not_available' box_score_data on events so they get retried."""
    _check_admin_secret(secret, request=request)

    result = await db.execute(
        text("""
            UPDATE events e
            SET box_score_data = NULL
            FROM sports s
            WHERE e.sport_id = s.id
              AND s.key LIKE :pattern
              AND e.box_score_data IS NOT NULL
              AND e.box_score_data->>'error' = 'not_available'
        """),
        {"pattern": f"{sport}%"},
    )
    await db.commit()
    return {"cleared": result.rowcount, "sport_pattern": f"{sport}%"}


@router.post("/espn/backfill-ids")
async def backfill_espn_ids(
    request: Request, secret: str = Query(None),
    days: int = Query(0, description="How many days back to scan (0 = all time)"),
    sport: Optional[str] = Query(None, description="Sport key filter (e.g., basketball_nba)"),
    dry_run: bool = Query(True, description="If true, report matches without updating"),
    limit: int = Query(500, description="Max events to process per call"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Retroactively match events to ESPN schedules and set espn_id.

    Scans events that have no espn_id, fetches ESPN's schedule for each
    date, and matches by team names. Set days=0 to scan all time.
    """
    _check_admin_secret(secret, request=request)

    from app.services.espn_api import ESPNAPIService
    from app.utils.sport_keys import ESPN_SPORT_MAPPING
    from app.utils.name_normalization import names_match

    # Find events without ESPN ID
    query = (
        select(Event)
        .options(selectinload(Event.sport))
        .where(
            Event.espn_id.is_(None),
        )
        .order_by(Event.commence_time.desc())
        .limit(limit)
    )
    if days > 0:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        query = query.where(Event.commence_time >= cutoff)
    if sport:
        query = query.where(Event.sport.has(key=sport))

    result = await db.execute(query)
    events = result.scalars().all()

    # Group by sport_key + date for efficient ESPN API calls.
    # ESPN uses US Eastern time for date boundaries, so a 10pm ET game on
    # April 14 = 2am UTC April 15. We must check BOTH UTC date and previous
    # day to catch cross-midnight games.
    from collections import defaultdict
    groups: dict[tuple[str, str], list] = defaultdict(list)
    for event in events:
        if not event.sport:
            continue
        sport_key = event.sport.key
        if sport_key not in ESPN_SPORT_MAPPING:
            continue
        utc_date = event.commence_time.strftime("%Y%m%d")
        prev_date = (event.commence_time - timedelta(days=1)).strftime("%Y%m%d")
        groups[(sport_key, utc_date)].append(event)
        # Also check previous day for late-night US games
        groups[(sport_key, prev_date)].append(event)

    # Fetch ESPN schedules and match
    from app.utils.espn_id_stamp import REFUSED, stamp_espn_id_if_unheld

    espn = ESPNAPIService()
    matched = 0
    scanned = 0
    matches = []
    #: #2049 / gotcha #53 — see the sibling rail above: a refused stamp must be
    #: reported, not folded into "unmatched".
    refused: list[dict] = []
    #: #2693 CERT-784 — the id is already worn by another row. See the sibling
    #: rail above for why this is its own count.
    id_refusals: list[dict] = []

    try:
        for (sport_key, date_str), group_events in groups.items():
            try:
                espn_events = await espn.get_scoreboard(sport_key, date=date_str)
            except Exception:
                continue

            if espn_events is None:
                # AUTHORITY DARK (lane1/045) — reported, not folded into
                # "unmatched", for the same reason a refused stamp is.
                refused.append({
                    "sport_key": sport_key,
                    "date": date_str,
                    "reason": "espn-authority-dark",
                    "events": len(group_events),
                })
                continue

            if not espn_events:
                continue

            for event in group_events:
                scanned += 1

                def _orientation(ee) -> str | None:
                    espn_home = ee.home_team.display_name or ee.home_team.name or ""
                    espn_away = ee.away_team.display_name or ee.away_team.name or ""
                    if (names_match(event.home_team_name, espn_home)
                            and names_match(event.away_team_name, espn_away)):
                        return "normal"
                    if (names_match(event.home_team_name, espn_away)
                            and names_match(event.away_team_name, espn_home)):
                        return "swapped"
                    return None

                # #2049: each (sport, date) group previously took its FIRST name
                # hit and raw-stamped it. Because every event is filed under BOTH
                # its UTC date and the previous day, one event is scanned against
                # two slates — so "first hit" was very often the neighbouring
                # day's game. Nearest candidate, then the same-game gate.
                ee, _reason = select_authorized_espn_candidate(
                    espn_events,
                    event.commence_time,
                    is_name_match=lambda c: _orientation(c) is not None,
                    anchor_espn_id=getattr(event, "espn_id", None),
                )
                if ee is None:
                    if _reason != "no-name-match":
                        refused.append({
                            "event_id": event.id,
                            "our_teams": f"{event.home_team_name} vs {event.away_team_name}",
                            "date": date_str,
                            "sport": sport_key,
                            "reason": _reason,
                        })
                    continue

                espn_home = ee.home_team.display_name or ee.home_team.name or ""
                espn_away = ee.away_team.display_name or ee.away_team.name or ""
                matches.append({
                    "event_id": event.id,
                    "our_teams": f"{event.home_team_name} vs {event.away_team_name}",
                    "espn_teams": f"{espn_home} vs {espn_away}",
                    "espn_id": ee.espn_id,
                    "date": date_str,
                    "sport": sport_key,
                    "orientation": _orientation(ee),
                })

                if not dry_run:
                    # #2693 CERT-784: holder-checked (#2017). See the sibling
                    # writer above — this rail selects on `espn_id IS NULL`, so
                    # every row it touches is one the step-2 repair may just
                    # have cleared, and a raw stamp hands the contested id
                    # straight back.
                    verdict, holder_id = await stamp_espn_id_if_unheld(
                        db, event, ee.espn_id, context="admin backfill-espn-ids",
                    )
                    if verdict == REFUSED:
                        id_refusals.append(
                            {"event_id": event.id, "espn_id": ee.espn_id,
                             "holder_event_id": holder_id}
                        )
                    # Also update win prob if ESPN has it
                    if ee.home_win_probability is not None:
                        event.espn_win_prob_home = ee.home_win_probability
                        # #1829: stamped (same gotcha #4 caveat as the
                        # sibling writer above).
                        from app.utils.aggregation import (
                            stamp_source_reading as _stamp_espn,
                        )
                        event.win_probability_sources = _stamp_espn(
                            event.win_probability_sources,
                            "espn",
                            ee.home_win_probability,
                        )

                matched += 1

        if not dry_run:
            await db.commit()

    finally:
        await espn.close()

    # Collect unmatched events with details
    matched_event_ids = {m["event_id"] for m in matches}
    unmatched = []
    for event in events:
        if event.id not in matched_event_ids and event.sport and event.sport.key in ESPN_SPORT_MAPPING:
            date_str = event.commence_time.strftime("%Y%m%d")
            unmatched.append({
                "event_id": event.id,
                "our_teams": f"{event.home_team_name} vs {event.away_team_name}",
                "sport": event.sport.key,
                "date": date_str,
                "status": event.status,
            })

    return {
        "dry_run": dry_run,
        "days_scanned": days if days > 0 else "all",
        "limit": limit,
        "events_without_espn_id": len(events),
        "events_scanned": scanned,
        "events_matched": matched,
        "match_rate": f"{matched*100/scanned:.1f}%" if scanned else "N/A",
        "matches": matches[:50],
        "unmatched": unmatched[:30],
        "refused_count": len(refused),
        "refused": refused[:20],
        "espn_id_held_count": len(id_refusals),
        "espn_id_held": id_refusals[:20],
    }


# =============================================================================
# Rosters
# =============================================================================


@router.get("/rosters/teams-debug")
async def rosters_teams_debug(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(..., description="Sport key (e.g., 'americanfootball_nfl')"),
    db: AsyncSession = Depends(get_db),
):
    """Debug: show team names, abbreviations, and roster status for a sport."""
    _check_admin_secret(secret, request=request)

    from app.models import Team, Sport

    sport_result = await db.execute(
        select(Sport.id, Sport.key).where(Sport.key == sport_key)
    )
    sport_row = sport_result.first()
    if not sport_row:
        return {"error": f"Sport '{sport_key}' not found"}

    result = await db.execute(
        select(
            Team.id, Team.name, Team.abbreviation, Team.roster_players
        ).where(Team.sport_id == sport_row.id).order_by(Team.name)
    )
    teams = result.all()

    return {
        "sport_key": sport_key,
        "sport_id": sport_row.id,
        "team_count": len(teams),
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "abbreviation": t.abbreviation,
                "roster_count": len(t.roster_players) if t.roster_players else 0,
            }
            for t in teams
        ],
    }


@router.post("/rosters/sync")
async def trigger_roster_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: Optional[str] = Query(None, description="Sport key (e.g., 'basketball_nba'). If omitted, syncs all supported sports."),
):
    """Trigger roster sync from ESPN + MLB Stats API (runs as background Celery task).

    Fetches player rosters and stores them on Team.roster_players for use
    in related-futures player name matching.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_rosters

    task = sync_rosters.delay(sport_key=sport_key)
    return {
        "status": "queued",
        "task_id": task.id,
        "sport_key": sport_key or "all",
        "message": f"Roster sync queued. Use /api/admin/rosters/task/{task.id} to check status.",
    }


@router.get("/rosters/task/{task_id}")
async def get_roster_sync_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of a roster sync task."""
    _check_admin_secret(secret, request=request)

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)

    return response


# =============================================================================
# MLB
# =============================================================================


@router.post("/mlb/sync")
async def trigger_mlb_win_prob_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """
    Trigger a one-off MLB win probability sync.

    Fetches live MLB games from the MLB Stats API and writes win probability
    snapshots for matched events. Normally runs automatically every 2 minutes.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_mlb_win_probability

    try:
        task = sync_mlb_win_probability.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"MLB win probability sync queued. "
                       f"Use /api/admin/mlb/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/mlb/task/{task_id}")
async def get_mlb_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of an MLB sync task."""
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


# =============================================================================
# Odds API Quota
# =============================================================================


@router.get("/odds-api/usage")
async def odds_api_usage(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Current Odds API quota status and hourly history."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_odds_api_quota, get_odds_api_quota_history

    quota = get_odds_api_quota()
    history = get_odds_api_quota_history(hours=720)  # 30 days

    # Compute daily aggregates from hourly data
    daily = {}
    for entry in history:
        day = entry["hour"][:10]
        daily[day] = entry  # Last reading of each day

    daily_usage = []
    sorted_days = sorted(daily.keys())
    for i, day in enumerate(sorted_days):
        used = daily[day]["used"]
        prev_used = daily[sorted_days[i - 1]]["used"] if i > 0 else 0
        delta = used - prev_used
        # Handle month rollover (used resets to 0)
        if delta < 0:
            delta = used
        daily_usage.append({"date": day, "daily_requests": delta, "cumulative": used})

    return {
        "current": quota,
        "daily_usage": daily_usage,
        "hourly_history": history[-168:],  # Last 7 days hourly
    }


@router.get("/odds-api/daily-activity")
async def odds_api_daily_activity(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
    month: int = Query(2, description="Month (1-12)"),
    year: int = Query(2026, description="Year"),
    table: str = Query("odds", description="Table to query: odds, futures, winprob, or all"),
):
    """Infer daily Odds API call volume from snapshot row counts.

    Query one table at a time (table=odds|futures|winprob) to stay within
    Heroku's 30-second timeout, or table=all to try all three.
    """
    _check_admin_secret(secret, request=request)

    from datetime import date

    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    # Set a statement timeout to avoid blocking the DB
    await db.execute(text("SET LOCAL statement_timeout = '25s'"))

    results = {}

    if table in ("odds", "all"):
        try:
            odds_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows,
                       COUNT(DISTINCT event_id) AS events
                FROM odds_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["odds"] = [
                {"date": str(r.day), "rows": r.rows, "events": r.events}
                for r in odds_q.all()
            ]
        except Exception as e:
            results["odds_error"] = str(e)

    if table in ("futures", "all"):
        try:
            futures_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows,
                       COUNT(DISTINCT outcome_id) AS outcomes
                FROM futures_odds_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["futures"] = [
                {"date": str(r.day), "rows": r.rows, "outcomes": r.outcomes}
                for r in futures_q.all()
            ]
        except Exception as e:
            results["futures_error"] = str(e)

    if table in ("winprob", "all"):
        try:
            wp_q = await db.execute(text("""
                SELECT captured_at::date AS day,
                       COUNT(*) AS rows
                FROM win_prob_snapshots
                WHERE captured_at >= :start AND captured_at < :end
                GROUP BY 1 ORDER BY 1
            """), {"start": start, "end": end})
            results["winprob"] = [
                {"date": str(r.day), "rows": r.rows}
                for r in wp_q.all()
            ]
        except Exception as e:
            results["winprob_error"] = str(e)

    return {
        "month": f"{year}-{month:02d}",
        "table_filter": table,
        **results,
    }


# =============================================================================
# StatPal
# =============================================================================


@router.get("/statpal/usage")
async def statpal_usage(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Current StatPal API usage and daily history."""
    _check_admin_secret(secret, request=request)

    from app.tasks.redis_state import get_statpal_usage, get_statpal_usage_history

    daily_limit = 300_000
    current = get_statpal_usage()
    history = get_statpal_usage_history(days=90)

    # Add percentage and health status
    if current.get("request_count") is not None:
        count = current["request_count"]
        pct = round(count / daily_limit * 100, 1)
        current["daily_limit"] = daily_limit
        current["pct_used"] = pct
        current["health"] = "critical" if pct > 80 else "warning" if pct > 50 else "healthy"

    return {
        "current": current,
        "daily_history": history,
    }


#: The two facts the ledger needs from the table itself, per sport. Kept beside
#: the endpoint because it is one query with one purpose: the banked row says
#: what the pass believed, and this says what the table holds now. When they
#: disagree, something outside the stamper wrote a StatPal anchor — which is a
#: finding, and it is invisible if only one of the two numbers is published.
_ANCHOR_CENSUS = """
SELECT COUNT(*) AS anchors,
       COUNT(*) FILTER (
           WHERE a.source_id = :prefix || e.statpal_fixture_id
       ) AS column_agrees
  FROM event_provider_anchors a
  JOIN events e ON e.id = a.event_id
 WHERE a.source = 'statpal'
   AND a.id_kind = 'game'
   AND a.source_id LIKE :like_prefix
"""

#: Two of our rows holding one StatPal id. The unique anchor index already makes
#: this impossible for two ANCHORED rows, so a hit here is a row whose column
#: was written by something that did not write an anchor.
_DUPLICATE_IDS = """
SELECT COUNT(*) AS duplicate_ids
  FROM (
        SELECT e.statpal_fixture_id
          FROM events e
          JOIN sports s ON s.id = e.sport_id
         WHERE s.key = :sport_key
           AND e.statpal_fixture_id IS NOT NULL
         GROUP BY e.statpal_fixture_id
        HAVING COUNT(*) > 1
       ) d
"""

#: The same census for a measurement population, whose rows are spread over MANY
#: `sports.key`s (`authority_agreement.MEASUREMENT_POPULATIONS`).
#:
#: Not `_DUPLICATE_IDS` with a wildcard bound in, for two separate reasons and
#: both of them bite:
#:
#:   * `s.key = :sport_key` matches nothing at all for `tennis_singles`, because
#:     no row carries that key. The census would publish a confident 0.
#:   * Binding `:sport_key` into a `LIKE` would make every real sport key a
#:     PATTERN — `baseball_mlb` has an underscore, which `LIKE` reads as
#:     "any one character" — so a scope named after one sport could silently
#:     widen to another. The prefix is written literally here instead.
#:
#: Duplicates split ACROSS keys are the shape tennis actually has: 1,170 pairs
#: appearing twice within five days sit under two different `sports.key`s
#: (production 2026-09-05). A per-key census cannot see one — the partition key
#: is inside the grouping key — which is why this one does not partition.
_DUPLICATE_IDS_TENNIS = """
SELECT COUNT(*) AS duplicate_ids
  FROM (
        SELECT e.statpal_fixture_id
          FROM events e
          JOIN sports s ON s.id = e.sport_id
         WHERE s.key LIKE 'tennis%'
           AND e.statpal_fixture_id IS NOT NULL
         GROUP BY e.statpal_fixture_id
        HAVING COUNT(*) > 1
       ) d
"""


@router.get("/statpal/authority-agreement")
async def statpal_authority_agreement(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """The agreement row bus bucket `M-R-AUTHORITY` reads. #2867 / D50, step 2.

    **SHIP: the seven-day count that gates whether StatPal may ever become a
    source of record can start, because the number it counts is published here
    instead of re-derived by hand every morning.**

    D50: *nothing user-visible flips without a measured 7-day ≥99.5% agreement
    row from the bus AND a YOUR-TURN entry Alex has seen.* The row's shape is
    fixed by `.claude/handoff/ARTIFACT-AUTHORITY-LEDGER-SPEC.md`; the numbers
    are computed by `app/utils/authority_agreement` inside the shadow stamper,
    which is the one moment both sides of the comparison are in hand at once.

    Precedent D46: the calibration lane moved its scoring into the app and
    published it, and the bus stopped running the script. Same move. A script
    that re-asks StatPal an hour after the stamper did is comparing two
    different afternoons and spending quota to do it.

    THREE THINGS THIS ENDPOINT DOES NOT DO
    ══════════════════════════════════════
    It does not call StatPal — it publishes the banked pass, so reading it is
    free and repeatable. It does not decide anything: `identity` governs the
    flip, `schedule` and `anchors` are reported and gate nothing, and no bucket
    is ever blended into another (spec rule 2). And it does not hide its own
    staleness: `pass_age_seconds` and `last_pass_at` are on every sport, because
    a row from yesterday's pass answers a question about yesterday.

    The `gate` string is `FLIP_GATE_SUMMARY`, imported rather than written here.
    Which of identity's two numbers scores a sport is a PER-SPORT ruling (D63),
    so the summary sends its reader to that sport's `identity.governing` instead
    of naming a number — the payload's opening sentence is the last place a
    reader should be pointed at the wrong one.
    """
    _check_admin_secret(secret, request=request)

    from app.config.authority_by_sport import (
        STATPAL,
        SWITCH_IS_WIRED,
        SWITCH_WIRING_NOTE,
        authority_for,
    )
    from app.tasks.redis_state import get_task_metrics
    from app.utils.authority_agreement import (
        FLIP_GATE_SUMMARY,
        MEASUREMENT_POPULATIONS,
        SHADOW_STAMPERS,
    )
    from app.utils.provider_anchor_keys import statpal_id_space

    now = datetime.now(timezone.utc)
    sports = []

    for sport_key, task_name in sorted(SHADOW_STAMPERS.items()):
        entry: dict = {"sport_key": sport_key, "stamper": task_name}

        # Read from `app/config/authority_by_sport`, never restated here. The
        # whole value of a one-line switch is that there is one line; a second
        # copy in a route is a second answer, and this endpoint is where a
        # reader comes to ask whether anything has flipped yet.
        entry["authority"] = {
            "current": authority_for(sport_key),
            "candidate": STATPAL,
            "note": (
                "the sport's source of record TODAY. The agreement row below "
                "measures the candidate; it does not select it. Flipping needs "
                "`config.authority_by_sport.flip_permitted` to say yes on seven "
                "consecutive daily gate states AND a YOUR-TURN entry Alex has "
                "seen (D50)."
            ),
            # Beside `current`, never folded into its note, because it qualifies
            # what `current` MEANS rather than adding detail to it. NFL/NBA/NHL
            # reach a genuine seven around 2026-09-11; on that day someone flips
            # a line, watches `current` change, and would otherwise conclude the
            # site had changed provider. It has not: nothing reads the switch.
            # Derived from the declared consumer set, so it cannot outlive the
            # condition it describes (`SWITCH_CONSUMERS`).
            "switch_wired": SWITCH_IS_WIRED,
            "switch_note": SWITCH_WIRING_NOTE,
        }

        metrics = get_task_metrics(task_name) or {}
        summary = metrics.get("last_result_summary") or {}
        # A task banks either ONE row under `agreement` or SEVERAL under
        # `agreements`, keyed by population — the tennis linker measures two
        # draws in one pass and neither may be published as "the" row. The plural
        # is read first and by key, so a task that grows a second population
        # cannot have one of them silently stand in for the other.
        agreements = summary.get("agreements") if isinstance(summary, dict) else None
        if isinstance(agreements, dict):
            agreement = agreements.get(sport_key)
        else:
            agreement = summary.get("agreement") if isinstance(summary, dict) else None
        last_at = metrics.get("last_success_at")

        entry["last_pass_at"] = last_at
        entry["pass_age_seconds"] = None
        if last_at:
            try:
                entry["pass_age_seconds"] = int(
                    (now - datetime.fromisoformat(last_at)).total_seconds()
                )
            except (TypeError, ValueError):
                # An unparseable stamp is not "fresh" and is not "old" — it is a
                # broken stamp, and guessing either way would publish a
                # confident wrong age. Left None, with the raw value above.
                pass

        if agreement:
            entry["agreement"] = agreement
        else:
            # NOT an empty row and NOT zero agreement. The stamper has not
            # banked one since the deploy that started banking them, and saying
            # so is the whole of gotcha #53: "it returned" is not "it worked".
            entry["agreement"] = None
            entry["note"] = (
                f"no agreement row banked by {task_name} yet — this is 'not "
                f"measured', not 'measured and disagreed'. It appears after the "
                f"next pass."
            )

        prefix = statpal_id_space(sport_key)
        entry["live"] = {"anchor_prefix": prefix}
        if sport_key in MEASUREMENT_POPULATIONS:
            # The agreement numbers above ARE split by draw; the census below is
            # not, and cannot be. StatPal numbers singles and doubles in one
            # sequence, so an id-space census has no draw to filter on — the
            # anchors it counts belong to both. Said on the row rather than left
            # to be inferred, because the two halves of this entry are now
            # scoped differently and nothing else on it would say so.
            entry["live"]["scope_note"] = (
                "counted over the whole `tennis:` id space — both draws. StatPal "
                "numbers singles and doubles in one sequence, so this census "
                "cannot be split the way the agreement numbers above are; it is "
                "the same figure on both tennis rows."
            )
        if prefix:
            census = (
                await db.execute(
                    text(_ANCHOR_CENSUS),
                    {"prefix": f"{prefix}:", "like_prefix": f"{prefix}:%"},
                )
            ).first()
            if sport_key in MEASUREMENT_POPULATIONS:
                dupes = (await db.execute(text(_DUPLICATE_IDS_TENNIS))).first()
            else:
                dupes = (
                    await db.execute(text(_DUPLICATE_IDS), {"sport_key": sport_key})
                ).first()
            anchors = int(census[0] or 0) if census else 0
            agrees = int(census[1] or 0) if census else 0
            entry["live"].update(
                {
                    "anchors": anchors,
                    "column_agrees": agrees,
                    # An anchor whose column no longer matches reads as STALE on
                    # every lookup (`anchor_channel.anchor_is_current`), so it
                    # resolves nothing while looking like a link.
                    "half_links": anchors - agrees,
                    "duplicate_ids": int(dupes[0] or 0) if dupes else 0,
                }
            )

        sports.append(entry)

    return {
        "generated_at": now.isoformat(),
        "spec": ".claude/handoff/ARTIFACT-AUTHORITY-LEDGER-SPEC.md",
        # Imported, never re-typed here: the summary names the four gate states,
        # and a copy of those names living in a route file is a copy that keeps
        # saying MEETS after the constant stops.
        "gate": FLIP_GATE_SUMMARY,
        "sports": sports,
    }


@router.post("/statpal/sync-schedules")
async def trigger_statpal_schedule_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key (e.g., basketball_nba). If omitted, syncs all."),
):
    """
    Trigger a StatPal schedule/fixture sync.

    Fetches fixtures from StatPal, corrects commence_time errors from The Odds API,
    populates end_time for finished games, and stores StatPal fixture IDs for
    play-by-play lookups.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_schedules

    try:
        task = sync_statpal_schedules.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal schedule sync queued{f' for {sport_key}' if sport_key else ' (all sports)'}. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/statpal/probe-endpoints")
async def statpal_probe_endpoints(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport: str = Query("nba", description="StatPal sport"),
):
    """Probe StatPal with different endpoints/params to find playoff schedules."""
    _check_admin_secret(secret, request=request)

    from app.services.statpal_api import StatPalAPIService, is_available
    if not is_available():
        return {"error": "StatPal API key not configured"}

    svc = StatPalAPIService()
    results = {}

    probes = [
        ("season-schedule (default)", "season-schedule", {}),
        ("season-schedule (season=2025-2026)", "season-schedule", {"season": "2025-2026"}),
        ("season-schedule (season=2026)", "season-schedule", {"season": "2026"}),
        ("season-schedule (season=playoffs)", "season-schedule", {"season": "playoffs"}),
        ("season-schedule (season=postseason)", "season-schedule", {"season": "postseason"}),
        ("fixtures (no params)", "fixtures", {}),
        ("schedule (no params)", "schedule", {}),
        ("upcoming-schedule", "upcoming-schedule", {}),
        ("season-schedule (date=2026-05-11)", "season-schedule", {"date": "2026-05-11"}),
        ("daily-schedule", "daily-schedule", {}),
        ("daily-schedule (date=today)", "daily-schedule", {"date": "2026-05-11"}),
        ("games", "games", {}),
        ("games/today", "games/today", {}),
        ("results", "results", {}),
        ("matches", "matches", {}),
        ("events", "events", {}),
        ("playoff-schedule", "playoff-schedule", {}),
        ("postseason-schedule", "postseason-schedule", {}),
        ("playoffs", "playoffs", {}),
    ]

    now = datetime.now(timezone.utc)

    # Grab RAW JSON to see if playoffs are present but dropped by parser
    raw_data = await svc._get(sport, "season-schedule", {})
    raw_debug = {}
    if raw_data and isinstance(raw_data, dict):
        raw_debug["top_keys"] = list(raw_data.keys())[:10]
        # Drill into scores -> tournament structure
        scores = raw_data.get("scores")
        if isinstance(scores, dict):
            raw_debug["scores_keys"] = list(scores.keys())[:10]
            tournament = scores.get("tournament")
            if isinstance(tournament, dict):
                raw_debug["tournament_type"] = "dict"
                raw_debug["tournament_keys"] = list(tournament.keys())[:10]
                matches = tournament.get("match", [])
                raw_debug["match_count"] = len(matches) if isinstance(matches, list) else "not_a_list"
                raw_debug["tournament_league"] = tournament.get("league")
                raw_debug["tournament_season"] = tournament.get("season")
                raw_debug["tournament_id"] = tournament.get("id")
                raw_debug["tournament_country"] = tournament.get("country")
                raw_debug["tournament_week"] = tournament.get("week")
            elif isinstance(tournament, list):
                raw_debug["tournament_type"] = "LIST"
                raw_debug["tournament_count"] = len(tournament)
                for i, t in enumerate(tournament[:5]):
                    if isinstance(t, dict):
                        league = t.get("league", "?")
                        match_count = len(t.get("match", [])) if isinstance(t.get("match"), list) else "?"
                        raw_debug[f"tournament_{i}"] = {
                            "league": league,
                            "match_count": match_count,
                            "keys": list(t.keys())[:8],
                        }
            else:
                raw_debug["tournament_type"] = type(tournament).__name__ if tournament else "missing"

    for label, endpoint, params in probes:
        try:
            data = await svc._get(sport, endpoint, params)
            if data is None:
                results[label] = {"status": "null/error", "count": 0}
                continue
            fixtures = svc._parse_fixtures(data, sport)
            future = [f for f in fixtures if f.start_time and f.start_time > now]
            latest = max((f.start_time for f in fixtures if f.start_time), default=None)
            results[label] = {
                "status": "ok",
                "total": len(fixtures),
                "future": len(future),
                "latest_date": latest.isoformat()[:10] if latest else None,
                "sample_future": [
                    {"home": f.home_team, "away": f.away_team,
                     "time": f.start_time.isoformat()[:16] if f.start_time else None}
                    for f in future[:5]
                ],
            }
        except Exception as e:
            results[label] = {"status": f"error: {str(e)[:100]}", "count": 0}

    results["_raw_debug"] = raw_debug
    return results


@router.get("/statpal/fixture-debug")
async def statpal_fixture_debug(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport: str = Query("nba", description="StatPal sport (nba, nhl, mlb)"),
):
    """Show raw StatPal fixture data to debug date parsing."""
    _check_admin_secret(secret, request=request)

    from app.services.statpal_api import StatPalAPIService, is_available
    if not is_available():
        return {"error": "StatPal API key not configured"}

    svc = StatPalAPIService()
    fixtures = await svc.get_fixtures(sport)

    now = datetime.now(timezone.utc)
    none_count = sum(1 for f in fixtures if f.start_time is None)
    future = [f for f in fixtures if f.start_time and f.start_time > now]
    past_week = [f for f in fixtures if f.start_time and (now - f.start_time).days < 7 and f.start_time <= now]

    return {
        "total_fixtures": len(fixtures),
        "with_start_time": len(fixtures) - none_count,
        "without_start_time": none_count,
        "future_fixtures": len(future),
        "past_week_fixtures": len(past_week),
        "sample_future": [
            {"home": f.home_team, "away": f.away_team,
             "start_time": f.start_time.isoformat() if f.start_time else None,
             "status": f.status, "fixture_id": f.fixture_id}
            for f in future[:10]
        ],
        "sample_none_time": [
            {"home": f.home_team, "away": f.away_team,
             "fixture_id": f.fixture_id, "status": f.status}
            for f in fixtures[:5] if f.start_time is None
        ][:5],
        "date_range": {
            "earliest": min((f.start_time for f in fixtures if f.start_time), default=None),
            "latest": max((f.start_time for f in fixtures if f.start_time), default=None),
        } if fixtures else {},
        "sample_all": [
            {"home": f.home_team, "away": f.away_team,
             "start_time": f.start_time.isoformat() if f.start_time else None,
             "fixture_id": f.fixture_id, "status": f.status}
            for f in fixtures[-5:]
        ],
    }


@router.post("/statpal/sync-injuries")
async def trigger_statpal_injury_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key (e.g., basketball_nba). If omitted, syncs all."),
):
    """
    Trigger a StatPal injury report sync.

    Fetches injury reports and attaches them to upcoming/live events for
    "Why Did the Line Move?" context.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_injuries

    try:
        task = sync_statpal_injuries.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal injury sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/statpal/sync-plays")
async def trigger_statpal_play_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key. If omitted, syncs all live games."),
):
    """
    Trigger a StatPal play-by-play sync for live games.

    Fetches recent plays from live games to provide context for probability
    movements and Pulse calculations.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_live_plays

    try:
        task = sync_statpal_live_plays.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal play-by-play sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.post("/statpal/sync-rosters")
async def trigger_statpal_roster_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Sport key. If omitted, syncs all."),
):
    """
    Trigger a StatPal roster sync (supplements ESPN roster data).

    Only updates teams that don't already have roster data from ESPN.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_rosters

    try:
        task = sync_statpal_rosters.delay(sport_key=sport_key)
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"StatPal roster sync queued. "
                       f"Use /api/admin/statpal/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/statpal/task/{task_id}")
async def get_statpal_task_status(
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of a StatPal sync task."""
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


@router.get("/statpal/status")
async def statpal_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check StatPal integration status -- API key configured, sport mapping, etc."""
    _check_admin_secret(secret, request=request)

    from app.services.statpal_api import is_available
    from app.tasks.config import STATPAL_SPORT_MAPPING

    return {
        "api_key_configured": is_available(),
        "mapped_sports": list(STATPAL_SPORT_MAPPING.keys()),
        "endpoints": {
            "sync_schedules": "POST /api/admin/statpal/sync-schedules",
            "sync_injuries": "POST /api/admin/statpal/sync-injuries",
            "sync_plays": "POST /api/admin/statpal/sync-plays",
            "sync_rosters": "POST /api/admin/statpal/sync-rosters",
            "sync_standings": "POST /api/admin/statpal/sync-standings",
            "sync_team_stats": "POST /api/admin/statpal/sync-team-stats",
            "task_status": "GET /api/admin/statpal/task/{task_id}",
        },
    }


@router.post("/statpal/sync-standings")
async def trigger_statpal_standings_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Optional: limit to one sport key"),
):
    """Trigger StatPal standings sync (daily task, runs at 8:00 AM UTC)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_standings

    try:
        task = sync_statpal_standings.delay(sport_key=sport_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {e}")
    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Standings sync queued. "
                   f"Use /api/admin/statpal/task/{task.id} to check status.",
    }


@router.post("/statpal/sync-team-stats")
async def trigger_statpal_team_stats_sync(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Optional: limit to one sport key"),
):
    """Trigger StatPal team stats sync (weekly task, runs Monday 9:00 AM UTC)."""
    _check_admin_secret(secret, request=request)

    from app.tasks import sync_statpal_team_stats

    try:
        task = sync_statpal_team_stats.delay(sport_key=sport_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {e}")
    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Team stats sync queued. "
                   f"Use /api/admin/statpal/task/{task.id} to check status.",
    }


# =============================================================================
# DataGolf
# =============================================================================


@router.post("/datagolf/poll")
async def trigger_datagolf_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Manually trigger DataGolf market polling (runs inline, not via Celery queue).

    The worker only has 2 concurrency slots permanently occupied by
    high-frequency tasks, so Celery .delay() would queue but never execute.
    """
    _check_admin_secret(secret, request=request)

    from app.tasks.datagolf import _poll_datagolf_markets
    try:
        result = await _poll_datagolf_markets()
        return {"status": "completed", "result": result}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}


@router.post("/datagolf/poll-live")
async def trigger_datagolf_live_poll(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Manually trigger DataGolf live in-play polling (runs inline)."""
    _check_admin_secret(secret, request=request)

    from app.tasks.datagolf import _poll_datagolf_live
    try:
        result = await _poll_datagolf_live()
        return {"status": "completed", "result": result}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:500]}


@router.get("/datagolf/debug-schedule")
async def datagolf_debug_schedule(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Fetch raw DataGolf schedule for field name discovery."""
    _check_admin_secret(secret, request=request)

    from app.services.datagolf_api import DataGolfAPIService
    service = DataGolfAPIService()
    try:
        data = await service._get("get-schedule", {"tour": "pga"})
        schedule = data.get("schedule", [])
        sample = schedule[:3] if schedule else []
        return {
            "top_level_keys": list(data.keys()),
            "schedule_count": len(schedule),
            "sample_entries": sample,
            "all_keys_first_entry": list(schedule[0].keys()) if schedule else [],
        }
    except Exception as exc:
        return {"error": str(exc)[:500]}
    finally:
        await service.close()


@router.get("/datagolf/status")
async def datagolf_status(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check DataGolf integration status: markets, outcomes, live flags."""
    _check_admin_secret(secret, request=request)

    # Count DataGolf markets
    market_result = await db.execute(
        select(func.count(FuturesMarket.id)).where(
            FuturesMarket.source == "datagolf"
        )
    )
    total_markets = market_result.scalar() or 0

    # Count open DataGolf markets
    open_result = await db.execute(
        select(func.count(FuturesMarket.id)).where(
            FuturesMarket.source == "datagolf",
            FuturesMarket.status == "open",
        )
    )
    open_markets = open_result.scalar() or 0

    # Count outcomes across DataGolf markets
    outcome_result = await db.execute(
        select(func.count(FuturesOutcome.id)).where(
            FuturesOutcome.market_id.in_(
                select(FuturesMarket.id).where(FuturesMarket.source == "datagolf")
            )
        )
    )
    total_outcomes = outcome_result.scalar() or 0

    # Count snapshots (last 24h)
    snap_result = await db.execute(
        select(func.count(FuturesOddsSnapshot.id)).where(
            FuturesOddsSnapshot.bookmaker == "datagolf_model",
            FuturesOddsSnapshot.captured_at >= datetime.now(timezone.utc) - timedelta(hours=24),
        )
    )
    recent_snapshots = snap_result.scalar() or 0

    # Check Redis live flags
    live_tours = {}
    try:
        from app.tasks.redis_state import get_redis_client
        from app.tasks.datagolf import LIVE_KEY_PREFIX, POLL_TOURS
        r = get_redis_client()
        for tour in POLL_TOURS:
            key = f"{LIVE_KEY_PREFIX}:{tour}"
            live_tours[tour] = r.exists(key) == 1
    except Exception:
        live_tours = {"error": "Redis unavailable"}

    # Get latest DataGolf markets with metadata
    latest_result = await db.execute(
        select(FuturesMarket)
        .where(FuturesMarket.source == "datagolf", FuturesMarket.status == "open")
        .order_by(FuturesMarket.id.desc())
        .limit(10)
    )
    latest_markets = []
    for m in latest_result.scalars().all():
        entry = {
            "id": m.id,
            "name": m.name,
            "external_id": m.external_id,
            "category": m.category,
        }
        if m.market_metadata:
            entry["tour"] = m.market_metadata.get("tour")
            entry["course"] = m.market_metadata.get("course")
            entry["has_leaderboard"] = "leaderboard" in m.market_metadata
            entry["round_history_count"] = len(m.market_metadata.get("round_history", []))
        latest_markets.append(entry)

    return {
        "total_markets": total_markets,
        "open_markets": open_markets,
        "total_outcomes": total_outcomes,
        "recent_snapshots_24h": recent_snapshots,
        "live_tours": live_tours,
        "latest_markets": latest_markets,
    }


@router.get("/odds-api/sport-polling-status")
async def sport_polling_status(
    request: Request, secret: str = Query(None),
):
    """Live polling status for each sport — shows 404 caches, adaptive slowdown, and skip reasons."""
    if not _check_admin_secret(secret, request=request):
        return {"error": "unauthorized"}

    from datetime import datetime, timezone
    from app.tasks.redis_state import get_redis_client
    from app.tasks.config import (
        SPORT_POLLING_TIERS, SPORT_POLLING_DEFAULT_TIER,
        SPORT_TIER_MULTIPLIERS, SPORT_REGION_OVERRIDES,
    )
    from app.utils.sport_keys import SPORT_LEAGUE_MAP

    r = get_redis_client()
    if not r:
        return {"error": "redis_unavailable"}

    now_ts = datetime.now(timezone.utc).timestamp()
    sports = []
    for sport_key in sorted(SPORT_LEAGUE_MAP.keys()):
        tier = SPORT_POLLING_TIERS.get(sport_key, SPORT_POLLING_DEFAULT_TIER)
        multiplier = SPORT_TIER_MULTIPLIERS.get(tier, 4)

        is_404 = bool(r.get(f"bainluck:sport_404:{sport_key}"))

        last_poll_raw = r.get(f"bainluck:last_poll:{sport_key}")
        last_poll_ago = round(now_ts - float(last_poll_raw.decode())) if last_poll_raw else None

        unchanged_raw = r.get(f"bainluck:unchanged_count:{sport_key}")
        unchanged_count = int(unchanged_raw.decode()) if unchanged_raw else 0

        region_override = SPORT_REGION_OVERRIDES.get(sport_key)

        status = "active"
        if is_404:
            status = "404_cached"
        elif last_poll_ago is None:
            status = "never_polled"
        elif last_poll_ago > 7200:
            status = "stale"

        sports.append({
            "sport": sport_key,
            "tier": tier,
            "multiplier": f"{multiplier}x",
            "status": status,
            "is_404_cached": is_404,
            "last_poll_seconds_ago": last_poll_ago,
            "unchanged_count": unchanged_count,
            "region_override": region_override,
            "effective_live_interval_s": 32 * multiplier,
        })

    cached_404 = [s for s in sports if s["is_404_cached"]]

    return {
        "total_sports": len(sports),
        "active": len([s for s in sports if s["status"] == "active"]),
        "cached_404": len(cached_404),
        "stale": len([s for s in sports if s["status"] == "stale"]),
        "never_polled": len([s for s in sports if s["status"] == "never_polled"]),
        "cached_404_sports": [s["sport"] for s in cached_404],
        "sports": sports,
    }
