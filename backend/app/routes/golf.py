"""
Golf category landing page endpoint.

Aggregates futures market odds across Polymarket, Kalshi, and The Odds API for golf tournaments.
Groups by tournament, merges cross-source golfer odds, and computes biggest movers.
Enriches with PGA tour schedule from DataGolf for accurate current-event detection.
"""

import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Event, Sport
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
    # Racquet sports that share tournament names with golf (#225: the "British
    # Open Squash" winner leaked into The (golf) Open's winner field and crowned
    # squash champion Paul Coll as a co-winner).
    r"\bsquash\b|\bbadminton\b|table\s+tennis|"
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
# "senior open" catches the U.S. Senior Open Championship (KXCHAMPTOUR-USSOC*)
# and The Senior Open Championship — Champions/senior-tour majors whose names
# contain "Open Championship" and would otherwise fold into The (British) Open's
# family, contaminating its winner group with a different field (L2-90 render gap).
# "last-chance qualifier"/"final qualifying" catch The Open's DISTINCT pre-tournament
# Final Qualifying event (KXPGATOUR-THOLCQ26, "The Open: Last-Chance Qualifier
# Winner") — a separate field of hopefuls competing for entry, not the championship
# itself; it name-matches "the open" and would otherwise surface on the championship
# page (L2-93 render gap, caught on the Open debut-eve pass).
_NOT_THE_OPEN_RE = re.compile(
    r"south\s+african\s+open|joburg\s+open|kenya\s+open|senior\s+open"
    r"|last[-\s]?chance\s+qualifier|final\s+qualifying",
    re.I,
)

# Order matters: more specific patterns first
_TOURNAMENT_PATTERNS = [
    (re.compile(r"(?:the\s+)?masters(?:\s+(?:tournament|golf|winner|champion))?(?!\s+(?:tour|bangkok|shanghai|madrid|tokyo|reykjavik|copenhagen))", re.I), "masters"),
    # NOTE: "Augusta National Invitational" is a Kalshi participation/field
    # market, NOT a winner market. Do NOT map it to "masters" — its high
    # per-golfer probabilities (80-95%) corrupt winner market averages.
    # It is suppressed below via the market probability sum guard.
    (re.compile(r"pga\s+championship", re.I), "pga_championship"),
    (re.compile(r"us\s+open|u\.s\.\s+open", re.I), "us_open"),
    (re.compile(r"the\s+open\s+championship|(?:the\s+)?open\s+championship|british\s+open|the\s+open\b", re.I), "the_open"),
    (re.compile(r"players\s+championship", re.I), "players"),
    (re.compile(r"ryder\s+cup", re.I), "ryder_cup"),
    (re.compile(r"presidents?\s+cup", re.I), "presidents_cup"),
    (re.compile(r"liv\s+golf", re.I), "liv"),
    (re.compile(r"tomorrow'?s?\s+golf\s+league|tgl\s+champion", re.I), "tgl"),
]

# #950: Polymarket intermittently obfuscates major trademarks (e.g. "uptspt
# Open" for "U.S. Open"). A scrambled name shares too few words with the real
# major, so it orphans into a separate card instead of merging. Normalize known
# scrambles to the canonical name BEFORE pattern matching. Small + reusable —
# extend as new scrambles are observed. (Defensive: as of prod 2026-06-18 no
# scrambled major name is present — current Polymarket major names are clean —
# but the obfuscation recurs, so this is forward insurance.)
_SCRAMBLED_MAJOR_FIXUPS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"uptspt\s+open", re.I), "U.S. Open"),
]


def _fix_scrambled_major(market_name: str) -> str:
    """Replace a known scrambled major name with its canonical form."""
    for pattern, canonical in _SCRAMBLED_MAJOR_FIXUPS:
        if pattern.search(market_name):
            return pattern.sub(canonical, market_name)
    return market_name


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
    # Women's variants — separated from men's to prevent cross-contamination
    "masters_womens": "The Masters (Women's)",
    "pga_championship_womens": "KPMG Women's PGA Championship",
    "us_open_womens": "U.S. Women's Open",
    "the_open_womens": "AIG Women's Open",
    "players_womens": "The Players Championship (Women's)",
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

from app.utils.name_normalization import clean_slug as _clean_slug, strip_diacritics as _strip_diacritics_canonical, _SPONSOR_SUFFIX_RE

TOURNAMENT_ORDER = [
    "masters", "pga_championship", "us_open", "the_open",
    "players", "ryder_cup", "presidents_cup",
    # Women's majors after men's majors
    "masters_womens", "pga_championship_womens", "us_open_womens", "the_open_womens",
    "liv", "tgl", "other",
]

# Max golfers to return per tournament
_MAX_GOLFERS = 15

# Outcomes that are not individual golfer names — skip these.
# Catches prop market outcomes that leak through when Kalshi groups
# multiple market types (winner, tour, nationality, score, margin)
# under the same tournament name.
_PROP_OUTCOME_RE = re.compile(
    r"(?:"
    r"\d\+\s|"                   # "1+ golf major..."
    r"\bany\s+golfer\b|"         # "Any golfer"
    r"\bcombined\b|"             # "...combined"
    r"\band\b.*\bcombined\b|"    # "X, Y, and Z combined"
    r"^yes$|^no$|"               # Binary yes/no outcomes
    # Tour name outcomes (from "tour of winner" props)
    r"^pga\s+tour$|"             # "PGA Tour"
    r"^liv$|"                    # "LIV"
    r"^dp\s+world|"              # "DP World Tour"
    r"^european\s+tour|"         # "European Tour"
    r"^korn\s+ferry|"            # "Korn Ferry Tour"
    r"^asian\s+tour|"            # "Asian Tour"
    # Country/region outcomes (from "nationality of winner" props)
    r"\bunited\s+states\b|"      # "United States"
    r"\bunited\s+kingdom\b|"     # "United Kingdom & Ireland"
    r"\bcontinental\s+europe\b|" # "Continental Europe"
    r"\brest\s+of\s+(?:the\s+)?world\b|" # "Rest of World"
    r"^(?:europe|asia|africa|australia|international)$|"  # Single-word regions
    # Score/margin outcomes (from "winning score" and "margin" props)
    r"\bexactly\s+\d+|"          # "Exactly 1 stroke", "Exactly 0 strokes"
    r"\bstroke|"                  # Anything with "stroke(s)"
    r"\bwinning\s+score|"        # "Winning Score: -13 to -15"
    r"-\d+\s+to\s+-\d+|"         # Score ranges like "-13 to -15"
    r"\bunder\s+par\b|"          # "Under par" props
    r"\bover\s+par\b|"           # "Over par" props
    r"\bbogey|"                   # "Bogey-free round" etc.
    r"\bbirdie"                   # "Most birdies" etc.
    r")",
    re.I,
)

# Markets that are NOT outright winner markets — exclude from headline probability.
# These include field/participation markets, placement, and prop bets.
_NON_WINNER_MARKET_RE = re.compile(
    r"(?:"
    r"\bcompete\s+(?:in|at)\b|"  # "Golfers to compete in/at The Masters"
    r"\bplay\s+(?:in|at)\b|"     # "Will Tiger Woods play in/at..."
    r"\bparticipat|"             # "participate in"
    r"\binvitational\b|"         # "Augusta National Invitational" (Kalshi participation market)
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
    r"\bwill\b.*\bcompete\b|"    # "Will X compete in/at..."
    r"\btee\s+(?:it\s+)?up\b|"   # "Will X tee up at..."
    r"\bin\s+the\s+field\b|"     # "Will X be in the field?"
    r"\bcaptain\b|"              # "U.S. Team Captain at 2027 Ryder Cup"
    # Prop market types (Kalshi creates separate events for these)
    r"\bnationality\b|"          # "Nationality of Winner"
    r"\bcountry\b.*\bwinner\b|"  # "Country of Winner"
    r"\btour\b.*\bwinner\b|"     # "Tour of Winner"
    r"\bwinner'?s?\s+tour\b|"    # "Winner's Tour"
    r"\bwinning\s+score\b|"      # "Winning Score"
    r"\bscore\s+range\b|"        # "Score Range"
    r"\bmargin\s+of\s+victory\b|" # "Margin of Victory"
    r"\bwinning\s+margin\b|"     # "Winning Margin"
    r"\bmargin\s+in\s+stroke|"   # "Margin in strokes"
    r"\b(?:over|under)\s+par\b|" # "Over/Under Par"
    r"\bstroke[s]?\s+(?:margin|lead|ahead)\b" # "Strokes margin/lead"
    r")",
    re.I,
)

# Positive outright-winner signal — paired with _NON_WINNER_MARKET_RE (which
# excludes props like "Nationality of Winner") to detect a true winner field.
_WINNER_MARKET_RE = re.compile(r"\b(?:winner|to\s+win)\b", re.I)

# #225 Item 3: minimum resolved-winner snapshot probability for a settled winner
# market to be preferred as the evolution (path-to-resolution) chart source. A
# real-money market converges to ~1.0 for the champion; a stale futures market
# that stopped before the finish never crosses this, so it stays a fallback.
_SETTLED_RESOLVE_MIN = 0.5

# Chart-specific exclusion for the contenders Win chart (#955): drop winner-PROP
# markets (nationality / country-of-winner / tour-of-winner / winning margin)
# that classify as type "winner" but hold no golfers. Unlike _NON_WINNER_MARKET_RE,
# this must NOT match a real field like "PGA Tour: U.S. Open Winner", so it uses
# the "X of (the) winner" prop phrasing and explicit prop nouns rather than a
# broad "tour .* winner".
_NON_CONTENDER_WINNER_RE = re.compile(
    r"\bnationality\b"
    r"|\bcontinent\b"
    r"|\b(?:country|tour|region|state)\s+of\s+(?:the\s+)?winner\b"
    r"|\bwinning\s+(?:country|nationality|tour|score|margin)\b"
    r"|\bwinner'?s?\s+(?:tour|nationality|country)\b"
    r"|\bmargin\s+of\s+victory\b",
    re.I,
)


