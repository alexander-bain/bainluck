"""
League context service — provides per-team championship probabilities
for any configured league.

Caches computed context in Redis (5-min TTL) so event detail pages
can cheaply look up "this team is 65% to make playoffs, 12% to win
the championship" without recomputing the full grid.

Usage:
    from app.services.league_context import get_league_context, get_team_context

    # Get all teams in a league
    ctx = await get_league_context("nba", db)

    # Get context for a specific team (by name)
    team = await get_team_context("Boston Celtics", "basketball_nba", db)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.league_configs import (
    LEAGUE_CONFIGS,
    get_league_for_sport_key,
    LEAGUE_TO_SPORT,
)
from app.utils.name_normalization import normalize_name

logger = logging.getLogger(__name__)

LEAGUE_CONTEXT_TTL = 300  # 5 minutes


@dataclass
class TeamLeagueContext:
    """What we know about a team's season outlook, from grid data."""

    team_name: str
    team_id: Optional[int] = None
    league_slug: str = ""
    conference: Optional[str] = None
    record: Optional[str] = None
    # Dynamic cells — keyed by GridColumn.key, varies per league
    cells: dict[str, float] = field(default_factory=dict)
    changes_24h: dict[str, float] = field(default_factory=dict)
    column_labels: dict[str, str] = field(default_factory=dict)
    sources_available: list[str] = field(default_factory=list)


@dataclass
class LeagueContext:
    """Full league state: all teams + their season outlook."""

    league_slug: str = ""
    league_name: str = ""
    sport_group: str = ""
    teams: dict[str, TeamLeagueContext] = field(default_factory=dict)
    columns: list[dict] = field(default_factory=list)  # [{key, label}]
    last_computed: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "LeagueContext":
        data = json.loads(raw)
        teams = {}
        for name, tdata in data.get("teams", {}).items():
            teams[name] = TeamLeagueContext(**tdata)
        data["teams"] = teams
        return cls(**data)


async def _compute_league_context(
    league_slug: str,
    db: AsyncSession,
) -> Optional[LeagueContext]:
    """Compute league context by calling the grid builder internally."""
    config = LEAGUE_CONFIGS.get(league_slug)
    if not config:
        return None

    # Import here to avoid circular imports.
    #
    # LAT-P128: this is the CACHED wrapper, not the raw builder. The three
    # arguments below are exactly `get_playoff_grid_cached`'s `cache_eligible`
    # set (`not debug and hours is None and top == 10`), so this call has
    # always been eligible to read the Redis key that the hourly grid warm
    # (#901) keeps populated — it just called past it into a full rebuild, on
    # every miss of league_context's own 300 s key.
    #
    # Measured on production, one sequence, three requests back to back
    # (2026-08-29T14:56:57Z). The key was warm on BOTH sides of the 21-second
    # read:
    #
    #   GET /api/playoffs/bundesliga              200   0.356 s  wall=20.7  q=0
    #   GET /api/events/14970280/related-futures  200  21.678 s  wall=21418 q=23
    #   GET /api/playoffs/bundesliga              200   0.329 s  wall=22.2  q=0
    #
    # q=23 cold vs q=14 warm; the difference of 9 is exactly the grid's own
    # query count when it rebuilds.
    #
    # The wrapper is strictly safer than the raw builder here, not merely
    # faster: it adds the 25 s wall and the labelled last-good fallback that
    # this path never had, and on a genuine miss it also REFILLS the shared
    # key, so an event page can no longer rebuild a grid without leaving the
    # result where the grid page will find it.
    from app.routes.playoffs import get_playoff_grid_cached

    try:
        # Call the grid endpoint function directly (not via HTTP)
        grid_data = await get_playoff_grid_cached(
            league_slug=league_slug,
            hours=None,
            top=10,
            debug=False,
            db=db,
        )
    except Exception as e:
        # Load-bearing since LAT-P128, and `Exception` rather than a narrower
        # tuple on purpose: the wrapper answers a timeout-with-no-last-good with
        # `HTTPException(503)`, which is the honest answer for the grid PAGE and
        # must never become the event page's answer. `HTTPException` subclasses
        # `Exception`, so the 503 degrades to `league_context: null` here — the
        # same shape a caller already gets when the grid has no data — instead of
        # turning a degraded side-panel into a failed event page.
        logger.warning("Failed to compute league context for %s: %s", league_slug, e)
        return None

    if not grid_data:
        return None

    # Build column metadata
    columns = [{"key": c.key, "label": c.label} for c in config.columns]
    column_labels = {c.key: c.label for c in config.columns}

    # Extract team data from grid response
    # Grid response format varies: golf uses "teams" with "cells",
    # team sports use "teams" with "stages"
    teams_data = grid_data.get("teams", [])
    if not teams_data:
        # Try grouped_teams (conference split)
        grouped = grid_data.get("grouped_teams", {})
        for group_teams in grouped.values():
            teams_data.extend(group_teams)

    teams: dict[str, TeamLeagueContext] = {}
    for team in teams_data:
        name = team.get("name", "")
        if not name:
            continue

        norm_name = normalize_name(name)
        cells: dict[str, float] = {}
        changes: dict[str, float] = {}
        sources: set[str] = set()

        # Golf format: team["cells"] = {col_key: {merged_probability, sources, trend_24h}}
        if "cells" in team:
            for col_key, cell_data in team["cells"].items():
                if isinstance(cell_data, dict):
                    prob = cell_data.get("merged_probability")
                    if prob is not None:
                        cells[col_key] = prob
                    trend = cell_data.get("trend_24h")
                    if trend is not None:
                        changes[col_key] = trend
                    for s in cell_data.get("sources", []):
                        sources.add(s.get("source", ""))

        # Team sports format: team["stages"] = [{key, label, probability, trend_24h, sources}]
        elif "stages" in team:
            for stage in team["stages"]:
                col_key = stage.get("key", "")
                prob = stage.get("probability")
                if prob is not None:
                    cells[col_key] = prob
                trend = stage.get("trend_24h")
                if trend is not None:
                    changes[col_key] = trend
                for s in stage.get("sources", []):
                    sources.add(s.get("source", ""))

        if not cells:
            continue

        teams[norm_name] = TeamLeagueContext(
            team_name=name,
            team_id=team.get("team_id"),
            league_slug=league_slug,
            conference=team.get("conference"),
            record=team.get("record"),
            cells=cells,
            changes_24h=changes,
            column_labels=column_labels,
            sources_available=sorted(s for s in sources if s),
        )

    sport_group = LEAGUE_TO_SPORT.get(league_slug, "")

    return LeagueContext(
        league_slug=league_slug,
        league_name=config.name,
        sport_group=sport_group,
        teams=teams,
        columns=columns,
        last_computed=datetime.now(timezone.utc).isoformat(),
    )


