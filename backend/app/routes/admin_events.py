"""Admin endpoints for event CRUD, dedup, merging, game state, and scheduling."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket
from app.models.models import LineMovementAnalysis
from app.services import get_db
from app.routes.admin_utils import _check_admin_secret

router = APIRouter()


# =============================================================================
# Event CRUD
# =============================================================================


@router.post("/events/create")
async def create_event_manually(
    secret: str = Query(..., description="Admin secret for authorization"),
    home_team: str = Query(..., description="Home team name (e.g., 'USA', 'Canada')"),
    away_team: str = Query(..., description="Away team name"),
    sport_key: str = Query(..., description="Sport key (e.g., 'icehockey_olympics')"),
    sport_name: Optional[str] = Query(None, description="Sport display name (auto-generated if omitted)"),
    commence_time: Optional[str] = Query(None, description="ISO 8601 timestamp (defaults to now)"),
    status: str = Query("live", description="Event status: scheduled, live, completed, closed"),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually create an Event for sports that The Odds API doesn't cover.

    Useful for Olympics, special events, or any sport where events need to
    exist for prediction market linking.

    After creating, use POST /api/admin/prediction-markets/link to connect
    prediction markets, or trigger the matching task to auto-link.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models.models import Sport

    # Parse commence_time
    ct = datetime.now(timezone.utc)
    if commence_time:
        try:
            ct = datetime.fromisoformat(commence_time)
            if ct.tzinfo is None:
                ct = ct.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid commence_time: {commence_time}")

    # Get or create Sport record
    sport_result = await db.execute(
        select(Sport).where(Sport.key == sport_key)
    )
    sport = sport_result.scalar_one_or_none()
    if not sport:
        display_name = sport_name or sport_key.replace("_", " ").title()
        group = sport_key.split("_")[0].title() if "_" in sport_key else display_name
        sport = Sport(key=sport_key, name=display_name, group=group, active=True)
        db.add(sport)
        await db.flush()

    # Check for duplicate
    existing = await db.execute(
        select(Event).where(
            Event.home_team_name == home_team,
            Event.away_team_name == away_team,
            Event.status.in_(["scheduled", "live"]),
        ).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Event already exists for {home_team} vs {away_team}",
        )

    # Create event
    external_id = f"manual_{sport_key}_{home_team}_{away_team}_{int(ct.timestamp())}"
    event = Event(
        sport_id=sport.id,
        external_id=external_id,
        home_team_name=home_team,
        away_team_name=away_team,
        commence_time=ct,
        status=status,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    return {
        "status": "created",
        "event_id": event.id,
        "external_id": event.external_id,
        "home_team": home_team,
        "away_team": away_team,
        "sport_key": sport_key,
        "commence_time": ct.isoformat(),
        "event_status": status,
        "url": f"https://bainluck.com/events/{event.id}",
        "next_step": f"Link prediction markets: POST /api/admin/prediction-markets/link?market_id=XXX&event_id={event.id}&secret=...",
    }


@router.patch("/events/{event_id}")
async def patch_event(
    event_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    home_team: Optional[str] = Query(None, description="New home team name"),
    away_team: Optional[str] = Query(None, description="New away team name"),
    status: Optional[str] = Query(None, description="New status"),
    db: AsyncSession = Depends(get_db),
):
    """Patch an event's fields (admin only)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    updates = {}
    if home_team is not None:
        event.home_team_name = home_team
        updates["home_team"] = home_team
    if away_team is not None:
        event.away_team_name = away_team
        updates["away_team"] = away_team
    if status is not None:
        event.status = status
        updates["status"] = status

    await db.commit()
    return {"event_id": event_id, "updated": updates}