def _golf_winner_renorm_factor(
    market_name: str, n_outcomes: int, prob_sum: float
) -> float | None:
    """Renormalization factor for a golf winner market, or None to skip it (#926).

    Kalshi tournament-WINNER markets are independent per-golfer binaries that sum
    well over 100% (gotcha #23). They represent a real field, so we renormalize
    them to sum 1.0 (factor = 1/sum) instead of dropping them at the >1.5
    participation-market skip — but ONLY when there's a positive winner signal,
    ≥4 candidates, and it isn't a participation/threshold/prop market. Markets
    summing <=1.5 are returned with factor 1.0 (used as-is, unchanged — keeps the
    existing majors like the 1.483-sum U.S. Open winner identical). Genuine
    participation markets (make-cut, top-N, round-leader, scores) return None.
    """
    if prob_sum <= 1.5:
        return 1.0
    is_winner_field = (
        n_outcomes >= 4
        and bool(_WINNER_MARKET_RE.search(market_name))
        and not _NON_WINNER_MARKET_RE.search(market_name)
    )
    if is_winner_field and prob_sum > 0:
        return 1.0 / prob_sum
    return None


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


# DataGolf tour codes → our tour keys
_DG_TOUR_TO_KEY = {
    "pga": "pga",
    "euro": "dp_world",
    "dp_world": "dp_world",
    "kft": "korn_ferry",
    "korn_ferry": "korn_ferry",
    "opp": "pga",         # opposite-field PGA Tour events (same week as majors)
    "alt": "dp_world",    # alternate/co-sanctioned events
    "asian": "asian",
    "asian_tour": "asian",
    "liv": "liv",
    "lpga": "lpga",
}


def _datagolf_tour_to_key(tour: str | None) -> str | None:
    """Map a DataGolf tour code or label to our public tour key."""
    if not tour:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", tour.lower()).strip("_")
    return _DG_TOUR_TO_KEY.get(normalized)


def _classify_tour(
    market_name: str,
    tournament_key: str,
    is_major: bool,
    is_womens: bool,
    market_external_ids: list[str] | None = None,
    market_metadata_tours: list[str] | None = None,
) -> str:
    """Classify a tournament into a tour. Returns tour key."""
    if is_major:
        return "major"
    if is_womens:
        return "lpga"
    for pattern, tour in _TOUR_CLASSIFICATION_PATTERNS:
        if pattern.search(market_name):
            return tour
    # Prefer DataGolf's explicit tournament tour metadata when present.
    # Some events have generic names (e.g. Hainan Open) and otherwise fall
    # through to the PGA default.
    if market_metadata_tours:
        for tour in market_metadata_tours:
            mapped = _datagolf_tour_to_key(tour)
            if mapped:
                return mapped
    # Check DataGolf external_id for authoritative tour classification
    # e.g., "datagolf:euro:123:win" → "dp_world"
    if market_external_ids:
        for eid in market_external_ids:
            if eid and eid.startswith("datagolf:"):
                parts = eid.split(":")
                if len(parts) >= 2:
                    mapped = _datagolf_tour_to_key(parts[1])
                    if mapped:
                        return mapped
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


_strip_diacritics = _strip_diacritics_canonical


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
    # Strip suffixes BEFORE comma reversal so "Love III, Davis" →
    # "Love, Davis" → "Davis Love" (not "Davis Love III, Love" order bug).
    name = re.sub(r"\s+(?:Jr|Sr|III|II|IV)\.?(?=\s*,|\s*$)", "", name, flags=re.I)
    # Convert "Last, First" to "First Last" (DataGolf format)
    # Unicode \w handles accented capitals (Højgaard, Müller, Skarsgård)
    # The first-name group uses [\w.'"-] to handle initials like "J.J." and
    # hyphenated names.
    comma_match = re.match(r"^(\w[\w'-]+),\s+([\w.]['.\w-]+.*)$", name, flags=re.UNICODE)
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
    # "si" omitted — conflicts with Korean names (Si Woo Kim)
    "sepp": "josef",
}


def _merge_abbreviated_golfers(golfer_data: dict[str, dict]) -> dict[str, dict]:
    """Merge abbreviated-name entries into full-name entries.

    Sportsbooks often abbreviate golfer names to "F. Lastname" while DataGolf
    and prediction markets use full names. This creates separate entries with
    different match keys (e.g., "c smith" vs "cameron smith").

    Algorithm:
    1. Group entries by last name (final token in match key)
    2. Identify abbreviated entries (1-char first part like "c") and
       initial entries (2-char first part like "ct", "jj")
    3. For each, find longer entries where the first letter matches
    4. If exactly ONE match → merge (unambiguous)
    5. If multiple matches → skip (ambiguous; DataGolf filter handles it)

    Handles three merge types:
    - "c smith" (1 char) → "cameron smith" (full name)
    - "j spaun" (1 char) → "jj spaun" (2-char initials)
    - "c pan" (1 char) → "ct pan" (2-char initials)

    Also handles _NAME_ALIASES reversals: "t finau" merges into
    "anthony finau" because "tony" (starts with 't') aliases to "anthony".
    """
    from collections import defaultdict

    # Build reverse alias map: expanded_name → set of first chars that alias to it
    # e.g., "anthony" → {"t"} (from tony→anthony), "thomas" → {"t"} (from tommy)
    _alias_first_chars: dict[str, set[str]] = {}
    for short, long in _NAME_ALIASES.items():
        _alias_first_chars.setdefault(long, set()).add(short[0])
    # Also add the canonical name's own first char
    for long_name in set(_NAME_ALIASES.values()):
        _alias_first_chars.setdefault(long_name, set()).add(long_name[0])

    def _first_chars_match(abbrev_first: str, candidate_first: str) -> bool:
        """Check if abbreviated first char(s) could match a candidate's first token."""
        # Direct first-letter match
        if candidate_first[0] == abbrev_first[0]:
            return True
        # Check alias reversals: does any alias starting with abbrev_first[0]
        # expand to candidate_first?
        possible_chars = _alias_first_chars.get(candidate_first, set())
        return abbrev_first[0] in possible_chars

    # Group by last name
    by_last: dict[str, list[str]] = defaultdict(list)
    for key in golfer_data:
        parts = key.split()
        if parts:
            by_last[parts[-1]].append(key)

    to_merge: dict[str, str] = {}  # abbreviated_key → full_key

    for last_name, keys in by_last.items():
        if len(keys) < 2:
            continue

        for key in keys:
            parts = key.split()
            first = " ".join(parts[:-1])

            # Is this an abbreviated entry? (1-char first part, all alpha)
            if not first or len(first) != 1 or not first.isalpha():
                continue

            # Find ALL longer entries where first letter could match
            candidates = [
                k for k in keys
                if k != key
                and len(k.split()[0]) > 1
                and _first_chars_match(first, k.split()[0])
            ]

            if len(candidates) == 1:
                to_merge[key] = candidates[0]

    if not to_merge:
        return golfer_data

    # Execute merges: fold abbreviated data into full-name entries
    for short_key, long_key in to_merge.items():
        if short_key not in golfer_data or long_key not in golfer_data:
            continue

        short = golfer_data[short_key]
        long = golfer_data[long_key]

        # Merge sources and probabilities
        long["sources"].update(short["sources"])
        long["probabilities"].extend(short["probabilities"])

        if short["movement_24h"] is not None and long["movement_24h"] is None:
            long["movement_24h"] = short["movement_24h"]
        if short["opening_probability"] is not None and long["opening_probability"] is None:
            long["opening_probability"] = short["opening_probability"]

        del golfer_data[short_key]
        logger.info("Golf dedup: merged '%s' into '%s'", short_key, long_key)

    return golfer_data


def _completed_round_ceiling(
    round_markets: list[tuple[str, int | None, bool]],
) -> int:
    """Last completed round, inferred from round-market signals (The Open 2026 p0).

    Each tuple is (kind, round_number, has_graded_winner). A round is complete
    when its LEADER market is graded (`is_winner` set on the actual leader) —
    Kalshi leaves the market status='open' (gotcha #33), so is_winner, not
    status, is the round-complete signal. Top-N projection markets never grade
    themselves, so they are settled purely by inference: every round <= this
    ceiling is over. A graded Top-N market does NOT count (only leaders mark a
    round done). Returns 0 when no round has concluded (nothing settles).
    """
    completed = [
        rnd
        for (kind, rnd, has_winner) in round_markets
        if kind == "leader" and has_winner and isinstance(rnd, int)
    ]
    return max(completed) if completed else 0


def _round_scoped_market_complete(name: str | None, max_completed_round: int) -> bool:
    """True when a round-scoped RELATED market belongs to a round already over.

    The Open 2026 p0 follow-up. "Round 1 Scores", "Round 2 Lowest Score" and
    friends encode their round in the name; once that round is over they must not
    keep showing live odds (settled-means-settled). The round-complete signal is
    the same cross-market ceiling the round groups use (`_completed_round_ceiling`
    — highest round whose leader is graded). Tournament-wide markets with no round
    number ("Lowest Round Score") and the live/future round ("End of Round 4 …"
    while round 4 is in play) return False — only settled PAST rounds are hidden.
    """
    m = re.search(r"Round\s+(\d+)", name or "", re.I)
    if not m:
        return False
    return int(m.group(1)) <= max_completed_round


def _round_outcome_in_field(
    name: str | None, is_winner: bool, field_keys: set[str], apply_filter: bool
) -> bool:
    """Field-membership guard for a round-scoped prop outcome (The Open 2026 p0).

    Kalshi "End of Round N Leader" markets carry a ~165-name speculative candidate
    roster that includes players who are NOT in the field — past champions and
    celebrities (Tiger Woods, Phil Mickelson, John Daly, Ernie Els). Rendered
    verbatim, they appeared as live round-leader outcomes. Keep an outcome only
    when:
      * the filter is OFF (no DataGolf-authoritative field for this event — the
        golfer list IS the padded source list, so filtering would be a no-op and
        we must not risk dropping a real entrant), OR
      * it is the graded round winner (authoritative even if its name key somehow
        misses the roster — never drop a settled winner), OR
      * its name matches a field competitor (same `_match_key` the placement grid
        already uses to line Kalshi outcomes up with the DataGolf field).
    """
    if not apply_filter:
        return True
    if is_winner:
        return True
    return _match_key(name or "") in field_keys


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
    - Multi-initial: "J. Spaun" (Odds API) → "jj spaun" (matches "J.J. Spaun")
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
    # Collapse adjacent single-letter tokens into one token.
    # "j j spaun" → "jj spaun", "c t pan" → "ct pan".
    # This handles space-separated initials from sportsbooks ("J. J. Spaun").
    parts = clean.split()
    collapsed: list[str] = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1 and parts[i].isalpha():
            # Gather consecutive single-letter tokens
            letters = parts[i]
            while i + 1 < len(parts) and len(parts[i + 1]) == 1 and parts[i + 1].isalpha():
                i += 1
                letters += parts[i]
            collapsed.append(letters)
        else:
            collapsed.append(parts[i])
        i += 1
    parts = collapsed
    # Expand first-name aliases for cross-source dedup
    if parts and parts[0] in _NAME_ALIASES:
        parts[0] = _NAME_ALIASES[parts[0]]
    clean = " ".join(parts)
    return clean


