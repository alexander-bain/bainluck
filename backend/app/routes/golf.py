"""
Golf category landing page endpoint.

Aggregates futures market odds across Polymarket, Kalshi, and The Odds API for golf tournaments.
Groups by tournament, merges cross-source golfer odds, and computes biggest movers.
Enriches with PGA tour schedule from DataGolf for accurate current-event detection.
"""

import logging
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOddsSnapshot, Event, Sport
from app.services import get_db
from app.utils.odds_math import probability_to_american

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================================
# Market validation — filter out non-golf false positives from LLM
# ============================================================================

# Non-golf terms in market names that indicate LLM miscategorization.
# The LLM sometimes classifies esports "Masters" events, entertainment props,
# and other non-golf markets as golf.
_NON_GOLF_RE = re.compile(
    r"\b(?:"
    # Esports
    r"vct|valorant|league\s+of\s+legends|\blol\b|dota|counter[-\s]?strike|"
    r"\bcs2?\b|esports?|overwatch|call\s+of\s+duty|fortnite|apex\s+legends|"
    r"rocket\s+league|starcraft|hearthstone|"
    # Sports leagues (not golf)
    r"\bnba\b|\bnfl\b|\bnhl\b|\bmlb\b|\bwnba\b|\bmls\b|\bufc\b|\bmma\b|"
    r"\bepl\b|la\s+liga|serie\s+a|\bbundesliga\b|"
    r"super\s+bowl|world\s+series|stanley\s+cup|"
    # English football / EFL (prevents "EFL Championship" matching golf)
    r"\befl\b|english\s+football|football\s+league|"
    r"\bleague\s+(?:one|two)\b|championship\s+(?:relegation|promotion)|"
    r"\bfa\s+cup\b|\bcarabao\b|\bpremier\s+league\b|"
    r"\bligue\s+1\b|\beredivisie\b|\bscottish\b|"
    # Entertainment / media
    r"\boscar|emmy|grammy|golden\s+globe|tony\s+award|"
    r"netflix|hulu|disney\+|streaming|tv\s+show|television|"
    r"box\s+office|academy\s+award|"
    r"most[- ]watched|most[- ]streamed|"
    r"k-?pop|anime|manga|"
    r"movie|film\b|cinema|"
    r"reality\s+tv|talk\s+show|podcast|"
    r"album\s+of|concert|"
    r"motion\s+picture|producers?\s+guild|pga\s+award|"
    # Politics
    r"election|president(?:ial)?|senate|governor|congress|democrat|republican|"
    r"cabinet|supreme\s+court|"
    # Finance/crypto
    r"bitcoin|ethereum|crypto|stock\s+market|s&p|nasdaq|"
    # Weather
    r"temperature|weather|hurricane|tornado"
    r")\b",
    re.I,
)

# Positive golf signals — market names that indicate actual golf content.
# For Kalshi/Polymarket, passing the blocklist is necessary but not sufficient.
# The market name must also contain at least one golf-related term.
_GOLF_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"golf|golfer|pga|lpga|"
    r"masters|"
    r"open|"
    r"classic|invitational|"
    r"ryder|presidents?\s+cup|"
    r"major|hole[-\s]in[-\s]one|"
    r"wgc|"
    r"liv\s+golf|korn\s+ferry|"
    r"dp\s+world|sunshine\s+tour|"
    r"asian\s+tour|european\s+tour|"
    r"top\s+\d+\s+finish|make\s+the?\s+cut|"
    r"birdie|bogey|eagle|par\s+\d|under\s+par"
    r")\b",
    re.I,
)


# Kalshi external_id patterns that are NOT golf despite LLM classification.
# These tickers indicate tennis or cross-sport markets.
_NON_GOLF_TICKER_RE = re.compile(
    r"kxgrandslam|kxgolftennis",
    re.I,
)


def _is_golf_market(market) -> bool:
    """Validate that a market is actually golf-related, not a false positive."""
    source = market.source or ""
    external_id = (market.external_id or "").lower()
    name = market.name or ""

    # DataGolf markets: always golf
    if source == "datagolf":
        return True

    # Odds API markets: trust the sport key prefix
    if source == "odds_api":
        return external_id.startswith("golf_")

    # Reject markets with non-golf Kalshi tickers (tennis grand slams, cross-sport)
    if _NON_GOLF_TICKER_RE.search(external_id):
        return False

    # For Kalshi/Polymarket: reject markets with clear non-golf signals
    if _NON_GOLF_RE.search(name):
        return False

    # Require at least one positive golf signal in the market name.
    # This catches entertainment markets that the LLM miscategorized as golf
    # (e.g., movie/show names) which don't trigger the blocklist but also
    # have no golf-related terms.
    if not _GOLF_SIGNAL_RE.search(name):
        logger.debug("Golf filter: rejected '%s' (source=%s) — no golf signal", name, source)
        return False

    return True


# ============================================================================
# Tournament classification
# ============================================================================

# Patterns that look like "Open Championship" but are NOT The Open Championship.
# Must be checked before _TOURNAMENT_PATTERNS to prevent false classification.
_NOT_THE_OPEN_RE = re.compile(
    r"south\s+african\s+open|joburg\s+open|kenya\s+open",
    re.I,
)

# Order matters: more specific patterns first
_TOURNAMENT_PATTERNS = [
    (re.compile(r"(?:the\s+)?masters(?:\s+(?:tournament|golf|winner|champion))?(?!\s+(?:tour|bangkok|shanghai|madrid|tokyo|reykjavik|copenhagen))", re.I), "masters"),
    (re.compile(r"pga\s+championship", re.I), "pga_championship"),
    (re.compile(r"us\s+open|u\.s\.\s+open", re.I), "us_open"),
    (re.compile(r"the\s+open\s+championship|(?:the\s+)?open\s+championship|british\s+open|the\s+open\b", re.I), "the_open"),
    (re.compile(r"players\s+championship", re.I), "players"),
    (re.compile(r"ryder\s+cup", re.I), "ryder_cup"),
    (re.compile(r"presidents?\s+cup", re.I), "presidents_cup"),
    (re.compile(r"liv\s+golf", re.I), "liv"),
    (re.compile(r"tomorrow'?s?\s+golf\s+league|tgl\s+champion", re.I), "tgl"),
]

TOURNAMENT_DISPLAY_NAMES = {
    "masters": "The Masters",
    "pga_championship": "PGA Championship",
    "us_open": "U.S. Open",
    "the_open": "The Open Championship",
    "players": "The Players Championship",
    "ryder_cup": "Ryder Cup",
    "presidents_cup": "Presidents Cup",
    "liv": "LIV Golf",
    "tgl": "TGL",
    "other": "Other Tournaments",
}

MAJOR_TOURNAMENTS = {"masters", "pga_championship", "us_open", "the_open"}

