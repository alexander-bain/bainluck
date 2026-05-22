"""Admin endpoints for team management, team identity, and futures team linking."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FuturesMarket, FuturesOutcome
from app.services import get_db
from app.routes.admin_utils import _check_admin_secret

router = APIRouter()


# =============================================================================
# Team Management
# =============================================================================


@router.post("/teams/backfill-logos")
async def trigger_team_logo_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """
    Manually trigger team logo backfill from ESPN's /teams endpoint.

    Fetches all teams for supported leagues and fills in missing logos.
    Queues as a background Celery task and returns immediately.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_logos

    try:
        task = backfill_team_logos.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": "Team logo backfill task queued. Check /api/admin/teams/task/{task_id} for results.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/teams/task/{task_id}")
async def get_team_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a team logo backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

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


@router.post("/teams/merge")
async def merge_duplicate_team(
    secret: str = Query(...),
    source_id: int = Query(..., description="Team ID to merge FROM (duplicate, will be deleted)"),
    target_id: int = Query(..., description="Team ID to merge INTO (canonical, will be kept)"),
    db: AsyncSession = Depends(get_db),
):
    """Merge a duplicate team into the canonical one. Reassigns all FKs then deletes the duplicate."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team

    # Verify both teams exist
    source = await db.get(Team, source_id)
    target = await db.get(Team, target_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Source team {source_id} not found")
    if not target:
        raise HTTPException(status_code=404, detail=f"Target team {target_id} not found")

    # Reassign all FKs from source to target
    fk_updates = [
        "UPDATE events SET home_team_id = :target WHERE home_team_id = :source",
        "UPDATE events SET away_team_id = :target WHERE away_team_id = :source",
        "UPDATE futures_outcomes SET team_id = :target WHERE team_id = :source",
        "UPDATE user_favorites SET team_id = :target WHERE team_id = :source",
        "UPDATE team_identity_mapping SET team_id = :target WHERE team_id = :source",
    ]
    counts = {}
    for sql in fk_updates:
        table = sql.split("UPDATE ")[1].split(" SET")[0]
        result = await db.execute(text(sql), {"source": source_id, "target": target_id})
        counts[table] = result.rowcount

    # Delete the duplicate
    await db.execute(text("DELETE FROM teams WHERE id = :source"), {"source": source_id})
    await db.commit()

    return {
        "merged": f"{source.name} (id={source_id}) -> {target.name} (id={target_id})",
        "fk_updates": counts,
        "deleted_team_id": source_id,
    }


@router.post("/teams/add-alias")
async def add_team_alias(
    secret: str = Query(...),
    team_id: int = Query(...),
    alias: str = Query(..., description="Alias to add to alternate_names"),
    db: AsyncSession = Depends(get_db),
):
    """Add an alias to a team's alternate_names list."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team
    team = await db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail=f"Team {team_id} not found")

    current = team.alternate_names or []
    if alias not in current:
        current.append(alias)
        team.alternate_names = current
        await db.commit()

    return {"team_id": team_id, "name": team.name, "alternate_names": current}


# =============================================================================
# Team Identity
# =============================================================================


@router.get("/team-identity/status")
async def team_identity_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Count mappings by source, total mapped teams, unmapped teams."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import TeamIdentityMapping, Team

    # Count by source
    source_counts = await db.execute(
        select(TeamIdentityMapping.source, func.count(TeamIdentityMapping.id))
        .group_by(TeamIdentityMapping.source)
    )
    by_source = {row[0]: row[1] for row in source_counts.all()}

    # Total mapped team IDs
    mapped_count = await db.execute(
        select(func.count(func.distinct(TeamIdentityMapping.team_id)))
    )
    total_mapped = mapped_count.scalar() or 0

    # Total teams
    total_teams = await db.execute(select(func.count(Team.id)))
    total = total_teams.scalar() or 0

    return {
        "total_teams": total,
        "mapped_teams": total_mapped,
        "unmapped_teams": total - total_mapped,
        "mappings_by_source": by_source,
        "total_mappings": sum(by_source.values()),
    }


@router.post("/team-identity/backfill")
async def trigger_team_identity_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Trigger one-time backfill of team identity mappings from existing data."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_identities
    try:
        task = backfill_team_identities.delay()
        return {
            "status": "queued",
            "task_id": task.id,
            "message": f"Team identity backfill queued. "
                       f"Use /api/admin/team-identity/task/{task.id} to check status.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue task: {str(e)}")


@router.get("/team-identity/task/{task_id}")
async def team_identity_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check team identity task status."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import celery_app as app
    result = app.AsyncResult(task_id)
    response = {"task_id": task_id, "state": result.state}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("/team-identity/search")
