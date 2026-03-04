"""
Golf category landing page endpoint.

Aggregates futures market odds across Polymarket, Kalshi, and The Odds API for golf tournaments.
Groups by tournament, merges cross-source golfer odds, and computes biggest movers.
Enriches with PGA tour schedule from StatPal for accurate current-event detection.
"""

import logging
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
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
    r"championship|"
    r"classic|invitational|"
    r"ryder|presidents?\s+cup|"
    r"major|hole[-\s]in[-\s]one|"
    r"wgc|winner|"
    r"liv\s+golf|korn\s+ferry|"
    r"dp\s+world|sunshine\s+tour|"
    r"asian\s+tour|european\s+tour"
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

# Women's / LPGA detection
_WOMENS_RE = re.compile(r"\b(?:lpga|women'?s?|ladies)\b", re.I)

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
# StatPal PGA schedule cache
# ============================================================================

_golf_schedule_cache: dict = {"data": None, "ts": 0}
_GOLF_SCHEDULE_TTL = 3600  # 1 hour


async def _get_golf_schedule() -> list[dict]:
    """Fetch PGA tour schedule from StatPal with 1-hour in-process cache.

    Returns a list of tournament dicts with name, start/end dates, venue, status.
    Returns empty list if StatPal is unavailable.
    """
    now_ts = time.time()
    if _golf_schedule_cache["data"] is not None and (now_ts - _golf_schedule_cache["ts"]) < _GOLF_SCHEDULE_TTL:
        return _golf_schedule_cache["data"]

    from app.services.statpal_api import StatPalAPIService, is_available

    if not is_available():
        return []

    service = StatPalAPIService()
    try:
        # StatPal golf endpoint returns {"fixtures": {"tournament": [...]}}
        data = await service._get("pga", "schedule")
        if not data or not isinstance(data, dict):
            logger.info("StatPal PGA schedule: empty or invalid response")
            return []

        # Extract tournament items from the response
        items = service._extract_match_items(data)
        logger.info("StatPal PGA schedule: extracted %d tournament items", len(items))

        result = []
        for item in items:
            if not isinstance(item, dict):
                continue

            name = item.get("name", item.get("tournament", item.get("league", "")))
            if not name:
                continue

            # Parse dates — StatPal uses DD.MM.YYYY or YYYY-MM-DD
            start_str = item.get("date", item.get("start_date", ""))
            end_str = item.get("end_date", "")
            venue = item.get("venue", item.get("course", ""))
            status = (item.get("status", "") or "").lower()
            round_info = item.get("round", "")

            start_date = _parse_statpal_date(start_str)
            end_date = _parse_statpal_date(end_str)

            # Try to match to our tournament key
            tourn_key = _normalize_tournament(name)

            result.append({
                "name": name,
                "key": tourn_key,
                "start_date": start_date,
                "end_date": end_date,
                "venue": venue if isinstance(venue, str) else "",
                "status": status,
                "round": round_info if isinstance(round_info, str) else "",
            })

        _golf_schedule_cache["data"] = result
        _golf_schedule_cache["ts"] = now_ts
        return result

    except Exception as e:
        logger.warning("Failed to fetch golf schedule from StatPal: %s", e)
        return []
    finally:
        await service.close()


def _parse_statpal_date(date_str: str) -> str | None:
    """Parse a date string from StatPal (DD.MM.YYYY or YYYY-MM-DD) to ISO format."""
    if not date_str:
        return None
    # DD.MM.YYYY format
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", date_str)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}T00:00:00+00:00"
    # YYYY-MM-DD format
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", date_str)
    if m:
        return f"{date_str}T00:00:00+00:00"
    return None


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