# PGA Tour Signature Events — elevated purse/field, top-tier regular season events
_SIGNATURE_EVENTS = {
    "arnold_palmer_invitational",
    "the_genesis_invitational",
    "genesis_invitational",
    "the_players_championship",
    "memorial_tournament",
    "the_sentry",
    "at_t_pebble_beach",
    "at_t_pebble_beach_pro_am",
    "rbc_heritage",
    "wells_fargo_championship",
    "travelers_championship",
    "fedex_st_jude_championship",
}

# Sponsor suffix pattern — strip "Presented By X", "Sponsored By X", etc. before slugifying
_SPONSOR_SUFFIX_RE = re.compile(
    r"\s+(?:presented|sponsored|hosted|powered)\s+by\s+.*$",
    re.I,
)


def _clean_slug(name: str) -> str:
    """Generate a clean URL slug from a tournament name, stripping sponsor suffixes."""
    cleaned = _SPONSOR_SUFFIX_RE.sub("", name)
    return re.sub(r"[^a-z0-9]+", "-", cleaned.lower()).strip("-")

TOURNAMENT_ORDER = [
    "masters", "pga_championship", "us_open", "the_open",
    "players", "ryder_cup", "presidents_cup", "liv", "tgl", "other",
]

# Max golfers to return per tournament
_MAX_GOLFERS = 15

# Outcomes that are not individual golfer names — skip these
_PROP_OUTCOME_RE = re.compile(
    r"(?:"
    r"\d\+\s|"                   # "1+ golf major..."
    r"\bany\s+golfer\b|"         # "Any golfer"
    r"\bcombined\b|"             # "...combined"
    r"\band\b.*\bcombined\b|"    # "X, Y, and Z combined"
    r"^yes$|^no$"                # Binary yes/no outcomes
    r")",
    re.I,
)

# Markets that are NOT outright winner markets — exclude from headline probability.
# These include field/participation markets, placement, and prop bets.
_NON_WINNER_MARKET_RE = re.compile(
    r"(?:"
    r"\bcompete\s+in\b|"         # "Golfers to compete in The Masters"
    r"\bplay\s+in\b|"            # "Will Tiger Woods play in..."
    r"\bparticipat|"             # "participate in"
    r"\bmake\s+(?:the\s+)?cut\b|" # "Make Cut" / "Make the Cut" placement markets
    r"\bmade\s+(?:the\s+)?cut\b|" # "Made Cut" / "Made the Cut" (past tense)
    r"\bTop\s+\d+\b|"            # "Top 5/10/20 Finishers"
    r"\bRound\s+\d+\s+Leader\b|" # "Round 1 Leader"
    r"\bfirst\s+round\s+leader\b|"
    r"\b(?:miss|made)\s+the\s+cut\b|"
    r"\bfield\s+size\b|"         # "Field size" props
    r"\bnumber\s+of\b|"          # "Number of birdies" etc.
    r"\bhole[- ]in[- ]one\b|"    # Hole-in-one props
    r"\bplayoff\b|"              # "Will there be a playoff"
    r"\bwill\b.*\bplay\b|"       # "Will X play in..."
    r"\bcaptain\b"               # "U.S. Team Captain at 2027 Ryder Cup"
    r")",
    re.I,
)

# Women's / LPGA detection
_WOMENS_RE = re.compile(r"\b(?:lpga|women'?s?|ladies)\b", re.I)

# ============================================================================
# Tour classification — classify each tournament by tour
# ============================================================================

_TOUR_CLASSIFICATION_PATTERNS = [
    (re.compile(r"\b(?:dp\s+world|european\s+tour|rolex\s+series)\b", re.I), "dp_world"),
    (re.compile(r"\b(?:lpga|women'?s?\s+(?:open|championship|tour))\b", re.I), "lpga"),
    (re.compile(r"\bliv\s+golf\b", re.I), "liv"),
    (re.compile(r"\b(?:korn\s+ferry|nationwide)\b", re.I), "korn_ferry"),
    (re.compile(r"\b(?:sunshine\s+tour)\b", re.I), "sunshine"),
    (re.compile(r"\b(?:asian\s+tour)\b", re.I), "asian"),
    (re.compile(r"\btgl\b|tomorrow'?s?\s+golf", re.I), "tgl"),
]

TOUR_DISPLAY_NAMES = {
    "pga": "PGA Tour",
    "dp_world": "DP World Tour",
    "lpga": "LPGA Tour",
    "liv": "LIV Golf",
    "korn_ferry": "Korn Ferry Tour",
    "sunshine": "Sunshine Tour",
    "asian": "Asian Tour",
    "tgl": "TGL",
    "major": "Major",
}


def _classify_tour(market_name: str, tournament_key: str, is_major: bool, is_womens: bool) -> str:
    """Classify a tournament into a tour. Returns tour key."""
    if is_major:
        return "major"
    if is_womens:
        return "lpga"
    for pattern, tour in _TOUR_CLASSIFICATION_PATTERNS:
        if pattern.search(market_name):
            return tour
    # Default to PGA Tour for non-major, non-women's, non-pattern-matched
    return "pga"

# ============================================================================
# Tour event extraction — sub-group "other" into named tour events
# ============================================================================

# Known PGA Tour event name patterns to extract from market names.
# These appear in Kalshi/Polymarket market names like:
#   "Cognizant Classic in The Palm Beaches Winner?"
#   "PGA Tour: Genesis Invitational Top 5"
_TOUR_EVENT_RE = re.compile(
    r"(?:PGA\s+Tour:\s*)?"  # Optional "PGA Tour:" prefix (Polymarket)
    r"((?:"
    # Named tournaments — add new ones as they appear
    r"Cognizant\s+Classic(?:\s+in\s+The\s+Palm\s+Beaches)?"
    r"|Genesis\s+Invitational"
    r"|Arnold\s+Palmer\s+Invitational"
    r"|Honda\s+Classic"
    r"|Valspar\s+Championship"
    r"|WGC[- ].*?(?=\s+(?:Winner|Top|End|Round|Make|Playoff))"
    r"|(?:Investec\s+)?South\s+African\s+Open(?:\s+Championship)?"
    r"|Joburg\s+Open"
    r"|Kenya\s+Open"
    r"|Honda\s+LPGA\s+Thailand"
    r"|HSBC\s+Women'?s?\s+World\s+Championship"
    r"|(?:DP\s+World\s+Tour|European\s+Tour|Sunshine\s+Tour|Asian\s+Tour)[:\s]+\w[\w\s]*?(?=\s+(?:Winner|Top|End|Round))"
    r"))",
    re.I,
)

# Display names for dynamically-extracted tour events.
# Keys are the normalized form (lowered, non-alpha replaced with underscores).
_TOUR_EVENT_DISPLAY_NAMES = {
    "cognizant_classic_in_the_palm_beaches": "Cognizant Classic",
    "cognizant_classic": "Cognizant Classic",
    "investec_south_african_open_championship": "South African Open",
    "investec_south_african_open": "South African Open",
    "south_african_open_championship": "South African Open",
    "south_african_open": "South African Open",
    "honda_lpga_thailand": "Honda LPGA Thailand",
    "hsbc_women_s_world_championship": "HSBC Women's World Championship",
    "hsbc_womens_world_championship": "HSBC Women's World Championship",
}


