"""
User data routes: pins, preferences, team search, onboarding.

All endpoints require authentication unless noted otherwise.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete, and_, or_, case, cast, func, String, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_current_user
from app.models.models import (
    User, UserPin, UserFavorite, UserPreference, Team,
    FuturesMarket, FuturesOutcome,
)
from app.services.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Metro alias mapping for city → teams lookup
# =============================================================================

# Maps brand/location names to their metro area aliases.
# When a user types "Boston", we also search for "New England" and vice versa.
METRO_ALIASES: dict[str, list[str]] = {
    "golden state": ["san francisco", "bay area", "oakland", "santa cruz"],
    "new england": ["boston", "foxborough", "foxboro"],
    "brooklyn": ["new york", "nyc"],
    "new york": ["brooklyn", "nyc"],
    "carolina": ["charlotte", "raleigh"],
    "tampa bay": ["tampa", "st. petersburg"],
    "tampa": ["tampa bay", "st. petersburg"],
    "dc": ["washington", "d.c."],
    "washington": ["dc", "d.c."],
    "minnesota": ["minneapolis", "twin cities", "st. paul"],
    "indiana": ["indianapolis"],
    "indianapolis": ["indiana"],
    "arizona": ["phoenix", "tempe", "glendale"],
    "phoenix": ["arizona"],
    "colorado": ["denver"],
    "denver": ["colorado"],
    "utah": ["salt lake city", "salt lake"],
    "salt lake city": ["utah"],
    "tennessee": ["nashville", "memphis"],
    "nashville": ["tennessee"],
    "miami": ["south florida", "fort lauderdale", "sunrise"],
    "dallas": ["arlington", "dfw"],
    "san francisco": ["golden state", "bay area", "oakland", "santa cruz"],
    "bay area": ["golden state", "san francisco", "oakland", "santa cruz"],
    "boston": ["new england", "foxborough"],
    "los angeles": ["la", "anaheim", "inglewood"],
    "la": ["los angeles", "anaheim", "inglewood"],
    "chicago": ["chi"],
    "detroit": ["michigan"],
    "pittsburgh": ["pennsylvania"],
    "philadelphia": ["philly"],
    "philly": ["philadelphia"],
}


def _expand_location_query(query: str) -> list[str]:
    """Expand a location query to include metro aliases.

    Returns a list of search terms including the original query
    and any known aliases.
    """
    q_lower = query.lower().strip()
    terms = [q_lower]

    # Check if the query matches any alias key
    if q_lower in METRO_ALIASES:
        terms.extend(METRO_ALIASES[q_lower])

    # Also check if the query is a value in any alias list
    for key, aliases in METRO_ALIASES.items():
        if q_lower in [a.lower() for a in aliases] and key not in terms:
            terms.append(key)

    return list(set(terms))


# =============================================================================
# Sport affinity key mapping
# =============================================================================

# Maps user-friendly sport keys to backend sport_key prefixes.
# For sports, these map to The Odds API sport keys.
# For non-sports categories, these map to llm_sport_category / category_tag values
# used by prediction markets (Polymarket, Kalshi).
SPORT_AFFINITY_MAPPING: dict[str, list[str]] = {
    # --- Sports (split pro vs college for football + basketball) ---
    "nfl": ["americanfootball_nfl"],
    "college_football": ["americanfootball_ncaaf"],
    "nba": ["basketball_nba"],
    "college_basketball": ["basketball_ncaab", "basketball_wncaab"],
    # Legacy keys — still accepted on input, map to the split keys' backend values
    "football": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "basketball": ["basketball_nba", "basketball_ncaab", "basketball_wncaab"],
    "baseball": ["baseball_mlb"],
    "hockey": ["icehockey_nhl"],
    "soccer": ["soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga",
               "soccer_germany_bundesliga", "soccer_italy_serie_a",
               "soccer_france_ligue_one", "soccer_uefa_champs_league"],
    # Golf tour split (like NFL/College Football)
    "golf_pga": ["golf_masters_tournament_winner", "golf_pga_championship_winner",
                 "golf_the_open_championship_winner", "golf_us_open_winner", "golf_pga"],
    "golf_dp_world": ["golf_dp_world"],
    "golf_lpga": ["golf_lpga"],
    "golf_liv": ["golf_liv"],
    # Legacy key — maps to ALL golf backend keys (backward compat)
    "golf": ["golf_masters_tournament_winner", "golf_pga_championship_winner",
             "golf_the_open_championship_winner", "golf_us_open_winner",
             "golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"],
    "tennis": ["tennis_atp_french_open", "tennis_atp_us_open",
               "tennis_atp_wimbledon", "tennis_atp_australian_open"],
    "mma": ["mma_mixed_martial_arts"],
    "boxing": ["boxing_boxing"],
    "cricket": ["cricket_icc_world_cup", "cricket_test_match"],
    "rugby": ["rugbyleague_nrl", "rugbyunion_six_nations"],
    "motorsport": ["motorsport_formula1"],
    "esports": ["esports_lol", "esports_csgo", "esports_dota2", "esports_valorant"],
    # --- Beyond Sports (prediction market categories) ---
    "politics": ["politics"],
    "entertainment": ["entertainment"],
    "crypto": ["crypto"],
    "economics": ["economics"],
    "tech": ["tech"],
    "weather": ["weather"],
    "geopolitics": ["geopolitics"],
    "culture": ["culture"],
}

# Reverse mapping for display: backend key → friendly category.
# Prefer split keys (nfl, college_football, etc.) over legacy keys (football, basketball).
SPORT_KEY_TO_CATEGORY: dict[str, str] = {}
# Legacy keys first (will be overwritten by split keys below)
_LEGACY_AFFINITY_KEYS = {"football", "basketball", "golf"}
for category, keys in SPORT_AFFINITY_MAPPING.items():
    if category in _LEGACY_AFFINITY_KEYS:
        for key in keys:
            if key not in SPORT_KEY_TO_CATEGORY:
                SPORT_KEY_TO_CATEGORY[key] = category
    else:
        for key in keys:
            SPORT_KEY_TO_CATEGORY[key] = category


def _expand_sport_affinities(frontend_affinities: dict[str, float]) -> dict[str, float]:
    """Expand user-friendly sport keys to full backend sport_key format.

    Input: {"football": 1.0, "basketball": 0.3}
    Output: {"americanfootball_nfl": 1.0, "americanfootball_ncaaf": 1.0,
             "basketball_nba": 0.3, "basketball_ncaab": 0.3, ...}
    """
    expanded: dict[str, float] = {}
    for sport_key, weight in frontend_affinities.items():
        backend_keys = SPORT_AFFINITY_MAPPING.get(sport_key, [])
        if backend_keys:
            for bk in backend_keys:
                expanded[bk] = weight
        else:
            # Pass through unrecognized keys (future-proofing)
            expanded[sport_key] = weight
    return expanded


def _compress_sport_affinities(backend_affinities: dict[str, float]) -> dict[str, float]:
    """Compress backend sport_key affinities back to user-friendly keys.

    Takes the max weight for each category.
    Input: {"americanfootball_nfl": 1.0, "americanfootball_ncaaf": 0.3}
    Output: {"nfl": 1.0, "college_football": 0.3}

    Uses SPORT_KEY_TO_CATEGORY which prefers split keys (nfl, college_football,
    nba, college_basketball) over legacy keys (football, basketball).
    """
    compressed: dict[str, float] = {}
    for backend_key, weight in backend_affinities.items():
        category = SPORT_KEY_TO_CATEGORY.get(backend_key)
        if category:
            compressed[category] = max(compressed.get(category, 0.0), weight)
        # Skip unknown keys in compressed view
    return compressed


# =============================================================================
# Schemas
# =============================================================================

class PinsResponse(BaseModel):
    """All pinned items for a user."""
    events: list[int]
    futures: list[int]


class AddPinRequest(BaseModel):
    """Add a single pin."""
    pin_type: str  # "event" or "future"
    target_id: int


class BulkPinsRequest(BaseModel):
    """Bulk upsert pins (for localStorage migration)."""
    events: list[int] = []
    futures: list[int] = []


class TeamSearchResult(BaseModel):
    """Team search result for autocomplete."""
    id: int
    name: str
    location: Optional[str]
    sport_key: Optional[str]
    logo_url: Optional[str]
    abbreviation: Optional[str]


class TeamRef(BaseModel):
    """Minimal team reference for onboarding submission."""
    team_id: int


class OnboardingRequest(BaseModel):
    """Complete onboarding data submitted from the frontend."""
    home_location: Optional[str] = None
    local_teams: list[TeamRef] = []
    follow_teams: list[TeamRef] = []  # Explicitly followed teams (any location)
    alma_mater_teams: list[TeamRef] = []
    rival_teams: list[TeamRef] = []
    sport_affinities: dict[str, float] = {}  # e.g., {"football": 1.0, "basketball": 0.3}
    raw_inputs: dict = {}  # Saved verbatim for debugging


class FavoriteItem(BaseModel):
    """A team favorite with metadata for display."""
    team_id: int
    team_name: str
    relation_type: str
    sport_key: Optional[str]
    logo_url: Optional[str]
    source: str


class PreferencesResponse(BaseModel):
    """Full preferences + favorites for the current user."""
    home_location: Optional[str]
    sport_affinities: dict[str, float]  # Compressed (user-friendly keys)
    onboarding_completed: bool
    favorites: list[FavoriteItem]


# =============================================================================
# Pin endpoints
# =============================================================================

MAX_PINS_PER_TYPE = 25  # More generous server-side limit than the 6 in localStorage


@router.get("/pins", response_model=PinsResponse)
async def get_pins(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all pinned event and futures IDs for the current user."""
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    pins = result.scalars().all()

    return PinsResponse(
        events=[p.target_id for p in pins if p.pin_type == "event"],
        futures=[p.target_id for p in pins if p.pin_type == "future"],
    )


