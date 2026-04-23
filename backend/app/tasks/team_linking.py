"""
Team linking task: populates team_id on FuturesOutcome records,
market_tier on FuturesMarket records, and backfills league/canonical keys.

Runs as a backfill task and is also called inline during futures polling.
"""

import logging
from typing import Optional

from sqlalchemy import select, func, or_, and_
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
        select(Team.id, Team.name, Team.alternate_names, Team.roster_players, Sport.key)
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
            "roster_players": row.roster_players,
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

    # Step 1: Identity service fast path (indexed lookup)
    from app.services.team_identity import team_identity_service
    # Determine sport key from teams list (all teams in same category share a key)
    identity_sport_key = ""
    if teams:
        identity_sport_key = teams[0].get("sport_key", "")
    if identity_sport_key:
        resolved = await team_identity_service.resolve_team(
            session, "futures", identity_sport_key,
            source_name=outcome_name,
        )
        if resolved:
            return resolved.id

    # Step 2: Direct name match
    team_id = match_outcome_to_team(outcome_name, teams)
    if team_id:
        # Register for future instant lookups
        if identity_sport_key:
            await team_identity_service.register_team_identity(
                session, team_id, "futures", identity_sport_key,
                source_name=outcome_name,
            )
        return team_id

    # Step 3: LLM player-team classification
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
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.team_linking import get_sport_keys_for_category

    stats = {
        "outcomes_processed": 0,
        "outcomes_linked": 0,
        "outcomes_linked_by_name": 0,
        "outcomes_linked_by_roster": 0,
        "outcomes_linked_by_llm": 0,
        "markets_tiered": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # --- Phase 1: Assign market_tier where missing or wrong ---
            # Re-tier: NULL tiers, game_prop ordering bugs, AND non-game-prop
            # markets stuck at tier 5 (catches regex improvements).
            tier_result = await session.execute(
                select(FuturesMarket)
                .where(
                    or_(
                        FuturesMarket.market_tier.is_(None),
                        and_(
                            FuturesMarket.category == "game_prop",
                            FuturesMarket.market_tier != 5,
                        ),
                        and_(
                            FuturesMarket.category != "game_prop",
                            FuturesMarket.market_tier == 5,
                        ),
                    )
                )
                .limit(limit * 5)
            )
            markets_to_tier = tier_result.scalars().all()

            for market in markets_to_tier:
                new_tier = compute_market_tier(
                    market.name, market.category,
                    sport_category=market.llm_sport_category,
                )
                if market.market_tier != new_tier:
                    market.market_tier = new_tier
                    stats["markets_tiered"] += 1

            # --- Phase 2: Link outcomes to teams ---
            # Skip generic outcomes that can never match a team/player name.
            # This dramatically reduces the number of outcomes we process.
            from sqlalchemy import text as sa_text
            _SKIP_PATTERNS = (
                "^(Yes|No|Over|Under|Draw|Tie|Push)$",          # Binary outcomes
                "^O/U ",                                         # Over/Under lines
                "^Spread ",                                      # Spread lines
                "^(Handicap|Game Handicap|Map Handicap)",        # Handicaps
                "^(Match Winner|Game [0-9]|Map [0-9]|Round [0-9])",  # Game/map labels
                "^(Odd/Even|Total Kills|First Blood|Both Teams|Any Player|Exact Score)",  # Esports/soccer generics
                "^[0-9]",                                        # Numeric outcomes ("218.5")
                "wins (by|the|1H)",                              # Spread descriptions ("Team wins by over 5.5")
                " over [0-9]",                                   # Point totals ("Team over 119.5 points")
                " -[0-9]",                                       # Game handicaps ("Frances Tiafoe -1.5 games")
                "\\(-[0-9]",                                     # Handicap notation ("Team (-2.5)")
                "^(Double Double|Triple Double|Both Teams to Score|No Goal)",  # Stat/game generics
            )
            skip_regex = "|".join(f"({p})" for p in _SKIP_PATTERNS)

            # Prioritize US major sports where we have roster data.
            # Skip golf — individual sport, no team rosters to match against.
            _US_SPORTS = ("basketball", "baseball", "football", "hockey")

            outcomes_result = await session.execute(
                select(FuturesOutcome)
                .options(selectinload(FuturesOutcome.market))
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .where(
                    FuturesOutcome.team_id.is_(None),
                    ~FuturesOutcome.name.op("~*")(skip_regex),
                    func.length(FuturesOutcome.name) >= 4,
                    FuturesMarket.llm_sport_category.in_(_US_SPORTS),  # US sports only
                )
                .order_by(FuturesOutcome.market_id)
                .limit(limit)
            )
            outcomes = outcomes_result.scalars().all()

            if not outcomes:
                return stats

            # --- Phase 2a: Fast path for event-linked markets ---
            # Game props (Kalshi/Polymarket) have FuturesMarket.event_id set,
            # which gives us the exact two teams. Match against only those
            # rosters — eliminates cross-team false positives entirely.
            from app.models import Event, Sport, Team as TeamModel
            from app.utils.team_linking import match_outcome_to_roster
            remaining_outcomes = []
            event_cache: dict[int, dict] = {}  # event_id → {team_id: [player_names]}

            def _extract_rosters(team_rows) -> dict[int, list[str]]:
                rosters: dict[int, list[str]] = {}
                for tr in team_rows:
                    roster = tr.roster_players
                    if roster and isinstance(roster, list):
                        players = []
                        for item in roster:
                            name = item.get("name") if isinstance(item, dict) else item if isinstance(item, str) else None
                            if isinstance(name, str) and len(name) >= 4:
                                players.append(name)
                        if players:
                            rosters[tr.id] = players
                return rosters

            for outcome in outcomes:
                market = outcome.market
                if not market.event_id:
                    remaining_outcomes.append(outcome)
                    continue

                stats["outcomes_processed"] += 1

                # Load event teams (cached per event_id)
                if market.event_id not in event_cache:
                    ev = await session.get(Event, market.event_id)
                    event_rosters: dict[int, list[str]] = {}
                    if ev:
                        if ev.home_team_id or ev.away_team_id:
                            # Fast path: FK team IDs exist
                            team_ids = [t for t in [ev.home_team_id, ev.away_team_id] if t]
                            team_rows = (await session.execute(
                                select(TeamModel.id, TeamModel.name, TeamModel.roster_players)
                                .where(TeamModel.id.in_(team_ids))
                            )).all()
                            event_rosters = _extract_rosters(team_rows)
                        elif ev.home_team_name and ev.away_team_name:
                            # Fallback: team IDs not set, look up by name + sport
                            name_filters = [
                                or_(
                                    TeamModel.name == ev.home_team_name,
                                    TeamModel.name == ev.away_team_name,
                                )
                            ]
                            if ev.sport_id:
                                name_filters.append(TeamModel.sport_id == ev.sport_id)
                            team_rows = (await session.execute(
                                select(TeamModel.id, TeamModel.name, TeamModel.roster_players)
                                .where(*name_filters)
                            )).all()
                            event_rosters = _extract_rosters(team_rows)
                    event_cache[market.event_id] = event_rosters
                    if not event_rosters and ev:
                        logger.info(
                            "Event %s (%s vs %s): no rosters found (team_ids=%s/%s, sport_id=%s)",
                            market.event_id, ev.home_team_name, ev.away_team_name,
                            ev.home_team_id, ev.away_team_id, ev.sport_id,
                        )

                event_rosters = event_cache[market.event_id]
                if event_rosters:
                    team_id = match_outcome_to_roster(outcome.name, event_rosters)
                    if team_id:
                        outcome.team_id = team_id
                        stats["outcomes_linked"] += 1
                        stats["outcomes_linked_by_roster"] += 1
                        continue

                # Event-linked but no roster match — fall through to category matching
                remaining_outcomes.append(outcome)

            # --- Phase 2b: Category-based matching for non-event-linked markets ---
            # Group outcomes by sport category to batch team loading
            category_outcomes: dict[str, list] = {}
            for outcome in remaining_outcomes:
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

                    # Build roster lookup: {team_id: [player_name, ...]}
                    from app.utils.team_linking import match_outcome_to_roster
                    team_rosters: dict[int, list[str]] = {}
                    for team in teams:
                        roster = team.get("roster_players")
                        if roster and isinstance(roster, list):
                            players = []
                            for item in roster:
                                if isinstance(item, dict):
                                    name = item.get("name")
                                elif isinstance(item, str):
                                    name = item
                                else:
                                    continue
                                if isinstance(name, str) and len(name) >= 4:
                                    players.append(name)
                            if players:
                                team_rosters[team["id"]] = players

                    for outcome in cat_outcomes:
                        try:
                            stats["outcomes_processed"] += 1

                            # Step 1: Try name matching first (no LLM)
                            from app.utils.team_linking import match_outcome_to_team
                            team_id = match_outcome_to_team(outcome.name, teams)

                            if team_id:
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_name"] += 1
                                continue

                            # Step 1.5: Try roster player matching
                            team_id = match_outcome_to_roster(
                                outcome.name, team_rosters
                            )
                            if team_id:
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_roster"] += 1
                                continue

                            # Step 2: Try LLM for player names
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


async def _backfill_canonical_keys(limit: int = 500):
    """
    Backfill canonical_market_key, llm_league, and llm_sport_category on
    FuturesMarket records.

    Processes markets where:
    - canonical_market_key IS NULL, or
    - llm_league IS NULL, or
    - llm_sport_category is 'other' or NULL (tries to upgrade via league
      inference or expanded pattern matching)

    Also fills in llm_league where missing.
    """
    from app.models import FuturesMarket
    from app.utils.futures_categorization import (
        categorize_by_rules, detect_league, detect_season,
        compute_canonical_market_key, infer_sport_from_league,
        extract_olympic_discipline,
    )

    stats = {
        "processed": 0,
        "leagues_set": 0,
        "keys_set": 0,
        "categories_upgraded": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find markets missing canonical key, league, or stuck as 'other'
            result = await session.execute(
                select(FuturesMarket)
                .where(
                    or_(
                        FuturesMarket.canonical_market_key.is_(None),
                        FuturesMarket.llm_league.is_(None),
                        FuturesMarket.llm_sport_category.is_(None),
                        FuturesMarket.llm_sport_category == "other",
                    )
                )
                .limit(limit)
            )
            markets = result.scalars().all()

            if not markets:
                stats["message"] = "No markets to backfill"
                return stats

            for market in markets:
                try:
                    stats["processed"] += 1

                    # Detect league if missing
                    if not market.llm_league:
                        sport_key = (
                            market.external_id
                            if market.source == "odds_api"
                            else None
                        )
                        league = detect_league(market.name, sport_key)
                        if league:
                            market.llm_league = league
                            stats["leagues_set"] += 1
                    else:
                        league = market.llm_league

                    # Try to upgrade 'other' or NULL sport category
                    if not market.llm_sport_category or market.llm_sport_category == "other":
                        upgraded = False

                        # Strategy 1: Infer sport from detected league
                        if league:
                            sport = infer_sport_from_league(league)
                            if sport:
                                market.llm_sport_category = sport
                                stats["categories_upgraded"] += 1
                                upgraded = True

                        # Strategy 2: Re-run pattern matching (catches newly added patterns)
                        if not upgraded:
                            sport_key = (
                                market.external_id
                                if market.source == "odds_api"
                                else None
                            )
                            rules_result = categorize_by_rules(market.name, sport_key)
                            if rules_result and rules_result != "other":
                                market.llm_sport_category = rules_result
                                stats["categories_upgraded"] += 1

                    # Compute canonical key if missing
                    if not market.canonical_market_key:
                        season = detect_season(
                            market.name, league, market.resolution_date,
                        )
                        # For Olympics, use specific discipline as category
                        canon_category = market.category
                        if market.llm_sport_category == "olympics":
                            discipline = extract_olympic_discipline(market.name)
                            if discipline:
                                canon_category = discipline
                        key = compute_canonical_market_key(
                            market.llm_sport_category,
                            league,
                            canon_category,
                            season,
                        )
                        if key:
                            market.canonical_market_key = key
                            stats["keys_set"] += 1

                except Exception as e:
                    stats["errors"].append(
                        f"Market {market.id} '{market.name}': {str(e)}"
                    )

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    stats["message"] = (
        f"Processed {stats['processed']} markets: "
        f"{stats['leagues_set']} leagues set, "
        f"{stats['keys_set']} canonical keys set, "
        f"{stats['categories_upgraded']} categories upgraded from 'other'"
    )
    logger.info(
        "Canonical key backfill: %d processed, %d leagues, %d keys, %d categories upgraded",
        stats["processed"],
        stats["leagues_set"],
        stats["keys_set"],
        stats["categories_upgraded"],
    )
    return stats