def _extract_tour_event(market_name: str) -> str | None:
    """Extract a tour event name from a market name, or None if not a tour event."""
    m = _TOUR_EVENT_RE.search(market_name)
    if m:
        name = m.group(1).strip()
        # Clean up trailing "in The Palm Beaches" etc. for display key
        return name
    return None


# ============================================================================
# DataGolf PGA schedule cache
# ============================================================================

_golf_schedule_cache: dict = {"data": None, "ts": 0}
_GOLF_SCHEDULE_TTL = 3600  # 1 hour


async def _get_golf_schedule() -> list[dict]:
    """Fetch PGA tour schedule from DataGolf with 1-hour in-process cache.

    Returns a list of tournament dicts with name, start/end dates, venue, status.
    Returns empty list if DataGolf is unavailable.
    """
    now_ts = time.time()
    if _golf_schedule_cache["data"] is not None and (now_ts - _golf_schedule_cache["ts"]) < _GOLF_SCHEDULE_TTL:
        return _golf_schedule_cache["data"]

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        tournaments = await service.get_schedule(tour="pga")

        result = []
        for t in tournaments:
            if not t.event_name:
                continue

            # Generate a stable key from the event name, stripping sponsor suffixes
            # so "Arnold Palmer Invitational Presented By Mastercard" -> "arnold_palmer_invitational"
            # This ensures keys match _SIGNATURE_EVENTS entries.
            clean_name = _SPONSOR_SUFFIX_RE.sub("", t.event_name)
            key = re.sub(r"[^a-z0-9]+", "_", clean_name.lower()).strip("_")

            result.append({
                "name": t.event_name,
                "key": key,
                "start_date": f"{t.start_date}T00:00:00+00:00" if t.start_date else None,
                "end_date": f"{t.end_date}T00:00:00+00:00" if t.end_date else None,
                "venue": t.course or "",
                "location": t.location or "",
                "status": t.status or "",
                "round": str(t.current_round) if t.current_round else "",
            })

        _golf_schedule_cache["data"] = result
        _golf_schedule_cache["ts"] = now_ts
        logger.info("DataGolf PGA schedule: loaded %d tournaments", len(result))
        return result

    except Exception as e:
        logger.warning("Failed to fetch golf schedule from DataGolf: %s", e)
        return []
    finally:
        await service.close()


# Characters that NFD decomposition doesn't handle (e.g., ø, đ, ł)
_EXTRA_TRANSLITERATIONS = str.maketrans({
    "ø": "o", "Ø": "O",
    "đ": "d", "Đ": "D",
    "ł": "l", "Ł": "L",
    "æ": "ae", "Æ": "AE",
})


def _strip_diacritics(s: str) -> str:
    """Remove accent marks and transliterate special letters.

    Handles both NFD-decomposable marks (ü→u, é→e, å→a) and
    non-decomposable letters (ø→o, đ→d, ł→l) that appear in
    Nordic and Eastern European golfer names.
    """
    s = s.translate(_EXTRA_TRANSLITERATIONS)
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


# Stopwords to strip when matching tournament names
_TOURN_STOPWORDS = {"the", "a", "at", "in", "of", "presented", "by", "pga", "tour"}


def _match_market_to_schedule(market_name: str, schedule: list[dict]) -> str | None:
    """Fuzzy-match a futures market name against DataGolf tournament names.

    Returns the DataGolf schedule key if matched, None otherwise.
    """
    if not schedule:
        return None

    # Clean market name: strip "PGA Tour:" prefix and common suffixes
    clean_market = re.sub(r"^PGA\s+Tour:\s*", "", market_name, flags=re.I)
    clean_market = re.sub(r"\s+(Winner|Top\s+\d+|End\s+of|Round\s+\d+|Make\s+Cut|Made\s+Cut)\b.*", "", clean_market, flags=re.I)
    clean_market = re.sub(r"\s*\?\s*$", "", clean_market)

    market_words = {w.lower() for w in re.findall(r"[a-z]{3,}", clean_market, re.I)} - _TOURN_STOPWORDS

    if len(market_words) < 2:
        return None

    best_match = None
    best_overlap = 0

    for entry in schedule:
        event_name = entry.get("name", "")
        # Strip "presented by X", "at X" suffixes for matching
        clean_event = re.sub(r"\s+(?:presented\s+by|at)\s+.*$", "", event_name, flags=re.I)
        event_words = {w.lower() for w in re.findall(r"[a-z]{3,}", clean_event, re.I)} - _TOURN_STOPWORDS

        if len(event_words) < 2:
            continue

        overlap = len(market_words & event_words)
        if overlap >= 2 and overlap > best_overlap:
            best_overlap = overlap
            best_match = entry.get("key")

    return best_match


def _normalize_golfer_name(name: str) -> str:
    """Normalize a golfer name for display.

    Handles DataGolf 'Last, First' format, Polymarket quoted names,
    and common prefix/suffix noise from prediction market outcomes.
    """
    name = name.strip()
    name = re.sub(r"^(Yes|No)\s*[-:]\s*", "", name, flags=re.I)
    # Strip wrapping quotes (Polymarket NegRisk format)
    name = re.sub(r'^"(.*)"$', r"\1", name)
    # Convert "Last, First" to "First Last" (DataGolf format)
    # Unicode \w handles accented capitals (Højgaard, Müller, Skarsgård)
    comma_match = re.match(r"^(\w[\w'-]+),\s+(\w[\w'-]+.*)$", name, flags=re.UNICODE)
    if comma_match:
        name = f"{comma_match.group(2)} {comma_match.group(1)}"
    return name


# Common first-name aliases for golfer dedup across sources.
# Maps short/informal name → canonical form used in match keys.
_NAME_ALIASES: dict[str, str] = {
    "matt": "matthew",
    "mike": "michael",
    "alex": "alexander",
    "dan": "daniel",
    "bob": "robert",
    "rob": "robert",
    "will": "william",
    "bill": "william",
    "billy": "william",
    "chris": "christopher",
    "dave": "david",
    "tony": "anthony",
    "tom": "thomas",
    "tommy": "thomas",
    "rick": "richard",
    "dick": "richard",
    "nick": "nicholas",
    "ben": "benjamin",
    "sam": "samuel",
    "joe": "joseph",
    "jim": "james",
    "jimmy": "james",
    "jake": "jacob",
    "ed": "edward",
    "pat": "patrick",
    "steve": "steven",
    "charlie": "charles",
    "max": "maximilian",
    "cam": "cameron",
    "si": "simon",
    "sepp": "josef",
}


