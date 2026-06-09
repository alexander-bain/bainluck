"""
Championship progression grid endpoint.

GET /api/playoffs/{league_slug} returns a grid of teams × playoff stages,
with multi-source probability merging, 24h movers, and trend chart data.
"""

import logging
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, and_, text, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config.league_configs import LeagueConfig, get_league_config, get_all_league_slugs
from app.models import FuturesMarket, FuturesOddsSnapshot, MatchingOverride, Team
from app.services import get_db
from app.utils.tournament_stages import classify_market_stage, get_stages_for_sport

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# NCAA Tournament 2026 bracket — regions and seeds
# Source: ESPN API (Selection Sunday 2026)
# ---------------------------------------------------------------------------

NCAA_2026_BRACKET: dict[str, dict] = {
    # East Region
    "Duke Blue Devils": {"region": "East", "seed": 1},
    "UConn Huskies": {"region": "East", "seed": 2},
    "Michigan State Spartans": {"region": "East", "seed": 3},
    "Kansas Jayhawks": {"region": "East", "seed": 4},
    "St. John's Red Storm": {"region": "East", "seed": 5},
    "Louisville Cardinals": {"region": "East", "seed": 6},
    "UCLA Bruins": {"region": "East", "seed": 7},
    "Ohio State Buckeyes": {"region": "East", "seed": 8},
    "TCU Horned Frogs": {"region": "East", "seed": 9},
    "UCF Knights": {"region": "East", "seed": 10},
    "South Florida Bulls": {"region": "East", "seed": 11},
    "Northern Iowa Panthers": {"region": "East", "seed": 12},
    "California Baptist Lancers": {"region": "East", "seed": 13},
    "North Dakota State Bison": {"region": "East", "seed": 14},
    "Furman Paladins": {"region": "East", "seed": 15},
    "Siena Saints": {"region": "East", "seed": 16},
    # West Region
    "Arizona Wildcats": {"region": "West", "seed": 1},
    "Purdue Boilermakers": {"region": "West", "seed": 2},
    "Gonzaga Bulldogs": {"region": "West", "seed": 3},
    "Arkansas Razorbacks": {"region": "West", "seed": 4},
    "Wisconsin Badgers": {"region": "West", "seed": 5},
    "BYU Cougars": {"region": "West", "seed": 6},
    "Miami Hurricanes": {"region": "West", "seed": 7},
    "Villanova Wildcats": {"region": "West", "seed": 8},
    "Utah State Aggies": {"region": "West", "seed": 9},
    "Missouri Tigers": {"region": "West", "seed": 10},
    "NC State Wolfpack": {"region": "West", "seed": 11},
    "Texas Longhorns": {"region": "West", "seed": 11},
    "High Point Panthers": {"region": "West", "seed": 12},
    "Hawai'i Rainbow Warriors": {"region": "West", "seed": 13},
    "Kennesaw State Owls": {"region": "West", "seed": 14},
    "Queens University Royals": {"region": "West", "seed": 15},
    "Long Island University Sharks": {"region": "West", "seed": 16},
    # South Region
    "Florida Gators": {"region": "South", "seed": 1},
    "Houston Cougars": {"region": "South", "seed": 2},
    "Illinois Fighting Illini": {"region": "South", "seed": 3},
    "Nebraska Cornhuskers": {"region": "South", "seed": 4},
    "Vanderbilt Commodores": {"region": "South", "seed": 5},
    "North Carolina Tar Heels": {"region": "South", "seed": 6},
    "Saint Mary's Gaels": {"region": "South", "seed": 7},
    "Clemson Tigers": {"region": "South", "seed": 8},
    "Iowa Hawkeyes": {"region": "South", "seed": 9},
    "Texas A&M Aggies": {"region": "South", "seed": 10},
    "VCU Rams": {"region": "South", "seed": 11},
    "McNeese Cowboys": {"region": "South", "seed": 12},
    "Troy Trojans": {"region": "South", "seed": 13},
    "Pennsylvania Quakers": {"region": "South", "seed": 14},
    "Idaho Vandals": {"region": "South", "seed": 15},
    "Lehigh Mountain Hawks": {"region": "South", "seed": 16},
    "Prairie View A&M Panthers": {"region": "South", "seed": 16},
    # Midwest Region
    "Michigan Wolverines": {"region": "Midwest", "seed": 1},
    "Iowa State Cyclones": {"region": "Midwest", "seed": 2},
    "Virginia Cavaliers": {"region": "Midwest", "seed": 3},
    "Alabama Crimson Tide": {"region": "Midwest", "seed": 4},
    "Texas Tech Red Raiders": {"region": "Midwest", "seed": 5},
    "Tennessee Volunteers": {"region": "Midwest", "seed": 6},
    "Kentucky Wildcats": {"region": "Midwest", "seed": 7},
    "Georgia Bulldogs": {"region": "Midwest", "seed": 8},
    "Saint Louis Billikens": {"region": "Midwest", "seed": 9},
    "Santa Clara Broncos": {"region": "Midwest", "seed": 10},
    "SMU Mustangs": {"region": "Midwest", "seed": 11},
    "Miami (OH) RedHawks": {"region": "Midwest", "seed": 11},
    "Akron Zips": {"region": "Midwest", "seed": 12},
    "Hofstra Pride": {"region": "Midwest", "seed": 13},
    "Wright State Raiders": {"region": "Midwest", "seed": 14},
    "Tennessee State Tigers": {"region": "Midwest", "seed": 15},
    "Howard Bison": {"region": "Midwest", "seed": 16},
    "UMBC Retrievers": {"region": "Midwest", "seed": 16},
    # Aliases for common name variations in market data
    "Michigan St Spartans": {"region": "East", "seed": 3},
    "North Carolina St.": {"region": "West", "seed": 11},
    "NC State": {"region": "West", "seed": 11},
    "Kennesaw St Owls": {"region": "West", "seed": 14},
    "Kennesaw State": {"region": "West", "seed": 14},
    "Wright St Raiders": {"region": "Midwest", "seed": 14},
    "North Dakota St Bison": {"region": "East", "seed": 14},
    "Cal Baptist Lancers": {"region": "East", "seed": 13},
    "Tennessee St Tigers": {"region": "Midwest", "seed": 15},
    "Prairie View Panthers": {"region": "South", "seed": 16},
    "LIU Sharks": {"region": "West", "seed": 16},
    "Michigan St": {"region": "East", "seed": 3},
    "St Johns Red Storm": {"region": "East", "seed": 5},
    "St. Johns Red Storm": {"region": "East", "seed": 5},
    "Saint Marys Gaels": {"region": "South", "seed": 7},
    "Hawaii Rainbow Warriors": {"region": "West", "seed": 13},
}


WNCAA_2026_BRACKET: dict[str, dict] = {
    # Region 1
    "UConn Huskies": {"region": "Region 1", "seed": 1},
    "Vanderbilt Commodores": {"region": "Region 1", "seed": 2},
    "Ohio State Buckeyes": {"region": "Region 1", "seed": 3},
    "North Carolina Tar Heels": {"region": "Region 1", "seed": 4},
    "Maryland Terrapins": {"region": "Region 1", "seed": 5},
    "Notre Dame Fighting Irish": {"region": "Region 1", "seed": 6},
    "Illinois Fighting Illini": {"region": "Region 1", "seed": 7},
    "Iowa State Cyclones": {"region": "Region 1", "seed": 8},
    "Syracuse Orange": {"region": "Region 1", "seed": 9},
    "Colorado Buffaloes": {"region": "Region 1", "seed": 10},
    "Fairfield Stags": {"region": "Region 1", "seed": 11},
    "Murray State Racers": {"region": "Region 1", "seed": 12},
    "Western Illinois Leathernecks": {"region": "Region 1", "seed": 13},
    "Howard Bison": {"region": "Region 1", "seed": 14},
    "High Point Panthers": {"region": "Region 1", "seed": 15},
    "UTSA Roadrunners": {"region": "Region 1", "seed": 16},
    # Region 2
    "UCLA Bruins": {"region": "Region 2", "seed": 1},
    "LSU Tigers": {"region": "Region 2", "seed": 2},
    "Duke Blue Devils": {"region": "Region 2", "seed": 3},
    "Minnesota Golden Gophers": {"region": "Region 2", "seed": 4},
    "Ole Miss Rebels": {"region": "Region 2", "seed": 5},
    "Baylor Bears": {"region": "Region 2", "seed": 6},
    "Texas Tech Lady Raiders": {"region": "Region 2", "seed": 7},
    "Oklahoma State Cowgirls": {"region": "Region 2", "seed": 8},
    "Princeton Tigers": {"region": "Region 2", "seed": 9},
    "Villanova Wildcats": {"region": "Region 2", "seed": 10},
    "Nebraska Cornhuskers": {"region": "Region 2", "seed": 11},
    "Gonzaga Bulldogs": {"region": "Region 2", "seed": 12},
    "Green Bay Phoenix": {"region": "Region 2", "seed": 13},
    "Charleston Cougars": {"region": "Region 2", "seed": 14},
    "Jacksonville Dolphins": {"region": "Region 2", "seed": 15},
    "California Baptist Lancers": {"region": "Region 2", "seed": 16},
    # Region 3
    "Texas Longhorns": {"region": "Region 3", "seed": 1},
    "Michigan Wolverines": {"region": "Region 3", "seed": 2},
    "Louisville Cardinals": {"region": "Region 3", "seed": 3},
    "West Virginia Mountaineers": {"region": "Region 3", "seed": 4},
    "Kentucky Wildcats": {"region": "Region 3", "seed": 5},
    "Alabama Crimson Tide": {"region": "Region 3", "seed": 6},
    "NC State Wolfpack": {"region": "Region 3", "seed": 7},
    "Oregon Ducks": {"region": "Region 3", "seed": 8},
    "Virginia Tech Hokies": {"region": "Region 3", "seed": 9},
    "Tennessee Lady Volunteers": {"region": "Region 3", "seed": 10},
    "Rhode Island Rams": {"region": "Region 3", "seed": 11},
    "James Madison Dukes": {"region": "Region 3", "seed": 12},
    "Miami (OH) RedHawks": {"region": "Region 3", "seed": 13},
    "Vermont Catamounts": {"region": "Region 3", "seed": 14},
    "Holy Cross Crusaders": {"region": "Region 3", "seed": 15},
    "Missouri State Lady Bears": {"region": "Region 3", "seed": 16},
    # Region 4
    "South Carolina Gamecocks": {"region": "Region 4", "seed": 1},
    "Iowa Hawkeyes": {"region": "Region 4", "seed": 2},
    "TCU Horned Frogs": {"region": "Region 4", "seed": 3},
    "Oklahoma Sooners": {"region": "Region 4", "seed": 4},
    "Michigan State Spartans": {"region": "Region 4", "seed": 5},
    "Washington Huskies": {"region": "Region 4", "seed": 6},
    "Georgia Lady Bulldogs": {"region": "Region 4", "seed": 7},
    "Clemson Tigers": {"region": "Region 4", "seed": 8},
    "USC Trojans": {"region": "Region 4", "seed": 9},
    "Virginia Cavaliers": {"region": "Region 4", "seed": 10},
    "South Dakota State Jackrabbits": {"region": "Region 4", "seed": 11},
    "Colorado State Rams": {"region": "Region 4", "seed": 12},
    "Idaho Vandals": {"region": "Region 4", "seed": 13},
    "UC San Diego Tritons": {"region": "Region 4", "seed": 14},
    "Fairleigh Dickinson Knights": {"region": "Region 4", "seed": 15},
    "Southern Jaguars": {"region": "Region 4", "seed": 16},
    # Common name aliases for matching
    "Oklahoma St.": {"region": "Region 2", "seed": 8},
    "Oklahoma State": {"region": "Region 2", "seed": 8},
    "Michigan St.": {"region": "Region 4", "seed": 5},
    "Michigan State": {"region": "Region 4", "seed": 5},
    "NC State": {"region": "Region 3", "seed": 7},
    "Virginia Tech": {"region": "Region 3", "seed": 9},
    "Iowa St.": {"region": "Region 1", "seed": 8},
    "Iowa State": {"region": "Region 1", "seed": 8},
    "Colorado St.": {"region": "Region 4", "seed": 12},
    "Murray St.": {"region": "Region 1", "seed": 12},
    "Tennessee": {"region": "Region 3", "seed": 10},
    "South Carolina": {"region": "Region 4", "seed": 1},
    "Cal Baptist": {"region": "Region 2", "seed": 16},
    "Green Bay": {"region": "Region 2", "seed": 13},
}