def _normalize_tournament(market_name: str, schedule: list[dict] | None = None) -> str:
    """Extract tournament key from a market name. Returns 'other' if no match."""
    # #950: de-obfuscate scrambled major trademarks (e.g. Polymarket's "uptspt
    # Open") so the event merges onto the canonical major card, not an orphan.
    market_name = _fix_scrambled_major(market_name)
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
        r"\s*[-–]\s*(?:Tournament\s+Winner|Winner|Top\s+\d+(?:\s+Finish)?|Make\s+(?:the\s+)?Cut|Round\s+\d+\s+Leader)\s*$",
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


def _is_h2h_matchup(market) -> bool:
    """Check if a market is a head-to-head matchup (exactly 2 golfer outcomes summing to ~1.0)."""
    valid = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in (
            "yes", "no", "tie", "field", "other", "the field",
        )
    ]
    if len(valid) != 2:
        return False
    prob_sum = sum(float(o.current_probability) for o in valid)
    if prob_sum < 0.85 or prob_sum > 1.15:
        return False
    for o in valid:
        if not _match_key(o.name):
            return False
        if len(o.name.strip().split()) < 2:
            return False
    return True


async def _fetch_24h_snapshots(
    db: AsyncSession, outcome_ids: list[int], now: datetime,
) -> dict[int, float]:
    """Batch-fetch probabilities from ~24h ago for a list of outcome IDs."""
    if not outcome_ids:
        return {}

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
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
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
    return {row.outcome_id: float(row.probability) for row in snap_result}


def _dedup_winner_markets(tourn_key: str, tourn_markets: list) -> tuple[dict[str, int], set[int]]:
    """Per-source dedup of winner-type markets, keeping the one with most golfer outcomes.

    Returns (source_best, dedup_candidates) where source_best maps source to best market id.
    """
    source_groups: dict[str, list[tuple[int, int]]] = defaultdict(list)
    dedup_candidates: set[int] = set()

    for m in tourn_markets:
        if _NON_WINNER_MARKET_RE.search(m.name):
            continue
        src = m.source or "unknown"
        golfer_count = sum(
            1 for o in m.outcomes
            if o.current_probability is not None
            and o.name.strip().lower() not in ("tie", "field", "other", "the field")
            and not _PROP_OUTCOME_RE.search(o.name.strip())
        )
        source_groups[src].append((m.id, golfer_count))
        dedup_candidates.add(m.id)

    source_best: dict[str, int] = {}
    for src, candidates in source_groups.items():
        best_id, best_count = max(candidates, key=lambda x: x[1])
        source_best[src] = best_id
        if len(candidates) > 1:
            logger.info(
                "Golf dedup: source '%s' has %d winner markets for %s, "
                "selected market %d (%d golfer outcomes, skipping %d)",
                src, len(candidates), tourn_key, best_id, best_count,
                len(candidates) - 1,
            )

    return source_best, dedup_candidates


def _extract_prop_market(market, source_label: str) -> dict | None:
    """Extract a prop market (Top 5/10/20, Make Cut) into a response dict."""
    source = market.source or "unknown"
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
    if not prop_outcomes:
        return None
    prop_outcomes.sort(key=lambda x: x["probability"], reverse=True)
    return {
        "name": market.name,
        "source": source_label,
        "outcomes": prop_outcomes[:5],
    }


def _extract_yes_no_prop(market, source_label: str) -> dict | None:
    """#952: surface a non-winner yes/no market as a single-probability prop.

    Markets like "U.S. Open: Playoff", "First Time Winner?", "Hole-in-One" are
    binary yes/no questions that were dropped at the <=2-outcome gate, so
    albatross/hole-in-one/playoff/first-time-winner/record-low-round never
    surfaced. Represent each as the YES probability (e.g. "Playoff: 22% Yes")
    with ``kind="binary"``; the frontend renders a single bar, not a Yes/No pair.
    """
    yes_p: float | None = None
    for o in market.outcomes:
        if o.current_probability is None:
            continue
        nm = (o.name or "").strip().lower()
        if nm == "yes":
            yes_p = float(o.current_probability)
        elif nm == "no" and yes_p is None:
            yes_p = 1.0 - float(o.current_probability)
    if yes_p is None:
        return None
    # Kalshi untraded mid (raw 0.5) is a placeholder, not a real price (#23).
    if (market.source or "") == "kalshi" and yes_p == 0.5:
        return None
    return {
        "name": market.name,
        "source": source_label,
        "kind": "binary",
        "yes_probability": round(yes_p, 3),
        "outcomes": [{"name": "Yes", "probability": round(yes_p, 3)}],
    }


def _aggregate_golfer_outcome(
    outcome, source_label: str, golfer_data: dict[str, dict],
    prob_24h_ago: dict[int, float], prob_scale: float = 1.0,
) -> None:
    """Aggregate a single outcome into golfer_data, tracking sources and movement.

    `prob_scale` renormalizes independent-binary winner fields (gotcha #23, #926)
    to sum 1.0; it is applied consistently to the stored probability, the 24h
    delta, and the opening probability so movement isn't distorted.
    """
    prob = float(outcome.current_probability) * prob_scale
    raw_name = outcome.name.strip()

    if raw_name.lower() in ("tie", "field", "other", "the field"):
        return
    if _PROP_OUTCOME_RE.search(raw_name):
        return

    display_name = _normalize_golfer_name(raw_name)
    key = _match_key(raw_name)
    if not key:
        return

    if key not in golfer_data:
        golfer_data[key] = {
            "name": display_name,
            "sources": {},
            "movement_24h": None,
            "opening_probability": None,
        }

    golfer_data[key]["sources"][source_label] = round(prob, 3)

    if outcome.id in prob_24h_ago:
        delta = prob - prob_24h_ago[outcome.id] * prob_scale
        if abs(delta) >= 0.001:
            existing = golfer_data[key]["movement_24h"]
            if existing is None or abs(delta) > abs(existing):
                golfer_data[key]["movement_24h"] = round(delta, 4)

    if golfer_data[key]["movement_24h"] is None and outcome.probability_change_24h is not None:
        change = float(outcome.probability_change_24h) * prob_scale
        if abs(change) >= 0.001:
            golfer_data[key]["movement_24h"] = round(change, 4)

    if outcome.opening_probability is not None and golfer_data[key]["opening_probability"] is None:
        golfer_data[key]["opening_probability"] = round(
            float(outcome.opening_probability) * prob_scale, 3
        )


def _build_tournament_entry(
    tourn_key: str, tourn_markets: list,
    golfer_data: dict[str, dict], prop_markets_list: list[dict],
    market_ids: list[int], market_sources: list[str],
    earliest_commence, latest_resolution,
) -> dict | None:
    """Build a single tournament response dict from aggregated golfer data."""
    golfer_data = _merge_abbreviated_golfers(golfer_data)

    # Filter to invitees when DataGolf field data exists
    has_datagolf = "datagolf" in market_sources
    if has_datagolf:
        datagolf_keys = {k for k, v in golfer_data.items() if "datagolf_model" in v["sources"]}
        if datagolf_keys:
            filtered_count = len(golfer_data) - len(datagolf_keys)
            if filtered_count > 0:
                logger.info("Golf invitee filter: removed %d non-field golfers from %s", filtered_count, tourn_key)
            golfer_data = {k: v for k, v in golfer_data.items() if k in datagolf_keys}

    golfers = []
    for data in golfer_data.values():
        source_vals = list(data["sources"].values())
        avg_prob = sum(source_vals) / len(source_vals) if source_vals else 0
        golfers.append({
            "name": data["name"],
            "probability": avg_prob,
            "movement_24h": data["movement_24h"],
            "sources": data["sources"],
            "opening_probability": data["opening_probability"],
        })

    golfers.sort(key=lambda g: g["probability"], reverse=True)

    if not golfers:
        return None

    all_golfers = golfers
    for g in all_golfers:
        g["probability"] = round(g["probability"], 3)
        g["american_odds"] = probability_to_american(g["probability"])
    for i, g in enumerate(all_golfers):
        g["rank"] = i + 1

    golfers = all_golfers[:_MAX_GOLFERS]

    order_idx = TOURNAMENT_ORDER.index(tourn_key) if tourn_key in TOURNAMENT_ORDER else 50
    display_name = TOURNAMENT_DISPLAY_NAMES.get(
        tourn_key,
        _TOUR_EVENT_DISPLAY_NAMES.get(tourn_key, tourn_key.replace("_", " ").title()),
    )
    is_tour_event = tourn_key not in TOURNAMENT_ORDER and not tourn_key.startswith("other_") and tourn_key != "other"

    if tourn_key.startswith("other_"):
        display_name = tourn_markets[0].name if tourn_markets else "Other"
        display_name = re.sub(r"\s*\?\s*$", "", display_name)
        order_idx = TOURNAMENT_ORDER.index("other") if "other" in TOURNAMENT_ORDER else 99

    if is_tour_event and latest_resolution:
        order_idx = 50

    market_names = [m.name for m in tourn_markets]
    is_womens = (
        bool(_WOMENS_RE.search(display_name))
        or any(_WOMENS_RE.search(m.name) for m in tourn_markets)
    )

    tour_name_for_classify = display_name
    if tourn_markets:
        tour_name_for_classify = tourn_markets[0].name
    market_ext_ids = [m.external_id for m in tourn_markets if m.external_id]
    market_metadata_tours = [
        m.market_metadata.get("tour")
        for m in tourn_markets
        if m.market_metadata and m.market_metadata.get("tour")
    ]
    tour = _classify_tour(
        tour_name_for_classify, tourn_key,
        tourn_key in MAJOR_TOURNAMENTS, is_womens,
        market_external_ids=market_ext_ids,
        market_metadata_tours=market_metadata_tours,
    )

    return {
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
        "_all_golfers": all_golfers,
    }