def _match_key(name: str) -> str:
    """
    Create a matching key from a golfer name for cross-source dedup.

    Handles name variations across DataGolf, Polymarket, Kalshi, and Odds API:
    - DataGolf: "Scheffler, Scottie" → "scottie scheffler"
    - Polymarket: "Scottie Scheffler" → "scottie scheffler"
    - Kalshi: "Yes: Scottie Scheffler" → "scottie scheffler"
    - Odds API: "S. Scheffler" → "s scheffler"
    - Diacritics: "Skarsgård" → "skarsgard"
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
    return clean


def _normalize_tournament(market_name: str) -> str:
    """Extract tournament key from a market name. Returns 'other' if no match."""
    for pattern, key in _TOURNAMENT_PATTERNS:
        if pattern.search(market_name):
            # Exclude non-Open Championship events that match "open championship"
            if key == "the_open" and _NOT_THE_OPEN_RE.search(market_name):
                continue
            return key

    # Try to extract a specific tour event name (creates dynamic tournament sections)
    tour_event = _extract_tour_event(market_name)
    if tour_event:
        # Create a stable key from the tour event name
        key = re.sub(r"[^a-z0-9]+", "_", tour_event.lower()).strip("_")
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
    # Group markets by tournament and aggregate golfer odds
    # ========================================================================
    tournament_markets: dict[str, list] = defaultdict(list)

    for market in markets:
        tournament_key = _normalize_tournament(market.name)
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

        market_ids = []
        earliest_commence = None
        latest_resolution = None

        for market in tourn_markets:
            market_ids.append(market.id)
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

        # Sort by probability descending, cap at max
        golfers.sort(key=lambda g: g["probability"], reverse=True)
        golfers = golfers[:_MAX_GOLFERS]

        # Normalize probabilities so they sum to ~100%
        total_prob = sum(g["probability"] for g in golfers)
        if total_prob > 0:
            for g in golfers:
                g["probability"] = round(g["probability"] / total_prob, 3)
                g["american_odds"] = probability_to_american(g["probability"])
        else:
            for g in golfers:
                g["probability"] = round(g["probability"], 3)
                g["american_odds"] = probability_to_american(g["probability"])

        # Assign ranks
        for i, g in enumerate(golfers):
            g["rank"] = i + 1

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

        tournaments.append({
            "key": tourn_key,
            "name": display_name,
            "is_major": tourn_key in MAJOR_TOURNAMENTS,
            "is_tour_event": is_tour_event,
            "is_womens": is_womens,
            "order": order_idx,
            "sort_date": latest_resolution.isoformat() if is_tour_event and latest_resolution else None,
            "commence_time": earliest_commence.isoformat() if earliest_commence else None,
            "resolution_date": latest_resolution.isoformat() if latest_resolution else None,
            "market_ids": market_ids,
            "market_names": market_names,
            "golfers": golfers,
        })

    # Sort tournaments by order, then by resolution date for tour events
    tournaments.sort(key=lambda t: (t["order"], t.get("sort_date") or "9999"))
    # Remove internal sort fields from response
    for t in tournaments:
        del t["order"]
        t.pop("sort_date", None)

    # ========================================================================
    # StatPal PGA schedule — enrich with real tournament dates
    # ========================================================================
    schedule = await _get_golf_schedule()
    schedule_by_key: dict[str, dict] = {}
    for s_event in schedule:
        key = s_event.get("key", "other")
        if key != "other" and key not in schedule_by_key:
            schedule_by_key[key] = s_event

    # Enrich tournaments with schedule data
    for t in tournaments:
        sched = schedule_by_key.get(t["key"])
        if sched:
            t["venue"] = sched.get("venue") or None
            t["schedule_status"] = sched.get("status") or None
            if sched.get("start_date"):
                t["start_date"] = sched["start_date"]
            if sched.get("end_date"):
                t["end_date"] = sched["end_date"]

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
    # Current tour event — smart detection using StatPal dates + fallback
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


def _find_current_event(
    tournaments: list[dict],
    schedule_by_key: dict[str, dict],
    now: datetime,
) -> dict | None:
    """Find the current tour event using StatPal dates with fallback heuristics.

    Priority order:
    1. StatPal schedule: event whose start_date <= now <= end_date
    2. StatPal schedule: nearest upcoming event (start_date > now, within 7 days)
    3. Fallback: tour event with most sources/golfer data (highest activity)
    """
    tour_events = [t for t in tournaments if t.get("is_tour_event")]
    if not tour_events:
        return None

    now_str = now.isoformat()

    # Phase 1: Use StatPal schedule dates if available
    if schedule_by_key:
        # Find event currently in progress
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            end = sched.get("end_date")
            if start and end and start <= now_str <= end:
                return _build_current_event(t)

        # Find nearest upcoming event from schedule
        nearest = None
        nearest_start = None
        for t in tour_events:
            sched = schedule_by_key.get(t["key"])
            if not sched:
                continue
            start = sched.get("start_date")
            if start and start > now_str:
                try:
                    start_dt = datetime.fromisoformat(start)
                    if (start_dt - now).days <= 7:
                        if nearest_start is None or start < nearest_start:
                            nearest_start = start
                            nearest = t
                except (ValueError, TypeError):
                    continue
        if nearest:
            return _build_current_event(nearest)

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
        candidates.append((t, movers, total_movement, total_sources, proximity_days))

    if candidates:
        # Sort by: movers desc, total_movement desc, proximity asc, sources desc
        candidates.sort(key=lambda c: (-c[1], -c[2], c[4], -c[3]))
        return _build_current_event(candidates[0][0])

    return None


def _build_current_event(t: dict) -> dict:
    """Build the current_event response dict from a tournament.

    Sorts market_ids so "Winner" markets appear first — the frontend uses
    market_ids[0] for the EvolutionView chart, and Winner markets have the
    richest probability evolution data.
    """
    raw_ids = t.get("market_ids", [])
    raw_names = t.get("market_names", [])

    # Pair IDs with names and sort: Winner markets first, then others
    pairs = list(zip(raw_ids, raw_names)) if len(raw_ids) == len(raw_names) else [(mid, "") for mid in raw_ids]

    def _winner_sort_key(pair):
        _id, name = pair
        name_lower = name.lower()
        # Winner markets get priority 0, others get 1
        if "winner" in name_lower and "round" not in name_lower:
            return (0, _id)
        return (1, _id)

    pairs.sort(key=_winner_sort_key)
    sorted_ids = [p[0] for p in pairs]
    sorted_names = [p[1] for p in pairs]

    return {
        "key": t["key"],
        "name": t["name"],
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
