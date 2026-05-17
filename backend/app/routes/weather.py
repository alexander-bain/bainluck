"""Weather markets API endpoints.

Serves prediction-market weather data from Kalshi and Polymarket,
organized into featured markets, city temperature distributions,
rain forecasts, natural disaster events, climate dashboards, and wildcards.
"""

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Sequence

from fastapi import APIRouter, Depends
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import FuturesMarket, FuturesOutcome
from app.services import get_db

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Tag classification helpers
# ---------------------------------------------------------------------------

_TAG_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\brain\b", re.I), "Daily rain"),
    (re.compile(r"\bhurricane\b", re.I), "Hurricane"),
    (re.compile(r"\b(?:earthquake|quake)\b", re.I), "Seismic"),
    (re.compile(r"\btornado\b", re.I), "Tornado"),
    (re.compile(r"\b(?:temperature|°)\b", re.I), "Temperature"),
    (re.compile(r"\b(?:hottest|climate|CO2)\b", re.I), "Climate"),
    (re.compile(r"\b(?:volcano|solar|arctic)\b", re.I), "Wild card"),
]


def _derive_tag(name: str) -> str:
    """Derive a category tag from a market name."""
    for pat, tag in _TAG_PATTERNS:
        if pat.search(name):
            return tag
    return "Weather"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_closes(dt: datetime | None) -> str | None:
    """Format a resolution_date as 'Tue, Apr 21'."""
    if dt is None:
        return None
    return dt.strftime("%a, %b %d").replace(" 0", " ")


def _highest_prob(market: FuturesMarket) -> float:
    """Return the highest current_probability among a market's outcomes, as 0-100 int."""
    best = 0.0
    for o in market.outcomes:
        p = float(o.current_probability or 0)
        if p > best:
            best = p
    return round(best * 100)


def _market_source(market: FuturesMarket) -> str:
    """Return normalized source string."""
    return (market.source or "").lower()


# ---------------------------------------------------------------------------
# Shared base query
# ---------------------------------------------------------------------------

def _open_weather_query():
    """Return a base select for open weather markets with outcomes eagerly loaded."""
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=7)
    return (
        select(FuturesMarket)
        .options(selectinload(FuturesMarket.outcomes))
        .where(
            FuturesMarket.llm_sport_category == "weather",
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.resolution_date.is_(None),
                FuturesMarket.resolution_date >= now - timedelta(hours=6),
            ),
            FuturesMarket.updated_at >= stale_cutoff,
        )
    )


# ---------------------------------------------------------------------------
# City coordinate lookup (visual positions for map, not lat/lng)
# ---------------------------------------------------------------------------