def _route_h2h_to_tournament(
    market, golfer_to_tournaments: dict[str, set[str]],
    tourn_by_commence: list[tuple[datetime, str]], schedule: list,
) -> str | None:
    """Route a head-to-head matchup market to its tournament."""
    valid_outcomes = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in ("yes", "no", "tie", "field", "other", "the field")
    ]
    if len(valid_outcomes) != 2:
        return None

    a, b = valid_outcomes
    a_key = _match_key(a.name)
    b_key = _match_key(b.name)
    if not a_key or not b_key:
        return None

    a_tourns = golfer_to_tournaments.get(a_key, set())
    b_tourns = golfer_to_tournaments.get(b_key, set())
    shared = a_tourns & b_tourns

    name_key = _normalize_tournament(market.name, schedule)
    if name_key != "other" and _WOMENS_RE.search(market.name):
        name_key = name_key + "_womens"

    if len(shared) == 1:
        return next(iter(shared))
    if len(shared) > 1:
        return name_key if name_key in shared else next(iter(shared))

    either = a_tourns | b_tourns
    if len(either) == 1:
        return next(iter(either))
    if name_key != "other":
        return name_key

    # commence_time fallback
    if not market.commence_time:
        return None
    m_ct = market.commence_time
    best_key = None
    best_delta = timedelta(days=4)
    for ct, tk in tourn_by_commence:
        delta = abs(ct - m_ct) if ct.tzinfo else abs(ct.replace(tzinfo=timezone.utc) - m_ct)
        if delta < best_delta:
            best_delta = delta
            best_key = tk
    return best_key


def _build_h2h_entry(market, tourn_key: str) -> dict:
    """Build a single H2H matchup dict from a market."""
    valid_outcomes = [
        o for o in market.outcomes
        if o.current_probability is not None
        and o.name.strip().lower() not in ("yes", "no", "tie", "field", "other", "the field")
    ]
    a, b = valid_outcomes[0], valid_outcomes[1]
    source = market.source or "unknown"
    source_label = "datagolf_model" if source == "datagolf" else source
    a_prob = float(a.current_probability)
    b_prob = float(b.current_probability)
    if b_prob > a_prob:
        a, b = b, a
        a_prob, b_prob = b_prob, a_prob

    return {
        "market_id": market.id,
        "source": source_label,
        "golfer_a": {
            "name": _normalize_golfer_name(a.name.strip()),
            "probability": round(a_prob, 3),
        },
        "golfer_b": {
            "name": _normalize_golfer_name(b.name.strip()),
            "probability": round(b_prob, 3),
        },
    }


def _enrich_with_schedule(
    tournaments: list[dict], schedule_by_key: dict[str, dict],
) -> None:
    """Enrich tournaments with DataGolf schedule data (venue, dates, etc.)."""
    _TOURN_TO_SCHED_KEY = {
        "masters": "masters_tournament",
        "us_open": "u_s_open",
        "the_open": "the_open_championship",
        "players": "the_players_championship",
    }
    for t in tournaments:
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
                # #1077: normalize resolution_date to the DataGolf tournament
                # end_date. As shipped, resolution_date carried the Kalshi
                # close-time artifact (gotcha #14), which diverges wildly across
                # surfaces for the same tournament (The Open 2026: Kalshi Aug-2,
                # detail-header Aug-16, real dates Jul-16–19). Once a real
                # schedule end_date exists it is the ground truth, so all
                # surfaces key the same date and resolution_date stops being a
                # latent countdown/header footgun.
                t["resolution_date"] = sched["end_date"]


def _filter_stale_tournaments(tournaments: list[dict], now: datetime) -> list[dict]:
    """Remove completed or stale tournaments based on schedule/date signals."""
    now_date = now.date()
    filtered = []
    for t in tournaments:
        if t.get("schedule_status") == "completed":
            continue
        end_date_str = t.get("end_date")
        if end_date_str:
            try:
                if datetime.fromisoformat(end_date_str).date() < now_date - timedelta(days=1):
                    continue
            except (ValueError, TypeError):
                pass
        elif t.get("start_date"):
            try:
                if datetime.fromisoformat(t["start_date"]).date() < now_date - timedelta(days=7):
                    continue
            except (ValueError, TypeError):
                pass
        elif t.get("resolution_date"):
            try:
                if datetime.fromisoformat(t["resolution_date"]).date() < now_date - timedelta(days=7):
                    continue
            except (ValueError, TypeError):
                pass
        filtered.append(t)
    return filtered


@router.get("")
async def get_golf_cached(
    db: AsyncSession = Depends(get_db),
):
    """Return golf data (Redis-cached to avoid OOM on 512MB dyno)."""
    import json as _json
    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        cached = await rc.get("bainluck:category:golf")
        await rc.aclose()
        if cached:
            return _json.loads(cached)
    except Exception:
        pass

    return await get_golf(db)