@router.post("/fix-live-statuses")
async def fix_live_statuses(
    secret: str = Query(..., description="Admin secret for authorization"),
    dry_run: bool = Query(False, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db),
):
    """Fix events incorrectly stuck in 'live' status.

    Resets events to 'scheduled' if they are marked 'live' but their
    commence_time is more than 1 hour in the future (clearly haven't started).
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=1)  # Buffer for clock drift

    # Find events marked live but with future commence_time
    result = await db.execute(
        select(Event).where(
            Event.status == "live",
            Event.commence_time > cutoff,
        )
    )
    bad_events = result.scalars().all()

    if dry_run:
        return {
            "dry_run": True,
            "events_to_fix": len(bad_events),
            "samples": [
                {
                    "id": e.id,
                    "external_id": e.external_id[:60] if e.external_id else None,
                    "home_team": e.home_team_name,
                    "away_team": e.away_team_name,
                    "commence_time": e.commence_time.isoformat() if e.commence_time else None,
                    "status": e.status,
                }
                for e in bad_events[:20]
            ],
        }

    # Fix them
    fixed_count = 0
    for event in bad_events:
        event.status = "scheduled"
        fixed_count += 1

    await db.commit()

    return {
        "fixed": fixed_count,
        "message": f"Reset {fixed_count} events from 'live' to 'scheduled'",
    }


# =============================================================================
# Event Backfill
# =============================================================================


@router.post("/events/backfill-game-state")
async def backfill_game_state(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max events to process"),
    sport: Optional[str] = Query(None, description="Sport key filter (e.g., 'baseball_mlb', 'basketball')"),
):
    """
    Backfill missing game state (period markers) for completed events.

    Finds completed/closed events with no period data in ScoringPlay table
    and reconstructs from ESPNSnapshot period data or score progression.
    Writes markers as WinProbSnapshot records with game_state.period so the
    history endpoint's existing fallback logic picks them up.

    Run with sport=baseball_mlb first (most impactful), then without filter
    for all sports. Safe to run multiple times -- skips events that already
    have data.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_game_state as task

    result = task.delay(limit=limit, sport_filter=sport)
    return {
        "status": "queued",
        "task_id": result.id,
        "message": (
            f"Game state backfill queued (limit={limit}, sport={sport or 'all'}). "
            f"Check status at /api/admin/events/task/{{task_id}}"
        ),
    }


@router.get("/events/task/{task_id}")
async def get_event_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of an event backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app

    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.result)
    return response