CITY_COORDS: dict[str, dict] = {
    # Americas
    "nyc": {"name": "New York", "region": "Americas", "x": 30.8, "y": 41},
    "la": {"name": "Los Angeles", "region": "Americas", "x": 18.8, "y": 45.4},
    "miami": {"name": "Miami", "region": "Americas", "x": 31.2, "y": 51},
    "chicago": {"name": "Chicago", "region": "Americas", "x": 26, "y": 38},
    "sf": {"name": "San Francisco", "region": "Americas", "x": 16.5, "y": 42},
    "dallas": {"name": "Dallas", "region": "Americas", "x": 24.5, "y": 47},
    "toronto": {"name": "Toronto", "region": "Americas", "x": 29, "y": 37},
    "mexico_city": {"name": "Mexico City", "region": "Americas", "x": 22.6, "y": 53},
    "sao_paulo": {"name": "São Paulo", "region": "Americas", "x": 35, "y": 67},
    "buenos_aires": {"name": "Buenos Aires", "region": "Americas", "x": 33, "y": 74},
    "boston": {"name": "Boston", "region": "Americas", "x": 32, "y": 38},
    "atlanta": {"name": "Atlanta", "region": "Americas", "x": 28, "y": 47},
    "houston": {"name": "Houston", "region": "Americas", "x": 24, "y": 51},
    "denver": {"name": "Denver", "region": "Americas", "x": 21, "y": 42},
    "seattle": {"name": "Seattle", "region": "Americas", "x": 17, "y": 34},
    "phoenix": {"name": "Phoenix", "region": "Americas", "x": 19.5, "y": 47},
    "minneapolis": {"name": "Minneapolis", "region": "Americas", "x": 24, "y": 36},
    "philadelphia": {"name": "Philadelphia", "region": "Americas", "x": 31, "y": 40},
    "las_vegas": {"name": "Las Vegas", "region": "Americas", "x": 19, "y": 45},
    "okc": {"name": "Oklahoma City", "region": "Americas", "x": 23.5, "y": 45},
    "san_antonio": {"name": "San Antonio", "region": "Americas", "x": 23, "y": 50},
    "new_orleans": {"name": "New Orleans", "region": "Americas", "x": 26, "y": 50},
    "dc": {"name": "Washington DC", "region": "Americas", "x": 30.5, "y": 42},
    "austin": {"name": "Austin", "region": "Americas", "x": 23.5, "y": 49},
    "panama_city": {"name": "Panama City", "region": "Americas", "x": 26.5, "y": 55},
    # Europe
    "london": {"name": "London", "region": "Europe", "x": 49, "y": 33},
    "paris": {"name": "Paris", "region": "Europe", "x": 50, "y": 34},
    "madrid": {"name": "Madrid", "region": "Europe", "x": 48, "y": 38},
    "munich": {"name": "Munich", "region": "Europe", "x": 52, "y": 33},
    "moscow": {"name": "Moscow", "region": "Europe", "x": 57, "y": 28},
    "istanbul": {"name": "Istanbul", "region": "Europe", "x": 55, "y": 39},
    "amsterdam": {"name": "Amsterdam", "region": "Europe", "x": 50.5, "y": 31},
    "helsinki": {"name": "Helsinki", "region": "Europe", "x": 54, "y": 26},
    "ankara": {"name": "Ankara", "region": "Europe", "x": 56, "y": 41},
    "warsaw": {"name": "Warsaw", "region": "Europe", "x": 53, "y": 30},
    "milan": {"name": "Milan", "region": "Europe", "x": 51, "y": 36},
    # Asia
    "tokyo": {"name": "Tokyo", "region": "Asia", "x": 83, "y": 39},
    "seoul": {"name": "Seoul", "region": "Asia", "x": 81, "y": 38},
    "beijing": {"name": "Beijing", "region": "Asia", "x": 78, "y": 37},
    "shanghai": {"name": "Shanghai", "region": "Asia", "x": 80, "y": 42},
    "hong_kong": {"name": "Hong Kong", "region": "Asia", "x": 79, "y": 49},
    "singapore": {"name": "Singapore", "region": "Asia", "x": 77, "y": 58},
    "lucknow": {"name": "Lucknow", "region": "Asia", "x": 71, "y": 48},
    "manila": {"name": "Manila", "region": "Asia", "x": 83, "y": 54},
    "jakarta": {"name": "Jakarta", "region": "Asia", "x": 79, "y": 60},
    "karachi": {"name": "Karachi", "region": "Asia", "x": 69, "y": 49},
    "tel_aviv": {"name": "Tel Aviv", "region": "Asia", "x": 57, "y": 44},
    "jeddah": {"name": "Jeddah", "region": "Asia", "x": 59, "y": 51},
    "busan": {"name": "Busan", "region": "Asia", "x": 82, "y": 40},
    "shenzhen": {"name": "Shenzhen", "region": "Asia", "x": 79, "y": 51},
    "kuala_lumpur": {"name": "Kuala Lumpur", "region": "Asia", "x": 77, "y": 56},
    "taipei": {"name": "Taipei", "region": "Asia", "x": 81, "y": 48},
    "chengdu": {"name": "Chengdu", "region": "Asia", "x": 76, "y": 44},
    "chongqing": {"name": "Chongqing", "region": "Asia", "x": 77, "y": 45},
    "wuhan": {"name": "Wuhan", "region": "Asia", "x": 78, "y": 44},
    # Africa
    "cape_town": {"name": "Cape Town", "region": "Africa", "x": 52, "y": 71},
    "lagos": {"name": "Lagos", "region": "Africa", "x": 50, "y": 57},
    # Oceania
    "wellington": {"name": "Wellington", "region": "Oceania", "x": 92.5, "y": 76},
}

