"""Admin endpoints for event CRUD, dedup, merging, game state, and scheduling."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket
from app.models.models import LineMovementAnalysis
from app.services import get_db, get_db_rw
from app.routes.admin_utils import _check_admin_destructive, _check_admin_secret
from app.tasks.prune_unanchored_duplicates import (
    DEFAULT_MAX_DELETE,
    MAX_DELETE_CEILING,
    PruneRefused,
    prune,
)
from app.utils.event_absorption_guard import assert_absorbable_now
from app.utils.event_merge_invariant import assert_mergeable, shared_provider_id_sql

router = APIRouter()


# =============================================================================
# Event CRUD
# =============================================================================


@router.post("/events/create")
async def create_event_manually(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    home_team: str = Query(..., description="Home team name (e.g., 'USA', 'Canada')"),
    away_team: str = Query(..., description="Away team name"),
    sport_key: str = Query(..., description="Sport key (e.g., 'icehockey_olympics')"),
    sport_name: Optional[str] = Query(None, description="Sport display name (auto-generated if omitted)"),
    commence_time: Optional[str] = Query(None, description="ISO 8601 timestamp (defaults to now)"),
    status: str = Query("live", description="Event status: scheduled, live, completed, closed"),
    db: AsyncSession = Depends(get_db_rw),
):
    """
    Manually create an Event for sports that The Odds API doesn't cover.

    Useful for Olympics, special events, or any sport where events need to
    exist for prediction market linking.

    After creating, use POST /api/admin/prediction-markets/link to connect
    prediction markets, or trigger the matching task to auto-link.
    """
    _check_admin_secret(secret, request=request)

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
        from app.utils.sport_keys import sport_display_name

        display_name = sport_name or sport_display_name(sport_key)
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
    request: Request,
    event_id: int,
    secret: str = Query(None, description="Admin secret for authorization"),
    home_team: Optional[str] = Query(None, description="New home team name"),
    away_team: Optional[str] = Query(None, description="New away team name"),
    status: Optional[str] = Query(None, description="New status"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Patch an event's fields (admin only)."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    dry_run: bool = Query(False, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Fix events incorrectly stuck in 'live' status.

    Resets events to 'scheduled' if they are marked 'live' but their
    commence_time is more than 1 hour in the future (clearly haven't started).
    """
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
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
    _check_admin_secret(secret, request=request)

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
    request: Request,
    task_id: str,
    secret: str = Query(None, description="Admin secret for authorization"),
):
    """Check the status of an event backfill task."""
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


