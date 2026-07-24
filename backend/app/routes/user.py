"""
User data routes: pins, preferences, team search, onboarding.

All endpoints require authentication unless noted otherwise.
"""

import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import select, delete, and_, or_, case, cast, func, String, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.dependencies.auth import get_current_user, get_optional_user
from app.models.models import (
    User, UserPin, UserFavorite, UserPreference, Team, Sport,
    FuturesMarket, FuturesOutcome, TeamIdentityMapping,
)
from app.services.database import get_db, get_db_rw
from app.utils.name_normalization import names_match as _names_match

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


class TeamSportVariant(BaseModel):
    """A specific sport variant of a team (e.g., Harvard Basketball vs Harvard Football)."""
    id: int
    sport_key: Optional[str]
    sport_display: Optional[str]


class TeamSearchResult(BaseModel):
    """Team search result for autocomplete."""
    id: int
    name: str
    location: Optional[str]
    sport_key: Optional[str]
    logo_url: Optional[str]
    abbreviation: Optional[str]
    sports: list[TeamSportVariant] = []


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


class EmailPreferencesResponse(BaseModel):
    """Email opt-in preferences (CAN-SPAM compliant, all default False)."""
    digest: bool = False
    bug_updates: bool = False
    market_alerts: bool = False


class PushPreferencesResponse(BaseModel):
    """Push notification preferences.

    daily_challenge/big_moves are opt-out (default True). morning_digest
    (Queue #200 notifications v1) is opt-IN (default False) — a user must
    explicitly enable the daily digest.
    """
    daily_challenge: bool = True
    big_moves: bool = True
    morning_digest: bool = False