_CITY_ALIASES: dict[str, str] = {
    "new york": "nyc", "nyc": "nyc", "new york city": "nyc",
    "los angeles": "la", "la": "la",
    "miami": "miami", "chicago": "chicago",
    "san francisco": "sf", "dallas": "dallas",
    "toronto": "toronto", "mexico city": "mexico_city",
    "são paulo": "sao_paulo", "sao paulo": "sao_paulo",
    "buenos aires": "buenos_aires",
    "boston": "boston", "atlanta": "atlanta",
    "houston": "houston", "denver": "denver",
    "seattle": "seattle", "phoenix": "phoenix",
    "minneapolis": "minneapolis", "philadelphia": "philadelphia",
    "las vegas": "las_vegas",
    "oklahoma city": "okc", "san antonio": "san_antonio",
    "new orleans": "new_orleans",
    "washington": "dc", "washington dc": "dc",
    "austin": "austin", "panama city": "panama_city",
    "london": "london", "paris": "paris",
    "madrid": "madrid", "munich": "munich",
    "moscow": "moscow", "istanbul": "istanbul",
    "amsterdam": "amsterdam", "helsinki": "helsinki",
    "ankara": "ankara", "warsaw": "warsaw", "milan": "milan",
    "tokyo": "tokyo", "seoul": "seoul",
    "beijing": "beijing", "shanghai": "shanghai",
    "hong kong": "hong_kong", "singapore": "singapore",
    "lucknow": "lucknow", "manila": "manila",
    "jakarta": "jakarta", "karachi": "karachi",
    "tel aviv": "tel_aviv", "jeddah": "jeddah",
    "busan": "busan", "shenzhen": "shenzhen",
    "kuala lumpur": "kuala_lumpur", "taipei": "taipei",
    "chengdu": "chengdu", "chongqing": "chongqing",
    "wuhan": "wuhan",
    "cape town": "cape_town", "lagos": "lagos",
    "wellington": "wellington",
}

_FAHRENHEIT_CITIES = {
    "nyc", "la", "miami", "chicago", "sf", "dallas", "boston", "atlanta",
    "houston", "denver", "seattle", "phoenix", "minneapolis", "philadelphia",
    "las_vegas", "okc", "san_antonio", "new_orleans", "dc", "austin",
}

# Temperature market name patterns
_TEMP_MARKET_RE = re.compile(
    r"(?:highest\s+temperature\s+in|temperature\s+(?:on|in|at))\s+(.+?)(?:\s+on\s+|\s+in\s+)",
    re.I,
)


def _resolve_city(name: str) -> str | None:
    """Try to extract and resolve a city name from a market name to a canonical city id."""
    name_lower = name.lower()
    # Direct alias match
    for alias, city_id in _CITY_ALIASES.items():
        if alias in name_lower:
            return city_id
    return None


# ---------------------------------------------------------------------------
# Rain helpers
# ---------------------------------------------------------------------------

def _rain_icon(prob: int) -> str:
    """Return an icon based on rain probability."""
    if prob >= 100:
        return "\u2614"   # ☔
    if prob >= 65:
        return "\U0001F327"  # 🌧️
    if prob >= 35:
        return "\u26C5"   # ⛅
    return "\u2600\uFE0F"  # ☀️


# ---------------------------------------------------------------------------
# Natural event keywords
# ---------------------------------------------------------------------------

_HURRICANE_RE = re.compile(r"\bhurricane\b", re.I)
_EARTHQUAKE_RE = re.compile(r"\b(?:earthquake|quake)\b", re.I)
_TORNADO_RE = re.compile(r"\btornado(?:es)?\b", re.I)

# ---------------------------------------------------------------------------
# Climate keywords
# ---------------------------------------------------------------------------

_CLIMATE_RE = re.compile(
    r"\b(?:hottest|climate|CO2|EV|2030|2050)\b", re.I,
)

# Wildcard keywords
_WILDCARD_RE = re.compile(
    r"\b(?:volcano|supervolcano|arctic|solar)\b", re.I,
)


# ---------------------------------------------------------------------------
# Cross-source matching — find markets on both Kalshi & Polymarket
# ---------------------------------------------------------------------------

_GARBAGE_OUTCOME_RE = re.compile(
    r"^(?:player|person|candidate|option|party)\s+[A-Z]{1,3}$", re.I
)


def _clean_outcomes(outcomes: list) -> list:
    """Filter garbage placeholder outcomes."""
    return [o for o in outcomes if not _GARBAGE_OUTCOME_RE.match(o.name or "")]


