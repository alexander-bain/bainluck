"""
Championship progression grid endpoint.

GET /api/playoffs/{league_slug} returns a grid of teams × playoff stages,
with multi-source probability merging, 24h movers, and trend chart data.
"""

import logging
import os
import re
import statistics
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.league_configs import LeagueConfig, get_league_config, get_all_league_slugs
from app.models import FuturesMarket, FuturesOutcome, FuturesOddsSnapshot, Team
from app.services import get_db
from app.utils.tournament_stages import classify_market_stage, get_stages_for_sport

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Static conference/division fallback maps
# Used when a team's standings_data doesn't have conference info.
# ---------------------------------------------------------------------------

NBA_CONFERENCES: dict[str, str] = {
    # Eastern Conference
    "Atlanta Hawks": "Eastern", "Boston Celtics": "Eastern", "Brooklyn Nets": "Eastern",
    "Charlotte Hornets": "Eastern", "Chicago Bulls": "Eastern", "Cleveland Cavaliers": "Eastern",
    "Detroit Pistons": "Eastern", "Indiana Pacers": "Eastern", "Miami Heat": "Eastern",
    "Milwaukee Bucks": "Eastern", "New York Knicks": "Eastern", "Orlando Magic": "Eastern",
    "Philadelphia 76ers": "Eastern", "Toronto Raptors": "Eastern", "Washington Wizards": "Eastern",
    # Western Conference
    "Dallas Mavericks": "Western", "Denver Nuggets": "Western", "Golden State Warriors": "Western",
    "Houston Rockets": "Western", "Los Angeles Clippers": "Western", "Los Angeles Lakers": "Western",
    "Memphis Grizzlies": "Western", "Minnesota Timberwolves": "Western",
    "New Orleans Pelicans": "Western", "Oklahoma City Thunder": "Western",
    "Phoenix Suns": "Western", "Portland Trail Blazers": "Western",
    "Sacramento Kings": "Western", "San Antonio Spurs": "Western", "Utah Jazz": "Western",
}

NFL_CONFERENCES: dict[str, str] = {
    # AFC
    "Baltimore Ravens": "AFC", "Buffalo Bills": "AFC", "Cincinnati Bengals": "AFC",
    "Cleveland Browns": "AFC", "Denver Broncos": "AFC", "Houston Texans": "AFC",
    "Indianapolis Colts": "AFC", "Jacksonville Jaguars": "AFC", "Kansas City Chiefs": "AFC",
    "Las Vegas Raiders": "AFC", "Los Angeles Chargers": "AFC", "Miami Dolphins": "AFC",
    "New England Patriots": "AFC", "New York Jets": "AFC", "Pittsburgh Steelers": "AFC",
    "Tennessee Titans": "AFC",
    # NFC
    "Arizona Cardinals": "NFC", "Atlanta Falcons": "NFC", "Carolina Panthers": "NFC",
    "Chicago Bears": "NFC", "Dallas Cowboys": "NFC", "Detroit Lions": "NFC",
    "Green Bay Packers": "NFC", "Los Angeles Rams": "NFC", "Minnesota Vikings": "NFC",
    "New Orleans Saints": "NFC", "New York Giants": "NFC", "Philadelphia Eagles": "NFC",
    "San Francisco 49ers": "NFC", "Seattle Seahawks": "NFC", "Tampa Bay Buccaneers": "NFC",
    "Washington Commanders": "NFC",
}

MLB_CONFERENCES: dict[str, str] = {
    # American League
    "Baltimore Orioles": "American League", "Boston Red Sox": "American League",
    "Chicago White Sox": "American League", "Cleveland Guardians": "American League",
    "Detroit Tigers": "American League", "Houston Astros": "American League",
    "Kansas City Royals": "American League", "Los Angeles Angels": "American League",
    "Minnesota Twins": "American League", "New York Yankees": "American League",
    "Oakland Athletics": "American League", "Seattle Mariners": "American League",
    "Tampa Bay Rays": "American League", "Texas Rangers": "American League",
    "Toronto Blue Jays": "American League",
    # National League
    "Arizona Diamondbacks": "National League", "Atlanta Braves": "National League",
    "Chicago Cubs": "National League", "Cincinnati Reds": "National League",
    "Colorado Rockies": "National League", "Los Angeles Dodgers": "National League",
    "Miami Marlins": "National League", "Milwaukee Brewers": "National League",
    "New York Mets": "National League", "Philadelphia Phillies": "National League",
    "Pittsburgh Pirates": "National League", "San Diego Padres": "National League",
    "San Francisco Giants": "National League", "St. Louis Cardinals": "National League",
    "Washington Nationals": "National League",
}

NHL_CONFERENCES: dict[str, str] = {
    # Eastern Conference
    "Boston Bruins": "Eastern", "Buffalo Sabres": "Eastern", "Carolina Hurricanes": "Eastern",
    "Columbus Blue Jackets": "Eastern", "Detroit Red Wings": "Eastern",
    "Florida Panthers": "Eastern", "Montreal Canadiens": "Eastern",
    "New Jersey Devils": "Eastern", "New York Islanders": "Eastern",
    "New York Rangers": "Eastern", "Ottawa Senators": "Eastern",
    "Philadelphia Flyers": "Eastern", "Pittsburgh Penguins": "Eastern",
    "Tampa Bay Lightning": "Eastern", "Toronto Maple Leafs": "Eastern",
    "Washington Capitals": "Eastern",
    # Western Conference
    "Anaheim Ducks": "Western", "Calgary Flames": "Western", "Chicago Blackhawks": "Western",
    "Colorado Avalanche": "Western", "Dallas Stars": "Western", "Edmonton Oilers": "Western",
    "Los Angeles Kings": "Western", "Minnesota Wild": "Western", "Nashville Predators": "Western",
    "San Jose Sharks": "Western", "Seattle Kraken": "Western", "St. Louis Blues": "Western",
    "Utah Hockey Club": "Western", "Vancouver Canucks": "Western",
    "Vegas Golden Knights": "Western", "Winnipeg Jets": "Western",
}

_CONFERENCE_FALLBACKS: dict[str, dict[str, str]] = {
    "nba": NBA_CONFERENCES,
    "nfl": NFL_CONFERENCES,
    "mlb": MLB_CONFERENCES,
    "nhl": NHL_CONFERENCES,
}


def _lookup_conference_fallback(league_slug: str, team_name: str) -> str | None:
    """Look up a team's conference from the static fallback map.

    Tries exact match first, then substring containment (handles names like
    "Brooklyn" matching "Brooklyn Nets").
    """
    fallback = _CONFERENCE_FALLBACKS.get(league_slug)
    if not fallback:
        return None
    # Exact match
    if team_name in fallback:
        return fallback[team_name]
    # Substring match — team_name might be "Nets" or "Brooklyn"
    name_lower = team_name.lower()
    for full_name, conf in fallback.items():
        if name_lower in full_name.lower() or full_name.lower() in name_lower:
            return conf
    return None


# ---------------------------------------------------------------------------
# Market filters — reject non-playoff markets
# ---------------------------------------------------------------------------