async def team_identity_search(
    q: str = Query(..., description="Search query for team name"),
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Search team identity mappings across all sources."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import TeamIdentityMapping, Team

    result = await db.execute(
        select(TeamIdentityMapping, Team.name).join(
            Team, TeamIdentityMapping.team_id == Team.id,
        ).where(
            or_(
                TeamIdentityMapping.source_name.ilike(f"%{q}%"),
                TeamIdentityMapping.source_abbreviation.ilike(f"%{q}%"),
                TeamIdentityMapping.source_id.ilike(f"%{q}%"),
            )
        ).order_by(Team.name).limit(50)
    )

    rows = result.all()
    return {
        "query": q,
        "count": len(rows),
        "results": [
            {
                "mapping_id": mapping.id,
                "team_id": mapping.team_id,
                "team_name": team_name,
                "source": mapping.source,
                "source_id": mapping.source_id,
                "source_name": mapping.source_name,
                "source_abbreviation": mapping.source_abbreviation,
                "sport_key": mapping.sport_key,
            }
            for mapping, team_name in rows
        ],
    }


@router.get("/team-identity/team/{team_id}")
async def team_identity_detail(
    team_id: int,
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """All identity mappings for a specific team."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import TeamIdentityMapping, Team

    # Get team info
    team_result = await db.execute(select(Team).where(Team.id == team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Get mappings
    mapping_result = await db.execute(
        select(TeamIdentityMapping).where(
            TeamIdentityMapping.team_id == team_id,
        ).order_by(TeamIdentityMapping.source)
    )
    mappings = mapping_result.scalars().all()

    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "abbreviation": team.abbreviation,
            "espn_id": team.espn_id,
            "alternate_names": team.alternate_names,
        },
        "mappings": [
            {
                "id": m.id,
                "source": m.source,
                "source_id": m.source_id,
                "source_name": m.source_name,
                "source_abbreviation": m.source_abbreviation,
                "sport_key": m.sport_key,
                "updated_at": m.updated_at.isoformat() if m.updated_at else None,
            }
            for m in mappings
        ],
    }


@router.get("/team-identity/unmapped")
async def team_identity_unmapped(
    secret: str = Query(..., description="Admin secret for authorization"),
    sport_key: str = Query(None, description="Filter by sport key"),
    db: AsyncSession = Depends(get_db),
):
    """Teams with no identity mappings."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.services.team_identity import TeamIdentityService
    service = TeamIdentityService()
    teams = await service.get_unmapped_teams(db, sport_key=sport_key)

    return {
        "count": len(teams),
        "sport_key": sport_key,
        "teams": [
            {
                "id": t.id,
                "name": t.name,
                "abbreviation": t.abbreviation,
                "espn_id": t.espn_id,
                "sport_id": t.sport_id,
            }
            for t in teams
        ],
    }


# =============================================================================
# Futures Team Linking
# =============================================================================


@router.post("/futures/link-teams")
async def trigger_team_linking(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(200, description="Max outcomes to process per run"),
    use_llm: bool = Query(True, description="Use LLM for player-team classification"),
):
    """Trigger team linking backfill for futures outcomes.

    Populates team_id on FuturesOutcome records (matching outcome names
    to Team records) and market_tier on FuturesMarket records.

    Runs as a background Celery task to avoid HTTP timeouts.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_team_links

    task = backfill_team_links.delay(limit=limit, use_llm=use_llm)
    return {
        "status": "queued",
        "task_id": task.id,
        "limit": limit,
        "use_llm": use_llm,
        "message": f"Team linking queued (limit={limit}). Use /api/admin/futures/link-teams/task/{task.id} to check status.",
    }


@router.get("/futures/link-teams/task/{task_id}")
async def get_team_linking_task_status(
    task_id: str,
    secret: str = Query(..., description="Admin secret for authorization"),
):
    """Check the status of a team linking backfill task."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

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


@router.get("/futures/team-links-status")
async def get_team_links_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of team linking across futures outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # Count outcomes with/without team_id
    total = (await db.execute(
        select(func.count(FuturesOutcome.id))
    )).scalar()
    linked = (await db.execute(
        select(func.count(FuturesOutcome.id))
        .where(FuturesOutcome.team_id.is_not(None))
    )).scalar()
    unlinked = total - linked

    # Count markets with/without market_tier
    markets_total = (await db.execute(
        select(func.count(FuturesMarket.id))
    )).scalar()
    markets_tiered = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.market_tier.is_not(None))
    )).scalar()

    return {
        "outcomes_total": total,
        "outcomes_linked": linked,
        "outcomes_unlinked": unlinked,
        "link_percentage": round(linked / total * 100, 1) if total else 0,
        "markets_total": markets_total,
        "markets_tiered": markets_tiered,
        "markets_untiered": markets_total - markets_tiered,
    }