def _is_resolved(market: FuturesMarket) -> bool:
    """A market is effectively resolved if the top outcome is >= 99%."""
    for o in market.outcomes:
        if float(o.current_probability or 0) >= 0.99:
            return True
    return False


def _normalize_q(q: str) -> str:
    """Normalize a question for cross-source matching."""
    return re.sub(r"[^a-z0-9 ]+", "", q.lower()).strip()


def _cross_source_row(market: FuturesMarket) -> dict | None:
    """Build a market row suitable for cross-source comparison."""
    outcomes = _clean_outcomes(list(market.outcomes))
    outcomes = sorted(
        outcomes, key=lambda o: float(o.current_probability or 0), reverse=True
    )
    if not outcomes:
        return None
    top = outcomes[:3]
    return {
        "q": market.name,
        "prob": round(float(outcomes[0].current_probability or 0) * 100, 1),
        "src": _market_source(market),
        "market_id": market.id,
        "tag": _derive_tag(market.name or ""),
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
            }
            for o in top
        ],
        "outcome_count": len(outcomes),
    }


def _find_cross_source(
    all_markets: Sequence[FuturesMarket],
) -> list[dict]:
    """Find markets that exist on both platforms, ranked by disagreement."""
    by_norm: dict[str, dict[str, dict]] = defaultdict(dict)

    for m in all_markets:
        if _is_resolved(m):
            continue
        row = _cross_source_row(m)
        if not row:
            continue
        if row["outcome_count"] <= 2 and row["prob"] > 95:
            continue
        src = _market_source(m)
        if src not in ("kalshi", "polymarket"):
            continue
        norm = _normalize_q(row["q"])
        if norm and src not in by_norm[norm]:
            by_norm[norm][src] = row

    matches = []
    for norm, sources in by_norm.items():
        if "kalshi" not in sources or "polymarket" not in sources:
            continue
        k = sources["kalshi"]
        p = sources["polymarket"]
        delta = round(abs(k["prob"] - p["prob"]), 1)
        matches.append({
            "q": k["q"],
            "kalshi": k["prob"],
            "poly": p["prob"],
            "delta": delta,
            "category": k["tag"],
            "kalshi_market_id": k["market_id"],
            "poly_market_id": p["market_id"],
        })

    matches.sort(key=lambda x: -x["delta"])
    return matches[:8]


# ============================================================================
# 0. Cross-source endpoint
# ============================================================================

@router.get("/cross-source")
async def get_cross_source(db: AsyncSession = Depends(get_db)):
    """Return weather markets that appear on both Kalshi and Polymarket."""
    result = await db.execute(_open_weather_query())
    all_markets: list[FuturesMarket] = list(result.scalars().unique().all())
    return _find_cross_source(all_markets)


# ============================================================================
# 1. Featured markets
# ============================================================================

@router.get("/featured")
async def get_featured(db: AsyncSession = Depends(get_db)):
    """Return top 5 weather markets suitable for hero rotation."""
    query = _open_weather_query()
    result = await db.execute(query)
    markets: list[FuturesMarket] = list(result.scalars().all())

    # Score markets for "featured-ness":
    # - has outcomes
    # - proximity to resolution_date (sooner = higher)
    # - more outcomes = more interesting
    now = datetime.now(timezone.utc)
    scored: list[tuple[float, FuturesMarket]] = []
    for m in markets:
        if not m.outcomes:
            continue
        if m.resolution_date:
            days = (m.resolution_date - now).total_seconds() / 86400
            if days < 0.5:
                continue
        else:
            days = 365
        score = len(m.outcomes) / days
        scored.append((score, m))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:5]

    items = []
    for _score, m in top:
        items.append({
            "q": m.name,
            "prob": _highest_prob(m),
            "src": _market_source(m),
            "tag": _derive_tag(m.name),
            "closes": _format_closes(m.resolution_date),
            "market_id": m.id,
        })
    return items


# ============================================================================
# 2. City temperature distributions
# ============================================================================