def _lookup_wncaa_bracket(team_name: str) -> dict | None:
    """Look up Women's NCAA tournament region/seed for a team."""
    if team_name in WNCAA_2026_BRACKET:
        return WNCAA_2026_BRACKET[team_name]

    def _expand(n: str) -> str:
        n = re.sub(r"\bSt\.?\b", "State", n)
        n = re.sub(r"\bCal\b", "California", n)
        return n.strip()

    expanded = _expand(team_name)
    if expanded != team_name and expanded in WNCAA_2026_BRACKET:
        return WNCAA_2026_BRACKET[expanded]

    name_lower = _expand(team_name).lower()
    for bracket_name, info in WNCAA_2026_BRACKET.items():
        bn = bracket_name.lower()
        if bn in name_lower or name_lower in bn:
            return info
        a_words = set(name_lower.split())
        b_words = set(bn.split())
        if len(a_words & b_words) >= 2:
            return info
    return None


def _lookup_ncaa_bracket(team_name: str) -> dict | None:
    """Look up NCAA tournament region/seed for a team.

    Tries exact match first, then normalized matching with common abbreviation
    expansion (St → State, Cal → California).
    """
    if team_name in NCAA_2026_BRACKET:
        return NCAA_2026_BRACKET[team_name]

    # Normalize: expand abbreviations for matching
    def _expand(n: str) -> str:
        n = re.sub(r"\bSt\.?\b", "State", n)
        n = re.sub(r"\bCal\b", "California", n)
        n = re.sub(r"\bN\.?\s*C\.?\s+State\b", "NC State", n, flags=re.I)
        return n.strip()

    expanded = _expand(team_name)
    if expanded != team_name and expanded in NCAA_2026_BRACKET:
        return NCAA_2026_BRACKET[expanded]

    # Substring match
    name_lower = _expand(team_name).lower()
    for bracket_name, info in NCAA_2026_BRACKET.items():
        bn = bracket_name.lower()
        if bn in name_lower or name_lower in bn:
            return info
        # Word overlap: 2+ shared words
        a_words = set(name_lower.split())
        b_words = set(bn.split())
        if len(a_words & b_words) >= 2:
            return info
    return None


def _extract_standings_label(standings: dict, field: str) -> str | None:
    """Return a display label from Team.standings_data.

    StatPal and ad hoc backfills can store group labels as plain strings or as
    small objects. Keep this tolerant so playoff grouping stays data-driven.
    """
    raw_value = standings.get(field)
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        label = raw_value.strip()
        return label or None
    if isinstance(raw_value, dict):
        for key in ("name", "display_name", "displayName", "short_name", "abbreviation"):
            value = raw_value.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
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
    \bupsets?\b            |   # "1+ upsets", "Number of Series Upsets" props
    \bsweeps?\b            |   # "Number of Series Sweeps" props
    \badvance\s+to\b       |   # "Team to advance to Conference Finals" — advancement, not winner
    \bnumber\s+of\s+series\b |  # "Number of Series Upsets/Sweeps" props
    \bseed\s+margin\b     |   # "Biggest Upset Seed Margin"
    \#\d+\s+seed\b        |   # "#1 Seed", "#2 Seed" — regular season finish, not playoffs
    \btop\s+seed\b        |   # "Top Seed" markets
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
    \bcover\b             |   # "Cover of NBA 2K27", "Cover Athlete"
    \b2k\b                |   # Video game markets (NBA 2K, 2K27, etc.)
    \bathlete\b            |   # "Cover Athlete" novelty markets
    \bticket\s+price\b    |   # "NBA Finals Ticket Price" prop markets
    \bfirst\s+(?:basket|tip|score)\b |  # Opening play prop markets
    \bopening\s+tip\b     |   # "Opening Tip Winner"
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
    \bsum\s+of\s+seeds\b  |   # "Sum of seeds in the Championship Game" props
    \bbiggest\s+upset\b   |   # "Biggest upset in..." props
    \bmost\s+outstanding\b |  # "Tournament Most Outstanding Player"
    \bannouncer\b         |   # "Announcers at..." props
    \bplayer\s+points\b   |   # "Player Points" props
    \bNIT\b               |   # NIT Tournament (not NCAA Tournament)
    \bseed\s+to\s+win\b   |   # "Seed to win the Championship" props
    \battend\b            |   # "Will Trump attend the NBA Finals?"
    \bexact\s+(?:series\s+)?score\b |  # Exact series score markets
    \b\d+-\d+\b.*\bexact\b |  # "4-0 be the exact..." series score
    \bseries\s+score\b    |   # "Series Score" props
    \bfirst\s+goal\b      |   # "First Goal Scorer" props
    \blast\s+goal\b       |   # "Last Goal Scorer" props
    \bseries\s+length\b   |   # "Series Length" props
    \bgames?\s+played\b   |   # "Games Played in Finals"
    \bsweep\b             |   # "Will the series be a sweep?"
    \bwin\s+in\s+\d\s+games?\b |  # "Win in 4 games"
    \b[4567]-[0-3]\b      |   # Series scores: 4-0, 4-1, 4-2, 4-3
    \bfinals?\s+mvp\b     |   # "Finals MVP" (more specific than bare \bmvp\b)
    \bplayer\s+to\s+record\b | # "Player to Record 40+ Points" finals props
    \btotal\s+(?:rebounds?|assists?|points?|goals?|saves?)\s+leader\b | # "Total Rebounds Leader"
    \bbuzzer\s+beater\b   |   # "Number of Buzzer Beaters"
    \bnumber\s+of\b        |   # "Number of [stat]" prop markets
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
# Season filtering — reject next-season markets
# ---------------------------------------------------------------------------

# Matches 4-digit years (2024–2030) in market names
_YEAR_RE = re.compile(r"\b(202[4-9]|2030)\b")

# Matches hyphenated season suffixes like "2026-27" → extracts both 2026 and 27
_SEASON_HYPHEN_RE = re.compile(r"\b(202[4-9])-(2[4-9]|30)\b")


def _extract_season_max_year(season_pattern: str) -> int | None:
    """Extract the maximum year from a season pattern like '2025-26' or '2026'.

    Returns the latest year referenced by the pattern:
      '2025-26' → 2026
      '2026'    → 2026
      '2026-27' → 2027
    Returns None if the pattern can't be parsed.
    """
    if not season_pattern:
        return None
    parts = season_pattern.split("-")
    try:
        if len(parts) == 2:
            base = int(parts[0])
            suffix = parts[1]
            if len(suffix) == 2:
                return base // 100 * 100 + int(suffix)
            return int(suffix)
        return int(parts[0])
    except (ValueError, IndexError):
        return None