@router.get("/events/creation-lead-time")
async def event_creation_lead_time(
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    sport: str = Query("basketball_nba", description="Sport key"),
    days: int = Query(14, description="Look back N days"),
    db: AsyncSession = Depends(get_db),
):
    """How far in advance are Tier 1 events created before their commence_time?"""
    _check_admin_secret(secret, request=request)

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
    request: Request, secret: str = Query(None),
    event_ids: str = Query(..., description="Comma-separated event IDs to delete"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Delete specific duplicate events with FK cleanup."""
    _check_admin_destructive(secret, request=request)

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


@router.post("/events/prune-unanchored-duplicates")
async def prune_unanchored_duplicates_endpoint(
    request: Request,
    secret: str = Query(None),
    sport_id: int = Query(..., description="Required. The partition is per-sport."),
    linked_copies: int = Query(
        1, ge=0, le=99,
        description="Fixtures with exactly this many futures-linked copies. "
                    "1 = Tranche A (the only prunable shape).",
    ),
    apply: bool = Query(False, description="DEFAULT FALSE. True deletes."),
    max_delete: int = Query(DEFAULT_MAX_DELETE, ge=1, le=MAX_DELETE_CEILING),
    expected_min: Optional[int] = Query(None, description="Required when apply=true"),
    expected_max: Optional[int] = Query(None, description="Required when apply=true"),
    plan_hash: Optional[str] = Query(
        None,
        description="Required when apply=true. The content address the dry run "
                    "returned over its exact ordered id set.",
    ),
    db: AsyncSession = Depends(get_db_rw),
):
    """#2020 — the bounded delete rail for the unanchored-duplicate surplus.

    Dry-run by default and readable with the ordinary admin secret, because a census
    an operator cannot take is a census nobody checks. ``apply`` additionally
    requires the destructive token, an expected band, AND the dry run's ``plan_hash``.

    Queue 382 stopped an authorized 61,000-row delete because this endpoint did not
    exist and the only available rail took a bare id list with no dry-run, no census
    and no cap. This is the shape that authorization actually described.

    **REBUILT queue 386 after ``C-DELETE-RAIL-PRE`` returned BLOCK and Alex voided all
    31 attended applies.** The band was the whole authorization and a band bounds
    CARDINALITY — every one of the six findings was about IDENTITY. ``plan_hash`` is
    the identity half: the dry run publishes a content address over its complete
    ordered id set, apply requires it, and the rail re-derives it inside the locked
    transaction. A count-preserving row swap between review and apply now refuses.
    """
    _check_admin_secret(secret, request=request)
    if apply:
        _check_admin_destructive(request=request)

    try:
        result = await prune(
            db,
            sport_id=sport_id,
            linked_copies=linked_copies,
            apply=apply,
            max_delete=max_delete,
            expected_min=expected_min,
            expected_max=expected_max,
            plan_hash=plan_hash,
        )
    except PruneRefused as exc:
        # A refusal is a 409, not a 500: the rail worked correctly and declined.
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if apply and result.get("terminal") == "complete":
        await db.commit()
    else:
        # Nothing should be pending on a non-apply path; rolling back makes that a
        # guarantee rather than a reading of the code above.
        await db.rollback()

    return result


@router.post("/events/reconcile-unanchored")
async def reconcile_unanchored_events_endpoint(
    request: Request,
    secret: str = Query(None),
    apply: bool = Query(False),
    limit: int = Query(1000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db_rw),
):
    """#1798 / ruling 048 — run the reconciliation drain and return its verdict.

    The scheduled beat is the ongoing rail; this is how a person gets a dated
    reading on demand, which is what a HELD gate written in verdict form needs.
    ``apply`` DELETEs and is therefore gated on the destructive check, not merely
    the read secret.
    """
    _check_admin_secret(secret, request=request)
    if apply:
        _check_admin_destructive(request=request)

    from app.tasks.reconcile_unanchored_events import reconcile, summarize_for_operator

    result = await reconcile(db, apply=apply, limit=limit)
    if apply:
        await db.commit()
    return {**result, "operator_line": summarize_for_operator(result)}


@router.get("/events/duplicates")
async def list_duplicate_events(
    request: Request, secret: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Find duplicate events: same sport, same teams, same date."""
    _check_admin_secret(secret, request=request)

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

    # ── Ruling 048 provenance meter ────────────────────────────────────
    # 048 declares rising duplicates a BOUNDED cost, bounded because id-keyed
    # reconciliation drains them. A declared cost with no meter is just a
    # regression with a good story, so the boundedness gets measured here:
    # how many rows the id-less path created, and how many of those are still
    # un-reconciled (created unanchored AND still holding no provider id).
    #
    # gotcha #53: an empty read and a broken read must not render identically.
    # `measured` is what separates "nothing to report" from "the meter did not
    # run", so a zero below is only trustworthy when measured is true.
    meter: dict = {"measured": False, "reason": None}
    try:
        m = (await db.execute(text("""
            SELECT
              COUNT(*) FILTER (
                WHERE event_tags @> '["provenance:unanchored"]'::jsonb
              ) AS created_unanchored,
              COUNT(*) FILTER (
                WHERE event_tags @> '["provenance:unanchored"]'::jsonb
                  AND external_id IS NULL
                  AND espn_id IS NULL
                  AND statpal_fixture_id IS NULL
              ) AS unreconciled,
              COUNT(*) FILTER (
                WHERE event_tags @> '["provenance:unanchored"]'::jsonb
                  AND (external_id IS NOT NULL OR espn_id IS NOT NULL
                       OR statpal_fixture_id IS NOT NULL)
              ) AS anchored,
              COUNT(*) AS window_events
            FROM events
            WHERE commence_time > NOW() - INTERVAL '30 days'
        """))).first()
        meter = {
            "measured": True,
            "reason": None,
            "window": "30d",
            # Rows the id-less create path produced (ruling 048's declared cost).
            "created_unanchored": m.created_unanchored or 0,
            # Of those, the ones an id has since reached.
            #
            # ⚠️ THIS FIELD WAS CALLED `reconciled` AND ITS COMMENT SAID "the drain
            # working". Both were wrong, in the way gotcha #145 describes: an id
            # ARRIVING and a duplicate being DRAINED are different events, and this
            # SQL only ever observed the first. It counts rows still present in
            # `events` that happen to hold an id — a drained row is DELETED and can
            # never appear in this count at all, so the field could not have
            # measured drains even in principle. It read **299** while the drain
            # had absorbed **zero** pairs, and 299 was reported as reconciliation
            # succeeding (queue 387, Fable directive 2026-08-21).
            "anchored": m.anchored or 0,
            # Drains are not derivable from this table for the reason above. The
            # honest value is "ask the task", and saying so beats a plausible zero.
            "drained": None,
            "drained_source": (
                "GET /api/admin/task-metrics?task=reconcile_unanchored_events "
                "— its `reconciled` field IS drains"
            ),
            # DEPRECATED ALIAS, retained ONLY so `flow_sentinel`'s
            # `reconciled_delta` keeps reading across the rename. It carries the
            # `anchored` value, which is what it always carried. Delete it once the
            # sentinel reads `anchored`; do not build anything new on it.
            "reconciled": m.anchored or 0,
            "reconciled_deprecated": (
                "alias of `anchored`; it never meant drains — see gotcha #145"
            ),
            # Of those, the ones still anonymous — the OUTSTANDING cost. This is
            # the number that must not grow without bound; if it climbs while
            # `reconciled` stays flat, reconciliation is not draining.
            "unreconciled": m.unreconciled or 0,
            "window_events": m.window_events or 0,
        }
    except Exception as exc:  # pragma: no cover - defensive
        # Never let the meter take the endpoint down, but never let it report a
        # confident zero either — say plainly that it could not measure.
        meter = {"measured": False, "reason": str(exc)[:200]}

    return {
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "provenance_meter": meter,
    }


@router.post("/events/merge-duplicates")
async def merge_duplicate_events(
    request: Request, secret: str = Query(None),
    dry_run: bool = Query(True, description="Preview without making changes"),
):
    """Queue a Celery task to merge duplicate events.

    Runs in background to avoid Heroku 30s timeout.
    Check status with GET /api/admin/events/merge-task/{task_id}
    """
    _check_admin_secret(secret, request=request)

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
    request: Request, secret: str = Query(None),
    dry_run: bool = Query(True, description="Preview without making changes"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Merge duplicate events: find orphans, clear FK refs, then delete.

    R6 (#1801, codex ``C-CERT-1801-R5``): this endpoint is the SECOND live rail
    that could absorb an id-less row, and it was the more direct of the two —
    exact team names inside six hours, with **no id requirement at all**. Its
    Case A ("keeper has an external_id, orphan does not") and Case B ("both
    NULL, keep the lowest id") are not identity tests; they are tie-breaks
    applied to a pair whose sameness was never established. Codex's
    doubleheader specimen — game 1 at 13:05 anchored, game 2 at 18:35 id-less —
    is selected by Case A directly, and game 2 is deleted.

    The invariant now comes from ``app/utils/event_merge_invariant.py`` for the
    same reason the drain's does: one definition, used by every rail that can
    destroy a row, re-asserted in Python immediately before the delete.
    """
    _check_admin_destructive(secret, request=request)

    # Step 1: Find keeper-orphan pairs
    result = await db.execute(text(f"""
        SELECT
            keeper.id AS keeper_id, orphan.id AS orphan_id,
            keeper.external_id AS keeper_external_id,
            keeper.espn_id AS keeper_espn_id,
            keeper.statpal_fixture_id AS keeper_statpal_fixture_id,
            orphan.external_id AS orphan_external_id,
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
            -- Ruling 048, from the one place it is defined. Everything above is
            -- name + window, which is precisely what does NOT establish identity.
            AND {shared_provider_id_sql("keeper", "orphan")}
        )
        WHERE keeper.commence_time > NOW() - INTERVAL '30 days'
          AND orphan.commence_time > NOW() - INTERVAL '30 days'
          AND NOT EXISTS(SELECT 1 FROM odds_snapshots WHERE event_id = orphan.id LIMIT 1)
          AND keeper.id < orphan.id
    """))
    pairs = result.all()

    # Re-assert on the rows in hand, before anything is destroyed.
    for row in pairs:
        assert_mergeable(
            {"external_id": row.keeper_external_id, "espn_id": row.keeper_espn_id,
             "statpal_fixture_id": row.keeper_statpal_fixture_id, "id": row.keeper_id},
            {"external_id": row.orphan_external_id, "espn_id": row.espn_id,
             "statpal_fixture_id": row.statpal_fixture_id, "id": row.orphan_id},
            context="merge_duplicate_events_sql",
        )

    if dry_run:
        return {"dry_run": True, "would_merge": len(pairs)}

    orphan_ids = [row.orphan_id for row in pairs]
    if not orphan_ids:
        return {"dry_run": False, "merged": 0, "deleted": 0}

    try:
        # #1947: both arms, re-read FOR UPDATE inside this transaction, for every
        # pair, BEFORE the batch delete below. This rail's SELECT also carries a
        # `< 21600` window; that number is now the invariant's, not this query's,
        # and a hand-edit here can no longer remove the protection.
        for row in pairs:
            await assert_absorbable_now(
                db, keep_id=row.keeper_id, orphan_id=row.orphan_id,
                context="merge_duplicate_events_sql",
            )

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
    request: Request, secret: str = Query(None),
):
    """Check status of a merge-duplicates background task."""
    _check_admin_secret(secret, request=request)

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
    request: Request, secret: str = Query(None),
    db: AsyncSession = Depends(get_db_rw),
):
    """Manually trigger the duplicate event merger (runs in non-dry-run mode)."""
    _check_admin_secret(secret, request=request)

    from app.tasks.sports import _merge_duplicate_events_impl
    result = await _merge_duplicate_events_impl(dry_run=False)
    return result


# =============================================================================
# Line Movement Cache
# =============================================================================


@router.delete("/line-movement/cache/{event_id}")
async def clear_line_movement_cache(
    request: Request,
    event_id: int,
    secret: str = Query(None, description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db_rw),
):
    """Delete cached line movement explanations for an event so they regenerate."""
    _check_admin_destructive(secret, request=request)

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
    request: Request, secret: str = Query(None),
    ticker: str = Query(None),
    name: str = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Look up futures markets by external_id prefix or name pattern."""
    _check_admin_secret(secret, request=request)

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
    request: Request,
    secret: str = Query(None, description="Admin secret for authorization"),
    days: int = Query(30, description="Look back period in days"),
    db: AsyncSession = Depends(get_db),
):
    """Per-sport source coverage for the admin Matching page.

    Two distinct dimensions, kept separate on purpose because they used to be
    conflated (which produced fake "0% Odds API" alarms):

    1. ``sources`` — TRUE source LINKAGE: how many events actually carry each
       source's external id (``external_id``=Odds API, ``espn_id``, ``statpal_fixture_id``).
       This is what "is this event linked to Odds API?" really means. An event can
       (and usually does) link to several sources at once, so these counts overlap.

    2. ``commence_time_sources`` — the distribution of ``commence_time_source``,
       i.e. which single highest-priority source won the race to set the event's
       start time (ESPN > StatPal > Odds API > prediction markets). This is a
       data-provenance audit, NOT a linkage measure: any event ESPN touches shows
       ``commence_time_source='espn'`` even when ``external_id`` is also set, which
       is why reading it as "Odds API coverage" wrongly reports ~0% for every
       ESPN-covered league.
    """
    _check_admin_secret(secret, request=request)

    from app.models import Sport

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)

    # --- Dimension 1: TRUE source linkage (id columns NOT NULL) -------------
    linkage_result = await db.execute(
        select(
            Sport.key,
            func.count(Event.id).label("total"),
            func.count(Event.external_id).label("odds_api"),
            func.count(Event.espn_id).label("espn"),
            func.count(Event.statpal_fixture_id).label("statpal"),
        )
        .join(Sport, Event.sport_id == Sport.id)
        .where(Event.commence_time >= cutoff)
        .group_by(Sport.key)
    )

    sports: dict[str, dict] = {}
    for row in linkage_result.all():
        sports[row.key] = {
            "total": row.total,
            # "sources" = linkage counts (what the UI labels "Odds API / ESPN / StatPal")
            "sources": {
                "odds_api": row.odds_api,
                "espn": row.espn,
                "statpal": row.statpal,
            },
            "commence_time_sources": {},
        }

    # --- Dimension 2: commence_time_source provenance (single value/event) ---
    cts_result = await db.execute(
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
    for row in cts_result.all():
        sport_key = row.key
        if sport_key not in sports:
            sports[sport_key] = {
                "total": 0,
                "sources": {"odds_api": 0, "espn": 0, "statpal": 0},
                "commence_time_sources": {},
            }
        sports[sport_key]["commence_time_sources"][row.commence_time_source or "null"] = row.count

    # Reliability rating is based on TRUE Odds API linkage (the sportsbook source
    # that drives event pages), not on who set the commence_time.
    for sport_key, data in sports.items():
        total = data["total"]
        odds_api_count = data["sources"].get("odds_api", 0)
        linked_pct = round(odds_api_count / total * 100, 1) if total > 0 else 0

        if linked_pct >= 80:
            rating = "HIGH"
        elif linked_pct >= 40:
            rating = "MEDIUM"
        else:
            rating = "LOW"

        data["odds_api_linked_pct"] = linked_pct
        data["reliability"] = rating

    # Sort by reliability (LOW first to surface genuine problems)
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