async def get_league_context(
    league_slug: str,
    db: AsyncSession,
) -> Optional[LeagueContext]:
    """Get cached league context, computing if stale (>5 min)."""
    from app.tasks.redis_state import get_redis_client

    cache_key = f"bainluck:league_context:{league_slug}"

    try:
        r = get_redis_client()
        cached = r.get(cache_key)
        if cached:
            return LeagueContext.from_json(cached.decode())
    except Exception:
        pass  # Redis unavailable — compute fresh

    ctx = await _compute_league_context(league_slug, db)
    if ctx:
        try:
            r = get_redis_client()
            r.setex(cache_key, LEAGUE_CONTEXT_TTL, ctx.to_json())
        except Exception:
            pass  # Cache write failed — still return computed result

    return ctx


async def get_team_context(
    team_name: str,
    sport_key: str,
    db: AsyncSession,
) -> Optional[TeamLeagueContext]:
    """Get league context for a specific team by name + sport key.

    Resolves the sport_key to a league, then looks up the team
    in the cached league context.
    """
    config = get_league_for_sport_key(sport_key)
    if not config:
        return None

    ctx = await get_league_context(config.slug, db)
    if not ctx:
        return None

    # Try exact normalized name match first
    norm = normalize_name(team_name)
    if norm in ctx.teams:
        return ctx.teams[norm]

    # Fuzzy fallback: check if team_name is a substring of any cached name
    for cached_norm, team_ctx in ctx.teams.items():
        if norm in cached_norm or cached_norm in norm:
            return team_ctx

    return None


async def enrich_event_with_context(
    event,
    db: AsyncSession,
) -> Optional[dict]:
    """Add league context to an event for the API response.

    Returns a dict with league_context data for both teams,
    or None if the event's sport doesn't have a league config.
    """
    # Resolve event's sport to a league
    sport_key = None
    if event.sport_id:
        from app.models import Sport
        from sqlalchemy import select
        sport_result = await db.execute(
            select(Sport.key).where(Sport.id == event.sport_id)
        )
        sport_key = sport_result.scalar()

    if not sport_key:
        return None

    config = get_league_for_sport_key(sport_key)
    if not config:
        return None

    ctx = await get_league_context(config.slug, db)
    if not ctx:
        return None

    # Look up both teams
    home_name = event.home_team_name or ""
    away_name = event.away_team_name or ""

    home_ctx = None
    away_ctx = None

    home_norm = normalize_name(home_name)
    away_norm = normalize_name(away_name)

    for cached_norm, team_ctx in ctx.teams.items():
        if not home_ctx and (home_norm == cached_norm or home_norm in cached_norm or cached_norm in home_norm):
            home_ctx = team_ctx
        if not away_ctx and (away_norm == cached_norm or away_norm in cached_norm or cached_norm in away_norm):
            away_ctx = team_ctx

    if not home_ctx and not away_ctx:
        return None

    sport_group = LEAGUE_TO_SPORT.get(config.slug, "")
    league_page_url = f"/{sport_group}/{config.slug}" if sport_group else f"/playoffs/{config.slug}"

    result = {
        "league_slug": config.slug,
        # STRIPPED — SCHEDULED, not yet executed. Queue 333, C272/B4 census (#1620).
        # The one field here with no retention argument at all: it is `config.name`, and
        # `league_slug` sits directly above it on the same object, so every client can
        # already resolve the display name from its own league config. It is redundancy
        # on the wire, not information — four months old (2026-04-14, `04899609`) with
        # zero client reads.
        # Old-build check RECORDED (Item 0's rule): iOS `leagueName` is `String?` —
        # OPTIONAL — so removal is decode-safe for shipped builds; the key simply stops
        # arriving. No crash.
        # NOT stripped here because a strip is Red and this one has THREE producers
        # (`events.py:7866`, `playoffs.py:4073`, and here) plus two typed clients, and it
        # moves the typecheck baseline, which the CI ratchet fails on in both directions
        # (gotcha #10). Scheduled deliberately rather than taken opportunistically.
        "league_name": config.name,
        "columns": ctx.columns,
        "league_page_url": league_page_url,
    }

    if home_ctx:
        result["home_team"] = {
            "cells": home_ctx.cells,
            "changes_24h": home_ctx.changes_24h,
            "record": home_ctx.record,
            "conference": home_ctx.conference,
            "sources_available": home_ctx.sources_available,
        }
    if away_ctx:
        result["away_team"] = {
            "cells": away_ctx.cells,
            "changes_24h": away_ctx.changes_24h,
            "record": away_ctx.record,
            "conference": away_ctx.conference,
            "sources_available": away_ctx.sources_available,
        }

    return result