def _extract_years_from_name(market_name: str) -> list[int]:
    """Extract all year references from a market name.

    Handles both standalone years ("2027") and hyphenated season formats
    ("2026-27" → [2026, 2027]).
    """
    years: set[int] = set()
    # First pass: find hyphenated season references like "2026-27"
    for match in _SEASON_HYPHEN_RE.finditer(market_name):
        base = int(match.group(1))
        suffix = int(match.group(2))
        years.add(base)
        years.add(base // 100 * 100 + suffix)
    # Second pass: find standalone 4-digit years
    for match in _YEAR_RE.finditer(market_name):
        years.add(int(match.group(1)))
    return sorted(years)


def _is_future_season_market(market_name: str, max_year: int) -> bool:
    """Check if a market name references a season beyond the current one.

    A market is considered future-season if it contains a year strictly
    greater than max_year.  Markets without any year reference pass through.

    Examples with max_year=2026:
      'NBA: 2027 Champion'        → True  (future)
      '2026 NBA Champion'         → False (current)
      'NBA Championship Winner'   → False (no year)
      'NBA 2026-27 Champion'      → True  (contains 2027)
    """
    years = _extract_years_from_name(market_name)
    if not years:
        return False
    return any(y > max_year for y in years)


def _is_past_season_market(market_name: str, max_year: int) -> bool:
    """Check if a market name references a season before the current one.

    A market is considered past-season if it contains year references and
    the maximum year in the name is strictly less than max_year.  Markets
    without any year reference pass through (assumed current season).

    This prevents stale resolved markets from prior seasons (e.g.,
    "2024-25 NBA Champion") from contaminating the current season grid
    via the per-source dedup which keeps the lowest probability.

    Examples with max_year=2026:
      '2024-25 NBA Champion'      → True  (past season, max=2025 < 2026)
      '2024 NBA Champion'         → True  (past season, max=2024 < 2026)
      '2025 NBA Champion'         → True  (past season, max=2025 < 2026)
      '2026 NBA Champion'         → False (current season)
      '2025-26 NBA Champion'      → False (current season, max=2026)
      'NBA Championship Winner'   → False (no year — assumed current)
      '2027 NBA Champion'         → False (future, handled by _is_future_season_market)
    """
    years = _extract_years_from_name(market_name)
    if not years:
        return False
    return max(years) < max_year


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Words that indicate a different school/team when they follow a location name.
# Prevents false merges like "Iowa" → "Iowa State" or "Tennessee" → "Tennessee Tech".
_LOCATION_MODIFIERS = frozenset({
    "state", "st", "tech", "city", "a&m", "southern", "northern",
    "central", "eastern", "western", "international",
})

# Non-prefix aliases: teams whose short/alternate names are completely different
# from their full names.  Maps normalized alias → normalized canonical name.
# Both directions are checked during merge.
_TEAM_NAME_ALIASES: dict[str, str] = {
    "connecticut": "uconn",
    "conn": "uconn",
    "pitt": "pittsburgh",
    "ole miss": "mississippi",
    "umass": "massachusetts",
    "cal baptist": "california baptist",
    "ca baptist": "california baptist",
    "smu": "southern methodist",
    "lsu": "louisiana state",
    "ucf": "central florida",
    "vcu": "virginia commonwealth",
    "byu": "brigham young",
    "a's": "athletics",
    "oakland a's": "oakland athletics",
}


from app.utils.name_normalization import (
    strip_diacritics as _strip_diacritics,  # noqa: F811 — re-exported for tests
    normalize_team_name as _normalize_team_name,
)


def _should_prefix_merge(short_name: str, long_name: str) -> bool:
    """Check if short_name should merge into long_name as a prefix.

    For multi-word short names: always merge if it's a prefix.
    For single-word short names: merge only if the next word in long_name
    is NOT a location modifier (prevents Iowa→Iowa State, Tennessee→Tennessee Tech).
    """
    if not (long_name.startswith(short_name + " ") or long_name.startswith(short_name + "-")):
        return False
    short_words = short_name.split()
    if len(short_words) >= 2:
        return True
    # Single-word: check what follows
    rest = long_name[len(short_name):].strip().lstrip("-").split()
    if rest and rest[0].lower() in _LOCATION_MODIFIERS:
        return False
    return True


def _alias_matches(name_a: str, name_b: str) -> bool:
    """Check if two normalized names refer to the same team via aliases.

    Returns True if name_a is an alias/canonical form that matches name_b.
    E.g., "connecticut" and "uconn huskies" → True (connecticut→uconn, prefix of uconn huskies).
    """
    for alias, canonical in _TEAM_NAME_ALIASES.items():
        # Check if one name starts with the alias and the other starts with canonical
        a_is_alias = name_a == alias or name_a.startswith(alias + " ")
        a_is_canonical = name_a == canonical or name_a.startswith(canonical + " ")
        b_is_alias = name_b == alias or name_b.startswith(alias + " ")
        b_is_canonical = name_b == canonical or name_b.startswith(canonical + " ")
        if (a_is_alias and b_is_canonical) or (a_is_canonical and b_is_alias):
            return True
    return False


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

    # 0b. Qualifier/berth/play-in keywords always mean make_playoffs, even if
    # the name also contains a conference term (e.g., "Teams to Make the
    # Eastern Conference Play-In Tournament").
    if any(c.key == "make_playoffs" for c in config.columns):
        if re.search(r"\b(?:playoff|postseason)\s*(?:qualif|berth)\b", name_lower):
            return "make_playoffs"
        if re.search(r"\bmake\b.*\b(?:playoffs|postseason)\b", name_lower):
            return "make_playoffs"
        if re.search(r"\bplay.in\s+tournament\b", name_lower):
            return None  # Play-in ≠ make playoffs — top seeds have 0% play-in but 99% playoffs

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


def _volume_confidence(volume_24h: int | None) -> float:
    """Map 24h trading volume to a confidence weight (0.3-1.0).

    Markets with higher volume have more reliable prices.
    Used to weight sources during probability merging.
    """
    if not volume_24h or volume_24h <= 0:
        return 0.5  # Unknown volume — moderate confidence
    if volume_24h < 1_000:
        return 0.3  # Very thin market
    if volume_24h < 10_000:
        return 0.6
    if volume_24h < 50_000:
        return 0.8
    return 1.0  # High-volume market — full confidence


def _merge_probabilities(
    probs: list[float],
    volumes: list[int | None] | None = None,
) -> float:
    """Merge probabilities from multiple sources.

    When volume data is available, uses volume-weighted average instead of
    plain median. This gives more weight to high-volume sources (which have
    more reliable prices) and less weight to thin/illiquid markets.

    Falls back to median when no volume data is available.
    Applies inversion correction and outlier filtering before merging.
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
        filtered_vols = []
        for i, p in enumerate(corrected):
            others = corrected[:i] + corrected[i + 1:]
            med_others = statistics.median(others)
            if med_others > 0 and p / med_others > 10:
                continue  # skip extreme outlier
            filtered.append(p)
            if volumes:
                filtered_vols.append(volumes[i] if i < len(volumes) else None)
        if filtered:
            corrected = filtered
            if filtered_vols:
                volumes = filtered_vols

    # Volume-weighted average when volume data is available for any source
    if volumes and any(v is not None and v > 0 for v in volumes):
        weights = [_volume_confidence(volumes[i] if i < len(volumes) else None)
                   for i in range(len(corrected))]
        total_weight = sum(weights)
        if total_weight > 0:
            return sum(p * w for p, w in zip(corrected, weights)) / total_weight

    return statistics.median(corrected)


async def _compute_movers(
    session: AsyncSession,
    outcome_ids: list[int],
    hours: int = 24,
) -> dict[int, float]:
    """Compute probability change over the last N hours for a set of outcomes.

    Returns {outcome_id: change_24h}.

    Gracefully handles query timeouts — returns whatever results were gathered
    before the timeout, or an empty dict if the first batch fails. The grid
    renders fine without mover data; it just won't show 24h trend arrows.
    """
    if not outcome_ids:
        return {}

    # Deduplicate outcome IDs to reduce query load
    unique_ids = list(set(outcome_ids))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Use LATERAL for efficient index seeks on
    # idx_fos_outcome_captured(outcome_id, captured_at).
    # The ORM GROUP BY version times out on 130+ outcome IDs.
    #
    # Batch into chunks of 40 to keep each query fast and avoid
    # overwhelming the planner with 100+ LATERAL lookups at once.
    _BATCH_SIZE = 40
    old_probs: dict[int, float] = {}

    from sqlalchemy import text

    try:
        for i in range(0, len(unique_ids), _BATCH_SIZE):
            batch = unique_ids[i : i + _BATCH_SIZE]
            result = await session.execute(
                text("""
                    SELECT fo.id AS outcome_id, snap.probability AS old_prob
                    FROM futures_outcomes fo
                    CROSS JOIN LATERAL (
                        SELECT fos.probability
                        FROM futures_odds_snapshots fos
                        WHERE fos.outcome_id = fo.id
                          AND fos.captured_at >= :cutoff
                        ORDER BY fos.captured_at ASC
                        LIMIT 1
                    ) snap
                    WHERE fo.id = ANY(:ids)
                """),
                {"ids": batch, "cutoff": cutoff},
            )
            old_probs.update(
                {row.outcome_id: float(row.old_prob) for row in result}
            )
    except Exception as exc:
        # Statement timeout or other DB error — log and return partial results.
        # The grid renders fine without movers; trend_24h will just be None.
        logger.warning(
            "_compute_movers: query failed after gathering %d/%d results: %s",
            len(old_probs), len(unique_ids), exc,
        )
        # After a cancelled statement the connection is in an error state;
        # rollback so subsequent queries on this session still work.
        try:
            await session.rollback()
        except Exception:
            pass

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
        .limit(5000)
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
    conference_field: str = "conference",
) -> dict[str, dict]:
    """Look up team metadata (logo, colors, record, conference) by name.

    Returns {normalized_name: metadata_dict}.
    Conference/division labels come from Team.standings_data.
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
            meta["conference"] = _extract_standings_label(standings, conference_field)
            meta["division"] = _extract_standings_label(standings, "division")
            meta["seed"] = standings.get("position") or standings.get("seed")

        # NCAA Tournament: look up region and seed from bracket data
        if league_slug == "ncaa-basketball" and team.name:
            bracket_info = _lookup_ncaa_bracket(team.name)
            if bracket_info:
                meta["region"] = bracket_info["region"]
                if not meta["seed"]:
                    meta["seed"] = bracket_info["seed"]
        elif league_slug == "ncaa-women-basketball" and team.name:
            bracket_info = _lookup_wncaa_bracket(team.name)
            if bracket_info:
                meta["region"] = bracket_info["region"]
                if not meta["seed"]:
                    meta["seed"] = bracket_info["seed"]

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

# Placement columns where Kalshi's binary market prices can be noise.
_GOLF_PLACEMENT_COLS = {"make_cut", "top_20", "top_10", "top_5"}

# Volume threshold: markets with zero trading activity are noise regardless
# of what probability they show. High or low probabilities are real signals.
_MIN_VOLUME = 10


def _is_kalshi_noise(source: dict) -> bool:
    """Detect if a Kalshi source entry is noise — no trading activity."""
    if source["source"] != "kalshi":
        return False
    vol = source.get("volume_24h")
    if vol is not None and vol < _MIN_VOLUME:
        return True
    return False


def _filter_kalshi_placement_noise(cells: dict) -> None:
    """Filter out Kalshi noise from golf placement columns.

    Removes Kalshi entries with no trading volume. High/low probabilities
    are kept — a 98% make-cut or 2% top-5 is real data, not noise.
    """
    for col_key in _GOLF_PLACEMENT_COLS:
        cell = cells.get(col_key)
        if not cell:
            continue
        sources = cell.get("sources", [])
        if len(sources) <= 1:
            if sources and _is_kalshi_noise(sources[0]):
                del cells[col_key]
            continue

        filtered = [s for s in sources if not _is_kalshi_noise(s)]
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

        # Track which tournament is the current PGA event (to avoid duplication)
        current_pga_event_name = None

        for tour in tours:
            event_grid = await _build_golf_tour_grid(
                service, tour, config, db, trend_hours, top,
            )
            if event_grid:
                events.append(event_grid)
                if tour == "pga":
                    current_pga_event_name = (
                        event_grid.get("tournament", {}).get("name", "")
                    )

        # Check for upcoming major tournaments on the PGA schedule that
        # aren't the current event. These get their own grid from DB data.
        try:
            pga_schedule = await service.get_schedule(tour="pga")
            if pga_schedule:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                lookahead = (
                    datetime.now(timezone.utc) + timedelta(days=14)
                ).strftime("%Y-%m-%d")

                for tourney in pga_schedule:
                    # Skip if it's the current event (already shown)
                    if (current_pga_event_name
                            and tourney.event_name
                            and (tourney.event_name.lower() == current_pga_event_name.lower()
                                 or tourney.event_name.lower() in current_pga_event_name.lower()
                                 or current_pga_event_name.lower() in tourney.event_name.lower())):
                        continue
                    # Skip completed events
                    if tourney.status == "completed":
                        continue
                    # Only look 14 days ahead
                    if tourney.start_date and tourney.start_date > lookahead:
                        continue
                    # Must be a recognizable major
                    if not tourney.event_name:
                        continue
                    is_major = any(
                        major in tourney.event_name.lower()
                        for major in _GOLF_MAJORS
                    )
                    if not is_major:
                        continue

                    logger.info(
                        "Golf grid: building upcoming major grid for '%s' (%s)",
                        tourney.event_name, tourney.start_date,
                    )
                    major_grid = await _build_upcoming_golf_event_grid(
                        tournament_name=tourney.event_name,
                        start_date=tourney.start_date,
                        end_date=tourney.end_date,
                        course=tourney.course,
                        location=tourney.location,
                        country=tourney.country,
                        config=config,
                        db=db,
                        trend_hours=trend_hours,
                        top=top,
                    )
                    if major_grid:
                        # Insert major events at the front (before non-PGA tours)
                        # but after the current PGA event
                        pga_count = sum(1 for e in events if e.get("tour") == "pga")
                        events.insert(pga_count, major_grid)
        except Exception as e:
            logger.warning("Golf grid: error scanning for upcoming majors: %s", e)

        if not events:
            logger.info("Golf grid: no events found across any tour, falling back")
            return None

        # Primary event: prefer a major if one is live, otherwise first event
        primary = events[0]
        for evt in events:
            if evt.get("tournament", {}).get("status") == "live":
                primary = evt
                break

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


def _find_current_golf_tournament(schedule: list, tour: str):
    """Find the current or upcoming tournament from a DataGolf schedule."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for t in schedule:
        if t.status and t.status != "completed":
            return t
        if t.end_date and t.end_date >= now_str:
            return t
    logger.debug("Golf grid [%s]: no current event", tour)
    return None


def _validate_in_play_data(
    in_play_players: list, in_play_info: dict | None,
    current_event, tour: str,
) -> list:
    """Discard stale in-play data if it's from a different event than the schedule."""
    if not in_play_players or not in_play_info:
        return in_play_players
    in_play_event = in_play_info.get("event_name", "")
    schedule_event = current_event.event_name
    if in_play_event and schedule_event:
        ip_lower = in_play_event.lower().strip()
        sched_lower = schedule_event.lower().strip()
        if ip_lower not in sched_lower and sched_lower not in ip_lower:
            logger.warning(
                "Golf grid [%s]: in-play event '%s' differs from schedule "
                "event '%s' — discarding stale in-play data",
                tour, in_play_event, schedule_event,
            )
            return []
    return in_play_players


def _build_player_lookups(
    players: list, pre_tournament_players: list, tour: str,
) -> tuple[dict[str, object], dict[str, str], dict[str, object]]:
    """Build canonical golfer field, display name, and pre-tournament lookups.

    Returns (dg_field, dg_display_names, pre_tourney_lookup).
    """
    pre_tourney_lookup: dict[str, object] = {}
    for p in pre_tournament_players:
        pre_tourney_lookup[_normalize_team_name(p.player_name)] = p

    dg_field: dict[str, object] = {}
    dg_display_names: dict[str, str] = {}
    for player in players:
        norm = _normalize_team_name(player.player_name)
        dg_field[norm] = player
        dg_display_names[norm] = player.player_name

    # Validate pre-tournament overlap
    if dg_field and pre_tourney_lookup:
        matched = sum(1 for n in dg_field if n in pre_tourney_lookup)
        overlap_pct = matched / len(dg_field) * 100 if dg_field else 0
        if overlap_pct < 50:
            logger.warning(
                "Golf grid [%s]: pre-tournament only covers %d/%d (%.0f%%) "
                "in-play golfers — likely a different event!",
                tour, matched, len(dg_field), overlap_pct,
            )
            pre_tourney_lookup.clear()

    return dg_field, dg_display_names, pre_tourney_lookup


async def _lookup_datagolf_outcome_ids(
    db: AsyncSession, tour: str, event_id: str,
) -> dict[str, dict[str, int]]:
    """Look up DataGolf FuturesOutcome IDs for trend charts and movers."""
    dg_outcome_lookup: dict[str, dict[str, int]] = {}
    dg_ext_prefix = f"datagolf:{tour}:{event_id}:"
    dg_market_stmt = (
        select(FuturesMarket)
        .where(
            FuturesMarket.source == "datagolf",
            FuturesMarket.external_id.like(f"{dg_ext_prefix}%"),
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    dg_result = await db.execute(dg_market_stmt)
    for dg_market in dg_result.scalars().unique().all():
        col_key = dg_market.external_id.rsplit(":", 1)[-1]
        for out in dg_market.outcomes:
            norm = _normalize_team_name(out.name)
            if norm not in dg_outcome_lookup:
                dg_outcome_lookup[norm] = {}
            dg_outcome_lookup[norm][col_key] = out.id
    return dg_outcome_lookup


async def _query_tournament_db_markets(
    db: AsyncSession, config: LeagueConfig, tournament_name: str, tour: str,
) -> list:
    """Query and filter DB markets (Kalshi/Polymarket/Odds API) for a golf tournament."""
    _GOLF_STOPWORDS = {
        "championship", "tournament", "invitational", "classic",
        "presented", "by", "the", "at", "pga", "tour", "winner",
        "top", "finish", "hosted", "sponsored", "powered", "open",
    }
    tourney_tokens = [
        w for w in tournament_name.lower().split()
        if w not in _GOLF_STOPWORDS and len(w) >= 3
    ]
    if not tourney_tokens and tournament_name:
        tourney_tokens = [tournament_name.lower().strip()]

    _KALSHI_GOLF_PREFIXES = (
        "kxpgatour", "kxpgamakecut", "kxpgatop5", "kxpgatop10",
        "kxpgatop20", "kxpgar1", "kxpgar2", "kxpgar3", "kxpgah2h",
        "kxpgaholeinone", "kxpgawinningscore", "kxpgacutline",
        "kxpgawinmargin", "kxlpgatour",
    )
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    sport_conditions = [
        FuturesMarket.external_id.ilike(f"{sk}%") for sk in config.sport_keys
    ]
    stmt = (
        select(FuturesMarket)
        .where(
            or_(*sport_conditions, FuturesMarket.llm_sport_category == "golf"),
            FuturesMarket.status != "resolved",
            FuturesMarket.source != "datagolf",
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    all_db_markets = result.scalars().unique().all()

    def _market_matches(market) -> bool:
        name_lower = (market.name or "").lower()
        if tourney_tokens and all(tok in name_lower for tok in tourney_tokens):
            return True
        eid = (market.external_id or "").lower()
        if eid and any(eid.startswith(p) for p in _KALSHI_GOLF_PREFIXES):
            return bool(market.updated_at and market.updated_at > freshness_cutoff)
        return not tourney_tokens

    name_matched = [m for m in all_db_markets if _market_matches(m)]

    # Filter garbage Polymarket binary aggregates
    db_markets = []
    for m in name_matched:
        if (len(m.outcomes) > 10 and not m.mutually_exclusive
                and m.source == "polymarket"):
            prob_sum = sum(
                float(o.current_probability) for o in m.outcomes if o.current_probability
            )
            if prob_sum > 2.0:
                continue
        db_markets.append(m)

    logger.info(
        "Golf grid [%s]: DB markets: %d raw -> %d name-matched -> %d after filter "
        "(tournament='%s', tokens=%s)",
        tour, len(all_db_markets), len(name_matched), len(db_markets),
        tournament_name, tourney_tokens,
    )
    return db_markets


def _match_outcomes_to_grid(
    db_markets: list, config: LeagueConfig, dg_field: dict, tour: str,
) -> tuple[dict, list[int], dict[int, str]]:
    """Match DB market outcomes to DataGolf golfers, building grid_raw.

    Returns (grid_raw, all_outcome_ids, outcome_id_to_name).
    """
    grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    all_outcome_ids: list[int] = []
    outcome_id_to_name: dict[int, str] = {}

    for market in db_markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                prob = float(outcome.current_probability)
            elif (outcome.current_yes_bid is not None
                  and outcome.current_yes_ask is not None
                  and float(outcome.current_yes_ask) > 0):
                prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
            else:
                continue
            if prob <= 0:
                continue

            oname = outcome.name or ""
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue

            matched_norm = _match_golfer_to_field(_normalize_team_name(oname), dg_field)
            if not matched_norm:
                continue

            grid_raw[col_key][matched_norm].append({
                "source": market.source,
                "probability": prob,
                "market_id": market.id,
                "outcome_id": outcome.id,
                "market_name": market.name,
                "last_updated": outcome.last_updated.isoformat() if outcome.last_updated else None,
                "volume_24h": market.volume_24h,
            })
            all_outcome_ids.append(outcome.id)
            outcome_id_to_name[outcome.id] = oname

    return grid_raw, all_outcome_ids, outcome_id_to_name


def _add_datagolf_model_probs(
    grid_raw: dict, dg_field: dict, pre_tourney_lookup: dict,
    dg_display_names: dict, dg_outcome_lookup: dict,
    current_event, is_live: bool,
    all_outcome_ids: list[int], outcome_id_to_name: dict[int, str],
) -> None:
    """Add DataGolf model probabilities into grid_raw (mutates in place)."""
    col_map = {"win": "win", "top_5": "top_5", "top_10": "top_10",
                "top_20": "top_20", "make_cut": "make_cut"}

    for norm_name in dg_field:
        player = dg_field[norm_name]
        pre_player = pre_tourney_lookup.get(norm_name)

        for dg_key, col_key in col_map.items():
            prob = getattr(player, dg_key, None)
            if prob is None and pre_player:
                prob = getattr(pre_player, dg_key, None)
            if prob is None:
                continue
            if is_live and prob < 0.0:
                continue
            if not is_live and (prob <= 0.0 or prob >= 1.0):
                continue

            dg_oid = dg_outcome_lookup.get(norm_name, {}).get(col_key)
            if dg_oid:
                all_outcome_ids.append(dg_oid)
                outcome_id_to_name[dg_oid] = dg_display_names.get(norm_name, norm_name)

            col_label = col_key.replace("_", " ").title()
            event_name = current_event.event_name or "Tournament"
            mode = "In-Play" if is_live else "Pre-Tournament"

            grid_raw[col_key][norm_name].append({
                "source": "datagolf",
                "probability": prob,
                "market_id": None,
                "outcome_id": dg_oid,
                "market_name": f"{event_name}: To {col_label} ({mode} statistical model)",
                "last_updated": datetime.now(timezone.utc).isoformat(),
            })

    # Deduplicate within same source per golfer+column
    for col_key in grid_raw:
        for norm_name in grid_raw[col_key]:
            entries = grid_raw[col_key][norm_name]
            if len(entries) <= 1:
                continue
            by_source: dict[str, list[dict]] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            grid_raw[col_key][norm_name] = [
                min(se, key=lambda e: e["probability"]) for se in by_source.values()
            ]


def _build_golf_grid_team_rows(
    dg_field: dict, dg_display_names: dict,
    grid_raw: dict, config: LeagueConfig,
    old_probs: dict[int, float], is_live: bool,
) -> list[dict]:
    """Build team rows for the golf grid from aggregated grid_raw data."""
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
            vols = [e.get("volume_24h") for e in entries]
            merged = min(_merge_probabilities(probs, vols), 1.0)

            sources = []
            for e in entries:
                src = {"source": e["source"], "probability": round(e["probability"], 4)}
                if e.get("market_name"):
                    src["market_name"] = e["market_name"]
                if e.get("last_updated"):
                    src["last_updated"] = e["last_updated"]
                if e.get("volume_24h") is not None:
                    src["volume_24h"] = e["volume_24h"]
                sources.append(src)

            trend_24h = None
            db_entries = [e for e in entries if e["outcome_id"]]
            if db_entries:
                old_p = old_probs.get(db_entries[0]["outcome_id"])
                if old_p is not None:
                    trend_24h = round(merged - old_p, 4)

            cell_data = {
                "merged_probability": round(merged, 4),
                "sources": sources,
                "trend_24h": trend_24h,
            }
            if (len(sources) == 1 and sources[0]["source"] == "kalshi"
                    and abs(merged - 0.01) < 0.001):
                cell_data["is_minimum_tick"] = True
            cells[col.key] = cell_data

        _filter_kalshi_placement_noise(cells)
        if not cells:
            continue

        team_row = {
            "name": display_name, "short_name": display_name,
            "team_id": None, "logo_url": None,
            "primary_color": None, "secondary_color": None,
            "record": None, "conference": None, "division": None,
            "seed": None, "cells": cells,
        }
        if is_live and player.position:
            team_row["position"] = player.position
            team_row["total_score"] = player.total_score
            team_row["today_score"] = player.today_score
            team_row["thru"] = player.thru
            team_row["current_round"] = player.current_round

        teams.append(team_row)

    teams.sort(key=lambda t: -(t["cells"].get("win", {}).get("merged_probability", 0)))
    return teams


async def _build_golf_tour_grid(
    service,
    tour: str,
    config: LeagueConfig,
    db: AsyncSession,
    trend_hours: int,
    top: int,
) -> dict | None:
    """Build a single tour's event grid from DataGolf data."""
    tour_label = _TOUR_LABELS.get(tour, tour.upper())

    try:
        # 1. Schedule + current event
        schedule = await service.get_schedule(tour=tour)
        if not schedule:
            logger.debug("Golf grid [%s]: no schedule", tour)
            return None

        current_event = _find_current_golf_tournament(schedule, tour)
        if not current_event:
            return None

        logger.info("Golf grid [%s]: %s (id=%s, %s)",
                    tour, current_event.event_name, current_event.event_id,
                    current_event.start_date)

        # 2. Player data
        in_play_players, in_play_info = await service.get_in_play_with_info(tour=tour)
        pre_tournament_players = await service.get_pre_tournament(tour=tour)

        in_play_players = _validate_in_play_data(
            in_play_players, in_play_info, current_event, tour,
        )
        is_live = bool(in_play_players)
        players = in_play_players or pre_tournament_players
        if not players:
            logger.debug("Golf grid [%s]: no players", tour)
            return None

        logger.info("Golf grid [%s]: %d golfers (in-play=%d, pre-tournament=%d)",
                    tour, len(players), len(in_play_players), len(pre_tournament_players))

        dg_field, dg_display_names, pre_tourney_lookup = _build_player_lookups(
            players, pre_tournament_players, tour,
        )

        # 3. DataGolf outcome IDs + DB markets
        dg_outcome_lookup = await _lookup_datagolf_outcome_ids(
            db, tour, current_event.event_id,
        )
        logger.info("Golf grid [%s]: found %d DataGolf outcome IDs",
                    tour, sum(len(v) for v in dg_outcome_lookup.values()))

        db_markets = await _query_tournament_db_markets(
            db, config, current_event.event_name or "", tour,
        )

        # 4. Match outcomes to grid
        grid_raw, all_outcome_ids, outcome_id_to_name = _match_outcomes_to_grid(
            db_markets, config, dg_field, tour,
        )

        # 5. Add DataGolf model probabilities
        _add_datagolf_model_probs(
            grid_raw, dg_field, pre_tourney_lookup, dg_display_names,
            dg_outcome_lookup, current_event, is_live,
            all_outcome_ids, outcome_id_to_name,
        )

        # 6. Build team rows
        old_probs = await _compute_movers(db, all_outcome_ids, hours=24)
        teams = _build_golf_grid_team_rows(
            dg_field, dg_display_names, grid_raw, config, old_probs, is_live,
        )
        teams = teams[:config.max_teams]

        # Movers
        championship_col = "win"
        movers = []
        for team_row in teams:
            champ_cell = team_row["cells"].get(championship_col)
            if champ_cell and champ_cell.get("trend_24h") is not None:
                movers.append({
                    "name": team_row["name"], "short_name": team_row["short_name"],
                    "team_id": None, "column": championship_col,
                    "change_24h": champ_cell["trend_24h"],
                    "direction": "up" if champ_cell["trend_24h"] > 0 else "down",
                    "logo_url": None, "primary_color": None,
                })
        movers.sort(key=lambda m: abs(m["change_24h"]), reverse=True)
        movers = movers[:10]

        # Trend chart
        top_team_norms = [_normalize_team_name(t["name"]) for t in teams[:top]]
        trend_outcome_ids = []
        trend_outcome_names: dict[int, str] = {}
        for norm_name in top_team_norms:
            for e in grid_raw.get(championship_col, {}).get(norm_name, []):
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

        # Sources + active columns
        sources_seen = {"datagolf"}
        for col_entries in grid_raw.values():
            for entries in col_entries.values():
                for e in entries:
                    sources_seen.add(e["source"])

        active_columns = []
        min_fill = max(1, len(teams) // 10)
        for col in config.columns:
            if col.key not in grid_raw:
                continue
            filled = sum(
                1 for t in teams
                if t["cells"].get(col.key, {}).get("merged_probability") is not None
            )
            if filled >= min_fill:
                active_columns.append({
                    "key": col.key, "label": col.label,
                    "order": col.order, "sequential": col.sequential,
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


# ---------------------------------------------------------------------------
# Upcoming major tournament grid (DB-only, no DataGolf API)
# ---------------------------------------------------------------------------

# Major tournament names to surface even before they become the current event
_GOLF_MAJORS = {
    "masters tournament", "the masters",
    "pga championship",
    "u.s. open", "us open",
    "the open championship", "the open",
    "players championship", "the players",
}

# Tournament name → search tokens for matching DB markets
_MAJOR_MARKET_TOKENS: dict[str, list[str]] = {
    "Masters Tournament": ["masters", "augusta"],
    "PGA Championship": ["pga championship"],
    "U.S. Open": ["u.s. open", "us open"],
    "The Open Championship": ["the open", "open championship"],
    "THE PLAYERS Championship": ["players championship"],
}


async def _build_upcoming_golf_event_grid(
    tournament_name: str,
    start_date: str | None,
    end_date: str | None,
    course: str | None,
    location: str | None,
    country: str | None,
    config: LeagueConfig,
    db: AsyncSession,
    trend_hours: int,
    top: int,
) -> dict | None:
    """Build a golf grid for an upcoming tournament using DB markets only.

    Used for major tournaments that haven't started yet (DataGolf API
    only serves the current event, so we can't get model predictions).
    Pulls from Kalshi, Polymarket, and Odds API markets in the DB.
    """
    # Find market search tokens for this tournament
    search_tokens = []
    for major_name, tokens in _MAJOR_MARKET_TOKENS.items():
        if major_name.lower() in tournament_name.lower() or tournament_name.lower() in major_name.lower():
            search_tokens = tokens
            break
    if not search_tokens:
        # Generic: use tournament name tokens
        stopwords = {"championship", "tournament", "invitational", "the", "open"}
        search_tokens = [
            w for w in tournament_name.lower().split()
            if w not in stopwords and len(w) >= 3
        ]
    if not search_tokens:
        return None

    logger.info(
        "Building upcoming golf event grid: '%s' (tokens=%s)",
        tournament_name, search_tokens,
    )

    # Query DB for markets matching this tournament
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
            FuturesMarket.source != "datagolf",
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    all_db_markets = result.scalars().unique().all()

    # Filter to markets matching this tournament
    def matches_tournament(market_name: str) -> bool:
        name_lower = (market_name or "").lower()
        return any(tok in name_lower for tok in search_tokens)

    matched_markets = [m for m in all_db_markets if matches_tournament(m.name)]

    # Filter out garbage binary aggregates (same logic as _build_golf_tour_grid)
    db_markets = []
    for m in matched_markets:
        if (
            len(m.outcomes) > 10
            and not m.mutually_exclusive
            and m.source == "polymarket"
        ):
            prob_sum = sum(
                float(o.current_probability)
                for o in m.outcomes
                if o.current_probability
            )
            if prob_sum > 2.0:
                continue
        # Filter out esports "Masters" markets
        if "bc game" in (m.name or "").lower():
            continue
        db_markets.append(m)

    if not db_markets:
        logger.info("Upcoming golf event '%s': no matching markets", tournament_name)
        return None

    logger.info(
        "Upcoming golf event '%s': %d markets from %s",
        tournament_name,
        len(db_markets),
        sorted(set(m.source for m in db_markets)),
    )

    # Build grid from market outcomes
    # column_key → norm_name → list of {source, probability, ...}
    grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    all_outcome_ids: list[int] = []
    outcome_id_to_name: dict[int, str] = {}

    for market in db_markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                prob = float(outcome.current_probability)
            elif (outcome.current_yes_bid is not None
                  and outcome.current_yes_ask is not None
                  and float(outcome.current_yes_ask) > 0):
                prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
            else:
                continue
            if prob <= 0:
                continue

            oname = outcome.name or ""
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            # Filter prediction market 0.5 noise
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue

            norm = _normalize_team_name(oname)
            grid_raw[col_key][norm].append({
                "source": market.source,
                "probability": prob,
                "market_id": market.id,
                "outcome_id": outcome.id,
                "market_name": market.name,
                "volume_24h": market.volume_24h,
            })
            all_outcome_ids.append(outcome.id)
            outcome_id_to_name[outcome.id] = oname

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

    # Build team rows
    old_probs = await _compute_movers(db, all_outcome_ids, hours=24)
    championship_col = "win"
    teams = []

    # Get all unique golfer names from the win column (primary sort)
    all_golfer_norms = set()
    for col_entries in grid_raw.values():
        all_golfer_norms.update(col_entries.keys())

    for norm_name in all_golfer_norms:
        # Find display name from any outcome
        display_name = norm_name
        for col_key in grid_raw:
            for e in grid_raw.get(col_key, {}).get(norm_name, []):
                oid = e.get("outcome_id")
                if oid and oid in outcome_id_to_name:
                    display_name = outcome_id_to_name[oid]
                    break

        cells = {}
        for col in config.columns:
            entries = grid_raw.get(col.key, {}).get(norm_name, [])
            if not entries:
                continue

            probs = [e["probability"] for e in entries]
            vols = [e.get("volume_24h") for e in entries]
            merged = min(_merge_probabilities(probs, vols), 1.0)

            sources = []
            for e in entries:
                src = {
                    "source": e["source"],
                    "probability": round(e["probability"], 4),
                }
                if e.get("market_name"):
                    src["market_name"] = e["market_name"]
                if e.get("volume_24h") is not None:
                    src["volume_24h"] = e["volume_24h"]
                sources.append(src)

            # 24h trend
            trend_24h = None
            db_entries = [e for e in entries if e.get("outcome_id")]
            if db_entries:
                oid = db_entries[0]["outcome_id"]
                old_p = old_probs.get(oid)
                if old_p is not None:
                    trend_24h = round(merged - old_p, 4)

            cell_data = {
                "merged_probability": round(merged, 4),
                "sources": sources,
                "trend_24h": trend_24h,
            }
            if (len(sources) == 1
                    and sources[0]["source"] == "kalshi"
                    and abs(merged - 0.01) < 0.001):
                cell_data["is_minimum_tick"] = True
            cells[col.key] = cell_data

        _filter_kalshi_placement_noise(cells)

        if not cells:
            continue

        teams.append({
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
        })

    # Sort by win probability descending
    teams.sort(key=lambda t: -(t["cells"].get("win", {}).get("merged_probability", 0)))
    teams = teams[:config.max_teams]

    if not teams:
        return None

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

    # Trend chart
    top_team_norms = [_normalize_team_name(t["name"]) for t in teams[:top]]
    trend_outcome_ids = []
    trend_outcome_names: dict[int, str] = {}
    for norm_name in top_team_norms:
        entries = grid_raw.get(championship_col, {}).get(norm_name, [])
        for e in entries:
            oid = e.get("outcome_id")
            if oid and oid not in trend_outcome_names:
                trend_outcome_ids.append(oid)
                trend_outcome_names[oid] = norm_name

    trend_chart = await _build_trend_chart(
        db, trend_outcome_ids, trend_outcome_names,
        hours=trend_hours, top_n=top,
    )
    trend_chart["column"] = championship_col
    trend_chart["top"] = top

    # Sources
    sources_seen = set()
    for col_entries in grid_raw.values():
        for entries in col_entries.values():
            for e in entries:
                sources_seen.add(e["source"])

    # Active columns
    active_columns = []
    min_fill = max(1, len(teams) // 10)
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
        "tour": "pga",
        "tour_name": "PGA Tour",
        "tournament": {
            "name": tournament_name,
            "course": course,
            "start_date": start_date,
            "end_date": end_date,
            "location": location,
            "country": country,
            "status": "upcoming",
            "current_round": None,
        },
        "columns": active_columns,
        "trend_chart": trend_chart,
        "teams": teams,
        "movers": movers,
        "team_count": len(teams),
        "field_count": len(teams),
        "sources_available": sorted(sources_seen),
    }


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
async def get_playoff_grid_cached(
    league_slug: str,
    hours: int = Query(default=None, description="Trend chart window in hours"),
    top: int = Query(default=10, ge=1, le=50, description="Top N teams for trend chart"),
    debug: bool = Query(default=False, description="Include column→market debug info"),
    db: AsyncSession = Depends(get_db),
):
    """Return championship progression grid for a league (Redis-cached, 1h TTL)."""
    import json

    # Only cache default/simple requests (no debug, default params)
    cache_eligible = not debug and hours is None and top == 10
    cache_key = f"bainluck:category:playoffs:{league_slug}"

    if cache_eligible:
        from app.tasks.redis_state import get_async_redis_client
        try:
            rc = get_async_redis_client()
            cached = await rc.get(cache_key)
            if cached:
                await rc.aclose()
                return json.loads(cached)
            # Stale fallback: serve old data while recomputing
            stale = await rc.get(f"{cache_key}:stale")
            if stale:
                await rc.aclose()
                return json.loads(stale)
            await rc.aclose()
        except Exception:
            pass  # Fall through to live query

    import asyncio as _asyncio
    try:
        result = await _asyncio.wait_for(
            get_playoff_grid(league_slug, hours, top, debug, db),
            timeout=25,
        )
    except _asyncio.TimeoutError:
        return {"teams": [], "columns": [], "error": "timeout"}

    if cache_eligible:
        try:
            rc = get_async_redis_client()
            payload = json.dumps(result, default=str)
            await rc.set(cache_key, payload, ex=3600)
            await rc.set(f"{cache_key}:stale", payload, ex=86400)
            await rc.aclose()
        except Exception:
            pass

    return result


async def get_playoff_grid(
    league_slug: str,
    hours: int = None,
    top: int = 10,
    debug: bool = False,
    db: AsyncSession = None,
):
    """Return championship progression grid for a league.

    Each team row shows probabilities of reaching each playoff stage,
    sourced from Odds API, Kalshi, and Polymarket.
    """
    await db.execute(text("SET LOCAL statement_timeout = '20s'"))

    config = get_league_config(league_slug)
    if not config:
        available = get_all_league_slugs()
        raise HTTPException(
            status_code=404,
            detail=f"League '{league_slug}' not found. Available: {available}",
        )

    trend_hours = hours or config.trend_hours

    # -----------------------------------------------------------------------
    # 0. Load admin matching overrides for this league
    # -----------------------------------------------------------------------
    override_result = await db.execute(
        select(MatchingOverride).where(MatchingOverride.league_slug == league_slug)
    )
    overrides = override_result.scalars().all()

    # Build lookup structures from overrides
    alias_overrides: dict[str, str] = {}  # source_name → target_name
    exclude_teams: set[str] = set()
    for ov in overrides:
        if ov.override_type == "team_alias" and ov.decision == "approved" and ov.target_name:
            alias_overrides[_normalize_team_name(ov.source_name)] = _normalize_team_name(ov.target_name)
        elif ov.override_type == "team_exclude" and ov.decision == "approved":
            exclude_teams.add(_normalize_team_name(ov.source_name))

    if alias_overrides:
        logger.info("Loaded %d alias overrides for %s", len(alias_overrides), league_slug)
    if exclude_teams:
        logger.info("Loaded %d exclude overrides for %s", len(exclude_teams), league_slug)

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

    # Path B.1: Match by external_id ticker prefix (Kalshi markets like KXNBA%)
    if config.external_id_prefixes:
        for pfx in config.external_id_prefixes:
            sport_conditions.append(FuturesMarket.external_id.ilike(f"{pfx}%"))

    # Path B.2: Match by llm_sport_category + league name patterns (Polymarket).
    # Push league name filter to SQL via ILIKE to avoid loading ALL category markets.
    category_conditions = []
    if config.league_name_patterns:
        for pattern_str in config.league_name_patterns:
            # Convert regex to SQL ILIKE: \bNBA\b → %NBA%, \bPro\s+Basketball\b → %Pro%Basketball%
            sql_pattern = re.sub(r"\\[bs]", "", pattern_str)
            sql_pattern = re.sub(r"\\s\+|\\s\*", "%", sql_pattern)
            sql_pattern = re.sub(r"[()?\[\]^$]", "", sql_pattern)
            sql_pattern = sql_pattern.replace("\\", "").strip()
            if sql_pattern:
                category_conditions.append(
                    and_(
                        FuturesMarket.llm_sport_category == config.sport_category,
                        FuturesMarket.name.ilike(f"%{sql_pattern}%"),
                    )
                )
    if not category_conditions:
        category_conditions.append(FuturesMarket.llm_sport_category == config.sport_category)

    # Ticker-prefixed markets (Kalshi/OddsAPI) can be resolved (e.g., division
    # winners after regular season). Category-matched (Polymarket) stay open/closed
    # to avoid loading thousands of resolved markets.
    ticker_filter = or_(*sport_conditions) if sport_conditions else None
    category_filter = or_(*category_conditions) if category_conditions else None

    status_conditions = []
    if ticker_filter is not None:
        status_conditions.append(and_(ticker_filter, FuturesMarket.status.in_(("open", "closed", "resolved"))))
    if category_filter is not None:
        status_conditions.append(and_(category_filter, FuturesMarket.status.in_(("open", "closed"))))
    market_filter_with_status = or_(*status_conditions) if status_conditions else FuturesMarket.status.in_(("open", "closed"))
    # Keep the original market_filter for the resolved backfill (which adds its own status filter)
    market_filter = or_(*sport_conditions, *category_conditions) if sport_conditions or category_conditions else None

    stmt = (
        select(FuturesMarket)
        .where(
            market_filter_with_status,
        )
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    all_markets = result.scalars().unique().all()

    # Filter by league name patterns (Python-side) to separate e.g. NBA from NCAAB
    league_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.league_name_patterns
    ] if config.league_name_patterns else []
    league_exclude = [
        re.compile(p, re.IGNORECASE) for p in config.league_exclude_patterns
    ] if config.league_exclude_patterns else []

    # Gender exclusion: Men's leagues should not include Women's markets and vice versa
    _WOMENS_RE = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
    _MENS_RE = re.compile(r"\bMen.?s\b", re.IGNORECASE)
    is_mens_league = config.slug in ("ncaa-basketball", "ncaa-football", "nba", "nhl", "nfl", "mlb")
    is_womens_league = config.slug in ("wnba", "ncaa-women-basketball")

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
        # Path B.1: Check external_id prefix (e.g., Kalshi tickers like KXMARMADROUND)
        if config.external_id_prefixes and eid:
            if any(eid.startswith(pfx) for pfx in config.external_id_prefixes):
                markets.append(market)
                continue
        # Path B.2: Match by league name pattern in market name
        if league_patterns:
            if any(pat.search(name) for pat in league_patterns) and \
               not any(excl.search(name) for excl in league_exclude):
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

    # -----------------------------------------------------------------------
    # 1b. Filter out non-current-season markets
    # -----------------------------------------------------------------------
    # Markets from other seasons contaminate the grid.  Two failure modes:
    #
    # Future seasons: "NBA: 2027 Champion" has systematically lower
    # probabilities (preseason lines), so the per-source dedup (keep lowest
    # prob) picks the wrong entry.
    #
    # Past seasons: "2024-25 NBA Champion" outcomes are settled near 0%/1%.
    # When a resolved past-season market and a fresh current-season market
    # both map to the championship column from the same source, the min()
    # dedup picks the stale ~1% value instead of the live ~30% value.
    # This caused 30x staleness on the NBA grid (issue #708).
    _season_max_year = _extract_season_max_year(config.season_pattern)
    if _season_max_year:
        before_filter = len(markets)
        markets = [
            m for m in markets
            if not _is_future_season_market(m.name or "", _season_max_year)
            and not _is_past_season_market(m.name or "", _season_max_year)
        ]
        filtered_season = before_filter - len(markets)
        if filtered_season:
            logger.info(
                "Playoff grid %s: filtered %d non-current-season markets (max_year=%d)",
                league_slug, filtered_season, _season_max_year,
            )

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
    _stale_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    # Settled columns (make_playoffs, division) stop trading after regular
    # season ends — prices stay at 99.5%/0.5% with no updates for weeks.
    # Use a much longer cutoff for these columns.
    _settled_cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    _SETTLED_COLUMNS = {"make_playoffs", "division"}
    _stale_skipped = 0

    for market in markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        cutoff = _settled_cutoff if col_key in _SETTLED_COLUMNS else _stale_cutoff
        for outcome in market.outcomes:
            if outcome.last_updated and outcome.last_updated < cutoff:
                _stale_skipped += 1
                continue
            if outcome.current_probability is not None:
                prob = float(outcome.current_probability)
            elif (outcome.current_yes_bid is not None
                  and outcome.current_yes_ask is not None
                  and float(outcome.current_yes_ask) > 0):
                # Fallback: compute from bid/ask when current_probability
                # wasn't written (e.g. during API format migrations).
                prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
            else:
                continue
            if prob <= 0 or prob >= 1.0:
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
            # Kalshi and Polymarket.  But skip this filter when bid/ask data
            # shows real trading activity (bid > 0 means someone placed a
            # real order, not just a default).
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue

            column_data[col_key].append((market, outcome))

    if _stale_skipped:
        logger.info(
            "Playoff grid %s: skipped %d stale outcomes (>7 days old)",
            league_slug, _stale_skipped,
        )

    # Backfill empty columns from resolved markets (e.g., make_playoffs after
    # regular season ends). Non-critical — grid works without it.
    empty_cols = [c for c in config.columns if not column_data.get(c.key)]
    logger.info("Grid %s: empty columns=%s", league_slug, [c.key for c in empty_cols])
    if empty_cols:
      try:
        resolved_stmt = (
            select(FuturesMarket)
            .where(
                market_filter,
                FuturesMarket.status == "resolved",
                FuturesMarket.market_tier.in_([1, 2, 3, 4]),
            )
            .options(selectinload(FuturesMarket.outcomes))
            .limit(50)
        )
        resolved_result = await db.execute(resolved_stmt)
        resolved_markets = resolved_result.scalars().unique().all()
        logger.info("Grid %s: resolved backfill found %d markets", league_slug, len(resolved_markets))
        for market in resolved_markets:
            if league_patterns and not any(p.search(market.name or "") for p in league_patterns):
                logger.debug("Grid %s backfill: %s rejected by league_patterns", league_slug, market.name[:40])
                continue
            if league_exclude and any(p.search(market.name or "") for p in league_exclude):
                logger.debug("Grid %s backfill: %s rejected by league_exclude", league_slug, market.name[:40])
                continue
            col_key = _match_market_to_column(market, config)
            logger.info("Grid %s backfill: %s (id=%d, tier=%s) → col=%s (empty=%s)",
                        league_slug, market.name[:40], market.id, market.market_tier,
                        col_key, [c.key for c in empty_cols])
            if col_key and col_key in [c.key for c in empty_cols]:
                for outcome in market.outcomes:
                    if outcome.is_winner is True:
                        outcome.current_probability = 1.0
                    if outcome.current_probability is None or float(outcome.current_probability) <= 0:
                        continue
                    oname = outcome.name or ""
                    if _NON_PLAYOFF_MARKET_RE.search(oname):
                        continue
                    if oname.lower().strip() in ("yes", "no", "over", "under"):
                        continue
                    column_data[col_key].append((market, outcome))
        if resolved_markets:
            logger.info("Playoff grid %s: backfilled %d resolved markets for empty columns %s",
                        league_slug, len(resolved_markets), [c.key for c in empty_cols])
      except Exception as e:
        logger.warning("Playoff grid %s: resolved backfill failed (non-critical): %s", league_slug, e)

    # Log column coverage + per-market breakdown for debugging
    for col in config.columns:
        entries = column_data.get(col.key, [])
        count = len(entries)
        logger.info("  Column %s (%s): %d outcome entries", col.key, col.label, count)
        # Log distinct markets feeding this column
        market_names: dict[int, str] = {}
        for market, outcome in entries:
            if market.id not in market_names:
                market_names[market.id] = f"{market.source}:{market.name}"
        if market_names:
            for mid, mname in list(market_names.items())[:10]:
                logger.info("    → market %d: %s", mid, mname)

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
                "market_name": market.name,
                "volume_24h": market.volume_24h,
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

    # First, apply admin alias overrides (highest priority — manual decisions)
    for alias_src, alias_tgt in alias_overrides.items():
        if alias_src in grid_raw and alias_tgt in grid_raw:
            for col_key, entries in grid_raw[alias_src].items():
                grid_raw[alias_tgt][col_key].extend(entries)
            del grid_raw[alias_src]
            logger.info("Applied admin alias override: '%s' → '%s'", alias_src, alias_tgt)
        elif alias_src in grid_raw and alias_tgt not in grid_raw:
            # Rename: source exists but target doesn't — just rename
            grid_raw[alias_tgt] = grid_raw.pop(alias_src)
            logger.info("Applied admin alias rename: '%s' → '%s'", alias_src, alias_tgt)

    norm_names = sorted(grid_raw.keys(), key=len, reverse=True)  # longest first
    merge_map: dict[str, str] = {}  # short_name → long_name

    # Abbreviation expansions for team name merging.
    # Single-word expansions keep both forms; multi-word expansions
    # replace the abbreviation (so subset check works correctly).
    _ABBREV_MAP = {
        "st": ["state"],
        "state": ["st"],
        "ws": ["white", "sox"],
    }

    def _expand_abbrevs(words):
        expanded = set()
        for w in words:
            expansion = _ABBREV_MAP.get(w)
            if expansion and len(expansion) > 1:
                # Multi-word: replace abbreviation with expansion
                expanded.update(expansion)
            elif expansion:
                # Single-word: keep both forms
                expanded.add(w)
                expanded.update(expansion)
            else:
                expanded.add(w)
        return expanded

    for i, long_name in enumerate(norm_names):
        for short_name in norm_names[i + 1:]:
            if short_name in merge_map:
                continue
            # 1. Prefix merge (single-word safe via location modifier check)
            if _should_prefix_merge(short_name, long_name):
                merge_map[short_name] = long_name
            # 2. Single-letter abbreviation suffix
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
            # 3. Word subset merge (e.g., "michigan state" vs "michigan st spartans")
            elif len(short_name.split()) >= 2:
                short_words = set(short_name.split())
                long_words = set(long_name.split())
                short_expanded = _expand_abbrevs(short_words)
                if short_expanded.issubset(_expand_abbrevs(long_words)):
                    merge_map[short_name] = long_name
            # 4. Alias-based merge (e.g., "connecticut" ↔ "uconn huskies")
            if short_name not in merge_map and _alias_matches(short_name, long_name):
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

    # Get team metadata — collect ALL unique display names + norm names
    # for the broadest possible Team table lookup
    team_names_raw = set()
    for norm_name in grid_raw:
        team_names_raw.add(norm_name)  # Include normalized name itself
        for col_entries in grid_raw[norm_name].values():
            for entry in col_entries:
                oid = entry["outcome_id"]
                if oid in outcome_id_to_name:
                    team_names_raw.add(outcome_id_to_name[oid])

    team_meta = await _get_team_metadata(
        db,
        team_names_raw,
        league_slug=config.slug,
        conference_field=config.conference_field,
    )

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

            # Deduplicate entries from same source — if two markets from
            # the same source (e.g., two Kalshi markets) map to the same
            # column for the same team, average them into one entry.
            deduped_entries: list[dict] = []
            source_groups: dict[str, list[dict]] = defaultdict(list)
            for e in entries:
                source_groups[e["source"]].append(e)
            for source, group in source_groups.items():
                if len(group) == 1:
                    deduped_entries.append(group[0])
                else:
                    # Average probabilities from same source
                    avg_prob = sum(g["probability"] for g in group) / len(group)
                    # Keep the entry with the highest probability as the "primary"
                    best = max(group, key=lambda g: g["probability"])
                    deduped_entries.append({
                        **best,
                        "probability": avg_prob,
                    })

            probs = [e["probability"] for e in deduped_entries]
            corrected = _correct_inverted_probs(probs)
            merged = min(_merge_probabilities(probs), 1.0)

            sources = []
            for e, corrected_p in zip(deduped_entries, corrected):
                src = {
                    "source": e["source"],
                    "probability": round(min(corrected_p, 1.0), 4),
                }
                if e.get("market_name"):
                    src["market_name"] = e["market_name"]
                sources.append(src)

            # Compute 24h trend from the championship outcome
            trend_24h = None
            if entries:
                # Use the first outcome's old probability
                oid = entries[0]["outcome_id"]
                old_p = old_probs.get(oid)
                if old_p is not None:
                    trend_24h = round(merged - old_p, 4)

            cell_data = {
                "merged_probability": round(merged, 4),
                "sources": sources,
                "trend_24h": trend_24h,
            }
            # Kalshi's minimum tick is 0.01 (1%). When a cell is exactly at the
            # minimum and Kalshi is the only source, flag it so the frontend
            # can display "< 1%" instead of a misleading "1.0%".
            if (len(sources) == 1
                    and sources[0]["source"] == "kalshi"
                    and abs(merged - 0.01) < 0.001):
                cell_data["is_minimum_tick"] = True
            cells[col.key] = cell_data

        # ---- Kalshi noise filter + monotonicity enforcement ----
        # Kalshi binary markets default to ~0.50-0.60 when illiquid.
        # For single-source Kalshi cells where the probability looks like
        # noise (0.45-0.65), remove the cell unless a prior sequential
        # column already has a high probability that makes this plausible.
        seq_cols = [c for c in config.columns if c.sequential]
        seq_keys = [c.key for c in sorted(seq_cols, key=lambda c: c.order)]

        for col_key in seq_keys:
            cell = cells.get(col_key)
            if not cell:
                continue
            srcs = cell.get("sources", [])
            prob = cell["merged_probability"]
            # Single-source Kalshi noise: probability in the 0.45-0.65 range
            # with no corroboration from another source
            if (len(srcs) == 1
                    and srcs[0]["source"] == "kalshi"
                    and 0.45 <= prob <= 0.65):
                # Check if a later column (closer to championship) has a
                # non-noise probability that makes this plausible.
                # If so, this team is real and the probability is genuine.
                col_idx = seq_keys.index(col_key)
                has_later_data = any(
                    cells.get(sk) is not None
                    for sk in seq_keys[col_idx + 1:]
                )
                if not has_later_data:
                    del cells[col_key]

        # Monotonicity: in sequential columns, P(round N) >= P(round N+1).
        # Cap later rounds to the min of earlier rounds.
        if len(seq_keys) >= 2:
            for i in range(1, len(seq_keys)):
                prev_key = seq_keys[i - 1]
                curr_key = seq_keys[i]
                prev_cell = cells.get(prev_key)
                curr_cell = cells.get(curr_key)
                if prev_cell and curr_cell:
                    prev_p = prev_cell["merged_probability"]
                    curr_p = curr_cell["merged_probability"]
                    if curr_p > prev_p:
                        curr_cell["merged_probability"] = prev_p
                        # Also cap individual source probabilities
                        for src in curr_cell.get("sources", []):
                            if src["probability"] > prev_p:
                                src["probability"] = round(prev_p, 4)

        if not cells:
            continue

        # Fallback: try bracket lookup on display_name if meta didn't have region
        region = meta.get("region")
        seed = meta.get("seed")
        if league_slug == "ncaa-basketball" and not region:
            bracket_info = _lookup_ncaa_bracket(display_name)
            if bracket_info:
                region = bracket_info["region"]
                seed = seed or bracket_info["seed"]
        elif league_slug == "ncaa-women-basketball" and not region:
            bracket_info = _lookup_wncaa_bracket(display_name)
            if bracket_info:
                region = bracket_info["region"]
                seed = seed or bracket_info["seed"]

        conference = meta.get("conference")

        team_row = {
            "name": display_name,
            "short_name": meta.get("short_name") or display_name,
            "team_id": meta.get("team_id"),
            "logo_url": meta.get("logo_url"),
            "primary_color": meta.get("primary_color"),
            "secondary_color": meta.get("secondary_color"),
            "record": meta.get("record"),
            "conference": conference,
            "division": meta.get("division"),
            "region": region,
            "seed": seed,
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

    from app.utils.playoff_grid import normalize_column_sums, enforce_monotonicity
    normalize_column_sums(teams, config.columns, config.slug)

    # Re-enforce monotonicity after normalization — normalize_column_sums can
    # scale conference probabilities upward (to sum to 200%), breaking the
    # per-team monotonicity that was enforced during cell building.
    mono_fixes = enforce_monotonicity(teams, config.columns)
    if mono_fixes:
        logger.info(
            "Playoff grid %s: fixed %d monotonicity violations after normalization",
            league_slug, mono_fixes,
        )

    # -----------------------------------------------------------------------
    # 4c. Apply admin exclude overrides
    # -----------------------------------------------------------------------
    if exclude_teams:
        before_count = len(teams)
        teams = [
            t for t in teams
            if _normalize_team_name(t["name"]) not in exclude_teams
        ]
        excluded_count = before_count - len(teams)
        if excluded_count:
            logger.info("Excluded %d teams via admin overrides for %s", excluded_count, league_slug)

    # -----------------------------------------------------------------------
    # 4d. NCAA Tournament: filter to bracket teams only
    # -----------------------------------------------------------------------
    # For tournament grids, only show teams actually in the bracket.
    # Non-bracket teams appear because championship markets (Odds API)
    # include the full league, not just tournament qualifiers.
    if league_slug == "ncaa-basketball" and NCAA_2026_BRACKET:
        before_count = len(teams)
        bracket_norms = {_normalize_team_name(t) for t in NCAA_2026_BRACKET}

        def _in_bracket(team_row: dict) -> bool:
            norm = _normalize_team_name(team_row["name"])
            if norm in bracket_norms:
                return True
            # Fuzzy: check if any bracket name contains or is contained by this name
            for bn in bracket_norms:
                if bn in norm or norm in bn:
                    return True
                # Word overlap: at least 2 common words
                tw = set(norm.split())
                bw = set(bn.split())
                if len(tw & bw) >= 2:
                    return True
            return False

        teams = [t for t in teams if _in_bracket(t)]
        filtered_count = before_count - len(teams)
        if filtered_count:
            logger.info(
                "Filtered %d non-bracket teams for %s (kept %d)",
                filtered_count, league_slug, len(teams),
            )

    if league_slug == "ncaa-women-basketball" and WNCAA_2026_BRACKET:
        before_count = len(teams)
        bracket_norms = {_normalize_team_name(t) for t in WNCAA_2026_BRACKET}

        def _in_wbracket(team_row: dict) -> bool:
            norm = _normalize_team_name(team_row["name"])
            if norm in bracket_norms:
                return True
            for bn in bracket_norms:
                if bn in norm or norm in bn:
                    return True
                tw = set(norm.split())
                bw = set(bn.split())
                if len(tw & bw) >= 2:
                    return True
            return False

        teams = [t for t in teams if _in_wbracket(t)]
        filtered_count = before_count - len(teams)
        if filtered_count:
            logger.info(
                "Filtered %d non-bracket teams for %s (kept %d)",
                filtered_count, league_slug, len(teams),
            )

    # -----------------------------------------------------------------------
    # 5. Sort teams
    # -----------------------------------------------------------------------

    from app.utils.playoff_grid import sort_teams_by_championship
    teams = sort_teams_by_championship(teams, championship_col, config.max_teams)

    # -----------------------------------------------------------------------
    # 6. Compute biggest movers (top 5 up, top 5 down)
    # -----------------------------------------------------------------------

    from app.utils.playoff_grid import compute_movers
    movers = compute_movers(teams, championship_col)

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

    # Only include columns that have data, with per-column market_id
    active_columns = []
    for col in config.columns:
        if col.key in column_data:
            # Find the most common market_id for this column
            col_market_ids = [m.id for m, _ in column_data[col.key]]
            col_market_id = Counter(col_market_ids).most_common(1)[0][0] if col_market_ids else None
            # Deduplicated list of all market IDs for cross-source aggregation
            col_market_ids_unique = sorted(set(col_market_ids))
            active_columns.append({
                "key": col.key,
                "label": col.label,
                "order": col.order,
                "sequential": col.sequential,
                "market_id": col_market_id,
                "market_ids": col_market_ids_unique,
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
                # Only add "Conference" suffix for directional names (Eastern/Western)
                # and league names (American/National). Don't suffix named conferences
                # like "SEC", "Big Ten", "ACC", etc.
                conf_norm = conf.strip()
                _CONF_SUFFIX_NAMES = {"eastern", "western", "american", "national"}
                if (conf_norm
                    and not conf_norm.lower().endswith("conference")
                    and not conf_norm.lower().endswith("league")
                    and conf_norm.lower() in _CONF_SUFFIX_NAMES):
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

    # -----------------------------------------------------------------------
    # 10. Extract championship market_id for evolution chart
    # -----------------------------------------------------------------------
    championship_market_id = None
    champ_market_ids: list[int] = []
    for norm_name in grid_raw:
        entries = grid_raw[norm_name].get(championship_col, [])
        for e in entries:
            if e.get("market_id"):
                champ_market_ids.append(e["market_id"])
    if champ_market_ids:
        # Pick the most common market_id (the main championship market)
        championship_market_id = Counter(champ_market_ids).most_common(1)[0][0]

    resp = {
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
        "championship_market_id": championship_market_id,
    }

    # Debug mode: include which markets feed each column
    if debug:
        debug_columns: dict[str, list[dict]] = {}
        for col_key, entries in column_data.items():
            seen_markets: dict[int, dict] = {}
            for market, outcome in entries:
                if market.id not in seen_markets:
                    seen_markets[market.id] = {
                        "market_id": market.id,
                        "source": market.source,
                        "name": market.name,
                        "external_id": market.external_id[:50] if market.external_id else None,
                        "outcome_count": 0,
                        "sample_outcomes": [],
                    }
                seen_markets[market.id]["outcome_count"] += 1
                if len(seen_markets[market.id]["sample_outcomes"]) < 3:
                    seen_markets[market.id]["sample_outcomes"].append({
                        "name": outcome.name,
                        "prob": float(outcome.current_probability) if outcome.current_probability else None,
                    })
            debug_columns[col_key] = list(seen_markets.values())
        resp["_debug_column_markets"] = debug_columns

    return resp


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


# ---------------------------------------------------------------------------
# Sport key → league config mapping (for event detail integration)
# ---------------------------------------------------------------------------

_SPORT_KEY_TO_LEAGUE_SLUG: dict[str, str] = {
    "basketball_nba": "nba",
    "basketball_ncaab": "ncaa-basketball",
    "basketball_wnba": "wnba",
    "americanfootball_nfl": "nfl",
    "americanfootball_ncaaf": "ncaa-football",
    "icehockey_nhl": "nhl",
    "baseball_mlb": "mlb",
    "soccer_usa_mls": "mls",
    "soccer_epl": "epl",
    "soccer_spain_la_liga": "la-liga",
    "soccer_uefa_champs_league": "champions-league",
    "soccer_germany_bundesliga": "bundesliga",
}


def get_league_config_for_sport_key(sport_key: str) -> LeagueConfig | None:
    """Map an Odds API sport key to a league config."""
    slug = _SPORT_KEY_TO_LEAGUE_SLUG.get(sport_key)
    if slug:
        return get_league_config(slug)
    return None


async def get_team_progression_for_event(
    db: AsyncSession,
    event_id: int,
    home_team_name: str,
    away_team_name: str,
    sport_key: str,
) -> dict | None:
    """Build team progression data for an event's two teams (Redis-cached, 15 min TTL).

    Returns a compact response with each team's championship grid row,
    or None if no league config exists for this sport.
    """
    import json

    cache_key = f"bainluck:team_progression:{event_id}"
    from app.tasks.redis_state import get_async_redis_client
    try:
        rc = get_async_redis_client()
        cached = await rc.get(cache_key)
        await rc.aclose()
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    result = await _get_team_progression_for_event_uncached(
        db, event_id, home_team_name, away_team_name, sport_key,
    )

    if result is not None:
        try:
            rc = get_async_redis_client()
            await rc.set(cache_key, json.dumps(result, default=str), ex=900)
            await rc.aclose()
        except Exception:
            pass

    return result


async def _get_team_progression_for_event_uncached(
    db: AsyncSession,
    event_id: int,
    home_team_name: str,
    away_team_name: str,
    sport_key: str,
) -> dict | None:
    """Build team progression data (uncached implementation)."""
    config = get_league_config_for_sport_key(sport_key)
    if not config:
        return None

    # Golf doesn't have team progression in the same way
    if config.slug == "golf":
        return None

    # Query markets using the same strategy as get_playoff_grid
    sport_conditions = []
    for sk in config.sport_keys:
        sport_conditions.append(FuturesMarket.external_id.ilike(f"{sk}%"))

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

    # Filter by league name patterns
    league_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.league_name_patterns
    ] if config.league_name_patterns else []

    _WOMENS_RE = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
    _MENS_RE = re.compile(r"\bMen.?s\b", re.IGNORECASE)
    is_mens_league = config.slug in ("ncaa-basketball", "ncaa-football", "nba", "nhl", "nfl", "mlb")
    is_womens_league = config.slug in ("wnba", "ncaa-women-basketball")

    markets = []
    for market in all_markets:
        eid = market.external_id or ""
        name = market.name or ""

        if is_mens_league and _WOMENS_RE.search(name):
            continue
        if is_womens_league and _MENS_RE.search(name) and not _WOMENS_RE.search(name):
            continue

        if any(eid.lower().startswith(sk.lower()) for sk in config.sport_keys):
            markets.append(market)
            continue
        if config.external_id_prefixes and eid:
            if any(eid.startswith(pfx) for pfx in config.external_id_prefixes):
                markets.append(market)
                continue
        if league_patterns:
            if any(pat.search(name) for pat in league_patterns):
                if config.slug == "champions-league" and re.search(
                    r"\b(?:qualif|spot|place|make.*champions|top\s*\d)\b",
                    name, re.IGNORECASE,
                ):
                    continue
                markets.append(market)
        elif not league_patterns:
            markets.append(market)

    # Filter out non-current-season markets (same logic as main grid endpoint)
    _prog_season_max = _extract_season_max_year(config.season_pattern)
    if _prog_season_max:
        markets = [
            m for m in markets
            if not _is_future_season_market(m.name or "", _prog_season_max)
            and not _is_past_season_market(m.name or "", _prog_season_max)
        ]

    # Match markets to columns and extract outcomes
    column_data: dict[str, list[tuple]] = defaultdict(list)

    for market in markets:
        col_key = _match_market_to_column(market, config)
        if not col_key:
            continue

        for outcome in market.outcomes:
            if outcome.current_probability is not None:
                prob = float(outcome.current_probability)
            elif (outcome.current_yes_bid is not None
                  and outcome.current_yes_ask is not None
                  and float(outcome.current_yes_ask) > 0):
                prob = (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2
            else:
                continue
            if prob <= 0 or prob >= 1.0:
                continue
            oname = outcome.name or ""
            if _NON_PLAYOFF_MARKET_RE.search(oname):
                continue
            if oname.lower().strip() in ("yes", "no", "over", "under"):
                continue
            if re.search(r"\band\b", oname, re.IGNORECASE) and \
               not re.search(r"\bTrail\s+Blazers\b", oname, re.IGNORECASE):
                if re.match(r"^[\w\s.]+ and [\w\s.]+$", oname.strip()):
                    continue
            if re.match(r"^#?\d+", oname.strip()):
                continue
            if config.sport_category == "soccer" and oname.strip() in _COUNTRY_NAMES:
                continue
            if market.source in ("kalshi", "polymarket") and abs(prob - 0.5) < 0.02:
                has_real_activity = (
                    outcome.current_yes_bid is not None
                    and float(outcome.current_yes_bid) > 0
                )
                if not has_real_activity:
                    continue

            column_data[col_key].append((market, outcome))

    # Build raw grid (same merging as full grid builder)
    grid_raw: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    all_outcome_ids: list[int] = []

    for col_key, entries in column_data.items():
        for market, outcome in entries:
            norm = _normalize_team_name(outcome.name)
            source_entry = {
                "source": market.source,
                "probability": float(outcome.current_probability)
                    if outcome.current_probability is not None
                    else (float(outcome.current_yes_bid) + float(outcome.current_yes_ask)) / 2,
                "market_id": market.id,
                "outcome_id": outcome.id,
                "market_name": market.name,
            }
            grid_raw[norm][col_key].append(source_entry)
            all_outcome_ids.append(outcome.id)

    # Deduplicate within same source per team+column (keep lowest prob)
    for norm_name in grid_raw:
        for col_key in grid_raw[norm_name]:
            entries = grid_raw[norm_name][col_key]
            if len(entries) <= 1:
                continue
            by_source: dict[str, list[dict]] = defaultdict(list)
            for e in entries:
                by_source[e["source"]].append(e)
            deduped = []
            for source, source_entries in by_source.items():
                best = min(source_entries, key=lambda e: e["probability"])
                deduped.append(best)
            grid_raw[norm_name][col_key] = deduped

    # Merge duplicate team names (prefix, word subset, alias)
    norm_names = sorted(grid_raw.keys(), key=len, reverse=True)
    merge_map: dict[str, str] = {}

    def _expand_abbrevs_local(words):
        expanded = set()
        for w in words:
            expanded.add(w)
            if w == "st":
                expanded.add("state")
            elif w == "state":
                expanded.add("st")
        return expanded

    for i, long_name in enumerate(norm_names):
        for short_name in norm_names[i + 1:]:
            if short_name in merge_map:
                continue
            if _should_prefix_merge(short_name, long_name):
                merge_map[short_name] = long_name
            elif len(short_name.split()) >= 2:
                short_words = set(short_name.split())
                long_words = set(long_name.split())
                if _expand_abbrevs_local(short_words).issubset(_expand_abbrevs_local(long_words)):
                    merge_map[short_name] = long_name
            if short_name not in merge_map and _alias_matches(short_name, long_name):
                merge_map[short_name] = long_name

    for short_name, long_name in merge_map.items():
        if short_name in grid_raw and long_name in grid_raw:
            for col_key, entries in grid_raw[short_name].items():
                grid_raw[long_name][col_key].extend(entries)
            del grid_raw[short_name]

    # Find the two teams from the event in the grid
    home_norm = _normalize_team_name(home_team_name)
    away_norm = _normalize_team_name(away_team_name)

    def _find_team_in_grid(team_name: str) -> str | None:
        """Find a team's normalized name in the grid, with fuzzy matching."""
        norm = _normalize_team_name(team_name)
        # Exact match
        if norm in grid_raw:
            return norm
        # Prefix/substring match
        for grid_name in grid_raw:
            if _should_prefix_merge(norm, grid_name) or _should_prefix_merge(grid_name, norm):
                return grid_name
            # Word subset match
            if len(norm.split()) >= 2:
                norm_words = set(norm.split())
                grid_words = set(grid_name.split())
                if _expand_abbrevs_local(norm_words).issubset(_expand_abbrevs_local(grid_words)):
                    return grid_name
                if _expand_abbrevs_local(grid_words).issubset(_expand_abbrevs_local(norm_words)):
                    return grid_name
            # Alias match
            if _alias_matches(norm, grid_name):
                return grid_name
        return None

    home_grid_name = _find_team_in_grid(home_team_name)
    away_grid_name = _find_team_in_grid(away_team_name)

    if not home_grid_name and not away_grid_name:
        return None  # Neither team found in any championship grid

    # Get team metadata
    team_names_raw = set()
    for name in [home_team_name, away_team_name]:
        team_names_raw.add(name)
        team_names_raw.add(_normalize_team_name(name))
    if home_grid_name:
        team_names_raw.add(home_grid_name)
    if away_grid_name:
        team_names_raw.add(away_grid_name)
    team_meta = await _get_team_metadata(
        db,
        team_names_raw,
        league_slug=config.slug,
        conference_field=config.conference_field,
    )

    # Compute 24h changes
    relevant_outcome_ids = []
    if home_grid_name:
        for col_entries in grid_raw.get(home_grid_name, {}).values():
            for e in col_entries:
                relevant_outcome_ids.append(e["outcome_id"])
    if away_grid_name:
        for col_entries in grid_raw.get(away_grid_name, {}).values():
            for e in col_entries:
                relevant_outcome_ids.append(e["outcome_id"])
    old_probs = await _compute_movers(db, relevant_outcome_ids, hours=24)

    def _build_team_row(grid_name: str | None, display_name: str) -> dict | None:
        if not grid_name or grid_name not in grid_raw:
            return None

        col_map = grid_raw[grid_name]
        meta = team_meta.get(grid_name, {}) or team_meta.get(_normalize_team_name(display_name), {})

        stages = []
        for col in config.columns:
            entries = col_map.get(col.key, [])
            if not entries:
                stages.append({
                    "key": col.key,
                    "label": col.label,
                    "probability": None,
                    "trend_24h": None,
                    "sources": [],
                })
                continue

            probs = [e["probability"] for e in entries]
            vols = [e.get("volume_24h") for e in entries]
            corrected = _correct_inverted_probs(probs)
            merged = min(_merge_probabilities(probs, vols), 1.0)

            sources = []
            for e, corrected_p in zip(entries, corrected):
                src = {
                    "source": e["source"],
                    "probability": round(min(corrected_p, 1.0), 4),
                }
                if e.get("market_name"):
                    src["market_name"] = e["market_name"]
                if e.get("volume_24h") is not None:
                    src["volume_24h"] = e["volume_24h"]
                sources.append(src)

            trend_24h = None
            oid = entries[0]["outcome_id"]
            old_p = old_probs.get(oid)
            if old_p is not None:
                trend_24h = round(merged - old_p, 4)

            stages.append({
                "key": col.key,
                "label": col.label,
                "probability": round(merged, 4),
                "trend_24h": trend_24h,
                "sources": sources,
            })

        return {
            "name": display_name,
            "short_name": meta.get("short_name") or display_name.split()[-1],
            "team_id": meta.get("team_id"),
            "logo_url": meta.get("logo_url"),
            "primary_color": meta.get("primary_color"),
            "secondary_color": meta.get("secondary_color"),
            "record": meta.get("record"),
            "conference": meta.get("conference"),
            "stages": stages,
        }

    home_row = _build_team_row(home_grid_name, home_team_name)
    away_row = _build_team_row(away_grid_name, away_team_name)

    return {
        "event_id": event_id,
        "league": config.slug,
        "league_name": config.name,
        "grid_url": f"/playoffs/{config.slug}",
        "columns": [
            {"key": c.key, "label": c.label, "order": c.order}
            for c in config.columns
        ],
        "home_team": home_row,
        "away_team": away_row,
    }