@router.put("/pins", response_model=PinsResponse)
async def bulk_upsert_pins(
    body: BulkPinsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk upsert pins. Used for migrating localStorage pins to the database.
    Merges with existing pins (doesn't delete unmentioned pins).
    """
    # Get existing pins
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    existing = result.scalars().all()
    existing_keys = {(p.pin_type, p.target_id) for p in existing}

    # Add new event pins
    for event_id in body.events[:MAX_PINS_PER_TYPE]:
        if ("event", event_id) not in existing_keys:
            db.add(UserPin(user_id=user.id, pin_type="event", target_id=event_id))

    # Add new futures pins
    for future_id in body.futures[:MAX_PINS_PER_TYPE]:
        if ("future", future_id) not in existing_keys:
            db.add(UserPin(user_id=user.id, pin_type="future", target_id=future_id))

    await db.flush()

    # Return the merged result
    result = await db.execute(
        select(UserPin).where(UserPin.user_id == user.id)
    )
    pins = result.scalars().all()

    return PinsResponse(
        events=[p.target_id for p in pins if p.pin_type == "event"],
        futures=[p.target_id for p in pins if p.pin_type == "future"],
    )


@router.post("/pins", status_code=status.HTTP_201_CREATED)
async def add_pin(
    body: AddPinRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a single pin."""
    if body.pin_type not in ("event", "future"):
        raise HTTPException(status_code=400, detail="pin_type must be 'event' or 'future'")

    # Check limit
    result = await db.execute(
        select(UserPin).where(
            and_(UserPin.user_id == user.id, UserPin.pin_type == body.pin_type)
        )
    )
    current_count = len(result.scalars().all())
    if current_count >= MAX_PINS_PER_TYPE:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PINS_PER_TYPE} pins per type")

    # Check for duplicate
    result = await db.execute(
        select(UserPin).where(
            and_(
                UserPin.user_id == user.id,
                UserPin.pin_type == body.pin_type,
                UserPin.target_id == body.target_id,
            )
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_pinned"}

    db.add(UserPin(
        user_id=user.id,
        pin_type=body.pin_type,
        target_id=body.target_id,
    ))

    return {"status": "pinned"}


@router.delete("/pins/{pin_type}/{target_id}")
async def remove_pin(
    pin_type: str,
    target_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a pin."""
    if pin_type not in ("event", "future"):
        raise HTTPException(status_code=400, detail="pin_type must be 'event' or 'future'")

    await db.execute(
        delete(UserPin).where(
            and_(
                UserPin.user_id == user.id,
                UserPin.pin_type == pin_type,
                UserPin.target_id == target_id,
            )
        )
    )

    return {"status": "unpinned"}


# =============================================================================
# Onboarding & Preferences endpoints
# =============================================================================

@router.post("/onboarding")
async def submit_onboarding(
    body: OnboardingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save complete onboarding data. Replaces any existing onboarding-sourced
    favorites and preferences.

    This is a batch endpoint — saves location, teams, sport affinities,
    and raw inputs all at once.
    """
    # 1. Delete existing onboarding-sourced favorites
    await db.execute(
        delete(UserFavorite).where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.source == "onboarding",
            )
        )
    )

    # 2. Insert new favorites
    # With the new constraint (user_id, team_id, relation_type), a team can have
    # multiple relations (e.g., both "local" and "follow"). We track (team_id, relation_type)
    # pairs to prevent exact duplicates within a single submission.
    seen_pairs: set[tuple[int, str]] = set()

    def _add_favorite(team_id: int, relation_type: str) -> None:
        pair = (team_id, relation_type)
        if pair in seen_pairs:
            return
        seen_pairs.add(pair)
        db.add(UserFavorite(
            user_id=user.id,
            team_id=team_id,
            relation_type=relation_type,
            source="onboarding",
            weight=1.0,
        ))

    for team_ref in body.local_teams:
        _add_favorite(team_ref.team_id, "local")

    for team_ref in body.follow_teams:
        _add_favorite(team_ref.team_id, "follow")

    for team_ref in body.alma_mater_teams:
        _add_favorite(team_ref.team_id, "alma_mater")

    for team_ref in body.rival_teams:
        _add_favorite(team_ref.team_id, "rival")

    # 3. Expand sport affinities to backend keys
    expanded_affinities = _expand_sport_affinities(body.sport_affinities)

    # 4. Update preferences
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs:
        prefs.home_location = body.home_location
        prefs.sport_affinities = expanded_affinities
        prefs.onboarding_completed = True
        prefs.onboarding_raw = body.raw_inputs
    else:
        prefs = UserPreference(
            user_id=user.id,
            home_location=body.home_location,
            sport_affinities=expanded_affinities,
            onboarding_completed=True,
            onboarding_raw=body.raw_inputs,
        )
        db.add(prefs)

    try:
        await db.flush()
    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Onboarding flush failed for user={user.id}: {error_msg}. "
            f"Teams: local={[t.team_id for t in body.local_teams]}, "
            f"follow={[t.team_id for t in body.follow_teams]}, "
            f"alma_mater={[t.team_id for t in body.alma_mater_teams]}, "
            f"rival={[t.team_id for t in body.rival_teams]}"
        )
        if "foreign key" in error_msg.lower() or "violates" in error_msg.lower():
            raise HTTPException(
                status_code=422,
                detail="One or more selected teams no longer exist. Please remove and re-add them.",
            )
        raise

    logger.info(
        f"Onboarding completed for user={user.id}: "
        f"{len(seen_pairs)} team-relations, {len(expanded_affinities)} sport keys"
    )

    return {"status": "ok", "onboarding_completed": True}


@router.get("/preferences", response_model=PreferencesResponse)
async def get_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current preferences and team favorites.
    Used to pre-populate the onboarding form for re-editing.
    """
    from app.models.models import Sport

    # Load preferences
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    # Load favorites with team info
    result = await db.execute(
        select(UserFavorite, Team, Sport.key.label("sport_key"))
        .join(Team, UserFavorite.team_id == Team.id)
        .join(Sport, Team.sport_id == Sport.id)
        .where(UserFavorite.user_id == user.id)
        .order_by(UserFavorite.relation_type, Team.name)
    )
    fav_rows = result.all()

    favorites = [
        FavoriteItem(
            team_id=fav.team_id,
            team_name=team.name,
            relation_type=fav.relation_type,
            sport_key=sport_key,
            logo_url=team.logo_url_small or team.logo_url,
            source=fav.source,
        )
        for fav, team, sport_key in fav_rows
    ]

    # Compress backend sport affinities to user-friendly keys
    raw_affinities = prefs.sport_affinities if prefs and prefs.sport_affinities else {}
    compressed = _compress_sport_affinities(raw_affinities)

    return PreferencesResponse(
        home_location=prefs.home_location if prefs else None,
        sport_affinities=compressed,
        onboarding_completed=prefs.onboarding_completed if prefs else False,
        favorites=favorites,
    )


# =============================================================================
# Team search (for onboarding autocomplete)
# =============================================================================

@router.get("/teams/search", response_model=list[TeamSearchResult])
async def search_teams(
    q: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Search teams by name for autocomplete.
    Does not require auth — used during onboarding flow.
    Searches team name, alternate_names, and location.

    Falls back to the events table for teams that don't have Team records yet
    (common for college teams that haven't been on an ESPN scoreboard).
    Auto-creates Team records for matches found in events.
    """
    if len(q) < 2:
        return []

    # Split multi-word queries into individual search terms.
    # "Brown University" → search for teams matching "Brown" OR "University"
    # This lets users type school names like "Harvard University" and find
    # "Harvard Crimson", or "Brown University" and find "Brown Bears".
    words = [w.strip() for w in q.split() if len(w.strip()) >= 2]
    if not words:
        return []

    from app.models.models import Sport, Event
    conditions = []
    for word in words:
        pattern = f"%{word}%"
        conditions.append(Team.name.ilike(pattern))
        conditions.append(Team.location.ilike(pattern))
        conditions.append(Team.abbreviation.ilike(pattern))
        # Search alternate_names JSONB (stored as ["Lakers", "LA Lakers"])
        conditions.append(cast(Team.alternate_names, String).ilike(pattern))

    # Relevance ordering: exact name match > starts-with > contains
    q_lower = q.lower()
    relevance = case(
        (Team.name.ilike(q), 0),            # Exact match
        (Team.name.ilike(f"{q}%"), 1),       # Starts with
        (Team.abbreviation.ilike(q), 2),     # Abbreviation match
        else_=3,                              # Contains
    )

    result = await db.execute(
        select(Team, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id)
        .where(or_(*conditions))
        .order_by(relevance, Team.name)
        .limit(20)
    )
    rows = result.all()

    results = [
        TeamSearchResult(
            id=team.id,
            name=team.name,
            location=team.location,
            sport_key=sport_key,
            logo_url=team.logo_url_small or team.logo_url,
            abbreviation=team.abbreviation,
        )
        for team, sport_key in rows
    ]

    # -------------------------------------------------------------------------
    # Events table fallback: find teams from events that lack Team records.
    # This catches college teams (Harvard, Brown, Stanford, etc.) that The Odds
    # API tracks but ESPN sync hasn't created Team records for yet.
    # -------------------------------------------------------------------------
    if len(results) < 15:
        existing_ids = {r.id for r in results}
        existing_name_sports: set[tuple[str, int]] = set()
        # Build a set of (name, sport_id) from existing results to avoid duplicates.
        # We need sport_id (not sport_key) for dedup, so re-query if needed.
        for team, sport_key in rows:
            existing_name_sports.add((team.name, team.sport_id))

        # Search both home and away team names in events
        home_conds = [Event.home_team_name.ilike(f"%{w}%") for w in words]
        away_conds = [Event.away_team_name.ilike(f"%{w}%") for w in words]

        home_subq = (
            select(
                Event.home_team_name.label("team_name"),
                Sport.id.label("sport_id"),
                Sport.key.label("sport_key"),
            )
            .join(Sport, Event.sport_id == Sport.id)
            .where(or_(*home_conds))
        )
        away_subq = (
            select(
                Event.away_team_name.label("team_name"),
                Sport.id.label("sport_id"),
                Sport.key.label("sport_key"),
            )
            .join(Sport, Event.sport_id == Sport.id)
            .where(or_(*away_conds))
        )
        combined = union_all(home_subq, away_subq).subquery()

        event_teams_result = await db.execute(
            select(
                combined.c.team_name,
                combined.c.sport_id,
                combined.c.sport_key,
            ).distinct().limit(50)
        )
        event_teams = event_teams_result.all()

        teams_created = 0
        for team_name, sport_id, sport_key in event_teams:
            if (team_name, sport_id) in existing_name_sports:
                continue

            # Check if a Team record already exists (may not be in our initial
            # search results due to missing location/alternate_names)
            team_check = await db.execute(
                select(Team).where(
                    Team.name == team_name,
                    Team.sport_id == sport_id,
                )
            )
            team = team_check.scalar_one_or_none()

            if not team:
                # Auto-create Team record — this team exists in events but has
                # no Team record (usually college teams not on ESPN scoreboard).
                # Copy logo/location from an existing Team with the same name
                # (different sport) so the logo shows up consistently.
                team = Team(name=team_name, sport_id=sport_id)

                existing_with_logo = await db.execute(
                    select(Team).where(
                        Team.name == team_name,
                        Team.logo_url_small.isnot(None),
                    ).limit(1)
                )
                donor = existing_with_logo.scalar_one_or_none()
                if donor:
                    team.logo_url = donor.logo_url
                    team.logo_url_small = donor.logo_url_small
                    team.location = donor.location
                    team.primary_color = donor.primary_color
                    team.secondary_color = donor.secondary_color

                db.add(team)
                await db.flush()
                teams_created += 1

            if team.id not in existing_ids:
                results.append(TeamSearchResult(
                    id=team.id,
                    name=team.name,
                    location=team.location,
                    sport_key=sport_key,
                    logo_url=team.logo_url_small or team.logo_url,
                    abbreviation=team.abbreviation,
                ))
                existing_ids.add(team.id)
                existing_name_sports.add((team_name, sport_id))

            if len(results) >= 20:
                break

        if teams_created > 0:
            logger.info(
                f"Auto-created {teams_created} Team records from events "
                f"fallback (query='{q}')"
            )

    return results


@router.get("/teams/by-location", response_model=list[TeamSearchResult])
async def teams_by_location(
    q: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Find teams by location/city with metro alias expansion.
    Does not require auth — used during onboarding city selection.

    Example: q="Boston" returns Celtics, Red Sox, Bruins, Patriots (via "New England" alias).
    """
    if len(q) < 2:
        return []

    # Expand query with metro aliases
    terms = _expand_location_query(q)

    # Build OR conditions for all expanded terms — search name, location,
    # abbreviation, and alternate_names for maximum recall.
    from app.models.models import Sport
    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.append(Team.location.ilike(pattern))
        conditions.append(Team.name.ilike(pattern))
        conditions.append(Team.abbreviation.ilike(pattern))
        conditions.append(cast(Team.alternate_names, String).ilike(pattern))

    # Relevance ordering: location match > name match > others
    q_lower = q.lower().strip()
    relevance = case(
        (Team.location.ilike(q_lower), 0),          # Exact location match
        (Team.location.ilike(f"%{q_lower}%"), 1),    # Location contains
        (Team.name.ilike(f"%{q_lower}%"), 2),        # Name contains
        else_=3,
    )

    result = await db.execute(
        select(Team, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id)
        .where(or_(*conditions))
        .order_by(relevance, Team.name)
        .limit(50)
    )
    rows = result.all()

    # Deduplicate by team ID (aliases can match the same team multiple times)
    seen: set[int] = set()
    results: list[TeamSearchResult] = []
    for team, sport_key in rows:
        if team.id not in seen:
            seen.add(team.id)
            results.append(
                TeamSearchResult(
                    id=team.id,
                    name=team.name,
                    location=team.location,
                    sport_key=sport_key,
                    logo_url=team.logo_url_small or team.logo_url,
                    abbreviation=team.abbreviation,
                )
            )

    return results


# =============================================================================
# Favorites CRUD (inline editing from preferences page)
# =============================================================================

class AddFavoriteRequest(BaseModel):
    """Add a single team favorite."""
    team_id: int
    relation_type: str  # "follow", "local", "alma_mater", "rival"


@router.post("/favorites", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    body: AddFavoriteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a single team favorite. Used for inline editing on the preferences page."""
    valid_types = {"follow", "local", "alma_mater", "rival"}
    if body.relation_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"relation_type must be one of {valid_types}")

    # Verify team exists
    result = await db.execute(select(Team).where(Team.id == body.team_id))
    team = result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check for duplicate (same user, team, relation_type)
    result = await db.execute(
        select(UserFavorite).where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.team_id == body.team_id,
                UserFavorite.relation_type == body.relation_type,
            )
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_exists"}

    db.add(UserFavorite(
        user_id=user.id,
        team_id=body.team_id,
        relation_type=body.relation_type,
        source="manual",
        weight=1.0,
    ))
    await db.flush()

    logger.info(f"Added favorite: user={user.id} team={body.team_id} type={body.relation_type}")
    return {"status": "added"}


@router.delete("/favorites/{team_id}")
async def remove_favorite(
    team_id: int,
    relation_type: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a specific team favorite by team_id and relation_type."""
    valid_types = {"follow", "local", "alma_mater", "rival"}
    if relation_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"relation_type must be one of {valid_types}")

    result = await db.execute(
        delete(UserFavorite).where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.team_id == team_id,
                UserFavorite.relation_type == relation_type,
            )
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")

    logger.info(f"Removed favorite: user={user.id} team={team_id} type={relation_type}")
    return {"status": "removed"}


class UpdateSportAffinitiesRequest(BaseModel):
    """Update sport affinities from preferences page."""
    sport_affinities: dict[str, float]  # e.g., {"football": 1.0, "basketball": 0.3}


@router.put("/preferences/sport-affinities")
async def update_sport_affinities(
    body: UpdateSportAffinitiesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update sport affinities. Accepts user-friendly keys, expands to backend format."""
    expanded = _expand_sport_affinities(body.sport_affinities)

    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs:
        prefs.sport_affinities = expanded
    else:
        prefs = UserPreference(
            user_id=user.id,
            sport_affinities=expanded,
        )
        db.add(prefs)

    await db.flush()

    logger.info(f"Updated sport affinities for user={user.id}: {len(expanded)} keys")
    return {"status": "updated"}


# =============================================================================
# Team Futures — aggregated futures for followed teams
# =============================================================================

def _escape_like(s: str) -> str:
    """Escape special LIKE/ILIKE characters for safe pattern matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _team_name_patterns(full_name: str) -> list[str]:
    """Build ILIKE-safe patterns for matching a team in outcome names.

    Returns escaped patterns suitable for use in ILIKE '%pattern%' queries.
    Includes full team name and short name (last word, if >= 4 chars).
    """
    if not full_name:
        return []

    patterns = []
    escaped_full = _escape_like(full_name.strip())
    patterns.append(escaped_full)

    # Short name: last word (e.g., "Celtics" from "Boston Celtics")
    parts = full_name.strip().split()
    if len(parts) > 1:
        short = parts[-1]
        if len(short) >= 4:
            escaped_short = _escape_like(short)
            if escaped_short.lower() != escaped_full.lower():
                patterns.append(escaped_short)

    return patterns


def _strict_team_name_matches(user_team: str, candidate: str) -> bool:
    """Check if a user's followed team name matches a candidate outcome name.

    Uses suffix-word matching to prevent false positives like "Bears" (from
    "Brown Bears") matching "Chicago Bears".

    Same logic as feed._team_name_matches, duplicated here to avoid
    cross-module coupling.
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


async def _query_team_futures(
    team_ids: list[int],
    db: AsyncSession,
    limit: int = 20,
) -> dict:
    """Shared logic for querying futures outcomes matched to a set of teams.

    Returns dict with keys: items, teams (list of team dicts), total_count.

    Two-query approach for fast execution:
    1. Team query — team_id FK + full team name ILIKE (championships, etc.)
    2. Award query — fetch outcomes from award-like markets, match roster
       player names in Python (MVP, Clutch Player, etc.)

    Game-level markets (spreads, O/U, matchups) are filtered out by both
    event_id and name patterns.
    """
    if not team_ids:
        return {"items": [], "teams": [], "total_count": 0}

    # Load Team records for the provided IDs
    result = await db.execute(
        select(Team).where(Team.id.in_(team_ids))
    )
    teams = {t.id: t for t in result.scalars().all()}

    if not teams:
        return {"items": [], "teams": [], "total_count": 0}

    # Build ILIKE patterns from FULL team names only — no alternate_names,
    # no short suffixes.  This prevents "Bears" (from "Brown Bears") from
    # matching "Chicago Bears" or "Eagles" matching "Philadelphia Eagles".
    team_patterns: list[str] = []
    seen_lower: set[str] = set()
    # Build roster player name → team ID map (for Python-side matching)
    player_to_team_id: dict[str, int] = {}

    for t in teams.values():
        if t.name:
            escaped = _escape_like(t.name.strip())
            if escaped.lower() not in seen_lower:
                seen_lower.add(escaped.lower())
                team_patterns.append(escaped)

        # Collect roster player names for Python-side matching (not SQL ILIKE)
        roster = t.roster_players
        if roster and isinstance(roster, list):
            for item in roster:
                if isinstance(item, dict):
                    player_name = item.get("name")
                elif isinstance(item, str):
                    player_name = item
                else:
                    continue
                if isinstance(player_name, str) and len(player_name) >= 4:
                    player_to_team_id[player_name.lower()] = t.id

    # Subquery: count outcomes per market (for ranking context like "#3 of 30")
    outcome_count_sq = (
        select(
            FuturesOutcome.market_id,
            func.count().label("outcome_total"),
        )
        .group_by(FuturesOutcome.market_id)
        .subquery()
    )

    # Common market-level filters
    market_base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        # Filter game-level markets by name pattern (some have event_id=None)
        ~FuturesMarket.name.ilike("% vs %"),
        ~FuturesMarket.name.ilike("% vs. %"),
    ]

    # ── Query 1: Team matching (team_id + team name ILIKE) ──
    # Fast — only team names in OR conditions, no roster players.
    team_conditions = [FuturesOutcome.team_id.in_(team_ids)]
    for pattern in team_patterns:
        team_conditions.append(FuturesOutcome.name.ilike(f"%{pattern}%"))

    query1 = (
        select(FuturesOutcome, FuturesMarket, outcome_count_sq.c.outcome_total)
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .outerjoin(outcome_count_sq, FuturesMarket.id == outcome_count_sq.c.market_id)
        .where(and_(*market_base_filters, or_(*team_conditions)))
        .order_by(
            func.abs(FuturesOutcome.probability_change_24h).desc().nulls_last(),
            FuturesOutcome.current_probability.desc().nulls_last(),
        )
        .limit(limit * 5)
    )
    result1 = await db.execute(query1)
    rows1 = result1.all()

    # ── Query 2: Award markets — fetch all outcomes, match players in Python ──
    # Only runs if we have roster players to match against.
    rows2 = []
    if player_to_team_id:
        award_keywords = [
            "MVP", "Player of the Year", "Rookie of the Year",
            "Defensive Player", "Coach of the Year", "Cy Young",
            "Heisman", "Most Improved", "Sixth Man", "Clutch",
            "Finals MVP", "All-Star",
        ]
        award_filters = [FuturesMarket.name.ilike(f"%{kw}%") for kw in award_keywords]

        query2 = (
            select(FuturesOutcome, FuturesMarket, outcome_count_sq.c.outcome_total)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .outerjoin(outcome_count_sq, FuturesMarket.id == outcome_count_sq.c.market_id)
            .where(and_(*market_base_filters, or_(*award_filters)))
            .order_by(FuturesOutcome.current_probability.desc().nulls_last())
            .limit(500)  # Award markets are few — fetch all outcomes
        )
        result2 = await db.execute(query2)
        rows2 = result2.all()

    # For each outcome, figure out which followed team matched.
    # Uses strict suffix-word matching + roster player matching.
    def _find_matched_team(outcome: FuturesOutcome) -> dict | None:
        # Direct team_id match (always correct)
        if outcome.team_id and outcome.team_id in teams:
            t = teams[outcome.team_id]
            return {
                "id": t.id,
                "name": t.name,
                "logo_small": t.logo_url_small or t.logo_url,
                "primary_color": t.primary_color,
            }
        # Name matching — use strict suffix-word logic to prevent
        # "Bears" (from "Brown Bears") matching "Chicago Bears".
        outcome_name = outcome.name or ""
        for t in teams.values():
            if _strict_team_name_matches(t.name, outcome_name):
                return {
                    "id": t.id,
                    "name": t.name,
                    "logo_small": t.logo_url_small or t.logo_url,
                    "primary_color": t.primary_color,
                }
        # Roster player matching — e.g., "Jayson Tatum" → Celtics
        outcome_lower = outcome_name.lower()
        for player_lower, tid in player_to_team_id.items():
            if player_lower in outcome_lower:
                t = teams.get(tid)
                if t:
                    return {
                        "id": t.id,
                        "name": t.name,
                        "logo_small": t.logo_url_small or t.logo_url,
                        "primary_color": t.primary_color,
                    }
        return None

    # Process both result sets: team matches (query 1) + award matches (query 2)
    items = []
    seen_market_ids: set[int] = set()  # Deduplicate: one outcome per market
    for outcome, market, outcome_total in list(rows1) + list(rows2):
        # Skip if we already have an outcome from this market
        if market.id in seen_market_ids:
            continue

        matched = _find_matched_team(outcome)
        if not matched:
            continue  # Skip if we can't determine which team matched

        seen_market_ids.add(market.id)

        prob = float(outcome.current_probability) if outcome.current_probability is not None else None
        change = float(outcome.probability_change_24h) if outcome.probability_change_24h is not None else None

        items.append({
            "outcome_id": outcome.id,
            "outcome_name": outcome.name,
            "market_id": market.id,
            "market_name": market.name,
            "market_tier": market.market_tier,
            "category": market.llm_sport_category,
            "source": market.source,
            "probability": prob,
            "probability_change_24h": change,
            "rank": outcome.rank,
            "total_outcomes": outcome_total,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "matched_team": matched,
            "canonical_market_key": market.canonical_market_key,
        })

        if len(items) >= limit:
            break

    # Build teams list for share link
    teams_list = [
        {
            "id": t.id,
            "name": t.name,
            "logo_small": t.logo_url_small or t.logo_url,
            "primary_color": t.primary_color,
        }
        for t in teams.values()
    ]

    return {
        "items": items,
        "teams": teams_list,
        "team_ids": list(teams.keys()),
        "total_count": len(items),
    }


@router.get("/team-futures")
async def get_team_futures(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get futures outcomes for the current user's followed teams.

    Returns outcomes ranked by |probability_change_24h|, tagged with
    which followed team matched.
    """
    # Load user's followed team IDs (all relation types except rival)
    result = await db.execute(
        select(UserFavorite.team_id)
        .where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.relation_type != "rival",
            )
        )
        .distinct()
    )
    team_ids = [row[0] for row in result.all()]

    if not team_ids:
        return {"items": [], "team_ids": [], "total_count": 0}

    data = await _query_team_futures(team_ids, db, limit=min(limit, 100))
    return data


# Public share endpoint — mounted separately in main.py at /api/shared
shared_router = APIRouter()


@shared_router.get("/team-futures")
async def get_shared_team_futures(
    team_ids: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint: get futures outcomes for specified teams.

    Used for share links — no auth required.
    Query param team_ids is a comma-separated list of team IDs.
    """
    try:
        parsed_ids = [int(x.strip()) for x in team_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="team_ids must be comma-separated integers")

    if not parsed_ids:
        raise HTTPException(status_code=400, detail="team_ids is required")

    if len(parsed_ids) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 teams")

    data = await _query_team_futures(parsed_ids, db, limit=min(limit, 50))
    return data