@router.get("/events/creation-lead-time")
async def event_creation_lead_time(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport: str = Query("basketball_nba", description="Sport key"),
    days: int = Query(14, description="Look back N days"),
    db: AsyncSession = Depends(get_db),
):
    """How far in advance are Tier 1 events created before their commence_time?"""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from sqlalchemy import text as _text

    await db.execute(_text("SET LOCAL statement_timeout = '15s'"))

    result = await db.execute(_text("""
        SELECT
            e.id,
            e.home_team_name,
            e.away_team_name,
            e.commence_time,
            e.created_at,
            e.status,
            e.external_id,
            e.statpal_fixture_id,
            e.commence_time_source,
            EXTRACT(EPOCH FROM (e.commence_time - e.created_at)) / 3600 AS lead_hours
        FROM events e
        JOIN sports s ON e.sport_id = s.id
        WHERE s.key = :sport
          AND e.commence_time > NOW() - make_interval(days => :days_back)
          AND e.created_at IS NOT NULL
          AND e.commence_time IS NOT NULL
        ORDER BY e.commence_time DESC
        LIMIT 50
    """), {"sport": sport, "days_back": days})
    rows = result.all()

    events = []
    for r in rows:
        events.append({
            "id": r.id,
            "matchup": f"{r.away_team_name} vs {r.home_team_name}",
            "commence": r.commence_time.isoformat()[:16] if r.commence_time else None,
            "created": r.created_at.isoformat()[:16] if r.created_at else None,
            "lead_hours": round(r.lead_hours, 1) if r.lead_hours else None,
            "status": r.status,
            "source": r.commence_time_source,
            "has_odds_api": r.external_id is not None,
            "has_statpal": r.statpal_fixture_id is not None,
        })

    lead_hours = [e["lead_hours"] for e in events if e["lead_hours"] is not None]
    return {
        "sport": sport,
        "events_analyzed": len(events),
        "lead_time_stats": {
            "min_hours": round(min(lead_hours), 1) if lead_hours else None,
            "max_hours": round(max(lead_hours), 1) if lead_hours else None,
            "median_hours": round(sorted(lead_hours)[len(lead_hours) // 2], 1) if lead_hours else None,
            "avg_hours": round(sum(lead_hours) / len(lead_hours), 1) if lead_hours else None,
            "under_6h": sum(1 for h in lead_hours if h < 6),
            "under_24h": sum(1 for h in lead_hours if h < 24),
            "under_48h": sum(1 for h in lead_hours if h < 48),
        },
        "events": events,
    }


# =============================================================================
# Duplicate Detection and Merging
# =============================================================================


@router.delete("/events/delete-duplicates")
async def delete_duplicate_events(
    secret: str = Query(...),
    event_ids: str = Query(..., description="Comma-separated event IDs to delete"),
    db: AsyncSession = Depends(get_db),
):
    """Delete specific duplicate events with FK cleanup."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    ids = [int(x.strip()) for x in event_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return {"error": "No valid event IDs provided"}

    # Clean up FKs
    fk_tables = [
        "odds_snapshots", "odds_aggregated", "win_prob_snapshots",
        "espn_snapshots", "score_snapshots", "scoring_plays",
        "line_movement_analyses",
    ]
    for table in fk_tables:
        await db.execute(text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"), {"ids": ids})

    await db.execute(text("UPDATE futures_markets SET event_id = NULL WHERE event_id = ANY(:ids)"), {"ids": ids})
    await db.execute(text("UPDATE user_pins SET target_id = NULL WHERE pin_type = 'event' AND target_id = ANY(:ids)"), {"ids": ids})

    result = await db.execute(text("DELETE FROM events WHERE id = ANY(:ids)"), {"ids": ids})
    await db.commit()

    return {"deleted": result.rowcount, "event_ids": ids}


@router.get("/events/duplicates")
async def list_duplicate_events(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Find duplicate events: same sport, same teams, same date."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(text("""
        WITH dupes AS (
            SELECT a.id AS id_a, b.id AS id_b
            FROM events a
            JOIN events b ON (
                a.sport_id = b.sport_id
                AND a.id < b.id
                AND LOWER(a.home_team_name) = LOWER(b.home_team_name)
                AND LOWER(a.away_team_name) = LOWER(b.away_team_name)
                AND ABS(EXTRACT(EPOCH FROM (a.commence_time - b.commence_time))) < 21600
            )
            WHERE a.commence_time > NOW() - INTERVAL '30 days'
              AND b.commence_time > NOW() - INTERVAL '30 days'
            LIMIT 100
        )
        SELECT
            a.id AS event_a_id, a.external_id AS event_a_external_id,
            EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = a.id LIMIT 1) AS event_a_has_snaps,
            a.statpal_fixture_id AS event_a_statpal,
            a.commence_time_source AS event_a_source,
            a.status AS event_a_status,
            b.id AS event_b_id, b.external_id AS event_b_external_id,
            EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = b.id LIMIT 1) AS event_b_has_snaps,
            b.statpal_fixture_id AS event_b_statpal,
            b.commence_time_source AS event_b_source,
            b.status AS event_b_status,
            s.key AS sport_key,
            a.home_team_name, a.away_team_name,
            a.commence_time AS commence_a,
            b.commence_time AS commence_b
        FROM dupes d
        JOIN events a ON a.id = d.id_a
        JOIN events b ON b.id = d.id_b
        JOIN sports s ON s.id = a.sport_id
        ORDER BY a.commence_time DESC
    """))
    rows = result.all()

    duplicates = []
    for row in rows:
        duplicates.append({
            "event_a": {
                "id": row.event_a_id,
                "external_id": row.event_a_external_id,
                "has_snapshots": row.event_a_has_snaps,
                "statpal_fixture_id": row.event_a_statpal,
                "commence_time_source": row.event_a_source,
                "status": row.event_a_status,
            },
            "event_b": {
                "id": row.event_b_id,
                "external_id": row.event_b_external_id,
                "has_snapshots": row.event_b_has_snaps,
                "statpal_fixture_id": row.event_b_statpal,
                "commence_time_source": row.event_b_source,
                "status": row.event_b_status,
            },
            "sport": row.sport_key,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "commence_a": row.commence_a.isoformat() if row.commence_a else None,
            "commence_b": row.commence_b.isoformat() if row.commence_b else None,
        })

    return {
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
    }


@router.post("/events/merge-duplicates")
async def merge_duplicate_events(
    secret: str = Query(...),
    dry_run: bool = Query(True, description="Preview without making changes"),
):
    """Queue a Celery task to merge duplicate events.

    Runs in background to avoid Heroku 30s timeout.
    Check status with GET /api/admin/events/merge-task/{task_id}
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import merge_duplicate_events_task
    task = merge_duplicate_events_task.delay(dry_run=dry_run)
    return {
        "status": "queued",
        "task_id": task.id,
        "dry_run": dry_run,
        "message": f"Merge task queued ({'dry run' if dry_run else 'LIVE'}). Check /api/admin/events/merge-task/{task.id}",
    }