# Markets that should never appear in a playoff grid (win totals, props, etc.)
_NON_PLAYOFF_MARKET_RE = re.compile(
    r"""
    \bover\s*\(           |   # Win totals: "Over (41.5)"
    \bunder\s*\(          |   # "Under (41.5)"
    \bover/under\b        |   # "Over/Under"
    \b\d+\+\s*wins\b      |   # "15+ wins", "20+ wins"
    \bwin\s+total\b       |   # "Win Total"
    \bseason\s+wins\b     |   # "Season Wins"
    \bbefore\s+\w+\s+\d   |   # "Before March 7th, 2026" (date markets)
    \bexact\s+wins\b      |   # "Exact Wins"
    \bpoints\b            |   # Player stat props
    \brebounds\b          |   # Player stat props
    \bassists\b           |   # Player stat props
    \bmvp\b               |   # MVP markets
    \brookie\b            |   # Rookie of the year
    \bdefensive\b         |   # DPOY
    \bmost\s+improved\b   |   # MIP
    \bscoring\s+leader\b  |   # Scoring leader
    \b6th\s+man\b         |   # 6th man
    \bcoach\b             |   # Coach of the year
    \bvs\.?\s              |   # Game-level "Team A vs Team B"
    \bat\b.*:             |   # "Team A at Team B: Points"
    \bdraft\b             |   # Draft markets
    \bdrafted\b           |   # "freshmen drafted"
    \bfreshmen\b          |   # Draft props
    \bupset\b             |   # "1+ upsets" props
    \bseed\s+margin\b     |   # "Biggest Upset Seed Margin"
    \bpick\b              |   # Draft pick markets
    \ball[- ]star\b       |   # All-Star markets
    \bhome[- ]?court\b    |   # Home court advantage
    \bregular\s+season\b  |   # Regular season awards
    \bseries\s+price\b    |   # Series pricing markets
    \bexact\s+score\b     |   # Exact score props
    \btotal\s+(?:goals|runs|points|games)\b |  # Totals
    \bper\s+game\s+leader\b |  # Stat leaders: "Blocks Per Game Leader"
    \bleader\b            |   # Stat leaders
    \bexpansion\b         |   # Expansion draft/team markets
    \bmost\s+valuable\b   |   # "Most Valuable Player"
    \bplayer\s+of\b       |   # "Player of the Year"
    \bgolden\s+glove\b    |   # Baseball awards
    \bcy\s+young\b        |   # Baseball awards
    \bheisman\b           |   # College football awards
    \b(?:steals|blocks|assists|rebounds|scoring)\s+(?:leader|per\s+game)\b |  # Stat categories
    \bwhich\s+teams\s+will\s+play\b |  # "Which teams will play in..." matchup markets
    \bwhich\s+cities\b    |   # Expansion city markets
    \bcover\s+of\b        |   # "Cover of NBA 2K27"
    \b2k\d+\b             |   # Video game markets (NBA 2K27, etc.)
    \b\d+\+\s+(?:golf|major|championship)\b |  # "1+ golf major championship wins"
    \b(?:and|&)\b(?=.*\b(?:cup|champion|final))  |
    \besports?\b          |   # Esports markets
    \b(?:LOL|LoL)\b       |   # League of Legends
    \bvalorant\b          |   # Valorant esports
    \bcounter[- ]?strike\b |  # CS2/CSGO
    \b(?:LCK|LPL|LEC|LCS|VCT|MSI)\b |  # Esports league codes
    \bhalftime\b          |   # Super Bowl Halftime Show
    \banthem\b            |   # National anthem markets
    \bcoin\s*toss\b       |   # Coin toss props
    \bgatorade\b          |   # Gatorade color markets
    \bdarts\b             |   # Premier League Darts (not football)
    \bsnooker\b           |   # Snooker (not football)
    \bcricket\b           |   # Cricket markets
    \brunning\b.*\bback\b |   # "Running back to win MVP" player props
    \bballon\s+d.or\b     |   # Ballon d'Or award
    \bgolden\s+boot\b     |   # Golden Boot award
    \bgolden\s+ball\b      |   # Golden Ball award
    \b\(W\)\s*$               # Women's tournament game suffix: "Team A vs. Team B (W)"
    """,
    re.IGNORECASE | re.VERBOSE,
)


# Country names that should never appear as outcomes in club competitions
# (EPL, La Liga, Champions League, Bundesliga, MLS)
_COUNTRY_NAMES = {
    "Argentina", "Australia", "Austria", "Belgium", "Brazil", "Cameroon",
    "Canada", "Chile", "China", "Colombia", "Costa Rica", "Croatia",
    "Czech Republic", "Denmark", "Ecuador", "Egypt", "England", "Finland",
    "France", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India",
    "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica",
    "Japan", "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria",
    "North Korea", "Norway", "Panama", "Paraguay", "Peru", "Poland",
    "Portugal", "Qatar", "Romania", "Russia", "Saudi Arabia", "Scotland",
    "Senegal", "Serbia", "Slovakia", "Slovenia", "South Africa",
    "South Korea", "Spain", "Sweden", "Switzerland", "Tunisia", "Turkey",
    "Ukraine", "United States", "Uruguay", "Venezuela", "Wales",
    "USA", "US", "UK",
}


def _is_playoff_relevant_market(market_name: str) -> bool:
    """Check if a market name is relevant to playoff progression grids.

    Rejects win totals, player props, awards, game-level markets, and
    date-based threshold markets.
    """
    return not _NON_PLAYOFF_MARKET_RE.search(market_name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_diacritics(s: str) -> str:
    """Remove diacritics for cross-source name dedup."""
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _normalize_team_name(name: str) -> str:
    """Normalize a team/outcome name for dedup across sources."""
    n = _strip_diacritics(name).lower().strip()
    # Strip common suffixes
    n = re.sub(r"\s*\(.*\)$", "", n)
    # Strip trailing periods (e.g. "Michigan St." → "Michigan St")
    n = n.rstrip(".")
    # Normalize internal periods in abbreviations (e.g. "St." → "St")
    # This prevents "St. Louis Blues" vs "St Louis Blues" split
    n = re.sub(r"\.(?=\s)", "", n)
    return n


def _match_market_to_column(
    market: FuturesMarket,
    config: LeagueConfig,
) -> str | None:
    """Determine which grid column a market belongs to.

    Uses matching_rules from the league config (name patterns + market_tier),
    then falls back to tournament_stages.py classify_market_stage.
    """
    name = market.name or ""
    name_lower = name.lower()

    # 0. Reject non-playoff markets (win totals, props, awards, etc.)
    if not _is_playoff_relevant_market(name):
        return None

    # 1. Try league config matching rules (most specific)
    for rule in config.matching_rules:
        # Tier match
        if rule.tier is not None and market.market_tier == rule.tier:
            # Verify the column key exists in config columns
            if any(c.key == rule.column for c in config.columns):
                # For tier matches, also check name patterns if available
                # to prevent false positives (e.g., tier 2 could be conference OR award)
                if rule.name_patterns:
                    for pat in rule.name_patterns:
                        if re.search(pat, name, re.IGNORECASE):
                            return rule.column
                else:
                    return rule.column

        # Name pattern match
        for pat in rule.name_patterns:
            if re.search(pat, name, re.IGNORECASE):
                return rule.column

    # 2. Fall back to tournament_stages.py classify_market_stage
    # NOTE: Do NOT pass market_tier to the fallback — our config matching rules
    # already handle tiers with name-pattern gating. The fallback's tier→stage
    # mapping has no name validation, which causes false positives like
    # "NBA 2K27 Cover" (tier=1) → championship.
    stages = get_stages_for_sport(config.sport_category, league=None)
    if stages:
        stage_key = classify_market_stage(
            market_name=name,
            external_id=market.external_id,
            market_tier=None,  # Intentionally None — see note above
            stages=stages,
        )
        if stage_key and any(c.key == stage_key for c in config.columns):
            return stage_key

    return None


def _correct_inverted_probs(probs: list[float]) -> list[float]:
    """Detect and correct probability inversions.

    When a source shows the "No" side probability (1 - p) instead of "Yes",
    the values from two sources will sum to ~1.0. Detect this and invert
    the outlier.

    Returns the corrected list (same length, same order).
    """
    if len(probs) < 2:
        return probs
    if len(probs) == 2:
        a, b = probs
        # If they sum to ~1.0, one is inverted
        if abs(a + b - 1.0) < 0.05:
            # Invert the higher one (the one showing "No" probability)
            if a > b:
                return [1.0 - a, b]
            else:
                return [a, 1.0 - b]
        return probs
    # 3+ sources: detect outlier inversion
    med = statistics.median(probs)
    corrected = []
    for p in probs:
        inverted = 1.0 - p
        if abs(p - med) > 0.3 and abs(inverted - med) < abs(p - med):
            corrected.append(inverted)
        else:
            corrected.append(p)
    return corrected


def _merge_probabilities(probs: list[float]) -> float:
    """Merge probabilities from multiple sources using median.

    Applies inversion correction and outlier filtering before merging.
    With only 2 sources, median=mean so a single outlier has 50% weight.
    We detect extreme divergence (>10x ratio) and trust the lower value
    (in golf/futures, outlier prediction market prices are almost always
    too high due to illiquidity).
    """
    if not probs:
        return 0.0
    corrected = _correct_inverted_probs(probs)
    # With 2 sources: if one is >10x the other, drop the outlier
    if len(corrected) == 2:
        lo, hi = sorted(corrected)
        if lo > 0 and hi / lo > 10:
            return lo
    # With 3+ sources: drop values >10x the median of the rest
    if len(corrected) >= 3:
        filtered = []
        for i, p in enumerate(corrected):
            others = corrected[:i] + corrected[i + 1:]
            med_others = statistics.median(others)
            if med_others > 0 and p / med_others > 10:
                continue  # skip extreme outlier
            filtered.append(p)
        if filtered:
            return statistics.median(filtered)
    return statistics.median(corrected)


async def _compute_movers(
    session: AsyncSession,
    outcome_ids: list[int],
    hours: int = 24,
) -> dict[int, float]:
    """Compute probability change over the last N hours for a set of outcomes.

    Returns {outcome_id: change_24h}.
    """
    if not outcome_ids:
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Get earliest snapshot after cutoff for each outcome
    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            sqlfunc.min(FuturesOddsSnapshot.captured_at).label("earliest_time"),
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
        )
        .group_by(FuturesOddsSnapshot.outcome_id)
    )
    result = await session.execute(stmt)
    earliest_times = {row.outcome_id: row.earliest_time for row in result}

    if not earliest_times:
        return {}

    # Get probabilities at those earliest times
    old_probs: dict[int, float] = {}
    for oid, t in earliest_times.items():
        snap_stmt = (
            select(FuturesOddsSnapshot.probability)
            .where(
                FuturesOddsSnapshot.outcome_id == oid,
                FuturesOddsSnapshot.captured_at == t,
            )
            .limit(1)
        )
        snap_result = await session.execute(snap_stmt)
        row = snap_result.first()
        if row and row.probability is not None:
            old_probs[oid] = float(row.probability)

    return old_probs