@router.get("/cities")
async def get_cities(db: AsyncSession = Depends(get_db)):
    """Return temperature distribution data grouped by city."""
    query = _open_weather_query().where(
        or_(
            FuturesMarket.name.ilike("Highest temperature in%"),
            FuturesMarket.name.ilike("Lowest temperature in%"),
            FuturesMarket.name.ilike("Highest temperature in%on%"),
        )
    )
    result = await db.execute(query)
    markets: list[FuturesMarket] = list(result.scalars().all())

    # Group markets by city; for each city, keep the latest resolution_date market
    city_markets: dict[str, list[FuturesMarket]] = defaultdict(list)
    for m in markets:
        city_id = _resolve_city(m.name)
        if city_id:
            city_markets[city_id].append(m)

    cities = []
    for city_id, mkts in city_markets.items():
        info = CITY_COORDS.get(city_id)
        if not info:
            continue

        # For cross-source cities, prefer the market with MORE outcomes
        # (Polymarket has 11 buckets, Kalshi has 6 — finer grain is better).
        # Among same-outcome-count markets, prefer latest date.
        mkts_with_outcomes = [m for m in mkts if m.outcomes and m.resolution_date]
        if not mkts_with_outcomes:
            continue
        mkts_with_outcomes.sort(
            key=lambda m: (len(m.outcomes), m.resolution_date),  # type: ignore[arg-type]
            reverse=True,
        )
        chosen = mkts_with_outcomes[0]

        if not chosen.outcomes:
            continue

        dist = []
        mode_prob = 0.0
        mode_label = ""
        sources = set()
        sources.add(_market_source(chosen))

        for o in chosen.outcomes:
            p = round(float(o.current_probability or 0) * 100)
            sort_key = _extract_sort_temp(o.name)
            dist.append({"label": o.name, "prob": p, "_sort": sort_key})
            if float(o.current_probability or 0) > mode_prob:
                mode_prob = float(o.current_probability or 0)
                mode_label = o.name

        dist.sort(key=lambda d: d["_sort"])
        for d in dist:
            del d["_sort"]

        # Extract numeric mode value from label (e.g., "50-55°F" -> 52.5)
        mode_val = _extract_mode_value(mode_label)
        expected_unit = "F" if city_id in _FAHRENHEIT_CITIES else "C"

        # Detect actual unit from outcome labels — Polymarket markets may use
        # Celsius for cities where we expect Fahrenheit
        all_labels = " ".join(o.name for o in chosen.outcomes)
        data_is_celsius = bool(re.search(r"°C\b|degrees?\s*C\b|celsius", all_labels, re.I))
        data_is_fahrenheit = bool(re.search(r"°F\b|degrees?\s*F\b|fahrenheit", all_labels, re.I))

        if expected_unit == "F" and data_is_celsius and not data_is_fahrenheit:
            if mode_val is not None:
                mode_val = round(mode_val * 9 / 5 + 32, 1)
        elif expected_unit == "C" and data_is_fahrenheit and not data_is_celsius:
            if mode_val is not None:
                mode_val = round((mode_val - 32) * 5 / 9, 1)

        # Heuristic fallback: if no unit marker in labels and value is
        # implausibly low for Fahrenheit (< 40 in a warm US city in spring/summer),
        # likely Celsius data
        if expected_unit == "F" and not data_is_celsius and not data_is_fahrenheit:
            if mode_val is not None and mode_val < 40 and city_id in ("la", "miami", "phoenix", "houston", "dallas", "austin", "san_antonio"):
                mode_val = round(mode_val * 9 / 5 + 32, 1)

        unit = expected_unit

        # Collect sources from all markets for this city
        for m in mkts:
            sources.add(_market_source(m))

        cities.append({
            "id": city_id,
            "name": info["name"],
            "region": info["region"],
            "preferredX": info["x"],
            "preferredY": info["y"],
            "x": info["x"],
            "y": info["y"],
            "srcs": sorted(sources),
            "marketId": chosen.id,
            "high": {
                "unit": unit,
                "mode": mode_val,
                "dist": dist,
            },
        })

    return cities


def _extract_sort_temp(label: str) -> float:
    """Extract a numeric temperature for sorting outcome buckets low→high.

    'or below' / '<' labels get a low sort key; 'or above' / '+' get a high one.
    """
    if re.search(r"or below|or lower|<", label, re.I):
        m = re.search(r"(\d+(?:\.\d+)?)", label)
        return float(m.group(1)) - 100 if m else -999
    if re.search(r"or above|or higher|\+|≥", label, re.I):
        m = re.search(r"(\d+(?:\.\d+)?)", label)
        return float(m.group(1)) + 100 if m else 999
    m = re.search(r"(\d+(?:\.\d+)?)", label)
    return float(m.group(1)) if m else 0