@router.post("/events/merge-duplicates-sql")
async def merge_duplicate_events_sql(
    secret: str = Query(...),
    dry_run: bool = Query(True, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db),
):
    """Merge duplicate events: find orphans, clear FK refs, then delete."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Step 1: Find keeper-orphan pairs
    result = await db.execute(text("""
        SELECT
            keeper.id AS keeper_id, orphan.id AS orphan_id,
            orphan.statpal_fixture_id, orphan.commence_time_source,
            orphan.statpal_end_time, orphan.home_team_id,
            orphan.away_team_id, orphan.espn_id
        FROM events keeper
        JOIN events orphan ON (
            keeper.sport_id = orphan.sport_id
            AND keeper.id != orphan.id
            AND LOWER(keeper.home_team_name) = LOWER(orphan.home_team_name)
            AND LOWER(keeper.away_team_name) = LOWER(orphan.away_team_name)
            AND ABS(EXTRACT(EPOCH FROM (keeper.commence_time - orphan.commence_time))) < 21600
        )
        WHERE keeper.commence_time > NOW() - INTERVAL '30 days'
          AND orphan.commence_time > NOW() - INTERVAL '30 days'
          AND NOT EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = orphan.id LIMIT 1)
          AND (
              -- Case A: keeper has external_id, orphan doesn't
              (keeper.external_id IS NOT NULL AND orphan.external_id IS NULL)
              OR
              -- Case B: both NULL, keep lowest ID
              (keeper.external_id IS NULL AND orphan.external_id IS NULL AND keeper.id < orphan.id)
          )
    """))
    pairs = result.all()

    if dry_run:
        return {"dry_run": True, "would_merge": len(pairs)}

    orphan_ids = [row.orphan_id for row in pairs]
    if not orphan_ids:
        return {"dry_run": False, "merged": 0, "deleted": 0}

    try:
        # Step 2: Absorb metadata per keeper
        for row in pairs:
            set_clauses = []
            params = {"kid": row.keeper_id}
            fields = [
                ("statpal_fixture_id", row.statpal_fixture_id),
                ("commence_time_source", row.commence_time_source),
                ("statpal_end_time", row.statpal_end_time),
                ("home_team_id", row.home_team_id),
                ("away_team_id", row.away_team_id),
                ("espn_id", row.espn_id),
            ]
            for i, (field, value) in enumerate(fields):
                if value is not None:
                    set_clauses.append(f"{field} = COALESCE({field}, :v{i})")
                    params[f"v{i}"] = value
            if set_clauses:
                await db.execute(
                    text(f"UPDATE events SET {', '.join(set_clauses)} WHERE id = :kid"),
                    params,
                )

        # Step 3: Clear ALL FK references to orphans before deleting
        fk_tables = [
            "odds_snapshots",
            "odds_aggregated",
            "score_snapshots",
            "line_movement_analyses",
        ]
        for table in fk_tables:
            await db.execute(
                text(f"DELETE FROM {table} WHERE event_id = ANY(:ids)"),
                {"ids": orphan_ids},
            )
        # futures_markets has nullable event_id -- NULL it instead of deleting
        await db.execute(
            text("UPDATE futures_markets SET event_id = NULL WHERE event_id = ANY(:ids)"),
            {"ids": orphan_ids},
        )

        # Step 4: Now delete orphan events (CASCADE handles espn/win_prob snapshots)
        await db.execute(
            text("DELETE FROM events WHERE id = ANY(:ids)"),
            {"ids": orphan_ids},
        )

        await db.commit()
        return {
            "dry_run": False,
            "merged": len(pairs),
            "deleted": len(orphan_ids),
        }
    except Exception as e:
        await db.rollback()
        import traceback
        return {
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc()[-2000:],
            "orphan_ids": orphan_ids[:10],
            "pairs_count": len(pairs),
        }


@router.get("/events/merge-task/{task_id}")
async def check_merge_task(
    task_id: str,
    secret: str = Query(...),
):
    """Check status of a merge-duplicates background task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from celery.result import AsyncResult
    from app.tasks import celery_app
    result = AsyncResult(task_id, app=celery_app)
    response = {
        "task_id": task_id,
        "state": result.state,
    }
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.post("/merge-events")
async def merge_events_admin(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger the duplicate event merger (runs in non-dry-run mode)."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Unauthorized")

    from app.tasks.sports import _merge_duplicate_events_impl
    result = await _merge_duplicate_events_impl(dry_run=False)
    return result


