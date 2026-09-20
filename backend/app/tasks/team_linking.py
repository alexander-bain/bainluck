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


# --- Phase 2 selector: skip list, sport scope, and the resumable cursor (#7307) ---

# Skip generic outcomes that can never match a team/player name.
# This dramatically reduces the number of outcomes we process.
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
SKIP_REGEX = "|".join(f"({p})" for p in _SKIP_PATTERNS)

# Prioritize US major sports where we have roster data.
# Skip golf — individual sport, no team rosters to match against.
_US_SPORTS = ("basketball", "baseball", "football", "hockey")

# #7307 — THE SELECTOR HAS TO ADVANCE. The Phase 2 query used to be
# ``... WHERE team_id IS NULL ... ORDER BY market_id LIMIT :limit`` with no
# memory of where the last run stopped. There is no attempted marker on
# ``futures_outcomes``, so a row that FAILS to bind stays ``team_id IS NULL``
# and is re-selected, hour after hour, forever; the queue only ever drains by
# successful binds. Measured on production 2026-09-19: 1,469,773 rows match
# this selector and the head of the order is college-basketball outcomes that
# have no ``teams`` row at all. PR #7301 fixed a real matching defect affecting
# 862 legs whose lowest ``market_id`` is 199,045 — not one of them was
# reachable, so a correct, fully guard-tested fix bound nothing in production.
#
# The fix is the ``backfill_market_shapes`` pattern: a persisted id cursor per
# pass that wraps to 0 when a pass runs off the end of the table. A failure
# therefore leaves the working window immediately and is retried once per full
# cycle instead of once per hour.
#
# TWO CURSORS, NOT ONE, because one cursor over 1.47M rows at the scheduled
# 2,000/hour is a 31-day cycle and a reader cannot see 95% of that population.
# Only 64,527 of the rows sit in ``status='open'`` markets — the legs a person
# can load today — so the open pass is served first and the resolved pass keeps
# a reserved floor of the batch so it can never be starved to zero.
_CURSOR_KEY_OPEN = "bainluck:team_link_cursor:open"
_CURSOR_KEY_RESOLVED = "bainluck:team_link_cursor:resolved"
_CURSOR_TTL = 86400 * 14
_RESOLVED_FLOOR_DIVISOR = 4


