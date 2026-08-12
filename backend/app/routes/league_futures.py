"""League-scoped futures endpoint.

Returns all open futures markets for a specific league, grouped by section
(series, awards, props, season_stats, more_markets). Powers the league
page's below-the-grid sections.

Phase 3 generalizes the sectioned layout to all major sports (NBA, NHL, MLB, NFL)
with sport-aware keyword classification for awards, series, and props.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Path
from sqlalchemy import select, and_, or_, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Event, FuturesMarket, FuturesOutcome, Sport
from app.services import get_db
from app.utils.aggregation import compute_aggregate_probability
from app.utils.entity_page_tiers import (
    AVAILABILITY_DEGRADED,
    AVAILABILITY_EMPTY,
    AVAILABILITY_FRESH,
    AVAILABILITY_STALE,
    resolve_entity_tier,
)
from app.utils.event_concept_cache import (
    ConceptCacheKeys,
    acquire_refresh_lock,
    cache_keys,
    release_refresh_lock,
)
from app.utils.sport_keys import SPORT_HIERARCHY

logger = logging.getLogger(__name__)

#: The league tier's Redis namespace. These are the keys that have been live since
#: #777, and `cache_keys()` reproduces them EXACTLY (`<prefix><sport_key>` and
#: `…:stale`) — so adopting the shared four-key layout here is a drop-in that adds
#: a `:refreshing` lock without moving or orphaning a single existing entry.
LEAGUE_CACHE_PREFIX = "bainluck:league:"

#: How fresh a *live* hit is. Unchanged from the value this route has always used;
#: the defect #1767 fixes was never this number (see `_schedule_league_refresh`).
LEAGUE_PRIMARY_TTL = 300

#: How long the mirror outlives an outage. Also unchanged, and deliberately so:
#: shortening it would have traded a 24-hour lie for a shorter one while leaving
#: the missing revalidation — the actual defect — in place.
LEAGUE_STALE_TTL = 86400

router = APIRouter()

# Sport key → league name patterns for filtering (case-insensitive SQL ILIKE).
# Markets matching ANY pattern are included for that league.
LEAGUE_NAME_PATTERNS: dict[str, list[str]] = {
    "basketball_nba": ["NBA%", "%National Basketball%"],
    "basketball_wnba": ["WNBA%", "%Women_s National Basketball%"],
    "basketball_ncaab": ["%NCAA%Basketball%", "%March Madness%", "%College Basketball%"],
    "icehockey_nhl": ["NHL%", "%National Hockey%", "%Stanley Cup%"],
    "baseball_mlb": ["MLB%", "%Major League Baseball%", "%World Series%"],
    "americanfootball_nfl": ["NFL%", "%National Football%", "%Super Bowl%"],
    "americanfootball_ncaaf": ["%NCAA%Football%", "%College Football%", "%CFP%"],
    "soccer_epl": ["%Premier League%", "%EPL%"],
    "soccer_usa_mls": ["%MLS%", "%Major League Soccer%"],
    "soccer_spain_la_liga": ["%La Liga%", "%LaLiga%"],
    "soccer_germany_bundesliga": ["%Bundesliga%"],
    "soccer_uefa_champs_league": ["%Champions League%", "%UCL%"],
    "mma_mixed_martial_arts": ["%UFC%", "%Mixed Martial Arts%"],
    "tennis_atp": ["%ATP%", "%Roland Garros ATP%", "%Wimbledon%Men%", "%US Open%Men%", "%Australian Open%Men%"],
    "tennis_wta": ["%WTA%", "%Roland Garros WTA%", "%Wimbledon%Women%", "%US Open%Women%", "%Australian Open%Women%"],
    "boxing_boxing": ["%Boxing%", "%WBC%", "%WBA%", "%IBF%", "%WBO%"],
    "motorsport_f1": ["%Formula 1%", "%F1 %", "%Grand Prix%"],
    "motorsport_nascar": ["%NASCAR%"],
    "esports_lol": ["%League of Legends%", "%LoL %"],
    "esports_cs2": ["%Counter-Strike%", "%CS2%"],
    "esports_valorant": ["%Valorant%"],
}

# Sport key → Kalshi external_id prefix for precise filtering
LEAGUE_TICKER_PREFIXES: dict[str, list[str]] = {
    "basketball_nba": ["KXNBA"],
    "basketball_wnba": ["KXWNBA"],
    "basketball_ncaab": ["KXNCAAB", "KXMM"],
    "icehockey_nhl": ["KXNHL"],
    "baseball_mlb": ["KXMLB"],
    "americanfootball_nfl": ["KXNFL"],
    "americanfootball_ncaaf": ["KXNCAAF", "KXCFP"],
    "soccer_epl": ["KXEPL"],
    "soccer_usa_mls": ["KXMLS"],
    "mma_mixed_martial_arts": ["KXUFC"],
    "tennis_atp": ["KXATP"],
    "tennis_wta": ["KXWTA"],
    "boxing_boxing": ["KXBOXING", "KXWBC"],
    "motorsport_f1": ["KXF1"],
    "motorsport_nascar": ["KXNASCAR"],
    "esports_lol": ["KXLOL"],
    "esports_cs2": ["KXCS2"],
    "esports_valorant": ["KXVALORANT", "KXVAL"],
}

# ---------------------------------------------------------------------------
# Section assignment: sport-aware classification
# ---------------------------------------------------------------------------
# Target sections (matching frontend expectations):
#   series       — Playoff series matchups (Team A vs Team B, total games O/U)
#   awards       — MVP, ROY, Cy Young, Vezina, Selke, etc.
#   props        — Team-level props (win totals, div winners, playoff quals,
#                  trades, no-hitters, draft, Madden cover, etc.)
#   season_stats — Player stat-based markets (scoring leader, HR leader, etc.)
#   more_markets — Everything else
# ---------------------------------------------------------------------------

# Sport-specific award name fragments (matched case-insensitively).
# Generic awards ("MVP", "Rookie of the Year") are caught by tier == 3.
_AWARD_KEYWORDS: list[str] = [
    # NBA
    "defensive player of the year", "sixth man", "most improved",
    "clutch player", "finals mvp",
    # NHL
    "vezina", "selke", "norris", "conn smythe", "hart", "calder",
    "richard trophy", "art ross", "jack adams", "lady byng",
    # MLB
    "cy young", "hank aaron", "gold glove", "silver slugger",
    "reliever of the year", "manager of the year", "rookie of the year",
    # NFL
    "comeback player", "offensive player of the year",
    "defensive player of the year", "walter payton",
    "offensive rookie", "defensive rookie", "coach of the year",
    # MMA / UFC
    "fight of the year", "fighter of the year", "knockout of the year",
    "performance of the night",
]

# Keywords that identify a market as a playoff series matchup.
_SERIES_KEYWORDS: list[str] = [
    "series", "total games o/u", "total games over",
]

# Keywords for team/season-level props (not player stats).
_PROPS_KEYWORDS: list[str] = [
    "win total", "win more than", "win 100", "win 90", "win 80",
    "division winner", "make playoff", "clinch",
    "postseason", "wild card",
    "traded", "be traded", "trade",
    "no-hitter", "perfect game",
    "draft", "lottery",
    "cover of madden", "madden nfl",
    "debut date", "free agent",
    "sweep", "game 7", "playoff win total", "elimination",
    "fired", "general manager", "head coach",
    # Soccer
    "relegation", "promotion", "golden boot", "top scorer",
    # MMA / UFC
    "method of", "distance", "total rounds", "finish",
]

# Sports where "vs" indicates an individual match/fight, not a playoff series.
# Markets in these sports should go to "matches" section, not "series".
_INDIVIDUAL_MATCH_SPORTS: frozenset[str] = frozenset({
    "tennis", "mma", "boxing", "esports",
})

# Categories surfaced as a single, futures-ONLY hub: no per-game league split and
# no per-tournament event grouping yet, so head-to-head matchup markets are pure
# noise. Esports has thousands of per-map "Team A vs Team B" rows that would bury
# the genuine tournament outrights (MSI/LCK/Worlds/EWC winners), and there is no
# championship GRID for these — so we match the whole category, drop matchups, and
# surface title/winner markets in a "futures" section rather than hiding them.
# (#159-era lesson: esports data is messy — build only what honestly stands.)
_CATEGORY_WIDE_FUTURES_ONLY: frozenset[str] = frozenset({"esports"})

# Keywords for player-stat markets (season stats section).
_SEASON_STAT_KEYWORDS: list[str] = [
    "leader", "scoring title", "assists title", "rebounds title",
    "home run leader", "batting average", "era leader", "strikeout leader",
    "rushing leader", "passing leader", "receiving leader",
    "goal leader", "points leader", "save leader",
    "regular season record", "regular season wins",
    # Soccer
    "clean sheets", "assist leader", "top assists",
]


# ---------------------------------------------------------------------------
# UX-P062 (#1743, epic #1741): league identity, from the register
# ---------------------------------------------------------------------------

#: Every sport key that `SPORT_HIERARCHY` navigates to. This is what makes a
#: league a REAL entity for the tier resolver (spec §2): a registered league with
#: zero answers is a legitimate T0 page, while an unrecognised key is not a page at
#: all — that distinction is the generation gate, and it needs an identity source.
#: Derived from the register rather than re-listed, so adding a league to the nav
#: cannot leave a second list behind (the C23 constant-scatter lesson).
_REGISTERED_SPORT_KEYS: frozenset[str] = frozenset(
    key
    for sport in SPORT_HIERARCHY.values()
    for league in (sport.get("leagues") or [])
    for key in (league.get("sport_keys") or [])
)


#: How far back a settled game still counts as a RESULT worth showing. Long enough
#: that a league playing weekly still has receipts, short enough that "recent"
#: stays true.
RESULTS_LOOKBACK_DAYS = 14

#: Rail sizes. Both are counted caps (spec §4) — the payload carries the totals, so
#: a cap is never a silent truncation.
UPCOMING_GAMES_LIMIT = 8
RESULTS_LIMIT = 8


def _event_probability(event: Event) -> float | None:
    """The blended home win probability, or None when we never measured one.

    Calls the canonical blend — it does NOT roll its own mean over sources.
    Register E9 records a second blend algorithm living in
    `teams.py::_get_championship_path`; this is not a third.

    #1776: this used to read `win_probability_sources["aggregate"]["home"]`, and
    THAT KEY HAS NEVER EXISTED. The column's schema is
    `{source: {value, display_name, type, color}}` — there is no `aggregate`
    member, because the blend is COMPUTED (`compute_aggregate_probability`, the
    reader CLAUDE.md names for this JSONB) rather than stored. So the function
    returned None unconditionally, for every event, and every league rail rendered
    its fixtures with no number at all: measured 118 of 118 upcoming games across
    all 29 registered leagues, including a LIVE MLB game holding five sources.
    The docstring above was already right about the intent; only the read was wrong.

    `status` travels implicitly on the event, and that matters here: the same
    formatter serves the RECENT RESULTS rail, and the canonical blend deliberately
    drops Kalshi/Polymarket once a game is completed/closed (their prices go stale
    post-final). Re-deriving a status rule locally would be the second algorithm
    this docstring exists to refuse.

    The isinstance guard is KEPT from the pre-#1776 version rather than dropped as
    dead weight: `compute_aggregate_probability` does `wps.items()` on
    `win_probability_sources or {}`, so a truthy NON-dict in that JSONB column
    (a list, a bare string) raises AttributeError rather than returning None. This
    runs inside a per-item formatter, and a throw here does not blank one row — it
    empties the entire rail (gotcha #42). The upstream fragility is real and is
    reported on #1776; guarding at the call site is this queue's business, editing
    the shared blend every surface depends on is not.
    """
    if not isinstance(event.win_probability_sources, (dict, type(None))):
        return None
    return compute_aggregate_probability(event)


def _format_game_brief(event: Event) -> dict:
    """Compact league-rail shape for one game.

    Deliberately NOT the team page's `_format_event_brief`: that one takes a team
    and renders from that team's perspective ("we had them at 72%"). A league rail
    has no home side to speak from, so the probability is stated as the home team's
    and named as such rather than left ambiguous.
    """
    return {
        "id": event.id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "commence_time": event.commence_time.isoformat() if event.commence_time else None,
        "status": event.status,
        "home_score": event.home_score,
        "away_score": event.away_score,
        "home_win_probability": _event_probability(event),
    }


def _assign_section(market: FuturesMarket, sport_key: str = "") -> str:
    """Assign a market to a display section.

    Uses sport-aware keyword matching to classify into one of six sections:
    series, matches, awards, props, season_stats, more_markets.

    Individual match/fight sports (tennis, MMA, boxing, esports) use "matches"
    instead of "series" for head-to-head markets.
    """
    name_lower = (market.name or "").lower()
    cat = (market.category or "").lower()
    tier = market.market_tier

    # Determine sport category for match vs series classification
    sport_cat = sport_key.split("_")[0] if sport_key else ""
    is_individual_sport = sport_cat in _INDIVIDUAL_MATCH_SPORTS

    # Championship / conference / division (tier 1-2, 4) — already on grid
    if tier in (1, 2):
        return "championship"
    if tier == 4:
        return "championship"

    # --- Series / Matches ---
    # "vs" in a tier-5 market is a matchup — "series" for team sports, "matches"
    # for individual sports (tennis, MMA, boxing, esports).
    matchup_section = "matches" if is_individual_sport else "series"

    if any(kw in name_lower for kw in _SERIES_KEYWORDS):
        # Exception: "World Series Winner" is a championship, not a series
        if "world series winner" in name_lower:
            return "championship"
        return matchup_section
    if " vs " in name_lower or " vs. " in name_lower:
        # Tier-5 matchup
        if tier == 5:
            return matchup_section

    # For individual match sports, game_prop category markets are matches too
    if is_individual_sport and cat == "game_prop":
        return "matches"

    # --- Awards ---
    # Tier 3 = award by definition. Also match known award name fragments.
    if tier == 3 or cat in ("award", "mvp"):
        return "awards"
    if any(kw in name_lower for kw in _AWARD_KEYWORDS):
        return "awards"

    # --- Season stats (player-level) ---
    # Check before props because "leader" could overlap with "win total" props.
    if cat == "season_stat" or any(kw in name_lower for kw in _SEASON_STAT_KEYWORDS):
        return "season_stats"

    # --- Props (team/season-level) ---
    if any(kw in name_lower for kw in _PROPS_KEYWORDS):
        return "props"

    return "more_markets"


def league_cache_keys(sport_key: str) -> ConceptCacheKeys:
    """Every Redis key one league owns. Shared by the route and the refresh task so
    the two can never disagree about where the mirror lives."""
    return cache_keys(sport_key, prefix=LEAGUE_CACHE_PREFIX)


def _redis_or_none():
    """The bounded shared client, or None. Never raises (gotcha #39)."""
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _read_league_slot(rc, key: str) -> dict | None:
    """Read one league cache slot, or None.

    Deliberately NOT `event_concept_cache.read_slot`: that helper validates the
    stamped `cache` envelope and reads an unstamped payload as a MISS, so adopting
    it here would silently invalidate every live league entry and, worse, couple a
    revalidation fix to a payload-shape migration. The keys are shared; the codec
    is this tier's own until it adopts the envelope deliberately.
    """
    if rc is None:
        return None
    try:
        raw = rc.get(key)
    except Exception:
        logger.warning("league cache: read failed for %s", key)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        logger.warning("league cache: refusing undecodable payload for %s", key)
        return None
    return payload if isinstance(payload, dict) else None


def _write_league_payload(rc, keys: ConceptCacheKeys, payload: dict) -> None:
    """Write both slots. Never raises."""
    if rc is None:
        return
    try:
        encoded = json.dumps(payload, default=str)
        rc.setex(keys.primary, LEAGUE_PRIMARY_TTL, encoded)
        rc.setex(keys.stale, LEAGUE_STALE_TTL, encoded)
    except Exception:
        logger.warning("league cache: write failed for %s", keys.primary)


def _schedule_league_refresh(rc, keys: ConceptCacheKeys, sport_key: str) -> None:
    """Kick exactly one background rebuild for `sport_key` and return immediately.

    #1767. This is the half that was missing, and its absence was not a slow cache
    — it was a 24-hour one. The stale branch returned the mirror and scheduled
    NOTHING, and the build path is reached only when BOTH slots miss, so a league
    rebuilt once per `LEAGUE_STALE_TTL` and served a stale copy for the other
    23h55m: ~99.6% of loads, measured in production an hour after the UX-P062
    deploy with every sampled league still pinned on a pre-deploy payload.

    Single-flight: a burst of readers arriving behind one TTL expiry produces one
    rebuild, not one per reader. The owner token travels WITH the dispatch because
    this request acquires the lock and the worker releases it (#1678 finding 1) —
    a producer that cannot name the token does not get to release.

    Best-effort throughout: the caller has already decided to serve the mirror, and
    nothing here may turn a served page into an error. If the dispatch itself fails
    the lock is released, so a dead broker costs the next reader a retry rather
    than wedging the key for `REFRESH_LOCK_TTL`.

    The guard wraps the ACQUIRE as well as the dispatch, so "never errors the
    page" is a property of this function rather than one inherited from
    `acquire_refresh_lock`'s internal hardening. A guarantee that holds only
    because a callee currently swallows its own exceptions is one refactor away
    from being false, and the caller has already committed to a 200 by the time it
    gets here.
    """
    token = None
    try:
        token = acquire_refresh_lock(rc, keys)
        if not token:
            return

        from app.tasks import celery_app

        celery_app.send_task(
            "app.tasks.refresh_league", args=[sport_key, token], queue="background"
        )
    except Exception:
        logger.warning("league: refresh dispatch failed for %s", sport_key, exc_info=True)
        if token:
            release_refresh_lock(rc, keys, token)


def is_empty_league(payload: dict) -> bool:
    """A league with no sections and neither games rail has nothing on it."""
    return not (
        payload.get("sections")
        or payload.get("upcoming_games")
        or payload.get("recent_results")
    )


async def build_and_cache_league(sport_key: str, db: AsyncSession, rc=None) -> dict:
    """Build one league, write both slots, return the payload.

    One implementation for the route's cold path and the background refresh, so the
    two cannot drift in what they store.

    **A degraded build is never mirrored.** `build_league` returns the `degraded`
    envelope when its market query times out, and caching that would pin an outage
    into the 24h mirror — the one payload that must never outlive its cause.

    **An empty build never overwrites a NON-EMPTY mirror**, the ordering
    `build_and_cache_hub` established: writing first would clobber the good
    snapshot with the blank page and then "rescue" by reading back the blank we
    just stored.

    This diverges from the hub's version in one deliberate way: the hub skips the
    write whenever *any* stale entry exists, and this skips only when the existing
    mirror still has content. An empty league whose mirror is also empty is the
    ordinary steady state for the 7 registered leagues that genuinely have nothing
    (`wncaab`, `cfl`, `ufl`, …), and skipping there would leave the primary slot
    permanently unset — so every request would fall to the stale branch and
    schedule another refresh, forever. Refusing to overwrite nothing with nothing
    protects no data and costs a rebuild per lock window.
    """
    payload = await build_league(sport_key, db)
    keys = league_cache_keys(sport_key)

    if payload.get("availability") == AVAILABILITY_DEGRADED:
        return payload

    if is_empty_league(payload):
        mirror = _read_league_slot(rc, keys.stale)
        if mirror is not None and not is_empty_league(mirror):
            return payload

    _write_league_payload(rc, keys, payload)
    return payload


@router.get("/{sport_key}")
async def get_league_futures(
    sport_key: str = Path(..., description="Sport key (e.g., basketball_nba, icehockey_nhl)"),
    db: AsyncSession = Depends(get_db),
):
    """Get all open futures markets for a league, grouped by section."""
    rc = _redis_or_none()
    keys = league_cache_keys(sport_key)

    cached = _read_league_slot(rc, keys.primary)
    if cached is not None:
        return cached

    stale = _read_league_slot(rc, keys.stale)
    if stale is not None:
        # UX-P062 (#1743), register E6: this served a 24h-old snapshot with no
        # declaration at all, so a substituted answer was indistinguishable from
        # a current one — ruling 025 clause 4, the named violation. The payload
        # was cached with `availability: fresh`; it is not fresh now.
        #
        # #1767: and the declaration is what made the REAL defect visible — the
        # mirror was being served almost always, because nothing ever rebuilt it.
        # Serve it (a fast answer beats a correct wait) and revalidate behind it.
        _schedule_league_refresh(rc, keys, sport_key)
        stale["availability"] = AVAILABILITY_STALE
        return stale

    return await build_and_cache_league(sport_key, db, rc)


async def build_league(sport_key: str, db: AsyncSession) -> dict:
    """Build one league payload from the database. Does not touch the cache."""
    now = datetime.now(timezone.utc)

    # Determine the sport category from the key
    # e.g., basketball_nba → llm_sport_category = "basketball"
    sport_category = sport_key.split("_")[0]
    # Map common prefixes to their llm_sport_category values
    _SPORT_KEY_TO_LLM_CATEGORY: dict[str, str] = {
        "americanfootball": "football",
        "icehockey": "hockey",
        "motorsport": "motorsports",
    }
    sport_category = _SPORT_KEY_TO_LLM_CATEGORY.get(sport_category, sport_category)

    # Build query filters
    filters = [
        FuturesMarket.status == "open",
        FuturesMarket.event_id.is_(None),
        or_(
            FuturesMarket.resolution_date.is_(None),
            FuturesMarket.resolution_date >= now,
        ),
        FuturesMarket.llm_sport_category == sport_category,
    ]

    if sport_key in _CATEGORY_WIDE_FUTURES_ONLY:
        # Whole category (already scoped by llm_sport_category above) — no per-game
        # league split. Drop head-to-head matchups; for esports these are the
        # thousands of per-map "Team A vs Team B" rows that would bury the real
        # tournament futures.
        filters.append(~FuturesMarket.name.ilike("% vs %"))
        filters.append(~FuturesMarket.name.ilike("% vs. %"))
    else:
        # League-level filtering: use ticker prefix (Kalshi) + name patterns
        league_conditions = []
        ticker_prefixes = LEAGUE_TICKER_PREFIXES.get(sport_key, [])
        for prefix in ticker_prefixes:
            league_conditions.append(FuturesMarket.external_id.ilike(f"{prefix}%"))

        name_patterns = LEAGUE_NAME_PATTERNS.get(sport_key, [])
        for pattern in name_patterns:
            league_conditions.append(FuturesMarket.name.ilike(pattern))

        # Also match llm_league if set
        league_short = sport_key.split("_", 1)[1] if "_" in sport_key else sport_key
        league_conditions.append(FuturesMarket.llm_league.ilike(league_short))

        if league_conditions:
            filters.append(or_(*league_conditions))

    # Exclude game-level matchup markets (vs patterns)
    filters.append(~FuturesMarket.name.ilike("% at %"))

    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(*filters)
        .order_by(FuturesMarket.market_tier.asc().nulls_last())
        .limit(200)
    )

    try:
        result = await asyncio.wait_for(db.execute(query), timeout=25)
    except asyncio.TimeoutError:
        # UX-P062 (#1743), register E6: a statement timeout returned the SAME empty
        # shape as a league that genuinely has no markets, so an outage and an
        # off-season rendered identically. `degraded` is the whole distinction
        # (ruling 025 clause 4), and `tier: None` would tell the page to render a
        # confident T0 statement about data we failed to read.
        return {
            "sport_key": sport_key,
            "sections": {},
            "total_markets": 0,
            "error": "timeout",
            "tier": None,
            "availability": AVAILABILITY_DEGRADED,
            "pool_counts": {"answers": 0, "dropped": 0, "settled": 0},
            "section_counts": {},
        }
    markets = list(result.scalars().unique().all())

    # Group by section + deduplicate by canonical_market_key
    sections: dict[str, list[dict]] = {
        "futures": [],
        "series": [],
        "matches": [],
        "awards": [],
        "props": [],
        "season_stats": [],
        "more_markets": [],
    }

    seen_canonical: dict[str, dict] = {}

    # UX-P062 (#1743), register E8 / ruling 025 clause 3. The two price-based skips
    # below used to be bare `continue`s, so a section that lost every row to them
    # simply disappeared and the page reported the remainder as if it were the
    # whole. A swallow that counts is detection; a swallow that doesn't is
    # concealment. This counts them PER SECTION so the envelope can say "showing 3
    # of 11" instead of quietly saying "3".
    #
    # It deliberately does NOT change WHICH markets are skipped. Spec §10 E8 records
    # that skipping on price alone is the C16 class and that whatever Alex rules for
    # Discover binds here identically — that ruling is not this queue's to make, and
    # counting the skip is what makes the eventual decision measurable.
    resolved_skipped: dict[str, int] = {}

    #: Championship/conference/division rows, kept for the CENSUS only — the grid
    #: renders them. See the amendment note at the skip site below.
    championship_census: list[dict] = []

    for market in markets:
        section = _assign_section(market, sport_key)

        # Skip championship/conference/division — already on the grid
        if section == "championship":
            if sport_key in _CATEGORY_WIDE_FUTURES_ONLY:
                # No championship grid exists for these hubs — surface the
                # title/winner markets in a dedicated "futures" section instead of
                # dropping them (they are the whole point of the esports hub).
                section = "futures"
            else:
                # UX-P062 (#1743) + Alex's 2026-08-11 amendment: the grid IS the
                # rendering of this family, and it is the league page's centerpiece
                # — so it must COUNT, even though it is not rendered as cards here.
                #
                # This was the census hole. Dropping the row entirely meant the
                # title-winner family was invisible to the tier resolver, which is
                # why MLB measured "awards + props" and nothing else, and why zero
                # of 29 leagues could reach T3. Counted, not rendered.
                championship_census.append(
                    {
                        "id": market.id,
                        "group_id": market.group_id,
                        "canonical_market_key": market.canonical_market_key,
                        "status": market.status,
                        "resolution_date": (
                            market.resolution_date.isoformat()
                            if market.resolution_date
                            else None
                        ),
                        "top_outcomes": [
                            {
                                "probability": (
                                    float(o.current_probability)
                                    if o.current_probability is not None
                                    else None
                                )
                            }
                            for o in market.outcomes
                        ],
                    }
                )
                continue

        # Sort outcomes by probability descending
        sorted_outcomes = sorted(
            market.outcomes,
            key=lambda o: float(o.current_probability) if o.current_probability else 0,
            reverse=True,
        )

        # Skip effectively resolved markets (leader ≥97% and opened ≥85%)
        if sorted_outcomes:
            leader_prob = float(sorted_outcomes[0].current_probability) if sorted_outcomes[0].current_probability else 0
            if leader_prob >= 0.97:
                leader_opening = float(sorted_outcomes[0].opening_probability) if sorted_outcomes[0].opening_probability else None
                if leader_opening is not None and leader_opening >= 0.85:
                    resolved_skipped[section] = resolved_skipped.get(section, 0) + 1
                    continue
            # All-settled filter: skip if every outcome is <3% or >97% (post-season resolved)
            probs = [float(o.current_probability) for o in sorted_outcomes if o.current_probability is not None]
            if len(probs) >= 2 and all(p < 0.03 or p > 0.97 for p in probs):
                resolved_skipped[section] = resolved_skipped.get(section, 0) + 1
                continue

        outcomes_data = [
            {
                "id": o.id,
                "name": o.name,
                "probability": float(o.current_probability) if o.current_probability else None,
                "opening_probability": float(o.opening_probability) if o.opening_probability else None,
                "rank": o.rank,
                "movement_24h": float(o.probability_change_24h) if o.probability_change_24h else None,
                "team_id": o.team_id,
            }
            for o in sorted_outcomes[:10]
        ]

        market_data = {
            "id": market.id,
            "name": market.name,
            "source": market.source,
            "external_id": market.external_id,
            "market_tier": market.market_tier,
            "category": market.category,
            "resolution_date": market.resolution_date.isoformat() if market.resolution_date else None,
            "outcome_count": len(market.outcomes),
            "top_outcomes": outcomes_data,
            "canonical_market_key": market.canonical_market_key,
            # UX-P061 (#1742, epic #1741): the entity tier resolver counts ANSWERS,
            # not rows, and it deduplicates by `group_id` + `canonical_market_key`
            # (spec §2). MEASURED before adding this: on the esports hub only 7 of
            # 190 rows carried a canonical key and `group_id` was not in the payload
            # at all, so 190 rows resolved to 187 "answers" — the flagship
            # answers-not-rows case the spec cites did not collapse ANYTHING.
            #
            # `group_id` is what makes ten Polymarket sub-markets about one question
            # count as one question. It is already on the model, already indexed,
            # and already the feed's dedup key; it was simply never serialized here.
            "group_id": market.group_id,
            "section": section,
        }

        # Deduplicate by canonical key (keep highest-tier / most outcomes)
        ck = market.canonical_market_key
        if ck:
            if ck in seen_canonical:
                existing = seen_canonical[ck]
                if len(outcomes_data) > len(existing["top_outcomes"]):
                    # Remove old from its section
                    old_section = existing["section"]
                    sections[old_section] = [m for m in sections[old_section] if m.get("canonical_market_key") != ck]
                    seen_canonical[ck] = market_data
                else:
                    continue
            else:
                seen_canonical[ck] = market_data

        sections[section].append(market_data)

    # Sort within each section by market importance
    for section_name, items in sections.items():
        items.sort(key=lambda m: (
            -(m.get("market_tier") or 99),
            -(m.get("outcome_count") or 0),
        ))

    # Remove empty sections
    sections = {k: v for k, v in sections.items() if v}

    # ── Alex's 2026-08-11 amendment: the games rails ──
    #
    # "League pages include an UPCOMING GAMES rail and a RECENT RESULTS rail — event
    # cards, the product's richest and freshest content. No new pipeline; events
    # already exist." They are served from THIS route rather than fetched separately
    # by the page, because the tier is declared here (ruling 021) and a census that
    # counts content the page sourced elsewhere can silently diverge from what the
    # reader actually sees.
    #
    # `events` has no sport_key column, so the league scope is a join through
    # `sports` (memory: project_events_no_sport_key). Guarded like every optional
    # section on the team page: a failure here degrades the rails, never the page.
    upcoming_games: list[dict] = []
    recent_results: list[dict] = []
    more_games = False
    more_results = False
    try:
        _games_q = (
            select(Event)
            .join(Sport, Sport.id == Event.sport_id)
            .where(
                Sport.key == sport_key,
                Event.status.in_(["live", "scheduled"]),
                Event.commence_time >= now - timedelta(hours=2),
            )
            .order_by(
                case((Event.status == "live", 0), else_=1),
                Event.commence_time.asc(),
            )
            # +1 so the cap can be DECLARED rather than silently applied. A full
            # COUNT would be a second round trip to say the same thing.
            .limit(UPCOMING_GAMES_LIMIT + 1)
        )
        _results_q = (
            select(Event)
            .join(Sport, Sport.id == Event.sport_id)
            .where(
                Sport.key == sport_key,
                # 'closed' as well as 'completed' — #1204's lesson: a settled
                # doubleheader (and every source that closes rather than completes)
                # is orphaned from a recents rail that only looks for 'completed'.
                Event.status.in_(["completed", "closed"]),
                Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),
            )
            .order_by(Event.commence_time.desc())
            .limit(RESULTS_LIMIT + 1)
        )
        _g = await asyncio.wait_for(db.execute(_games_q), timeout=10)
        _grows = [_format_game_brief(e) for e in _g.scalars().all()]
        more_games = len(_grows) > UPCOMING_GAMES_LIMIT
        upcoming_games = _grows[:UPCOMING_GAMES_LIMIT]

        _r = await asyncio.wait_for(db.execute(_results_q), timeout=10)
        _rrows = [_format_game_brief(e) for e in _r.scalars().all()]
        more_results = len(_rrows) > RESULTS_LIMIT
        recent_results = _rrows[:RESULTS_LIMIT]
    except Exception:
        logger.exception("league page: games rails failed for %s", sport_key)

    # ── UX-P062 (#1743, epic #1741): the entity envelope (spec §7) ──
    #
    # Spec §2 / ruling 021: the TIER is a typed backend field. The moment web and
    # SwiftUI each count arrays to pick a layout, the same league renders as a map
    # on one and an answer on the other, and the parity bug is unfindable because
    # both clients are "correct". Counts come from the SHARED resolver and are never
    # reimplemented here — a second count is a second policy, and the histogram
    # would then predict a tier the page does not render.
    # The census is a SUPERSET of the rendered card sections, because two kinds of
    # content are rendered by something other than a card list (Alex's amendment):
    #   `championship` — rendered as the GRID, the page's centerpiece
    #   `games`        — rendered as the upcoming-games rail
    # Both are real content a reader sees, so both earn their place in the count.
    #
    # RECENT RESULTS are deliberately NOT a census section: settled content feeds
    # the RECORD, never the answer count (doctrine A4, which the kernel encodes —
    # settled rows resolve to zero answers, so a results "section" could never be
    # populated without changing the resolver). They arrive as `record_n`, which is
    # what the receipts strip is for (spec §5.3). Stated here because it is the one
    # clause of the amendment that does not resolve mechanically.
    census_sections = dict(sections)
    if championship_census:
        census_sections["championship"] = championship_census
    if upcoming_games:
        census_sections["games"] = [
            {
                "id": f"game:{g['id']}",
                # A game with no blended number is not an answer — it is a fixture.
                # Shaping it this way lets the ONE resolver make that call, instead
                # of this route inventing a second rule about what counts.
                "top_outcomes": [{"probability": g["home_win_probability"]}],
            }
            for g in upcoming_games
        ]

    tiering = resolve_entity_tier(
        census_sections,
        now=now,
        # A league in SPORT_HIERARCHY is a real entity; an unrecognised key is not a
        # page at all. That is the generation gate, and it is an IDENTITY question,
        # not a density one.
        entity_is_real=sport_key in _REGISTERED_SPORT_KEYS,
        # Settled games are the league's receipts. This is what makes a registered
        # league with zero live answers a legitimate T0 PAGE (a statement with a
        # record on it) rather than a generation-gate 404.
        record_n=len(recent_results),
        next_event_count=len(upcoming_games),
        season_known=False,
    )

    # Per-section total/shown/dropped. The key set is the UNION of what survived and
    # what was skipped on price: a section whose every row was skipped vanished from
    # `sections` entirely, and reporting nothing about it is precisely the silent
    # truncation clause 3 forbids.
    section_counts: dict[str, dict[str, int]] = {}
    for name in set(tiering["per_section"]) | set(resolved_skipped):
        s = tiering["per_section"].get(
            name, {"total": 0, "answers": 0, "unpriced": 0, "settled": 0}
        )
        skipped = resolved_skipped.get(name, 0)
        section_counts[name] = {
            # `total` is what we HAD before the price skip, so "showing X of Y" is
            # true about the league rather than true about the leftovers.
            "total": s["total"] + skipped,
            "shown": s["total"],
            "dropped": s["unpriced"] + skipped,
            "answers": s["answers"],
        }

    total_skipped = sum(resolved_skipped.values())
    pool_counts = dict(tiering["pool_counts"])
    pool_counts["dropped"] = pool_counts["dropped"] + total_skipped

    response = {
        "sport_key": sport_key,
        "sections": sections,
        "total_markets": sum(len(v) for v in sections.values()),
        # Alex's amendment. The cap is DECLARED, not silent: `has_more` says there
        # is more behind it (spec §4 — an uncounted cap reads as coverage).
        "upcoming_games": upcoming_games,
        "upcoming_games_has_more": more_games,
        "recent_results": recent_results,
        "recent_results_has_more": more_results,
        "record_n": len(recent_results),
        "tier": tiering["tier"],
        # Ruling 025's vocabulary, never live/stale_ok/unavailable (register E10).
        # A freshly built response with nothing AT ALL in it is EMPTY — a real
        # state, and a different one from the degraded reads stamped on the cache
        # and timeout paths, which is the whole point of declaring it. "Nothing"
        # has to include the games rails, or a league mid-season with a full
        # schedule and no futures would declare itself empty.
        "availability": (
            AVAILABILITY_FRESH
            if (sections or upcoming_games or recent_results)
            else AVAILABILITY_EMPTY
        ),
        "pool_counts": pool_counts,
        "section_counts": section_counts,
    }

    return response
