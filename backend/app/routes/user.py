"""
User data routes: pins, preferences, team search, onboarding.

All endpoints require authentication unless noted otherwise.
"""

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy import (
    Integer,
    Select,
    String,
    Text,
    and_,
    any_,
    bindparam,
    case,
    cast,
    delete,
    false,
    func,
    literal,
    or_,
    select,
    text,
    tuple_,
    union,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only, selectinload

from app.config.major_team_search import MAJOR_TEAM_QUERY_ALIASES
from app.dependencies.auth import get_current_user, get_optional_user
from app.utils.surface_rank import (
    MY_STUFF_SURFACE_PROFILE,
    order_my_stuff_team_buckets,
)
from app.models.models import (
    User,
    UserPin,
    UserFavorite,
    UserPreference,
    Team,
    Sport,
    RetiredTeamRedirect,
    FuturesMarket,
    FuturesOutcome,
    OpenFuturesOutcome,
    TeamIdentityMapping,
)
from app.services.database import get_db, get_db_rw
from app.services.onboarding_team_aliases import VenueAliases, onboarding_venue_aliases
from app.services.onboarding_team_membership import (
    club_filters,
    onboarding_team_members,
)
from app.utils.futures_source_mark import futures_outcome_source_mark
from app.utils.series_card_labels import market_threshold_label, reader_outcome_name
from app.utils.market_team_sport import (
    link_crosses_gender as _link_crosses_gender,
    link_crosses_league as _link_crosses_league,
    link_crosses_sport as _link_crosses_sport,
    market_event_slug as _market_event_slug,
    sport_key_llm_category as _sport_key_llm_category,
)
from app.utils.name_normalization import names_match as _names_match
from app.utils.sport_keys import (
    SPORT_HIERARCHY,
    SPORT_PREFIX_TO_DISPLAY_FAMILY,
    SPORT_PREFIX_TO_LLM_CATEGORY,
    competition_gender,
    is_season_variant,
    sport_family_key,
)
from app.utils.statement_timeout import is_statement_timeout
from app.utils.team_linking import given_name_before_city
from app.utils.team_page_cache import is_real_pg_engine
from app.utils.team_short_name import is_college_sport, school_label

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Metro alias mapping for city → teams lookup
# =============================================================================

# Maps brand/location names to their metro area aliases.
# When a user types "Boston", we also search for "New England" and vice versa.
_BAY_AREA = [
    "golden state",
    "san francisco",
    "bay area",
    "oakland",
    "santa cruz",
    "santa clara",
    "san jose",
    "san josé",
]
_LOS_ANGELES = ["los angeles", "la", "anaheim", "inglewood", "carson"]
_ST_LOUIS = ["st louis", "st. louis", "saint louis"]
_TWIN_CITIES = [
    "minnesota", "minneapolis", "st. paul", "st paul", "saint paul", "twin cities"
]
_DC = ["dc", "d.c.", "washington", "washington dc", "washington, dc"]
_METRO_CLUB_LEAGUES = {
    "americanfootball_nfl", "baseball_mlb", "basketball_nba", "basketball_wnba",
    "icehockey_nhl", "soccer_usa_mls", "soccer_usa_nwsl",
}
_METRO_MAJOR_CLUBS = {
    name.casefold(): league
    for (league, name) in MAJOR_TEAM_QUERY_ALIASES
    if league in _METRO_CLUB_LEAGUES
}
_METRO_LEAGUE_SCOPE = {
    "boston", "new york", "los angeles", "kansas city", "bay area",
    "las vegas", "st louis", "philadelphia", "dc", "twin cities",
}
_METRO_CLUB_ALIASES = {
    "kansas city": {
        "soccer_usa_mls": ("sporting kansas city", "sporting kc"),
        "soccer_usa_nwsl": ("kansas city current", "kc current"),
    },
    "bay area": {"soccer_usa_nwsl": ("bay fc",)},
    "dc": {"soccer_usa_nwsl": ("washington spirit",)},
}
_LEAGUES_CUP = "soccer_concacaf_leagues_cup"
METRO_ALIASES: dict[str, list[str]] = {
    "golden state": _BAY_AREA,
    "new england": ["boston", "foxborough", "foxboro"],
    "brooklyn": ["new york", "nyc"],
    "new york": ["brooklyn", "nyc", "elmont", "long island", "uniondale"],
    "carolina": ["charlotte", "raleigh"],
    "tampa bay": ["tampa", "st. petersburg"],
    "tampa": ["tampa bay", "st. petersburg"],
    "dc": _DC,
    "d.c.": _DC,
    "washington": _DC,
    "minnesota": _TWIN_CITIES,
    "twin cities": _TWIN_CITIES,
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
    "san francisco": _BAY_AREA,
    "sf": _BAY_AREA,
    "bay area": _BAY_AREA,
    "boston": ["new england", "foxborough"],
    "los angeles": _LOS_ANGELES,
    "la": _LOS_ANGELES,
    "kc": ["kansas city"],
    "kansas city": ["kc"],
    "vegas": ["las vegas"],
    "las vegas": ["vegas", "paradise"],
    "st louis": _ST_LOUIS,
    "st. louis": _ST_LOUIS,
    "saint louis": _ST_LOUIS,
    "jersey": ["new jersey"],
    "nola": ["new orleans"],
    "indy": ["indianapolis", "indiana"],
    "okc": ["oklahoma city"],
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

    return sorted(set(terms))


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
    # `aussierules_afl` alone would cover the other two by the prefix fallback in
    # `_lookup_sport_affinity`; all three are named because this dict is also the
    # REVERSE map's source (`SPORT_KEY_TO_CATEGORY`), and that lookup is exact —
    # a backend key missing from here is a stored affinity the preferences
    # endpoint silently declines to serve back. Keys per `utils/sport_keys.py`
    # plus the live `aussierules_aflw` (#6671).
    "aussierules": ["aussierules_afl", "aussierules_aflw", "aussierules_other"],
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

# A client key that reached `_expand_sport_affinities` before it had a mapping was
# passed through VERBATIM (the unrecognised-key branch below) and is sitting in
# `users.sport_affinities` under its own name. This lookup is exact, so adding the
# mapping alone repairs only the NEXT save and is inert for every reader who
# already made the choice — which is the entire population the repair is for.
# Naming the stored key here is what makes it retroactive (#6671, CERT-2999).
_PASS_THROUGH_STORED_KEYS: dict[str, str] = {
    "aussierules": "aussierules",
}
for stored_key, category in _PASS_THROUGH_STORED_KEYS.items():
    SPORT_KEY_TO_CATEGORY.setdefault(stored_key, category)


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
    replace: bool = False  # Full-replace opt-in for website wizard; default additive (#13779)


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
    Save onboarding data. Additive for signed-in users who already have
    saved onboarding teams, category affinities, or a home location (#13779 / 427: A).

    Reopening the first-run checklist adds newly followed teams and unconfigured
    categories without removing prior favorites, altering existing Preferences
    category levels, or clearing home_location.
    """
    selections = (
        (body.local_teams, "local"),
        (body.follow_teams, "follow"),
        (body.alma_mater_teams, "alma_mater"),
        (body.rival_teams, "rival"),
    )
    submitted = {ref.team_id for refs, _ in selections for ref in refs}
    candidate_ids = {team_id for team_id in submitted if -(2**31) <= team_id < 2**31}
    canonical_ids: dict[int, int] = {}
    if candidate_ids:
        from app.utils.team_redirects import resolve_retired_team_ids_batch

        canonical_ids = await resolve_retired_team_ids_batch(db, candidate_ids)
        # Hold the team keys until the favorites have been saved. A concurrent
        # club fold cannot delete a validated team between this read and flush.
        existing = set(
            (
                await db.execute(
                    select(Team.id)
                    .where(Team.id.in_(sorted(canonical_ids.values())))
                    .order_by(Team.id)
                    .with_for_update(read=True, key_share=True)
                )
            )
            .scalars()
            .all()
        )
        canonical_ids = {
            original: canonical
            for original, canonical in canonical_ids.items()
            if canonical in existing
        }
    skipped = sorted(submitted - canonical_ids.keys())

    # 1. Replace existing onboarding-sourced favorites ONLY when the caller
    #    explicitly sends the complete edited state (website setup wizard).
    #    Default replace=False keeps earlier onboarding, Settings, and chip
    #    follows intact (protecting both 1.0.7 and 1.0.8 checklist sits).
    if body.replace:
        await db.execute(
            delete(UserFavorite).where(
                and_(
                    UserFavorite.user_id == user.id,
                    UserFavorite.source == "onboarding",
                )
            )
        )

    existing_pairs: set[tuple[int, str]] = set(
        (
            await db.execute(
                select(UserFavorite.team_id, UserFavorite.relation_type).where(
                    UserFavorite.user_id == user.id
                )
            )
        ).all()
    )

    # 2. Insert new favorites (without duplicating already-stored team relations)
    # With the new constraint (user_id, team_id, relation_type), a team can have
    # multiple relations (e.g., both "local" and "follow"). We track both existing
    # rows and (team_id, relation_type) pairs in this submission to prevent exact
    # duplicates.
    seen_pairs: set[tuple[int, str]] = set()
    for refs, relation_type in selections:
        for ref in refs:
            canonical_id = canonical_ids.get(ref.team_id)
            if (
                canonical_id is None
                or (canonical_id, relation_type) in seen_pairs
                or (canonical_id, relation_type) in existing_pairs
            ):
                continue
            seen_pairs.add((canonical_id, relation_type))
            db.add(
                UserFavorite(
                    user_id=user.id,
                    team_id=canonical_id,
                    relation_type=relation_type,
                    source="onboarding",
                    weight=1.0,
                )
            )

    # 3. Expand sport affinities to backend keys
    expanded_affinities = _expand_sport_affinities(body.sport_affinities)

    # 4. Update preferences (additive when a record already exists)
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs:
        if body.replace:
            prefs.home_location = body.home_location
            prefs.sport_affinities = expanded_affinities
            prefs.onboarding_completed = True
            prefs.onboarding_raw = body.raw_inputs
        else:
            if body.home_location is not None and body.home_location.strip():
                prefs.home_location = body.home_location.strip()
            existing_affinities = (
                dict(prefs.sport_affinities)
                if isinstance(prefs.sport_affinities, dict)
                else {}
            )
            # Picking a category in the checklist may raise a low stored level,
            # while untouched or higher stored levels stay unchanged (#13779).
            for backend_key, weight in expanded_affinities.items():
                stored = existing_affinities.get(backend_key)
                if stored is None or weight > stored:
                    existing_affinities[backend_key] = weight
            prefs.sport_affinities = existing_affinities
            prefs.onboarding_completed = True
            if body.raw_inputs:
                existing_raw = (
                    dict(prefs.onboarding_raw)
                    if isinstance(prefs.onboarding_raw, dict)
                    else {}
                )
                existing_raw.update(body.raw_inputs)
                prefs.onboarding_raw = existing_raw
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

    response: dict[str, str | bool | list[int]] = {
        "status": "ok",
        "onboarding_completed": True,
    }
    if skipped:
        response["skipped_team_ids"] = skipped
        response["message"] = (
            "Saved your preferences. Some selected teams no longer exist."
        )
    return response


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

_TEAM_SEARCH_TIER = {
    "basketball_nba": 1,
    "americanfootball_nfl": 1,
    "baseball_mlb": 1,
    "icehockey_nhl": 1,
    "soccer_epl": 1,
    "soccer_usa_mls": 1,
    "basketball_wnba": 2,
    "basketball_ncaab": 2,
    "americanfootball_ncaaf": 2,
    "soccer_germany_bundesliga": 2,
    "soccer_spain_la_liga": 2,
    "soccer_italy_serie_a": 2,
}
_TEAM_SEARCH_SPORT_LABELS = {
    **{
        key: league["name"]
        for sport in SPORT_HIERARCHY.values()
        for league in sport["leagues"]
        for key in league["sport_keys"]
    },
    "basketball_nba": "NBA",
    "americanfootball_nfl": "NFL",
    "baseball_mlb": "MLB",
    "icehockey_nhl": "NHL",
    "soccer_usa_mls": "MLS",
    "basketball_wnba": "WNBA",
    "basketball_ncaab": "NCAAB",
    "basketball_wncaab": "WNCAAB",
    "americanfootball_ncaaf": "NCAAF",
    "soccer_epl": "EPL",
    "soccer_spain_la_liga": "La Liga",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "UEFA Champions League",
    "soccer_uefa_champs_league_women": "UEFA Women's Champions League",
    "icehockey_ncaa": "NCAA Hockey",
    "baseball_ncaa": "NCAA Baseball",
}


def _team_search_sport_display(sport_key: str, sport_name: str | None) -> str:
    label = _TEAM_SEARCH_SPORT_LABELS.get(sport_key)
    if label:
        return label

    # The stored label is the same league name used by the search pills.
    label = (sport_name or "").strip()
    if (
        label
        and "_" not in label
        and label.casefold() != sport_key.replace("_", " ").casefold()
    ):
        return label
    return SPORT_PREFIX_TO_DISPLAY_FAMILY.get(sport_family_key(sport_key) or "", "Sport")


_TEAM_SEARCH_PRO_LEAGUES = frozenset(
    key for key in _TEAM_SEARCH_TIER if "_ncaa" not in key
) | {"soccer_france_ligue_one"}
_TEAM_SEARCH_COLUMNS = load_only(
    Team.id,
    Team.sport_id,
    Team.name,
    Team.espn_id,
    Team.location,
    Team.logo_url,
    Team.logo_url_small,
    Team.abbreviation,
)


def _onboarding_venue_pairs(pairs: set[tuple[int, int]]):
    if not pairs:
        return false()
    team_ids, sport_ids = zip(*sorted(pairs))
    return tuple_(Team.id, Team.sport_id).in_(
        select(
            func.unnest(bindparam(None, list(team_ids), type_=ARRAY(Integer))),
            func.unnest(bindparam(None, list(sport_ids), type_=ARRAY(Integer))),
        )
    )


def _onboarding_name_candidates(
    words: list[str],
    venue_aliases: VenueAliases,
) -> Select[tuple[Team, str, str]]:
    # Tokens contain only letters and digits. Anchor at the start of a word
    # so Real cannot match Montreal and Los cannot match Carlos.
    aliases_json = cast(Team.alternate_names, String)
    aliases = case((aliases_json.startswith("["), aliases_json), else_="")
    search_fields = (Team.name, Team.abbreviation, Team.location, aliases)
    retired = select(RetiredTeamRedirect.retired_team_id).where(
        RetiredTeamRedirect.canonical_team_id == Team.id,
        RetiredTeamRedirect.sport_id == Team.sport_id,
    )

    def retired_alias_match(pattern: str):
        return retired.where(
            RetiredTeamRedirect.retired_name.regexp_match(pattern)
        ).exists()

    venue_prefix = {
        word: _onboarding_venue_pairs(venue_aliases.prefix(word))
        for word in dict.fromkeys(words)
    }
    # Every result needs this term. The name arm can use ix_teams_name_trgm
    # separately from the saved location, abbreviation and JSON aliases.
    anchor = max(words, key=len)
    substring = f"%{anchor}%"
    possible_ids = union(
        select(Team.id).where(Team.name.ilike(substring)),
        select(Team.id).where(
            or_(
                Team.abbreviation.ilike(substring),
                Team.location.ilike(substring),
                aliases_json.ilike(substring),
            )
        ),
        select(RetiredTeamRedirect.canonical_team_id).where(
            RetiredTeamRedirect.retired_name.ilike(substring)
        ),
        select(Team.id).where(venue_prefix[anchor]),
    ).cte("possible_onboarding_team_ids")

    word_start = r"(?i)(?:^|\W|_)"
    matches = [
        or_(
            *(field.regexp_match(word_start + word) for field in search_fields),
            retired_alias_match(word_start + word),
            venue_prefix[word],
        )
        for word in dict.fromkeys(words)
    ]
    phrase = r"(?:\W|_)+".join(words)
    exact = rf"(?i)^\s*{phrase}\s*$"
    # Keep an exact alias inside a single JSON string.
    alias_phrase = r"(?:[\s.'’_&/-]+)".join(words)
    relevance = case(
        (Team.name.regexp_match(exact), 0),
        (
            or_(
                Team.abbreviation.regexp_match(exact),
                aliases.regexp_match(rf'(?i)"{alias_phrase}"'),
                retired_alias_match(exact),
                _onboarding_venue_pairs(venue_aliases.exact(words)),
            ),
            1,
        ),
        (Team.name.regexp_match(rf"(?i)^\s*{phrase}"), 2),
        (Team.name.regexp_match(word_start + phrase), 3),
        else_=4,
    )
    has_espn_id = func.nullif(Team.espn_id, "").is_not(None)
    tier = case(_TEAM_SEARCH_TIER, value=Sport.key, else_=5)
    order = [
        relevance,
        has_espn_id.desc(),
        func.length(Team.name),
        tier,
        Team.name,
        Team.id,
    ]
    if len(words) == 1:
        full_word = Team.name.regexp_match(word_start + words[0] + r"(?:$|\W|_)")
        pro_club = and_(
            Sport.key.in_(_TEAM_SEARCH_PRO_LEAGUES), or_(full_word, relevance <= 1)
        )
        # A top-league nickname prefix is more useful than a prefix in the
        # first word of another club's name. Keep exact matches ahead of it.
        location_length = func.length(Team.location)
        after_location = and_(
            func.substr(func.lower(Team.name), 1, location_length + 1)
            == func.lower(Team.location) + " ",
            func.substr(Team.name, location_length + 2).regexp_match(rf"(?i)^{words[0]}"),
        )
        last_word = Team.name.regexp_match(word_start + words[0] + r"[^\W_]*\s*$")
        nickname_prefix = and_(tier == 1, or_(after_location, last_word))
        order[:0] = [
            pro_club.desc().nulls_last(),
            case((relevance <= 1, 0), (nickname_prefix, 1), else_=2),
        ]
    return (
        select(Team, Sport.key, Sport.name)
        .options(_TEAM_SEARCH_COLUMNS)
        .join(possible_ids, possible_ids.c.id == Team.id)
        .join(Sport, Team.sport_id == Sport.id)
        .where(*matches, *club_filters(include_mlb_preseason=True))
        .order_by(*order)
        .limit(60)
    )


async def _fold_onboarding_season_clubs(
    db: AsyncSession,
    clubs: list[tuple[Team, str, str]],
    *,
    mls_metro: bool = False,
) -> list[tuple[Team, str, str]]:
    parents = {
        key: key.removesuffix("_preseason").removesuffix("_summer_league")
        for _, key, _ in clubs
        if is_season_variant(key)
    }
    # Only this US metro lookup can assume an MLS parent for the Leagues Cup.
    # The existing identity check still requires the two registrations to match.
    if mls_metro and any(key == _LEAGUES_CUP for _, key, _ in clubs):
        parents[_LEAGUES_CUP] = "soccer_usa_mls"
    if not parents:
        return clubs

    variants = [team for team, key, _ in clubs if key in parents]
    espn_ids = {team.espn_id for team in variants if team.espn_id}
    names = {team.name for team in variants}
    # Search the parent leagues in one read. Literal ILIKE can use the name
    # index even when the preseason copy differs in case.
    name_matches = []
    for name in sorted(names):
        escaped = name.replace("|", "||").replace("%", "|%").replace("_", "|_")
        name_matches.append(Team.name.ilike(escaped, escape="|"))
    parent_rows = (
        await db.execute(
            select(Team, Sport.key, Sport.name)
            .options(_TEAM_SEARCH_COLUMNS)
            .join(Sport, Team.sport_id == Sport.id)
            .where(
                Sport.key.in_(sorted(set(parents.values()))),
                or_(Team.espn_id.in_(sorted(espn_ids)), *name_matches),
                *club_filters(),
            )
        )
    ).all()

    folded = []
    for team, sport_key, sport_name in clubs:
        if sport_key not in parents:
            folded.append((team, sport_key, sport_name))
            continue
        parent_key = parents[sport_key]
        league_clubs = [
            (parent, name) for parent, key, name in parent_rows if key == parent_key
        ]
        matching_ids = [
            (parent, name)
            for parent, name in league_clubs
            if team.espn_id and parent.espn_id == team.espn_id
        ]
        matching_names = [
            (parent, name)
            for parent, name in league_clubs
            if parent.name.casefold() == team.name.casefold()
            and not (parent.espn_id and team.espn_id and parent.espn_id != team.espn_id)
        ]
        # Equivalent ESPN rows still go through the membership winner below.
        if matching_ids:
            parent, name = min(matching_ids, key=lambda match: match[0].id)
            folded.append((parent, parent_key, name))
        elif (
            matching_names
            and len({parent.espn_id for parent, _ in matching_names if parent.espn_id})
            <= 1
        ):
            parent, name = min(
                matching_names, key=lambda match: (not match[0].espn_id, match[0].id)
            )
            folded.append((parent, parent_key, name))
        elif sport_key != "baseball_mlb_preseason":
            folded.append((team, sport_key, sport_name))
    return folded


async def _verified_onboarding_clubs(
    db: AsyncSession,
    rows: list[tuple[Team, str, str]],
) -> list[tuple[Team, str, str]]:
    eligible = await onboarding_team_members(
        [(team.sport_id, team.id) for team, _, _ in rows]
    )
    if eligible is None:
        return rows

    by_id = {team.id: team for team, _, _ in rows}
    other_ids = set(eligible.values()) - by_id.keys()
    if other_ids:
        # A verified ESPN alias can match when its canonical club did not.
        # Fetch only the canonical IDs named for the shortlisted candidates.
        teams = await db.scalars(
            select(Team)
            .options(_TEAM_SEARCH_COLUMNS)
            .join(Sport, Sport.id == Team.sport_id)
            .where(Team.id.in_(sorted(other_ids)), *club_filters())
        )
        by_id.update((team.id, team) for team in teams)

    verified = []
    for matched, sport_key, sport_name in rows:
        canonical_id = eligible.get((matched.sport_id, matched.id))
        if canonical_id is None:
            continue
        canonical = by_id.get(canonical_id)
        if (
            canonical
            and canonical.sport_id == matched.sport_id
            and canonical.espn_id == matched.espn_id
        ):
            verified.append((canonical, sport_key, sport_name))
    return verified


@router.get("/teams/search", response_model=list[TeamSearchResult])
async def search_teams(
    q: str,
    db: AsyncSession = Depends(get_db),
) -> list[TeamSearchResult]:
    """Rank saved clubs, then filter by league when the snapshot is available."""
    if len(q) > 200:
        return []
    words = re.findall(r"[^\W_]+", q)
    if len(words) > 12 or sum(map(len, words)) < 2:
        return []

    venue_aliases = onboarding_venue_aliases(db)
    rows = (await db.execute(_onboarding_name_candidates(words, venue_aliases))).all()
    if not rows:
        return []
    folded = await _fold_onboarding_season_clubs(
        db, [(team, key, name) for team, key, name in rows]
    )
    clubs = await _verified_onboarding_clubs(db, folded) if folded else []

    # ESPN uses a shared soccer club key across competitions. Require the
    # full name to agree too. All other rows keep their stored team identity.
    groups: dict[int | tuple[str, str], TeamSearchResult] = {}
    seen_names_and_leagues: set[tuple[str, str]] = set()
    seen_espn_ids_and_leagues: set[tuple[str, str]] = set()
    for team, sport_key, sport_name in clubs:
        name_and_league = (team.name, sport_key)
        espn_id_and_league = (team.espn_id, sport_key) if team.espn_id else None
        if (
            name_and_league in seen_names_and_leagues
            or espn_id_and_league in seen_espn_ids_and_leagues
        ):
            continue
        seen_names_and_leagues.add(name_and_league)
        if espn_id_and_league:
            seen_espn_ids_and_leagues.add(espn_id_and_league)
        key = team.id
        if team.espn_id and sport_key.startswith("soccer_"):
            key = (team.espn_id, " ".join(team.name.casefold().split()))
        variant = TeamSportVariant(
            id=team.id,
            sport_key=sport_key,
            sport_display=_team_search_sport_display(sport_key, sport_name),
        )
        if key in groups:
            groups[key].sports.append(variant)
        else:
            groups[key] = TeamSearchResult(
                id=team.id,
                name=team.name,
                location=team.location,
                sport_key=sport_key,
                logo_url=team.logo_url_small or team.logo_url,
                abbreviation=team.abbreviation,
                sports=[variant],
            )

    results = list(groups.values())[:20]
    mens_soccer_names = {
        result.name.casefold()
        for result in results
        if (result.sport_key or "").startswith("soccer_")
        and competition_gender(result.sport_key) == "men"
    }
    for result in results:
        # A single-competition result displays its team name in the installed app.
        if (
            result.name.casefold() in mens_soccer_names
            and (result.sport_key or "").startswith("soccer_")
            and competition_gender(result.sport_key) == "women"
        ):
            result.name += " (Women)"
        if len(result.sports) == 1:
            result.sports = []
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
    q_lower = q.strip().lower()
    if len(q_lower) < 2:
        return []

    from app.models.models import Sport

    terms = _expand_location_query(q_lower)
    scoped_metro = _METRO_LEAGUE_SCOPE.intersection(terms)
    college = Sport.key.regexp_match(r"_(?:w?ncaa|college)")
    location_matches = []
    brand_matches = []
    for term in terms:
        if len(term.replace(".", "")) <= 3 and len(terms) > 1:
            # Short aliases name a metro. A stored LA or D.C. label can match,
            # while the same letters in Lagos or La Coruña prove no link.
            location_matches.append(func.lower(Team.location) == term)
            brand_matches.append(
                Team.name.regexp_match(rf"^{re.escape(term.upper())}(?:$|\W)")
            )
            continue
        if term == "washington" and q_lower in _DC:
            # The state and its college teams share this generic label.
            location_matches.append(and_(func.lower(Team.location) == term, ~college))
            brand_matches.append(
                and_(Team.name.istartswith(term + " ", autoescape=True), ~college)
            )
            continue
        boundary = rf"(?i)^{re.escape(term)}(?:$|\W)"
        location_matches.append(
            Team.location.istartswith(term, autoescape=True)
            if len(terms) == 1
            else Team.location.regexp_match(boundary)
        )
        brand_matches.append(Team.name.regexp_match(boundary))
    for metro in sorted(scoped_metro):
        for league, names in _METRO_CLUB_ALIASES.get(metro, {}).items():
            brand_matches.append(and_(Sport.key == league, func.lower(Team.name).in_(names)))

    filters = list(club_filters(include_mlb_preseason=True))
    if scoped_metro:
        variants = {
            key + suffix
            for key in _METRO_CLUB_LEAGUES
            for suffix in ("_preseason", "_summer_league")
        }
        filters.append(or_(college, Sport.key.in_(sorted(_METRO_CLUB_LEAGUES | variants | {_LEAGUES_CUP}))))
    if "bay area" in scoped_metro:
        # College locations are sometimes an institution's abbreviated name.
        # A bare "Oakland" cannot place an Oakland University team in California.
        filters.append(~and_(college, func.lower(Team.location) == "oakland"))

    relevance = case(
        (func.lower(Team.location) == q_lower, 0),
        (Team.location.istartswith(q_lower, autoescape=True), 1),
        (Team.name.istartswith(q_lower + " ", autoescape=True), 2),
        else_=3,
    )

    result = await db.execute(
        select(Team, Sport.key, Sport.name)
        .options(_TEAM_SEARCH_COLUMNS)
        .join(Sport, Team.sport_id == Sport.id)
        .where(or_(*location_matches, and_(~college, or_(*brand_matches))), *filters)
        .order_by(relevance, Team.name, Team.id)
        # A named metro has a bounded league scope. Its raw registrations
        # can exceed the reader's cap before they fold into actual clubs.
        .limit(None if scoped_metro else 50)
    )
    rows = result.all()
    if not rows:
        return []
    folded = await _fold_onboarding_season_clubs(
        db, [(team, key, name) for team, key, name in rows], mls_metro=bool(scoped_metro)
    )
    clubs = await _verified_onboarding_clubs(db, folded) if folded else []

    seen: set[tuple[str, str]] = set()
    seen_schools: set[str] = set()
    results: list[TeamSearchResult] = []
    for team, sport_key, _ in clubs:
        college_team = is_college_sport(sport_key)
        if scoped_metro and not college_team and sport_key not in _METRO_CLUB_LEAGUES:
            continue
        name = " ".join(team.name.casefold().split())
        if scoped_metro and _METRO_MAJOR_CLUBS.get(name, sport_key) != sport_key:
            continue
        key = (sport_key, name)
        if college_team:
            school = school_label(team.name, team.location) or team.name
            school_key = " ".join(school.casefold().split())
            campus = (team.location or "").casefold().split()
            if campus and campus[-1] == "university" and school_key == "".join(word[0] for word in campus):
                school_key = " ".join(campus)
            key = ("college", school_key)
            if team.espn_id:
                if team.espn_id in seen_schools:
                    continue
                seen_schools.add(team.espn_id)
        if key in seen:
            continue
        seen.add(key)
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

    return results[:50]


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

    # Verify team exists (following retired_team_redirects for folded duplicate rows, #13229)
    target_team_id = body.team_id
    result = await db.execute(select(Team).where(Team.id == target_team_id))
    team = result.scalar_one_or_none()
    if not team:
        from app.utils.team_redirects import resolve_retired_team_id

        canonical_id = await resolve_retired_team_id(db, target_team_id)
        if canonical_id != target_team_id:
            canonical_result = await db.execute(select(Team).where(Team.id == canonical_id))
            team = canonical_result.scalar_one_or_none()
            if team:
                target_team_id = team.id
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    # Check for duplicate (same user, team, relation_type)
    result = await db.execute(
        select(UserFavorite).where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.team_id == target_team_id,
                UserFavorite.relation_type == body.relation_type,
            )
        )
    )
    if result.scalar_one_or_none():
        return {"status": "already_exists"}

    db.add(UserFavorite(
        user_id=user.id,
        team_id=target_team_id,
        relation_type=body.relation_type,
        source="manual",
        weight=1.0,
    ))
    await db.flush()

    safe_relation_type = {
        "follow": "follow",
        "local": "local",
        "alma_mater": "alma_mater",
        "rival": "rival",
    }[body.relation_type]
    logger.info(
        "Added favorite: user=%d team=%d type=%s",
        int(user.id),
        int(target_team_id),
        safe_relation_type,
    )
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

    target_team_id = team_id
    result = await db.execute(
        delete(UserFavorite).where(
            and_(
                UserFavorite.user_id == user.id,
                UserFavorite.team_id == target_team_id,
                UserFavorite.relation_type == relation_type,
            )
        )
    )

    if result.rowcount == 0:
        from app.utils.team_redirects import resolve_retired_team_id

        canonical_id = await resolve_retired_team_id(db, team_id)
        if canonical_id != team_id:
            target_team_id = canonical_id
            retry_result = await db.execute(
                delete(UserFavorite).where(
                    and_(
                        UserFavorite.user_id == user.id,
                        UserFavorite.team_id == target_team_id,
                        UserFavorite.relation_type == relation_type,
                    )
                )
            )
            result = retry_result

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Favorite not found")

    safe_relation_type = {
        "follow": "follow",
        "local": "local",
        "alma_mater": "alma_mater",
        "rival": "rival",
    }[relation_type]
    logger.info(
        "Removed favorite: user=%d team=%d type=%s",
        int(user.id),
        int(target_team_id),
        safe_relation_type,
    )
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

# #10078 — A SUM PAST 100% IS NOT ILLIQUIDITY. A many-winner board sums to its
# winner count: Kalshi's College Football Playoff Qualifiers (12 slots) summed
# 11.30, past the band, so Miami's 0.83/0.84 leg — and every NFL/NBA/NHL
# playoff-qualifier leg — was dropped from every team page as an "illiquid
# ladder". #237's own specimen (market 479, the Championship MVP board) quotes
# bid 0.00 / ask 1.00 on every leg; THAT is the illiquid class. So an over-sum
# board is illiquid only when the leg being served has no two-sided quote this
# tight. Measured 2026-10-01: 715 team-bound over-sum legs at <= 0.05.
_TEAM_ODDS_LIQUID_LEG_SPREAD_MAX = 0.05
# ...and a liquid leg priced near-certain stays suppressed: it is a ladder's
# bottom rung, not news. Without this, Miami's list would have opened with
# eight "Top 25 Ranked Teams" rows at 96-98% (one per poll date) above its
# 83.5% playoff leg; the board path that matters sits in the uncertain middle.
_TEAM_ODDS_LIQUID_LEG_PROB_MAX = 0.95


def _is_illiquid_binary_field(
    source: str | None, field_prob_sum, yes_bid=None, yes_ask=None, probability=None
) -> bool:
    """True for a Kalshi independent-binary award/prop field whose outcome
    probabilities sum well past 100% (the overrounded, illiquid ladder class)
    AND whose served leg has no tight two-sided quote, or is priced at or past
    ``_TEAM_ODDS_LIQUID_LEG_PROB_MAX`` (#10078).
    Source-scoped to Kalshi because odds_api fields are single coherent markets;
    a missing/None sum fails open (treated as coherent). A missing or zero bid
    is no quote — the leg stays illiquid."""
    if source != "kalshi" or field_prob_sum is None:
        return False
    try:
        if float(field_prob_sum) <= _TEAM_ODDS_COHERENT_FIELD_SUM_MAX:
            return False
    except (TypeError, ValueError):
        return False
    try:
        bid = float(yes_bid) if yes_bid is not None else None
        ask = float(yes_ask) if yes_ask is not None else None
        prob = float(probability) if probability is not None else None
    except (TypeError, ValueError):
        return True
    if prob is not None and prob >= _TEAM_ODDS_LIQUID_LEG_PROB_MAX:
        return True
    if bid is None or ask is None or bid <= 0 or ask < bid:
        return True
    return round(ask - bid, 4) > _TEAM_ODDS_LIQUID_LEG_SPREAD_MAX


def _many_winner_series_key(
    source: str | None, external_id: str | None, field_prob_sum, illiquid: bool
) -> str | None:
    """#10078: the Kalshi series of an over-sum board whose leg was SERVED (liquid,
    not near-certain), else None. One series can hold many such boards — dated
    poll ladders ("Top 25 on Oct 4 / Oct 11 AP Poll"), per-position fantasy
    top-10s — and one NFL page would otherwise gain 12 fantasy rows."""
    if illiquid or source != "kalshi" or not external_id or field_prob_sum is None:
        return None
    try:
        if float(field_prob_sum) <= _TEAM_ODDS_COHERENT_FIELD_SUM_MAX:
            return None
    except (TypeError, ValueError):
        return None
    return external_id.split("-", 1)[0] or None


async def _team_outcome_prices(
    db: AsyncSession, outcome_ids: list[int]
) -> tuple[list[dict], dict[str, str]]:
    """#10090: fresh prices for team-page rows already on screen, by outcome id.

    The row fields `_query_team_futures` serves for one leg — probability, 24h
    move, rank, field size, graded winner — under the SAME refusals it applies:
    open, not game-bound (`event_id IS NULL`), and not withheld by the market
    page's screen plus board staleness (#8503, #11534). A refused leg gets an
    explicit disposition (`withheld` / `closed`), never a bare number, so a row
    stops showing a price the page would no longer serve. Which rows a team page
    shows (coherence, series caps) is composition and stays with the full read.

    FAILS CLOSED, unlike the page read: a screen that cannot run returns
    `unresolved` for every leg, so a live patch never prints an unscreened price.
    """
    from app.routes.futures import withheld_price_outcome_ids_for_markets
    from app.routes.prop_families import _board_staleness_withheld

    dispositions = {f"outcome-{oid}": "missing" for oid in outcome_ids}
    if not outcome_ids:
        return [], dispositions
    outcomes = (await db.execute(
        select(FuturesOutcome).where(FuturesOutcome.id.in_(outcome_ids))
    )).scalars().all()
    market_ids = sorted({o.market_id for o in outcomes})
    markets = (await db.execute(
        select(FuturesMarket)
        .where(FuturesMarket.id.in_(market_ids))
        .options(selectinload(FuturesMarket.outcomes))
    )).scalars().all() if market_ids else []
    by_market = {m.id: m for m in markets}

    screen = await db.begin_nested()
    try:
        withheld = await withheld_price_outcome_ids_for_markets(db, list(markets))
        for market in markets:
            stopped = await _board_staleness_withheld(db, market)
            if stopped:
                withheld[market.id] = withheld.get(market.id, set()) | stopped
        await screen.commit()
    except Exception:  # noqa: BLE001 — refuse, never patch unscreened
        await screen.rollback()
        logger.exception("team outcome prices: price screen failed for %s", market_ids)
        for outcome in outcomes:
            dispositions[f"outcome-{outcome.id}"] = "unresolved"
        return [], dispositions

    items = []
    for outcome in outcomes:
        key = f"outcome-{outcome.id}"
        market = by_market.get(outcome.market_id)
        if market is None or market.status != "open" or market.event_id is not None:
            dispositions[key] = "closed"
            continue
        if outcome.id in withheld.get(market.id, ()):
            dispositions[key] = "withheld"
            continue
        revision = outcome.__dict__.get("last_updated")
        if isinstance(revision, datetime) and revision.tzinfo is None:
            revision = revision.replace(tzinfo=timezone.utc)
        items.append({
            "outcome_id": outcome.id,
            "market_id": market.id,
            "probability": float(outcome.current_probability) if outcome.current_probability is not None else None,
            "probability_change_24h": float(outcome.probability_change_24h) if outcome.probability_change_24h is not None else None,
            "rank": outcome.rank,
            "total_outcomes": len(market.outcomes),
            "is_winner": bool(outcome.is_winner),
            "price_revision_at": revision.isoformat() if isinstance(revision, datetime) else None,
        })
        dispositions[key] = "updated"
    return items, dispositions


def _prefer_coherent_team_items(per_team_items: dict[int, list[dict]]) -> None:
    """#237 Item 3, in place: when a team has at least one coherent candidate, drop
    its illiquid-binary ones (keyed on the private ``_illiquid_binary`` flag); keep
    the illiquid ones only when that is ALL the team has, so a followed team is
    never emptied. Strips the private flags from every surviving item afterward.
    Both directions matter: illiquid Kalshi is suppressed when a coherent field
    exists, and the coherent field always survives.

    #10078: a served over-sum leg (private ``_many_winner_series``) keeps only the
    first — highest-priced, the list's own order — leg of its Kalshi series per
    team. Single-winner boards carry no key and are never capped here."""
    for tid, tid_items in per_team_items.items():
        coherent = [it for it in tid_items if not it.get("_illiquid_binary")]
        if coherent and len(coherent) < len(tid_items):
            per_team_items[tid] = coherent
    for tid, tid_items in per_team_items.items():
        seen_series: set[str] = set()
        kept = []
        for it in tid_items:
            series = it.get("_many_winner_series")
            if series:
                if series in seen_series:
                    continue
                seen_series.add(series)
            kept.append(it)
        per_team_items[tid] = kept
    for tid_items in per_team_items.values():
        for it in tid_items:
            it.pop("_illiquid_binary", None)
            it.pop("_many_winner_series", None)


_TEAM_FUTURES_PG_QUERY_TIMEOUT_MS = 8000
_TEAM_FUTURES_PG_SCREEN_TIMEOUT_MS = 5000
_SCREEN_WAVE_SIZE = 60


class _LiteScreenOutcome:
    """Lightweight slots container for Postgres screening (avoids selectinload ORM bloat)."""

    __slots__ = (
        "id",
        "market_id",
        "current_probability",
        "current_yes_bid",
        "current_yes_ask",
        "resolution_source",
        "is_winner",
        "volume_24h",
        "volume_24h_at",
        "last_updated",
    )

    def __init__(self, row: Any) -> None:
        (
            self.id,
            self.market_id,
            self.current_probability,
            self.current_yes_bid,
            self.current_yes_ask,
            self.resolution_source,
            self.is_winner,
            self.volume_24h,
            self.volume_24h_at,
            self.last_updated,
        ) = row


class _LiteScreenMarket:
    """Lightweight slots container for Postgres screening (avoids selectinload ORM bloat)."""

    __slots__ = (
        "id",
        "source",
        "external_id",
        "status",
        "event_id",
        "market_type",
        "market_metadata",
        "updated_at",
        "name",
        "outcomes",
    )

    def __init__(self, row: Any) -> None:
        (
            self.id,
            self.source,
            self.external_id,
            self.status,
            self.event_id,
            self.market_type,
            self.market_metadata,
            self.updated_at,
            self.name,
        ) = row
        self.outcomes: list[_LiteScreenOutcome] = []


async def _load_pg_screen_wave(db: AsyncSession, wave_ids: list[int]) -> list[_LiteScreenMarket]:
    """Fetch minimal screen columns via two flat tuple queries (no ORM IdentityMap overhead)."""
    m_rows = (
        await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.source,
                FuturesMarket.external_id,
                FuturesMarket.status,
                FuturesMarket.event_id,
                FuturesMarket.market_type,
                FuturesMarket.market_metadata,
                FuturesMarket.updated_at,
                FuturesMarket.name,
            ).where(FuturesMarket.id.in_(wave_ids))
        )
    ).all()
    if not m_rows:
        return []
    o_rows = (
        await db.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.market_id,
                FuturesOutcome.current_probability,
                FuturesOutcome.current_yes_bid,
                FuturesOutcome.current_yes_ask,
                FuturesOutcome.resolution_source,
                FuturesOutcome.is_winner,
                FuturesOutcome.volume_24h,
                FuturesOutcome.volume_24h_at,
                FuturesOutcome.last_updated,
            ).where(FuturesOutcome.market_id.in_(wave_ids))
        )
    ).all()
    by_market = {row[0]: _LiteScreenMarket(row) for row in m_rows}
    for row in o_rows:
        market = by_market.get(row[1])
        if market is not None:
            market.outcomes.append(_LiteScreenOutcome(row))
    return list(by_market.values())
_AWARD_OUTCOMES_TTL = 60.0
_AWARD_OUTCOMES_CACHE_MAX = 4
# (engine_key) -> (monotonic_at, list_of_snapshots)
_award_outcomes_cache: dict[int, tuple[float, list]] = {}
_inflight_locks: dict[tuple, asyncio.Lock] = {}

_AWARD_KEYWORDS: tuple[str, ...] = (
    "MVP",
    "Player of the Year",
    "Rookie of the Year",
    "Defensive Player",
    "Coach of the Year",
    "Cy Young",
    "Heisman",
    "Most Improved",
    "Sixth Man",
    "Clutch",
    # Note: "Finals MVP" is subsumed by "%MVP%" and is omitted from the PG pattern list.
    "All-Star",
)


def _is_postgresql_session(db: Any) -> bool:
    """True only for real AsyncSessions connected to PostgreSQL (never SQLite or mocks)."""
    if not isinstance(db, AsyncSession):
        return False
    try:
        bind = db.get_bind()
        return getattr(getattr(bind, "dialect", None), "name", None) == "postgresql"
    except Exception:
        return False


def _cache_scope_key(db: Any) -> int:
    """Per-engine scope for real AsyncSessions; per-session-id scope for mocks/SQLite."""
    if isinstance(db, AsyncSession):
        try:
            bind = db.get_bind()
            if bind is not None:
                return id(bind)
        except Exception:
            return id(db)
    return id(db)


def _get_inflight_lock(namespace: str, cache_key: tuple) -> asyncio.Lock:
    """Loop-bound singleflight lock (safe across pytest function loops)."""
    loop_key = (id(asyncio.get_running_loop()), namespace, cache_key)
    lock = _inflight_locks.get(loop_key)
    if lock is None:
        if len(_inflight_locks) > 512:
            for k in [kk for kk, lk in _inflight_locks.items() if not lk.locked()][:256]:
                _inflight_locks.pop(k, None)
        lock = asyncio.Lock()
        _inflight_locks[loop_key] = lock
    return lock


async def _set_local_timeout_pg(db: AsyncSession, timeout_ms: int) -> None:
    """Arm SET LOCAL statement_timeout on real PG AsyncSessions only."""
    if _is_postgresql_session(db):
        await db.execute(text(f"SET LOCAL statement_timeout = '{int(timeout_ms)}'"))


async def _get_local_timeout_pg(db: AsyncSession) -> str | None:
    """Read current PostgreSQL session statement_timeout, or None for non-PG."""
    if not _is_postgresql_session(db):
        return None
    val = (await db.execute(text("SHOW statement_timeout"))).scalar_one_or_none()
    return None if val is None else str(val)


async def _restore_local_timeout_pg(db: AsyncSession, prev_timeout: str | None) -> None:
    """Restore caller transaction's statement_timeout before returning."""
    if not _is_postgresql_session(db) or prev_timeout is None:
        return
    await db.execute(
        text("SELECT set_config('statement_timeout', :val, true)"),
        {"val": str(prev_timeout)},
    )


@asynccontextmanager
async def _pg_capped_tx(db: AsyncSession, is_pg: bool, timeout_ms: int):
    """Run PG capped queries inside an outer SAVEPOINT and restore caller timeout on exit."""
    if not is_pg:
        yield
        return
    prev_timeout = await _get_local_timeout_pg(db)
    savepoint = await db.begin_nested()
    try:
        await _set_local_timeout_pg(db, timeout_ms)
        yield
    except BaseException:
        try:
            await savepoint.rollback()
        except Exception:
            logger.warning("team futures: outer savepoint rollback failed", exc_info=True)
        raise
    else:
        await savepoint.commit()
    finally:
        if prev_timeout is not None:
            try:
                await _restore_local_timeout_pg(db, prev_timeout)
            except Exception:
                logger.warning("team futures: restore statement_timeout failed", exc_info=True)


def _snapshot_award_rows(raw_rows: list) -> list[tuple]:
    """Detach cached Query-2 award rows into plain attribute holders (no session pin)."""
    snaps: list[tuple] = []
    for o, m, sk in raw_rows:
        o_ns = SimpleNamespace(
            id=o.id,
            market_id=o.market_id,
            external_id=getattr(o, "external_id", None),
            name=o.name,
            team_id=o.team_id,
            current_probability=o.current_probability,
            probability_change_24h=o.probability_change_24h,
            current_yes_bid=getattr(o, "current_yes_bid", None),
            current_yes_ask=getattr(o, "current_yes_ask", None),
            rank=o.rank,
            is_winner=o.is_winner,
            resolution_source=getattr(o, "resolution_source", None),
        )
        m_ns = SimpleNamespace(
            id=m.id,
            source=m.source,
            external_id=getattr(m, "external_id", None),
            sport_id=getattr(m, "sport_id", None),
            event_id=getattr(m, "event_id", None),
            name=m.name,
            llm_sport_category=m.llm_sport_category,
            market_tier=m.market_tier,
            market_type=getattr(m, "market_type", None),
            status=getattr(m, "status", "open"),
            resolution_date=m.resolution_date,
            canonical_market_key=m.canonical_market_key,
            market_metadata=getattr(m, "market_metadata", None),
        )
        snaps.append((o_ns, m_ns, sk))
    return snaps


def _build_team_futures_result_item(
    outcome: Any,
    market: Any,
    matched: dict,
    *,
    outcome_total: int | None,
    field_prob_sum: float | None,
) -> dict:
    prob = float(outcome.current_probability) if outcome.current_probability is not None else None
    change = (
        float(outcome.probability_change_24h)
        if outcome.probability_change_24h is not None
        else None
    )
    season_year = _extract_season_year(market.canonical_market_key, market.name)
    _illiquid = _is_illiquid_binary_field(
        market.source,
        field_prob_sum,
        getattr(outcome, "current_yes_bid", None),
        getattr(outcome, "current_yes_ask", None),
        outcome.current_probability,
    )
    return {
        "outcome_id": outcome.id,
        "outcome_name": reader_outcome_name(
            getattr(outcome, "external_id", None),
            outcome.name,
            market_threshold_label(market),
            market_name=getattr(market, "name", None),
        )
        or outcome.name,
        "market_id": market.id,
        "market_name": market.name,
        "market_tier": market.market_tier,
        "category": market.llm_sport_category,
        "source": market.source,
        "probability": prob,
        "source_mark": futures_outcome_source_mark(market, outcome, {"probability": prob}),
        "probability_change_24h": change,
        "rank": outcome.rank,
        "total_outcomes": outcome_total,
        "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
        "is_winner": bool(outcome.is_winner),
        "matched_team": matched,
        "canonical_market_key": market.canonical_market_key,
        "season_year": season_year,
        "_illiquid_binary": _illiquid,
        "_many_winner_series": _many_winner_series_key(
            market.source,
            getattr(market, "external_id", None),
            field_prob_sum,
            _illiquid,
        ),
    }


class TeamFuturesScreenUnavailableError(HTTPException):
    """Raised when the team-futures price screen fails and zero verified items survive."""

    def __init__(
        self,
        detail: str = "Team futures price screen unavailable; no verified markets survived",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


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

    is_pg = _is_postgresql_session(db)
    async with _pg_capped_tx(db, is_pg, _TEAM_FUTURES_PG_QUERY_TIMEOUT_MS):

        # Load Team records with their sport for sport-scoped matching (BR53).
        team_stmt = (
            select(Team, Sport.key.label("sport_key"))
            .join(Sport, Team.sport_id == Sport.id)
            .where(Team.id.in_(team_ids))
        )
        if isinstance(db, AsyncSession):
            team_stmt = team_stmt.options(
                load_only(
                    Team.id,
                    Team.sport_id,
                    Team.name,
                    Team.espn_id,
                    Team.logo_url_small,
                    Team.logo_url,
                    Team.primary_color,
                    Team.alternate_names,
                    Team.roster_players,
                )
            )
        team_result = await db.execute(team_stmt)
        teams: dict[int, Team] = {}
        # team_id → sport category (e.g., "hockey", "baseball")
        team_sport_categories: dict[int, str] = {}
        # team_id → sport key, for the side test (#9593)
        team_sport_keys: dict[int, str] = {}
        for t, sport_key in team_result.all():
            teams[t.id] = t
            team_sport_keys[t.id] = sport_key
            cat = _sport_key_llm_category(sport_key)
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
        loaded_teams: dict[int, Team] = dict(teams)
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
                return re.sub(r"\s+", " ", (nm or "").strip().lower())

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
            # The collapse never crosses sport_id, so a cluster shares one key.
            team_sport_keys = {
                id_to_canonical.get(_tid, _tid): _key
                for _tid, _key in team_sport_keys.items()
            }

        # Build ILIKE patterns from FULL team names only — no alternate_names,
        # no short suffixes.  This prevents "Bears" (from "Brown Bears") from
        # matching "Chicago Bears" or "Eagles" matching "Philadelphia Eagles".
        #
        # #9219 — EVERY MEMBER'S SPELLING, NOT ONLY THE CANONICAL'S. The patterns
        # used to be built after the collapse, from the one row that won it. The
        # Canadiens are 568 "Montreal Canadiens" and 3706 "Montréal Canadiens", tied
        # on mappings and name length, so whichever won, the other spelling was
        # never searched: the page served 3 of the club's markets while the
        # division, playoff-round and title legs, all named "Montreal Canadiens",
        # sat unread. A dupe row's full name is the same club's full name, so it
        # is searched too and a hit resolves to the canonical.
        team_patterns: list[str] = []
        seen_lower: set[str] = set()
        member_names: dict[int, list[str]] = {}
        # Build roster player name → team ID map (for Python-side matching)
        player_to_team_id: dict[str, int] = {}

        for member_id, member in loaded_teams.items():
            canonical_id = id_to_canonical.get(member_id, member_id)
            if canonical_id not in teams or not member.name:
                continue
            names = member_names.setdefault(canonical_id, [])
            if member.name not in names:
                names.append(member.name)
            escaped = _escape_like(member.name.strip())
            if escaped.lower() not in seen_lower:
                seen_lower.add(escaped.lower())
                team_patterns.append(escaped)

        for t in teams.values():
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

        roster_regex: re.Pattern[str] | None = None
        if player_to_team_id:
            # Longest-first single C-engine alternation skips linear ~800-key scans per outcome.
            roster_keys_desc = sorted(player_to_team_id, key=len, reverse=True)
            roster_regex = re.compile("|".join(re.escape(k) for k in roster_keys_desc))

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
        # #1197 (r259): split OR into separate indexed branches.
        # #13573: push sport-category scoping down into SQL (matching
        # `_find_matched_team`: exact match or empty/NULL for name; fail-open
        # foreign-sport denylist for FK so NON_SPORT_LLM_CATEGORIES / NULL stay
        # eligible) and materialize candidate outcome ids BEFORE joining/probing
        # `futures_outcomes` / `futures_markets` (`ofo_hits` filters game props
        # on `open_futures_outcomes`, `tail_scan` scans only `id > floor` by PK
        # so the 8.8M trigram GIN is untouched, and `fk_hits` can run Index-Only
        # over `ix_fo_team_market_id`).
        all_have_cat = bool(teams) and all(
            bool(team_sport_categories.get(t.id)) for t in teams.values()
        )
        allowed_team_cats = (
            sorted({team_sport_categories[t.id] for t in teams.values()})
            if all_have_cat
            else []
        )
        known_sport_cats = frozenset(SPORT_PREFIX_TO_LLM_CATEGORY.values()) | {"handball"}
        foreign_sport_cats = (
            sorted(known_sport_cats - set(allowed_team_cats)) if all_have_cat else []
        )
        name_sport_filters = []
        if is_pg and allowed_team_cats:
            name_sport_filters.append(
                or_(
                    FuturesMarket.llm_sport_category.is_(None),
                    FuturesMarket.llm_sport_category == "",
                    FuturesMarket.llm_sport_category.in_(allowed_team_cats),
                )
            )
        fk_sport_filters = []
        if is_pg and foreign_sport_cats:
            fk_sport_filters.append(
                or_(
                    FuturesMarket.llm_sport_category.is_(None),
                    ~FuturesMarket.llm_sport_category.in_(foreign_sport_cats),
                )
            )

        _order_by = (
            FuturesOutcome.current_probability.desc().nulls_last(),
            func.abs(FuturesOutcome.probability_change_24h).desc().nulls_last(),
            FuturesOutcome.id.asc(),
        )

        _outcome_load_opts = load_only(
            FuturesOutcome.id,
            FuturesOutcome.market_id,
            FuturesOutcome.external_id,
            FuturesOutcome.name,
            FuturesOutcome.team_id,
            FuturesOutcome.current_probability,
            FuturesOutcome.probability_change_24h,
            FuturesOutcome.current_yes_bid,
            FuturesOutcome.current_yes_ask,
            FuturesOutcome.rank,
            FuturesOutcome.is_winner,
            FuturesOutcome.resolution_source,
            FuturesOutcome.last_updated,
            FuturesOutcome.volume_24h,
            FuturesOutcome.volume_24h_at,
        )
        _market_load_opts = load_only(
            FuturesMarket.id,
            FuturesMarket.source,
            FuturesMarket.external_id,
            FuturesMarket.sport_id,
            FuturesMarket.event_id,
            FuturesMarket.name,
            FuturesMarket.llm_sport_category,
            FuturesMarket.market_tier,
            FuturesMarket.market_type,
            FuturesMarket.status,
            FuturesMarket.resolution_date,
            FuturesMarket.canonical_market_key,
            FuturesMarket.market_metadata,
            FuturesMarket.updated_at,
        )

        def _q1(cond):
            stmt = (
                select(FuturesOutcome, FuturesMarket, Sport.key.label("market_sport_key"))
                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
                .where(and_(*market_base_filters, cond))
                .order_by(*_order_by)
                .limit(limit * 5)
            )
            if isinstance(db, AsyncSession):
                stmt = stmt.options(_outcome_load_opts, _market_load_opts)
            return stmt

        _tq = time.perf_counter()
        if is_pg:
            if is_real_pg_engine(db):
                open_fk_ids = list(
                    (
                        await db.execute(
                            select(FuturesMarket.id).where(
                                *market_base_filters,
                                *fk_sport_filters,
                            )
                        )
                    ).scalars().all()
                )
                if not open_fk_ids:
                    rows1 = []
                else:
                    open_fk_param = bindparam(
                        "open_fk_ids", value=open_fk_ids, type_=ARRAY(Integer)
                    )
                    fk_hits = (
                        select(FuturesOutcome.id.label("outcome_id"))
                        .where(
                            FuturesOutcome.team_id.in_(team_ids),
                            FuturesOutcome.market_id == any_(open_fk_param),
                        )
                        .cte("fk_hits")
                        .prefix_with("MATERIALIZED")
                    )
                    fk_stmt = _q1(
                        FuturesOutcome.id
                        == any_(func.array(select(fk_hits.c.outcome_id).scalar_subquery()))
                    )
                    rows1 = list((await db.execute(fk_stmt)).all())
            else:
                fk_hits = (
                    select(FuturesOutcome.id.label("outcome_id"))
                    .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                    .where(
                        FuturesOutcome.team_id.in_(team_ids),
                        *market_base_filters,
                        *fk_sport_filters,
                    )
                    .cte("fk_hits")
                    .prefix_with("MATERIALIZED")
                )
                fk_stmt = _q1(
                    FuturesOutcome.id
                    == any_(func.array(select(fk_hits.c.outcome_id).scalar_subquery()))
                )
                rows1 = list((await db.execute(fk_stmt)).all())
        else:
            fk_stmt = _q1(FuturesOutcome.team_id.in_(team_ids))
            rows1 = list((await db.execute(fk_stmt)).all())
        if team_patterns:
            if is_pg:
                from app.utils.open_futures_outcomes import open_outcomes_floor

                pats = [f"%{p}%" for p in team_patterns]
                pats_expr = literal(pats, ARRAY(Text))
                floor = open_outcomes_floor()
                if floor is not None:
                    ofo_hits = (
                        select(OpenFuturesOutcome.outcome_id.label("outcome_id"))
                        .join(
                            FuturesMarket,
                            FuturesMarket.id == OpenFuturesOutcome.market_id,
                        )
                        .where(
                            OpenFuturesOutcome.name.ilike(any_(pats_expr)),
                            *market_base_filters,
                            *name_sport_filters,
                        )
                        .cte("ofo_hits")
                        .prefix_with("MATERIALIZED")
                    )
                    tail_scan = (
                        select(
                            FuturesOutcome.id.label("outcome_id"),
                            FuturesOutcome.market_id.label("market_id"),
                            FuturesOutcome.name.label("name"),
                        )
                        .where(FuturesOutcome.id > floor)
                        .cte("tail_scan")
                        .prefix_with("MATERIALIZED")
                    )
                    tail_hits = (
                        select(tail_scan.c.outcome_id.label("outcome_id"))
                        .join(FuturesMarket, FuturesMarket.id == tail_scan.c.market_id)
                        .where(
                            tail_scan.c.name.ilike(any_(pats_expr)),
                            *market_base_filters,
                            *name_sport_filters,
                        )
                    )
                    name_hits = (
                        select(ofo_hits.c.outcome_id.label("outcome_id"))
                        .union_all(tail_hits)
                        .cte("name_hits")
                        .prefix_with("MATERIALIZED")
                    )
                    name_stmt = _q1(
                        FuturesOutcome.id
                        == any_(
                            func.array(select(name_hits.c.outcome_id).scalar_subquery())
                        )
                    )
                else:
                    pg_name_cond = FuturesOutcome.name.ilike(any_(pats_expr))
                    name_stmt = (
                        select(
                            FuturesOutcome,
                            FuturesMarket,
                            Sport.key.label("market_sport_key"),
                        )
                        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                        .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
                        .where(
                            and_(
                                *market_base_filters,
                                *name_sport_filters,
                                pg_name_cond,
                            )
                        )
                        .order_by(*_order_by)
                        .limit(limit * 5)
                    )
                    if isinstance(db, AsyncSession):
                        name_stmt = name_stmt.options(_outcome_load_opts, _market_load_opts)
            else:
                name_cond = or_(
                    *[FuturesOutcome.name.ilike(f"%{p}%") for p in team_patterns]
                )
                name_stmt = _q1(name_cond)
            name_rows = (await db.execute(name_stmt)).all()
            _seen_oids = {o.id for o, _m, _sk in rows1}
            rows1.extend(r for r in name_rows if r[0].id not in _seen_oids)
        if timings is not None:
            timings["q1"] = round((time.perf_counter() - _tq) * 1000)

        # ── Query 2: Award markets — fetch all outcomes, match players in Python ──
        # Only runs if we have roster players to match against.
        # Zero team/user inputs: cache on real PG sessions for 60s with singleflight.
        rows2: list = []
        _award_wall_ts: float | None = None
        if player_to_team_id:
            _tq = time.perf_counter()
            if is_pg:
                _eng_key = _cache_scope_key(db)
                _now_mono = time.monotonic()
                cached_award = _award_outcomes_cache.get(_eng_key)
                if cached_award is not None and (_now_mono - cached_award[0]) < _AWARD_OUTCOMES_TTL:
                    _award_wall_ts, rows2 = cached_award[1], cached_award[2]
                else:
                    async with _get_inflight_lock("award_q2", (_eng_key,)):
                        _now_mono = time.monotonic()
                        cached_award = _award_outcomes_cache.get(_eng_key)
                        if cached_award is not None and (_now_mono - cached_award[0]) < _AWARD_OUTCOMES_TTL:
                            _award_wall_ts, rows2 = cached_award[1], cached_award[2]
                        else:
                            award_pats = [f"%{kw}%" for kw in _AWARD_KEYWORDS]
                            award_cond = FuturesMarket.name.ilike(any_(literal(award_pats, ARRAY(Text))))
                            query2 = (
                                select(FuturesOutcome, FuturesMarket, Sport.key.label("market_sport_key"))
                                .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
                                .outerjoin(Sport, FuturesMarket.sport_id == Sport.id)
                                .where(and_(*market_base_filters, award_cond))
                                .order_by(FuturesOutcome.current_probability.desc().nulls_last(), FuturesOutcome.id.asc())
                                .limit(500)
                                .options(_outcome_load_opts, _market_load_opts)
                            )
                            raw_award = (await db.execute(query2)).all()
                            rows2 = _snapshot_award_rows(raw_award)
                            _award_wall_ts = time.time()
                            if len(_award_outcomes_cache) >= _AWARD_OUTCOMES_CACHE_MAX:
                                oldest_ak = min(_award_outcomes_cache, key=lambda k: _award_outcomes_cache[k][0])
                                del _award_outcomes_cache[oldest_ak]
                            _award_outcomes_cache[_eng_key] = (time.monotonic(), _award_wall_ts, rows2)
            else:
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
                if isinstance(db, AsyncSession):
                    query2 = query2.options(_outcome_load_opts, _market_load_opts)
                result2 = await db.execute(query2)
                rows2 = result2.all()
            if timings is not None:
                timings["q2"] = round((time.perf_counter() - _tq) * 1000)

        # For each outcome, figure out which followed team matched ONCE (#13552).
        # Uses strict suffix-word matching + O(1)/regex roster player matching.
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
                market_sport_cat = _sport_key_llm_category(market_sport_key)
            outcome_name = outcome.name or ""
            market_name = (market.name or "").casefold()

            def _coach_surname_matches_city(team: Team) -> bool:
                # A stored Blues link can put Canadiens coach Martin St. Louis
                # on the Blues rail. A full roster match can still bind.
                if "coach of the year" not in market_name and "jack adams award" not in market_name:
                    return False
                if player_to_team_id.get(outcome_name.lower()) == team.id:
                    return False
                aliases = getattr(team, "alternate_names", None)
                return isinstance(aliases, list) and any(
                    given_name_before_city(outcome_name, alias, team.name, ignore_city_periods=True)
                    for alias in aliases if isinstance(alias, str)
                )

            # #2593 / #9593 / #9761: verify sport, gender side, and league on every branch.
            def _crosses_side(team_id: int) -> bool:
                return _link_crosses_gender(
                    market.name,
                    team_sport_keys.get(team_id),
                    market_sport_key,
                    getattr(market, "source", None),
                    getattr(market, "external_id", None),
                ) or _link_crosses_league(
                    getattr(market, "source", None),
                    getattr(market, "external_id", None),
                    team_sport_keys.get(team_id),
                    _market_event_slug(getattr(market, "market_metadata", None)),
                )

            canonical_id = id_to_canonical.get(outcome.team_id) if outcome.team_id else None
            if canonical_id and (
                _link_crosses_sport(market_sport_cat, team_sport_categories.get(canonical_id))
                or _crosses_side(canonical_id)
            ):
                canonical_id = None
            if canonical_id and canonical_id in teams:
                t = teams[canonical_id]
                if not _coach_surname_matches_city(t):
                    return {
                        "id": t.id,
                        "name": t.name,
                        "logo_small": t.logo_url_small or t.logo_url,
                        "primary_color": t.primary_color,
                    }
            # Name matching — use strict suffix-word logic to prevent
            # "Bears" (from "Brown Bears") matching "Chicago Bears".
            for t in teams.values():
                if any(
                    _strict_team_name_matches(nm, outcome_name)
                    for nm in member_names.get(t.id, [t.name or ""])
                ):
                    # BR53: verify sport compatibility for name matches
                    if market_sport_cat:
                        team_cat = team_sport_categories.get(t.id)
                        if team_cat and team_cat != market_sport_cat:
                            continue  # sport mismatch — try next team
                    if _crosses_side(t.id) or _coach_surname_matches_city(t):
                        continue
                    return {
                        "id": t.id,
                        "name": t.name,
                        "logo_small": t.logo_url_small or t.logo_url,
                        "primary_color": t.primary_color,
                    }
            # Roster player matching — O(1) exact check first, single compiled regex for substrings.
            if player_to_team_id:
                outcome_lower = outcome_name.lower()
                exact_tid = player_to_team_id.get(outcome_lower)
                if exact_tid is not None:
                    t = teams.get(exact_tid)
                    if t:
                        ok = True
                        if market_sport_cat:
                            team_cat = team_sport_categories.get(t.id)
                            if team_cat and team_cat != market_sport_cat:
                                ok = False
                        if ok and _crosses_side(t.id):
                            ok = False
                        if ok:
                            return {
                                "id": t.id,
                                "name": t.name,
                                "logo_small": t.logo_url_small or t.logo_url,
                                "primary_color": t.primary_color,
                            }
                if roster_regex is not None and roster_regex.search(outcome_lower):
                    for player_lower, tid in player_to_team_id.items():
                        if player_lower in outcome_lower:
                            t = teams.get(tid)
                            if t:
                                if market_sport_cat:
                                    team_cat = team_sport_categories.get(t.id)
                                    if team_cat and team_cat != market_sport_cat:
                                        continue  # sport mismatch — try next player
                                if _crosses_side(t.id):
                                    continue  # the other side's market (#9593)
                                return {
                                    "id": t.id,
                                    "name": t.name,
                                    "logo_small": t.logo_url_small or t.logo_url,
                                    "primary_color": t.primary_color,
                                }
            return None

        candidate_rows = list(rows1) + list(rows2)
        matched_rows: list[tuple[Any, Any, str | None, dict]] = []
        matched_oids_by_market: dict[int, set[int]] = {}
        for _o, _m, _sk in candidate_rows:
            _matched = _find_matched_team(_o, _m, market_sport_key=_sk)
            if not _matched:
                continue
            matched_rows.append((_o, _m, _sk, _matched))
            matched_oids_by_market.setdefault(_m.id, set()).add(_o.id)

        # #1197 / #13552: scoped per-market stats ONLY for markets that matched a team.
        _mkt_ids = sorted(matched_oids_by_market)
        _market_stats: dict[int, tuple[int, float | None]] = {}
        _tq = time.perf_counter()
        if _mkt_ids:
            for _mid, _tot, _fsum in (await db.execute(
                select(
                    FuturesOutcome.market_id,
                    func.count().label("outcome_total"),
                    func.sum(FuturesOutcome.current_probability).label("field_prob_sum"),
                )
                .where(FuturesOutcome.market_id.in_(_mkt_ids))
                .group_by(FuturesOutcome.market_id)
            )).all():
                _market_stats[_mid] = (_tot, _fsum)
        if timings is not None:
            timings["stats"] = round((time.perf_counter() - _tq) * 1000)
            timings["rows1"] = len(rows1)
            timings["rows2"] = len(rows2)

        # Pre-build per-row candidate item stubs (reused across early-stop checks + final build).
        candidate_items: list[tuple[int, int, dict]] = []
        team_has_coherent_candidate: dict[int, set[int]] = {}
        for idx, (_o, _m, _sk, _matched) in enumerate(matched_rows):
            _otot, _fsum = _market_stats.get(_m.id, (None, None))
            _stub = _build_team_futures_result_item(
                _o,
                _m,
                _matched,
                outcome_total=_otot,
                field_prob_sum=_fsum,
            )
            candidate_items.append((_o.id, _m.id, _stub))
            if not _stub["_illiquid_binary"]:
                team_has_coherent_candidate.setdefault(_matched["id"], set()).add(_m.id)

        def _pick_next_wave_ids(
            screened_mids: set[int],
            focus_tids: set[int] | None,
        ) -> list[int]:
            """Prioritize coherent-first candidates round-robin per team for the next wave."""
            per_team_coh: dict[int, list[int]] = {}
            per_team_ill: dict[int, list[int]] = {}
            seen_per_team_mid: dict[int, set[int]] = {}
            for _oid, _mid, _stub in candidate_items:
                if _mid in screened_mids:
                    continue
                tid = _stub["matched_team"]["id"]
                if focus_tids is not None and tid not in focus_tids:
                    continue
                seen_m = seen_per_team_mid.setdefault(tid, set())
                if _mid in seen_m:
                    continue
                seen_m.add(_mid)
                if not _stub["_illiquid_binary"]:
                    per_team_coh.setdefault(tid, []).append(_mid)
                else:
                    per_team_ill.setdefault(tid, []).append(_mid)

            wave: list[int] = []
            wave_set: set[int] = set()
            # Sort teams by highest unscreened candidate probability desc for fair round-robin order.
            top_prob_by_tid: dict[int, float] = {}
            for _oid, _mid, _stub in candidate_items:
                if _mid in screened_mids:
                    continue
                tid = _stub["matched_team"]["id"]
                if focus_tids is not None and tid not in focus_tids:
                    continue
                p = _stub.get("probability") or 0.0
                if not _stub["_illiquid_binary"]:
                    p += 10.0  # coherent first in screening order
                if tid not in top_prob_by_tid or p > top_prob_by_tid[tid]:
                    top_prob_by_tid[tid] = p
            tids_order = sorted(top_prob_by_tid, key=lambda tid: top_prob_by_tid[tid], reverse=True)

            # Interleave coherent buckets first, then illiquid buckets.
            for buckets in (per_team_coh, per_team_ill):
                depth = 0
                while len(wave) < _SCREEN_WAVE_SIZE:
                    progressed = False
                    for tid in tids_order:
                        b = buckets.get(tid)
                        if b and depth < len(b):
                            mid = b[depth]
                            progressed = True
                            if mid not in wave_set:
                                wave.append(mid)
                                wave_set.add(mid)
                                if len(wave) >= _SCREEN_WAVE_SIZE:
                                    break
                    if not progressed:
                        break
                    depth += 1
            return sorted(wave)

        def _prefix_cutoff_state(
            screened_mids: set[int],
            withheld_map: dict[int, set[int]],
        ) -> tuple[bool, set[int]]:
            """Sound certificate proving whether remaining unscreened markets cannot enter items[:limit]."""
            all_tids = list(
                dict.fromkeys(_stub["matched_team"]["id"] for _oid, _mid, _stub in candidate_items)
            )
            if not all_tids:
                return True, set()

            mid_has_any_coherent: dict[int, bool] = {}
            for _oid, _mid, _stub in candidate_items:
                if not _stub["_illiquid_binary"]:
                    mid_has_any_coherent[_mid] = True
                else:
                    mid_has_any_coherent.setdefault(_mid, False)

            sim_seen_mids: set[int] = set()
            screened_all_items: dict[int, list[tuple[int, dict]]] = {}
            for idx, (oid, mid, _stub) in enumerate(candidate_items):
                if mid not in screened_mids:
                    continue
                if mid in sim_seen_mids:
                    continue
                if oid in withheld_map.get(mid, ()):
                    continue
                sim_seen_mids.add(mid)
                tid = _stub["matched_team"]["id"]
                screened_all_items.setdefault(tid, []).append((idx, _stub))

            coherent_survives_by_tid: dict[int, bool] = {
                tid: any(not it["_illiquid_binary"] for _i, it in screened_all_items.get(tid, ()))
                for tid in all_tids
            }
            first_unscreened_idx: dict[int, int] = {tid: len(candidate_items) for tid in all_tids}
            unscreened_coh_exists: dict[int, bool] = {tid: False for tid in all_tids}
            for idx, (_oid, _mid, _stub) in enumerate(candidate_items):
                tid = _stub["matched_team"]["id"]
                if _mid not in screened_mids:
                    if not _stub["_illiquid_binary"]:
                        unscreened_coh_exists[tid] = True
                    # If this team already has a surviving coherent item AND this market has
                    # NO coherent candidates for ANY team, it can never keep/claim a slot.
                    if coherent_survives_by_tid[tid] and not mid_has_any_coherent.get(_mid, False):
                        continue
                    if idx < first_unscreened_idx[tid]:
                        first_unscreened_idx[tid] = idx

            locked_prefix: dict[int, list[dict]] = {}
            needs_more_tids: set[int] = set()
            for tid in all_tids:
                all_t_rows = screened_all_items.get(tid, [])
                has_unscreened = first_unscreened_idx[tid] < len(candidate_items)
                coherent_survives = coherent_survives_by_tid[tid]
                if not coherent_survives and unscreened_coh_exists[tid]:
                    locked_prefix[tid] = []
                    needs_more_tids.add(tid)
                    continue

                prefix = [
                    it for idx, it in all_t_rows if idx < first_unscreened_idx[tid]
                ]
                if coherent_survives:
                    prefix = [it for it in prefix if not it["_illiquid_binary"]]
                seen_series: set[str] = set()
                deduped: list[dict] = []
                for it in prefix:
                    ser = it.get("_many_winner_series")
                    if ser:
                        if ser in seen_series:
                            continue
                        seen_series.add(ser)
                    deduped.append(it)
                locked_prefix[tid] = deduped
                if has_unscreened and not deduped:
                    needs_more_tids.add(tid)

            if needs_more_tids:
                return False, needs_more_tids

            unscreened_tids = [
                tid for tid in all_tids if first_unscreened_idx[tid] < len(candidate_items)
            ]
            if not unscreened_tids:
                return True, set()

            d_safe = min(len(locked_prefix[tid]) for tid in unscreened_tids)
            non_empty_tids = [tid for tid in all_tids if locked_prefix[tid]]
            if not non_empty_tids:
                return False, set(unscreened_tids)

            ordered_tids = sorted(
                non_empty_tids,
                key=lambda tid: (locked_prefix[tid][0].get("probability") or 0),
                reverse=True,
            )
            rr_count = 0
            for depth in range(d_safe):
                for tid in ordered_tids:
                    if depth < len(locked_prefix[tid]):
                        rr_count += 1
                        if rr_count >= limit:
                            return True, set()

            # Need more items from teams with unscreened markets that ran shallowest first.
            focus = {tid for tid in unscreened_tids if len(locked_prefix[tid]) <= d_safe}
            return False, (focus or set(unscreened_tids))

        # #8503 / #11534 / #13552: screen in bounded waves inside SAVEPOINT; run hoisted
        # staleness BEFORE snapshot trade reads so stopped/dead boards skip 51 GB trade lookups.
        withheld_by_market: dict[int, set[int]] = {}
        _screen_ids = _mkt_ids
        _screened_mids: set[int] = set()
        _total_screened = 0
        _screen_waves = 0
        _screen_early_stopped = False
        _screen_incomplete = False
        _screen_unscreened_count = 0
        if _screen_ids:
            from app.routes import prop_families as prop_families_route
            from app.routes.futures import withheld_price_outcome_ids_for_markets
            from app.utils.futures_price_screen import (
                _fleet_newest_observation as _shared_fleet_newest,
            )

            # Capture the original function so monkeypatches in tests are still honored.
            _orig_staleness_fn = getattr(prop_families_route, "_orig_board_staleness_withheld", None)
            if _orig_staleness_fn is None:
                prop_families_route._orig_board_staleness_withheld = prop_families_route._board_staleness_withheld
                _orig_staleness_fn = prop_families_route._orig_board_staleness_withheld

            _tq = time.perf_counter()
            _focus_tids: set[int] | None = None
            _fleet_newest_val: Any = None
            while len(_screened_mids) < len(_screen_ids):
                if len(_screen_ids) <= _SCREEN_WAVE_SIZE and not _screened_mids:
                    wave_ids = list(_screen_ids)
                else:
                    wave_ids = _pick_next_wave_ids(_screened_mids, _focus_tids)
                    if not wave_ids and _focus_tids is not None:
                        wave_ids = _pick_next_wave_ids(_screened_mids, None)
                    if not wave_ids:
                        break

                _screen_waves += 1
                _screen_savepoint = await db.begin_nested()
                _wave_markets: list = []
                try:
                    await _set_local_timeout_pg(db, _TEAM_FUTURES_PG_SCREEN_TIMEOUT_MS)
                    if is_pg:
                        _wave_markets = await _load_pg_screen_wave(db, wave_ids)
                    else:
                        screen_stmt = (
                            select(FuturesMarket)
                            .where(FuturesMarket.id.in_(wave_ids))
                            .options(selectinload(FuturesMarket.outcomes))
                        )
                        _wave_markets = (await db.execute(screen_stmt)).scalars().all()
                    _total_screened += len(_wave_markets)

                    # Run board staleness FIRST with ONE hoisted fleet observation across waves (#13552).
                    _fn = prop_families_route._board_staleness_withheld
                    if _fn is _orig_staleness_fn:
                        if _fleet_newest_val is None and _wave_markets:
                            _fleet_newest_val = await _shared_fleet_newest(db, *_wave_markets)
                        for _m in _wave_markets:
                            _stopped = await _fn(db, _m, fleet_newest=_fleet_newest_val)
                            if _stopped:
                                withheld_by_market[_m.id] = (
                                    withheld_by_market.get(_m.id, set()) | _stopped
                                )
                    else:
                        for _m in _wave_markets:
                            _stopped = await _fn(db, _m)
                            if _stopped:
                                withheld_by_market[_m.id] = (
                                    withheld_by_market.get(_m.id, set()) | _stopped
                                )

                    # Skip trade snapshot lookups for boards whose matched outcomes are already all stopped.
                    _surviving_markets = [
                        _m
                        for _m in _wave_markets
                        if not (
                            matched_oids_by_market.get(_m.id, set())
                            <= withheld_by_market.get(_m.id, set())
                        )
                    ]
                    if _surviving_markets:
                        _price_withheld = await withheld_price_outcome_ids_for_markets(
                            db, _surviving_markets
                        )
                        for _pmid, _poids in _price_withheld.items():
                            if _poids:
                                withheld_by_market[_pmid] = (
                                    withheld_by_market.get(_pmid, set()) | _poids
                                )
                            else:
                                withheld_by_market.setdefault(_pmid, set())
                    await _screen_savepoint.commit()
                except Exception as _screen_exc:  # noqa: BLE001 — omit unscreened markets cleanly
                    await _screen_savepoint.rollback()
                    _screen_incomplete = True
                    _screen_unscreened_count = len(_screen_ids) - len(_screened_mids)
                    if is_statement_timeout(_screen_exc):
                        logger.warning(
                            "team futures: price screen timed out for teams %s after %d ms — omitting %d unscreened markets (keeping %d screened)",
                            sorted(teams),
                            _TEAM_FUTURES_PG_SCREEN_TIMEOUT_MS,
                            _screen_unscreened_count,
                            len(_screened_mids),
                        )
                    else:
                        logger.exception(
                            "team futures: price screen failed for teams %s — omitting %d unscreened markets (keeping %d screened)",
                            sorted(teams),
                            _screen_unscreened_count,
                            len(_screened_mids),
                        )
                    break

                _screened_mids.update(wave_ids)
                if len(_screened_mids) >= len(_screen_ids):
                    break
                _done, _focus_tids = _prefix_cutoff_state(_screened_mids, withheld_by_market)
                if _done:
                    _screen_early_stopped = True
                    break
                await asyncio.sleep(0)

            if timings is not None:
                timings["screen"] = round((time.perf_counter() - _tq) * 1000)
                timings["screened"] = _total_screened

        if timings is not None:
            timings["screen_waves"] = _screen_waves
            timings["screen_incomplete"] = _screen_incomplete
            timings["screen_unscreened"] = _screen_unscreened_count
            if _award_wall_ts is not None:
                timings["_award_cached_at"] = _award_wall_ts

    # Process matched result rows in original candidate order using single-pass matched_rows.
    per_team_items: dict[int, list[dict]] = {}
    seen_market_ids: set[int] = set()  # Deduplicate: one outcome per market
    for oid, mid, item in candidate_items:
        if (_screen_early_stopped or _screen_incomplete) and mid not in _screened_mids:
            continue
        if mid in seen_market_ids:
            continue
        if oid in withheld_by_market.get(mid, ()):
            continue  # #8503: the market page refuses this price
        seen_market_ids.add(mid)
        per_team_items.setdefault(item["matched_team"]["id"], []).append(item)

    # #237 Item 3: prefer coherent fields.
    _prefer_coherent_team_items(per_team_items)

    # Round-robin fill via shared Stage 2 My Stuff surface ranker.
    items = order_my_stuff_team_buckets(
        per_team_items,
        limit=limit,
        profile=MY_STUFF_SURFACE_PROFILE,
    )

    if _screen_incomplete and not items:
        raise TeamFuturesScreenUnavailableError()

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

    result: dict[str, Any] = {
        "items": items,
        "teams": teams_list,
        "team_ids": list(teams.keys()),
        "total_count": len(items),
    }
    if _screen_incomplete:
        result["partial"] = True
        result["omitted_count"] = _screen_unscreened_count
    return result


_team_futures_cache: dict[tuple, tuple[float, dict]] = {}
_shared_team_futures_cache: dict[tuple, tuple[float, dict]] = {}
_TEAM_FUTURES_TTL = 120
_TEAM_FUTURES_MAX_SIZE = 100


def _cache_get(store: dict[tuple, tuple[float, dict]], key: tuple, now: float) -> dict | None:
    entry = store.get(key)
    if entry is not None and (now - entry[0]) < _TEAM_FUTURES_TTL:
        return entry[1]
    return None


def _cache_set(store: dict[tuple, tuple[float, dict]], key: tuple, now: float, data: dict) -> None:
    if len(store) >= _TEAM_FUTURES_MAX_SIZE and key not in store:
        oldest = min(store, key=lambda k: store[k][0])
        del store[oldest]
    store[key] = (now, data)


@router.get("/team-futures")
async def get_team_futures(
    limit: int = 20,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get futures outcomes for the current user's followed teams."""
    eff_limit = max(1, min(limit, 100))
    scope = _cache_scope_key(db)
    cache_key = (scope, user.id, eff_limit)
    _now = time.time()
    cached = _cache_get(_team_futures_cache, cache_key, _now)
    if cached is not None:
        return cached

    async with _get_inflight_lock("me_team_futures", cache_key):
        _now = time.time()
        cached = _cache_get(_team_futures_cache, cache_key, _now)
        if cached is not None:
            return cached

        fav_result = await db.execute(
            select(UserFavorite.team_id)
            .where(
                and_(
                    UserFavorite.user_id == user.id,
                    UserFavorite.relation_type != "rival",
                )
            )
            .distinct()
        )
        team_ids = [row[0] for row in fav_result.all()]

        if not team_ids:
            return {"items": [], "team_ids": [], "total_count": 0}

        route_meta: dict[str, Any] = {}
        data = await _query_team_futures(team_ids, db, limit=eff_limit, timings=route_meta)
        if not route_meta.get("screen_incomplete") and not data.get("partial"):
            _now = time.time()
            award_ts = route_meta.get("_award_cached_at")
            cache_ts = min(_now, float(award_ts)) if award_ts is not None else _now
            _cache_set(_team_futures_cache, cache_key, cache_ts, data)
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

    eff_limit = max(1, min(limit, 50))
    scope = _cache_scope_key(db)
    cache_key = (scope, tuple(sorted(set(parsed_ids))), eff_limit)
    _now = time.time()
    cached = _cache_get(_shared_team_futures_cache, cache_key, _now)
    if cached is not None:
        return cached

    async with _get_inflight_lock("shared_team_futures", cache_key):
        _now = time.time()
        cached = _cache_get(_shared_team_futures_cache, cache_key, _now)
        if cached is not None:
            return cached

        route_meta: dict[str, Any] = {}
        data = await _query_team_futures(parsed_ids, db, limit=eff_limit, timings=route_meta)
        if not route_meta.get("screen_incomplete") and not data.get("partial"):
            _now = time.time()
            award_ts = route_meta.get("_award_cached_at")
            cache_ts = min(_now, float(award_ts)) if award_ts is not None else _now
            _cache_set(_shared_team_futures_cache, cache_key, cache_ts, data)
        return data