def _match_key(name: str) -> str:
    """
    Create a matching key from a golfer name for cross-source dedup.

    Handles name variations across DataGolf, Polymarket, Kalshi, and Odds API:
    - DataGolf: "Scheffler, Scottie" → "scottie scheffler"
    - Polymarket: "Scottie Scheffler" → "scottie scheffler"
    - Kalshi: "Yes: Scottie Scheffler" → "scottie scheffler"
    - Odds API: "S. Scheffler" → "s scheffler"
    - Diacritics: "Skarsgård" → "skarsgard"
    - Aliases: "Matt Fitzpatrick" → "matthew fitzpatrick"
    """
    clean = _normalize_golfer_name(name)
    clean = re.split(r"\s+[-\u2013]\s+|\s+for\s+", clean, maxsplit=1)[0]
    clean = _strip_diacritics(clean)
    clean = clean.lower()
    clean = re.sub(r"^the\s+", "", clean)
    clean = clean.split(":")[0].strip()
    # Remove Jr./Sr./III suffixes for matching
    clean = re.sub(r"\b(?:jr|sr|iii|ii|iv)\.?\b", "", clean)
    clean = re.sub(r"[^a-z0-9\s]", "", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    # Expand first-name aliases for cross-source dedup
    parts = clean.split()
    if parts and parts[0] in _NAME_ALIASES:
        parts[0] = _NAME_ALIASES[parts[0]]
        clean = " ".join(parts)
    return clean


def _normalize_tournament(market_name: str, schedule: list[dict] | None = None) -> str:
    """Extract tournament key from a market name. Returns 'other' if no match."""
    # Priority 1: Hardcoded major/special patterns
    for pattern, key in _TOURNAMENT_PATTERNS:
        if pattern.search(market_name):
            if key == "the_open" and _NOT_THE_OPEN_RE.search(market_name):
                continue
            return key

    # Priority 2: DataGolf schedule fuzzy match
    if schedule:
        schedule_key = _match_market_to_schedule(market_name, schedule)
        if schedule_key:
            # Guard: don't let South African/Joburg/Kenya Open
            # fuzzy-match The Open Championship schedule entry
            if "open" in schedule_key and _NOT_THE_OPEN_RE.search(market_name):
                pass  # Skip — fall through to tour event regex
            elif schedule_key == "the_open_championship":
                return "the_open"  # Canonical key for The Open
            else:
                return schedule_key

    # Priority 3: Hardcoded tour event regex
    tour_event = _extract_tour_event(market_name)
    if tour_event:
        key = re.sub(r"[^a-z0-9]+", "_", tour_event.lower()).strip("_")
        return key

    # Priority 4: Generic tournament name extraction — strip market type
    # suffixes (" - Winner", " - Top 5 Finish", etc.) and slugify.
    # Handles DataGolf markets ("LECOM Suncoast Classic - Winner") and other
    # well-structured names that don't match hardcoded patterns.
    clean = re.sub(
        r"\s*[-–]\s*(?:Winner|Top\s+\d+(?:\s+Finish)?|Make\s+(?:the\s+)?Cut|Round\s+\d+\s+Leader)\s*$",
        "", market_name, flags=re.I,
    )
    # Also strip "Winner" / "Champion" without dash separator
    clean = re.sub(r"\s+(?:Winner|Champion)\s*\??\s*$", "", clean, flags=re.I)
    # Strip common prefixes
    clean = re.sub(r"^(?:PGA\s+Tour|DP\s+World\s+Tour|European\s+Tour):\s*", "", clean, flags=re.I)
    # Strip trailing "?"
    clean = re.sub(r"\s*\?\s*$", "", clean)
    key = re.sub(r"[^a-z0-9]+", "_", clean.lower()).strip("_")
    if key and len(key) >= 3:
        return key

    return "other"


@router.get("")
async def get_golf(
    db: AsyncSession = Depends(get_db),
):
    """
    Get golf tournament futures with aggregated odds across sources.

    Returns tournaments ordered by importance (Majors first), with golfers
    merged across Polymarket, Kalshi, and Odds API sources.
    """
    now = datetime.now(timezone.utc)

    # Query golf-related futures markets using both sport key and LLM category
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                # Odds API markets with golf_ sport key (authoritative)
                FuturesMarket.external_id.ilike("golf_%"),
                # LLM-classified golf markets (may have false positives)
                FuturesMarket.llm_sport_category == "golf",
            ),
        )
    )

    result = await db.execute(query)
    markets = result.scalars().unique().all()

    # Filter out game-level markets (e.g., "Player A vs Player B" matchups)
    markets = [m for m in markets if " vs " not in m.name.lower() and " vs." not in m.name.lower()]

    # Filter out non-golf false positives (esports, entertainment, politics, etc.)
    markets = [m for m in markets if _is_golf_market(m)]

    logger.info("Golf endpoint: %d markets after filtering", len(markets))

    # ========================================================================
    # Compute 24h movement from futures_odds_snapshots
    # ========================================================================
    # Collect all outcome IDs to query snapshots in one batch
    all_outcome_ids = []
    for market in markets:
        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                all_outcome_ids.append(outcome.id)

    # Get probability from ~24h ago for each outcome (single batch query)
    prob_24h_ago: dict[int, float] = {}
    if all_outcome_ids:
        # Use row_number to get the most recent snapshot in the 23-25h window
        snapshot_subq = (
            select(
                FuturesOddsSnapshot.outcome_id,
                FuturesOddsSnapshot.probability,
                sqlfunc.row_number().over(
                    partition_by=FuturesOddsSnapshot.outcome_id,
                    order_by=FuturesOddsSnapshot.captured_at.desc()
                ).label("rn")
            )
            .where(
                FuturesOddsSnapshot.outcome_id.in_(all_outcome_ids),
                FuturesOddsSnapshot.captured_at.between(
                    now - timedelta(hours=25),
                    now - timedelta(hours=23),
                ),
            )
            .subquery()
        )

        snap_result = await db.execute(
            select(snapshot_subq.c.outcome_id, snapshot_subq.c.probability)
            .where(snapshot_subq.c.rn == 1)
        )
        prob_24h_ago = {row.outcome_id: float(row.probability) for row in snap_result}

    logger.info("Golf endpoint: found 24h-ago snapshots for %d/%d outcomes",
                len(prob_24h_ago), len(all_outcome_ids))

    # ========================================================================
    # Fetch DataGolf schedule for date enrichment + tournament matching
    # ========================================================================
    schedule = await _get_golf_schedule()
    schedule_by_key: dict[str, dict] = {}
    for s_event in schedule:
        key = s_event.get("key", "other")
        if key != "other" and key not in schedule_by_key:
            schedule_by_key[key] = s_event

    # ========================================================================
    # Group markets by tournament and aggregate golfer odds
    # ========================================================================
    tournament_markets: dict[str, list] = defaultdict(list)

    for market in markets:
        tournament_key = _normalize_tournament(market.name, schedule)
        if tournament_key == "other":
            # Don't merge unrelated markets — give each its own entry
            per_market_key = f"other_{market.id}"
            tournament_markets[per_market_key].append(market)
        else:
            tournament_markets[tournament_key].append(market)

    # Build tournament response with cross-source aggregation
    tournaments = []

    for tourn_key, tourn_markets in tournament_markets.items():
        golfer_data: dict[str, dict] = {}  # match_key -> aggregated data
        prop_markets_list: list[dict] = []  # Non-winner markets shown separately

        market_ids = []
        market_sources = []
        earliest_commence = None
        latest_resolution = None

        for market in tourn_markets:
            market_ids.append(market.id)
            market_sources.append(market.source or "unknown")
            source = market.source or "unknown"
            # DataGolf provides model predictions, not market prices — label accordingly
            source_label = "datagolf_model" if source == "datagolf" else source

            # Track tournament timing
            if market.commence_time:
                if earliest_commence is None or market.commence_time < earliest_commence:
                    earliest_commence = market.commence_time
            if market.resolution_date:
                if latest_resolution is None or market.resolution_date > latest_resolution:
                    latest_resolution = market.resolution_date

            # Non-winner markets (captain, participation, placement, etc.)
            # are shown separately with proper labels — not mixed into winner odds.
            if _NON_WINNER_MARKET_RE.search(market.name):
                prop_outcomes = []
                for outcome in market.outcomes:
                    if outcome.current_probability is None:
                        continue
                    p = float(outcome.current_probability)
                    if source == "kalshi" and p == 0.5:
                        continue
                    raw = outcome.name.strip()
                    if raw.lower() in ("tie", "field", "other", "the field"):
                        continue
                    prop_outcomes.append({
                        "name": _normalize_golfer_name(raw),
                        "probability": round(p, 3),
                    })
                if prop_outcomes:
                    prop_outcomes.sort(key=lambda x: x["probability"], reverse=True)
                    prop_markets_list.append({
                        "name": market.name,
                        "source": source_label,
                        "outcomes": prop_outcomes[:5],
                    })
                continue

            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue

                prob = float(outcome.current_probability)

                # Skip Kalshi entries at exactly 0.5 — illiquid binary markets
                if source == "kalshi" and prob == 0.5:
                    continue

                # Skip generic outcomes
                raw_name = outcome.name.strip()
                if raw_name.lower() in ("tie", "field", "other", "the field"):
                    continue

                # Skip prop/meta outcomes that aren't individual golfer names
                if _PROP_OUTCOME_RE.search(raw_name):
                    continue

                display_name = _normalize_golfer_name(raw_name)
                key = _match_key(raw_name)

                if not key:
                    continue

                if key not in golfer_data:
                    golfer_data[key] = {
                        "name": display_name,
                        "sources": {},
                        "probabilities": [],
                        "movement_24h": None,
                        "opening_probability": None,
                    }

                golfer_data[key]["sources"][source_label] = round(prob, 3)
                golfer_data[key]["probabilities"].append(prob)

                # Compute 24h movement from snapshots
                if outcome.id in prob_24h_ago:
                    delta = prob - prob_24h_ago[outcome.id]
                    if abs(delta) >= 0.001:  # Skip noise
                        existing = golfer_data[key]["movement_24h"]
                        if existing is None or abs(delta) > abs(existing):
                            golfer_data[key]["movement_24h"] = round(delta, 4)

                # Fall back to outcome field if snapshot not available
                if golfer_data[key]["movement_24h"] is None and outcome.probability_change_24h is not None:
                    change = float(outcome.probability_change_24h)
                    if abs(change) >= 0.001:
                        golfer_data[key]["movement_24h"] = round(change, 4)

                # Track opening probability
                if outcome.opening_probability is not None and golfer_data[key]["opening_probability"] is None:
                    golfer_data[key]["opening_probability"] = round(float(outcome.opening_probability), 3)

        # Filter to invitees only — when DataGolf field data exists for a
        # tournament, only include golfers who appear in the DataGolf field.
        # Prevents non-invitees from sportsbooks polluting the landing page
        # (e.g., Gary Woodland showing 8.7% to "win Masters" because sportsbooks
        # still have odds on him even though he's not invited).
        has_datagolf = "datagolf" in market_sources
        if has_datagolf:
            datagolf_keys = {k for k, v in golfer_data.items() if "datagolf_model" in v["sources"]}
            if datagolf_keys:  # Only filter if DataGolf actually has outcomes
                filtered_count = len(golfer_data) - len(datagolf_keys)
                if filtered_count > 0:
                    logger.info("Golf invitee filter: removed %d non-field golfers from %s", filtered_count, tourn_key)
                golfer_data = {k: v for k, v in golfer_data.items() if k in datagolf_keys}

        # Compute average probability
        golfers = []
        for data in golfer_data.values():
            avg_prob = sum(data["probabilities"]) / len(data["probabilities"])
            golfers.append({
                "name": data["name"],
                "probability": avg_prob,
                "movement_24h": data["movement_24h"],
                "sources": data["sources"],
                "opening_probability": data["opening_probability"],
            })

        # Sort by probability descending
        golfers.sort(key=lambda g: g["probability"], reverse=True)

        # Keep full list for detail pages, cap for landing page cards
        all_golfers = golfers

        # Round probabilities (no renormalization — raw source averages are
        # already meaningful and renormalizing across 144 golfers dilutes
        # the top contenders to unrealistically low values)
        for g in all_golfers:
            g["probability"] = round(g["probability"], 3)
            g["american_odds"] = probability_to_american(g["probability"])

        # Assign ranks (full list)
        for i, g in enumerate(all_golfers):
            g["rank"] = i + 1

        # Landing page cards use the capped list
        golfers = all_golfers[:_MAX_GOLFERS]

        order_idx = TOURNAMENT_ORDER.index(tourn_key) if tourn_key in TOURNAMENT_ORDER else 50
        display_name = TOURNAMENT_DISPLAY_NAMES.get(
            tourn_key,
            _TOUR_EVENT_DISPLAY_NAMES.get(tourn_key, tourn_key.replace("_", " ").title()),
        )
        is_tour_event = tourn_key not in TOURNAMENT_ORDER and not tourn_key.startswith("other_") and tourn_key != "other"

        # Per-market "other" entries: use market name as display name, group with Other
        if tourn_key.startswith("other_"):
            display_name = tourn_markets[0].name if tourn_markets else "Other"
            # Clean up common suffixes from market names for display
            display_name = re.sub(r"\s*\?\s*$", "", display_name)  # trailing "?"
            order_idx = TOURNAMENT_ORDER.index("other") if "other" in TOURNAMENT_ORDER else 99

        # For dynamic tour events, sort by resolution date (nearest first)
        if is_tour_event and latest_resolution:
            # Use resolution date as tiebreaker within the tour events band (50-98)
            order_idx = 50

        # Collect deduplicated market names for context labels
        market_names = sorted({m.name for m in tourn_markets})

        # Detect women's / LPGA tournaments
        is_womens = (
            bool(_WOMENS_RE.search(display_name))
            or any(_WOMENS_RE.search(m.name) for m in tourn_markets)
        )

        # Classify tour
        tour_name_for_classify = display_name
        if tourn_markets:
            tour_name_for_classify = tourn_markets[0].name
        tour = _classify_tour(
            tour_name_for_classify, tourn_key,
            tourn_key in MAJOR_TOURNAMENTS, is_womens,
        )

        tournaments.append({
            "key": tourn_key,
            "name": display_name,
            "is_major": tourn_key in MAJOR_TOURNAMENTS,
            "is_tour_event": is_tour_event,
            "is_womens": is_womens,
            "tour": tour,
            "tour_label": TOUR_DISPLAY_NAMES.get(tour, tour),
            "order": order_idx,
            "sort_date": latest_resolution.isoformat() if is_tour_event and latest_resolution else None,
            "commence_time": earliest_commence.isoformat() if earliest_commence else None,
            "resolution_date": latest_resolution.isoformat() if latest_resolution else None,
            "market_ids": market_ids,
            "market_sources": market_sources,
            "market_names": market_names,
            "golfers": golfers,
            "prop_markets": prop_markets_list,
            "_all_golfers": all_golfers,  # Full list for detail endpoint
        })

    # Sort tournaments by order, then by resolution date for tour events
    tournaments.sort(key=lambda t: (t["order"], t.get("sort_date") or "9999"))
    # Remove internal sort fields from response
    for t in tournaments:
        del t["order"]
        t.pop("sort_date", None)

    # ========================================================================
    # Enrich tournaments with DataGolf schedule data
    # ========================================================================
    # Map tournament keys (from _normalize_tournament) to schedule keys (from DataGolf).
    # e.g., "masters" → "masters_tournament", "us_open" → "u_s_open", etc.
    _TOURN_TO_SCHED_KEY = {
        "masters": "masters_tournament",
        "us_open": "u_s_open",
        "the_open": "the_open_championship",
        "players": "the_players_championship",
    }
    for t in tournaments:
        # Add slug for tournament detail page URLs
        t["slug"] = _clean_slug(t["name"])

        sched = schedule_by_key.get(t["key"]) or schedule_by_key.get(_TOURN_TO_SCHED_KEY.get(t["key"], ""))
        if sched:
            t["venue"] = sched.get("venue") or t.get("venue") or None
            t["location"] = sched.get("location") or None
            t["schedule_status"] = sched.get("status") or None
            if sched.get("start_date"):
                t["start_date"] = sched["start_date"]
            if sched.get("end_date"):
                t["end_date"] = sched["end_date"]

    # ========================================================================
    # Filter out completed tournaments (end_date in the past, >1 day buffer)
    # ========================================================================
    now_date = now.date()
    filtered_tournaments = []
    for t in tournaments:
        end_date_str = t.get("end_date")
        if end_date_str:
            try:
                end_dt = datetime.fromisoformat(end_date_str).date()
                if end_dt < now_date - timedelta(days=1):
                    logger.debug("Golf: filtering completed tournament '%s' (ended %s)", t["name"], end_dt)
                    continue
            except (ValueError, TypeError):
                pass
        filtered_tournaments.append(t)
    tournaments = filtered_tournaments

    # ========================================================================
    # Biggest movers — top 5 golfers across all tournaments by |movement_24h|
    # ========================================================================
    all_movers = []
    for tourn in tournaments:
        for g in tourn["golfers"]:
            if g["movement_24h"] is not None and abs(g["movement_24h"]) >= 0.005:
                all_movers.append({
                    "name": g["name"],
                    "tournament_key": tourn["key"],
                    "tournament_name": tourn["name"],
                    "movement_24h": g["movement_24h"],
                    "probability": g["probability"],
                })
    all_movers.sort(key=lambda m: abs(m["movement_24h"]), reverse=True)
    biggest_movers = all_movers[:5]

    # ========================================================================
    # Golf events — live + upcoming from events table
    # ========================================================================
    events_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.ilike("golf_%"),
            or_(
                # Currently live events
                Event.status == "live",
                # Upcoming events in next 30 days
                Event.commence_time.between(now, now + timedelta(days=30)),
                # Recently started (last 6h, may not be marked 'live' yet)
                Event.commence_time.between(now - timedelta(hours=6), now),
            ),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    events_result = await db.execute(events_query)
    upcoming_events_rows = events_result.scalars().all()

    upcoming_events = [
        {
            "id": e.id,
            "name": f"{e.home_team_name} vs {e.away_team_name}" if e.away_team_name else e.home_team_name,
            "commence_time": e.commence_time.isoformat() if e.commence_time else None,
            "status": e.status,
        }
        for e in upcoming_events_rows
    ]

    # ========================================================================
    # Current tour event — smart detection using DataGolf dates + fallback
    # ========================================================================
    current_event = _find_current_event(tournaments, schedule_by_key, now)

    return {
        "tournaments": tournaments,
        "biggest_movers": biggest_movers,
        "upcoming_events": upcoming_events,
        "current_event": current_event,
        "total_tournaments": len(tournaments),
        "total_golfers": sum(len(t["golfers"]) for t in tournaments),
        "pga_schedule": schedule if schedule else None,
    }