# =============================================================================
# Line Movement Cache
# =============================================================================


@router.delete("/line-movement/cache/{event_id}")
async def clear_line_movement_cache(
    event_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Delete cached line movement explanations for an event so they regenerate."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    result = await db.execute(
        select(LineMovementAnalysis).where(
            LineMovementAnalysis.event_id == event_id,
            LineMovementAnalysis.analysis_type == "line_movement",
        )
    )
    rows = result.scalars().all()
    for row in rows:
        await db.delete(row)
    await db.commit()

    return {"deleted": len(rows), "event_id": event_id}


# =============================================================================
# Market Lookup
# =============================================================================


@router.get("/market-lookup")
async def market_lookup(
    secret: str = Query(...),
    ticker: str = Query(None),
    name: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Look up futures markets by external_id prefix or name pattern."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    query = select(
        FuturesMarket.id, FuturesMarket.external_id, FuturesMarket.name,
        FuturesMarket.status, FuturesMarket.source, FuturesMarket.market_tier,
        FuturesMarket.llm_sport_category,
    )
    if ticker:
        query = query.where(FuturesMarket.external_id.ilike(f"{ticker}%"))
    elif name:
        query = query.where(FuturesMarket.name.ilike(f"%{name}%"))
    else:
        raise HTTPException(status_code=400, detail="Provide ticker or name")
    query = query.limit(20)
    result = await db.execute(query)
    return [
        {"id": r.id, "external_id": r.external_id, "name": r.name,
         "status": r.status, "source": r.source, "tier": r.market_tier,
         "category": r.llm_sport_category}
        for r in result.all()
    ]


# =============================================================================
# Schedule Accuracy
# =============================================================================


@router.get("/schedule/accuracy")
async def schedule_accuracy(
    secret: str = Query(..., description="Admin secret for authorization"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Per-sport breakdown of commence_time_source to audit date accuracy."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Sport

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # Get per-sport breakdown of commence_time_source
    result = await db.execute(
        select(
            Sport.key,
            Event.commence_time_source,
            func.count(Event.id).label("count"),
        )
        .join(Sport, Event.sport_id == Sport.id)
        .where(Event.commence_time >= cutoff)
        .group_by(Sport.key, Event.commence_time_source)
        .order_by(Sport.key, Event.commence_time_source)
    )
    rows = result.all()

    # Aggregate by sport
    sports: dict[str, dict] = {}
    for row in rows:
        sport_key = row.key
        source = row.commence_time_source or "null"
        count = row.count

        if sport_key not in sports:
            sports[sport_key] = {"total": 0, "sources": {}}
        sports[sport_key]["total"] += count
        sports[sport_key]["sources"][source] = count

    # Calculate reliability ratings
    for sport_key, data in sports.items():
        total = data["total"]
        espn_count = data["sources"].get("espn", 0)
        statpal_count = data["sources"].get("statpal", 0)
        null_count = data["sources"].get("null", 0)
        corrected = espn_count + statpal_count
        corrected_pct = round(corrected / total * 100, 1) if total > 0 else 0
        null_pct = round(null_count / total * 100, 1) if total > 0 else 0

        if corrected_pct >= 80:
            rating = "HIGH"
        elif corrected_pct >= 40:
            rating = "MEDIUM"
        else:
            rating = "LOW"

        data["corrected_pct"] = corrected_pct
        data["uncorrected_pct"] = null_pct
        data["reliability"] = rating

    # Sort by reliability (LOW first to surface problems)
    reliability_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    sorted_sports = dict(
        sorted(
            sports.items(),
            key=lambda item: (reliability_order.get(item[1].get("reliability", "LOW"), 3), item[0])
        )
    )

    return {
        "period_days": days,
        "sports": sorted_sports,
        "summary": {
            "total_sports": len(sorted_sports),
            "high_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "HIGH"),
            "medium_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "MEDIUM"),
            "low_reliability": sum(1 for s in sorted_sports.values() if s.get("reliability") == "LOW"),
        },
    }