async def _build_trend_chart(
    session: AsyncSession,
    outcome_ids: list[int],
    outcome_names: dict[int, str],
    hours: int = 168,
    top_n: int = 10,
    bucket_seconds: int = 3600,
) -> dict:
    """Build trend chart data for top N outcomes.

    Returns probability timeline in the same format as the futures
    probability-timeline endpoint.
    """
    if not outcome_ids:
        return {"timeline": [], "outcomes": []}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    stmt = (
        select(
            FuturesOddsSnapshot.outcome_id,
            FuturesOddsSnapshot.captured_at,
            FuturesOddsSnapshot.probability,
        )
        .where(
            FuturesOddsSnapshot.outcome_id.in_(outcome_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
            FuturesOddsSnapshot.probability.isnot(None),
        )
        .order_by(FuturesOddsSnapshot.captured_at)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"timeline": [], "outcomes": []}

    # Bucket by time
    buckets: dict[int, dict[int, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        ts = int(row.captured_at.timestamp())
        bucket_ts = (ts // bucket_seconds) * bucket_seconds
        if row.probability is not None:
            buckets[bucket_ts][row.outcome_id].append(float(row.probability))

    # Build timeline — aggregate across outcome IDs sharing the same name
    timeline = []
    for bucket_ts in sorted(buckets.keys()):
        entry = {
            "timestamp": datetime.fromtimestamp(bucket_ts, tz=timezone.utc).isoformat(),
            "outcomes": {},
        }
        # Group all probs by golfer name (multiple outcome IDs may share a name)
        by_name: dict[str, list[float]] = defaultdict(list)
        for oid, probs in buckets[bucket_ts].items():
            name = outcome_names.get(oid, str(oid))
            by_name[name].extend(probs)
        for name, all_probs in by_name.items():
            entry["outcomes"][name] = _merge_probabilities(all_probs)
        timeline.append(entry)

    # Build outcomes metadata (current probability = latest timeline entry)
    outcomes_meta = []
    if timeline:
        latest = timeline[-1]["outcomes"]
        for name, prob in sorted(latest.items(), key=lambda x: x[1], reverse=True):
            outcomes_meta.append({
                "name": name,
                "current_probability": prob,
            })

    return {
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }


async def _get_team_metadata(
    session: AsyncSession,
    team_names: set[str],
    league_slug: str = "",
) -> dict[str, dict]:
    """Look up team metadata (logo, colors, record, conference) by name.

    Returns {normalized_name: metadata_dict}.
    Falls back to static conference maps when standings_data is missing.
    """
    if not team_names:
        return {}

    # Build ILIKE conditions for each name
    conditions = []
    for name in team_names:
        escaped = name.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Team.name.ilike(f"%{escaped}%"))

    stmt = select(Team).where(*[] if not conditions else [conditions[0]])
    if len(conditions) > 1:
        stmt = select(Team).where(or_(*conditions))
    elif conditions:
        stmt = select(Team).where(conditions[0])

    result = await session.execute(stmt)
    teams = result.scalars().all()

    # Build lookup by normalized name
    team_lookup: dict[str, dict] = {}
    for team in teams:
        meta = {
            "team_id": team.id,
            "name": team.name,
            "short_name": team.abbreviation or team.name.split()[-1] if team.name else None,
            "abbreviation": getattr(team, "abbreviation", None),
            "logo_url": team.logo_url_small or team.logo_url_large,
            "primary_color": team.primary_color,
            "secondary_color": team.secondary_color,
            "record": team.current_record,
            "conference": None,
            "division": None,
            "seed": None,
        }

        # Extract standings info if available
        standings = team.standings_data or {}
        if isinstance(standings, dict):
            meta["conference"] = standings.get("conference")
            meta["division"] = standings.get("division")
            meta["seed"] = standings.get("position") or standings.get("seed")

        # Fallback to static conference map if standings didn't provide one
        if not meta["conference"] and league_slug and team.name:
            meta["conference"] = _lookup_conference_fallback(league_slug, team.name)

        norm = _normalize_team_name(team.name)
        team_lookup[norm] = meta

        # Also index by abbreviation if available
        if team.abbreviation:
            team_lookup[_normalize_team_name(team.abbreviation)] = meta

        # And alternate names
        alt_names = team.alternate_names or []
        for alt in alt_names:
            team_lookup[_normalize_team_name(alt)] = meta

    return team_lookup


# ---------------------------------------------------------------------------
# Golf Kalshi noise filter
# ---------------------------------------------------------------------------

# Placement columns where Kalshi's binary market prices are often noise.
_GOLF_PLACEMENT_COLS = {"make_cut", "top_20", "top_10", "top_5"}


def _filter_kalshi_placement_noise(cells: dict) -> None:
    """Filter out Kalshi price floor/ceiling noise from golf placement columns.

    Kalshi binary golf markets (e.g., "Will X finish Top 20?") are often
    illiquid, with prices stuck at 0.005 (floor) or 0.995 (ceiling).
    These aren't real probabilities — they're just the min/max prices
    on an empty order book.

    For placement columns: remove Kalshi values ≤ 0.02 or ≥ 0.98.
    For the "win" column: keep all values (low win odds can be legitimate).
    """
    for col_key in _GOLF_PLACEMENT_COLS:
        cell = cells.get(col_key)
        if not cell:
            continue
        sources = cell.get("sources", [])
        if len(sources) <= 1:
            # Only one source — even if it's noise, it's all we have.
            # But if it's a Kalshi floor/ceiling value alone, remove the cell entirely.
            if (sources and sources[0]["source"] == "kalshi"
                    and (sources[0]["probability"] <= 0.02 or sources[0]["probability"] >= 0.98)):
                del cells[col_key]
            continue

        # Multiple sources: filter out Kalshi floor/ceiling values
        filtered = [s for s in sources
                    if s["source"] != "kalshi"
                    or (0.02 < s["probability"] < 0.98)]
        if filtered and len(filtered) < len(sources):
            cell["sources"] = filtered
            probs = [s["probability"] for s in filtered]
            cell["merged_probability"] = round(statistics.median(probs), 4)


# ---------------------------------------------------------------------------
# DataGolf-first golf grid builder
# ---------------------------------------------------------------------------


# Tour display names
_TOUR_LABELS: dict[str, str] = {
    "pga": "PGA Tour",
    "euro": "DP World Tour",
    "kft": "Korn Ferry Tour",
    "liv": "LIV Golf",
    "alt": "LIV Golf",
    "opp": "PGA Tour (Opposite)",
}


async def _build_golf_grid_from_datagolf(
    config: LeagueConfig,
    db: AsyncSession,
    trend_hours: int,
    top: int,
) -> dict | None:
    """Build multi-tour golf grids using DataGolf as the source of truth.

    Fetches schedule + predictions from all supported DataGolf tours
    (PGA, European, Korn Ferry, LIV, Opposite events) and returns
    a response with an `events` array containing one grid per active event.

    Kalshi, Polymarket, and Odds API odds are overlaid when available.
    Returns None if DataGolf API is unavailable (falls back to normal flow).
    """
    if not os.getenv("DATAGOLF_API_KEY"):
        return None

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        # Build grids for all tours in parallel-ish fashion
        tours = ["pga", "euro", "kft", "opp", "alt"]
        events = []

        for tour in tours:
            event_grid = await _build_golf_tour_grid(
                service, tour, config, db, trend_hours, top,
            )
            if event_grid:
                events.append(event_grid)

        if not events:
            logger.info("Golf grid: no events found across any tour, falling back")
            return None

        # Primary event is the first one (PGA gets priority)
        primary = events[0]

        return {
            "league": config.slug,
            "name": primary.get("tour_name", config.name),
            "season": config.season_pattern,
            "tournament": primary.get("tournament"),
            "columns": primary.get("columns", []),
            "trend_chart": primary.get("trend_chart", {"timeline": [], "outcomes": []}),
            "teams": primary.get("teams", []),
            "grouped_teams": None,
            "movers": primary.get("movers", []),
            "team_count": primary.get("team_count", 0),
            "field_count": primary.get("field_count", 0),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "sources_available": primary.get("sources_available", []),
            "source_of_truth": "datagolf",
            # Multi-tour data
            "events": events,
        }

    except Exception as e:
        logger.error("Golf grid DataGolf error, falling back: %s", e)
        return None
    finally:
        await service.close()


async def _build_golf_tour_grid(
    service,
    tour: str,
    config: LeagueConfig,
    db: AsyncSession,
    trend_hours: int,
    top: int,
) -> dict | None:
    """Build a single tour's event grid from DataGolf data.

    Returns a dict with tournament info, teams, movers, trend chart, etc.
    Returns None if no current event or no players for this tour.
    """
    from app.services.datagolf_api import normalize_player_name, strip_diacritics

    tour_label = _TOUR_LABELS.get(tour, tour.upper())

    try:
        # 1. Get schedule → find current/upcoming tournament
        schedule = await service.get_schedule(tour=tour)
        if not schedule:
            logger.debug("Golf grid [%s]: no schedule", tour)
            return None

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_event = None
        for t in schedule:
            if t.status and t.status != "completed":
                current_event = t
                break
            if t.end_date and t.end_date >= now_str:
                current_event = t
                break

        if not current_event:
            logger.debug("Golf grid [%s]: no current event", tour)
            return None

        logger.info(
            "Golf grid [%s]: %s (id=%s, %s)",
            tour, current_event.event_name, current_event.event_id,
            current_event.start_date,
        )

        # 2. Get DataGolf model predictions
        in_play_players, in_play_info = await service.get_in_play_with_info(tour=tour)
        pre_tournament_players = await service.get_pre_tournament(tour=tour)

        # Detect stale in-play data: if in-play returns a DIFFERENT event
        # than the schedule says is current, discard it. This happens when
        # last week's event just finished and in-play hasn't cleared yet.
        if in_play_players and in_play_info:
            in_play_event = in_play_info.get("event_name", "")
            schedule_event = current_event.event_name
            if in_play_event and schedule_event:
                # Simple containment check (names may not match exactly)
                ip_lower = in_play_event.lower().strip()
                sched_lower = schedule_event.lower().strip()
                if ip_lower not in sched_lower and sched_lower not in ip_lower:
                    logger.warning(
                        "Golf grid [%s]: in-play event '%s' differs from schedule "
                        "event '%s' — discarding stale in-play data",
                        tour, in_play_event, schedule_event,
                    )
                    in_play_players = []

        is_live = bool(in_play_players)

        players = in_play_players or pre_tournament_players
        if not players:
            logger.debug("Golf grid [%s]: no players", tour)
            return None

        logger.info(
            "Golf grid [%s]: %d golfers (in-play=%d, pre-tournament=%d)",
            tour, len(players), len(in_play_players), len(pre_tournament_players),
        )

        # Build pre-tournament probability lookup
        pre_tourney_lookup: dict[str, object] = {}
        for p in pre_tournament_players:
            pre_tourney_lookup[_normalize_team_name(p.player_name)] = p

        # Build canonical golfer lookup
        dg_field: dict[str, object] = {}
        dg_display_names: dict[str, str] = {}
        for player in players:
            norm = _normalize_team_name(player.player_name)
            dg_field[norm] = player
            dg_display_names[norm] = player.player_name

        # Log pre-tournament lookup coverage for diagnostics
        if dg_field and pre_tourney_lookup:
            matched = sum(1 for n in dg_field if n in pre_tourney_lookup)
            overlap_pct = matched / len(dg_field) * 100 if dg_field else 0

            # Low overlap means pre-tournament is likely for a DIFFERENT event
            if overlap_pct < 50:
                logger.warning(
                    "Golf grid [%s]: pre-tournament only covers %d/%d (%.0f%%) "
                    "in-play golfers — likely a different event! "
                    "Will use in-play values directly.",
                    tour, matched, len(dg_field), overlap_pct,
                )
                # Clear the lookup — don't use mismatched pre-tournament data
                pre_tourney_lookup.clear()
            else:
                logger.info(
                    "Golf grid [%s]: pre-tournament lookup covers %d/%d (%.0f%%) "
                    "in-play golfers",
                    tour, matched, len(dg_field), overlap_pct,
                )
        elif dg_field and not pre_tourney_lookup:
            logger.warning(
                "Golf grid [%s]: pre-tournament endpoint returned 0 players — "
                "all %d golfers will use in-play data only",
                tour, len(dg_field),
            )

        # 3a. Look up DataGolf FuturesOutcome IDs for this event
        # The DataGolf polling task creates FuturesMarket/Outcome/Snapshot
        # records. We need the outcome IDs to enable trend charts and 24h movers.
        dg_outcome_lookup: dict[str, dict[str, int]] = {}  # norm_name → {col_key → outcome_id}
        dg_ext_prefix = f"datagolf:{tour}:{current_event.event_id}:"
        dg_market_stmt = (
            select(FuturesMarket)
            .where(
                FuturesMarket.source == "datagolf",
                FuturesMarket.external_id.like(f"{dg_ext_prefix}%"),
            )
            .options(selectinload(FuturesMarket.outcomes))
        )
        dg_result = await db.execute(dg_market_stmt)
        dg_markets = dg_result.scalars().unique().all()
        for dg_market in dg_markets:
            col_key = dg_market.external_id.rsplit(":", 1)[-1]  # "win", "top_5", etc.
            for out in dg_market.outcomes:
                norm = _normalize_team_name(out.name)
                if norm not in dg_outcome_lookup:
                    dg_outcome_lookup[norm] = {}
                dg_outcome_lookup[norm][col_key] = out.id

        logger.info(
            "Golf grid [%s]: found %d DataGolf outcome IDs across %d markets",
            tour, sum(len(v) for v in dg_outcome_lookup.values()), len(dg_markets),
        )

        # 3b. Query DB for Kalshi/Polymarket/Odds API golf markets
        # IMPORTANT: Filter to only markets matching the CURRENT tournament.
        # Without this, season-long major championship odds (Masters, PGA
        # Championship, US Open, The Open) from Odds API contaminate every
        # tournament grid — e.g., Bridgeman's 0.59% Open odds mix into Valspar.
        sport_conditions = [
            FuturesMarket.external_id.ilike(f"{sk}%")
            for sk in config.sport_keys
        ]
        category_condition = FuturesMarket.llm_sport_category == "golf"
        market_filter = or_(*sport_conditions, category_condition)

        stmt = (
            select(FuturesMarket)
            .where(
                market_filter,
                FuturesMarket.status != "resolved",
                # Exclude DataGolf's own markets — we use the API directly
                FuturesMarket.source != "datagolf",
            )
            .options(selectinload(FuturesMarket.outcomes))
        )
        result = await db.execute(stmt)
        all_db_markets = result.scalars().unique().all()

        # Filter to only markets whose name matches the current tournament
        tournament_name = current_event.event_name or ""
        # Extract meaningful words from tournament name for matching
        # "Valspar Championship" → ["valspar"]
        # "Arnold Palmer Invitational" → ["arnold", "palmer"]
        _GOLF_STOPWORDS = {
            "championship", "tournament", "invitational", "classic",
            "presented", "by", "the", "at", "pga", "tour", "winner",
            "top", "finish", "hosted", "sponsored", "powered",
        }
        tourney_tokens = [
            w for w in tournament_name.lower().split()
            if w not in _GOLF_STOPWORDS and len(w) >= 3
        ]
        # Handle ambiguous tournament names:
        # "The Open" / "US Open" → use full name phrase to avoid cross-match
        if not tourney_tokens and tournament_name:
            tourney_tokens = [tournament_name.lower().strip()]
        elif len(tourney_tokens) == 1 and tourney_tokens[0] == "open":
            # "open" alone matches both "US Open" and "The Open" — use phrase
            tourney_tokens = [tournament_name.lower().strip()]

        def _market_matches_tournament(market_name: str) -> bool:
            """Check if a market name references the current tournament."""
            if not tourney_tokens:
                return True  # Can't filter without tournament name
            name_lower = market_name.lower() if market_name else ""
            # At least one distinctive tournament token must appear
            return any(tok in name_lower for tok in tourney_tokens)

        db_markets = [
            m for m in all_db_markets
            if _market_matches_tournament(m.name)
        ]

        if len(db_markets) < len(all_db_markets):
            logger.info(
                "Golf grid [%s]: filtered %d → %d DB markets (tournament='%s', tokens=%s)",
                tour, len(all_db_markets), len(db_markets),
                tournament_name, tourney_tokens,
            )

        # 4. Match DB market outcomes to DataGolf golfers
        # column_key → norm_name → list of {source, probability, ...}
        grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        all_outcome_ids: list[int] = []
        outcome_id_to_name: dict[int, str] = {}

        for market in db_markets:
            col_key = _match_market_to_column(market, config)
            if not col_key:
                continue

            for outcome in market.outcomes:
                if outcome.current_probability is None:
                    continue
                prob = float(outcome.current_probability)
                if prob <= 0:
                    continue

                oname = outcome.name or ""
                if _NON_PLAYOFF_MARKET_RE.search(oname):
                    continue
                if oname.lower().strip() in ("yes", "no", "over", "under"):
                    continue
                # Filter prediction market 0.5 noise
                if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                    continue

                # Match outcome name to DataGolf field
                outcome_norm = _normalize_team_name(oname)
                matched_norm = _match_golfer_to_field(outcome_norm, dg_field)
                if not matched_norm:
                    continue  # Not in the DataGolf field → skip

                grid_raw[col_key][matched_norm].append({
                    "source": market.source,
                    "probability": prob,
                    "market_id": market.id,
                    "outcome_id": outcome.id,
                })
                all_outcome_ids.append(outcome.id)
                outcome_id_to_name[outcome.id] = oname

        # 5. Add DataGolf model probabilities
        # The in-play endpoint returns LIVE updated probabilities during
        # tournaments (not binary 0/1). Pre-tournament is only useful
        # before the event starts or as a fallback when in-play is unavailable.
        col_map = {"win": "win", "top_5": "top_5", "top_10": "top_10",
                    "top_20": "top_20", "make_cut": "make_cut"}

        for norm_name in dg_field:
            player = dg_field[norm_name]
            pre_player = pre_tourney_lookup.get(norm_name)

            for dg_key, col_key in col_map.items():
                # Try in-play first, fall back to pre-tournament
                prob = getattr(player, dg_key, None)
                if prob is None and pre_player:
                    prob = getattr(pre_player, dg_key, None)

                if prob is None:
                    continue

                # During live tournaments, 0.0 = eliminated, 1.0 = clinched
                # These are meaningful. During pre-tournament, values should
                # be real probabilities (0 < p < 1), so 0.0/1.0 are noise.
                if is_live:
                    # Include 0.0 (eliminated) but skip negative
                    if prob < 0.0:
                        continue
                else:
                    # Pre-tournament: skip non-meaningful values
                    if prob <= 0.0 or prob >= 1.0:
                        continue

                # Look up the DataGolf outcome ID from the polling task's
                # FuturesOutcome records — this enables trend charts and 24h movers
                dg_oid = dg_outcome_lookup.get(norm_name, {}).get(col_key)
                if dg_oid:
                    all_outcome_ids.append(dg_oid)
                    outcome_id_to_name[dg_oid] = dg_display_names.get(norm_name, norm_name)

                grid_raw[col_key][norm_name].append({
                    "source": "datagolf",
                    "probability": prob,
                    "market_id": None,
                    "outcome_id": dg_oid,
                })

        # Deduplicate within same source per golfer+column (keep lowest prob)
        for col_key in grid_raw:
            for norm_name in grid_raw[col_key]:
                entries = grid_raw[col_key][norm_name]
                if len(entries) <= 1:
                    continue
                by_source: dict[str, list[dict]] = defaultdict(list)
                for e in entries:
                    by_source[e["source"]].append(e)
                deduped = []
                for source, source_entries in by_source.items():
                    best = min(source_entries, key=lambda e: e["probability"])
                    deduped.append(best)
                grid_raw[col_key][norm_name] = deduped

        # 6. Build team rows — start from DataGolf field (canonical)
        # Compute 24h movers
        old_probs = await _compute_movers(db, all_outcome_ids, hours=24)

        championship_col = "win"
        teams = []

        for norm_name in dg_field:
            display_name = dg_display_names[norm_name]
            player = dg_field[norm_name]

            cells = {}
            for col in config.columns:
                entries = grid_raw.get(col.key, {}).get(norm_name, [])
                if not entries:
                    continue

                probs = [e["probability"] for e in entries]
                merged = _merge_probabilities(probs)

                sources = []
                for e in entries:
                    sources.append({
                        "source": e["source"],
                        "probability": round(e["probability"], 4),
                    })

                # 24h trend
                trend_24h = None
                db_entries = [e for e in entries if e["outcome_id"]]
                if db_entries:
                    oid = db_entries[0]["outcome_id"]
                    old_p = old_probs.get(oid)
                    if old_p is not None:
                        trend_24h = round(merged - old_p, 4)

                cells[col.key] = {
                    "merged_probability": round(merged, 4),
                    "sources": sources,
                    "trend_24h": trend_24h,
                }

            # Filter Kalshi price floor/ceiling noise for placement columns.
            # Kalshi binary golf markets often have illiquid prices stuck at
            # 0.005 (floor) or 0.995 (ceiling). These aren't real probabilities.
            _filter_kalshi_placement_noise(cells)

            # Include golfer even if no cells (they're in the field)
            # But skip if absolutely no data
            if not cells:
                continue

            team_row = {
                "name": display_name,
                "short_name": display_name,
                "team_id": None,
                "logo_url": None,
                "primary_color": None,
                "secondary_color": None,
                "record": None,
                "conference": None,
                "division": None,
                "seed": None,
                "cells": cells,
            }

            # Add leaderboard info if in-play
            if is_live and player.position:
                team_row["position"] = player.position
                team_row["total_score"] = player.total_score
                team_row["today_score"] = player.today_score
                team_row["thru"] = player.thru
                team_row["current_round"] = player.current_round

            teams.append(team_row)

        # Sort by win probability descending
        teams.sort(key=lambda t: -(t["cells"].get("win", {}).get("merged_probability", 0)))

        # Cap at max_teams
        teams = teams[:config.max_teams]

        # Movers
        movers = []
        for team_row in teams:
            champ_cell = team_row["cells"].get(championship_col)
            if champ_cell and champ_cell.get("trend_24h") is not None:
                movers.append({
                    "name": team_row["name"],
                    "short_name": team_row["short_name"],
                    "team_id": None,
                    "column": championship_col,
                    "change_24h": champ_cell["trend_24h"],
                    "direction": "up" if champ_cell["trend_24h"] > 0 else "down",
                    "logo_url": None,
                    "primary_color": None,
                })
        movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
        movers = movers[:10]

        # Trend chart for top N golfers — collect ALL outcome IDs per golfer
        # (DataGolf + Kalshi + Polymarket) so we get the richest timeline
        top_team_norms = [_normalize_team_name(t["name"]) for t in teams[:top]]
        trend_outcome_ids = []
        trend_outcome_names: dict[int, str] = {}
        for norm_name in top_team_norms:
            entries = grid_raw.get(championship_col, {}).get(norm_name, [])
            for e in entries:
                oid = e.get("outcome_id")
                if oid and oid not in trend_outcome_names:
                    trend_outcome_ids.append(oid)
                    trend_outcome_names[oid] = dg_display_names.get(norm_name, norm_name)

        trend_chart = await _build_trend_chart(
            db, trend_outcome_ids, trend_outcome_names,
            hours=trend_hours, top_n=top,
        )
        trend_chart["column"] = championship_col
        trend_chart["top"] = top

        # Sources
        sources_seen = {"datagolf"}
        for col_entries in grid_raw.values():
            for entries in col_entries.values():
                for e in entries:
                    sources_seen.add(e["source"])

        # Active columns — only include columns where ≥10% of shown golfers
        # have data. Prevents showing "Make Cut" for LIV (alt tour) where
        # only 1 stray Kalshi market exists.
        active_columns = []
        min_fill = max(1, len(teams) // 10)  # At least 10% of golfers
        for col in config.columns:
            if col.key not in grid_raw:
                continue
            filled = sum(
                1 for t in teams
                if t["cells"].get(col.key, {}).get("merged_probability") is not None
            )
            if filled >= min_fill:
                active_columns.append({
                    "key": col.key,
                    "label": col.label,
                    "order": col.order,
                    "sequential": col.sequential,
                })

        return {
            "tour": tour,
            "tour_name": tour_label,
            "tournament": {
                "name": current_event.event_name,
                "course": current_event.course,
                "start_date": current_event.start_date,
                "end_date": current_event.end_date,
                "location": current_event.location,
                "country": current_event.country,
                "status": "live" if is_live else "upcoming",
                "current_round": current_event.current_round,
            },
            "columns": active_columns,
            "trend_chart": trend_chart,
            "teams": teams,
            "movers": movers,
            "team_count": len(teams),
            "field_count": len(dg_field),
            "sources_available": sorted(sources_seen),
        }

    except Exception as e:
        logger.warning("Golf grid [%s] error: %s", tour, e)
        return None


def _match_golfer_to_field(
    outcome_norm: str,
    dg_field: dict[str, object],
) -> str | None:
    """Match a market outcome name to a DataGolf golfer in the field.

    Tries exact match first, then fuzzy matching (last name + first initial).
    Returns the normalized DataGolf name or None.
    """
    # Exact match
    if outcome_norm in dg_field:
        return outcome_norm

    # Try matching by last name + first name prefix
    outcome_parts = outcome_norm.split()
    if len(outcome_parts) < 2:
        return None

    for dg_norm in dg_field:
        dg_parts = dg_norm.split()
        if len(dg_parts) < 2:
            continue

        # Match: same last word and first word starts the same
        if (outcome_parts[-1] == dg_parts[-1] and
                outcome_parts[0][:3] == dg_parts[0][:3] and
                len(outcome_parts[0]) >= 3):
            return dg_norm

        # Match: reversed order (some sources use "Last, First")
        if (outcome_parts[0] == dg_parts[-1] and
                outcome_parts[-1] == dg_parts[0]):
            return dg_norm

    return None


# ---------------------------------------------------------------------------
# Golf schedule endpoint (must be before /{league_slug} catch-all)
# ---------------------------------------------------------------------------


@router.get("/golf/schedule")
async def get_golf_schedule():
    """Return golf season schedule from DataGolf across all tours.

    Returns tournaments grouped by tour with status indicators
    for current/upcoming/completed events.
    """
    if not os.getenv("DATAGOLF_API_KEY"):
        raise HTTPException(status_code=503, detail="DataGolf API not configured")

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        tours = ["pga", "euro", "kft", "opp", "alt"]
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        tour_schedules = []
        for tour in tours:
            try:
                schedule = await service.get_schedule(tour=tour)
            except Exception as e:
                logger.warning("Golf schedule [%s]: error: %s", tour, e)
                continue

            if not schedule:
                continue

            tour_label = _TOUR_LABELS.get(tour, tour.upper())

            # Find current event for this tour
            current_event_id = None
            for t in schedule:
                if t.status and t.status != "completed":
                    current_event_id = t.event_id
                    break
                if t.end_date and t.end_date >= now_str:
                    current_event_id = t.event_id
                    break

            events = []
            for t in schedule:
                is_current = t.event_id == current_event_id
                # Determine display status
                if t.status == "completed":
                    display_status = "completed"
                elif is_current:
                    display_status = "current"
                elif t.start_date and t.start_date > now_str:
                    display_status = "upcoming"
                else:
                    display_status = t.status or "unknown"

                events.append({
                    "event_id": t.event_id,
                    "name": t.event_name,
                    "course": t.course,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "location": t.location,
                    "country": t.country,
                    "status": display_status,
                    "current_round": t.current_round,
                    "is_current": is_current,
                })

            tour_schedules.append({
                "tour": tour,
                "tour_name": tour_label,
                "events": events,
                "current_event_id": current_event_id,
            })

        return {
            "tours": tour_schedules,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error("Golf schedule error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch golf schedule")
    finally:
        await service.close()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("/{league_slug}")
async def get_playoff_grid(
    league_slug: str,
    hours: int = Query(default=None, description="Trend chart window in hours"),
    top: int = Query(default=10, ge=1, le=50, description="Top N teams for trend chart"),
    db: AsyncSession = Depends(get_db),
):
    """Return championship progression grid for a league.

    Each team row shows probabilities of reaching each playoff stage,
    sourced from Odds API, Kalshi, and Polymarket.
    """
    config = get_league_config(league_slug)
    if not config:
        available = get_all_league_slugs()
        raise HTTPException(
            status_code=404,
            detail=f"League '{league_slug}' not found. Available: {available}",
        )

    trend_hours = hours or config.trend_hours

    # -----------------------------------------------------------------------
    # Golf: use DataGolf as the source of truth for the field
    # -----------------------------------------------------------------------
    if league_slug == "golf":
        golf_result = await _build_golf_grid_from_datagolf(
            config, db, trend_hours, top,
        )
        if golf_result is not None:
            return golf_result
        # Fall through to normal flow if DataGolf unavailable

    # -----------------------------------------------------------------------
    # 1. Query futures markets that match this league
    # -----------------------------------------------------------------------

    # Path A: Match by external_id sport key prefix (Odds API markets)
    sport_conditions = []
    for sk in config.sport_keys:
        sport_conditions.append(FuturesMarket.external_id.ilike(f"{sk}%"))

    # Path B: Match by llm_sport_category (Kalshi/Polymarket markets)
    # These sources use non-sport-key external IDs (tickers, numeric IDs).
    # We filter by category, then use league_name_patterns in Python to
    # separate leagues that share a category (NBA vs NCAAB both = "basketball").
    category_condition = FuturesMarket.llm_sport_category == config.sport_category

    market_filter = or_(*sport_conditions, category_condition)

    stmt = (
        select(FuturesMarket)
        .where(
            market_filter,
            FuturesMarket.status != "resolved",
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    all_markets = result.scalars().unique().all()

    # Filter by league name patterns (Python-side) to separate e.g. NBA from NCAAB
    league_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.league_name_patterns
    ] if config.league_name_patterns else []

    # Gender exclusion: Men's leagues should not include Women's markets and vice versa
    _WOMENS_RE = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
    _MENS_RE = re.compile(r"\bMen.?s\b", re.IGNORECASE)
    is_mens_league = config.slug in ("ncaa-basketball", "ncaa-football", "nba", "nhl", "nfl", "mlb")
    is_womens_league = config.slug in ("wnba",)

    markets = []
    for market in all_markets:
        eid = market.external_id or ""
        name = market.name or ""

        # Gender filter: reject women's markets from men's grids and vice versa
        if is_mens_league and _WOMENS_RE.search(name):
            continue
        if is_womens_league and _MENS_RE.search(name) and not _WOMENS_RE.search(name):
            continue

        # Path A markets (sport key prefix) always pass
        if any(eid.lower().startswith(sk.lower()) for sk in config.sport_keys):
            markets.append(market)
            continue
        # Path B markets must match a league name pattern
        if league_patterns:
            if any(pat.search(name) for pat in league_patterns):
                # For Champions League: reject "Champions League Qualification/Spot"
                # markets from domestic leagues (they're about qualifying TO UCL,
                # not performance IN the UCL).
                if config.slug == "champions-league" and re.search(
                    r"\b(?:qualif|spot|place|make.*champions|top\s*\d)\b",
                    name, re.IGNORECASE,
                ):
                    continue
                markets.append(market)
        # If no league_name_patterns configured, all category matches pass
        elif not league_patterns:
            markets.append(market)

    logger.info(
        "Playoff grid %s: found %d markets for sport_keys=%s, category=%s",
        league_slug,
        len(markets),
        config.sport_keys,
        config.sport_category,
    )

    # -----------------------------------------------------------------------
    # 2. Match each market to a grid column
    # -----------------------------------------------------------------------

    # column_key -> list of (market, outcome) tuples
    column_data: dict[str, list[tuple]] = defaultdict(list)

    for market in markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        for outcome in market.outcomes:
            if outcome.current_probability is None:
                continue
            prob = float(outcome.current_probability)
            if prob <= 0:
                continue
            # Skip non-team outcome names (thresholds, dates, generic)
            oname = outcome.name or ""
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            # Skip generic yes/no, over/under outcomes
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            # Skip matchup pair outcomes like "Tampa Bay and Colorado"
            if re.search(r"\band\b", oname, re.IGNORECASE) and \
               not re.search(r"\bTrail\s+Blazers\b", oname, re.IGNORECASE):
                # Allow "Trail Blazers" which is a real team (Portland Trail Blazers)
                # but block "Tampa Bay and Colorado" matchup pairs
                if re.match(r"^[\w\s.]+ and [\w\s.]+$", oname.strip()):
                    continue
            # Skip generic/seeded outcomes like "#1 seed", "1+ wins"
            if re.match(r"^#?\d+", oname.strip()):
                continue
            # Skip country/national team names in club competitions
            # (catches World Cup outcomes leaking into Champions League, EPL, etc.)
            if config.sport_category == "soccer" and oname.strip() in _COUNTRY_NAMES:
                continue
            # Filter prediction market 0.5 noise — binary markets near 50%
            # are illiquid defaults, not real predictions.  Applies to both
            # Kalshi and Polymarket.
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                continue

            column_data[col_key].append((market, outcome))

    # Log column coverage
    for col in config.columns:
        count = len(column_data.get(col.key, []))
        logger.info("  Column %s (%s): %d outcome entries", col.key, col.label, count)

    # -----------------------------------------------------------------------
    # 3. Aggregate by team × column with cross-source merging
    # -----------------------------------------------------------------------

    # team_norm_name -> {col_key -> {source -> {probability, bookmaker, market_id, outcome_id, last_updated}}}
    grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    # Track outcome IDs for trend/mover queries
    all_outcome_ids: list[int] = []
    outcome_id_to_team: dict[int, str] = {}
    outcome_id_to_name: dict[int, str] = {}

    for col_key, entries in column_data.items():
        for market, outcome in entries:
            team_name = outcome.name
            norm = _normalize_team_name(team_name)

            source_entry = {
                "source": market.source,
                "probability": float(outcome.current_probability),
                "market_id": market.id,
                "outcome_id": outcome.id,
            }

            grid_raw[norm][col_key].append(source_entry)
            all_outcome_ids.append(outcome.id)
            outcome_id_to_team[outcome.id] = norm
            # Store display name (first occurrence wins)
            if norm not in outcome_id_to_name:
                outcome_id_to_name[outcome.id] = team_name

    # Deduplicate within same source per team+column: when a source has
    # multiple entries (e.g., both "NCAAB Championship" and "Make Championship
    # Game" matched to the championship column), keep the LOWEST probability.
    # The genuine championship market always has lower probability than
    # round-advancement markets.
    for norm_name in grid_raw:
        for col_key in grid_raw[norm_name]:
            entries = grid_raw[norm_name][col_key]
            if len(entries) <= 1:
                continue
            # Group by source
            by_source: dict[str, list[dict]] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            # Keep lowest prob per source
            deduped = []
            for source, source_entries in by_source.items():
                best = min(source_entries, key=lambda e: e["probability"])
                deduped.append(best)
            grid_raw[norm_name][col_key] = deduped

    # -----------------------------------------------------------------------
    # 3b. Merge duplicate teams (short name → full name dedup)
    # -----------------------------------------------------------------------
    # Kalshi uses "Oklahoma City", Odds API uses "Oklahoma City Thunder".
    # Merge entries where one normalized name is a prefix of another.

    norm_names = sorted(grid_raw.keys(), key=len, reverse=True)  # longest first
    merge_map: dict[str, str] = {}  # short_name → long_name

    for i, long_name in enumerate(norm_names):
        for short_name in norm_names[i + 1:]:
            if short_name in merge_map:
                continue
            # Check if short_name is a prefix of long_name
            if long_name.startswith(short_name + " ") or long_name.startswith(short_name + "-"):
                merge_map[short_name] = long_name
            # Check single-letter abbreviation suffix
            # e.g., "los angeles l" → "los angeles lakers"
            elif (
                len(short_name) >= 3
                and short_name[-2] == " "
                and short_name[-1].isalpha()
                and long_name.startswith(short_name[:-1])
                and len(long_name) > len(short_name)
                and long_name[len(short_name) - 1] == short_name[-1]
            ):
                merge_map[short_name] = long_name
            # Check if short_name words are a subset of long_name words
            # (e.g., "michigan state" vs "michigan st spartans")
            elif len(short_name.split()) >= 2:
                short_words = set(short_name.split())
                long_words = set(long_name.split())
                # Normalize common abbreviations for comparison
                def _expand_abbrevs(words):
                    expanded = set()
                    for w in words:
                        expanded.add(w)
                        if w == "st":
                            expanded.add("state")
                        elif w == "state":
                            expanded.add("st")
                    return expanded
                short_expanded = _expand_abbrevs(short_words)
                if short_expanded.issubset(_expand_abbrevs(long_words)):
                    merge_map[short_name] = long_name

    # Apply merges
    for short_name, long_name in merge_map.items():
        if short_name in grid_raw and long_name in grid_raw:
            for col_key, entries in grid_raw[short_name].items():
                grid_raw[long_name][col_key].extend(entries)
            del grid_raw[short_name]
            logger.debug("Merged team '%s' into '%s'", short_name, long_name)

    # -----------------------------------------------------------------------
    # 4. Build team rows with merged probabilities
    # -----------------------------------------------------------------------

    # Get team metadata
    team_names_raw = set()
    for norm_name in grid_raw:
        # Find any display name for lookup
        for col_entries in grid_raw[norm_name].values():
            for entry in col_entries:
                oid = entry["outcome_id"]
                if oid in outcome_id_to_name:
                    team_names_raw.add(outcome_id_to_name[oid])
                    break
            break

    team_meta = await _get_team_metadata(db, team_names_raw, league_slug=config.slug)

    # Second merge pass: use team metadata to identify teams that share
    # the same team_id but have different normalized names
    # (e.g., "Connecticut" vs "UConn Huskies")
    team_id_to_norm: dict[int, str] = {}
    meta_merge_map: dict[str, str] = {}
    for norm_name in list(grid_raw.keys()):
        meta = team_meta.get(norm_name, {})
        tid = meta.get("team_id")
        if tid is None:
            continue
        if tid in team_id_to_norm:
            # Same team_id, different norm name — merge shorter into longer
            existing = team_id_to_norm[tid]
            if len(norm_name) > len(existing):
                meta_merge_map[existing] = norm_name
                team_id_to_norm[tid] = norm_name
            else:
                meta_merge_map[norm_name] = existing
        else:
            team_id_to_norm[tid] = norm_name

    for short_name, long_name in meta_merge_map.items():
        if short_name in grid_raw and long_name in grid_raw:
            for col_key, entries in grid_raw[short_name].items():
                grid_raw[long_name][col_key].extend(entries)
            del grid_raw[short_name]
            logger.debug("Merged team '%s' into '%s' (same team_id)", short_name, long_name)

    # Compute 24h changes
    old_probs = await _compute_movers(db, all_outcome_ids, hours=24)

    teams = []
    championship_col = config.columns[-1].key  # Last column is typically championship

    for norm_name, col_map in grid_raw.items():
        # Find display name
        display_name = norm_name
        for col_entries in col_map.values():
            for entry in col_entries:
                oid = entry["outcome_id"]
                if oid in outcome_id_to_name:
                    display_name = outcome_id_to_name[oid]
                    break
            break

        # Look up team metadata
        meta = team_meta.get(norm_name, {})

        cells = {}
        for col in config.columns:
            entries = col_map.get(col.key, [])
            if not entries:
                continue

            probs = [e["probability"] for e in entries]
            corrected = _correct_inverted_probs(probs)
            merged = statistics.median(corrected)

            sources = []
            for e, corrected_p in zip(entries, corrected):
                src = {
                    "source": e["source"],
                    "probability": round(corrected_p, 4),
                }
                sources.append(src)

            # Compute 24h trend from the championship outcome
            trend_24h = None
            if entries:
                # Use the first outcome's old probability
                oid = entries[0]["outcome_id"]
                old_p = old_probs.get(oid)
                if old_p is not None:
                    trend_24h = round(merged - old_p, 4)

            cells[col.key] = {
                "merged_probability": round(merged, 4),
                "sources": sources,
                "trend_24h": trend_24h,
            }

        if not cells:
            continue

        team_row = {
            "name": display_name,
            "short_name": meta.get("short_name") or display_name,
            "team_id": meta.get("team_id"),
            "logo_url": meta.get("logo_url"),
            "primary_color": meta.get("primary_color"),
            "secondary_color": meta.get("secondary_color"),
            "record": meta.get("record"),
            "conference": meta.get("conference"),
            "division": meta.get("division"),
            "seed": meta.get("seed"),
            "cells": cells,
        }
        teams.append(team_row)

    # -----------------------------------------------------------------------
    # 4b. Column-sum sanity check
    # -----------------------------------------------------------------------
    # Expected sums: championship ~100%, conference ~200% (2 winners),
    # make_playoffs ~N_spots × 100%. If any column sums to > 2× expected,
    # log a warning. For championship column specifically, reject teams
    # with > 50% single-source probability as likely misclassified.

    _EXPECTED_SUMS = {
        "championship": 1.0,
        "conference": 2.0,  # 2 conference champions
        "pennant": 2.0,     # 2 pennant winners
    }
    for col in config.columns:
        col_sum = sum(
            t["cells"].get(col.key, {}).get("merged_probability", 0)
            for t in teams
        )
        expected = _EXPECTED_SUMS.get(col.key)
        if expected and col_sum > expected * 2.5:
            logger.warning(
                "Column %s sum=%.1f%% exceeds 2.5× expected %.0f%% for %s — "
                "possible misclassified markets",
                col.key, col_sum * 100, expected * 100, config.slug,
            )

    # -----------------------------------------------------------------------
    # 5. Sort teams
    # -----------------------------------------------------------------------

    def _sort_key(team_row):
        champ_prob = (
            team_row["cells"]
            .get(championship_col, {})
            .get("merged_probability", 0)
        )
        return -champ_prob  # descending

    teams.sort(key=_sort_key)

    # Cap at max_teams
    teams = teams[: config.max_teams]

    # -----------------------------------------------------------------------
    # 6. Compute biggest movers (top 5 up, top 5 down)
    # -----------------------------------------------------------------------

    movers = []
    for team_row in teams:
        champ_cell = team_row["cells"].get(championship_col)
        if champ_cell and champ_cell.get("trend_24h") is not None:
            movers.append({
                "name": team_row["name"],
                "short_name": team_row["short_name"],
                "team_id": team_row["team_id"],
                "column": championship_col,
                "change_24h": champ_cell["trend_24h"],
                "direction": "up" if champ_cell["trend_24h"] > 0 else "down",
                "logo_url": team_row.get("logo_url"),
                "primary_color": team_row.get("primary_color"),
            })

    movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
    movers = movers[:10]

    # -----------------------------------------------------------------------
    # 7. Build trend chart for top N teams
    # -----------------------------------------------------------------------

    # Collect championship outcome IDs for top N teams
    top_team_norms = [_normalize_team_name(t["name"]) for t in teams[:top]]
    trend_outcome_ids = []
    trend_outcome_names: dict[int, str] = {}

    for norm_name in top_team_norms:
        entries = grid_raw.get(norm_name, {}).get(championship_col, [])
        for e in entries:
            oid = e["outcome_id"]
            trend_outcome_ids.append(oid)
            trend_outcome_names[oid] = outcome_id_to_name.get(oid, norm_name)
            break  # one outcome per team for the chart

    trend_chart = await _build_trend_chart(
        db,
        trend_outcome_ids,
        trend_outcome_names,
        hours=trend_hours,
        top_n=top,
    )
    trend_chart["column"] = championship_col
    trend_chart["top"] = top

    # -----------------------------------------------------------------------
    # 8. Determine available sources
    # -----------------------------------------------------------------------

    sources_seen = set()
    for col_entries in column_data.values():
        for market, _ in col_entries:
            sources_seen.add(market.source)

    # -----------------------------------------------------------------------
    # 9. Build response
    # -----------------------------------------------------------------------

    # Only include columns that have data
    active_columns = []
    for col in config.columns:
        if col.key in column_data:
            active_columns.append({
                "key": col.key,
                "label": col.label,
                "order": col.order,
                "sequential": col.sequential,
            })

    # Group teams by conference if configured
    grouped_teams = None
    if config.conference_split:
        groups: dict[str, list] = defaultdict(list)
        ungrouped = []
        for team_row in teams:
            conf = team_row.get("conference")
            if conf:
                # Normalize conference names: "Eastern" → "Eastern Conference"
                # Prevents orphan groups from inconsistent standings data
                conf_norm = conf.strip()
                if conf_norm and not conf_norm.lower().endswith("conference"):
                    conf_norm = f"{conf_norm} Conference"
                team_row["conference"] = conf_norm
                groups[conf_norm].append(team_row)
            else:
                ungrouped.append(team_row)
        if groups:
            grouped_teams = {
                conf: rows for conf, rows in sorted(groups.items())
            }
            if ungrouped:
                grouped_teams["Other"] = ungrouped
    elif config.region_split:
        groups: dict[str, list] = defaultdict(list)
        ungrouped = []
        for team_row in teams:
            region = team_row.get("region")
            if region:
                groups[region].append(team_row)
            else:
                ungrouped.append(team_row)
        if groups:
            grouped_teams = {
                region: rows for region, rows in sorted(groups.items())
            }
            if ungrouped:
                grouped_teams["Other"] = ungrouped

    return {
        "league": config.slug,
        "name": config.name,
        "season": config.season_pattern,
        "columns": active_columns,
        "trend_chart": trend_chart,
        "teams": teams,
        "grouped_teams": grouped_teams,
        "movers": movers,
        "team_count": len(teams),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "sources_available": sorted(sources_seen),
    }


@router.get("/")
async def list_leagues():
    """List all available playoff grid leagues."""
    leagues = []
    for slug in get_all_league_slugs():
        config = get_league_config(slug)
        if config:
            leagues.append({
                "slug": config.slug,
                "name": config.name,
                "sport_category": config.sport_category,
                "column_count": len(config.columns),
            })
    return {"leagues": leagues}