def _tournament_importance(key: str) -> int:
    """Return importance tier for a tournament key. Higher = more important."""
    if key in MAJOR_TOURNAMENTS:
        return 3
    if key in _SIGNATURE_EVENTS:
        return 2
    # Safety net: strip sponsor suffixes that may remain in the key
    # e.g. "arnold_palmer_invitational_presented_by_mastercard" -> check without suffix
    clean_key = re.sub(r"_(?:presented|sponsored|hosted|powered)_by_.*$", "", key)
    if clean_key != key and clean_key in _SIGNATURE_EVENTS:
        return 2
    return 1


def _find_current_event(
    tournaments: list[dict],
    schedule_by_key: dict[str, dict],
    now: datetime,
) -> dict | None:
    """Find the current tour event using DataGolf dates with fallback heuristics.

    Priority order:
    1. DataGolf schedule: event whose start_date <= now <= end_date (prefer most important)
    2. DataGolf schedule: nearest upcoming event (start_date > now, within 7 days, prefer most important)
    3. Fallback: tour event closest to now, weighted by importance + activity
    """
    tour_events = [t for t in tournaments if t.get("is_tour_event")]
    if not tour_events:
        return None

    now_str = now.isoformat()

    # Phase 1: Use DataGolf schedule dates if available
    if schedule_by_key:
        # Find events currently in progress — collect all, pick most important
        in_progress = []
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            end = sched.get("end_date")
            if start and end and start <= now_str <= end:
                in_progress.append(t)

        if in_progress:
            in_progress.sort(key=lambda t: -_tournament_importance(t["key"]))
            return _build_current_event(in_progress[0])

        # Find nearest upcoming events — collect all in nearest date, pick most important
        upcoming_by_start: dict[str, list[dict]] = defaultdict(list)
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            if start and start > now_str:
                try:
                    start_dt = datetime.fromisoformat(start)
                    if (start_dt - now).days <= 7:
                        upcoming_by_start[start].append(t)
                except (ValueError, TypeError):
                    continue

        if upcoming_by_start:
            # Get the nearest start date group
            nearest_start = min(upcoming_by_start.keys())
            nearest_group = upcoming_by_start[nearest_start]
            nearest_group.sort(key=lambda t: -_tournament_importance(t["key"]))
            return _build_current_event(nearest_group[0])

    # Phase 2: Fallback — pick the tour event closest to "right now".
    # Primary signal: commence_time proximity to now (nearest current/upcoming wins).
    # Secondary: odds movement (active events have more movement).
    # Tertiary: source count as tiebreaker.
    candidates = []
    for t in tour_events:
        # Use commence_time to determine relevance
        commence_str = t.get("commence_time")
        resolution_str = t.get("resolution_date")

        # Need at least one date signal
        if not commence_str and not resolution_str:
            continue

        # Filter out events that ended >7 days ago based on commence_time
        # (resolution_date can be misleading — Kalshi markets resolve weeks after
        # tournaments end, so a finished tournament might have a far-future resolution_date)
        if commence_str:
            try:
                commence_dt = datetime.fromisoformat(commence_str)
                # Golf tournaments are ~4 days. Skip if commenced >6 days ago.
                if commence_dt < now - timedelta(days=6):
                    continue
            except (ValueError, TypeError):
                pass

        # Compute proximity to now (lower = better)
        proximity_days = 999.0
        if commence_str:
            try:
                commence_dt = datetime.fromisoformat(commence_str)
                proximity_days = abs((now - commence_dt).total_seconds()) / 86400
            except (ValueError, TypeError):
                pass

        # Movement signals: how many golfers moved + total movement magnitude
        movers = sum(
            1 for g in t["golfers"]
            if g.get("movement_24h") is not None and abs(g["movement_24h"]) >= 0.005
        )
        total_movement = sum(
            abs(g["movement_24h"]) for g in t["golfers"]
            if g.get("movement_24h") is not None
        )
        total_sources = sum(len(g.get("sources", {})) for g in t["golfers"])
        importance = _tournament_importance(t["key"])
        candidates.append((t, importance, movers, total_movement, total_sources, proximity_days))

    if candidates:
        # Sort by: importance desc, proximity asc, movers desc, total_movement desc, sources desc
        candidates.sort(key=lambda c: (-c[1], c[5], -c[2], -c[3], -c[4]))
        return _build_current_event(candidates[0][0])

    return None


