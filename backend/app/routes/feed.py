"""Unified feed API endpoint.

Merges scored events and scored futures into a single ranked list,
providing a "what's interesting right now" view across all content types.

Supports optional authentication: logged-in users get personalized scoring
based on their favorite teams, sport affinities, and pinned items.
Anonymous users see the generic interestingness feed.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_optional_user
from app.models import Event, Sport, FuturesMarket, FuturesOutcome
from app.models.models import User, UserFavorite, UserPreference, UserPin, Team
from app.services import get_db
from app.utils import (
    compute_highlight,
    get_highlight_label,
    should_highlight,
)
from app.utils.futures_highlights import compute_futures_highlight, should_highlight_futures
from app.utils.feed_reasons import generate_event_reason, generate_futures_reason
from app.utils.personalization import (
    PersonalizationContext,
    compute_event_multiplier,
    compute_futures_multiplier,
)
from app.routes.events import _build_team_lookup, _format_team_data

logger = logging.getLogger(__name__)

router = APIRouter()


def _pulse_label(score: int) -> str:
    """Short Pulse label for feed display."""
    if score >= 90:
        return "Incredible"
    if score >= 81:
        return "Must-Watch"
    if score >= 71:
        return "Exciting"
    if score >= 61:
        return "Engaging"
    if score >= 51:
        return "Competitive"
    return "Steady"


def _team_name_matches(user_team: str, candidate: str) -> bool:
    """Check if a user's followed team name matches a candidate team name.

    The safe direction (user's full team name found inside candidate) is kept
    as-is since full names are specific enough.  The dangerous direction (short
    candidate found inside the longer user team name) requires the candidate to
    match the *trailing words* of the user's team name.  This prevents
    "Celtic" matching "Boston Celtics" and "England" matching "New England
    Patriots" while still allowing "Celtics" and "Patriots" to match.
    """
    user_lower = user_team.lower().strip()
    cand_lower = candidate.lower().strip()
    if not user_lower or not cand_lower:
        return False
    if user_lower == cand_lower:
        return True
    # user team name appears in candidate (safe — full name is specific)
    if user_lower in cand_lower:
        return True
    # candidate appears in user team (dangerous — require suffix word match)
    if cand_lower in user_lower:
        user_words = user_lower.split()
        cand_words = cand_lower.split()
        if len(cand_words) <= len(user_words):
            if user_words[-len(cand_words):] == cand_words:
                return True
    return False


@router.get("")
async def get_feed(
    limit: int = Query(200, description="Number of feed items to return", ge=1, le=5000),
    offset: int = Query(0, description="Offset for pagination", ge=0),
    sport: Optional[str] = Query(None, description="Filter by sport category (e.g., basketball, football)"),
    include_events: bool = Query(True, description="Include game events in feed"),
    include_futures: bool = Query(True, description="Include futures markets in feed"),
    my_teams_only: bool = Query(False, description="Filter to only the user's followed teams"),
    db: AsyncSession = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """
    Get a unified ranked feed of interesting events and futures.

    When authenticated, scores are personalized based on:
    - Favorite teams (follow, local, alma_mater, rival relationships)
    - Sport affinities (boost/suppress by sport preference)
    - Pinned items (boosted in feed)
    - Rival schadenfreude (rival losing = extra boost)

    Returns a single list where each item has:
    - type: "event" or "futures"
    - score: 0-100 interestingness (personalized if authenticated)
    - reason: human-readable explanation
    - headline: short label for badges
    - data: full event or futures payload
    - personalized: whether score was personalized (only present if true)
    """
    now = datetime.now(timezone.utc)

    # my_teams_only requires authentication
    if my_teams_only and not user:
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "has_more": False,
            "my_teams_only": True,
            "requires_auth": True,
        }

    # Load personalization context (one DB query for all user data)
    ctx = await _load_personalization_context(db, user)

    # Build team name set once (used by both scoring functions + response).
    # Only uses Team.name (full ESPN display name like "Brown Bears"), NOT
    # alternate_names (short forms like "Bears", "Brown") which cause false
    # positives: "bears" matching "chicago bears", "brown" matching "browns".
    my_team_names: list[str] = []
    if my_teams_only and user and ctx.team_relations:
        team_ids = list(ctx.team_relations.keys())
        team_name_result = await db.execute(
            select(Team.name).where(Team.id.in_(team_ids))
        )
        my_team_names = [name for (name,) in team_name_result.all() if name]

    feed_items = []

    # === SCORE EVENTS ===
    if include_events:
        event_items = await _score_events(db, now, sport, ctx, my_teams_only=my_teams_only, my_team_names=my_team_names)
        feed_items.extend(event_items)

    # === ENRICH EVENTS WITH TEAM DATA ===
    # _build_team_lookup is cached in-memory (5-min TTL, ~500 teams) — essentially free.
    if feed_items:
        all_team_names = []
        for item in feed_items:
            if item["type"] == "event":
                d = item["data"]
                all_team_names.append(d["home_team"])
                all_team_names.append(d["away_team"])
        if all_team_names:
            team_lookup = await _build_team_lookup(db, all_team_names)
            for item in feed_items:
                if item["type"] == "event":
                    d = item["data"]
                    home_team = team_lookup.get(d["home_team"])
                    away_team = team_lookup.get(d["away_team"])
                    if home_team:
                        d["home_team_data"] = _format_team_data(home_team)
                    if away_team:
                        d["away_team_data"] = _format_team_data(away_team)

    # === SCORE FUTURES ===
    if include_futures:
        futures_items = await _score_futures(db, now, sport, ctx, my_teams_only=my_teams_only, my_team_names=my_team_names)

        # Deduplicate futures by canonical_market_key — keep highest-scoring per group.
        # Without this, "NBA Championship" from Polymarket, Kalshi, and Odds API
        # all appear as separate cards in the feed.
        seen_canonical: dict[str, dict] = {}
        deduped: list[dict] = []
        for fitem in futures_items:
            key = fitem["data"].get("canonical_market_key")
            if key is None:
                deduped.append(fitem)  # No canonical key — can't dedup
                continue
            if key not in seen_canonical or fitem["score"] > seen_canonical[key]["score"]:
                seen_canonical[key] = fitem
        deduped.extend(seen_canonical.values())
        feed_items.extend(deduped)

    # === RANK AND PAGINATE ===
    # Sort by score descending, then by recency as tiebreaker
    feed_items.sort(key=lambda x: (x["score"], x.get("_sort_time", 0)), reverse=True)

    # === DIVERSITY GUARANTEE ===
    # Ensure the feed has a mix of events and futures.
    # Without this, futures can dominate (they get "resolving soon" + "multi source"
    # bonuses that events don't have).
    # For anonymous users, enforce a stronger event bias (events are the core product).
    # Skip diversity enforcement for my_teams_only — show everything matching.
    if not my_teams_only:
        is_anonymous = not ctx.is_authenticated
        feed_items = _ensure_feed_diversity(feed_items, limit, event_pct=0.6 if is_anonymous else 0.4)

    total = len(feed_items)
    paginated = feed_items[offset:offset + limit]

    # Remove internal sort keys
    for item in paginated:
        item.pop("_sort_time", None)

    response = {
        "items": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }

    if my_teams_only:
        response["my_teams_only"] = True
        if my_team_names:
            response["matched_teams"] = my_team_names

    # Include personalization metadata if authenticated
    if ctx.is_authenticated:
        response["personalized"] = True
        response["personalization"] = {
            "team_count": len(ctx.team_relations),
            "sport_affinities_count": len(ctx.sport_affinities),
            "pinned_events": len(ctx.pinned_event_ids),
            "pinned_futures": len(ctx.pinned_futures_ids),
        }

    return response


async def _load_personalization_context(
    db: AsyncSession,
    user: Optional[User],
) -> PersonalizationContext:
    """Load all user personalization data into a context object.

    Single query pattern: load favorites, preferences, and pins in parallel-ish
    SQLAlchemy queries, then assemble into the context.
    """
    if not user:
        return PersonalizationContext()

    # Load user favorites, preferences, and pins in parallel
    favorites_result, prefs_result, pins_result = await asyncio.gather(
        db.execute(select(UserFavorite).where(UserFavorite.user_id == user.id)),
        db.execute(select(UserPreference).where(UserPreference.user_id == user.id)),
        db.execute(select(UserPin).where(UserPin.user_id == user.id)),
    )

    favorites = favorites_result.scalars().all()

    team_relations: dict[int, set[str]] = {}
    team_weights: dict[int, float] = {}
    for fav in favorites:
        if fav.team_id not in team_relations:
            team_relations[fav.team_id] = set()
        team_relations[fav.team_id].add(fav.relation_type)
        team_weights[fav.team_id] = float(fav.weight) if fav.weight else 1.0

    prefs = prefs_result.scalar_one_or_none()
    sport_affinities = prefs.sport_affinities if prefs and prefs.sport_affinities else {}

    pins = pins_result.scalars().all()
    pinned_event_ids = {p.target_id for p in pins if p.pin_type == "event"}
    pinned_futures_ids = {p.target_id for p in pins if p.pin_type == "future"}

    # Load roster player names from followed teams for player-futures matching
    roster_player_names: set[str] = set()
    followed_team_ids = [
        tid for tid, rels in team_relations.items()
        if "follow" in rels or "local" in rels or "alma_mater" in rels
    ]
    if followed_team_ids:
        teams_result = await db.execute(
            select(Team.roster_players).where(
                Team.id.in_(followed_team_ids),
                Team.roster_players.isnot(None),
            )
        )
        for (roster,) in teams_result.all():
            if isinstance(roster, list):
                for item in roster:
                    if isinstance(item, dict):
                        name = item.get("name")
                    elif isinstance(item, str):
                        name = item
                    else:
                        continue
                    if name:
                        roster_player_names.add(name.lower())

    return PersonalizationContext(
        team_relations=team_relations,
        team_weights=team_weights,
        sport_affinities=sport_affinities,
        pinned_event_ids=pinned_event_ids,
        pinned_futures_ids=pinned_futures_ids,
        roster_player_names=roster_player_names,
        is_authenticated=True,
    )


async def _score_events(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
) -> list[dict]:
    """Score and format events for the feed.

    PERFORMANCE: Uses opening odds (already on Event model) for scoring
    instead of re-aggregating from odds_snapshots. This avoids the expensive
    window-function query that was taking 25+ seconds with 130+ live events.
    Opening odds are accurate enough for ranking — the full aggregated odds
    are shown when the user clicks through to the event detail page.
    """
    # Wider time windows for my_teams_only — users want to see all their
    # team's upcoming games and recent results.
    # 72h completed window ensures yesterday's and weekend games are visible
    # when checking on Monday morning (24h was too tight — games disappeared).
    if my_teams_only:
        recent_cutoff = now - timedelta(hours=72)
        upcoming_cutoff = now + timedelta(days=7)
    else:
        # Tighter time windows than the full events list to keep query fast
        recent_cutoff = now - timedelta(hours=24)
        upcoming_cutoff = now + timedelta(hours=12)
    # Guard against events incorrectly stuck in "live" status with future
    # commence_times (e.g., from Scores API returning upcoming events as
    # completed=False). Only include "live" events that have actually started.
    live_start_cutoff = now + timedelta(hours=1)  # Small buffer for clock drift

    query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .options(selectinload(Event.sport))
        .where(
            or_(
                and_(
                    Event.status == "live",
                    Event.commence_time <= live_start_cutoff,
                ),
                and_(
                    Event.status == "scheduled",
                    Event.commence_time >= now,
                    Event.commence_time <= upcoming_cutoff,
                ),
                and_(
                    Event.status.in_(["completed", "closed"]),
                    Event.commence_time >= recent_cutoff,
                ),
            )
        )
    )

    if sport_filter:
        query = query.where(Sport.key.ilike(f"%{sport_filter}%"))

    # For my_teams_only, push team filtering to SQL so we don't miss events
    # beyond the safety cap (the 7-day window can have 1000+ events across
    # all sports, but only ~20-40 involve the user's teams).
    if my_teams_only:
        team_conditions = []
        user_team_ids_list = list(set(ctx.team_relations.keys())) if ctx.team_relations else []
        if user_team_ids_list:
            team_conditions.append(Event.home_team_id.in_(user_team_ids_list))
            team_conditions.append(Event.away_team_id.in_(user_team_ids_list))
        if my_team_names:
            for tn in my_team_names:
                escaped = tn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                team_conditions.append(Event.home_team_name.ilike(f"%{escaped}%"))
                team_conditions.append(Event.away_team_name.ilike(f"%{escaped}%"))
        if team_conditions:
            query = query.where(or_(*team_conditions))
        else:
            # No teams → nothing to show
            return []
        query = query.limit(200)  # Safety cap (user's teams only)
    else:
        query = query.limit(500)  # Safety cap (all events)

    result = await db.execute(query)
    events = result.scalars().all()

    if not events:
        return []

    # Score each event using stored opening odds (no snapshot query needed)
    scored_items = []
    user_team_ids = set(ctx.team_relations.keys()) if my_teams_only else set()

    for event in events:
        # my_teams_only: skip events that don't involve the user's teams
        if my_teams_only:
            # Try team_id matching first (fast, when IDs are linked)
            event_team_ids = {event.home_team_id, event.away_team_id} - {None}
            matched_by_id = bool(event_team_ids & user_team_ids)

            # Fall back to name matching (handles events without team_id links)
            matched_by_name = False
            if not matched_by_id and my_team_names:
                home_name = event.home_team_name or ""
                away_name = event.away_team_name or ""
                for team_name in (my_team_names or []):
                    if _team_name_matches(team_name, home_name):
                        matched_by_name = True
                        break
                    if _team_name_matches(team_name, away_name):
                        matched_by_name = True
                        break

            if not matched_by_id and not matched_by_name:
                continue

        opening_home_prob = float(event.opening_home_probability) if event.opening_home_probability else None
        opening_away_prob = float(event.opening_away_probability) if event.opening_away_probability else None

        # Skip events with no odds — the whole point of the site is probabilities.
        # Events can exist without odds if they were discovered but haven't been
        # polled yet, or if all bookmakers were filtered as stale.
        if opening_home_prob is None:
            continue

        # For scoring, use opening odds as "current" — good enough for ranking.
        # The highlight scorer detects closeness, upset potential, etc. from these.
        current_home_prob = opening_home_prob
        current_away_prob = opening_away_prob

        # Auto-detect preseason as exhibition from sport key when
        # llm_importance isn't set (ESPN doesn't sync preseason sport keys)
        importance = event.llm_importance
        if not importance or importance == "unknown":
            sport_key_str = event.sport.key if event.sport else ""
            if "preseason" in sport_key_str:
                importance = "exhibition"

        highlight_result = compute_highlight(
            status=event.status,
            commence_time=event.commence_time,
            sport_key=event.sport.key if event.sport else None,
            current_home_prob=current_home_prob,
            current_away_prob=current_away_prob,
            current_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
            current_over_under=float(event.opening_over_under) if event.opening_over_under else None,
            opening_home_prob=opening_home_prob,
            opening_away_prob=opening_away_prob,
            opening_home_spread=float(event.opening_home_spread) if event.opening_home_spread else None,
            opening_over_under=float(event.opening_over_under) if event.opening_over_under else None,
            opening_favorite=event.opening_favorite,
            now=now,
            home_team_name=event.home_team_name,
            away_team_name=event.away_team_name,
            importance=importance,
        )

        base_score = highlight_result.score

        # Boost completed events that had high Pulse scores — these are the
        # "fascinating outcomes" worth surfacing even hours later.
        if event.status in ("completed", "closed") and event.raw_gei:
            pulse_score = max(1, min(100, round(float(event.raw_gei) * 100)))
            if pulse_score >= 80:
                base_score += 25  # Must-Watch / Incredible — always surface
                highlight_result.reasons.append("high_pulse")
            elif pulse_score >= 60:
                base_score += 15  # Engaging / Exciting — good boost
                highlight_result.reasons.append("good_pulse")

        # Apply personalization multiplier
        p_result = compute_event_multiplier(
            ctx=ctx,
            home_team_id=event.home_team_id,
            away_team_id=event.away_team_id,
            sport_key=event.sport.key if event.sport else None,
            event_id=event.id,
            home_score=event.home_score,
            away_score=event.away_score,
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

        # --- "Nah" sport hard filter ---
        # If the user explicitly said "Nah" to this sport, don't show it
        # UNLESS it's a championship or playoff game.  A user who said "Nah"
        # to soccer shouldn't see Champions League regular matches, but a
        # World Cup Final is a genuine cultural event worth surfacing.
        is_nah = any("sport_nah" in r for r in p_result.reasons)
        if is_nah and not my_teams_only:
            if importance not in ("championship", "playoff"):
                continue
            # Championship/playoff in a "Nah" sport: override but explain
            personalized_score = max(personalized_score, 35)

        # --- "If it's wild" sport — higher bar ---
        # The user said "If it's wild" (affinity 0.1) — only show if something
        # genuinely unusual is happening (upset, lead change, big swing, playoff).
        # A live close game alone isn't enough.
        is_low_affinity = any("sport_suppress" in r for r in p_result.reasons)
        if is_low_affinity and not my_teams_only:
            # Require a genuinely notable game — live+close+tier1 = 75 * 0.7 = 52
            # isn't enough. Need upset(+20), lead change(+8), big swing(+15),
            # or playoff(+15) to clear the bar.
            min_score = 55
        elif my_teams_only:
            min_score = 0
        elif p_result.is_personalized and p_result.multiplier >= 1.0:
            min_score = 10
        else:
            min_score = 30
        if personalized_score < min_score:
            continue

        # Generate reason text
        reason = generate_event_reason(
            home_team=event.home_team_name,
            away_team=event.away_team_name,
            status=event.status,
            highlight_reasons=highlight_result.reasons,
            home_probability=current_home_prob,
            away_probability=current_away_prob,
            opening_home_prob=opening_home_prob,
            home_score=event.home_score,
            away_score=event.away_score,
        )

        # Build compact event data for the feed
        event_data = {
            "id": event.id,
            "external_id": event.external_id,
            "sport": event.sport.key if event.sport else None,
            "sport_name": event.sport.name if event.sport else None,
            "home_team": event.home_team_name,
            "away_team": event.away_team_name,
            "commence_time": event.commence_time.isoformat(),
            "status": event.status,
            "home_score": event.home_score,
            "away_score": event.away_score,
        }

        if current_home_prob is not None:
            event_data["current_odds"] = {
                "home_probability": current_home_prob,
                "away_probability": current_away_prob,
            }

        if opening_home_prob is not None:
            event_data["opening_odds"] = {
                "home_probability": opening_home_prob,
                "away_probability": opening_away_prob,
                "favorite": event.opening_favorite,
            }

        # Include highlight metadata (label, flags) for frontend display
        label = get_highlight_label(highlight_result)
        if label:
            event_data["highlight"] = {"label": label}

        # Include Pulse score for completed/closed events
        if event.status in ("completed", "closed") and event.raw_gei:
            raw_score = max(1, min(100, round(float(event.raw_gei) * 100)))
            event_data["pulse"] = {
                "score": raw_score,
                "label": _pulse_label(raw_score),
            }

        # Compute sort time: live games first (far future), then by commence_time
        sort_time = event.commence_time.timestamp()
        if event.status == "live":
            sort_time = now.timestamp() + 86400  # Push live to top

        item = {
            "type": "event",
            "score": personalized_score,
            "reason": reason,
            "headline": get_highlight_label(highlight_result),
            "data": event_data,
            "_sort_time": sort_time,
        }

        # Include personalization debug info when score was boosted/suppressed
        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


async def _score_futures(
    db: AsyncSession,
    now: datetime,
    sport_filter: Optional[str],
    ctx: PersonalizationContext,
    my_teams_only: bool = False,
    my_team_names: Optional[list] = None,
) -> list[dict]:
    """Score and format futures markets for the feed.

    Uses per-category queries to guarantee diversity. A single big query
    sorted by resolution_date is dominated by crypto's 8,955 five-minute
    markets, so we query each category separately.
    """
    # === BASE FILTERS ===
    base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        ~FuturesMarket.name.ilike('% vs %'),
        ~FuturesMarket.name.ilike('% vs. %'),
        ~FuturesMarket.name.ilike('% at %'),
    ]

    base_options = [
        selectinload(FuturesMarket.outcomes),
        selectinload(FuturesMarket.sport),
    ]

    # For my_teams_only: use full Team.name (not alternate_names) to avoid false positives.
    user_team_ids = set(ctx.team_relations.keys()) if ctx.team_relations else set()

    # === SINGLE QUERY WITH ROW_NUMBER() PARTITION ===
    # Instead of 29 per-category queries (~90 round-trips with selectinload),
    # use a single query with ROW_NUMBER() OVER (PARTITION BY category) to
    # get the top PER_CAT_LIMIT markets per category in one round-trip.
    PER_CAT_LIMIT = 10

    # Step 1: Subquery to assign row numbers per category
    category_col = func.coalesce(
        FuturesMarket.llm_sport_category, "__null__"
    )
    row_num = func.row_number().over(
        partition_by=category_col,
        order_by=FuturesMarket.resolution_date.asc().nulls_last(),
    ).label("_rn")

    id_filters = list(base_filters)
    if sport_filter:
        id_filters.append(
            or_(
                FuturesMarket.llm_sport_category.ilike(f"%{sport_filter}%"),
                FuturesMarket.external_id.ilike(f"%{sport_filter}%"),
            )
        )

    subq = (
        select(FuturesMarket.id, row_num)
        .where(*id_filters)
        .subquery()
    )

    # Step 2: Load full market objects (with outcomes + sport) for the top N per category
    main_query = (
        select(FuturesMarket)
        .options(*base_options)
        .join(subq, FuturesMarket.id == subq.c.id)
        .where(subq.c._rn <= PER_CAT_LIMIT)
    )

    result = await db.execute(main_query)
    markets = list(result.scalars().unique().all())

    if not markets:
        return []

    # Build canonical key → source count map for cross-source scoring
    canonical_source_counts = await _get_canonical_source_counts(db)

    scored_items = []
    for market in markets:
        # Prepare outcome data for scoring
        outcomes_data = []
        leader_name = None
        leader_prob = None

        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )

        for o in sorted_outcomes[:10]:  # Score based on top 10 outcomes
            prob = float(o.current_probability) if o.current_probability else None
            change = float(o.probability_change_24h) if o.probability_change_24h else None
            outcomes_data.append({
                "name": o.name,
                "probability": prob,
                "probability_change_24h": change,
                "rank": o.rank,
                "rank_change_24h": o.rank_change_24h,
                "opening_probability": float(o.opening_probability) if o.opening_probability else None,
            })

        if sorted_outcomes:
            leader = sorted_outcomes[0]
            leader_name = leader.name
            leader_prob = float(leader.current_probability) if leader.current_probability else None

        # Get source count from canonical key
        source_count = 1
        if market.canonical_market_key:
            source_count = canonical_source_counts.get(market.canonical_market_key, 1)

        highlight_result = compute_futures_highlight(
            market_tier=market.market_tier,
            sport_category=market.llm_sport_category,
            resolution_date=market.resolution_date,
            outcomes=outcomes_data,
            source_count=source_count,
            now=now,
            market_name=market.name,
        )

        base_score = highlight_result.score

        # Apply personalization multiplier
        outcome_team_ids = [o.team_id for o in market.outcomes if o.team_id is not None]

        # my_teams_only: skip futures that don't involve the user's teams
        if my_teams_only:
            matched_by_id = bool(set(outcome_team_ids) & user_team_ids)

            # Fall back to outcome name matching when team_ids aren't linked
            matched_by_name = False
            if not matched_by_id and my_team_names:
                for o in market.outcomes:
                    if o.name:
                        for team_name in (my_team_names or []):
                            if _team_name_matches(team_name, o.name):
                                matched_by_name = True
                                break
                    if matched_by_name:
                        break

            if not matched_by_id and not matched_by_name:
                continue

        # Collect matched outcome details for "why is this here?" context
        matched_outcomes_list = []
        if my_teams_only and user_team_ids:
            for o in market.outcomes:
                is_match = False
                if o.team_id and o.team_id in user_team_ids:
                    is_match = True
                elif my_team_names and o.name:
                    for team_name in (my_team_names or []):
                        if _team_name_matches(team_name, o.name):
                            is_match = True
                            break
                if is_match:
                    matched_outcomes_list.append({
                        "name": o.name,
                        "probability": float(o.current_probability) if o.current_probability else None,
                        "rank": o.rank,
                        "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
                    })

        outcome_names = [o.name for o in market.outcomes if o.name]
        p_result = compute_futures_multiplier(
            ctx=ctx,
            sport_category=market.llm_sport_category,
            outcome_team_ids=outcome_team_ids,
            futures_market_id=market.id,
            sport_key=market.sport.key if market.sport else None,
            outcome_names=outcome_names,
        )
        personalized_score = min(100, int(base_score * p_result.multiplier))

        # --- "Nah" category hard filter for futures ---
        is_nah = any("sport_nah" in r for r in p_result.reasons)
        if is_nah and not my_teams_only:
            continue  # No override for futures — no "championship" equivalent

        # "If it's wild" — higher bar for low-affinity futures too
        is_low_affinity = any("sport_suppress" in r for r in p_result.reasons)
        if is_low_affinity and not my_teams_only and personalized_score < 55:
            continue

        # Filter low-signal futures (my_teams_only shows everything)
        if not my_teams_only and personalized_score < 35:
            continue

        # Find the actual biggest mover (with sign) for reason generation
        top_mover_name = highlight_result.top_mover_name
        top_mover_change = None
        if top_mover_name:
            for o in outcomes_data:
                if o["name"] == top_mover_name and o.get("probability_change_24h"):
                    top_mover_change = o["probability_change_24h"]
                    break

        reason = generate_futures_reason(
            market_name=market.name,
            highlight_reasons=highlight_result.reasons,
            top_mover_name=top_mover_name,
            top_mover_change=top_mover_change,
            leader_name=leader_name,
            leader_probability=leader_prob,
            source_count=source_count,
        )

        # Build compact futures data for the feed
        top_outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "rank": o.rank,
                "movement": float(o.probability_change_24h) if o.probability_change_24h else None,
            }
            for o in sorted_outcomes[:3]  # Show top 3 in feed card
        ]

        futures_data = {
            "id": market.id,
            "name": market.name,
            "sport": market.sport.key if market.sport else None,
            "sport_name": market.sport.name if market.sport else None,
            "llm_sport_category": market.llm_sport_category,
            "source": market.source,
            "source_count": source_count,
            "market_tier": market.market_tier,
            "status": market.status,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "top_outcomes": top_outcomes_data,
            "outcome_count": len(market.outcomes),
            "canonical_market_key": market.canonical_market_key,
        }

        if matched_outcomes_list:
            futures_data["matched_outcomes"] = matched_outcomes_list

        # Sort time: higher-tier markets and markets resolving soon get priority
        sort_time = now.timestamp()
        if market.resolution_date:
            # Closer resolution = more timely
            days_until = (market.resolution_date - now).total_seconds()
            sort_time = now.timestamp() + max(0, 86400 * 30 - days_until)

        item = {
            "type": "futures",
            "score": personalized_score,
            "reason": reason,
            "headline": highlight_result.primary_reason,
            "data": futures_data,
            "_sort_time": sort_time,
        }

        if p_result.is_personalized:
            item["personalized"] = True
            item["base_score"] = base_score
            item["multiplier"] = round(p_result.multiplier, 2)
            item["personalization_reasons"] = p_result.reasons

        scored_items.append(item)

    return scored_items


_canonical_source_counts_cache: Optional[dict[str, int]] = None
_canonical_source_counts_ts: float = 0.0
_CANONICAL_CACHE_TTL = 300  # 5 minutes


async def _get_canonical_source_counts(db: AsyncSession) -> dict[str, int]:
    """Get source count for each canonical market key (cached 5 min)."""
    import time

    global _canonical_source_counts_cache, _canonical_source_counts_ts
    now = time.time()
    if _canonical_source_counts_cache is not None and (now - _canonical_source_counts_ts) < _CANONICAL_CACHE_TTL:
        return _canonical_source_counts_cache

    result = await db.execute(
        select(
            FuturesMarket.canonical_market_key,
            func.count(func.distinct(FuturesMarket.source)).label("source_count"),
        )
        .where(FuturesMarket.canonical_market_key.isnot(None))
        .group_by(FuturesMarket.canonical_market_key)
    )
    cache = {row.canonical_market_key: row.source_count for row in result.all()}
    _canonical_source_counts_cache = cache
    _canonical_source_counts_ts = now
    return cache


def _ensure_feed_diversity(
    items: list[dict],
    target_size: int,
    event_pct: float = 0.4,
) -> list[dict]:
    """
    Ensure the feed has a healthy mix of events and futures.

    The feed should lead with real games when available. Without this,
    futures can dominate because they get "resolving soon" + "multi source"
    bonuses that events don't have.

    Strategy:
    - Reserve at least event_pct of slots for events (if available).
    - Among the top N items, interleave so events aren't all pushed down.
    - Preserves score ordering within each type.
    """
    if not items:
        return items

    events = [i for i in items if i["type"] == "event"]
    futures = [i for i in items if i["type"] == "futures"]

    # If one type is empty, nothing to balance
    if not events or not futures:
        return items

    # Determine minimum event slots (event_pct of target, at least 3)
    min_event_slots = max(3, int(target_size * event_pct))
    min_event_slots = min(min_event_slots, len(events))

    # Check if the natural ordering already has enough events in the top N
    top_n = items[:target_size]
    events_in_top = sum(1 for i in top_n if i["type"] == "event")

    if events_in_top >= min_event_slots:
        # Natural ordering is fine
        return items

    # Need to promote events. Take top events that aren't already in top N,
    # and interleave them with the existing top items.
    result = []
    event_idx = 0
    futures_idx = 0
    events_placed = 0

    for slot in range(min(target_size, len(items))):
        need_event = events_placed < min_event_slots and event_idx < len(events)

        # Every 2-3 items, prefer an event if we need more
        if need_event and (slot % 3 != 2 or futures_idx >= len(futures)):
            result.append(events[event_idx])
            event_idx += 1
            events_placed += 1
        elif futures_idx < len(futures):
            result.append(futures[futures_idx])
            futures_idx += 1
        elif event_idx < len(events):
            result.append(events[event_idx])
            event_idx += 1
            events_placed += 1

    # Append remaining items (beyond target_size) in original order
    placed_ids = set()
    for item in result:
        data = item.get("data", {})
        key = (item["type"], data.get("id"))
        placed_ids.add(key)

    for item in items:
        data = item.get("data", {})
        key = (item["type"], data.get("id"))
        if key not in placed_ids:
            result.append(item)

    return result