async def get_golf(
    db: AsyncSession = Depends(get_db),
):
    """Get golf tournament futures with aggregated odds across sources."""
    now = datetime.now(timezone.utc)

    # Query + filter golf markets
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.external_id.ilike("golf_%"),
                FuturesMarket.llm_sport_category == "golf",
            ),
        )
    )
    result = await db.execute(query)
    markets_all = result.scalars().unique().all()
    markets_all = [m for m in markets_all if _is_golf_market(m)]

    # Split H2H matchups from winner markets
    h2h_markets_raw: list = []
    markets: list = []
    for m in markets_all:
        if _is_h2h_matchup(m):
            h2h_markets_raw.append(m)
        else:
            markets.append(m)
    logger.info(
        "Golf endpoint: %d markets after filtering (%d h2h matchups)",
        len(markets), len(h2h_markets_raw),
    )

    # 24h movement snapshots
    all_outcome_ids = []
    for market in markets:
        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                all_outcome_ids.append(outcome.id)
    prob_24h_ago = await _fetch_24h_snapshots(db, all_outcome_ids, now)
    logger.info("Golf endpoint: found 24h-ago snapshots for %d/%d outcomes",
                len(prob_24h_ago), len(all_outcome_ids))

    # DataGolf schedule
    schedule = await _get_golf_schedule()
    schedule_by_key: dict[str, dict] = {}
    for s_event in schedule:
        key = s_event.get("key", "other")
        if key != "other" and key not in schedule_by_key:
            schedule_by_key[key] = s_event

    # Group markets by tournament
    tournament_markets: dict[str, list] = defaultdict(list)
    for market in markets:
        tournament_key = _normalize_tournament(market.name, schedule)
        if tournament_key == "other":
            tournament_markets[f"other_{market.id}"].append(market)
        else:
            if _WOMENS_RE.search(market.name):
                tournament_key = tournament_key + "_womens"
            tournament_markets[tournament_key].append(market)

    # Build tournament entries with cross-source aggregation
    tournaments = []
    for tourn_key, tourn_markets in tournament_markets.items():
        golfer_data: dict[str, dict] = {}
        prop_markets_list: list[dict] = []
        market_ids = []
        market_sources = []
        earliest_commence = None
        latest_resolution = None

        source_best, dedup_candidates = _dedup_winner_markets(tourn_key, tourn_markets)

        for market in tourn_markets:
            market_ids.append(market.id)
            market_sources.append(market.source or "unknown")
            source = market.source or "unknown"
            source_label = "datagolf_model" if source == "datagolf" else source

            if market.commence_time:
                if earliest_commence is None or market.commence_time < earliest_commence:
                    earliest_commence = market.commence_time
            if market.resolution_date:
                if latest_resolution is None or market.resolution_date > latest_resolution:
                    latest_resolution = market.resolution_date

            if market.id in dedup_candidates and market.id != source_best.get(source):
                continue

            # Per-golfer binary markets: drop the winner-field fragments, but
            # surface NON-winner yes/no questions (playoff, hole-in-one,
            # first-time winner, albatross, record-low-round) as single-prob
            # props instead of dropping them entirely (#952).
            if len(market.outcomes) <= 2:
                outcome_names = {o.name.strip().lower() for o in market.outcomes if o.name}
                if outcome_names & {"yes", "no"}:
                    if _NON_WINNER_MARKET_RE.search(market.name):
                        prop = _extract_yes_no_prop(market, source_label)
                        if prop:
                            prop_markets_list.append(prop)
                    continue

            # Skip participation/field markets (prob sum >> 1) — EXCEPT Kalshi
            # tournament-WINNER fields, which are independent per-golfer binaries
            # that also sum >100% (gotcha #23); those get renormalized to a real
            # field instead of dropped (#926). Markets summing <=1.5 are unchanged.
            outcome_prob_sum = sum(
                float(o.current_probability)
                for o in market.outcomes
                if o.current_probability is not None
            )
            renorm_factor = _golf_winner_renorm_factor(
                market.name, len(market.outcomes), outcome_prob_sum
            )
            if renorm_factor is None:
                continue

            # Non-winner markets go to props
            if _NON_WINNER_MARKET_RE.search(market.name):
                prop = _extract_prop_market(market, source_label)
                if prop:
                    prop_markets_list.append(prop)
                continue

            # Aggregate winner outcomes
            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue
                # Skip Kalshi untraded mid (raw 0.5) before any renormalization.
                if source == "kalshi" and float(outcome.current_probability) == 0.5:
                    continue
                _aggregate_golfer_outcome(
                    outcome, source_label, golfer_data, prob_24h_ago,
                    prob_scale=renorm_factor,
                )

        entry = _build_tournament_entry(
            tourn_key, tourn_markets, golfer_data, prop_markets_list,
            market_ids, market_sources, earliest_commence, latest_resolution,
        )
        if entry:
            tournaments.append(entry)

    # Route H2H matchups to tournaments
    golfer_to_tournaments: dict[str, set[str]] = defaultdict(set)
    for t in tournaments:
        for g in t.get("_all_golfers", t.get("golfers", [])):
            k = _match_key(g["name"])
            if k:
                golfer_to_tournaments[k].add(t["key"])

    tourn_by_commence: list[tuple[datetime, str]] = []
    for t in tournaments:
        ct_str = t.get("commence_time")
        if ct_str:
            try:
                tourn_by_commence.append((datetime.fromisoformat(ct_str), t["key"]))
            except (ValueError, TypeError):
                pass

    h2h_by_tournament: dict[str, list[dict]] = defaultdict(list)
    h2h_unrouted = 0
    for market in h2h_markets_raw:
        tourn_key = _route_h2h_to_tournament(
            market, golfer_to_tournaments, tourn_by_commence, schedule,
        )
        if not tourn_key:
            h2h_unrouted += 1
            continue
        h2h_by_tournament[tourn_key].append(_build_h2h_entry(market, tourn_key))

    if h2h_unrouted:
        logger.info("Golf h2h: %d matchups unrouted (no matching tournament)", h2h_unrouted)

    # Attach and dedupe H2H matchups
    for t in tournaments:
        raw_matchups = h2h_by_tournament.get(t["key"], [])
        seen_pairs: set[tuple[str, str]] = set()
        deduped: list[dict] = []
        for m in raw_matchups:
            key = tuple(sorted([
                _match_key(m["golfer_a"]["name"]) or m["golfer_a"]["name"].lower(),
                _match_key(m["golfer_b"]["name"]) or m["golfer_b"]["name"].lower(),
            ]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            deduped.append(m)
        deduped.sort(key=lambda m: abs(m["golfer_a"]["probability"] - m["golfer_b"]["probability"]))
        t["h2h_matchups"] = deduped

    # Sort and clean up
    tournaments.sort(key=lambda t: (t["order"], t.get("sort_date") or "9999"))
    for t in tournaments:
        del t["order"]
        t.pop("sort_date", None)

    # Enrich + filter
    _enrich_with_schedule(tournaments, schedule_by_key)
    tournaments = _filter_stale_tournaments(tournaments, now)

    # Biggest movers
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

    # Upcoming events
    events_query = (
        select(Event)
        .join(Sport, Event.sport_id == Sport.id)
        .where(
            Sport.key.ilike("golf_%"),
            or_(
                Event.status == "live",
                Event.commence_time.between(now, now + timedelta(days=30)),
                Event.commence_time.between(now - timedelta(hours=6), now),
            ),
        )
        .order_by(Event.commence_time)
        .limit(10)
    )
    events_result = await db.execute(events_query)
    upcoming_events = [
        {
            "id": e.id,
            "name": f"{e.home_team_name} vs {e.away_team_name}" if e.away_team_name else e.home_team_name,
            "commence_time": e.commence_time.isoformat() if e.commence_time else None,
            "status": e.status,
        }
        for e in events_result.scalars().all()
    ]

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
    # Majors are NOT flagged is_tour_event (they sit in TOURNAMENT_ORDER), yet they
    # must be eligible for the marquee slot so an imminent/in-progress major wins the
    # current_event over minor qualifiers (e.g. The Open Championship over "The Open
    # Last Chance Qualifier"). Schedule-date priority (Phase 1) and the >6-days-ago
    # commence filter (Phase 2) still keep a finished major from displacing the true
    # current event, and _tournament_importance ranks a live major above any tour
    # event when both qualify. (#1075)
    tour_events = [t for t in tournaments if t.get("is_tour_event") or t.get("is_major")]
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

# Market type detection patterns for sub-grouping.
# ORDER MATTERS — checked top-to-bottom, first match wins.
_MARKET_TYPE_PATTERNS = [
    (re.compile(r"\b(?:Winner|Champion)\b(?!.*Round)", re.I), "winner", "Winner"),
    # #951: "Round N Top M Finishers" must be caught BEFORE the bare Top-N
    # patterns — otherwise "Round 2 Top 5 Finishers" classifies as tournament
    # "top_5" and gets AVERAGED into the tournament Top-5 grid column
    # (data corruption). Round-specific Top-N is its own type, excluded from the
    # tournament placement columns (a dedicated rounds panel is a follow-up).
    (re.compile(r"\bRound\s+\d+\s+Top\s+\d+\b", re.I), "round_top", "Round Top N"),
    (re.compile(r"\bTop\s+5\b", re.I), "top_5", "Top 5"),
    (re.compile(r"\bTop\s+10\b", re.I), "top_10", "Top 10"),
    (re.compile(r"\bTop\s+20\b", re.I), "top_20", "Top 20"),
    # Alex's ruling (The Open 2026): every per-golfer placement market becomes a
    # column in the ONE golfer grid — "Top 40 Finishers" (Kalshi, 150+ outcomes)
    # was classifying "other" and rendering as a wall of numbers in Related
    # Futures instead of a fused per-golfer column.
    (re.compile(r"\bTop\s+40\b", re.I), "top_40", "Top 40"),
    (re.compile(r"\bMa[dk]e\s+(?:the\s+)?Cut\b", re.I), "make_cut", "Make Cut"),
    (re.compile(r"\bRound\s+\d+\s+Leader\b", re.I), "round_leader", "Round Leader"),
]


def _detect_market_type(market_name: str) -> tuple[str, str]:
    """Detect the market type from a market name. Returns (type_key, label)."""
    for pattern, type_key, label in _MARKET_TYPE_PATTERNS:
        if pattern.search(market_name):
            return type_key, label
    return "other", "Other"


# L2-89: "Winner"-named markets that are NOT the tournament's golfer winner field.
# "The Open: Last-Chance Qualifier Winner" is a separate qualifying field (15
# golfers who never make the main grid); nationality/continent/etc. props are
# caught by _NON_CONTENDER_WINNER_RE. Both classify as type "winner" (they contain
# "Winner") but must not pollute the winner group/evolution chart.
_QUALIFIER_WINNER_RE = re.compile(r"\bqualif(?:y|ier|ying|ication|iers)\b", re.I)


def _tournament_market_type(market_name: str) -> tuple[str, str]:
    """Market type for the tournament DETAIL grouping.

    Wraps _detect_market_type but DOWN-CLASSIFIES a "winner" market that is not the
    real golfer winner field — nationality/continent/country-of-winner props (#955)
    and last-chance *qualifier* fields (L2-89) — into "other" so they surface in
    Related Futures instead of vanishing. Previously they were filtered out of the
    golfer grid + evolution chart (#955) but never routed anywhere, so the whole
    family was invisible on the event page.
    """
    type_key, label = _detect_market_type(market_name or "")
    if type_key == "winner" and (
        _NON_CONTENDER_WINNER_RE.search(market_name or "")
        or _QUALIFIER_WINNER_RE.search(market_name or "")
    ):
        return "other", "Other"
    return type_key, label


_PLAYOFF_RE = re.compile(r"\bplayoff\b", re.I)

# Source preference when collapsing cross-source duplicate "other" markets into
# one card (#956): DataGolf model first, then the deepest liquidity.
_RELATED_SOURCE_PRIORITY = {"datagolf": 0, "polymarket": 1, "kalshi": 2, "odds_api": 3}


def _related_dedup_key(market_name: str) -> str:
    """Group key for collapsing cross-source duplicate 'other' markets (#956).

    Two source markets asking the same real-world question render as two stacked
    cards with conflicting probabilities (Polymarket "Will there be a playoff..."
    27% vs Kalshi "U.S. Open: Playoff" 22%). Their normalized question text does
    NOT match, so a tournament playoff is keyed explicitly; everything else falls
    back to the normalized question (collapses only exact cross-source dupes, not
    the distinct multi-winner family — that stays a separate work item).
    """
    from app.utils.cross_source_matching import normalize_question

    if _PLAYOFF_RE.search(market_name or ""):
        return "playoff"
    return normalize_question(market_name or "")


def _prefer_datagolf_merge(
    existing: float | None,
    existing_is_dg: bool,
    incoming: float,
    incoming_is_dg: bool,
) -> tuple[float, bool]:
    """Combine two probabilities for the same (golfer, placement type), preferring
    DataGolf over one-sided Polymarket/Kalshi placeholders (#954).

    DataGolf is the authoritative in-play model. A blind cross-source average
    blended DataGolf's well-differentiated make_cut (Scheffler 0.85, Puig 0.40)
    with the compressed ~0.5 "To Make the Cut" placeholder markets, flattening
    Bubble Watch to ~50% for everyone. Rules: DataGolf wins over non-DataGolf;
    two same-class values average (preserving prior behavior).

    Returns (value, is_datagolf).
    """
    if existing is None:
        return incoming, incoming_is_dg
    if existing_is_dg and not incoming_is_dg:
        return existing, True              # keep DataGolf, drop placeholder
    if incoming_is_dg and not existing_is_dg:
        return incoming, True              # DataGolf overrides placeholder
    return (existing + incoming) / 2, existing_is_dg  # same source class → average


def _settled_outcome_signal(outcome) -> float | None:
    """Best pre-settlement probability for ordering a settled winner field: live
    price → closing (calibration) line → opening line. Settled winner markets
    carry current_probability=None (gotcha #33), so the closing/opening line is
    the only surviving ordering signal."""
    for v in (
        outcome.current_probability,
        getattr(outcome, "calibration_probability", None),
        outcome.opening_probability,
    ):
        if v is not None:
            return float(v)
    return None


def _assemble_completed_winner_field(
    tournament_markets: list,
) -> tuple[list[dict], list[int], list[str], list[str]]:
    """Assemble the winner field for a SETTLED tournament (#225 Items 1 & 2).

    Returns (golfers, market_ids, market_names, market_sources). Pure over a list
    of market objects (each with .id/.name/.source/.outcomes; each outcome with
    .name/.current_probability/.calibration_probability/.opening_probability/
    .current_american_odds/.is_winner) so it is unit-testable without a DB.

    The prior settled builder pooled EVERY market type — winner, make-cut, top-N,
    round-leader — into one name-keyed map (first-market-wins) using raw
    current_probability. Settled placement markets resolve YES≈0.99 for the whole
    made-cut field (gotcha #33: Kalshi stays status='open' with stale prices), so
    the winner field read as a wall of 0.990000 and the champion could never be
    named (the "R2: Åberg under 69.5" hero Alex flagged). Fixes:
      * FIELD from winner-type markets only (never placement/round/props, never
        nationality/first-time/qualifier props down-classified to "other");
      * champion crowned from is_winner (settled-means-settled — authoritative even
        when the price is stale/None), ordered first;
      * restrict to the authoritative DataGolf field so speculative Kalshi-only
        names for players who never entered (the Tiger-Woods class) drop out.
    """
    market_ids: list[int] = []
    market_names: list[str] = []
    market_sources: list[str] = []
    for market in tournament_markets:
        market_ids.append(market.id)
        market_names.append(market.name or "")
        src = market.source or "sportsbook"
        if src not in market_sources:
            market_sources.append(src)

    def _collect(winner_only: bool) -> dict[str, dict]:
        gmap: dict[str, dict] = {}
        for market in tournament_markets:
            src = market.source or "sportsbook"
            if winner_only and _tournament_market_type(market.name or "")[0] != "winner":
                continue
            for outcome in market.outcomes:
                if not outcome.name:
                    continue
                name = outcome.name.strip()
                if name.lower() in ("yes", "no", "over", "under", "draw"):
                    continue
                prob = _settled_outcome_signal(outcome)
                if not winner_only and prob is None:
                    continue  # legacy fallback keeps the old "has a price" guard
                if name not in gmap:
                    gmap[name] = {
                        "name": name,
                        "probability": prob,
                        "american_odds": outcome.current_american_odds,
                        "movement_24h": None,
                        "opening_probability": outcome.opening_probability,
                        "rank": 0,
                        "sources": {},
                        "won": False,
                    }
                elif gmap[name]["probability"] is None and prob is not None:
                    gmap[name]["probability"] = prob
                if prob is not None:
                    gmap[name]["sources"][src] = prob
                if outcome.is_winner:
                    gmap[name]["won"] = True
                    gmap[name]["is_winner"] = True
        return gmap

    golfer_map = _collect(winner_only=True)
    # Never regress to an empty field: an odd tournament with only placement
    # markets still open falls back to the legacy all-market behavior.
    if not golfer_map:
        golfer_map = _collect(winner_only=False)

    # Restrict to the authoritative DataGolf field when present (mirrors the live
    # invitee filter). The graded champion is always kept even if a key misses.
    dg_field = {k for k, v in golfer_map.items() if "datagolf" in v.get("sources", {})}
    if len(dg_field) >= 20:
        golfer_map = {
            k: v for k, v in golfer_map.items() if k in dg_field or v.get("won")
        }

    # Champion(s) first, then pre-settlement probability desc, then name — a
    # longshot winner is crowned above the field's higher-priced favorites.
    golfers = sorted(
        golfer_map.values(),
        key=lambda g: (0 if g.get("won") else 1, -(g.get("probability") or 0.0), g["name"]),
    )
    for i, g in enumerate(golfers):
        g["rank"] = i + 1
    return golfers, market_ids, market_names, market_sources


async def _build_completed_tournament(
    slug: str,
    db: AsyncSession,
) -> dict | None:
    """Build tournament data from closed/resolved markets for completed tournaments.

    Called when the main golf listing doesn't include the tournament (markets closed).
    Returns a tournament dict compatible with get_golf_tournament's expectations, or None.
    """
    # Find golf markets (any status) whose name matches the slug
    query = (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            or_(
                FuturesMarket.external_id.ilike("golf_%"),
                FuturesMarket.llm_sport_category == "golf",
            ),
        )
    )
    result = await db.execute(query)
    all_markets = result.scalars().unique().all()

    # Group by normalized tournament key using existing logic
    tournament_markets: list[FuturesMarket] = []
    matched_key = None
    for m in all_markets:
        if not _is_golf_market(m):
            continue
        market_name = m.name or ""
        key = _normalize_tournament(market_name)
        # Check slug against both the display name and the raw key
        display = TOURNAMENT_DISPLAY_NAMES.get(key, key.replace("_", " ").title())
        display_slug = _clean_slug(display)
        key_slug = _clean_slug(key.replace("_", " "))
        if display_slug == slug or key_slug == slug:
            tournament_markets.append(m)
            if not matched_key:
                matched_key = key

    if not tournament_markets:
        return None

    # Derive display name from the tournament key
    display_name = TOURNAMENT_DISPLAY_NAMES.get(matched_key or "", (matched_key or slug).replace("_", " ").title())
    key = matched_key or slug

    # Build the settled WINNER FIELD (#225 Items 1 & 2). Pure assembly extracted to
    # _assemble_completed_winner_field so the champion-crown + field-purge logic is
    # unit-tested independently of the DB.
    golfers, market_ids, market_names, market_sources = _assemble_completed_winner_field(
        tournament_markets
    )

    # Try to find schedule data from the golf API response (already cached)
    start_date = None
    end_date = None
    venue = None
    schedule_status = None
    try:
        golf_data = await get_golf(db=db)
        schedule = golf_data.get("pga_schedule", [])
        for event in schedule:
            # Match by multiple strategies: display name slug, key slug, or
            # normalized tournament key matching
            event_name = event.get("name", "")
            event_key = event.get("key", "")
            event_name_slug = _clean_slug(event_name)
            event_key_slug = _clean_slug(event_key.replace("_", " "))
            norm_key = _normalize_tournament(event_name)
            norm_display = TOURNAMENT_DISPLAY_NAMES.get(norm_key, "")
            norm_slug = _clean_slug(norm_display) if norm_display else ""

            if slug in (event_name_slug, event_key_slug, norm_slug):
                start_date = event.get("start_date")
                end_date = event.get("end_date")
                venue = event.get("venue") or event.get("course")
                schedule_status = event.get("status")
                break
    except Exception:
        pass

    return {
        "name": display_name,
        "slug": slug,
        "key": key,
        "is_major": any(k in key.lower() for k in ("masters", "pga_championship", "us_open", "the_open")),
        "is_womens": bool(re.search(r"women|lpga|chevron|amundi", display_name, re.I)),
        "start_date": start_date,
        "end_date": end_date,
        "venue": venue,
        "location": None,
        "schedule_status": schedule_status,
        "commence_time": start_date,
        "resolution_date": end_date,
        "golfers": golfers,
        "market_ids": market_ids,
        "market_names": market_names,
        # #225 Item 2: carry the settled tournament's sources so the round-leader
        # field-membership filter (apply_field_filter) activates — otherwise it
        # defaults off and Kalshi's speculative round-leader roster (Tiger Woods
        # et al., who never entered) surfaces on completed rounds.
        "market_sources": market_sources,
        "_all_golfers": golfers,
    }


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
        # Fallback: tournament may have completed and its markets closed.
        # Query closed/resolved markets directly to serve completed tournament data.
        tournament = await _build_completed_tournament(slug, db)
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
        type_key, label = _tournament_market_type(mname)
        if type_key not in market_groups:
            market_groups[type_key] = {
                "type": type_key,
                "label": label,
                "market_ids": [],
                "market_names": [],
            }
        market_groups[type_key]["market_ids"].append(mid)
        market_groups[type_key]["market_names"].append(mname)

    # Order: winner first, then top_5/10/20/40, make_cut, round_leader, other
    type_order = ["winner", "top_5", "top_10", "top_20", "top_40", "make_cut", "round_leader", "other"]
    sorted_groups = sorted(
        market_groups.values(),
        key=lambda g: type_order.index(g["type"]) if g["type"] in type_order else 99
    )

    # Find winner market for evolution chart — pick the one with the most
    # snapshot data (richest time coverage). Filter out non-golfer markets
    # like "League of Winner" or "Winner Nationality" by requiring >5 outcomes.
    evolution_market_id = None
    # #225 Item 3 — for a SETTLED tournament, the "Path to resolution" chart must
    # show the winner converging to ~100%. The snapshot-richest winner market for a
    # settled major is the long-lived odds_api futures market, which stops updating
    # before the finish (its winner line fizzles at ~18% and never resolves); a
    # real-money Kalshi market converges to 99.9%. So prefer the winner market whose
    # graded winner actually RESOLVED high; fall back to snapshot-richest when no
    # market carries a resolved winner (live/upcoming — no is_winner exists yet).
    resolved_best_id = None
    resolved_best_val = _SETTLED_RESOLVE_MIN
    for g in sorted_groups:
        if g["type"] == "winner" and g["market_ids"]:
            best_id = None
            best_count = -1
            for mid in g["market_ids"]:
                # #955: "Winner Nationality"/"Tour of Winner"/"Country of Winner"
                # classify as type "winner" (they contain "Winner") but are PROPS,
                # not golfer winner fields. The 26-outcome nationality market
                # passes the >5 filter and was plotted as the contenders chart
                # (US/England/Spain/Other). Exclude any non-winner prop by name.
                mname = id_to_name.get(mid, "")
                if _NON_CONTENDER_WINNER_RE.search(mname):
                    continue
                # Check outcome count to filter non-golfer markets
                outcome_count = await db.execute(
                    select(sqlfunc.count(FuturesOutcome.id))
                    .where(FuturesOutcome.market_id == mid)
                )
                n_outcomes = outcome_count.scalar() or 0
                if n_outcomes < 5:
                    continue  # Skip "League of Winner" (3 outcomes), Yes/No binaries, etc.
                snap_count = await db.execute(
                    select(sqlfunc.count(FuturesOddsSnapshot.id))
                    .where(FuturesOddsSnapshot.outcome_id.in_(
                        select(FuturesOutcome.id).where(FuturesOutcome.market_id == mid)
                    ))
                )
                total = snap_count.scalar() or 0
                if total > best_count:
                    best_count = total
                    best_id = mid
                # Settled preference: the graded winner's LATEST snapshot value —
                # i.e. did this market END with the winner resolved high and STAY
                # there. A real-money Kalshi market closes at ~0.999 for the
                # champion; the odds_api futures market fizzled (~18%) and the
                # DataGolf model RESETS to ~0.5% post-event (its momentary in-play
                # 1.0 spike would win a max()-based rank but leaves an ugly end-drop
                # on the chart). Ranking by the final value picks the market whose
                # completed journey actually stays at the top. Live/upcoming
                # tournaments carry no is_winner, so this stays None and the
                # snapshot-richest pick is used unchanged.
                gw = await db.execute(
                    select(FuturesOddsSnapshot.probability)
                    .where(
                        FuturesOddsSnapshot.outcome_id.in_(
                            select(FuturesOutcome.id).where(
                                FuturesOutcome.market_id == mid,
                                FuturesOutcome.is_winner.is_(True),
                            )
                        )
                    )
                    .order_by(FuturesOddsSnapshot.captured_at.desc())
                    .limit(1)
                )
                winner_resolve = gw.scalar()
                if winner_resolve is not None and float(winner_resolve) >= resolved_best_val:
                    resolved_best_val = float(winner_resolve)
                    resolved_best_id = mid
            # A resolved-winner market (settled) wins over snapshot-richness.
            evolution_market_id = resolved_best_id or best_id
            break
    if not evolution_market_id and market_ids:
        evolution_market_id = market_ids[0]

    # Filter movers for this tournament
    all_movers = golf_data.get("biggest_movers", [])
    tournament_movers = [
        m for m in all_movers
        if m.get("tournament_key") == tournament.get("key")
    ]

    # ------------------------------------------------------------------
    # Enrich golfers with Top 5/10/20/Make Cut probabilities from
    # non-winner markets so the grid shows placement odds pre-tournament.
    # ------------------------------------------------------------------
    golfers = tournament.get("_all_golfers", tournament.get("golfers", []))

    placement_market_ids: dict[str, list[int]] = {}  # type_key -> [market_ids]
    for g in sorted_groups:
        if g["type"] in ("top_5", "top_10", "top_20", "top_40", "make_cut", "round_leader"):
            placement_market_ids[g["type"]] = g["market_ids"]

    if placement_market_ids:
        # Collect all placement market IDs
        all_placement_ids = []
        for ids in placement_market_ids.values():
            all_placement_ids.extend(ids)

        # Query outcomes for these markets in one batch
        placement_result = await db.execute(
            select(FuturesOutcome)
            .where(
                FuturesOutcome.market_id.in_(all_placement_ids),
                FuturesOutcome.current_probability.isnot(None),
            )
        )
        placement_outcomes = placement_result.scalars().all()

        # Build market_id -> type_key lookup
        mid_to_type: dict[int, str] = {}
        for type_key, mids in placement_market_ids.items():
            for mid in mids:
                mid_to_type[mid] = type_key

        # market_id -> source, so placement probs can prefer DataGolf (#954).
        src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(all_placement_ids)
            )
        )
        mid_to_source: dict[int, str] = {row[0]: row[1] for row in src_result.all()}

        # Build match_key -> {type_key: probability} from placement outcomes.
        # DataGolf is the authoritative in-play model; a blind cross-source
        # average blended its well-differentiated make_cut (Scheffler 0.85,
        # Puig 0.40) with the one-sided Polymarket/Kalshi "To Make the Cut"
        # placeholders (compressed ~0.5), flattening Bubble Watch to ~50% for
        # everyone (#954). Prefer DataGolf when present; otherwise keep the
        # prior pairwise-average behavior across non-DataGolf sources.
        placement_probs: dict[str, dict[str, float]] = defaultdict(dict)
        _from_datagolf: dict[str, dict[str, bool]] = defaultdict(dict)
        for o in placement_outcomes:
            type_key = mid_to_type.get(o.market_id)
            if not type_key:
                continue
            key = _match_key(o.name)
            if not key:
                continue
            prob = float(o.current_probability)
            is_dg = mid_to_source.get(o.market_id) == "datagolf"
            val, val_dg = _prefer_datagolf_merge(
                placement_probs[key].get(type_key),
                _from_datagolf[key].get(type_key, False),
                prob,
                is_dg,
            )
            placement_probs[key][type_key] = val
            _from_datagolf[key][type_key] = val_dg

        # Merge into golfers
        for g in golfers:
            key = _match_key(g["name"])
            if key and key in placement_probs:
                probs = placement_probs[key]
                g["top_5_prob"] = round(probs["top_5"] * 100, 1) if "top_5" in probs else None
                g["top_10_prob"] = round(probs["top_10"] * 100, 1) if "top_10" in probs else None
                g["top_20_prob"] = round(probs["top_20"] * 100, 1) if "top_20" in probs else None
                g["top_40_prob"] = round(probs["top_40"] * 100, 1) if "top_40" in probs else None
                g["make_cut_prob"] = round(probs["make_cut"] * 100, 1) if "make_cut" in probs else None
                g["round_leader_prob"] = round(probs["round_leader"] * 100, 1) if "round_leader" in probs else None
                # Enforce cross-column monotonicity: Win <= Top5 <= Top10 <= Top20 <= Top40 <= MakeCut
                win = g.get("win_prob") or 0
                for col in ["top_5_prob", "top_10_prob", "top_20_prob", "top_40_prob", "make_cut_prob"]:
                    if g.get(col) is not None and g[col] < win:
                        g[col] = win
                    if g.get(col) is not None:
                        win = g[col]

    # ------------------------------------------------------------------
    # Round-scoped groups (#951 round_top + L2-89 round_leader).
    #   * "Round N Top M Finishers" (DataGolf projections, kind="top")
    #   * "End of Round N Leader" (first/second/third-round leader fields, kind="leader")
    # Both are excluded from the tournament placement grid (round-specific numbers
    # would corrupt the whole-tournament Top-N columns). round_top previously
    # surfaced only as bare ids; round_leader was collapsed into a single averaged
    # phantom `round_leader_prob` that NO surface renders (L2-89 gap). Expose both
    # per-market (round + kind + per-golfer outcomes) so the frontend renders a
    # dedicated per-round panel. Disambiguated by (round, kind, top_n) — no
    # grid-key collision.
    # ------------------------------------------------------------------
    round_top_groups: list[dict] = []
    # Last completed round (0 = none). Computed inside the round block from the
    # graded leaders; hoisted here so the related-futures build below can settle
    # round-scoped scoring props ("Round 1 Scores", "Round 2 Lowest Score") too.
    max_completed_round = 0
    rt_group = next((g for g in sorted_groups if g["type"] == "round_top"), None)
    rl_group = next((g for g in sorted_groups if g["type"] == "round_leader"), None)
    round_market_kinds: dict[int, str] = {}
    for mid in (rt_group or {}).get("market_ids", []):
        round_market_kinds[mid] = "top"
    for mid in (rl_group or {}).get("market_ids", []):
        round_market_kinds[mid] = "leader"
    if round_market_kinds:
        # ------------------------------------------------------------------
        # Field-membership guard (The Open 2026 p0 — the "Tiger Woods" bug).
        # Kalshi "End of Round N Leader" markets carry a ~165-name speculative
        # candidate roster that includes players who are NOT in the field —
        # past champions and celebrities (Tiger Woods, Phil Mickelson, John
        # Daly, Ernie Els) — each floated at a phantom ~0.30 with no opening.
        # The WINNER grid is already protected by the DataGolf invitee filter
        # (`_build_tournament_entry`, has_datagolf branch); the round groups
        # were NOT, so out-of-field names rendered as live round-leader
        # outcomes. `golfers` (== `_all_golfers`) is that same invitee-filtered
        # field, so its `_match_key` set is the authoritative roster. Only
        # trust the filter when DataGolf actually supplied the field (otherwise
        # `golfers` IS the padded source list and filtering is a safe no-op)
        # and the set is non-trivially sized. `_match_key` is the SAME name key
        # the placement-grid merge already uses to line Kalshi outcomes up with
        # DataGolf golfers, so field members key-match reliably.
        # ------------------------------------------------------------------
        has_authoritative_field = "datagolf" in (tournament.get("market_sources") or [])
        field_keys: set[str] = set()
        if has_authoritative_field:
            field_keys = {k for k in (_match_key(g.get("name", "")) for g in golfers) if k}
        apply_field_filter = has_authoritative_field and len(field_keys) >= 20

        rt_ids = list(round_market_kinds.keys())
        rt_out_result = await db.execute(
            select(FuturesOutcome).where(
                FuturesOutcome.market_id.in_(rt_ids),
                FuturesOutcome.current_probability.isnot(None),
            )
        )
        rt_by_market: dict[int, list] = defaultdict(list)
        for o in rt_out_result.scalars().all():
            rt_by_market[o.market_id].append(o)
        rt_src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(rt_ids)
            )
        )
        rt_src = {row[0]: row[1] for row in rt_src_result.all()}

        # Which rounds are OVER — derived from the data itself, no live call.
        # The highest graded-leader round is the last completed round; every
        # round <= it is over. Top-N projection markets carry NO is_winner, so
        # they can only be settled by this cross-market inference, not their own
        # grade. Round leaders self-settle via their own is_winner below.
        def _round_of(_mid: int) -> int | None:
            _m = re.search(r"Round\s+(\d+)", id_to_name.get(_mid, ""), re.I)
            return int(_m.group(1)) if _m else None

        max_completed_round = _completed_round_ceiling(
            [
                (
                    round_market_kinds.get(_mid, ""),
                    _round_of(_mid),
                    any(bool(_o.is_winner) for _o in _outs),
                )
                for _mid, _outs in rt_by_market.items()
            ]
        )

        for mid in rt_ids:
            outs = rt_by_market.get(mid)
            if not outs:
                continue  # false-positive-safe: never surface an empty group
            # Settled-means-settled. A round is done when it carries its own
            # graded winner (leader markets) OR its number is <= the last
            # completed round (Top-N projection markets, which never grade
            # themselves — inferred complete from the leaders). A done round must
            # never show live odds on an in-progress tournament: leaders render
            # WHAT HIT (the graded leader); Top-N projections have no single
            # gradeable winner, so the props body suppresses them.
            _mid_name = id_to_name.get(mid, "")
            _mid_round = _round_of(mid)
            graded_winner = next((o.name for o in outs if o.is_winner), None)
            round_is_over = _mid_round is not None and _mid_round <= max_completed_round
            settled = bool(graded_winner) or round_is_over
            # Drop out-of-field candidates (never the graded winner, which is
            # authoritative even if a name key somehow misses the roster).
            field_outs = [
                o for o in outs
                if _round_outcome_in_field(
                    o.name, bool(o.is_winner), field_keys, apply_field_filter
                )
            ]
            if not field_outs:
                continue  # whole group was out-of-field noise — surface nothing
            name = _mid_name
            kind = round_market_kinds[mid]
            rnd = _mid_round
            if kind == "top":
                tn_m = re.search(r"Top\s+(\d+)", name, re.I)
                top_n = int(tn_m.group(1)) if tn_m else None
                label = f"Top {top_n} Finishers" if top_n else "Top Finishers"
            else:
                top_n = None
                label = "Round Leader"
            outcomes = sorted(
                (
                    {
                        "name": o.name,
                        "probability": round(float(o.current_probability), 3),
                        # L2-121: opening probability = the pregame mark the concept
                        # page's PropsSection renders as THE SCRIPT (opening → current
                        # divergence). Already loaded on the ORM row (zero new query);
                        # None where the polling pipeline never captured an opening.
                        "opening_probability": (
                            round(float(o.opening_probability), 4)
                            if o.opening_probability is not None
                            else None
                        ),
                    }
                    for o in field_outs
                ),
                key=lambda x: x["probability"],
                reverse=True,
            )[:10]
            round_top_groups.append(
                {
                    "market_id": mid,
                    "market_name": name,
                    "round": rnd,
                    "top_n": top_n,
                    "kind": kind,
                    "label": label,
                    "source": "datagolf_model" if rt_src.get(mid) == "datagolf" else rt_src.get(mid, ""),
                    "outcomes": outcomes,
                    "settled": settled,
                    "graded_winner": graded_winner,
                }
            )
        # Within a round: leader field first, then Top-N ascending.
        round_top_groups.sort(
            key=lambda g: (
                g["round"] or 99,
                0 if g["kind"] == "leader" else 1,
                g["top_n"] or 99,
            )
        )

    # ------------------------------------------------------------------
    # Build "Related Futures" — tournament-specific markets NOT in the grid.
    # These are H2H matchups, nationality props, hole-in-one, bogey-free, etc.
    # ------------------------------------------------------------------
    other_group = next((g for g in sorted_groups if g["type"] == "other"), None)
    related_futures = []
    if other_group and other_group["market_ids"]:
        other_outcomes_result = await db.execute(
            select(FuturesOutcome)
            .options(selectinload(FuturesOutcome.market))
            .where(
                FuturesOutcome.market_id.in_(other_group["market_ids"]),
                FuturesOutcome.current_probability.isnot(None),
            )
            .order_by(FuturesOutcome.current_probability.desc())
        )
        other_outcomes = other_outcomes_result.scalars().all()

        # Group outcomes by market
        from collections import defaultdict as _defaultdict
        outcomes_by_market: dict[int, list] = _defaultdict(list)
        for o in other_outcomes:
            outcomes_by_market[o.market_id].append({
                "name": o.name,
                "probability": round(float(o.current_probability), 4) if o.current_probability else None,
                "american_odds": o.current_american_odds,
                "probability_change_24h": round(float(o.probability_change_24h), 4) if o.probability_change_24h else None,
                # L2-121: pregame mark for the concept page PropsSection (see round
                # groups above). Free — the ORM row is already loaded.
                "opening_probability": (
                    round(float(o.opening_probability), 4)
                    if o.opening_probability is not None
                    else None
                ),
            })

        # market_id -> source for cross-source dedup + per-card attribution (#956/#957).
        other_src_result = await db.execute(
            select(FuturesMarket.id, FuturesMarket.source).where(
                FuturesMarket.id.in_(other_group["market_ids"])
            )
        )
        other_mid_to_source: dict[int, str] = {r[0]: r[1] for r in other_src_result.all()}

        def _lead_prob(outcomes: list) -> float | None:
            """Representative probability for a card — the 'Yes' side of a binary
            question, else the top outcome (used for the cross-source comparison)."""
            for o in outcomes:
                if (o.get("name") or "").strip().lower() == "yes":
                    return o.get("probability")
            return outcomes[0]["probability"] if outcomes else None

        # #956: collapse cross-source duplicates (e.g. the two playoff cards) into
        # ONE card. Keep the highest-priority source's outcomes; expose every
        # source's probability under `sources` so the card can show "Poly 27% /
        # Kalshi 22%" instead of two stacked, disagreeing cards.
        grouped_related: dict[str, dict] = {}
        for mid in other_group["market_ids"]:
            if mid not in outcomes_by_market:
                continue
            mname = id_to_name.get(mid, "")
            # Settled-means-settled: a round-scoped scoring prop ("Round 1
            # Scores", "Round 2 Lowest Score") for a round that is already over
            # must not keep showing live odds. These are multi-winner fields /
            # ladders with no single gradeable result, so drop them entirely
            # (they'd otherwise render live in Props and Scoring & Records). The
            # live/future round ("End of Round 4 …") and tournament-wide records
            # ("Lowest Round Score") carry no completed-round match and survive.
            if _round_scoped_market_complete(mname, max_completed_round):
                continue
            src = other_mid_to_source.get(mid, "unknown")
            key = _related_dedup_key(mname)
            entry = {
                "market_id": mid,
                "market_name": mname,
                "source": src,
                "outcomes": outcomes_by_market[mid],
            }
            source_row = {
                "source": src,
                "market_id": mid,
                "probability": _lead_prob(outcomes_by_market[mid]),
            }
            existing = grouped_related.get(key)
            if existing is None:
                entry["sources"] = [source_row]
                grouped_related[key] = entry
            else:
                existing["sources"].append(source_row)
                # Keep the higher-priority source's card as the primary.
                cur_pri = _RELATED_SOURCE_PRIORITY.get(existing["source"], 99)
                new_pri = _RELATED_SOURCE_PRIORITY.get(src, 99)
                if new_pri < cur_pri:
                    sources = existing["sources"]
                    entry["sources"] = sources
                    grouped_related[key] = entry
        for entry in grouped_related.values():
            # Drop the single-source `sources` list when there's nothing to compare.
            if len(entry.get("sources", [])) <= 1:
                entry.pop("sources", None)
            related_futures.append(entry)

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
        "golfers": golfers,
        "markets": sorted_groups,
        "related_futures": related_futures,
        "evolution_market_id": evolution_market_id,
        "biggest_movers": tournament_movers,
        "h2h_matchups": tournament.get("h2h_matchups", []),
        "round_top_groups": round_top_groups,
    }


