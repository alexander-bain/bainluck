"""Prop-family API: grouped prop families for a team.

``GET /api/teams/{identifier}/prop-families`` loads a team's futures/prop
markets and returns them grouped into prop families (Next Team, award
races, threshold ladders) via ``app.utils.prop_families``.

The team → props matching mirrors the pattern in ``app.routes.user``
``_query_team_futures`` (team_id FK + full team-name ILIKE + roster player
name ILIKE), reproduced here rather than shared to avoid coupling — this
route is public read-only and does not need the round-robin/coherence
post-processing that ``_query_team_futures`` applies for the "Your Teams'
Odds" surface.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Team, FuturesMarket, FuturesOutcome
from app.services import get_db
from app.utils.prop_families import group_prop_families

logger = logging.getLogger(__name__)

router = APIRouter()

# Terminal statuses we still want to surface so a settled prop can be
# labelled WHAT-HIT (bug b) rather than dropped.
_INCLUDED_STATUSES = ["open", "resolved", "closed", "settled", "suspended"]

_MAX_ROSTER_PATTERNS = 40


def _escape_like(s: str) -> str:
    """Escape special LIKE/ILIKE characters for safe pattern matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _roster_player_names(team: Team) -> list[str]:
    """Extract roster player names for player-prop family matching."""
    names: list[str] = []
    roster = getattr(team, "roster_players", None)
    if roster and isinstance(roster, list):
        for item in roster:
            if isinstance(item, dict):
                nm = item.get("name")
            elif isinstance(item, str):
                nm = item
            else:
                nm = None
            if isinstance(nm, str) and len(nm.strip()) >= 4:
                names.append(nm.strip())
            if len(names) >= _MAX_ROSTER_PATTERNS:
                break
    return names


@router.get("/{identifier}/prop-families")
async def get_team_prop_families(
    identifier: str,
    limit: int = 400,
    db: AsyncSession = Depends(get_db),
):
    """Detect and return prop families over a team's futures/prop markets.

    Response shape::

        {
          "team": {"id": int, "name": str, "slug": str | None},
          "families": [ {family_key, label, entity_count, sources, rows: [...]}, ... ],
          "total_families": int,
        }
    """
    # Resolve team by integer id or slug.
    team_filter = Team.slug == identifier
    try:
        team_id = int(identifier)
        team_filter = or_(Team.id == team_id, Team.slug == identifier)
    except ValueError:
        pass

    result = await db.execute(select(Team).where(team_filter))
    team = result.scalars().first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Build match conditions: team_id FK, full team-name ILIKE (on outcome
    # names AND market names), and roster player-name ILIKE.
    conditions = [FuturesOutcome.team_id == team.id]
    if team.name:
        pat = f"%{_escape_like(team.name.strip())}%"
        conditions.append(FuturesOutcome.name.ilike(pat))
        conditions.append(FuturesMarket.name.ilike(pat))
    for player in _roster_player_names(team):
        ppat = f"%{_escape_like(player)}%"
        conditions.append(FuturesMarket.name.ilike(ppat))
        conditions.append(FuturesOutcome.name.ilike(ppat))

    query = (
        select(FuturesOutcome, FuturesMarket)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            and_(
                FuturesMarket.event_id.is_(None),
                FuturesMarket.status.in_(_INCLUDED_STATUSES),
                or_(*conditions),
            )
        )
        .order_by(FuturesOutcome.current_probability.desc().nulls_last())
        .limit(max(1, min(limit, 2000)))
    )
    # #1197 / #1239: the multi-ILIKE roster scan can occasionally run long enough
    # to hit Heroku's 30s H12 request timeout (a hung 503). Bound it with a
    # per-statement timeout so a slow scan fails fast and the endpoint degrades to
    # an empty families list (200) instead of hanging the dyno to a 503.
    try:
        await db.execute(text("SET LOCAL statement_timeout = '12000'"))
        rows = (await db.execute(query)).all()
    except Exception:
        logger.exception(
            "prop-families: query failed/timed out for team %s — empty degrade",
            team.id,
        )
        return {
            "team": {
                "id": team.id,
                "name": team.name,
                "slug": getattr(team, "slug", None),
            },
            "families": [],
            "total_families": 0,
        }

    # Reassemble outcomes onto their market dicts.
    by_market: dict[int, dict] = {}
    for outcome, market in rows:
        entry = by_market.get(market.id)
        if entry is None:
            entry = {
                "market_id": market.id,
                "name": market.name,
                "source": market.source,
                "group_id": market.group_id,
                "status": market.status,
                "resolution_date": (
                    market.resolution_date.isoformat()
                    if market.resolution_date else None
                ),
                "market_metadata": market.market_metadata,
                "outcomes": [],
            }
            by_market[market.id] = entry
        prob = (
            float(outcome.current_probability)
            if outcome.current_probability is not None else None
        )
        entry["outcomes"].append(
            {
                "outcome_id": outcome.id,
                "name": outcome.name,
                "probability": prob,
                "is_winner": bool(outcome.is_winner),
            }
        )

    families = group_prop_families(list(by_market.values()))

    return {
        "team": {
            "id": team.id,
            "name": team.name,
            "slug": getattr(team, "slug", None),
        },
        "families": families,
        "total_families": len(families),
    }