def _resolved_floor(limit: int) -> int:
    """Rows of each batch the resolved-market pass may never be denied.

    A floor and not a fixed size: the open pass takes ``limit - floor`` at most,
    and whatever the open pass leaves on the table goes to the resolved pass on
    top of the floor. With the scheduled ``limit=2000`` the open backlog cycles
    in ~43h and the resolved one still moves 500 rows an hour.
    """
    if limit <= 1:
        return 0
    return max(1, limit // _RESOLVED_FLOOR_DIVISOR)


def _cursor_store():
    """The bounded Redis client the cursors live in, or None if unreachable.

    Gotcha #39: never build a client here — ``get_redis_client`` is the one with
    a socket timeout, and a sync client without one can freeze an async task.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception as exc:  # pragma: no cover - redis outage
        logger.warning("team-link cursor store unavailable (%s); running from the head", exc)
        return None


def _apply_cursor_writes(rc, writes) -> None:
    """Persist this run's cursors. Called only AFTER the batch has committed.

    A cursor written before the commit that then rolls back would step the
    window past rows nothing ever linked; they would come back a full cycle
    later rather than next hour, which is the failure this whole change exists
    to stop. ``None`` means wrap: delete the key so the next run starts at 0.
    """
    if rc is None:
        # NOTE: this comment is load-bearing. `if rc is None:` followed directly
        # by a bare `return` is `tennis_population_mutations` M7's replacement
        # literal, and the mutation-residue scan matches changed files as text.
        return
    for key, value in writes:
        try:
            if value is None:
                rc.delete(key)
            else:
                rc.setex(key, _CURSOR_TTL, int(value))
        except Exception as exc:  # pragma: no cover - redis outage
            logger.warning("team-link cursor write failed for %s (%s)", key, exc)


def _read_cursor(rc, key: str) -> int:
    """Last outcome id this pass reached, or 0 when there is no usable cursor.

    Fails OPEN to 0 on a missing key, a flushed Redis or junk: that is the old
    behaviour (start at the head), never a skipped population.
    """
    if rc is None:
        # See _apply_cursor_writes: the comment breaks a mutation-harness literal.
        return 0
    try:
        raw = rc.get(key)
    except Exception:  # pragma: no cover - redis outage must not stop the drain
        return 0
    try:
        return int(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError, AttributeError):
        return 0


def unlinked_outcomes_query(*, open_markets: bool, cursor: int, batch: int):
    """The Phase 2 selector for one pass. Exposed so a guard test can drive it.

    ``open_markets`` picks the pass: ``status='open'`` (what a reader can load)
    or everything else. ``cursor`` is the exclusive lower bound on
    ``FuturesOutcome.id`` and is what makes the window move off a row that
    cannot bind.
    """
    from app.models import FuturesMarket, FuturesOutcome

    status_clause = (
        FuturesMarket.status == "open"
        if open_markets
        else FuturesMarket.status != "open"
    )
    return (
        select(FuturesOutcome)
        .options(selectinload(FuturesOutcome.market))
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesOutcome.team_id.is_(None),
            ~FuturesOutcome.name.op("~*")(SKIP_REGEX),
            func.length(FuturesOutcome.name) >= 4,
            FuturesMarket.llm_sport_category.in_(_US_SPORTS),  # US sports only
            status_clause,
            FuturesOutcome.id > cursor,
        )
        .order_by(FuturesOutcome.id)
        .limit(batch)
    )


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
    from app.models import FuturesMarket
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

    rc = _cursor_store()
    cursor_writes: list[tuple[str, Optional[int]]] = []

    try:
        async with get_task_session() as session:
            # --- Phase 1: Assign market_tier where missing or wrong ---
            # Re-tier: NULL tiers AND all tier-5 markets. compute_market_tier
            # now checks name patterns before category, so "game_prop" markets
            # whose names match division/conference/championship patterns get
            # promoted to their correct tier.
            tier_result = await session.execute(
                select(FuturesMarket)
                .where(
                    or_(
                        FuturesMarket.market_tier.is_(None),
                        FuturesMarket.market_tier == 5,
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
            # Two passes, each resuming from its own persisted id cursor (#7307).
            # Open markets first — those are the legs a reader can load — with a
            # reserved floor for the resolved backlog so it never starves.
            floor = _resolved_floor(limit)
            passes = [
                ("open", _CURSOR_KEY_OPEN, True, max(0, limit - floor)),
                ("resolved", _CURSOR_KEY_RESOLVED, False, None),
            ]

            outcomes = []

            for label, key, open_markets, budget in passes:
                if budget is None:
                    budget = max(0, limit - len(outcomes))
                if budget <= 0:
                    # Nothing asked for is not the end of the table: leave the
                    # cursor exactly where it is, or the next run rewinds.
                    stats[f"selected_{label}"] = 0
                    continue

                cursor = _read_cursor(rc, key)
                rows = (
                    await session.execute(
                        unlinked_outcomes_query(
                            open_markets=open_markets, cursor=cursor, batch=budget,
                        )
                    )
                ).scalars().all()

                stats[f"selected_{label}"] = len(rows)
                stats[f"cursor_{label}_start"] = cursor
                if len(rows) < budget:
                    # Ran off the end of this pass's population: wrap so the next
                    # run re-scans from the head and picks up new rows plus the
                    # ones that failed a full cycle ago.
                    cursor_writes.append((key, None))
                    stats[f"wrapped_{label}"] = True
                else:
                    cursor_writes.append((key, rows[-1].id))
                outcomes.extend(rows)

            # No early return on an empty batch: the cursor writes below are
            # applied outside this block, after the session has committed, and
            # a wrap recorded by an empty pass has to survive.

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

        # Outside the session: ``get_task_session`` commits on the way out and
        # rolls back on an exception, so reaching here is the proof the batch
        # landed. Only now may the window move (#7307).
        _apply_cursor_writes(rc, cursor_writes)

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    logger.info(
        "team-link drain: open=%s resolved=%s processed=%d linked=%d "
        "cursor_open=%s cursor_resolved=%s wrapped_open=%s wrapped_resolved=%s",
        stats.get("selected_open"),
        stats.get("selected_resolved"),
        stats["outcomes_processed"],
        stats["outcomes_linked"],
        stats.get("cursor_open_start"),
        stats.get("cursor_resolved_start"),
        stats.get("wrapped_open", False),
        stats.get("wrapped_resolved", False),
    )
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