# ============================================================================
# Live leaderboard (ultra-low-data endpoint)
# ============================================================================

# In-process cache for leaderboard (avoid hammering DataGolf on every refresh)
_leaderboard_cache: dict[str, tuple[float, dict]] = {}
_LEADERBOARD_CACHE_TTL = 120  # 2 minutes


@router.get("/leaderboard/debug")
async def get_golf_leaderboard_debug():
    """Debug: return raw DataGolf in-play response to diagnose field names."""
    from app.services.datagolf_api import DataGolfAPIService
    service = DataGolfAPIService()
    try:
        data = await service._get("preds/in-play", {"tour": "pga"})
    except Exception as e:
        return {"error": str(e)}
    finally:
        await service.close()
    # Return raw response with first 3 player entries
    raw_players = data.get("data", [])
    return {
        "info": data.get("info", {}),
        "top_level_keys": sorted(data.keys()),
        "player_count": len(raw_players),
        "sample_players": raw_players[:3],
    }


@router.get("/leaderboard/{tour}")
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

    # Log score availability for debugging
    has_scores = sum(1 for p in players if p.total_score is not None)
    logger.info(
        "Leaderboard: %d players, %d with scores, event=%s, round=%s",
        len(players), has_scores, info.get("event_name"), info.get("current_round"),
    )

    # Sort by position (numeric sort, with CUT/WD at bottom)
    def _pos_sort_key(p):
        pos = (p.position or "999").lstrip("T")
        try:
            return int(pos)
        except ValueError:
            return 9999

    players.sort(key=_pos_sort_key)

    # ----------------------------------------------------------------
    # Load baseline for delta computation.
    # For Round 1, use pre-tournament odds from DataGolf FuturesOutcome
    # (more meaningful than the first in-play snapshot).
    # For subsequent rounds, use start-of-day leaderboard snapshot.
    # ----------------------------------------------------------------
    snapshot_lookup: dict[str, dict] = {}  # player_name -> {position, win_prob, ...}
    current_round = info.get("current_round")
    try:
        from app.models.models import GolfLeaderboardSnapshot
        from app.services.database import async_session_maker
        from sqlalchemy import select as sa_select
        from zoneinfo import ZoneInfo

        if current_round and current_round >= 2:
            # Rounds 2-4: use start-of-day leaderboard snapshot
            et_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
            today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)

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
        else:
            # Round 1: use last DataGolf snapshot from before today as baseline
            # (captures pre-tournament odds from close to midnight)
            et_now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
            today_start = et_now.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff = today_start.astimezone(timezone.utc)

            async with async_session_maker() as snap_session:
                # Find the DataGolf winner market for this tour
                dg_result = await snap_session.execute(
                    sa_select(FuturesMarket).where(
                        FuturesMarket.source == "datagolf",
                        FuturesMarket.external_id.like(f"datagolf:{tour}:%:win"),
                        FuturesMarket.status == "open",
                    )
                )
                dg_market = dg_result.scalar_one_or_none()
                if dg_market:
                    # Get outcome IDs for this market
                    out_result = await snap_session.execute(
                        sa_select(FuturesOutcome.id, FuturesOutcome.name).where(
                            FuturesOutcome.market_id == dg_market.id,
                        )
                    )
                    outcomes = out_result.all()
                    outcome_ids = [o.id for o in outcomes]
                    outcome_names = {o.id: o.name for o in outcomes}

                    if outcome_ids:
                        # Get the last snapshot per outcome before today
                        from sqlalchemy import func as sa_func
                        subq = (
                            sa_select(
                                FuturesOddsSnapshot.outcome_id,
                                sa_func.max(FuturesOddsSnapshot.captured_at).label("max_ts"),
                            )
                            .where(
                                FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
                                FuturesOddsSnapshot.captured_at < cutoff,
                            )
                            .group_by(FuturesOddsSnapshot.outcome_id)
                            .subquery()
                        )
                        snap_result = await snap_session.execute(
                            sa_select(FuturesOddsSnapshot).join(
                                subq,
                                (FuturesOddsSnapshot.outcome_id == subq.c.outcome_id)
                                & (FuturesOddsSnapshot.captured_at == subq.c.max_ts),
                            )
                        )
                        for snap in snap_result.scalars().all():
                            name = outcome_names.get(snap.outcome_id, "")
                            if name and snap.probability is not None:
                                wp = round(float(snap.probability) * 100, 1)
                                snapshot_lookup[name.lower()] = {"win_prob": wp}

                    logger.info("Leaderboard R1: loaded %d-player pre-round snapshot (cutoff=%s)",
                                len(snapshot_lookup), cutoff.isoformat())
    except Exception as e:
        logger.warning("Leaderboard: could not load baseline: %s", e)

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

    # Detect completed tournaments: if ALL players have win prob exactly 0 or 100,
    # the event is over — report "completed" instead of "live".
    win_probs = [entry["win_prob"] for entry in leaderboard if entry["win_prob"] is not None]
    is_completed = (
        win_probs
        and all(wp in (0.0, 100.0) for wp in win_probs)
    )

    result = {
        "status": "completed" if is_completed else "live",
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