def _build_current_event(t: dict) -> dict:
    """Build the current_event response dict from a tournament.

    Sorts market_ids so DataGolf Winner markets appear first, then other Winner
    markets, then remaining. DataGolf markets give best progression results
    (exact prefix-based sibling discovery via Method 1).
    """
    raw_ids = t.get("market_ids", [])
    raw_names = t.get("market_names", [])
    raw_sources = t.get("market_sources", [])

    # Build triples: (id, name, source)
    if len(raw_ids) == len(raw_names) == len(raw_sources):
        triples = list(zip(raw_ids, raw_names, raw_sources))
    elif len(raw_ids) == len(raw_names):
        triples = [(mid, nm, "") for mid, nm in zip(raw_ids, raw_names)]
    else:
        triples = [(mid, "", "") for mid in raw_ids]

    def _sort_key(triple):
        _id, name, source = triple
        name_lower = name.lower()
        is_winner = "winner" in name_lower and "round" not in name_lower
        is_datagolf = source == "datagolf"
        # DataGolf Winner = 0, Other Winner = 1, DataGolf Non-Winner = 2, Rest = 3
        if is_winner and is_datagolf:
            return (0, _id)
        elif is_winner:
            return (1, _id)
        elif is_datagolf:
            return (2, _id)
        return (3, _id)

    triples.sort(key=_sort_key)
    sorted_ids = [t[0] for t in triples]
    sorted_names = [t[1] for t in triples]

    return {
        "key": t["key"],
        "name": t["name"],
        "slug": _clean_slug(t["name"]),
        "resolution_date": t.get("resolution_date"),
        "start_date": t.get("start_date"),
        "end_date": t.get("end_date"),
        "venue": t.get("venue"),
        "golfer_count": len(t["golfers"]),
        "leader": t["golfers"][0]["name"] if t["golfers"] else None,
        "leader_probability": t["golfers"][0]["probability"] if t["golfers"] else None,
        "top_golfers": t["golfers"][:5],
        "market_ids": sorted_ids,
        "market_names": sorted_names,
    }