@router.get("/futures/team-links-sample")
async def sample_team_linked_outcomes(
    secret: str = Query(...),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    """Sample recently linked outcomes to verify matching accuracy."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.models import Team

    result = await db.execute(
        select(
            FuturesOutcome.id,
            FuturesOutcome.name,
            FuturesOutcome.team_id,
            Team.name.label("team_name"),
            Team.sport_id,
            FuturesMarket.name.label("market_name"),
            FuturesMarket.source,
            FuturesMarket.llm_sport_category,
        )
        .join(Team, FuturesOutcome.team_id == Team.id)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(FuturesOutcome.team_id.isnot(None))
        .order_by(FuturesOutcome.id.desc())
        .limit(limit)
    )
    samples = [
        {
            "outcome_id": r.id,
            "outcome_name": r.name,
            "team_id": r.team_id,
            "team_name": r.team_name,
            "market_name": r.market_name,
            "source": r.source,
            "sport_category": r.llm_sport_category,
        }
        for r in result.all()
    ]

    return {"count": len(samples), "samples": samples}


@router.get("/futures/team-links-debug")
async def debug_team_links(
    secret: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Debug team linking: show distribution of unlinked outcomes."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    # How many markets have event_id?
    event_linked = await db.execute(text("""
        SELECT
            COUNT(*) FILTER (WHERE fm.event_id IS NOT NULL) AS markets_with_event,
            COUNT(*) FILTER (WHERE fm.event_id IS NULL) AS markets_without_event
        FROM futures_markets fm
    """))
    el = event_linked.first()

    # Unlinked outcomes on event-linked markets
    unlinked_event = await db.execute(text("""
        SELECT COUNT(*) FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.team_id IS NULL AND fm.event_id IS NOT NULL
    """))

    # Comprehensive breakdown by scope
    breakdown = await db.execute(text("""
        SELECT
            CASE
                WHEN fm.event_id IS NOT NULL THEN 'event_linked'
                WHEN fm.llm_sport_category IS NOT NULL THEN 'sport_scoped'
                ELSE 'unscoped'
            END AS scope,
            fm.source,
            fm.market_tier,
            COUNT(*) AS total_outcomes,
            COUNT(fo.team_id) AS linked,
            COUNT(*) - COUNT(fo.team_id) AS unlinked,
            -- Classify outcome types
            COUNT(*) FILTER (WHERE fo.name IN ('Yes', 'No')) AS yes_no_outcomes,
            COUNT(*) FILTER (WHERE fo.name ~* '^(Over|Under|O/U|Spread|Handicap|Draw|Tie)') AS generic_outcomes,
            COUNT(*) FILTER (WHERE fo.name ~* '(Winner|Game [0-9]|Map [0-9]|Match Winner)') AS game_label_outcomes,
            COUNT(*) FILTER (WHERE fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Winner|Game [0-9]|Map [0-9]|Match Winner)'
                              AND length(fo.name) >= 4
                              AND fo.name ~ '[A-Z][a-z]+ [A-Z]') AS likely_names
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        GROUP BY scope, fm.source, fm.market_tier
        ORDER BY scope, fm.source, fm.market_tier
    """))
    breakdown_rows = [
        {
            "scope": r.scope, "source": r.source, "tier": r.market_tier,
            "total": r.total_outcomes, "linked": r.linked, "unlinked": r.unlinked,
            "yes_no": r.yes_no_outcomes, "generic": r.generic_outcomes,
            "game_labels": r.game_label_outcomes, "likely_names": r.likely_names,
        }
        for r in breakdown.all()
    ]

    # Sample of "likely_names" that are unlinked (the ones we SHOULD be matching)
    name_samples = await db.execute(text("""
        SELECT fo.name, fm.name AS market_name, fm.event_id, fm.source,
               fm.llm_sport_category, fm.market_tier,
               CASE WHEN fm.event_id IS NOT NULL THEN 'event_linked'
                    WHEN fm.llm_sport_category IS NOT NULL THEN 'sport_scoped'
                    ELSE 'unscoped' END AS scope
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fo.team_id IS NULL
          AND fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Winner|Game [0-9]|Map [0-9]|Match Winner)'
          AND length(fo.name) >= 4
          AND fo.name ~ '[A-Z][a-z]+ [A-Z]'
        ORDER BY random()
        LIMIT 40
    """))
    name_sample_list = [
        {"outcome": r.name, "market": r.market_name, "event_id": r.event_id,
         "source": r.source, "sport": r.llm_sport_category, "tier": r.market_tier,
         "scope": r.scope}
        for r in name_samples.all()
    ]

    # Team roster coverage
    roster_coverage = await db.execute(text("""
        SELECT s.key AS sport_key,
            COUNT(*) AS total_teams,
            COUNT(*) FILTER (WHERE t.roster_players IS NOT NULL AND t.roster_players != '[]'::jsonb) AS with_roster,
            AVG(jsonb_array_length(COALESCE(t.roster_players, '[]'::jsonb))) FILTER
                (WHERE t.roster_players IS NOT NULL AND t.roster_players != '[]'::jsonb) AS avg_roster_size
        FROM teams t
        JOIN sports s ON t.sport_id = s.id
        WHERE s.key IN ('basketball_nba', 'baseball_mlb', 'americanfootball_nfl', 'icehockey_nhl',
                        'basketball_ncaab', 'americanfootball_ncaaf')
        GROUP BY s.key
        ORDER BY total_teams DESC
    """))
    roster_data = [
        {"sport": r.sport_key, "total_teams": r.total_teams, "with_roster": r.with_roster,
         "avg_roster_size": round(float(r.avg_roster_size or 0), 1)}
        for r in roster_coverage.all()
    ]

    # US major sport matching rates
    us_sports = await db.execute(text("""
        SELECT
            fm.llm_sport_category AS sport,
            COUNT(*) AS total_outcomes,
            COUNT(fo.team_id) AS linked,
            COUNT(*) FILTER (
                WHERE fo.team_id IS NULL
                  AND fo.name !~* '^(Yes|No|Over|Under|O/U|Spread|Handicap|Draw|Tie|Push)$'
                  AND fo.name !~* '^(Match Winner|Game [0-9]|Map [0-9]|Round [0-9]|Odd/Even|Total Kills|First Blood)'
                  AND fo.name !~* '^[0-9]'
                  AND length(fo.name) >= 4
                  AND fo.name ~ '[A-Z][a-z]+ [A-Z]'
            ) AS unlinked_names
        FROM futures_outcomes fo
        JOIN futures_markets fm ON fo.market_id = fm.id
        WHERE fm.llm_sport_category IN ('basketball', 'baseball', 'football', 'hockey', 'golf')
        GROUP BY fm.llm_sport_category
        ORDER BY total_outcomes DESC
    """))
    us_sport_rates = [
        {"sport": r.sport, "total": r.total_outcomes, "linked": r.linked,
         "unlinked_names": r.unlinked_names,
         "match_rate": f"{r.linked*100/(r.linked+r.unlinked_names):.1f}%" if (r.linked + r.unlinked_names) > 0 else "0%"}
        for r in us_sports.all()
    ]

    return {
        "markets_with_event_id": el.markets_with_event if el else 0,
        "markets_without_event_id": el.markets_without_event if el else 0,
        "unlinked_outcomes_on_event_markets": unlinked_event.scalar(),
        "roster_coverage": roster_data,
        "us_sport_match_rates": us_sport_rates,
        "breakdown": breakdown_rows,
        "unlinked_name_samples": name_sample_list,
    }


# =============================================================================
# Canonical Market Key (Cross-source matching)
# =============================================================================


@router.post("/futures/backfill-canonical-keys")
async def trigger_canonical_key_backfill(
    secret: str = Query(..., description="Admin secret for authorization"),
    limit: int = Query(500, description="Max markets to process per run"),
):
    """Trigger backfill of canonical_market_key and llm_league on futures markets.

    Runs as a background Celery task. Returns task_id for status polling.
    """
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    from app.tasks import backfill_canonical_keys
    task = backfill_canonical_keys.delay(limit)

    return {
        "status": "queued",
        "task_id": task.id,
        "message": f"Backfilling canonical keys for up to {limit} markets",
    }


@router.get("/futures/canonical-key-status")
async def get_canonical_key_status(
    secret: str = Query(..., description="Admin secret for authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Check the status of canonical market key population across futures markets."""
    if not _check_admin_secret(secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    total = (await db.execute(
        select(func.count(FuturesMarket.id))
    )).scalar()
    with_key = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.canonical_market_key.is_not(None))
    )).scalar()
    with_league = (await db.execute(
        select(func.count(FuturesMarket.id))
        .where(FuturesMarket.llm_league.is_not(None))
    )).scalar()

    # Count distinct canonical keys with multiple sources
    multi_source = (await db.execute(
        select(func.count())
        .select_from(
            select(FuturesMarket.canonical_market_key)
            .where(FuturesMarket.canonical_market_key.is_not(None))
            .group_by(FuturesMarket.canonical_market_key)
            .having(func.count(func.distinct(FuturesMarket.source)) > 1)
            .subquery()
        )
    )).scalar()

    return {
        "markets_total": total,
        "markets_with_canonical_key": with_key,
        "markets_without_canonical_key": total - with_key,
        "markets_with_league": with_league,
        "canonical_key_percentage": round(with_key / total * 100, 1) if total else 0,
        "multi_source_keys": multi_source,
    }