class PreferencesResponse(BaseModel):
    """Full preferences + favorites for the current user."""
    home_location: Optional[str]
    sport_affinities: dict[str, float]  # Compressed (user-friendly keys)
    onboarding_completed: bool
    favorites: list[FavoriteItem]
    email_preferences: EmailPreferencesResponse = EmailPreferencesResponse()
    push_preferences: PushPreferencesResponse = PushPreferencesResponse()


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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current preferences and team favorites.
    Returns defaults for anonymous users.
    """
    if not user:
        return PreferencesResponse(
            home_location=None,
            sport_affinities={},
            onboarding_completed=False,
            favorites=[],
        )

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

    # Build email preferences from User.email_preferences JSONB
    raw_email_prefs = user.email_preferences if isinstance(user.email_preferences, dict) else {}
    email_prefs = EmailPreferencesResponse(
        digest=bool(raw_email_prefs.get("digest", False)),
        bug_updates=bool(raw_email_prefs.get("bug_updates", False)),
        market_alerts=bool(raw_email_prefs.get("market_alerts", False)),
    )

    # Build push preferences from User.push_preferences JSONB (default True)
    raw_push_prefs = user.push_preferences if isinstance(user.push_preferences, dict) else {}
    push_prefs = PushPreferencesResponse(
        daily_challenge=bool(raw_push_prefs.get("daily_challenge", True)),
        big_moves=bool(raw_push_prefs.get("big_moves", True)),
        morning_digest=bool(raw_push_prefs.get("morning_digest", False)),
    )

    return PreferencesResponse(
        home_location=prefs.home_location if prefs else None,
        sport_affinities=compressed,
        onboarding_completed=prefs.onboarding_completed if prefs else False,
        favorites=favorites,
        email_preferences=email_prefs,
        push_preferences=push_prefs,
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

    # Sport keys to exclude: preseason, minor leagues, obscure foreign leagues
    _EXCLUDED_SPORT_KEYS = {
        "baseball_mlb_preseason",
        "soccer_copa_sudamericana", "soccer_copa_libertadores",
        "soccer_brazil_campeonato", "soccer_brazil_serie_b",
        "soccer_argentina_primera_division",
        "soccer_chile_primera_division", "soccer_colombia_primera_a",
    }

    # Tier ordering: lower = more relevant. Used for dedup (keep best tier).
    _SPORT_TIER = {
        "basketball_nba": 1, "americanfootball_nfl": 1, "baseball_mlb": 1,
        "icehockey_nhl": 1, "soccer_epl": 1, "soccer_usa_mls": 1,
        "basketball_wnba": 2, "basketball_ncaab": 2,
        "americanfootball_ncaaf": 2, "soccer_germany_bundesliga": 2,
        "soccer_spain_la_liga": 2, "soccer_italy_serie_a": 2,
    }

    result = await db.execute(
        select(Team, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id)
        .where(
            or_(*conditions),
            Sport.key.notin_(_EXCLUDED_SPORT_KEYS),
        )
        .order_by(relevance, Team.name)
        .limit(50)  # Fetch extra for dedup
    )
    rows = result.all()

    # Group by normalized team name — collect all sport variants
    _SPORT_DISPLAY = {
        "basketball_nba": "NBA", "americanfootball_nfl": "NFL",
        "baseball_mlb": "MLB", "icehockey_nhl": "NHL",
        "soccer_usa_mls": "MLS", "basketball_wnba": "WNBA",
        "basketball_ncaab": "NCAAB", "basketball_wncaab": "WNCAAB",
        "americanfootball_ncaaf": "NCAAF",
        "soccer_epl": "EPL", "soccer_spain_la_liga": "La Liga",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_italy_serie_a": "Serie A", "soccer_france_ligue_one": "Ligue 1",
        "icehockey_ncaa": "NCAA Hockey", "baseball_ncaa": "NCAA Baseball",
    }

    grouped: dict[str, dict] = {}
    for team, sport_key in rows:
        norm = team.name.lower().strip()
        tier = _SPORT_TIER.get(sport_key, 5)
        display = _SPORT_DISPLAY.get(sport_key, sport_key.split("_", 1)[-1].upper() if sport_key else "OTHER")
        variant = TeamSportVariant(id=team.id, sport_key=sport_key, sport_display=display)

        # Find an existing group that fuzzy-matches this team name.
        # Handles "Stanford" vs "Stanford Cardinal" being the same team.
        matched_key = None
        for existing_key in grouped:
            if _names_match(norm, existing_key):
                matched_key = existing_key
                break

        if matched_key is None:
            grouped[norm] = {
                "primary": team,
                "sport_key": sport_key,
                "tier": tier,
                "logo": team.logo_url_small or team.logo_url,
                "variants": [variant],
            }
        else:
            grouped[matched_key]["variants"].append(variant)
            if tier < grouped[matched_key]["tier"]:
                grouped[matched_key]["primary"] = team
                grouped[matched_key]["sport_key"] = sport_key
                grouped[matched_key]["tier"] = tier
                if team.logo_url_small or team.logo_url:
                    grouped[matched_key]["logo"] = team.logo_url_small or team.logo_url
            # Prefer the longer (more specific) name as the display name
            elif len(norm) > len(matched_key) and tier <= grouped[matched_key]["tier"]:
                grouped[matched_key]["primary"] = team
                if team.logo_url_small or team.logo_url:
                    grouped[matched_key]["logo"] = team.logo_url_small or team.logo_url

    results = []
    for norm, g in grouped.items():
        team = g["primary"]
        variants = sorted(g["variants"], key=lambda v: _SPORT_TIER.get(v.sport_key or "", 5))
        results.append(TeamSearchResult(
            id=team.id,
            name=team.name,
            location=team.location,
            sport_key=g["sport_key"],
            logo_url=g["logo"],
            abbreviation=team.abbreviation,
            sports=variants if len(variants) > 1 else [],
        ))
    results.sort(key=lambda r: _SPORT_TIER.get(r.sport_key or "", 5))
    results = results[:20]

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

            # Also skip if a fuzzy-matching team is already in results
            # (e.g., "Stanford" when "Stanford Cardinal" is already showing)
            if any(
                _names_match(team_name, existing_name)
                for existing_name, existing_sid in existing_name_sports
                if existing_sid == sport_id
            ):
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

            # Fuzzy match: find existing team with a matching name
            if not team:
                _first_word = team_name.split()[0] if team_name else ""
                if len(_first_word) >= 3:
                    fuzzy_check = await db.execute(
                        select(Team).where(
                            Team.sport_id == sport_id,
                            Team.name.ilike(f"%{_first_word}%"),
                        )
                    )
                    for candidate in fuzzy_check.scalars():
                        if _names_match(team_name, candidate.name):
                            team = candidate
                            break

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

    # Deduplicate by team ID and fuzzy name match
    # (catches "Stanford" vs "Stanford Cardinal" as separate Team records)
    seen: set[int] = set()
    seen_names: list[str] = []
    results: list[TeamSearchResult] = []
    for team, sport_key in rows:
        if team.id in seen:
            continue
        # Skip if a fuzzy-matching team name already in results
        if any(_names_match(team.name, sn) for sn in seen_names):
            continue
        seen.add(team.id)
        seen_names.append(team.name)
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
    db: AsyncSession = Depends(get_db_rw),
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
# Email preferences (CAN-SPAM compliant)
# =============================================================================

class UpdateEmailPreferencesRequest(BaseModel):
    """Update email opt-in preferences."""
    digest: Optional[bool] = None
    bug_updates: Optional[bool] = None
    market_alerts: Optional[bool] = None


@router.patch("/preferences/email")
async def update_email_preferences(
    body: UpdateEmailPreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    """Update email preferences. Only provided fields are changed.

    All email types default to False (opt-in required per CAN-SPAM).
    """
    from app.utils.email_compliance import (
        EMAIL_PREF_KEYS,
        generate_unsubscribe_token,
        merge_email_preferences,
    )

    # Build updates dict from provided (non-None) fields
    updates: dict[str, bool] = {}
    if body.digest is not None:
        updates["digest"] = body.digest
    if body.bug_updates is not None:
        updates["bug_updates"] = body.bug_updates
    if body.market_alerts is not None:
        updates["market_alerts"] = body.market_alerts

    if not updates:
        return {"status": "no_changes"}

    # Read current preferences
    current = user.email_preferences if isinstance(user.email_preferences, dict) else {}
    new_prefs = merge_email_preferences(current, updates)

    # If any preference is now True and user has no unsubscribe token, generate one
    values: dict = {"email_preferences": new_prefs}
    if any(new_prefs.values()) and not user.unsubscribe_token:
        values["unsubscribe_token"] = generate_unsubscribe_token(user.id)

    # Use Core update to avoid JSONB ORM assignment issues (Gotcha #4)
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(User)
        .where(User.id == user.id)
        .values(**values)
    )
    await db.flush()

    logger.info(
        "Updated email preferences for user=%d: %s",
        user.id, new_prefs,
    )
    return {
        "status": "updated",
        "email_preferences": new_prefs,
    }


# =============================================================================
# Push notification preferences
# =============================================================================

# Opt-out keys default True; opt-in keys default False (must be enabled).
PUSH_PREF_KEYS = frozenset({"daily_challenge", "big_moves"})
PUSH_PREF_OPTIN_KEYS = frozenset({"morning_digest"})
ALL_PUSH_PREF_KEYS = PUSH_PREF_KEYS | PUSH_PREF_OPTIN_KEYS


class UpdatePushPreferencesRequest(BaseModel):
    """Update push notification preferences."""
    daily_challenge: Optional[bool] = None
    big_moves: Optional[bool] = None
    morning_digest: Optional[bool] = None


@router.patch("/preferences/push")
async def update_push_preferences(
    body: UpdatePushPreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_rw),
):
    """Update push notification preferences. Only provided fields are changed.

    Push types default to True (opt-out model — users get notifications
    unless they explicitly disable them).
    """
    # Build updates dict from provided (non-None) fields
    updates: dict[str, bool] = {}
    if body.daily_challenge is not None:
        updates["daily_challenge"] = body.daily_challenge
    if body.big_moves is not None:
        updates["big_moves"] = body.big_moves
    if body.morning_digest is not None:
        updates["morning_digest"] = body.morning_digest

    if not updates:
        return {"status": "no_changes"}

    # Read current preferences. Opt-out keys default True; opt-in keys default False.
    current = user.push_preferences if isinstance(user.push_preferences, dict) else {}
    new_prefs = {key: current.get(key, True) for key in sorted(PUSH_PREF_KEYS)}
    for key in sorted(PUSH_PREF_OPTIN_KEYS):
        new_prefs[key] = current.get(key, False)
    for key, value in updates.items():
        if key in ALL_PUSH_PREF_KEYS:
            new_prefs[key] = value

    # Use Core update to avoid JSONB ORM assignment issues (Gotcha #4)
    from sqlalchemy import update as sa_update
    await db.execute(
        sa_update(User)
        .where(User.id == user.id)
        .values(push_preferences=new_prefs)
    )
    await db.flush()

    logger.info(
        "Updated push preferences for user=%d: %s",
        user.id, new_prefs,
    )
    return {
        "status": "updated",
        "push_preferences": new_prefs,
    }


# =============================================================================
# Team Futures — aggregated futures for followed teams
# =============================================================================

import re as _re

_SEASON_YEAR_RE = _re.compile(r"(20\d{2}(?:\s*[-/]\s*\d{2,4})?)")


def _extract_season_year(
    canonical_market_key: str | None,
    market_name: str | None,
) -> str | None:
    """Extract a season/year string for display (BR52).

    Tries canonical_market_key first (format: sport:league:category:season),
    then falls back to regex on market_name.

    Returns e.g. "2025-26", "2026", or None.
    """
    if canonical_market_key:
        parts = canonical_market_key.split(":")
        if len(parts) >= 4 and parts[3]:
            return parts[3]
    if market_name:
        m = _SEASON_YEAR_RE.search(market_name)
        if m:
            return m.group(1).replace(" ", "")
    return None


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


# #237 Item 3: a coherent probability field sums to ~1.0; mirrors event_soccer's
# _FIELD_SUM_MAX. An award/prop field whose YES prices sum far past 100% is an
# illiquid Kalshi independent-binary ladder (one YES market per player), not a
# legible probability field — the "Your Teams' Odds" surface should not let one
# crowd out a team's coherent odds_api championship field.
_TEAM_ODDS_COHERENT_FIELD_SUM_MAX = 1.60


def _is_illiquid_binary_field(source: str | None, field_prob_sum) -> bool:
    """True for a Kalshi independent-binary award/prop field whose outcome
    probabilities sum well past 100% (the overrounded, illiquid ladder class).
    Source-scoped to Kalshi because odds_api fields are single coherent markets;
    a missing/None sum fails open (treated as coherent)."""
    if source != "kalshi" or field_prob_sum is None:
        return False
    try:
        return float(field_prob_sum) > _TEAM_ODDS_COHERENT_FIELD_SUM_MAX
    except (TypeError, ValueError):
        return False


def _prefer_coherent_team_items(per_team_items: dict[int, list[dict]]) -> None:
    """#237 Item 3, in place: when a team has at least one coherent candidate, drop
    its illiquid-binary ones (keyed on the private ``_illiquid_binary`` flag); keep
    the illiquid ones only when that is ALL the team has, so a followed team is
    never emptied. Strips the private flag from every surviving item afterward.
    Both directions matter: illiquid Kalshi is suppressed when a coherent field
    exists, and the coherent field always survives."""
    for tid, tid_items in per_team_items.items():
        coherent = [it for it in tid_items if not it.get("_illiquid_binary")]
        if coherent and len(coherent) < len(tid_items):
            per_team_items[tid] = coherent
    for tid_items in per_team_items.values():
        for it in tid_items:
            it.pop("_illiquid_binary", None)


async def _query_team_futures(
    team_ids: list[int],
    db: AsyncSession,
    limit: int = 20,
    timings: dict | None = None,
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

    # Load Team records with their sport for sport-scoped matching (BR53).
    result = await db.execute(
        select(Team, Sport.key.label("sport_key"))
        .join(Sport, Team.sport_id == Sport.id)
        .where(Team.id.in_(team_ids))
    )
    teams: dict[int, Team] = {}
    # team_id → sport category (e.g., "hockey", "baseball")
    team_sport_categories: dict[int, str] = {}
    for t, sport_key in result.all():
        teams[t.id] = t
        root = sport_key.split("_")[0].lower() if sport_key else ""
        if root == "americanfootball":
            cat = "football"
        elif root == "icehockey":
            cat = "hockey"
        else:
            cat = root
        if cat:
            team_sport_categories[t.id] = cat

    if not teams:
        return {"items": [], "teams": [], "total_count": 0}

    # ── Identity-collapse duplicate Team rows before matching ──
    # Bare-location dupes ("Boston" dup of "Boston Bruins"; "New England" dup of
    # "New England Revolution") share the SAME (sport_id, espn_id) as the canonical
    # row but carry a bare name and ZERO team_identity_mapping rows. A null-espn
    # dupe ("Boston Celtics" espn_id=NULL vs "Boston Celtics" espn_id=2) shares the
    # canonical's name+sport. Without collapse a followed team surfaces twice
    # (two matched_team + two teams_list entries) and its ILIKE patterns double up.
    # Collapse is STRICTLY within sport_id — never merge a same-name different-sport
    # team (NFL "New England Patriots" must not fold into MLS "New England Revolution").
    # id_to_canonical maps EVERY loaded team id (dup + canonical) → the canonical id
    # so the team_id FK match, matched_team, and teams_list all dedup.
    id_to_canonical: dict[int, int] = {tid: tid for tid in teams}
    if len(teams) > 1:
        # One query for identity-mapping row counts across all loaded team ids.
        tim_counts: dict[int, int] = {}
        tim_result = await db.execute(
            select(TeamIdentityMapping.team_id, func.count().label("n"))
            .where(TeamIdentityMapping.team_id.in_(list(teams.keys())))
            .group_by(TeamIdentityMapping.team_id)
        )
        for _tid, _n in tim_result.all():
            tim_counts[_tid] = _n

        def _norm_team_name(nm: str | None) -> str:
            return _re.sub(r"\s+", " ", (nm or "").strip().lower())

        # Union-find over loaded teams (within sport only). Two teams merge when
        # they share a non-null espn_id OR a normalized name (same sport).
        parent: dict[int, int] = {tid: tid for tid in teams}

        def _find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a: int, b: int) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[ra] = rb

        team_list = list(teams.values())
        for i in range(len(team_list)):
            for j in range(i + 1, len(team_list)):
                a, b = team_list[i], team_list[j]
                if a.sport_id != b.sport_id:
                    continue  # NEVER merge across sports
                same_espn = bool(a.espn_id) and bool(b.espn_id) and str(a.espn_id) == str(b.espn_id)
                a_norm = _norm_team_name(a.name)
                same_name = bool(a_norm) and a_norm == _norm_team_name(b.name)
                if same_espn or same_name:
                    _union(a.id, b.id)

        # Pick the canonical row per cluster: most identity-mapping rows, tiebreak
        # longest name (the bare-location dup has the shorter name).
        clusters: dict[int, list[Team]] = {}
        for t in team_list:
            clusters.setdefault(_find(t.id), []).append(t)

        collapsed_teams: dict[int, Team] = {}
        id_to_canonical = {}
        for members in clusters.values():
            canonical = max(
                members,
                key=lambda m: (tim_counts.get(m.id, 0), len(m.name or "")),
            )
            collapsed_teams[canonical.id] = canonical
            for m in members:
                id_to_canonical[m.id] = canonical.id

        teams = collapsed_teams
        # Remap sport categories onto the canonical ids.
        remapped_cats: dict[int, str] = {}
        for _tid, _cat in team_sport_categories.items():
            remapped_cats[id_to_canonical.get(_tid, _tid)] = _cat
        team_sport_categories = remapped_cats

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

    # NOTE (#1197 r259 team-route latency): the per-market outcome count + field
    # probability sum ("#3 of 30" context; #237 Item 3 coherence signal) used to be
    # an outcome_count_sq subquery — a GROUP BY over the ENTIRE 1.2M-row
    # futures_outcomes table with NO filter — pre-joined into query1/query2. That
    # unfiltered full-table aggregate was the ~6s team-page futures section (and a
    # drag on the feed). It is now a post-hoc lookup SCOPED to only the result
    # markets (a few hundred), computed after query1/query2 below.

    # Common market-level filters
    market_base_filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        # Filter game-level markets by name pattern (some have event_id=None)
        ~FuturesMarket.name.ilike("% vs %"),
        ~FuturesMarket.name.ilike("% vs. %"),
    ]

    # ── Query 1: Team matching (team_id FK + team-name ILIKE) ──
    # #1197 (r259): a single `or_(team_id IN (...), name ILIKE '%team%')` defeated
    # index usage and seq-scanned the 1.2M-row futures_outcomes table (~3s for ~7
    # rows). Split the OR into two SEPARATELY-INDEXED queries — the FK branch uses
    # ix_futures_outcomes_team_id, the name branch the GIN trigram on name — and
    # merge/dedup. Same rows, but each branch hits its index.
    _order_by = (
        FuturesOutcome.current_probability.desc().nulls_last(),
        func.abs(FuturesOutcome.probability_change_24h).desc().nulls_last(),
    )

    def _q1(cond):
        return (
            select(FuturesOutcome, FuturesMarket, Sport.key.label("market_sport_key"))
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
            .where(and_(*market_base_filters, cond))
            .order_by(*_order_by)
            .limit(limit * 5)
        )

    _tq = time.perf_counter()
    rows1 = list((await db.execute(_q1(FuturesOutcome.team_id.in_(team_ids)))).all())
    if team_patterns:
        name_cond = or_(*[FuturesOutcome.name.ilike(f"%{p}%") for p in team_patterns])
        name_rows = (await db.execute(_q1(name_cond))).all()
        _seen_oids = {o.id for o, _m, _sk in rows1}
        rows1.extend(r for r in name_rows if r[0].id not in _seen_oids)
    if timings is not None:
        timings["q1"] = round((time.perf_counter() - _tq) * 1000)

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
            select(FuturesOutcome, FuturesMarket, Sport.key.label("market_sport_key"))
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
            .where(and_(*market_base_filters, or_(*award_filters)))
            .order_by(FuturesOutcome.current_probability.desc().nulls_last())
            .limit(500)  # Award markets are few — fetch all outcomes
        )
        _tq = time.perf_counter()
        result2 = await db.execute(query2)
        rows2 = result2.all()
        if timings is not None:
            timings["q2"] = round((time.perf_counter() - _tq) * 1000)

    # #1197: scoped per-market count + field-prob-sum for ONLY the result markets
    # (replaces the old unfiltered full-table outcome_count_sq — the ~6s culprit).
    _mkt_ids = {m.id for _o, m, _sk in rows1} | {m.id for _o, m, _sk in rows2}
    _market_stats: dict[int, tuple[int, float | None]] = {}
    _tq = time.perf_counter()
    if _mkt_ids:
        for _mid, _tot, _fsum in (await db.execute(
            select(
                FuturesOutcome.market_id,
                func.count().label("outcome_total"),
                func.sum(FuturesOutcome.current_probability).label("field_prob_sum"),
            )
            .where(FuturesOutcome.market_id.in_(list(_mkt_ids)))
            .group_by(FuturesOutcome.market_id)
        )).all():
            _market_stats[_mid] = (_tot, _fsum)
    if timings is not None:
        timings["stats"] = round((time.perf_counter() - _tq) * 1000)
        timings["rows1"] = len(rows1)
        timings["rows2"] = len(rows2)

    # For each outcome, figure out which followed team matched.
    # Uses strict suffix-word matching + roster player matching.
    # BR53: name/player matches require the market's sport category to match
    # the team's sport category to prevent cross-sport false positives
    # (e.g., "Aliya Boston" WNBA player under Boston Bruins branding,
    # or "Believers: Boston Red Sox" Sports Emmy matching baseball teams).
    def _find_matched_team(
        outcome: FuturesOutcome,
        market: FuturesMarket,
        market_sport_key: str | None = None,
    ) -> dict | None:
        # Derive market sport category for cross-sport filtering (BR53).
        market_sport_cat: str | None = market.llm_sport_category
        if not market_sport_cat and market_sport_key:
            root = market_sport_key.split("_")[0].lower()
            if root == "americanfootball":
                market_sport_cat = "football"
            elif root == "icehockey":
                market_sport_cat = "hockey"
            else:
                market_sport_cat = root

        # Direct team_id match (always correct — team_id is sport-scoped).
        # Resolve dup ids onto the canonical row so a market linked to a
        # bare-location dupe still matches the followed canonical team.
        canonical_id = id_to_canonical.get(outcome.team_id) if outcome.team_id else None
        if canonical_id and canonical_id in teams:
            t = teams[canonical_id]
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
                # BR53: verify sport compatibility for name matches
                if market_sport_cat:
                    team_cat = team_sport_categories.get(t.id)
                    if team_cat and team_cat != market_sport_cat:
                        continue  # sport mismatch — try next team
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
                    # BR53: verify sport compatibility for player matches
                    if market_sport_cat:
                        team_cat = team_sport_categories.get(t.id)
                        if team_cat and team_cat != market_sport_cat:
                            continue  # sport mismatch — try next player
                    return {
                        "id": t.id,
                        "name": t.name,
                        "logo_small": t.logo_url_small or t.logo_url,
                        "primary_color": t.primary_color,
                    }
        return None

    # Process both result sets: team matches (query 1) + award matches (query 2).
    # Item 2: bucket candidate items per matched team (preserving the query sort
    # order — highest-probability headline markets first), then interleave
    # round-robin up to `limit`. This guarantees every followed team gets its
    # headline markets in before the limit fills, so one team with many markets
    # can't starve another (the "Celtics shows 1 of several" truncation).
    per_team_items: dict[int, list[dict]] = {}
    seen_market_ids: set[int] = set()  # Deduplicate: one outcome per market
    for outcome, market, mkt_sport_key in list(rows1) + list(rows2):
        outcome_total, field_prob_sum = _market_stats.get(market.id, (None, None))
        # Skip if we already have an outcome from this market
        if market.id in seen_market_ids:
            continue

        matched = _find_matched_team(outcome, market, market_sport_key=mkt_sport_key)
        if not matched:
            continue  # Skip if we can't determine which team matched

        seen_market_ids.add(market.id)

        prob = float(outcome.current_probability) if outcome.current_probability is not None else None
        change = float(outcome.probability_change_24h) if outcome.probability_change_24h is not None else None

        # BR52: Extract season/year for card subtitle display.
        season_year = _extract_season_year(market.canonical_market_key, market.name)

        per_team_items.setdefault(matched["id"], []).append({
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
            "season_year": season_year,
            # #237 Item 3 (private, stripped before return): illiquid Kalshi
            # independent-binary award/prop ladder whose field sums far past 100%.
            "_illiquid_binary": _is_illiquid_binary_field(market.source, field_prob_sum),
        })

    # #237 Item 3: prefer coherent fields. An illiquid Kalshi independent-binary
    # award ladder (a player's MVP / passing-yards YES markets, field summing far
    # past 100%) can carry a higher raw YES probability than the team's coherent
    # odds_api championship/division outcome, so it sorts first and crowds the
    # legible field out of the per-team bucket.
    _prefer_coherent_team_items(per_team_items)

    # Round-robin fill: strongest team (by its top market) leads each round.
    items: list[dict] = []
    if per_team_items:
        ordered_team_ids = sorted(
            per_team_items.keys(),
            key=lambda tid: (per_team_items[tid][0].get("probability") or 0),
            reverse=True,
        )
        depth = 0
        while len(items) < limit:
            progressed = False
            for tid in ordered_team_ids:
                bucket = per_team_items[tid]
                if depth < len(bucket):
                    items.append(bucket[depth])
                    progressed = True
                    if len(items) >= limit:
                        break
            if not progressed:
                break
            depth += 1

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


_team_futures_cache: dict[int, tuple[float, dict]] = {}
_TEAM_FUTURES_TTL = 120
_TEAM_FUTURES_MAX_SIZE = 100


@router.get("/team-futures")
async def get_team_futures(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get futures outcomes for the current user's followed teams."""
    import time as _time
    _now = _time.time()
    if user.id in _team_futures_cache:
        _cached_at, _cached_resp = _team_futures_cache[user.id]
        if _now - _cached_at < _TEAM_FUTURES_TTL:
            return _cached_resp

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

    if len(_team_futures_cache) >= _TEAM_FUTURES_MAX_SIZE:
        oldest = min(_team_futures_cache, key=lambda k: _team_futures_cache[k][0])
        del _team_futures_cache[oldest]
    _team_futures_cache[user.id] = (_now, data)

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