# ============================================================================
# Tournament detail page
# ============================================================================

# Market type detection patterns for sub-grouping
_MARKET_TYPE_PATTERNS = [
    (re.compile(r"\b(?:Winner|Champion)\b(?!.*Round)", re.I), "winner", "Winner"),
    (re.compile(r"\bTop\s+5\b", re.I), "top_5", "Top 5"),
    (re.compile(r"\bTop\s+10\b", re.I), "top_10", "Top 10"),
    (re.compile(r"\bTop\s+20\b", re.I), "top_20", "Top 20"),
    (re.compile(r"\bMa[dk]e\s+Cut\b", re.I), "make_cut", "Make Cut"),
    (re.compile(r"\bRound\s+\d+\s+Leader\b", re.I), "round_leader", "Round Leader"),
]


def _detect_market_type(market_name: str) -> tuple[str, str]:
    """Detect the market type from a market name. Returns (type_key, label)."""
    for pattern, type_key, label in _MARKET_TYPE_PATTERNS:
        if pattern.search(market_name):
            return type_key, label
    return "other", "Other"


@router.get("/tournaments/{slug}")
async def get_golf_tournament(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed tournament data for a specific golf tournament."""
    # Reuse get_golf() for its caching and aggregation
    golf_data = await get_golf(db=db)

    tournaments = golf_data.get("tournaments", [])

    # Find matching tournament by slug
    tournament = None
    for t in tournaments:
        t_slug = t.get("slug") or _clean_slug(t["name"])
        if t_slug == slug:
            tournament = t
            break

    if not tournament:
        raise HTTPException(status_code=404, detail=f"Tournament '{slug}' not found")

    # Sub-group markets by type (winner, top_5, top_10, etc.)
    market_ids = tournament.get("market_ids", [])
    market_names = tournament.get("market_names", [])

    # Build market_id -> market_name mapping
    id_to_name: dict[int, str] = {}
    if len(market_ids) == len(market_names):
        id_to_name = dict(zip(market_ids, market_names))

    # Group by type
    market_groups: dict[str, dict] = {}
    for mid in market_ids:
        mname = id_to_name.get(mid, "")
        type_key, label = _detect_market_type(mname)
        if type_key not in market_groups:
            market_groups[type_key] = {
                "type": type_key,
                "label": label,
                "market_ids": [],
                "market_names": [],
            }
        market_groups[type_key]["market_ids"].append(mid)
        market_groups[type_key]["market_names"].append(mname)

    # Order: winner first, then top_5/10/20, make_cut, round_leader, other
    type_order = ["winner", "top_5", "top_10", "top_20", "make_cut", "round_leader", "other"]
    sorted_groups = sorted(
        market_groups.values(),
        key=lambda g: type_order.index(g["type"]) if g["type"] in type_order else 99
    )

    # Find winner market for evolution chart
    evolution_market_id = None
    for g in sorted_groups:
        if g["type"] == "winner" and g["market_ids"]:
            evolution_market_id = g["market_ids"][0]
            break
    if not evolution_market_id and market_ids:
        evolution_market_id = market_ids[0]

    # Filter movers for this tournament
    all_movers = golf_data.get("biggest_movers", [])
    tournament_movers = [
        m for m in all_movers
        if m.get("tournament_key") == tournament.get("key")
    ]

    return {
        "tournament": {
            "name": tournament["name"],
            "slug": slug,
            "key": tournament.get("key"),
            "is_major": tournament.get("is_major", False),
            "is_womens": tournament.get("is_womens", False),
            "start_date": tournament.get("start_date"),
            "end_date": tournament.get("end_date"),
            "venue": tournament.get("venue"),
            "location": tournament.get("location"),
            "schedule_status": tournament.get("schedule_status"),
            "commence_time": tournament.get("commence_time"),
            "resolution_date": tournament.get("resolution_date"),
        },
        "golfers": tournament.get("_all_golfers", tournament.get("golfers", [])),
        "markets": sorted_groups,
        "evolution_market_id": evolution_market_id,
        "biggest_movers": tournament_movers,
    }


# ============================================================================
# Live leaderboard (ultra-low-data endpoint)
# ============================================================================

# In-process cache for leaderboard (avoid hammering DataGolf on every refresh)
_leaderboard_cache: dict[str, tuple[float, dict]] = {}
_LEADERBOARD_CACHE_TTL = 120  # 2 minutes


@router.get("/leaderboard")
async def get_golf_leaderboard(
    tour: str = "pga",
):
    """Live leaderboard with position, score, thru, hole, and win probability.

    Designed for ultra-low-data views — returns everything needed to render
    a lightweight leaderboard table without JavaScript.
    """
    import time

    cache_key = f"leaderboard_{tour}"
    now = time.time()

    # Check cache
    if cache_key in _leaderboard_cache:
        cached_time, cached_data = _leaderboard_cache[cache_key]
        if now - cached_time < _LEADERBOARD_CACHE_TTL:
            return cached_data

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        players, info = await service.get_in_play_with_info(tour)
    finally:
        await service.close()

    if not players:
        return {
            "status": "no_event",
            "message": "No tournament currently in play",
            "event_name": None,
            "current_round": None,
            "last_updated": None,
            "players": [],
        }

    # Sort by position (numeric sort, with CUT/WD at bottom)
    def _pos_sort_key(p):
        pos = (p.position or "999").lstrip("T")
        try:
            return int(pos)
        except ValueError:
            return 9999

    players.sort(key=_pos_sort_key)

    # ----------------------------------------------------------------
    # Load start-of-day snapshot for delta computation
    # ----------------------------------------------------------------
    snapshot_lookup: dict[str, dict] = {}  # player_name -> {position, win_prob, ...}
    try:
        from app.models.models import GolfLeaderboardSnapshot
        from app.services import get_db as _get_db
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select as sa_select
        from zoneinfo import ZoneInfo

        et_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
        today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Use a fresh DB session for snapshot lookup
        from app.services.database import async_session_maker
        async with async_session_maker() as snap_session:
            snap_result = await snap_session.execute(
                sa_select(GolfLeaderboardSnapshot).where(
                    GolfLeaderboardSnapshot.tour == tour,
                    GolfLeaderboardSnapshot.snapshot_date == today_start,
                    GolfLeaderboardSnapshot.snapshot_type == "start_of_day",
                )
            )
            snapshot = snap_result.scalar_one_or_none()
            if snapshot and snapshot.data:
                for entry in snapshot.data:
                    name = entry.get("player_name", "")
                    snapshot_lookup[name.lower()] = entry
                logger.info("Leaderboard: loaded %d-player start-of-day snapshot", len(snapshot_lookup))
    except Exception as e:
        logger.warning("Leaderboard: could not load snapshot: %s", e)

    # Build response
    leaderboard = []
    for p in players:
        # Determine hole — thru "F" means finished round, otherwise it's the hole number
        thru = p.thru
        if thru and thru.upper() == "F":
            hole_display = "F"
        elif thru and thru.isdigit():
            hole_display = f"H{thru}"
        else:
            hole_display = thru or "—"

        # Format scores
        total = p.total_score
        if total is not None:
            score_display = "E" if total == 0 else f"{total:+d}" if total != 0 else "E"
        else:
            score_display = "—"

        today = p.today_score
        if today is not None:
            today_display = "E" if today == 0 else f"{today:+d}" if today != 0 else "E"
        else:
            today_display = "—"

        win_prob = round(p.win * 100, 1) if p.win else 0.0

        # Compute deltas from start-of-day snapshot
        position_change = None
        win_prob_change = None
        snap_entry = snapshot_lookup.get(p.player_name.lower())
        if snap_entry:
            # Position change: positive = moved up the leaderboard
            snap_pos = snap_entry.get("position", "")
            if snap_pos and p.position:
                try:
                    snap_pos_num = int(str(snap_pos).lstrip("T"))
                    cur_pos_num = int(str(p.position).lstrip("T"))
                    position_change = snap_pos_num - cur_pos_num  # positive = climbed
                except (ValueError, TypeError):
                    pass

            # Win probability change
            snap_wp = snap_entry.get("win_prob")
            if snap_wp is not None:
                win_prob_change = round(win_prob - snap_wp, 1)

        leaderboard.append({
            "position": p.position or "—",
            "name": p.player_name,
            "score": score_display,
            "total_score_raw": p.total_score,
            "today": today_display,
            "today_raw": p.today_score,
            "thru": thru or "—",
            "hole": hole_display,
            "win_prob": win_prob,
            "win_prob_change": win_prob_change,
            "position_change": position_change,
            "top_5_prob": round(p.top_5 * 100, 1) if p.top_5 else None,
            "top_10_prob": round(p.top_10 * 100, 1) if p.top_10 else None,
            "top_20_prob": round(p.top_20 * 100, 1) if p.top_20 else None,
            "make_cut_prob": round(p.make_cut * 100, 1) if p.make_cut else None,
            "current_round": p.current_round,
        })

    result = {
        "status": "live",
        "event_name": info.get("event_name", "Unknown Event"),
        "current_round": info.get("current_round"),
        "last_updated": info.get("last_updated") or datetime.now(timezone.utc).isoformat(),
        "tour": tour,
        "player_count": len(leaderboard),
        "has_snapshot": bool(snapshot_lookup),
        "players": leaderboard,
    }

    # Cache it
    _leaderboard_cache[cache_key] = (now, result)

    return result
