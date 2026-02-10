"""
Team linking task: populates team_id on FuturesOutcome records
and market_tier on FuturesMarket records.

Runs as a backfill task and is also called inline during futures polling.
"""

import logging
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


async def _load_teams_by_sport(
    session: AsyncSession,
    sport_keys: Optional[list[str]] = None,
) -> list[dict]:
    """Load team records scoped by sport keys.

    Returns list of dicts: [{id, name, alternate_names, sport_key}, ...]
    """
    from app.models import Team, Sport

    query = (
        select(Team.id, Team.name, Team.alternate_names, Sport.key)
        .join(Sport, Team.sport_id == Sport.id)
    )
    if sport_keys:
        query = query.where(Sport.key.in_(sport_keys))

    result = await session.execute(query)
    return [
        {
            "id": row.id,
            "name": row.name,
            "alternate_names": row.alternate_names or [],
            "sport_key": row.key,
        }
        for row in result.all()
    ]


async def link_outcome_to_team(
    session: AsyncSession,
    outcome_name: str,
    sport_category: Optional[str],
    market_name: Optional[str],
    teams: list[dict],
    use_llm: bool = True,
) -> Optional[int]:
    """
    Try to match a futures outcome name to a team_id.

    1. Try direct name matching against team records
    2. If no match and use_llm=True, try LLM player-team classification

    Args:
        session: DB session (for potential follow-up queries)
        outcome_name: The outcome name (e.g., "Boston Celtics" or "Jaylen Brown")
        sport_category: Sport category (e.g., "basketball")
        market_name: Market name for LLM context
        teams: Pre-loaded team records to match against
        use_llm: Whether to fall back to LLM for player names

    Returns:
        team_id if matched, None otherwise
    """
    from app.utils.team_linking import match_outcome_to_team

    # Step 1: Direct name match
    team_id = match_outcome_to_team(outcome_name, teams)
    if team_id:
        return team_id

    # Step 2: LLM player-team classification
    if use_llm:
        from app.services import llm
        if not llm.is_available():
            return None

        team_name = llm.classify_player_team_cached(
            player_name=outcome_name,
            sport_category=sport_category,
            market_name=market_name,
        )
        if team_name:
            # Now match the LLM's team name against our team records
            team_id = match_outcome_to_team(team_name, teams)
            if team_id:
                logger.info(
                    f"LLM linked '{outcome_name}' → '{team_name}' → team_id={team_id}"
                )
            return team_id

    return None


async def _backfill_team_links(limit: int = 200, use_llm: bool = True):
    """
    Backfill team_id on FuturesOutcome records and market_tier on FuturesMarket records.

    Processes outcomes where team_id IS NULL and the market has a known sport category.
    Also sets market_tier on any FuturesMarket where it's NULL.
    """
    from app.models import FuturesMarket, FuturesOutcome
    from app.utils.team_linking import compute_market_tier, get_sport_keys_for_category

    stats = {
        "outcomes_processed": 0,
        "outcomes_linked": 0,
        "outcomes_linked_by_name": 0,
        "outcomes_linked_by_llm": 0,
        "markets_tiered": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # --- Phase 1: Assign market_tier where missing ---
            tier_result = await session.execute(
                select(FuturesMarket)
                .where(FuturesMarket.market_tier.is_(None))
                .limit(limit * 5)  # Tiers are cheap to compute
            )
            markets_to_tier = tier_result.scalars().all()

            for market in markets_to_tier:
                market.market_tier = compute_market_tier(market.name, market.category)
                stats["markets_tiered"] += 1

            # --- Phase 2: Link outcomes to teams ---
            # Get markets with outcomes that need linking, grouped by sport category
            outcomes_result = await session.execute(
                select(FuturesOutcome)
                .options(selectinload(FuturesOutcome.market))
                .where(FuturesOutcome.team_id.is_(None))
                .order_by(FuturesOutcome.market_id)
                .limit(limit)
            )
            outcomes = outcomes_result.scalars().all()

            if not outcomes:
                return stats

            # Group outcomes by sport category to batch team loading
            category_outcomes: dict[str, list] = {}
            for outcome in outcomes:
                market = outcome.market
                category = (
                    market.llm_sport_category
                    or market.category
                    or "unknown"
                )
                category_outcomes.setdefault(category, []).append(outcome)

            # Process each category
            for category, cat_outcomes in category_outcomes.items():
                try:
                    # Load teams for this sport category
                    sport_keys = get_sport_keys_for_category(category)
                    teams = await _load_teams_by_sport(session, sport_keys)

                    if not teams and sport_keys:
                        # Fallback: load all teams if sport-scoped search returned nothing
                        teams = await _load_teams_by_sport(session, None)

                    for outcome in cat_outcomes:
                        try:
                            stats["outcomes_processed"] += 1

                            # Try name matching first (no LLM)
                            from app.utils.team_linking import match_outcome_to_team
                            team_id = match_outcome_to_team(outcome.name, teams)

                            if team_id:
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_name"] += 1
                                continue

                            # Try LLM for player names
                            if use_llm:
                                team_id = await link_outcome_to_team(
                                    session=session,
                                    outcome_name=outcome.name,
                                    sport_category=category,
                                    market_name=outcome.market.name,
                                    teams=teams,
                                    use_llm=True,
                                )
                                if team_id:
                                    outcome.team_id = team_id
                                    stats["outcomes_linked"] += 1
                                    stats["outcomes_linked_by_llm"] += 1

                        except Exception as e:
                            stats["errors"].append(
                                f"Outcome {outcome.id} '{outcome.name}': {str(e)}"
                            )

                except Exception as e:
                    stats["errors"].append(f"Category '{category}': {str(e)}")

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    return stats