def _extract_mode_value(label: str) -> float | None:
    """Extract a numeric temperature from an outcome label.

    Handles patterns like:
    - "50-55°F" -> 52.5
    - "<45°F" -> 45.0
    - ">=70°F" -> 70.0
    - "55°F or higher" -> 55.0
    """
    # Range pattern: "50-55"
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", label)
    if m:
        return (float(m.group(1)) + float(m.group(2))) / 2

    # Single number
    m = re.search(r"(\d+(?:\.\d+)?)", label)
    if m:
        return float(m.group(1))

    return None


# ============================================================================
# 3. Rain data
# ============================================================================

@router.get("/rain")
async def get_rain(db: AsyncSession = Depends(get_db)):
    """Return NYC 7-day rain forecast and monthly city rain data."""
    # --- Daily NYC rain ---
    daily_query = _open_weather_query().where(
        FuturesMarket.name.ilike("Will it rain in NYC on%"),
    ).order_by(FuturesMarket.resolution_date.asc())

    daily_result = await db.execute(daily_query)
    daily_markets: list[FuturesMarket] = list(daily_result.scalars().all())

    daily_rain = []
    for m in daily_markets:
        if not m.resolution_date:
            continue
        # Get the "Yes" outcome probability
        prob = _get_yes_probability(m)
        dt = m.resolution_date
        daily_rain.append({
            "day": dt.strftime("%a"),
            "date": dt.strftime("%b %d").replace(" 0", " "),
            "prob": prob,
            "icon": _rain_icon(prob),
        })

    # --- Monthly city rain ---
    monthly_query = _open_weather_query().where(
        FuturesMarket.name.ilike("Rain in%in%"),
    )
    monthly_result = await db.execute(monthly_query)
    monthly_markets: list[FuturesMarket] = list(monthly_result.scalars().all())

    # Dedup by city — keep the market with the latest resolution date per city
    city_best: dict[str, tuple] = {}  # city -> (resolution_date, market)
    for m in monthly_markets:
        city_match = re.search(r"Rain in (.+?) in \w+ \d{4}", m.name, re.I)
        city_name = city_match.group(1).strip() if city_match else m.name
        res_date = m.resolution_date
        existing = city_best.get(city_name)
        if not existing or (res_date and (not existing[0] or res_date > existing[0])):
            city_best[city_name] = (res_date, m)

    monthly_rain = []
    for city_name, (_, m) in city_best.items():
        prob = _get_yes_probability(m)
        delta = 0
        best_prob = 0.0
        for o in m.outcomes:
            p = float(o.current_probability or 0)
            if p > best_prob:
                best_prob = p
                if o.probability_change_24h is not None:
                    delta = round(float(o.probability_change_24h) * 100)
                else:
                    delta = 0

        monthly_rain.append({
            "city": city_name,
            "prob": prob,
            "src": _market_source(m),
            "delta24h": delta,
        })

    monthly_rain.sort(key=lambda x: x["prob"], reverse=True)

    return {
        "daily": daily_rain,
        "monthly": monthly_rain,
    }


def _get_yes_probability(market: FuturesMarket) -> int:
    """Extract the 'Yes' outcome probability from a binary market.

    For binary markets (will it rain?), return the Yes probability.
    Falls back to highest probability outcome if no 'Yes' found.
    """
    for o in market.outcomes:
        if o.name and o.name.lower() in ("yes", "y"):
            return round(float(o.current_probability or 0) * 100)
    # Fallback: use highest probability
    return _highest_prob(market)


# ============================================================================
# 4. Natural events
# ============================================================================

