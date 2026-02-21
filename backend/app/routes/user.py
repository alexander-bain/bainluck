"""
User data routes: pins, preferences, team search, onboarding.

All endpoints require authentication unless noted otherwise.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, delete, and_, or_, case, cast, String, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_current_user
from app.models.models import User, UserPin, UserFavorite, UserPreference, Team
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
    # --- Sports ---
    "football": ["americanfootball_nfl", "americanfootball_ncaaf"],
    "basketball": ["basketball_nba", "basketball_ncaab", "basketball_wncaab"],
    "baseball": ["baseball_mlb"],
    "hockey": ["icehockey_nhl"],
    "soccer": ["soccer_epl", "soccer_usa_mls", "soccer_spain_la_liga",
               "soccer_germany_bundesliga", "soccer_italy_serie_a",
               "soccer_france_ligue_one", "soccer_uefa_champs_league"],
    "golf": ["golf_masters_tournament_winner", "golf_pga_championship_winner",
             "golf_the_open_championship_winner", "golf_us_open_winner"],
    "tennis": ["tennis_atp_french_open", "tennis_atp_us_open",
               "tennis_atp_wimbledon", "tennis_atp_australian_open"],
    "mma": ["mma_mixed_martial_arts"],
    "boxing": ["boxing_boxing"],
    "cricket": ["cricket_icc_world_cup", "cricket_test_match"],
    "rugby": ["rugbyleague_nrl", "rugbyunion_six_nations"],
    "motorsport": ["motorsport_formula1"],
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

# Reverse mapping for display: backend key → friendly category
SPORT_KEY_TO_CATEGORY: dict[str, str] = {}
for category, keys in SPORT_AFFINITY_MAPPING.items():
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
    Input: {"americanfootball_nfl": 1.0, "americanfootball_ncaaf": 1.0}
    Output: {"football": 1.0}
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

    await db.flush()

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
                # no Team record (usually college teams not on ESPN scoreboard)
                team = Team(name=team_name, sport_id=sport_id)
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