@router.get("/events")
async def get_events(db: AsyncSession = Depends(get_db)):
    """Return natural disaster/event markets grouped by type."""
    query = _open_weather_query().where(
        or_(
            FuturesMarket.name.ilike("%hurricane%"),
            FuturesMarket.name.ilike("%earthquake%"),
            FuturesMarket.name.ilike("%quake%"),
            FuturesMarket.name.ilike("%tornado%"),
        )
    )
    result = await db.execute(query)
    markets: list[FuturesMarket] = list(result.scalars().all())

    groups: dict[str, list] = {
        "hurricane": [],
        "earthquake": [],
        "tornadoes": [],
    }

    for m in markets:
        item = {
            "q": m.name,
            "prob": _highest_prob(m),
            "src": _market_source(m),
            "closes": _format_closes(m.resolution_date),
            "_res_date": m.resolution_date,
        }
        name = m.name
        if _HURRICANE_RE.search(name):
            groups["hurricane"].append(item)
        elif _EARTHQUAKE_RE.search(name):
            groups["earthquake"].append(item)
        elif _TORNADO_RE.search(name):
            groups["tornadoes"].append(item)

    # Sort: tornadoes chronologically, others by probability
    groups["tornadoes"].sort(key=lambda x: x.get("_res_date") or datetime.max)
    groups["hurricane"].sort(key=lambda x: x["prob"], reverse=True)
    groups["earthquake"].sort(key=lambda x: x["prob"], reverse=True)

    # Remove internal sort key
    for group in groups.values():
        for item in group:
            item.pop("_res_date", None)

    return groups


# ============================================================================
# 5. Climate dashboard
# ============================================================================

@router.get("/climate")
async def get_climate(db: AsyncSession = Depends(get_db)):
    """Return long-range climate markets with time scale classification."""
    now = datetime.now(timezone.utc)
    six_months_out = now.replace(
        year=now.year if now.month <= 6 else now.year + 1,
        month=(now.month + 6 - 1) % 12 + 1,
    )

    query = _open_weather_query().where(
        or_(
            # Long resolution date
            FuturesMarket.resolution_date >= six_months_out,
            # Or climate keywords regardless of date
            FuturesMarket.name.ilike("%hottest%"),
            FuturesMarket.name.ilike("%climate%"),
            FuturesMarket.name.ilike("%CO2%"),
            FuturesMarket.name.ilike("%EV %"),
            FuturesMarket.name.ilike("%2030%"),
            FuturesMarket.name.ilike("%2050%"),
        )
    )
    result = await db.execute(query)
    markets: list[FuturesMarket] = list(result.scalars().all())

    _EXCLUDE_RE = re.compile(
        r"\b(?:Ifo|temperature|rain |snow |daily)\b",
        re.I,
    )

    seen_names: set[str] = set()
    items = []
    for m in markets:
        if not m.outcomes:
            continue
        if _EXCLUDE_RE.search(m.name):
            continue
        dedup_key = m.name.lower().strip()
        if dedup_key in seen_names:
            continue
        seen_names.add(dedup_key)
        scale = _classify_scale(m)
        items.append({
            "q": m.name,
            "prob": _highest_prob(m),
            "src": _market_source(m),
            "closes": _format_closes(m.resolution_date),
            "scale": scale,
        })

    # Sort: current year first, then by date
    scale_order = {"2026": 0, "2030": 1, "2050": 2}
    items.sort(key=lambda x: (scale_order.get(x["scale"], 99), x["closes"] or ""))

    return items


def _classify_scale(market: FuturesMarket) -> str:
    """Classify a climate market into a time scale bucket."""
    name = market.name
    if re.search(r"\b2050\b", name):
        return "2050"
    if re.search(r"\b20(?:3[0-9]|40)\b", name):
        return "2030"
    # Check resolution date
    if market.resolution_date:
        year = market.resolution_date.year
        if year >= 2050:
            return "2050"
        if year >= 2030:
            return "2030"
    return "2026"


# ============================================================================
# 6. Wildcards
# ============================================================================

@router.get("/wildcards")
async def get_wildcards(db: AsyncSession = Depends(get_db)):
    """Return rare/dramatic weather markets (volcano, arctic, solar, etc.)."""
    query = _open_weather_query().where(
        or_(
            FuturesMarket.name.ilike("%volcano%"),
            FuturesMarket.name.ilike("%supervolcano%"),
            FuturesMarket.name.ilike("%arctic%"),
            FuturesMarket.name.ilike("%solar%"),
        )
    )
    result = await db.execute(query)
    markets: list[FuturesMarket] = list(result.scalars().all())

    items = []
    for m in markets:
        if not m.outcomes:
            continue
        items.append({
            "q": m.name,
            "prob": _highest_prob(m),
            "src": _market_source(m),
            "closes": _format_closes(m.resolution_date),
            "tag": _derive_tag(m.name),
        })

    items.sort(key=lambda x: x["prob"], reverse=True)
    return items
