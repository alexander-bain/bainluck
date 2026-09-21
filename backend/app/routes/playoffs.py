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

from app.config.league_configs import (
    LeagueConfig,
    get_league_config,
    get_all_league_slugs,
    resolve_league_slug,
)
from app.models import (
    FuturesMarket,
    FuturesOddsSnapshot,
    FuturesOutcome,
    MatchingOverride,
    Team,
)
from app.services import get_db
from app.utils.db_cancellation import is_query_canceled
from app.utils.futures_unsupported_price import price_refuted_by_live_book  # #6532
from app.utils.futures_liveness import leg_is_graded  # #7387
from app.utils.tournament_stages import classify_market_stage, get_stages_for_sport
from app.utils.static_divisions import canonical_conference as _canonical_conference
from app.utils.static_divisions import canonical_division as _canonical_division
from app.utils.static_divisions import grid_conference_key as _grid_conference_key
from app.utils.static_divisions import lookup_division as _static_lookup_division
from app.utils.grid_register import GridRegister, load_register
from app.utils.odds_math import devig_consensus
# #7076: the one implementation of the stage bound. `playoff_grid` imports
# nothing but logging/re, so this is import-safe at module level, and a
# module-level name is what stops the per-team pass and the post-normalization
# pass from ever again being two different rules.
from app.utils.playoff_grid import enforce_monotonicity as _grid_enforce_monotonicity
from app.utils.regex_to_ilike import regex_to_ilike
from app.utils.team_short_name import compact_team_label  # #7798

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

    Merge only if the next word in long_name is NOT a location modifier
    (prevents Iowa→Iowa State, Tennessee→Tennessee Tech).

    #7821: the modifier check used to be skipped for multi-word short names
    (`if len(short_words) >= 2: return True` returned before reaching it), so
    the docstring above described a guard that ran on one input shape out of
    two and `north carolina` prefix-merged into `north carolina st` — a
    different school. The word count of the SHORT name says nothing about
    whether the remainder of the LONG one is a mascot or another institution,
    which is the only question this predicate asks, so it no longer branches
    on it. Measured over the live NCAAB key set (351 keys) the widened guard
    moves nothing today — it removes a latent trap that the longest-first
    ordering happened to mask, not a live merge.
    """
    if not (long_name.startswith(short_name + " ") or long_name.startswith(short_name + "-")):
        return False
    rest = long_name[len(short_name):].strip().lstrip("-").split()
    if rest and rest[0].lower() in _LOCATION_MODIFIERS:
        return False
    return True


def _ticker_suffix(outcome_external_id: str | None, market_external_id: str | None) -> str | None:
    """The per-team tail of a venue ticker: ``KXMARMADROUND-27R32-FLA`` → ``FLA``.

    Split on the MARKET's own ticker rather than on the last ``-``: Loyola
    Chicago is ``KXMARMADROUND-27R32-L-IL``, whose tail is ``L-IL``, not ``IL``.

    Returns None for any source that does not key its outcomes off the market
    ticker. odds_api stores the outcome NAME in ``external_id``
    (``"Florida Gators"``), so it never satisfies the prefix test and never
    contributes a false anchor.
    """
    if not outcome_external_id or not market_external_id:
        return None
    prefix = market_external_id + "-"
    if not outcome_external_id.startswith(prefix):
        return None
    return outcome_external_id[len(prefix):] or None


def _canon_ticker(value: str | None) -> str:
    """Upper-case, alphanumerics only — so ``TA&M`` and ``ta&m`` compare equal."""
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


# #7829. Venue ticker suffix → our ``Team.abbreviation``, for the cases where
# the two spell ONE identifier differently by more than punctuation. Kalshi
# tickers Texas A&M ``TXAM`` (``KXMARMADROUND-27R32-TXAM``); our abbreviation is
# ``TA&M``, which :func:`_canon_ticker` reduces to ``TAM``. Same school, same id,
# two spellings — so without a declared equality the anchor sees zero hits and
# falls back to the length answer, which is *Texas A&M-CC*, and the Aggies' five
# bracket cells land on an unserved row.
#
# This is a DECLARED equality, never a loosened comparison. A substring or fuzzy
# test between suffix and abbreviation would reintroduce exactly the guessing
# #7821 removed, and it is especially unsafe here because the abbreviation column
# is measurably dirty — *California Golden Bears* carries ``MIA`` and *Florida
# A&M Rattlers* carries ``MSU``. An alias can only add one named, auditable
# equivalent that a reader can check against the venue; it cannot widen what any
# other key matches. The exactly-one-hit rule below still arbitrates, so a second
# hit still fails closed.
#
# Keys and values are both already canonical (see the guard in
# ``tests/test_grid_ticker_suffix_alias_7829.py``): a non-canonical entry such as
# ``"TA&M"`` would silently never match, which is the likeliest way to get this
# map wrong.
_TICKER_SUFFIX_ALIASES: dict[str, str] = {
    "TXAM": "TAM",  # Texas A&M Aggies — Kalshi `TXAM`, our `TA&M`
}


def _resolve_ambiguous_merge(
    short_name: str,
    candidates: list[str],
    ticker_suffixes: dict[str, set[str]],
    abbreviations: dict[str, str],
) -> str:
    """Pick the merge target for a short name that matches several teams (#7821).

    ``candidates`` arrives longest-first, so ``candidates[0]`` is what the grid
    has always chosen. **Length is not evidence of correctness**: it
    systematically prefers the more-qualified sibling, which is always a
    different institution. Kalshi's ``Florida`` went to *Florida Atlantic* and
    its ``Miami (FL)`` prices published on *Miami (OH)*, while Florida — the #1
    overall seed — was served blank.

    So an ambiguous key is settled by the venue's own ticker suffix
    (``KXMARMADROUND-27R32-FLA`` → ``FLA``) matched against the candidates'
    ``Team.abbreviation``. That is an id, not a name.

    Two deliberate refusals, both because the inputs are known-dirty:

    * The suffix must match EXACTLY ONE candidate. ``Team.abbreviation`` is not
      unique (171 NCAAB rows, 142 distinct) and is wrong in places — *California
      Golden Bears* carries ``MIA`` — so it is only ever used to choose among
      candidates a name rule already produced, never as a lookup on its own. A
      corrupt abbreviation can only do harm if it lands on a sibling of the same
      prefix family, and a second hit means we do not know.
    * No suffix, or no unique hit, falls back to ``candidates[0]``. Today's
      answer may be wrong, but it is wrong in a way that is already measured;
      replacing it with a second guess is how the "fewest remaining words" rule
      traded Florida for California.

    #7829 adds :data:`_TICKER_SUFFIX_ALIASES` — a declared equality for the
    handful of ids the venue and we spell differently (Kalshi ``TXAM`` vs our
    ``TA&M``). It widens the suffix SET, never the comparison, so both refusals
    above are untouched: a key with no alias entry behaves exactly as before, and
    an aliased key that still hits two candidates still falls back.
    """
    suffixes = {c for c in (_canon_ticker(s) for s in ticker_suffixes.get(short_name, ())) if c}
    suffixes |= {a for s in suffixes if (a := _TICKER_SUFFIX_ALIASES.get(s))}
    if suffixes:
        hits = [
            c for c in candidates
            if (ab := _canon_ticker(abbreviations.get(c))) and ab in suffixes
        ]
        if len(hits) == 1:
            return hits[0]
    return candidates[0]


async def _team_abbreviations(session: AsyncSession, names: set[str]) -> dict[str, str]:
    """``{normalized Team.name: abbreviation}`` for EXACT normalized names only.

    Deliberately NOT :func:`_get_team_metadata`. That lookup is
    ``Team.name ILIKE '%name%'`` with a last-one-wins write — its own docstring
    says "THE NAME IS NOT A KEY" — so asking it for ``florida`` returns whichever
    of six Florida schools Postgres happened to return last. An anchor that
    inherits that guess is not an anchor.

    Here the ILIKE only narrows the scan. A row is kept ONLY when its normalized
    name equals the requested candidate exactly, and a name whose rows disagree
    about the abbreviation yields nothing at all — fail closed, so the caller
    falls back to the behaviour that is already measured rather than to a
    coin flip. (Cross-sport duplicates agree in practice: Florida Gators is
    ``FLA`` in all four of its sports.)
    """
    if not names:
        return {}

    conditions = []
    for name in names:
        escaped = name.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Team.name.ilike(f"%{escaped}%"))

    stmt = select(Team)
    stmt = stmt.where(or_(*conditions)) if len(conditions) > 1 else stmt.where(conditions[0])
    loaded = list((await session.execute(stmt)).scalars().all())

    seen: dict[str, set[str]] = defaultdict(set)
    for team in loaded:
        if not team.name or not getattr(team, "abbreviation", None):
            continue
        key = _normalize_team_name(team.name)
        if key in names:
            seen[key].add(team.abbreviation)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


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


def _is_champion_ticker(external_id: str | None, config: LeagueConfig) -> bool | None:
    """Is this ticker the league's genuine full-field champion series?

    #1059: the ``KXNBA`` prefix admits *every* KXNBA* market — conference
    (KXNBAEAST/WEST), game (KXNBAGAME), and props (KXNBAPTS/REB/AST/…) — and
    the loose ``\\bchampion\\b`` fallback let their team outcomes leak into the
    Champion column, producing the degenerate ~37.5% weak-team / ~1.6%-favorite
    prices the A4 shadow table flagged.

    A real champion market's ticker is the bare league prefix immediately
    followed by the season (e.g. ``KXNBA2026`` / ``KXNBA-27``), NOT a
    sub-competition (which inserts extra letters: ``KXNBA`` + ``EAST`` / ``GAME``
    / ``PTS``). Corroborated by calibration_sentinel folding "KXNBA2026" and
    "KXNBA2025" as one champion series.

    Returns True (genuine champion series), False (a sub-competition ticker of
    this league — must NOT populate the Champion column), or None (ticker does
    not belong to this league's prefixes → gate not applicable, e.g. odds_api).
    """
    if not external_id:
        return None
    ext = external_id.upper()
    matched_league = False
    for pfx in config.external_id_prefixes:
        P = pfx.upper()
        if ext.startswith(P):
            matched_league = True
            rest = ext[len(P):]
            # Bare prefix + season (hyphen/digit) ⇒ champion series.
            if not rest or not rest[0].isalpha():
                return True
    return False if matched_league else None


# "AFC East Division Winner", "NHL Pacific Division Winner", "Division Champion",
# "Win the AFC West Division", "Division Title". NOT "… Undefeated in their
# Division", NOT "Division with the Most Total Wins" — ``wins`` is not ``winner``,
# and the second alternative is ORDERED (win … division), so a name that counts
# wins inside a division never reaches it.
_DIVISION_TITLE_RE = re.compile(
    r"\bdivision\s+(?:winner|champion|champions|championship|title|crown)\b"
    r"|\b(?:win|winning|wins)\s+(?:\w+\s+){0,3}?division\b",
    re.IGNORECASE,
)

# "Most Wins in the AL West Division" would satisfy the ordered alternative
# above; a quantity in front of the win word means the market counts wins
# rather than awarding the title.
_COUNTS_WINS_RE = re.compile(
    r"\b(?:most|least|fewest|total|number\s+of|over|under|exact)\b"
    r"[^.?!]{0,20}?\b(?:win|wins|winning)\b",
    re.IGNORECASE,
)


def _asks_who_wins_the_division(market_name: str) -> bool:
    """Does a market that SAYS "division" ask who WINS one? (#6245)

    The NFL, NHL and MLB configs all match the Division column on a bare
    ``\\bDivision\\b``, and ``classify_market_stage``'s football/hockey/baseball
    sub-stages carry the same bare word (``tournament_stages.py:484``), so the
    word alone is the whole test on both paths. Kalshi lists three NFL series
    that contain it and answer a different question:

      * ``KXNFLDIVUNDEFEATED-27`` "Pro Football Teams to go Undefeated in their
        Division" — a strictly rarer event, priced ~0.06 where the division
        title is ~0.55
      * ``KXNFLDIVMOSTWINS-27``  "Division with the Most Total Wins"
      * ``KXNFLDIVLEASTWINS-27`` "Division with the Least Total Wins"

    Measured on production 2026-09-15: all three were in the column, every one
    of the 8 divisions summed to 0.63-0.68, and the undefeated market did not
    merely drag the number down — the per-source dedup at :3793 keeps the
    LOWEST probability, so 0.06 *displaced* Kansas City's genuine 0.555 from
    ``KXNFLAFCWEST-27`` and the reader was told a 33.5% favourite was a 20% one.

    Deliberately narrow: this refuses only names that say "division" without
    asking who wins it. A market that reached the column some other way —
    Polymarket's "Pro Football: AFC West Champion", which matches the config's
    ``(?:AFC|NFC)\\s+(?:East|West|North|South)`` pattern and never says the word
    — is untouched, so the gate cannot drop a title market it has not enumerated.
    All 24 live division-column markets carrying the word (NFL 8, NHL 4, MLB 6,
    NBA 6) are "… Division Winner" and pass. Counts re-read from
    ``/api/playoffs/{nfl,nhl,mlb,nba}?debug=true`` on 2026-09-15; every one of
    the 24 is asserted by name in ``TestDivisionColumnAsksWhoWins``.
    """
    low = market_name.lower()
    if not re.search(r"\bdivisions?\b", low):
        return True  # entered the column without the word — not this gate's business
    if _COUNTS_WINS_RE.search(low):
        return False
    return bool(_DIVISION_TITLE_RE.search(low))


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

    def _gate(col: str | None) -> str | None:
        # #1059 champion-ticker gate: a sub-competition ticker of this league
        # (conference/game/prop) must never land in the Champion column.
        if col == "championship" and _is_champion_ticker(market.external_id, config) is False:
            return None
        # #6245 division gate: a market that says "division" but does not ask
        # who WINS one must never populate the Division column. Both the config
        # rules and the classify_market_stage fallback funnel through here, so
        # this is the one place that closes both doors.
        if col == "division" and not _asks_who_wins_the_division(name):
            return None
        return col

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
                            return _gate(rule.column)
                else:
                    return _gate(rule.column)

        # Name pattern match
        for pat in rule.name_patterns:
            if re.search(pat, name, re.IGNORECASE):
                return _gate(rule.column)

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
            return _gate(stage_key)

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


# Batch size for the deferred outcome fetch. Bounds the IN-list handed to the
# planner; the surviving (column-matched) market set is small in practice, so
# this is a safety rail rather than a hot path.
_OUTCOME_FETCH_BATCH = 200


async def _load_outcomes_for_markets(
    session: AsyncSession,
    market_ids: list[int],
) -> dict[int, list[FuturesOutcome]]:
    """Load outcomes for exactly ``market_ids`` — the #1484 bounded-compute half.

    The grid used to eager-load (``selectinload``) the outcomes of every market
    that matched the league's ticker/category filters, then throw most of them
    away: only markets that resolve to a grid column are ever read. In-season
    MLB matches thousands of per-game markets, so that eager load was the
    league-specific cost behind the grid timing out and serving an empty grid.

    Returns ``{market_id: [outcome, ...]}``. Markets with no outcomes are simply
    absent, so callers should use ``.get(mid, ())``.
    """
    grouped: dict[int, list[FuturesOutcome]] = defaultdict(list)
    if not market_ids:
        return grouped
    unique_ids = list(dict.fromkeys(market_ids))
    for i in range(0, len(unique_ids), _OUTCOME_FETCH_BATCH):
        batch = unique_ids[i : i + _OUTCOME_FETCH_BATCH]
        result = await session.execute(
            select(FuturesOutcome).where(FuturesOutcome.market_id.in_(batch))
        )
        for outcome in result.scalars().all():
            grouped[outcome.market_id].append(outcome)
    return grouped


async def _build_register_column_data(
    session: AsyncSession,
    register: GridRegister,
) -> tuple[dict[str, list[tuple]], dict[int, tuple[str, str]], dict[str, int]]:
    """Resolve grid cells from an explicit register instead of fuzzy matching.

    This is the whole point of Queue 295. The fuzzy path asks "which markets
    *look like* they belong to this league?" and then "which team does this
    outcome name *look like*?" — two guesses per cell, both silent when wrong.
    Here we instead load exactly the ``market_id``/``outcome_id`` pairs the
    register pins, and key each cell by the register's canonical ``entity_key``.

    Returns ``(column_data, outcome_entity, stats)`` where ``column_data``
    matches the shape the existing aggregation step already consumes, so every
    probability, blend, and normalization semantic downstream is untouched.

    Note what is deliberately *absent*: no ILIKE candidate scan, no league or
    season name regex, no stage classifier, no team-name prefix/abbreviation/
    alias merging. A registered identity that the DB no longer carries becomes
    an honest ``missing`` cell and is counted — never a silent 50% or a
    neighbouring team's number.
    """
    column_data: dict[str, list[tuple]] = defaultdict(list)
    outcome_entity: dict[int, tuple[str, str]] = {}
    stats: dict[str, int] = {
        "registered": len(register.entries),
        "live": 0,
        "settled": 0,
        "missing": 0,
        "unresolved": 0,
    }

    outcomes_by_market = await _load_outcomes_for_markets(session, register.market_ids)
    markets_by_id: dict[int, FuturesMarket] = {}
    if register.market_ids:
        result = await session.execute(
            select(FuturesMarket).where(FuturesMarket.id.in_(register.market_ids))
        )
        markets_by_id = {m.id: m for m in result.scalars().unique().all()}

    outcome_index: dict[tuple, FuturesOutcome] = {
        (mid, outcome.id): outcome
        for mid, outcomes in outcomes_by_market.items()
        for outcome in outcomes
    }

    for entry in register.entries:
        status = entry.get("status")
        if status == "missing":
            stats["missing"] += 1
            continue
        if status == "settled":
            stats["settled"] += 1
            continue

        market = markets_by_id.get(entry.get("market_id"))
        outcome = outcome_index.get((entry.get("market_id"), entry.get("outcome_id")))
        if market is None or outcome is None:
            # Registered but not present in the DB right now. This is the case
            # the fuzzy matcher used to paper over by finding *some* other
            # market; the register makes it visible instead.
            stats["unresolved"] += 1
            logger.warning(
                "Grid register %s v%s: %s/%s/%s pins market=%s outcome=%s which is not loadable",
                register.league, register.version, entry.get("stage"),
                entry.get("entity_key"), entry.get("source"),
                entry.get("market_id"), entry.get("outcome_id"),
            )
            continue

        prob = outcome.current_probability
        if prob is None:
            stats["unresolved"] += 1
            continue
        prob = float(prob)
        if prob <= 0 or prob >= 1.0:
            stats["unresolved"] += 1
            continue

        stats["live"] += 1
        column_data[entry["stage"]].append((market, outcome))
        outcome_entity[outcome.id] = (
            entry["entity_key"],
            entry.get("entity_name") or entry["entity_key"],
        )

    return column_data, outcome_entity, stats


#: ``futures_odds_snapshots.bookmaker`` values whose ``probability`` is ALREADY a
#: probability when it is written, not a vig-inclusive price.
#:
#: The three of them write the SAME number into ``FuturesOutcome
#: .current_probability`` and into the snapshot row on the same pass
#: (``tasks/kalshi.py``, ``tasks/polymarket.py``, ``tasks/datagolf.py``), so the
#: snapshot is already on the live side's scale. The seven Odds API sportsbooks
#: are the opposite: their snapshot is raw American-odds-implied and the live
#: value is de-vigged at ingest by ``_aggregate_futures_outcomes``. Measured on
#: production 2026-09-17, NBA markets: every kalshi/polymarket column has
#: ``max|raw - live| <= 0.06`` and the same sum, while every sportsbook column on
#: ``NBA Championship Winner`` sums 1.107-1.241 raw against a live sum of exactly
#: 1.000.
#:
#: Adding a source to ``futures_odds_snapshots`` means classifying it here.
#: ``test_playoff_movers_basis.py`` scans the writers for ``bookmaker=`` literals
#: and fails on any value this module has never heard of, so a new source cannot
#: land unclassified (#6675).
_ALREADY_PROBABILITY_SOURCES = frozenset({"kalshi", "polymarket", "datagolf_model"})

#: The Odds API sportsbooks, whose raw column IS a vig-inclusive price set over a
#: mutually exclusive outcome set — the only shape ``remove_vig_nway`` is valid on.
_DEVIGGED_AT_INGEST_SOURCES = frozenset({
    "betmgm", "betrivers", "betonlineag", "bovada", "draftkings", "fanduel", "lowvig",
})


class MoversResult(dict):
    """``{outcome_id: de-vigged consensus probability at t-N hours}``.

    A ``dict`` subclass so every existing ``old_probs.get(outcome_id)`` call site
    keeps working unchanged, while carrying the metadata a caller needs to say
    "this read was partial" out loud.

    #1844 acceptance 2: a degraded read must DECLARE itself. The old code
    swallowed a statement timeout and returned partial results, so the set of
    teams that got a delta depended on the query plan and a truncated read was
    indistinguishable from "nothing moved" — gotcha #53 in the grid.
    """

    __slots__ = ("degraded", "requested", "covered", "markets_normalized")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.degraded: bool = False
        self.requested: int = 0
        self.covered: int = 0
        self.markets_normalized: int = 0


async def _compute_movers(
    session: AsyncSession,
    outcome_ids: list[int],
    hours: int = 24,
) -> MoversResult:
    """Reconstruct the de-vigged consensus as of N hours ago, per outcome.

    Returns a :class:`MoversResult` mapping ``{outcome_id: consensus_then}``.
    Callers subtract it from today's merged probability to get ``trend_24h``.

    **Both sides of that subtraction must be the same quantity.** They were not
    (#1844). This function used to return ``fos.probability`` from ONE row per
    outcome — and ``futures_odds_snapshots`` is per-BOOKMAKER, so that was a
    single arbitrary book's RAW, vig-inclusive price. Subtracting it from a
    de-vigged consensus is negative by construction and proportional to each
    outcome's probability: the MLB grid rendered 29 of 30 teams falling, every
    day, deterministically. LAD's headline "-7.6 in 24h" was
    ``0.3153 x 0.245`` — the betrivers overround — not a market move.

    Four defects, all closed here:

    1. **Vig basis mismatch.** We now de-vig the historical column per book and
       average across books, through the SAME ``odds_math.devig_consensus`` the
       live path uses. The reconstructed column sums to ~1.0, like the now side.
    2. **Single book vs consensus.** Every book present at the reference capture
       contributes, so a mover can no longer be one book's disagreement.
    3. **Non-deterministic tie-break.** All books share an identical
       ``captured_at``, and the old ``ORDER BY captured_at ASC LIMIT 1`` had no
       tie-break — a plan change silently swapped a 32.5%-vig book for a
       16.6%-vig one and halved every published mover with zero market movement.
       ``DISTINCT ON`` here carries an explicit ``fos.id`` tie-break.

    4. **Cardinality basis mismatch** (#6675). #1844 made both sides the same
       quantity with respect to VIG; they were still different quantities with
       respect to WHAT THE COLUMN SUMS TO. De-vigging was applied to every
       source, including kalshi/polymarket/datagolf — which store a probability,
       not a price — so each such column was silently re-scaled by its own sum.
       Harmless-looking on a winner market (sum ~1.0); catastrophic on a
       multi-qualifier one: "Pro Basketball Playoff Qualifiers" is 30 INDEPENDENT
       binaries summing to 16.54, so every reconstructed price was divided by
       ~16.5 and ``merged - old_p`` collapsed to ``merged x (1 - 1/16.5)``. The
       NBA grid told a reader all 30 teams' playoff odds rose by ~94% of their
       own value in 24 hours (OKC: 98.5%, "▲93"). The same re-scaling was live
       and wrong, just less visible, on every kalshi award market — "Pro
       Basketball MVP Winner" sums to 1.46, a 31% inflation of every mover.

       The fix is not a threshold on the column sum: production sums run
       CONTINUOUSLY from 1.0 to 20+ (measured over 24h of snapshots — 729 book
       columns land in 2.0-3.0 alone), so no cut separates "winner market with
       heavy vig" from "small qualifier market". It is the SOURCE that decides,
       because the source decides whether ingest already normalized.

    The naming trap that hid all of this: ``FuturesOddsSnapshot.probability`` is
    commented "Normalized probability (always calculated)". It is normalized
    from American odds and is PER BOOKMAKER — never de-vigged, never a consensus.
    For kalshi/polymarket/datagolf it is not even that: it is the venue's own
    published probability, copied verbatim.
    """
    empty = MoversResult()
    if not outcome_ids:
        return empty

    # Deduplicate outcome IDs to reduce query load
    unique_ids = list(set(outcome_ids))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    empty.requested = len(unique_ids)

    # One row per (outcome, bookmaker): that bookmaker's EARLIEST snapshot since
    # the cutoff. DISTINCT ON rides idx_fos_outcome_captured(outcome_id,
    # captured_at) the same way the old LATERAL did, but keeps the whole book
    # column instead of collapsing to one arbitrary row.
    #
    # `fos.id ASC` is the deterministic tie-break (#1844 acceptance 3): books
    # written in the same poll share a captured_at to the microsecond.
    #
    # Batch by outcome id to keep each query fast and bound the planner's work.
    _BATCH_SIZE = 40
    # market_id -> bookmaker -> outcome_id -> raw vig-inclusive probability
    columns: dict[int, dict[str, dict[int, float]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    degraded = False

    from sqlalchemy import text

    for i in range(0, len(unique_ids), _BATCH_SIZE):
        batch = unique_ids[i : i + _BATCH_SIZE]
        try:
            result = await session.execute(
                text("""
                    SELECT DISTINCT ON (fo.id, fos.bookmaker)
                           fo.id AS outcome_id,
                           fo.market_id AS market_id,
                           fos.bookmaker AS bookmaker,
                           fos.probability AS raw_prob
                    FROM futures_outcomes fo
                    JOIN futures_odds_snapshots fos
                      ON fos.outcome_id = fo.id
                     AND fos.captured_at >= :cutoff
                    WHERE fo.id = ANY(:ids)
                    ORDER BY fo.id, fos.bookmaker, fos.captured_at ASC, fos.id ASC
                """),
                {"ids": batch, "cutoff": cutoff},
            )
            for row in result:
                columns[row.market_id][row.bookmaker][row.outcome_id] = float(
                    row.raw_prob
                )
        except Exception as exc:
            # Statement timeout or other DB error. We keep the batches that DID
            # land, but the result is flagged degraded so the response can say
            # so — a partial read must never render as "no movement".
            degraded = True
            logger.warning(
                "_compute_movers: batch %d failed after gathering %d/%d "
                "outcome ids: %s",
                i // _BATCH_SIZE, len(unique_ids) - len(batch), len(unique_ids),
                exc,
            )
            # After a cancelled statement the connection is in an error state;
            # rollback so subsequent queries on this session still work.
            try:
                await session.rollback()
            except Exception:
                pass

    # De-vig each book's column on its own market, then average across books —
    # the SAME helper the live path uses (app/tasks/futures.py) — but only for
    # the sources whose stored snapshot is a PRICE. See #6675 and defect 4 above.
    old_probs = MoversResult()
    old_probs.requested = len(unique_ids)
    # A source in neither bucket is being de-vigged by the default arm. That is
    # right for a new Odds API sportsbook and WRONG for a new prediction market,
    # and the two are indistinguishable from here — so say so once per read
    # rather than let it ride silently. CI's source-scan is the real guard; this
    # is the backstop for a source that arrives without a string literal.
    unknown_sources = {
        bookmaker
        for book_columns in columns.values()
        for bookmaker in book_columns
        if bookmaker not in _ALREADY_PROBABILITY_SOURCES
        and bookmaker not in _DEVIGGED_AT_INGEST_SOURCES
    }
    if unknown_sources:
        logger.warning(
            "_compute_movers: unclassified snapshot source(s) %s de-vigged by "
            "default — if any of them stores a probability rather than a price, "
            "its 24h deltas are re-scaled by the column sum (#6675)",
            sorted(unknown_sources),
        )

    for _market_id, book_columns in columns.items():
        # Keys are outcome ids; devig_consensus is key-agnostic.
        consensus = devig_consensus(
            book_columns,
            method="mean",
            already_normalized=_ALREADY_PROBABILITY_SOURCES,
        )
        if consensus:
            old_probs.markets_normalized += 1
        old_probs.update(consensus)

    old_probs.covered = len(old_probs)
    # A partial read is degraded whether the cause was a timeout or a market
    # whose column could not be normalized at all.
    old_probs.degraded = degraded
    return old_probs


def _collect_trend_outcomes(
    teams: list[dict],
    grid_raw: dict,
    championship_col: str,
    top: int,
) -> tuple[list[int], dict[int, str]]:
    """Pick the outcomes the register-backed grid's trend chart draws.

    #7458, and extracted so it can be tested: this loop lived inline, and both
    mutants of it — restoring the ``break`` and labelling per outcome — survived
    the whole playoff test band, because the integration tests that reach this
    path patch ``_build_trend_chart`` out.

    Two rules, and the second is load-bearing only because of the first:

    * **Every source that prices a team is carried**, not the one that happens
      to sort first. The chart used to keep one outcome per team while the table
      beside it blended all of them — half of the 6.67pt the NBA legend
      disagreed with its own table by. This is safe only because
      :func:`_build_trend_chart` de-vigs each venue's column and holds it across
      the buckets that venue did not write in; pooling venues raw would draw a
      sawtooth between two honest opinions.

    * **A team's outcomes all carry the TEAM's display name**, never the
      outcome's own. Venues spell a club differently and the old fallback was
      the lowercase normalized form, so naming per outcome would split one club
      into two differently-named series the moment the ``break`` came out.
    """
    trend_outcome_ids: list[int] = []
    trend_outcome_names: dict[int, str] = {}

    for team in teams[:top]:
        norm_name = _normalize_team_name(team["name"])
        for entry in grid_raw.get(norm_name, {}).get(championship_col, []):
            outcome_id = entry.get("outcome_id")
            if not outcome_id or outcome_id in trend_outcome_names:
                continue
            trend_outcome_ids.append(outcome_id)
            trend_outcome_names[outcome_id] = team["name"]

    return trend_outcome_ids, trend_outcome_names


#: Upper bound on the historical rows one trend chart may read. The chart reads
#: each market's WHOLE outcome column, because the de-vig denominator is the
#: column and not the ten names we happen to draw, so this is ~3x the old
#: top-N-only read: measured 6,090 rows for the NBA championship column and
#: 7,019 for MLB's over 168h (2026-09-20). It is a rail, not a budget — and the
#: read is ordered NEWEST FIRST so that hitting it drops the oldest tail rather
#: than the current price the legend publishes.
_TREND_ROW_CAP = 20000


async def _build_trend_chart(
    session: AsyncSession,
    outcome_ids: list[int],
    outcome_names: dict[int, str],
    hours: int = 168,
    top_n: int = 10,
    bucket_seconds: int = 3600,
    column_scale: float = 1.0,
) -> dict:
    """Build the grid's trend chart on the SAME basis as the grid's table.

    #7458. This function used to pool ``FuturesOddsSnapshot.probability`` across
    every row that landed in an hour and take the median. That column is the
    raw, vig-inclusive, per-BOOKMAKER price — see ``_compute_movers``' docstring
    for why its name lies — so the chart published a different quantity from the
    table beside it and the movers rail below it. On 2026-09-20 the NBA grid's
    legend said OKC 28.17% while its own table said 21.50%, and all five leagues
    disagreed with themselves; EPL's top NINE clubs summed to 102%, which is not
    a probability distribution but a 21% overround.

    Three defects, and the first two only look like one:

    1. **Vig basis.** Each book's column is now de-vigged on its own outcome set
       through ``odds_math.devig_consensus`` — the same helper the live path, the
       table and ``_compute_movers`` use — carrying the same
       ``already_normalized`` classification, so a venue that publishes a
       probability is never re-scaled by its own column sum (#6675).

    2. **Whose column.** De-vigging needs the WHOLE market column as its
       denominator, so the read widens from the ten drawn outcomes to every
       sibling outcome of their markets. Reading a tenth of a column and
       dividing by its sum is #6675 with a different numerator.

    3. **Which source happened to write this hour.** Venues write on their own
       cadences: the NBA championship column takes four Odds API books together
       at one minute and polymarket alone at another. Pooling by row let whoever
       wrote in a bucket decide its value, and de-vigging alone would only trade
       the resulting flat line for a sawtooth (measured: 23.3% on odds_api
       hours, 21.5% on polymarket hours — ±1.8pt on a market that did not move).
       Each book column is therefore carried forward into the buckets where it
       did not write, so every point is a consensus over the same source set and
       a change in the line is a change in the market.

    4. **The table's last stage.** De-vigging and blending still left the chart
       one step short of the table, and the gap was a CONSTANT per league:
       EPL's legend read x1.140 of every one of its own table cells, MLB's
       x1.052. A constant ratio is a column rescale, not a per-venue vig
       decision — ``normalize_column_sums`` scales a championship column that
       sums outside ``[0.85, 1.05]`` back onto 1.0, and the chart never ran it.
       ``column_scale`` is the factor that call ACTUALLY applied, handed in by
       the caller rather than recomputed here, so the two surfaces cannot drift.

    On ``column_scale`` being one scalar for the whole window rather than a
    per-bucket sum: a per-bucket factor is the tempting version and it is wrong
    here. The policy has a hard threshold at 1.05 and MLB's column sits at
    1.0524 — a hair over — so a per-bucket factor would snap on and off as the
    sum drifted across it and draw ~5pt STEPS into every series that no market
    ever moved. That is a worse defect than the one being fixed, and it is the
    same class as the flat line in (3): a line that moves for a reason outside
    the market. A single scalar cannot do it: it rescales the level and leaves
    the SHAPE — which is what a trend chart is for — exactly as measured.

    Only ``outcome_names``' names are drawn; the siblings exist to make the
    denominator honest and are dropped before the payload is built.
    """
    if not outcome_ids:
        return {"timeline": [], "outcomes": []}

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    drawn_ids = set(outcome_ids)

    # The callers hand us outcome ids, not markets; the de-vig needs markets.
    market_result = await session.execute(
        select(FuturesOutcome.market_id)
        .where(FuturesOutcome.id.in_(list(drawn_ids)))
        .distinct()
    )
    market_ids = [m for (m,) in market_result.all() if m is not None]
    if not market_ids:
        return {"timeline": [], "outcomes": []}

    stmt = (
        select(
            FuturesOutcome.id.label("outcome_id"),
            FuturesOutcome.market_id.label("market_id"),
            FuturesOddsSnapshot.bookmaker.label("bookmaker"),
            FuturesOddsSnapshot.captured_at.label("captured_at"),
            FuturesOddsSnapshot.probability.label("probability"),
        )
        .join(
            FuturesOddsSnapshot,
            FuturesOddsSnapshot.outcome_id == FuturesOutcome.id,
        )
        .where(
            FuturesOutcome.market_id.in_(market_ids),
            FuturesOddsSnapshot.captured_at >= cutoff,
            FuturesOddsSnapshot.probability.isnot(None),
        )
        .order_by(
            FuturesOddsSnapshot.captured_at.desc(),
            FuturesOddsSnapshot.id.desc(),
        )
        .limit(_TREND_ROW_CAP)
    )
    result = await session.execute(stmt)
    rows = result.all()

    if not rows:
        return {"timeline": [], "outcomes": []}

    # bucket -> market -> bookmaker -> {outcome_id: raw vig-inclusive price}.
    # Rows arrive newest-first, so the FIRST row seen for a key is that bucket's
    # latest write and an older row may never overwrite it.
    observed: dict[int, dict[int, dict[str, dict[int, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(dict))
    )
    for row in rows:
        bucket_ts = (
            int(row.captured_at.timestamp()) // bucket_seconds
        ) * bucket_seconds
        column = observed[bucket_ts][row.market_id][row.bookmaker or "unknown"]
        if row.outcome_id not in column:
            column[row.outcome_id] = float(row.probability)

    # A source in neither bucket is de-vigged by the default arm. That is right
    # for a new Odds API sportsbook and WRONG for a new prediction market, and
    # the two are indistinguishable from here — so say so once per read rather
    # than let a whole trend line ride on it silently (#6675).
    unknown_sources = {
        book
        for markets in observed.values()
        for books in markets.values()
        for book in books
        if book not in _ALREADY_PROBABILITY_SOURCES
        and book not in _DEVIGGED_AT_INGEST_SOURCES
    }
    if unknown_sources:
        logger.warning(
            "_build_trend_chart: unclassified snapshot source(s) %s de-vigged "
            "by default — if any of them stores a probability rather than a "
            "price, its entire trend line is re-scaled by its column sum (#6675)",
            sorted(unknown_sources),
        )

    timeline = []
    # Last column seen for each (market, bookmaker), carried into later buckets.
    carried: dict[tuple[int, str], dict[int, float]] = {}
    for bucket_ts in sorted(observed.keys()):
        for market_id, books in observed[bucket_ts].items():
            for book, column in books.items():
                carried[(market_id, book)] = column

        per_market: dict[int, dict[str, dict[int, float]]] = defaultdict(dict)
        for (market_id, book), column in carried.items():
            per_market[market_id][book] = column

        by_name: dict[str, list[float]] = defaultdict(list)
        for market_id, book_columns in per_market.items():
            # Keys are outcome ids; devig_consensus is key-agnostic.
            consensus = devig_consensus(
                book_columns,
                method="mean",
                already_normalized=_ALREADY_PROBABILITY_SOURCES,
            )
            for outcome_id, probability in consensus.items():
                if outcome_id in drawn_ids:
                    by_name[outcome_names.get(outcome_id, str(outcome_id))].append(
                        probability
                    )

        if not by_name:
            continue
        timeline.append({
            "timestamp": datetime.fromtimestamp(bucket_ts, tz=timezone.utc).isoformat(),
            "outcomes": {
                # Rounded to 4dp and capped at 1.0 exactly as the table's cells
                # are, so the legend and the cell are the same number rather
                # than two numbers that agree to within a rounding step.
                name: min(round(_merge_probabilities(probs) * column_scale, 4), 1.0)
                for name, probs in by_name.items()
            },
        })

    if not timeline:
        return {"timeline": [], "outcomes": []}

    # Outcomes metadata — current probability is the latest timeline entry, so
    # the legend can never publish a number the line it labels does not reach.
    latest = timeline[-1]["outcomes"]
    outcomes_meta = [
        {"name": name, "current_probability": prob}
        for name, prob in sorted(latest.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "timeline": timeline,
        "outcomes": outcomes_meta,
    }


def _in_scope(team, scope_keys: set[str]) -> int:
    """1 when this row's sport is one the league config asked for, else 0.

    `getattr` rather than `team.sport.key` because a row whose sport did not
    load must rank as out-of-scope, not raise.
    """
    sport_key = getattr(getattr(team, "sport", None), "key", None)
    return 1 if (scope_keys and sport_key in scope_keys) else 0


def _secondary_claims(team) -> list[str]:
    """The keys a row claims that are not its own `name`: abbreviation + aliases.

    One list, built once, so the contest below and the write loop can never
    disagree about which keys were even claimed.
    """
    claims = []
    if getattr(team, "abbreviation", None):
        claims.append(team.abbreviation)
    claims.extend(getattr(team, "alternate_names", None) or [])
    return [c for c in claims if c]


def _alias_prefix_remainder(alias_norm: str, name: str | None) -> int | None:
    """How many tokens of `name` the alias does NOT cover, or None if it is no prefix.

    Token-wise, not substring: `oklahoma` leads `oklahoma st cowgirls`, but
    `land` does not lead `cleveland cavaliers`.
    """
    if not name:
        return None
    alias_tokens = alias_norm.split()
    name_tokens = _normalize_team_name(name).split()
    if not alias_tokens or len(alias_tokens) > len(name_tokens):
        return None
    if name_tokens[: len(alias_tokens)] != alias_tokens:
        return None
    return len(name_tokens) - len(alias_tokens)


def _alias_contest_winner(alias_norm: str, claimants: list, scope_keys: set[str]):
    """Which of several ELIGIBLE claimants takes a contested alias key (#7761).

    #7727 decides who is eligible. This decides who wins, and the caller
    composes the two — see `eligible_claims` in `_get_team_metadata`. Wherever
    #7727 admits more than one row for a key, the key used to fall through to
    last-one-wins by `id`, and that happens in two ways:

    * the key is NOBODY's canonical name, which is how college feeds publish —
      `oklahoma` is nobody's name, `Oklahoma Sooners` is;
    * the key IS a row's canonical name but in ANOTHER SCOPE TIER, where
      #7727's cross-tier branch admits every in-scope claimant. `West Virginia`
      is the entire name of a `baseball_ncaa` row, which is why the women's
      basketball grid never consulted a rule at all for that key.

    Measured on production 2026-09-21, the two together put **Oklahoma State's
    crest and 24-10 record on the row labelled "Oklahoma"** (2400 > 235, and
    that is the whole reason) and **Utah's row under "West Virginia"** —
    thirteen unrelated schools claim to be West Virginia. Which impostor won
    depended on which rows the `ILIKE` happened to load: across four loaded
    sets the old rule answered 149, 2407, 2705, 2705, while this rule answers
    149 every time. That is the point — the answer stops being a function of
    the query and becomes a function of the row.

    An arbitrary order is wrong about as often as it is right, so the rule is to
    prefer what is TRUE about the claim and to refuse when nothing is:

    1. Scope first, exactly as the write order always has it — an in-scope row
       beats an out-of-scope one and the tiers never mix (#6230).
    2. A row whose OWN NAME THE ALIAS LEADS beats one where it does not.
       `west virginia` leads `West Virginia Mountaineers` and leads none of the
       other twelve, which settles a 13-way contest on a fact.
    3. Among those, the alias that accounts for MORE of the name wins:
       `oklahoma` leaves one token of `Oklahoma Sooners` and two of
       `Oklahoma St Cowgirls`, and `Oklahoma State` is a different school.
    4. Still tied and the rows are DIFFERENT anchored clubs ⇒ refuse the key
       outright. `new york` is genuinely not the Yankees rather than the Mets;
       serving either crest is a guess, and a guess is what this repair is
       against. Tied rows sharing one anchor are one club with two rows, where
       highest-`id` is the behaviour #6230/#7675 are built on — kept.

    Measured over all 9,958 `teams` rows, every sport: 659 ownerless contested
    keys, of which 599 keep today's winner byte-for-byte, 56 rebind (every one
    to the correct club — `michigan` off `Akron Zips`, `texas tech` off
    `Auburn Tigers`, `atlanta` off `Inter Miami CF`) and 4 refuse.

    THAT CENSUS GROUPED BY SPORT AND IS BLIND TO THE SECOND ARM ABOVE, which is
    how the West Virginia specimen shipped unfixed the first time: the real
    lookup has no sport filter — deliberately, #6230 — so a canonical owner can
    sit in another sport and the key never looked ownerless at all. The honest
    measurement replays both versions over the SERVED grid rows: across the 14
    warm leagues, 530 rows, exactly ONE row changes hand outside the specimens
    (bundesliga `Hamburg`, 19304 → 14983 — the same club, both `espn_id` 127,
    both `1-0-3`, picking the row whose name the label actually is) and NO row
    loses its metadata. Measure a change to this function over the cross-sport
    loaded set; a per-sport census will agree with you and be wrong.

    RESIDUAL, stated because it is a guess this rule does not remove: where two
    differently-anchored rows both lead with the alias and differ only in
    mascot length, step 3 picks the shorter — `chicago` takes the Cubs over the
    White Sox. That key is arbitrary TODAY too (it takes the White Sox, by
    `id`), no grid consults it (MLB rows carry full club names), and the honest
    fix is the anchor channel (#7676), not a longer name rule. Four keys reach
    step 3 at all; two are `chicago`, two are `oklahoma`/`colorado`, where the
    loser's extra token is `St` and the answer is right.
    """
    top_tier = max(_in_scope(t, scope_keys) for t in claimants)
    pool = [t for t in claimants if _in_scope(t, scope_keys) == top_tier]
    if len(pool) == 1:
        return pool[0].id

    ranked = [(_alias_prefix_remainder(alias_norm, t.name), t) for t in pool]
    leading = [(rem, t) for rem, t in ranked if rem is not None]
    if not leading:
        # Nothing to prefer — the alias leads nobody's name. Today's order
        # stands rather than inventing a different arbitrary answer.
        return pool[-1].id

    best = min(rem for rem, _ in leading)
    finalists = [t for rem, t in leading if rem == best]
    if len(finalists) == 1:
        return finalists[0].id

    anchors = {
        str(getattr(t, "espn_id", None))
        for t in finalists
        if getattr(t, "espn_id", None)
    }
    if len(anchors) > 1:
        return None  # different clubs, nothing true separates them
    return finalists[-1].id


def _alias_may_claim(
    alias_norm: str,
    team,
    canonical_owners: dict[str, tuple[int, object, int]],
    scope_keys: set[str],
    alias_winners: dict[str, object] | None = None,
) -> bool:
    """May `team` index itself under `alias_norm`, an abbreviation or alias?

    AN ALIAS IS A CLAIM; A ROW'S OWN `name` IS THE ROW (#7727). The lookup this
    guards is last-one-wins by `id`, so before this an alias belonging to a
    higher-id row silently deleted a lower-id row's own name — and the deleted
    row then vanished from the grid, its markets merging into the claimant on
    the shared `team_id`. Measured on production 2026-09-21: `Auburn Tigers`
    (id 271) carries the alias `Texas Tech Red Raiders`, so the men's NCAA grid
    printed "Texas Tech Red Raiders" over Auburn's crest, `AUB` and Auburn's
    22-16 record, and Auburn had no row at all. `Akron Zips` claimed
    `Michigan Wolverines`; `Oklahoma St Cowgirls` claimed `Oklahoma Sooners`.

    THE DISCRIMINATOR IS THE ANCHOR, NOT THE NAME (ruling 048). Most keys where
    an alias beats a name are ONE club holding two rows — `Bournemouth` and
    `AFC Bournemouth`, `St.Louis Cardinals` and `St. Louis Cardinals` — and
    there the alias winning is the behaviour every other grid rule is built on;
    flipping those regresses far more rows than it fixes (930's measurement on
    this same function). So the claim is refused only when the two rows are
    anchored to DIFFERENT ESPN teams. Absent either anchor the rule fails
    closed and today's order stands — those rows need the anchor channel
    (#7676), not a looser name rule.

    Scope is untouched: the refusal applies only within one scope tier, so an
    in-scope row still beats an out-of-scope one exactly as before.

    THIS FUNCTION DECIDES ELIGIBILITY ONLY. Which of several ELIGIBLE claimants
    actually takes the key is `_alias_contest_winner`'s question (#7761), and
    the two are composed by the caller rather than sequenced — see the comment
    on `alias_winners` in `_get_team_metadata`.
    """
    if alias_winners is not None and alias_norm in alias_winners:
        # Contested by several eligible rows: one wins on the merits, or the
        # key is refused (winner None, which no `id` equals) rather than
        # guessed. Eligibility was already applied when the contest was built.
        return alias_winners[alias_norm] == team.id

    owner = canonical_owners.get(alias_norm)
    if owner is None:
        return True  # nobody's own name
    _owner_id, owner_espn_id, owner_in_scope = owner
    # A row aliasing its OWN name needs no clause of its own: it is its own
    # anchor, so the equal-anchor return below already admits it.
    if owner_in_scope != _in_scope(team, scope_keys):
        return True  # cross-tier: scope decides, as it always has
    my_espn_id = getattr(team, "espn_id", None)
    if not my_espn_id or not owner_espn_id:
        return True  # no anchor channel — fail closed
    if str(my_espn_id) == str(owner_espn_id):
        return True  # one club, two rows
    return False


async def _get_team_metadata(
    session: AsyncSession,
    team_names: set[str],
    league_slug: str = "",
    conference_field: str = "conference",
) -> dict[str, dict]:
    """Look up team metadata (logo, colors, record, conference) by name.

    Returns {normalized_name: metadata_dict}.
    Conference/division labels come from Team.standings_data.

    THE NAME IS NOT A KEY, AND THIS LOOKUP NEVER PRETENDED OTHERWISE (#6230).
    The match is `Team.name ILIKE '%name%'` and the write below is last-one-wins,
    so when a club owns more than one `teams` row the record, logo and colours a
    grid shows are decided by the order Postgres happened to return — nothing
    else. That is not a hypothetical: every MLB club has two rows, one under
    `baseball_mlb` and one under `baseball_mlb_preseason`, and the preseason row
    carries a SPRING TRAINING record. Measured on production 2026-09-14:

        855  Minnesota Twins  10-18-1  baseball_mlb_preseason
        10739 Minnesota Twins 70-79    baseball_mlb

    `10-18-1` cannot be an MLB record — MLB has no ties — and spring training is
    where the W-L-D shape and the ~30-game sum come from. 19 of 24 sampled clubs
    served the preseason row; the five that did not (Yankees among them) differ in
    nothing but row order. The reader saw it as one event page printing two
    different records for one team, hero vs Championship Path, on the same iPad
    screen.

    So the scope key goes in. `LeagueConfig.sport_keys` is exactly it — `mlb` is
    `["baseball_mlb"]`, which does not contain `baseball_mlb_preseason`.

    IT IS A PREFERENCE, NOT A FILTER, AND THAT IS DELIBERATE. A hard
    `sport.key IN (...)` would drop every row whose sport key the config does not
    list, taking the logo, colours, conference and record with it — one wrong
    number traded for many missing ones, on leagues nobody measured here. So an
    in-scope row WINS over an out-of-scope one, and an out-of-scope row is still
    used when it is all there is. Ordering does the choosing: rows are processed
    out-of-scope first, in-scope last, and `id` ascending within each group, so
    the existing last-one-wins write lands on the in-scope row. Within one scope
    the highest `id` wins — the same rule this function always had, now stated and
    reproducible instead of planner-dependent.

    The duplicate rows themselves are not this function's business and are not
    touched: whether `baseball_mlb_preseason` clubs should exist at all is a
    matching question (#2693), and a read path is the wrong place to answer it.
    """
    if not team_names:
        return {}

    # Build ILIKE conditions for each name
    conditions = []
    for name in team_names:
        escaped = name.replace("%", "\\%").replace("_", "\\_")
        conditions.append(Team.name.ilike(f"%{escaped}%"))

    stmt = select(Team).options(selectinload(Team.sport))
    if len(conditions) > 1:
        stmt = stmt.where(or_(*conditions))
    elif conditions:
        stmt = stmt.where(conditions[0])

    result = await session.execute(stmt)
    loaded = list(result.scalars().all())

    config = get_league_config(league_slug) if league_slug else None
    scope_keys = {k for k in (config.sport_keys if config else []) if k}

    def _rank(team) -> tuple[int, int]:
        """Sort key: out-of-scope first, in-scope last, `id` ascending inside.

        The scope half is `_in_scope`, shared with `_alias_may_claim` so the
        ordering and the refusal can never disagree about which tier a row is
        in: the refusal is deliberately confined to one tier.
        """
        team_id = getattr(team, "id", 0)
        return (
            _in_scope(team, scope_keys),
            team_id if isinstance(team_id, int) else 0,
        )

    teams = sorted(loaded, key=_rank)

    # Who owns each key as their OWN name, in the same last-one-wins order the
    # lookup below uses. Computed first because an alias can be written before
    # the row it would overwrite is even reached.
    canonical_owners: dict[str, tuple[int, object, int]] = {}
    for team in teams:
        if not team.name:
            continue
        canonical_owners[_normalize_team_name(team.name)] = (
            team.id,
            getattr(team, "espn_id", None),
            _in_scope(team, scope_keys),
        )

    # THE TWO RULES ARE COMPOSED, NOT SEQUENCED. #7727 says who is ELIGIBLE to
    # claim a key; #7761 says who WINS among the eligible. Sequencing them —
    # "settle the contest only where #7727 found no owner" — leaves the case
    # that produced #7761's second specimen unfixed, because a key can have a
    # canonical owner in a DIFFERENT SCOPE TIER: `West Virginia` is the whole
    # name of row 13387 in `baseball_ncaa`, so on the women's basketball grid
    # #7727's cross-tier branch admitted every in-scope claimant and `max(id)`
    # picked `Utah Utes` out of thirteen. Eligibility first, then the contest
    # among whoever survived it, and the write loop re-asks both.
    #
    # Computed before the first write for the same reason `canonical_owners` is:
    # a contest has to be settled before its first claimant is written, not
    # discovered as rows arrive.
    eligible_claims: dict[str, list] = {}
    for team in teams:
        for alt in _secondary_claims(team):
            alt_norm = _normalize_team_name(alt)
            if _alias_may_claim(alt_norm, team, canonical_owners, scope_keys):
                eligible_claims.setdefault(alt_norm, []).append(team)
    alias_winners: dict[str, object] = {
        alias_norm: _alias_contest_winner(alias_norm, claimants, scope_keys)
        for alias_norm, claimants in eligible_claims.items()
        if len(claimants) > 1
    }

    # Build lookup by normalized name
    team_lookup: dict[str, dict] = {}
    for team in teams:
        meta = {
            "team_id": team.id,
            # The join key for ESPN's standings authority (#7663). Not published
            # in the grid payload — it exists so the clinch overlay can match on
            # an id instead of a name: ours is `St.Louis Cardinals` and ESPN's is
            # `St. Louis Cardinals`, and that club is eliminated, so a name join
            # drops precisely the row the overlay is there to correct.
            "espn_id": getattr(team, "espn_id", None),
            "name": team.name,
            # #7798 — the abbreviation, else the name, else its last word only
            # when that word is distinctive. The line this replaced took the
            # last word unconditionally, so `Coventry City` and `Hull City`
            # both served "City" on one EPL grid and `Manchester United` served
            # "United". It also mis-parsed: `a or b if c else None` binds as
            # `(a or b) if c else None`, so a row with an abbreviation and no
            # name served null. 4 of 379 grid rows move; see the docstring.
            "short_name": compact_team_label(team.name, team.abbreviation),
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

        # Queue #242 Item 1c: MLB/NFL have NULL standings_data (StatPal only
        # populates NBA/NHL divisions), so the division race never rendered for
        # those two leagues (L2-162). Conference/division membership is stable in
        # MLB and NFL — fall back to the static map when the label is missing.
        if team.name and (not meta["division"] or not meta["conference"]):
            static_conf, static_div = _static_lookup_division(league_slug, team.name)
            if not meta["conference"] and static_conf:
                meta["conference"] = static_conf
            if not meta["division"] and static_div:
                meta["division"] = static_div

        # #6246: one vocabulary, applied to BOTH arms above and here rather than
        # at the grouping site alone — the event page's Championship Path reads
        # this metadata without ever building `grouped_teams`, so a rule that
        # lived only in the grid would let the two surfaces disagree about which
        # conference a club is in.
        meta["conference"] = _canonical_conference(league_slug, meta["conference"])
        meta["division"] = _canonical_division(league_slug, meta["division"])

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

        # Secondary identifiers. An abbreviation or an alternate name is a
        # CLAIM about who a row is; the row's own `name` is the row itself. So
        # a claim may not take a key that is another CLUB's own name — see
        # `_alias_may_claim`.
        for alt in _secondary_claims(team):
            alt_norm = _normalize_team_name(alt)
            if _alias_may_claim(
                alt_norm, team, canonical_owners, scope_keys, alias_winners
            ):
                team_lookup[alt_norm] = meta

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
        # One candidate load for the whole build. Every tour and every upcoming
        # major below issued this same query and filtered its result differently
        # in Python; three active tours therefore paid for it three times.
        candidates = GolfCandidateMarkets(db, config)

        # Track which tournament is the current PGA event (to avoid duplication)
        current_pga_event_name = None

        for tour in tours:
            event_grid = await _build_golf_tour_grid(
                service, tour, config, db, trend_hours, top, candidates=candidates,
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
                        candidates=candidates,
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
            "movers_degraded": primary.get("movers_degraded", False),
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


# ---------------------------------------------------------------------------
# Golf candidate markets — one query per grid build, and one that uses an index
# ---------------------------------------------------------------------------

# ``FuturesMarket.external_id`` is not one id space. It is one column holding
# several, and which one a row holds is decided entirely by ``source`` —
# ``models.py`` says so out loud: "sport_key or event_ticker". Golf's
# ``config.sport_keys`` ("golf_pga", "golf_masters", …) are Odds API sport keys,
# so only ``odds_api`` rows can ever match them. There are twelve of those in the
# whole table.
#
# Leaving that unsaid is what made the golf grid a seq scan. An OR across two
# columns with no composite index is a decision to read the whole table:
# Postgres stopped trying and read all 911,284 rows to return 96, once per tour.
# Naming the source turns each branch into its own index scan under a BitmapOr.
# Measured on production 2026-08-29 against the exact SQL this builds:
# 6,122 ms / 50,364 blocks off disk -> 483 ms / 1,346 blocks, identical 96 rows.
_GOLF_SPORT_KEY_ID_SPACE_SOURCE = "odds_api"


def _build_golf_candidate_filters(config: LeagueConfig) -> list:
    """WHERE clauses selecting every golf market the tour grids can draw on.

    Pure — a config in, SQLAlchemy clauses out, no session and no I/O. The
    defect this replaces had exactly one symptom, a query plan: it selected the
    right rows, so a results test passes against it and a timing test merely
    gets slower on a bad day. The guard suite therefore asserts the *shape* of
    what is sent to Postgres, and it can only do that if building the shape is
    separable from running it.
    """
    sport_key_prefixes = [
        FuturesMarket.external_id.ilike(f"{sk}%") for sk in (config.sport_keys or [])
    ]
    # The category branch is deliberately NOT source-scoped. ``llm_sport_category``
    # is written for kalshi and polymarket rows too, and they are where all 96
    # candidates actually come from — the sport-key branch contributes rows only
    # from the twelve-row odds_api space. Scoping both spaces to one source would
    # be faster still, silent, and would empty the grid. See the second-door test.
    category_branch = FuturesMarket.llm_sport_category == "golf"
    if not sport_key_prefixes:
        market_filter = category_branch
    else:
        market_filter = or_(
            and_(
                FuturesMarket.source == _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
                or_(*sport_key_prefixes),
            ),
            category_branch,
        )
    return [
        market_filter,
        FuturesMarket.status != "resolved",
        FuturesMarket.source != "datagolf",
    ]


async def _load_golf_candidate_markets(db: AsyncSession, config: LeagueConfig) -> list:
    """Load the golf candidate market set (markets + outcomes) in one query."""
    stmt = (
        select(FuturesMarket)
        .where(*_build_golf_candidate_filters(config))
        .options(selectinload(FuturesMarket.outcomes))
    )
    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


class GolfCandidateMarkets:
    """Request-scoped lazy holder for the golf candidate set.

    Every tour grid and every upcoming-major grid in a single build issued the
    *identical* query — same config, same category, nothing tour-dependent in the
    SQL — and then filtered the identical 96 rows differently in Python. Three
    active tours meant three full scans inside a 25 s request budget.

    Deliberately an instance, not a module-level dict: it holds live ORM rows
    bound to one build's session, and gotcha #6 is that a module-global cache
    must never do that. Lazy, so an off-season build where no tour has an event
    still issues no query at all. ``loads`` is public so the guard suite can
    assert "one query across three tours" without monkeypatching the session.
    """

    __slots__ = ("_db", "_config", "_markets", "loads")

    def __init__(self, db: AsyncSession, config: LeagueConfig):
        self._db = db
        self._config = config
        self._markets: list | None = None
        self.loads = 0

    async def get(self) -> list:
        if self._markets is None:
            self._markets = await _load_golf_candidate_markets(self._db, self._config)
            self.loads += 1
        return self._markets


async def _resolve_golf_candidates(
    db: AsyncSession, config: LeagueConfig, candidates: "GolfCandidateMarkets | None",
) -> list:
    """Use the build's shared candidate set, or load one if called standalone."""
    if candidates is not None:
        return await candidates.get()
    return await _load_golf_candidate_markets(db, config)


async def _query_tournament_db_markets(
    db: AsyncSession, config: LeagueConfig, tournament_name: str, tour: str,
    candidates: "GolfCandidateMarkets | None" = None,
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

    all_db_markets = await _resolve_golf_candidates(db, config, candidates)

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
                # Explicit cell state. Additive — existing consumers keep reading
                # merged_probability. Register-backed grids additionally emit
                # "won"/"eliminated"/"missing" cells, which carry no probability.
                "state": "live",
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
    candidates: "GolfCandidateMarkets | None" = None,
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
            db, config, current_event.event_name or "", tour, candidates=candidates,
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
            # #1844 acceptance 2: a partial mover read declares itself rather
            # than rendering as "no movement".
            "movers_degraded": getattr(old_probs, "degraded", False),
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
    candidates: "GolfCandidateMarkets | None" = None,
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

    # Same candidate set as every tour grid in this build — identical SQL, only
    # the Python-side tournament filter below differs.
    all_db_markets = await _resolve_golf_candidates(db, config, candidates)

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
                # Explicit cell state. Additive — existing consumers keep reading
                # merged_probability. Register-backed grids additionally emit
                # "won"/"eliminated"/"missing" cells, which carry no probability.
                "state": "live",
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
                # ANNOTATED — queue 333, C272/B4 zero-read census (#1620).
                # NOT dead: the backend reads this itself — `playoff_grid.py:33` selects
                # `seq_cols` on exactly this attribute — so it is live grid SEMANTICS
                # that happens also to be serialized. It rides along so a client can
                # reproduce the same column logic instead of re-deriving it from column
                # order and getting a different answer.
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
        # #1844 acceptance 2: a partial mover read declares itself rather than
        # rendering as "no movement".
        "movers_degraded": getattr(old_probs, "degraded", False),
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

#: The tours the `/playoffs/golf` schedule section is built from, in render
#: order. Frozen here rather than inline so the warmer fetches exactly what the
#: route serves.
GOLF_SCHEDULE_TOURS: tuple[str, ...] = ("pga", "euro", "kft", "opp", "alt")

#: Primary cache key for the CLOCK-FREE tour payloads. Deliberately a sibling of
#: `bainluck:category:playoffs:golf` (the grid on the same page), because the two
#: are warmed by the same hourly task and a reader looking for one should find
#: the other.
GOLF_SCHEDULE_CACHE_KEY = "bainluck:category:playoffs:golf:schedule"

#: 65 minutes, and the number is the #901 lesson applied one endpoint later: the
#: warm cadence is hourly, so a 3600s TTL expires marginally BEFORE the next warm
#: and hands a cold rebuild to whoever arrives in the gap. The TTL must outlive
#: the cadence that refreshes it.
GOLF_SCHEDULE_TTL_S = 3900

#: 24h last-good mirror, matching the grid's. Serving week-old tournament dates
#: is right; serving nothing while DataGolf is down is not.
GOLF_SCHEDULE_STALE_TTL_S = 86400

#: The upstream `status` values that actually mean A BALL IS IN THE AIR.
#:
#: #7690 rung 2 taught the date test to ask whether a tournament had STARTED, and
#: measured on production immediately afterwards it changed nothing, because the
#: rung above it never let the dates be consulted: it asked only
#: `status != "completed"`, and DataGolf's live vocabulary on `get-schedule` is
#: `{"completed", "upcoming"}` — 38 and 9 of 47 pga rows on 2026-09-21, with the
#: Presidents Cup (start 2026-09-24) carrying `"upcoming"`. So "not finished" was
#: read as "in progress" for every tournament on the calendar, and the first one
#: of them won the `break`.
#:
#: An ALLOWLIST rather than a wider denylist, because the two directions fail in
#: opposite directions and only one of them is safe: a value we have not seen
#: before must not be able to assert that play is underway. Anything unrecognised
#: — including `"upcoming"` — falls through to the date window, which is the
#: honest test and the authority. An explicit upstream status can therefore only
#: ADD a tournament the dates would have missed (a delayed finish, a Monday
#: playoff), never invent one that has not teed off.
GOLF_LIVE_STATUSES: frozenset[str] = frozenset(
    {"in-progress", "in_progress", "in progress", "inprogress", "active", "live", "started"}
)


def _golf_status(tournament: dict) -> str:
    """One upstream `status`, folded once, for every comparison in the cascade.

    Case and surrounding space are upstream formatting, not meaning. The point of
    a single helper is that the liveness test and the terminal `completed` test
    cannot drift apart: fold on one side only and a row can be neither finished
    nor live, which is precisely the gap a badge falls through.
    """
    return (tournament.get("status") or "").strip().lower()


async def fetch_golf_schedule_raw() -> dict:
    """Fetch every tour's schedule from DataGolf. Contains NO clock-derived state.

    Two properties this function is shaped around:

    **It is parallel.** The five tours are five independent external round trips
    and the old code awaited them one after another, so the user paid the sum.
    Nothing downstream depends on the order they *complete* in — only on the
    order they are *rendered* in — so `gather` is answer-identical, and
    `return_exceptions=True` preserves the old per-tour tolerance exactly: a tour
    that raises is logged and skipped, its siblings survive (gotcha #42).

    **It is clock-free.** Everything time-dependent — `is_current`,
    `display_status`, `current_event_id` — is derived in `shape_golf_schedule`
    from a `now_str` passed at SERVE time, never baked in here. That is what makes
    this payload safe to cache for an hour: a cached response cannot print a
    "This Week" badge on last week's tournament, because the badge is not in the
    cache. Only DataGolf's own `status`/`current_round` can age, and those move on
    a scale of days.
    """
    import asyncio as _asyncio

    from app.services.datagolf_api import DataGolfAPIService

    service = DataGolfAPIService()
    try:
        results = await _asyncio.gather(
            *(service.get_schedule(tour=tour) for tour in GOLF_SCHEDULE_TOURS),
            return_exceptions=True,
        )
    finally:
        await service.close()

    tours = []
    for tour, schedule in zip(GOLF_SCHEDULE_TOURS, results):
        if isinstance(schedule, BaseException):
            logger.warning("Golf schedule [%s]: error: %s", tour, schedule)
            continue
        if not schedule:
            continue
        tours.append({
            "tour": tour,
            "tournaments": [
                {
                    "event_id": t.event_id,
                    "event_name": t.event_name,
                    "course": t.course,
                    "start_date": t.start_date,
                    "end_date": t.end_date,
                    "location": t.location,
                    "country": t.country,
                    "status": t.status,
                    "current_round": t.current_round,
                }
                for t in schedule
            ],
        })

    return {
        "tours": tours,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def shape_golf_schedule(raw: dict, now_str: str) -> dict:
    """Turn a cached raw payload into the response, applying TODAY's date.

    Pure and clock-injected on purpose (gotcha #44): the caller supplies
    `now_str`, so the same cached bytes shape differently on two different days
    and a test can prove it without faking a clock.

    The status cascade is carried over verbatim from the pre-cache route — the
    same order, the same `break` semantics, the same fallbacks — because the ship
    here is latency, and a rendering change smuggled in beside it would be
    invisible in the timings.
    """
    tour_schedules = []
    for entry in raw.get("tours") or []:
        tour = entry.get("tour")
        tournaments = entry.get("tournaments") or []
        if not tournaments:
            continue

        tour_label = _TOUR_LABELS.get(tour, str(tour).upper())

        # Find current event for this tour
        current_event_id = None
        for t in tournaments:
            # #7690 rung 1. This used to read "any status that is not
            # `completed`" as in-progress, which is how a tournament three days
            # out kept the THIS WEEK badge even after the date rung below was
            # taught to require a start: DataGolf stamps future events
            # `"upcoming"`, so this rung fired and broke before the dates were
            # ever consulted. Only a status that genuinely means play is
            # underway short-circuits now; see GOLF_LIVE_STATUSES.
            if _golf_status(t) in GOLF_LIVE_STATUSES:
                current_event_id = t.get("event_id")
                break
            # #7690: this rung used to ask only "has it not finished yet", and
            # the list is chronological — so the first UNFINISHED tournament is
            # the NEXT one, and between tournaments the next event was always
            # badged "THIS WEEK". On 2026-09-20 that put the badge on a
            # Presidents Cup starting 2026-09-24. A tournament is current only
            # while the day sits INSIDE its window; no break when it does not,
            # because a future event must not stop the scan.
            if (
                t.get("start_date")
                and t.get("end_date")
                and t["start_date"] <= now_str <= t["end_date"]
            ):
                current_event_id = t.get("event_id")
                break

        events = []
        for t in tournaments:
            is_current = t.get("event_id") == current_event_id
            # Determine display status. The terminal test reads through the same
            # normalisation as the liveness test above: with one side exact and
            # the other folded, a `"COMPLETED"` row escapes "finished" here and
            # is then eligible to be badged current by the date rung — the same
            # class of defect this fix exists to close, one branch over.
            if _golf_status(t) == "completed":
                display_status = "completed"
            elif is_current:
                display_status = "current"
            elif t.get("start_date") and t["start_date"] > now_str:
                display_status = "upcoming"
            else:
                display_status = t.get("status") or "unknown"

            events.append({
                "event_id": t.get("event_id"),
                "name": t.get("event_name"),
                "course": t.get("course"),
                "start_date": t.get("start_date"),
                "end_date": t.get("end_date"),
                "location": t.get("location"),
                "country": t.get("country"),
                "status": display_status,
                "current_round": t.get("current_round"),
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
        # The time the DATA was fetched, not the time this response was
        # assembled. Once a cache exists the two differ, and a serve-time stamp
        # on hour-old bytes is a claim of freshness the payload cannot back.
        "last_updated": raw.get("fetched_at"),
    }


@router.get("/golf/schedule")
async def get_golf_schedule():
    """Return golf season schedule from DataGolf across all tours (Redis-cached).

    Returns tournaments grouped by tour with status indicators
    for current/upcoming/completed events.

    LAT-P126: this used to make five sequential DataGolf calls on EVERY request,
    with no cache of any kind — three reads in a row measured 0.74 / 0.80 / 0.69 s
    against a 0.25 s floor. The `/playoffs/golf` page's other half, the
    championship grid, has been Redis-cached and hourly-warmed since #901; the
    schedule section beside it was never given the same treatment, so every first
    visit paid the external round trips.

    The middleware's blanket `public, max-age=300` on `/api/playoffs/` does not
    cover this: it is per-browser, so it helps a reload and does nothing for the
    first load — which is the load this lane exists to fix.
    """
    if not os.getenv("DATAGOLF_API_KEY"):
        raise HTTPException(status_code=503, detail="DataGolf API not configured")

    import json

    from app.tasks.redis_state import get_async_redis_client

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        rc = get_async_redis_client()
        try:
            cached = await rc.get(GOLF_SCHEDULE_CACHE_KEY)
        finally:
            await rc.aclose()
        if cached:
            return shape_golf_schedule(json.loads(cached), now_str)
    except Exception:
        pass  # Fall through to a live fetch

    try:
        raw = await fetch_golf_schedule_raw()
    except Exception as e:
        logger.error("Golf schedule error: %s", e)
        # Last-good rather than a 500: a week-old schedule is a real answer, an
        # error page is not (#1484's rule, applied to this endpoint).
        stale = await _read_golf_schedule_stale()
        if stale is not None:
            return _mark_last_good(
                shape_golf_schedule(stale, now_str), "fetch_failed", degraded=True
            )
        raise HTTPException(status_code=500, detail="Failed to fetch golf schedule")

    if not raw.get("tours"):
        # Every tour failed or returned nothing. The old code returned
        # `{"tours": []}` here, which renders as a page with no schedule section
        # at all — indistinguishable from "golf has no season". Prefer last-good,
        # and never cache the empty answer over a good one (gotcha #53).
        stale = await _read_golf_schedule_stale()
        if stale is not None:
            return _mark_last_good(
                shape_golf_schedule(stale, now_str), "empty_fetch", degraded=True
            )
        return shape_golf_schedule(raw, now_str)

    try:
        rc = get_async_redis_client()
        try:
            payload = json.dumps(raw, default=str)
            await rc.set(GOLF_SCHEDULE_CACHE_KEY, payload, ex=GOLF_SCHEDULE_TTL_S)
            await rc.set(
                f"{GOLF_SCHEDULE_CACHE_KEY}:stale",
                payload,
                ex=GOLF_SCHEDULE_STALE_TTL_S,
            )
        finally:
            await rc.aclose()
    except Exception:
        pass  # A cache that cannot be written must not fail the request

    return shape_golf_schedule(raw, now_str)


async def _read_golf_schedule_stale() -> dict | None:
    """Read the 24h last-good raw payload, or None. Never raises."""
    import json

    from app.tasks.redis_state import get_async_redis_client

    try:
        rc = get_async_redis_client()
        try:
            raw = await rc.get(f"{GOLF_SCHEDULE_CACHE_KEY}:stale")
        finally:
            await rc.aclose()
        if raw:
            candidate = json.loads(raw)
            if isinstance(candidate, dict) and candidate.get("tours"):
                return candidate
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Degradation labelling (#1484)
# ---------------------------------------------------------------------------

def _grid_payload_usable(payload) -> bool:
    """Whether a cached grid payload is worth serving as last-good.

    A last-good payload must actually carry teams. An empty grid — including a
    previously-cached timeout envelope — is NOT a usable fallback: serving one
    would re-create the exact "zero teams looks like a real answer" failure this
    guard exists to remove.
    """
    if not isinstance(payload, dict):
        return False
    if payload.get("error"):
        return False
    teams = payload.get("teams")
    return isinstance(teams, list) and len(teams) > 0


GRID_FAILURE_TIMEOUT = "timeout"
GRID_FAILURE_DB_CANCELED = "db_query_canceled"

_GRID_FAILURE_PHRASE = {
    GRID_FAILURE_TIMEOUT: "timed out",
    GRID_FAILURE_DB_CANCELED: "was cancelled by the database",
}


def degraded_grid_detail(
    league_slug: str, reason: str = GRID_FAILURE_TIMEOUT
) -> str:
    """The sentence a reader sees when the grid 503s (#1484, UX-P175).

    Public and named rather than inlined at the ``raise`` site because it is a
    CROSS-LAYER string: the route emits it, ``apiFetch`` preserves it, and
    ``/playoffs/[sport]`` renders it verbatim in place of "Failed to load".
    Re-typing it on the frontend side would make two layers agree today from two
    sources and drift apart later with nothing going red — so the frontend
    fixture is generated FROM this function and
    ``test_playoff_degraded_contract.py`` fails if the two ever diverge.

    The wording is load-bearing. "not an empty league" exists because the
    failure mode being corrected is a reader concluding the competition has no
    markets, which is the same false claim UX-P173 removed from the empty state.

    ``reason`` names WHICH failure produced the 503. #2303 added a second one —
    a Postgres ``statement_timeout`` firing below the route's own 25 s wall — and
    the two are not the same sentence: telling a reader the grid "timed out" when
    the database cancelled it sends them to the wrong place. The phrase varies;
    the "not an empty league" clause never does. Defaults to the timeout wording
    so the generated fixture and every existing single-argument caller are
    unaffected.
    """
    phrase = _GRID_FAILURE_PHRASE.get(reason, "could not be built")
    return (
        f"Playoff grid for '{league_slug}' {phrase} and no last-good "
        f"payload is available. This is a degraded state, not an empty league."
    )


def _mark_last_good(payload: dict, reason: str, *, degraded: bool) -> dict:
    """Label a last-good serve. Additive fields only; existing keys untouched.

    Two DIFFERENT conditions share this path and must not share a severity:

    * ``degraded=False`` (``reason="cache_miss"``) — routine. The fresh key was
      cold, so the bounded last-good key answered. The data is a real, complete
      grid; it is just not this minute's build. Marked ``stale`` so consumers can
      see it, but NOT ``degraded``: treating an ordinary between-warms serve as a
      failure would fire RED on three healthy grids every deploy, which is the
      cry-wolf the Grid Sentinel exists to avoid.
    * ``degraded=True`` (``reason="timeout"``) — the live build FAILED and we are
      substituting old data for a measurement we could not make. That is a real
      defect and must read as one.
    """
    if not isinstance(payload, dict):
        return payload
    payload["stale"] = True
    payload["stale_reason"] = reason
    if degraded:
        payload["degraded"] = True
        payload["degraded_reason"] = reason
    return payload


# The two ways a grid build can fail without finishing, and the phrase each one
# puts in the 503 body. Both produce the SAME response shape (see
# ``_serve_grid_degraded``) because they are the same event to a user: the grid
# could not be built. They keep DIFFERENT reason strings because the Grid
# Sentinel and the precompute log both surface ``degraded_reason`` verbatim, and
# "the route's wall fired" and "Postgres cancelled the statement" send an
# operator to different places.
async def _serve_grid_degraded(
    league_slug: str,
    cache_key: str,
    cache_eligible: bool,
    reason: str,
):
    """The single degradation path: labelled last-good if usable, else 503.

    #1484 built this for the route's own 25 s wall. #2303 found a second way in
    — a Postgres ``statement_timeout`` firing BELOW the wall, which reached the
    client as a bare 500 and bypassed all of it. The two failures are
    indistinguishable to a user, so they are answered by one function rather
    than by two branches that agree today: a duplicated degradation path is a
    path that drifts, and the drift is invisible until the rarer branch fires.

    Never returns a 200 with an empty grid. That is the whole point of #1484 and
    it is preserved here unchanged — an unusable last-good is no last-good.
    """
    import json

    last_good = None
    if cache_eligible:
        from app.tasks.redis_state import get_async_redis_client

        try:
            rc = get_async_redis_client()
            raw = await rc.get(f"{cache_key}:stale")
            await rc.aclose()
            if raw:
                candidate = json.loads(raw)
                if _grid_payload_usable(candidate):
                    last_good = candidate
        except Exception:
            last_good = None

    if last_good is not None:
        return _mark_last_good(last_good, reason, degraded=True)

    raise HTTPException(
        status_code=503,
        detail=degraded_grid_detail(league_slug, reason),
    )


# ---------------------------------------------------------------------------
# Refresh-behind for the last-good serve (#7109)
# ---------------------------------------------------------------------------
#
# 🔴 **A LAPSED GRID KEY USED TO BE SELF-SUSTAINING.** The read path below finds
# the 3900 s fresh key cold, finds the 24 h ``:stale`` mirror usable, serves it
# and STOPS — it rebuilds nothing and rewrites neither key. So the only thing in
# the system that can end the lapse is ``precompute_category_pages``, which owns
# both writes. For a league that beat cannot warm, "stale" is not a window that
# closes: every subsequent read is answered by the same mirror until it expires
# a day later, and the next read after THAT pays a cold build.
#
# Measured on production 2026-09-19 (#7109, found paying #7076's after-check):
# ``/api/playoffs/mlb`` served a payload built at 00:26:33Z for 3 h 24 m, while
# nhl/nba/nfl warmed inside one 18-second window at 02:25Z. The reader's
# Championship Path read Division 1% / AL Champ 1% / World Series 1% — the exact
# defect #7076 had already FIXED and verified (the cache-bypassing door served
# 1% / 12% / 5%) — plus 22 of 30 MLB team records a game behind. A correct,
# merged, released fix could not reach the page.
#
# The repair is serve-stale-and-REFRESH, and the distinction from a warmer is
# the whole point (LAT-P116 argues it at length in ``routes/events.py``): a
# warmer is a second schedule that can silently stop, and this defect IS that
# schedule silently stopping. A refresh triggered BY the read has no schedule to
# fail — if it never runs, the only consequence is that the next read tries
# again.
#
# 🔴 This does NOT repair the warm beat, and must not be read as having done so.
# MLB still times out on the background worker (``duration_s=89.4`` against a
# ``timeout_s=66.1`` it was offered — a ``wait_for`` overrunning its own deadline
# by 23.3 s, which is a blocking stretch inside the build, not a slow query), and
# the pass that overruns far enough dies at ``time_limit=360`` without writing
# its run report. Those live in ``tasks/precompute_category_pages.py`` and are
# the latency lane's (notice 41). This layer's claim is narrower and is the
# reader's: a league the beat failed to warm now heals on the next read instead
# of waiting a day for the mirror to expire.

#: How long a refresh-behind rebuild may run before it is abandoned. The same
#: wall the reader's own live build gets below, on purpose: this path does, off
#: the reader's clock, exactly the build the reader would otherwise have paid
#: for, so a second and quieter number here would mean a grid that is refusable
#: in the foreground and unbounded in the background. Measured cost of the
#: build this actually runs, three consecutive production reads on 2026-09-19:
#: 5.1 s / 6.4 s / 6.8 s for mlb, the most expensive league in the list.
GRID_REFRESH_BEHIND_TIMEOUT_S = 25


async def _rebuild_playoff_grid(league_slug: str) -> None:
    """Rebuild one league's grid behind a last-good serve, and publish both keys.

    Opens its OWN session: the request's ``AsyncSession`` is not ours to hold
    past the response (``_serve_stale_and_refresh``'s contract, and the reason
    that helper takes a zero-arg coroutine function rather than a coroutine).

    🔴 **Publishes only what the READER would accept as last-good.** This writer
    owns the 24 h ``:stale`` mirror as well as the fresh key, so a transiently
    empty build here would not merely fail to help — it would replace a working
    grid with one the route then refuses as a fallback, turning a healthy page
    into a live rebuild, which for a league like NFL is the 503. That is the
    same reasoning, and the same predicate, as the warm task's publish; three
    leagues build empty out of season today, so it is the ordinary case.

    Never raises into the reader's path: ``_serve_stale_and_refresh`` wraps the
    call and logs, leaving the existing cached value alone on any failure.
    """
    import asyncio
    import json

    from app.services.database import async_session_maker
    from app.tasks.redis_state import get_async_redis_client

    cache_key = f"bainluck:category:playoffs:{league_slug}"

    async with async_session_maker() as session:
        # `hours=None, top=10, debug=False` is not a default — it is the ONE
        # shape whose cache keys this writer owns (`cache_eligible` below).
        # Rebuilding any other shape and publishing it here would put a payload
        # under a key the reader asks a different question of.
        result = await asyncio.wait_for(
            get_playoff_grid(league_slug, None, 10, False, session),
            timeout=GRID_REFRESH_BEHIND_TIMEOUT_S,
        )

    if not _grid_payload_usable(result):
        logger.warning(
            "Playoff grid refresh-behind for %s built an unusable/empty "
            "payload — keeping last-good (#7109)",
            league_slug,
        )
        return

    rc = get_async_redis_client()
    try:
        payload = json.dumps(result, default=str)
        await rc.set(cache_key, payload, ex=3900)
        await rc.set(f"{cache_key}:stale", payload, ex=86400)
    finally:
        await rc.aclose()

    logger.info(
        "Playoff grid refresh-behind republished %s (%d teams) — the lapsed "
        "key is no longer self-sustaining (#7109)",
        league_slug,
        len(result.get("teams") or []),
    )


def _schedule_grid_refresh(league_slug: str) -> bool:
    """Kick a rebuild onto the loop behind a last-good serve. Never raises.

    Returns True when a rebuild is running or already in flight. False means the
    lapse was NOT repaired this time — an unrecognised league, no running loop,
    or a dispatch that failed — in which case the caller still serves last-good
    exactly as it did before #7109, and the next read tries again.

    🔴 **The slug is resolved against the league registry before it is used for
    anything, and the RESOLVED value is what travels on.** ``league_slug`` is a
    path parameter, so it is a user-controlled string: interpolating it into a
    log line is log injection (CodeQL ``py/log-injection``, medium — caught on
    this change), and dispatching background work keyed on it would let an
    arbitrary string name a task and a cache key. Resolving through
    ``get_all_league_slugs()`` answers both at once, and it is the honest guard
    rather than a sanitiser: a slug we have no config for has no grid to
    rebuild, so there is nothing here to do for it.

    That registry holds no aliases, which is why the route resolves the path
    slug BEFORE it reaches here (#7766): until it did, every read of
    ``/api/playoffs/ncaab`` fell through this ``return False`` and #7109's
    repair never fired on the one slug the page requests.
    """
    from functools import partial

    # Deliberately the value from OUR registry, not the caller's string — that
    # is what makes everything downstream (task name, log line) untainted.
    slug = next((s for s in get_all_league_slugs() if s == league_slug), None)
    if slug is None:
        return False

    try:
        from app.routes.events import _serve_stale_and_refresh

        return _serve_stale_and_refresh(
            f"playoff_grid:{slug}",
            partial(_rebuild_playoff_grid, slug),
        )
    except Exception:  # noqa: BLE001
        # A refresh that cannot even be dispatched must not turn a working
        # last-good serve into a 500. The reader's payload is already in hand.
        logger.warning(
            "Playoff grid refresh-behind could not be scheduled for %s (#7109)",
            slug,
            exc_info=True,
        )
        return False


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

    # 🔴 #7766. RESOLVE THE ALIAS FIRST, AND USE THE RESOLVED SLUG FOR EVERYTHING
    # BELOW. `get_league_config` resolves aliases, so the build LOOKED
    # alias-safe; nothing else here did. Keyed on the raw path slug,
    # `/api/playoffs/ncaab` and `/api/playoffs/ncaa-basketball` were two grids
    # for one league — and the page requests the alias
    # (`frontend/lib/playoffLeagues.ts`, `/sport/basketball/ncaab`), so the
    # alias is the arm a reader actually sees. Measured 2026-09-21 09:55Z: the
    # alias keys were 164 m stale against 29 m on the canonical, because the
    # hourly warm beat iterates canonical `GRID_WARM_LEAGUES` and #7109's
    # refresh-behind resolves against `get_all_league_slugs()`, which holds no
    # aliases — so the one repair built for a self-sustaining lapse could not
    # fire on the only slug that had one.
    #
    # Staleness was the symptom that found it; the divergence is worse than a
    # clock. `get_playoff_grid` branches on the RAW slug — the NCAA/WNCAA
    # bracket lookups (`league_slug == "ncaa-basketball"`, twice) and the
    # `MatchingOverride.league_slug` query — so a build entered through the
    # alias silently skips them. Measured the same minute: `/ncaab` carried a
    # seed and a region on 41 of 68 teams where `/ncaa-basketball` carried 67.
    # Resolving here is therefore not only the cache fix; it is what makes the
    # two doors build the same grid, which is the precondition for them sharing
    # a key at all.
    league_slug = resolve_league_slug(league_slug)

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
            # Stale fallback: serve old data while recomputing. #1484 changes
            # two things here. (a) It is LABELLED — serving a last-good payload
            # is right, serving it unlabelled made a stale grid
            # indistinguishable from a fresh one to every consumer including the
            # Grid Sentinel. (b) It must be USABLE — an empty grid or a
            # previously-cached timeout envelope is not a fallback, and serving
            # one would launder the failure into a 200. An unusable stale
            # payload falls through to the live rebuild instead.
            stale = await rc.get(f"{cache_key}:stale")
            if stale:
                candidate = json.loads(stale)
                if _grid_payload_usable(candidate):
                    await rc.aclose()
                    # #7109. Serving last-good and STOPPING is what made a
                    # lapsed key self-sustaining: neither key is rewritten, so
                    # only the warm beat could ever end the lapse, and a league
                    # that beat cannot warm stayed on one payload for the
                    # mirror's full 24 h. Refresh behind the serve — the reader
                    # still gets this payload, on this request, at this speed.
                    _schedule_grid_refresh(league_slug)
                    return _mark_last_good(candidate, "cache_miss", degraded=False)
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
        # #1484 truthful degradation. The old behaviour returned
        # ``200 + {"teams": [], "columns": [], "error": "timeout"}``: an empty
        # grid that every consumer reads as a successful response describing a
        # league with no teams. The Grid Sentinel duly filed "MLB grid returned
        # ZERO teams" plus four "missing column" defects — five REAL defects
        # that were all one timeout wearing a healthy costume.
        #
        # Now: serve a validated last-good payload when one exists (explicitly
        # labelled degraded), and otherwise fail with a non-success status so
        # nothing downstream can mistake it for a populated grid.
        logger.error(
            "Playoff grid %s: request timed out after 25s — attempting last-good",
            league_slug,
        )
        return await _serve_grid_degraded(
            league_slug, cache_key, cache_eligible, GRID_FAILURE_TIMEOUT
        )
    except Exception as exc:
        # #2303. A Postgres ``statement_timeout`` fires BELOW this route's 25 s
        # wall (measured: 500 at 20.30 s against a wall that never rang), so the
        # ``asyncio.TimeoutError`` handler above never saw it. It arrived as
        # ``DBAPIError``/``QueryCanceledError``, nothing caught it, and the user
        # got a bare 500 — the exact "failed grid that does not degrade
        # truthfully" #1484 was built to end, entering through a door #1484 did
        # not know about.
        #
        # 🔴 This is NOT a widened ``except``. Only SQLSTATE 57014 is contained;
        # every other database error — a bad predicate, a dead connection, a
        # constraint violation — re-raises here and still becomes a 500, because
        # a 503 that says "degraded, try later" about a query bug is a lie that
        # nobody would ever chase. The re-raise is the load-bearing line.
        if not is_query_canceled(exc):
            raise
        # ``exc_info`` deliberately: containing this must not make it invisible.
        # Sentry's logging integration is how we learn the frequency, and the
        # whole reason #2303 was findable is that the 500s were in Sentry.
        logger.error(
            "Playoff grid %s: database cancelled the build (SQLSTATE 57014) "
            "below the 25s wall — attempting last-good",
            league_slug,
            exc_info=True,
        )
        return await _serve_grid_degraded(
            league_slug, cache_key, cache_eligible, GRID_FAILURE_DB_CANCELED
        )

    if cache_eligible:
        try:
            rc = get_async_redis_client()
            payload = json.dumps(result, default=str)
            # #901: raise TTL 900 -> 3900 so a request-rebuilt grid outlives the
            # hourly precompute warm beat (e.g. immediately post-deploy, before
            # the first warm). 900s expired before the next warm, forcing repeated
            # ~12s cold rebuilds; 3900s bridges to the next warm cycle.
            await rc.set(cache_key, payload, ex=3900)
            await rc.set(f"{cache_key}:stale", payload, ex=86400)
            await rc.aclose()
        except Exception:
            pass

    return result


#: Cell states that record a VENUE SETTLEMENT rather than a price — the
#: register's terminal results (``app.utils.grid_register.TERMINAL_RESULTS``,
#: plus the tournament register's "lost"). A cell in one of these carries no
#: probability and needs none: the outcome has been graded.
_GRID_DECIDED_STATES = frozenset({"won", "eliminated", "lost"})

#: Fraction of the grid's rows that must carry a cell before the column may be
#: called DECIDED (#6442). Measured on all 14 live grids 2026-09-17 06:26Z: of
#: the 33 columns the fleet serves, 22 cover 100% of their rows and the lowest
#: coverage on a column of full-league shape is NBA ``division`` at 29/30 =
#: 0.967, while the defect this floor removes is 1/36 = 0.028. Nothing sits
#: between 0.60 and 0.967, so the floor is not tuned to a boundary case.
_GRID_RESOLVED_COVERAGE = 0.9


def _grid_leg_is_terminal(graded: bool, probability: float) -> bool:
    """A graded leg whose price is AT THE RAIL, and nothing wider (#7387).

    🔴 THE SCOPE LIMITER, and it is the whole correctness of this ship. The
    defect was that ``prob <= 0 or prob >= 1.0`` DELETED graded legs, so the
    repair may only restore that exact population. A graded leg the grid was
    already serving keeps its number, untouched.

    Measured why, on #6532's La Liga relegation fixture, which this got wrong
    first: a mid-season relegation market carries ``api_settlement`` on legs
    that are still quoting — Barcelona ``is_winner=true`` at **0.99**, Levante
    ``false`` at 0.60, Espanyol ``false`` at 0.02. Treating the badge alone as a
    verdict turned three honestly-priced rows into blank terminal cells, which
    is precisely the harm `test_grid_book_refuted_price_6532_pg` exists to
    catch. #6442 had already written the general form of this: *an extreme price
    is a QUOTE, not a grade* — and the mirror holds, a badge on a mid-market
    price is not a settlement.

    At the rail the two agree and there is no number left to lose: the cell was
    going to be dropped entirely, so stating the result strictly beats silence.
    """
    return graded and (probability <= 0 or probability >= 1.0)


#: How long one league's ESPN standings reading is reused. The grid itself
#: caches for 3900s, so this only collapses the cold rebuilds of sibling leagues
#: and dynos; 900s keeps a clinch visible within a quarter hour of ESPN posting
#: it, which matters in the last week of a season when several land per day.
_STANDINGS_CACHE_TTL = 900

#: Both readings ESPN's standings give the grid, empty. The shape every failure
#: path returns, so no caller has to distinguish "absent" from "nothing to say".
_EMPTY_READING: dict[str, dict] = {"claims": {}, "records": {}}


async def _espn_standings_reading(config) -> dict[str, dict]:
    """ESPN's standings reading for one league: clinch claims and records.

    ``{"claims": {}, "records": {}}`` for every failure mode there is — no sport
    key, no ESPN mapping, ESPN dark, Redis down, a parse that raises. **This may
    never be able to blank or badge a grid, or empty a record, on its own
    absence.** The grid rendered without it is exactly the grid we serve today,
    so failing open costs a correction and failing closed would cost the page.

    Read on the request path deliberately rather than from a task: it runs only
    on a cold rebuild (hourly per league, ~12s of work already), one bounded
    call whose client carries its own timeout, and a task would put the ship
    behind a `bainluck-heavy` release (notice 48) for no latency the reader
    would ever notice.
    """
    sport_key = next((k for k in (getattr(config, "sport_keys", None) or []) if k), None)
    if not sport_key:
        return dict(_EMPTY_READING)

    import json

    # `standings`, not the old `clinch`: the cached VALUE changed shape from a
    # claims map to a two-key reading, and a key that outlived its shape would
    # be read back as `{"331": "out"}.get("claims")` — a silent empty reading
    # for the whole TTL. A new shape gets a new key.
    cache_key = f"grid:standings:{sport_key}"
    rc = None
    try:
        from app.tasks.redis_state import get_async_redis_client

        # NOT awaited (#7677). `get_async_redis_client` is a plain `def` that
        # returns the client; only the client's own calls are coroutines.
        # Awaiting the factory raised `TypeError` into the `except` below on
        # every single request, so `rc` was always `None` and this cache never
        # once engaged — a permanent failure wearing a transient one's clothes.
        rc = get_async_redis_client()
        cached = await rc.get(cache_key)
        if cached:
            stored = json.loads(cached)
            if isinstance(stored, dict) and "claims" in stored:
                return stored
    except Exception as exc:
        # Fail open, but never silently: the swallow is what hid #7677 for the
        # whole life of the feature. The read below still runs.
        logger.warning("Grid standings cache read failed for %s: %s", sport_key, exc)
        rc = None

    reading: dict[str, dict] = dict(_EMPTY_READING)
    try:
        from app.services.espn_api import ESPNAPIService

        espn = ESPNAPIService()
        try:
            fetched = await espn.get_standings_reading(sport_key)
        finally:
            await espn.close()
        # `None` is ESPN dark and an empty reading is ESPN answering "nothing to
        # report". Both leave the grid alone, but only the second may be cached
        # — caching a dark read would hold the outage a quarter hour past its end.
        if fetched is None:
            return dict(_EMPTY_READING)
        reading = fetched
    except Exception as exc:
        logger.warning("ESPN standings read failed for %s: %s", sport_key, exc)
        return dict(_EMPTY_READING)

    if rc is not None:
        try:
            await rc.set(cache_key, json.dumps(reading), ex=_STANDINGS_CACHE_TTL)
        except Exception as exc:
            logger.warning("Grid standings cache write failed for %s: %s", sport_key, exc)
    return reading


def _grid_dedup_rank(entry: dict) -> tuple:
    """Which of one source's several legs for a team+column survives (#7387).

    The rule was "keep the LOWEST probability", because a source that matched
    both `Championship` and `Make Championship Game` to one column is quoting
    the second and the genuine market is the cheaper one. That reasoning is
    about QUOTES and silently discarded a verdict: a graded winner sits at 1.0,
    which is the highest number in its group and therefore never chosen, so the
    club went back to rendering a blank.

    Ungraded groups are unchanged — every ungraded leg shares the last rank, so
    ``min`` still picks the lowest price, byte for byte the old behaviour.
    """
    if entry.get("terminal"):
        return (0 if entry.get("is_winner") else 1, entry["probability"])
    return (2, entry["probability"])


def _grid_terminal_state(entries: list[dict]) -> str | None:
    """The cell state a graded leg forces, or ``None`` for an ordinary cell.

    #7387. Settled outranks trading — the same order the register path states
    two hundred lines below ("a terminal result still supersedes it") — so one
    graded leg decides the cell even when another source is still quoting.

    A WINNER OUTRANKS A LOSER, and the asymmetry is not a tie-break for its own
    sake. ``is_winner = true`` is only ever written by a grader reading a
    verdict, while ``is_winner = false`` is the column's own default
    (``server_default=text("false")``); the affirmative claim is therefore the
    better-evidenced one whenever two legs disagree, and a club that has clinched
    must never be published as eliminated on the strength of a default.
    """
    state = None
    for e in entries:
        if not e.get("terminal"):
            continue
        if e.get("is_winner"):
            return "won"
        state = "eliminated"
    return state


def _grid_price_is_decided(p: float, eps: float) -> bool:
    """A price within ε of 0 (eliminated) or 1 (clinched).

    Necessary for a cell to be decided, never sufficient: #6442's Barcelona
    cleared it at 0.99 on a market trading until 2027-04-01. Callers must pair
    it with :func:`_grid_column_still_trading`.
    """
    return p <= eps or p >= 1.0 - eps


def _grid_column_still_trading(entries: list | None, now: datetime | None = None) -> bool:
    """Whether a market behind a grid column has not finished trading (#6442).

    ``entries`` is the column's ``column_data`` list of ``(market, outcome)``.
    A market is still trading when it is not ``status='resolved'`` and its
    ``resolution_date`` — which since CAL-P989 holds Kalshi's ``close_time``,
    "when trading actually stopped", not the ``expiration_time`` backstop — is
    still in the future.

    That direction is the measured-reliable one. ``app/utils/
    kalshi_resolution_window.py`` sampled 179 Kalshi events: **0 of 130 still
    active** markets had a past ``close_time``, so a future ``resolution_date``
    is trustworthy evidence that the question is open. The converse is only
    39/49, which is why a past date is read here as nothing more than "no
    objection" — permission for the price arm, never a settlement on its own.

    ``resolution_date IS NULL`` cannot contradict anything and is skipped;
    gotcha #33 (settled Kalshi markets keep ``status='open'``) is why the
    status test alone would be the wrong gate and why both are read together.
    """
    if not entries:
        return False
    now = now or datetime.now(timezone.utc)
    for market, _outcome in entries:
        if getattr(market, "status", None) == "resolved":
            continue
        rd = getattr(market, "resolution_date", None)
        if rd is None:
            continue
        if rd.tzinfo is None:
            rd = rd.replace(tzinfo=timezone.utc)
        if rd > now:
            return True
    return False


def _grid_column_resolved(
    teams: list,
    key: str,
    eps: float = 0.01,
    entries: list | None = None,
    now: datetime | None = None,
) -> bool:
    """Whether a grid column is season-state RESOLVED (#927, corrected #6442).

    This is a DERIVED display signal only: it reads the existing cells and
    never mutates them or the column set, so grid accuracy is untouched. The
    frontend prints it as the ``DECIDED`` sublabel on the column header and
    then renders every cell as a decided glyph — ``✓`` clinched, ``—``
    eliminated — so a wrong ``True`` does not de-emphasize a column, it states
    a result. E.g. mid-June NBA make_playoffs/division resolve; MLB
    make_playoffs (live spread) does not.

    A column is resolved only when ALL of:

    * **Coverage.** At least ``_GRID_RESOLVED_COVERAGE`` of the grid's rows
      carry a cell for it. #6442: the UCL ``quarterfinal`` column had ONE
      priced club of 36 and resolved, because the old loop appended only cells
      that HAD a value and then ran ``all()`` over a one-element list — the 35
      empty rows were skipped rather than counted against the claim, and the
      page told a reader in September that Barcelona had clinched a
      quarter-final and 35 clubs were out. Absent is not eliminated.
    * **Every present cell decided.** By venue settlement
      (``_GRID_DECIDED_STATES``) or by a price within ε of 0 or 1. A cell that
      is present but neither — state ``missing``, or any unpriced non-terminal
      cell — refuses the column.
    * **No live market contradicting it.** An extreme price is a QUOTE, not a
      grade (the class of #5896/#5771). Barcelona's 0.99 cleared ``p >= 1 - eps``
      on the boundary exactly while ``KXUCLROUND-27QUAR`` was ``status='open'``
      and due to resolve 2027-04-01, seven months out. Settled cells are exempt
      from this test: they carry their own grade, so a column that is decided at
      the venue still resolves even if a straggler market is open.

    Either of the first two faults alone was enough for #6442; both were
    present, and both are now closed independently.
    """
    if not teams:
        return False
    cells = []
    for t in teams:
        cell = (t.get("cells") or {}).get(key)
        if cell:
            cells.append(cell)
    if not cells:
        return False
    if len(cells) < _GRID_RESOLVED_COVERAGE * len(teams):
        return False

    still_trading = _grid_column_still_trading(entries, now=now)
    for cell in cells:
        if cell.get("state") in _GRID_DECIDED_STATES:
            continue
        p = cell.get("merged_probability")
        if p is None:
            return False
        if not _grid_price_is_decided(float(p), eps):
            return False
        if still_trading:
            return False
    return True


# Gender exclusion: Men's leagues should not include Women's markets and vice versa
_GRID_WOMENS_RE = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
_GRID_MENS_RE = re.compile(r"\bMen.?s\b", re.IGNORECASE)
# #6250: this guard shipped covering the six US leagues and NOTHING ELSE, so
# every soccer grid kept the bug it was written to stop. "UEFA Women's
# Champions League 2026-27 Winner" (polymarket 994389) matches
# CHAMPIONS_LEAGUE_CONFIG's `\bChampions\s+League\b` name pattern and its
# `Champions\s+League.*(?:Winner|Champion)` column rule, so it landed in the
# men's Champion column and Real Madrid rendered 0.32 — the mean of the
# women's 0.495 and the men's 0.145, a number neither market states.
#
# The five soccer grids are listed here rather than derived because the list is
# a claim that the refusal was MEASURED for each: the complete delta is ten
# soccer rows (six open, four resolved), enumerated on production 2026-09-15 as
# every soccer market matching ``_GRID_WOMENS_RE`` — all ten are genuine
# women's competitions and none of the five grids is a women's competition, so
# nothing correct is dropped. ``golf`` stays out: PGA/LPGA is a live question
# nobody has measured, and a guess here would silently drop LPGA rows the way
# this omission silently kept them.
#
# ``TestGridGenderGuardCoversEveryConfig`` fails when a new LeagueConfig lands
# in none of the three sets, so the next league cannot skip the guard in
# silence the way the soccer five did.
_GRID_MENS_LEAGUES = (
    "ncaa-basketball", "ncaa-football", "nba", "nhl", "nfl", "mlb",
    "mls", "epl", "la-liga", "champions-league", "bundesliga",
)
_GRID_WOMENS_LEAGUES = ("wnba", "ncaa-women-basketball")
#: Grids that are deliberately NOT gender-filtered, with the reason. Being here
#: is a decision; being in none of the three sets is an oversight.
_GRID_UNGENDERED_LEAGUES = ("golf",)

# Columns that stop trading once the regular season ends — prices sit at
# 99.5%/0.5% for weeks with no updates, so they get a 60-day staleness cutoff
# instead of the usual 7-day one. Module-level so the choice is assertable:
# admitting a knockout column here would let a settled prior tournament merge
# onto the grid at 0%/100%.
_SETTLED_COLUMNS = {"make_playoffs", "division"}


def _build_league_name_conditions(config) -> list:
    """SQL prefilter for Path B.2 — league name patterns pushed down as ILIKE.

    Exists so the grid does not have to load every market in a sport category
    before deciding league membership. The authoritative decision is still
    ``_market_passes_league_filter``, which re-applies the real regexes, so
    this filter has exactly one obligation: **be a SUPERSET of the patterns,
    never narrower.**

    The converter this replaced was narrower — fatally so. It stripped ``\\b``
    and ``\\s`` in a single pass, so ``\\s+`` had already lost its ``\\s`` by the
    time the ``\\s+ → %`` rule ran and was left as a bare ``+``. Every
    multi-word pattern therefore compiled to an impossible literal
    (``\\bLa\\s+Liga\\b`` → ``%La+Liga%``). ``ILIKE`` is total on text, so the
    condition was simply false for every row: no error, no warning, no log
    line. Leagues reachable only by name (la-liga, champions-league, and EPL's
    Champion column) rendered a tidy "no championship odds available yet" over
    markets that were open, tier-1 and freshly priced.
    """
    conditions: list = []
    for pattern_str in (config.league_name_patterns or []):
        sql_pattern = regex_to_ilike(pattern_str)
        if not sql_pattern:
            # Nothing literal survived, so this pattern cannot be pushed down.
            # Dropping it would NARROW the prefilter and hide rows the real
            # regex would have accepted, so widen to the whole category and let
            # Python decide.
            return [FuturesMarket.llm_sport_category == config.sport_category]
        conditions.append(
            and_(
                FuturesMarket.llm_sport_category == config.sport_category,
                FuturesMarket.name.ilike(f"%{sql_pattern}%"),
            )
        )
    if not conditions:
        return [FuturesMarket.llm_sport_category == config.sport_category]
    return conditions


def _market_passes_league_filter(name: str, external_id: str, config) -> bool:
    """Decide whether a market belongs in ``config``'s playoff grid.

    Encapsulates the series -> league gating so it is unit-testable. Order
    matters: gender + universal exclusion run BEFORE any inclusion path, so a
    colliding ticker prefix (e.g. KXNBACUP under the NBA's KXNBA prefix) or a
    colliding market name (e.g. "Pro Basketball Cup Champion" matching the
    ``\\bPro Basketball\\b`` name pattern) cannot leak a *different* competition
    into this league's grid. ``re.compile`` on constant pattern strings is
    module-cached, so per-call compilation here is cheap.
    """
    name = name or ""
    eid = external_id or ""

    # Gender filter: reject women's markets from men's grids and vice versa
    if config.slug in _GRID_MENS_LEAGUES and _GRID_WOMENS_RE.search(name):
        return False
    if config.slug in _GRID_WOMENS_LEAGUES and _GRID_MENS_RE.search(name) \
            and not _GRID_WOMENS_RE.search(name):
        return False

    # Universal league exclusion (series -> league gating).
    if config.external_id_exclude_prefixes and eid and \
            any(eid.startswith(pfx) for pfx in config.external_id_exclude_prefixes):
        return False
    league_exclude = [
        re.compile(p, re.IGNORECASE) for p in config.league_exclude_patterns
    ] if config.league_exclude_patterns else []
    if league_exclude and any(excl.search(name) for excl in league_exclude):
        return False

    # Path A: sport key prefix (Odds API) always passes
    if any(eid.lower().startswith(sk.lower()) for sk in config.sport_keys):
        return True
    # Path B.1: external_id ticker prefix (Kalshi)
    if config.external_id_prefixes and eid and \
            any(eid.startswith(pfx) for pfx in config.external_id_prefixes):
        return True
    # Path B.2: league name pattern in market name (Polymarket)
    league_patterns = [
        re.compile(p, re.IGNORECASE) for p in config.league_name_patterns
    ] if config.league_name_patterns else []
    if league_patterns:
        if any(pat.search(name) for pat in league_patterns):
            # Champions League: reject "qualify TO UCL" markets from domestic leagues.
            if config.slug == "champions-league" and re.search(
                r"\b(?:qualif|spot|place|make.*champions|top\s*\d)\b",
                name, re.IGNORECASE,
            ):
                return False
            return True
        return False
    # No league_name_patterns configured -> all category matches pass
    return True


#: Which source OWNS each external-id space the grid matches on.
#:
#: ``FuturesMarket.external_id`` is documented in ``models.py`` as "sport_key or
#: event_ticker", and which of the two a given row carries is decided entirely
#: by ``source``. ``LeagueConfig.sport_keys`` holds The Odds API's sport keys;
#: ``LeagueConfig.external_id_prefixes`` holds Kalshi series tickers. This map
#: is that already-documented pairing, written where a query can read it.
GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "odds_api",
    "external_id_prefixes": "kalshi",
}


#: ``_league_pattern_to_ilike`` USED TO LIVE HERE AND IS DELIBERATELY GONE.
#:
#: It converted a league name regex to an ILIKE body by stripping ``\b`` and
#: ``\s`` in one pass, which left every multi-word pattern as an impossible
#: literal (``\bLa\s+Liga\b`` -> ``La+Liga``) that matched no row. LAT-P129
#: lifted it out of ``get_playoff_grid`` and pinned the behaviour as
#: pre-existing (parked P129-2); UX-P173 measured what it cost — whole
#: championship grids rendering "no odds available yet" over open, tier-1,
#: freshly-priced markets — and replaced it with
#: :func:`app.utils.regex_to_ilike.regex_to_ilike`, which widens rather than
#: narrows for anything it cannot represent.
#:
#: The single caller, ``_build_grid_market_filters``, now delegates to
#: :func:`_build_league_name_conditions`. Nothing else may reintroduce a
#: narrowing converter: the prefilter's one obligation is to be a SUPERSET of
#: the real regexes, which ``_market_passes_league_filter`` re-applies.


#: Characters an ``external_id`` prefix may contain for the range bound below to
#: be emitted. Deliberately narrow: every configured prefix is an ASCII ticker or
#: sport key, and a prefix outside this alphabet is a decision for a human, not a
#: default.
_PREFIX_SAFE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-."
)

#: Last characters whose successor is NOT alphanumeric. ``'z' + 1`` is ``'{'``,
#: ``'9' + 1`` is ``':'`` — both punctuation, and this database collates
#: ``en_US.UTF-8``, which IGNORES punctuation at the primary level. A bound ending
#: in punctuation therefore does not mean what it looks like it means, so no bound
#: is emitted at all and the prefix falls back to the bare ``ILIKE``.
_PREFIX_UNINCREMENTABLE = frozenset("zZ9")


def external_id_prefix_range(prefix: str) -> tuple[str, str] | None:
    """A ``[low, high)`` range that PROVABLY contains every ``ILIKE 'prefix%'``
    match, or ``None`` when no such range can be constructed.

    ``None`` means "no safe bound" and the caller must fall back to the bare
    ``ILIKE`` — a slow query is a correct query; a wrong bound is a missing grid
    column.

    🔴 **The low bound drops the prefix's last character on purpose, and that is
    what makes this a proof instead of a census.** LAT-P129 measured this exact
    20× win, wrote ``external_id >= 'KXMLB' AND < 'KXMLC'``, and **rejected it**:
    this database collates ``en_US.UTF-8``, *a range is only a prefix in ``C``
    collation*, and "same rows today is a coincidence, not an equality"
    (P129-3, parked NEEDS ALEX behind ``text_pattern_ops`` + a migration slot).
    That objection is correct and it is answered here rather than argued around:

    * **``low = prefix[:-1]``.** Every string that starts with ``prefix`` (in any
      case) carries at least one more *non-ignorable* character than
      ``prefix[:-1]`` — namely ``prefix[-1]``, which this function guarantees is
      ASCII alphanumeric. So its PRIMARY weight sequence strictly extends the low
      bound's, and it is greater at the primary level, where no case, accent or
      punctuation tie-break can reach it. ``>= 'KXMLB'`` is NOT safe in the same
      way: glibc sorts lowercase before uppercase at the tertiary level, so a
      hypothetical ``'kxmlb'`` row would sort BELOW ``'KXMLB'`` and be silently
      dropped. ``'KXML'`` has no such case.
    * **``high = prefix[:-1] + succ(prefix[-1])``**, where ``succ`` is refused
      unless it stays inside the same ASCII class (``z``/``Z``/``9`` are refused
      because ``'{'``/``'['``/``':'`` are punctuation, which ``en_US.UTF-8``
      IGNORES at the primary level — a bound that does not mean what it looks
      like). Within a class every collation orders ``b < c``, so a string
      starting with ``prefix`` differs from ``high`` at that character's primary
      weight and is strictly less.

    Neither bound is a claim about today's rows, which is exactly what P129-3
    could not say. A whole-table census is kept as corroboration, not as the
    argument (2026-08-29, all 25 ``(source, prefix)`` pairs configured by all 14
    league configs): **zero** rows match ``ILIKE prefix%`` while falling outside
    the TIGHTER ``[prefix, high)`` range — 54,120 matching Kalshi rows and 9
    matching Odds API rows. The shipped range is a strict superset of the one
    censused (same ``high``, lower ``low``), so zero there implies zero here. A
    direct re-census under the shipped bounds completed 3 of its 6 chunks —
    27,077 matches, 0 out of range — and the other 3 were **statement_timeout,
    a story about the harness and not a difference** (P129's own lesson).
    """
    if len(prefix) < 2:
        # A one-character prefix would leave `low = ''`, which bounds nothing and
        # scans the index from the start. Refuse rather than emit a useless range.
        return None
    if any(ch not in _PREFIX_SAFE_CHARS for ch in prefix):
        return None
    last = prefix[-1]
    if not last.isalnum() or last in _PREFIX_UNINCREMENTABLE:
        return None
    stem = prefix[:-1]
    return stem, stem + chr(ord(last) + 1)


def _external_id_prefix_condition(prefix: str):
    """``external_id`` matches ``prefix``, expressed so an index can serve it.

    🔴 **The ``ILIKE`` is retained and is still the authority.** The two range
    terms are added, never substituted: the result set is
    ``range ∩ ILIKE``, so the only way this can change an answer is by the range
    EXCLUDING a row the ``ILIKE`` matches. That is the property the census below
    measured, and the property the guard suite pins the shape of.

    Why a range at all — measured on production 2026-08-29, the
    ``ncaa-basketball`` candidate scan:

    ``EXPLAIN (ANALYZE, BUFFERS)`` on the EXACT predicate this builder emits,
    production 2026-08-29, three leagues, ILIKE-only vs ILIKE+range:

    ================  ==========  ==========  =========  ==================
    league            OLD ms      NEW ms      rows        heap blocks
    ================  ==========  ==========  =========  ==================
    ncaa-basketball   **24,465**  **984**     12 = 12    73,644 -> 161
    nba               **22,804**  **586**     9,042 = 9,042  74,137 -> 5,033
    ncaa-football     926         1,171       13 = 13    314 -> 314
    ================  ==========  ==========  =========  ==================

    🔴 **Row counts are IDENTICAL in every pair**, including NBA's 9,042 — an
    equivalence measured on a large result set, not inferred from a 12-row one.
    ``ncaa-football`` is the honest null: its arms were already index-served, the
    heap block count does not move, and 926 -> 1,171 ms is trigram-scan variance,
    not a regression. ``mlb`` and ``wnba`` could NOT be measured this way: their
    name patterns render ``'%AL+:East|West|Central%'``, and ``:East`` inside the
    admin ``db-query`` rail's ``text()`` parses as a bind parameter (gotcha #45).
    That is an instrument limit, not a production one — SQLAlchemy binds the
    pattern as a parameter on the real path.

    The in-request reading agrees with the bench: ``/api/playoffs/ncaa-basketball
    ?top=11`` served ``wall=21558 ms; db=20980; app=578; q=26; maxq=16159`` —
    ``maxq`` IS this scan.

    ``external_id ILIKE 'KXMARMADROUND%'`` is not index-usable in ANY form —
    ``ILIKE`` never uses a btree, and this database collates ``en_US.UTF-8`` so
    even ``LIKE`` would need ``text_pattern_ops`` (parked P129-3: DDL, a
    migration slot, gotcha #31). So the planner served the id-space arm from
    ``ix_futures_markets_source`` — *the whole of Kalshi*, 266K rows — and
    rechecked every one of them in the heap. **P129 stopped the 911K-row
    sequential scan; this is the 266K-row remainder it left behind.** A range is
    a plain comparison, so ``uq_futures_source_external`` — ``(source,
    external_id)``, already on the table — serves it as an index scan.
    **No DDL, no migration slot, so P129-3's Alex gate does not apply to this
    form.** The bounds' safety is argued in ``external_id_prefix_range``; the
    ``ILIKE`` staying conjoined is what makes an over-wide bound harmless.
    """
    ilike = FuturesMarket.external_id.ilike(f"{prefix}%")
    bounds = external_id_prefix_range(prefix)
    if bounds is None:
        return ilike
    low, high = bounds
    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )


#: The market tiers a grid COLUMN can be populated from. The resolved backfill
#: has always used this set (``market_tier.in_([1, 2, 3, 4])``); LAT-P332 gives
#: it a name so the candidate scan and the backfill cannot drift apart, and so a
#: future tier is added in one place rather than two.
GRID_COLUMN_TIERS = (1, 2, 3, 4)


def _resolved_tier_bound():
    """A ``resolved`` ticker row is a candidate only at a tier a column can use.

    ═══ LAT-P332 / #7124 — 57,218 rows an hour, to produce nothing ═══

    The ticker arm admits ``resolved`` because division winners settle and the
    grid still has to show them. For an OUT-of-season league that costs nothing.
    For an IN-season one it admits the whole season of per-game Kalshi markets:
    measured on production 2026-09-19, ``KXMLB*`` carried **232 open rows and
    42,714 resolved ones**, 39,504 of them ``market_tier = 5`` — innings, first-
    run, spreads, totals, strikeouts, player props. The phase-1 scan selects
    FULL ``FuturesMarket`` entities, so at the plan's 1,538-byte row width the
    MLB grid moved **~66 MB across the wire every hour to build a 30-row grid**,
    then constructed 43K ORM objects and regex-matched every one of them.

    That is the residual #7124 was actually about. The warm half of that issue
    (the ``GRID_WARM_LEAGUES`` seat) gave ``mlb`` the full 120 s ceiling instead
    of 65.75 s; the very first pass on the new code then failed at 24.3 s with
    ``QueryCanceledError: canceling statement due to statement timeout`` — this
    route's own ``SET LOCAL statement_timeout = '20s'`` firing on that scan.

    🔴 **The bound is measured lossless, not argued.** ``_match_market_to_column``
    has three doors — a tier-matched rule, any rule's name pattern, and the
    ``classify_market_stage`` fallback — so a proof against the config patterns
    alone would be true and beside the point. Every one of the 57,218 rows this
    drops across all 14 league configs was paged out of production and run
    through the REAL ``_market_passes_league_filter`` + ``_match_market_to_column``
    (``.lat587-lossless-full-matcher.py``, 2026-09-19):

    ===================  ==========  ===================  ================
    league               dropped     pass league filter   reach a column
    ===================  ==========  ===================  ================
    mlb                  39,504      39,504               **0**
    nba                  7,366       7,366                **0**
    wnba                 5,474       5,474                **0**
    nhl                  2,806       2,806                **0**
    nfl                  2,068       2,068                **0**
    other 9 leagues      0           0                    0
    ===================  ==========  ===================  ================

    Every dropped row passes the league filter — the Python side is not what
    saves us, the column matcher is — and none reaches a column. The instrument
    is not vacuous: run over the rows this KEEPS, the same code finds 23
    resolved rows that DO reach a column (nba 8, nhl 5, ncaa-basketball 5,
    ncaa-women-basketball 3, wnba 2), which is why ``resolved`` is bounded here
    rather than dropped.

    ``market_tier IS NULL`` is kept deliberately: an untiered row is unclassified,
    not classified-as-junk, and it must not vanish from a grid silently. Today
    there are none in any ticker arm, so this costs nothing and fails open.

    ═══ WHAT THIS BUYS, AND WHAT IT DOES NOT ═══

    🔴 **It is not a scan fix, and the query plan says so.** Alternating
    ``EXPLAIN (ANALYZE, BUFFERS)`` on production, three rounds, MLB:

    ==========  ========  ========  =============  ========
    variant     ms        rows      heap blocks    returned
    ==========  ========  ========  =============  ========
    before      204       43,199    44,000         66.4 MB
    after       553-1004  3,695     **44,000**     5.7 MB
    ==========  ========  ========  =============  ========

    ``market_tier`` lives in the heap, so the bitmap is unchanged and every one
    of those 44,000 blocks is still read; the predicate is evaluated on rows the
    scan already had to touch, which is why the server-side statement gets a few
    hundred ms SLOWER. Reported here rather than left for someone to discover:
    the cold-cache scan of 44,000 blocks is what can still exceed the route's 20 s
    ``statement_timeout``, and closing THAT needs a partial index (DDL, attended,
    gotcha #31) which is not in this change.

    What it buys is everything the plan cannot see — 60.7 MB not sent and 39,504
    ORM entities not built, per league, per hourly pass. That is where the grid's
    time actually goes. Across the five leagues with a ticker arm, the 06:25Z run
    report's own durations are linear in candidate count at **r = 0.993**:

        duration_s = 0.395 ms x candidates + 0.94 s
        nba  9,103 -> 4.2 s   nhl 3,439 -> 2.7 s   nfl 4,744 -> 3.8 s
        wnba 6,094 -> 2.2 s   mlb 43,199 -> 18.1 s

    — against a DB scan of ~200 ms, so ~0.4 ms per candidate is app-side work on
    markets that are discarded a moment later. The model predicts the five
    leagues fall from 31.0 s to 8.4 s a pass, ``mlb`` 18.1 s -> 2.4 s. It is a
    PREDICTION; the after-check grades the run report, not this docstring.
    """
    return or_(
        FuturesMarket.market_tier.is_(None),
        FuturesMarket.market_tier.in_(GRID_COLUMN_TIERS),
    )


def _build_grid_market_filters(config: LeagueConfig):
    """Build the grid's candidate-market filters: ``(with_status, bare)``.

    Three matching paths, unchanged in what they select:

    * **A** — ``external_id`` starts with one of the league's Odds API sport keys.
    * **B.1** — ``external_id`` starts with one of its Kalshi series tickers.
    * **B.2** — ``llm_sport_category`` matches and the market NAME matches one of
      the league's name patterns (Polymarket).

    **A and B.1 are each scoped to the source that owns their id space, and that
    scoping is the whole latency fix.** Without it the predicate is an ``OR``
    across two unrelated columns — ``external_id`` on one side,
    ``llm_sport_category`` + ``name`` on the other — which no single index can
    serve, so Postgres abandons indexes entirely and sequentially scans the
    whole of ``futures_markets``: 911,217 rows, 645K of them Polymarket and 266K
    Kalshi, read to find markets that can only ever be among the **12** odds_api
    rows in the table.

    Measured on production 2026-08-29, EPL:

    ========================  ===========  ==========  ======
    query                     before       after       rows
    ========================  ===========  ==========  ======
    candidate scan            16,503 ms    2,473 ms    37
    resolved backfill         6,246 ms     375 ms      16
    ========================  ===========  ==========  ======

    Before: ``Parallel Seq Scan`` discarding 911,180 rows. After: a ``BitmapOr``
    over ``ix_fm_source_created_at`` and ``ix_futures_name_trgm``. Identical
    result sets.

    The narrowing is **lossless, measured rather than assumed**: across all
    911,217 rows, ZERO non-odds_api rows match any of the 18 configured
    sport_keys and ZERO non-kalshi rows match any of the 7 configured ticker
    prefixes, and ``source`` is NOT NULL with 0 null rows. Because that is a
    fact about data and not a constraint, the guard suite pins it from the
    inside: every ``external_id`` predicate this function emits must be
    conjoined with a ``source`` equality, so a future source that starts minting
    the other's id shape fails a test rather than silently dropping a grid
    column.

    🔴 **Source-scoping was necessary and not sufficient.** It stopped the 911K
    sequential scan and left a 266K one: ``source = 'kalshi'`` was the only term
    in the id-space arm an index could serve, so the planner bitmapped the whole
    of Kalshi and rechecked 265,961 rows in the heap to return 90. See
    ``_external_id_prefix_condition`` for the range bound that closes it — and
    for the measured proof that the bound drops nothing.
    """
    # Paths A and B.1 — one AND-group per id space, each scoped to its source.
    id_space_conditions = []
    for attr, source in GRID_ID_SPACE_SOURCE.items():
        prefixes = getattr(config, attr, None) or []
        prefix_conditions = [
            _external_id_prefix_condition(prefix) for prefix in prefixes
        ]
        if prefix_conditions:
            id_space_conditions.append(
                and_(FuturesMarket.source == source, or_(*prefix_conditions))
            )

    # Path B.2 — category + league name patterns (Polymarket). The name filter is
    # pushed to SQL so the category's whole inventory is never loaded.
    #
    # ═══ WHY THIS DELEGATES (the LAT-P129 / UX-P173 union) ═══
    #
    # This function used to inline the conversion via `_league_pattern_to_ilike`,
    # which stripped `\b` and `\s` in ONE pass — so `\s+` had already lost its
    # `\s` by the time the `\s+ -> %` rule ran and was left as a bare `+`. Every
    # multi-word pattern compiled to an impossible literal (`\bLa\s+Liga\b` ->
    # `%La+Liga%`), and because ILIKE is total on text the condition was simply
    # false for every row: no error, no warning, no log line. LAT-P129 measured
    # that behaviour and deliberately PINNED it as pre-existing (parked P129-2),
    # because widening the candidate set is a product change and that queue's was
    # a latency one. UX-P173 is that product change: it proved the class (la-liga
    # and champions-league rendered "no championship odds available yet" over
    # open, tier-1, freshly-priced markets) and replaced the converter with
    # `regex_to_ilike`, which is a SUPERSET by construction.
    #
    # The two fixes are orthogonal and BOTH are required. LAT-P129's contribution
    # is the source-scoped id-space predicates above, which is what keeps this off
    # the 911,217-row scan; UX-P173's is the converter, which is what lets the
    # name-matched leagues see their rows at all. Delegating here is what composes
    # them — inlining the old converter would keep the grids empty at speed, and
    # the guard in `test_playoffs_league_prefilter.py` exists precisely so that
    # "the builder stopped calling the real converter" fails a test.
    category_conditions = _build_league_name_conditions(config)

    # Ticker-prefixed markets (Kalshi/OddsAPI) can be resolved (e.g. division
    # winners after the regular season) — but only at a tier a column can use,
    # or an in-season league's whole settled per-game inventory rides along
    # (LAT-P332, `_resolved_tier_bound`). Category-matched (Polymarket) stay
    # open/closed to avoid loading thousands of resolved markets.
    ticker_filter = or_(*id_space_conditions) if id_space_conditions else None
    category_filter = or_(*category_conditions) if category_conditions else None

    status_conditions = []
    if ticker_filter is not None:
        status_conditions.append(
            and_(
                ticker_filter,
                or_(
                    FuturesMarket.status.in_(("open", "closed")),
                    and_(
                        FuturesMarket.status == "resolved",
                        _resolved_tier_bound(),
                    ),
                ),
            )
        )
    if category_filter is not None:
        status_conditions.append(
            and_(category_filter, FuturesMarket.status.in_(("open", "closed")))
        )
    market_filter_with_status = (
        or_(*status_conditions)
        if status_conditions
        else FuturesMarket.status.in_(("open", "closed"))
    )
    # The bare filter feeds the resolved backfill, which adds its own status term.
    market_filter = (
        or_(*id_space_conditions, *category_conditions)
        if id_space_conditions or category_conditions
        else None
    )
    return market_filter_with_status, market_filter


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
    # 1r. Register-backed identity (Queue 295) — preferred when one exists
    # -----------------------------------------------------------------------
    # A committed register pins every cell to an exact market/outcome id, so the
    # whole fuzzy candidate scan below is skipped for that league. Leagues with
    # no register keep their existing path byte-for-byte, which makes this
    # cutover per-league and reversible by deleting a file.
    register_data = load_register(config.slug, config.season_pattern)
    register = GridRegister(register_data) if register_data else None
    register_stats: dict[str, int] = {}
    register_entities: dict[int, tuple[str, str]] = {}

    # -----------------------------------------------------------------------
    # 1. Query futures markets that match this league
    # -----------------------------------------------------------------------

    if register is not None:
        # Explicit identity: exactly the pinned market/outcome pairs, keyed by
        # the register's canonical entity. None of the candidate scanning,
        # season regex, stage classification, or name merging below runs.
        column_data, register_entities, register_stats = await _build_register_column_data(
            db, register,
        )
        logger.info(
            "Playoff grid %s: register v%s (%s) resolved %s",
            league_slug, register.version, register.season, register_stats,
        )
    else:
        # Candidate-market filters. Each external-id path is scoped to the source
        # that owns its id space, which is what keeps this off a 911,217-row
        # sequential scan — see `_build_grid_market_filters` for the measurement.
        market_filter_with_status, market_filter = _build_grid_market_filters(config)

        # #1484 bounded compute — phase 1 of a two-phase load: market ROWS only, no
        # outcomes. Every filter between here and the column match (`_market_passes_
        # league_filter`, the season filter, `_match_market_to_column`) reads only
        # market fields (name / external_id / market_tier), so eagerly loading the
        # outcomes of every candidate market was pure waste. In-season MLB matches
        # every per-game Kalshi series (`KXMLB%`) and every Odds-API game market
        # (`baseball_mlb%`), and `selectinload` pulled ALL of their outcomes — the
        # league-specific cost that pushed the MLB grid past its 25s request budget
        # while the out-of-season NBA/NHL grids stayed cheap. Phase 2 (below) loads
        # outcomes only for markets that actually resolved to a grid column, so the
        # response is unchanged and only the wasted I/O is gone.
        stmt = select(FuturesMarket).where(market_filter_with_status)
        result = await db.execute(stmt)
        all_markets = result.scalars().unique().all()

        # Filter by league membership (Python-side) to separate e.g. NBA from NCAAB
        # and reject sibling competitions (e.g. the NBA Cup) whose ticker/name would
        # otherwise leak in. The full gating decision lives in the pure, unit-tested
        # helper _market_passes_league_filter (series -> league gating guard).
        markets = [
            market for market in all_markets
            if _market_passes_league_filter(market.name or "", market.external_id or "", config)
        ]

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
        _stale_skipped = 0
        # #6532. A SEPARATE counter from `_stale_skipped` on purpose: staleness is
        # a clock fact about a row nobody refreshed, and this is a row that IS
        # being refreshed — its book columns are current and its price is not —
        # so collapsing the two would report the loud case as the quiet one.
        _book_refuted_skipped = 0

        # Resolve every market to its column FIRST (market fields only), then load
        # outcomes for just the survivors — phase 2 of the #1484 bounded load.
        matched_markets: list[tuple[FuturesMarket, str]] = []
        for market in markets:
            col_key = _match_market_to_column(market, config)
            if col_key:
                matched_markets.append((market, col_key))

        outcomes_by_market = await _load_outcomes_for_markets(
            db, [m.id for m, _ in matched_markets]
        )
        logger.info(
            "Playoff grid %s: %d/%d markets matched a column; loaded outcomes for those only",
            league_slug, len(matched_markets), len(markets),
        )

        for market, col_key in matched_markets:
            cutoff = _settled_cutoff if col_key in _SETTLED_COLUMNS else _stale_cutoff
            for outcome in outcomes_by_market.get(market.id, ()):
                if outcome.last_updated and outcome.last_updated < cutoff:
                    _stale_skipped += 1
                    continue
                # #6532 — A PRICE THE ROW'S OWN BOOK PRICES OUT IS NOT A CELL.
                #
                # This is the surface the defect was FOUND on, not a rider.
                # `/events/15312074` printed "Relegated 99%" for Real Sociedad
                # under Season context, beneath that club's own 2-1-3 record, on
                # a fixture four days from kick-off; `/sport/soccer/laliga`
                # printed the same number in a column summing to 8.24 where
                # exactly three clubs go down. Both read THIS grid through
                # `services/league_context`, never `/api/futures/{id}`, so the
                # serve-side withholding the futures ladder gained in the same
                # ship would have left every surface the reader complained about
                # unchanged.
                #
                # Row-local and no query: the predicate reads the served price
                # against the two book columns beside it, three fields of one
                # write. Everything measured about it, and why a graded winner is
                # never touched, is in
                # `app.utils.futures_unsupported_price.price_refuted_by_live_book`.
                #
                # BEFORE the bid/ask fallback below, which is the order that
                # matters: that branch AVERAGES the book, so its result can never
                # exceed the ask and asking it this question would always answer
                # no. Only a stored price can be priced out by the book it was
                # stored beside.
                if price_refuted_by_live_book(
                    market.source,
                    outcome.resolution_source,
                    outcome.is_winner,
                    float(outcome.current_probability)
                    if outcome.current_probability is not None
                    else None,
                    float(outcome.current_yes_bid)
                    if outcome.current_yes_bid is not None
                    else None,
                    float(outcome.current_yes_ask)
                    if outcome.current_yes_ask is not None
                    else None,
                ):
                    _book_refuted_skipped += 1
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
                # #7387. A price at the rail is junk from a market that is still
                # trading and a RESULT from one that has been graded, and this
                # line could not tell them apart: it deleted the answers we are
                # most sure of. Eight of thirty MLB clubs — including the four
                # best records in baseball — reached the reader with no
                # Make Playoffs cell at all, which reads as "no data" beside a
                # 90% division cell on the same row.
                #
                # The verdict travels on the outcome itself, so nothing is
                # plumbed: `_grid_terminal_state` re-reads it where the cell is
                # built. Graded legs still face every team-name filter below —
                # a settled "#1 seed" is as much not-a-team as a trading one.
                if not leg_is_graded(outcome.is_winner, outcome.resolution_source) \
                        and (prob <= 0 or prob >= 1.0):
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
        if _book_refuted_skipped:
            # `config.slug` and not `league_slug`, and the difference is not
            # cosmetic: the parameter is a path segment the caller controls and
            # CodeQL reads a new line logging it as `py/log-injection` (medium).
            # The two are the same string on every request that gets this far —
            # `get_league_config` 404s otherwise — so the config object is the
            # same value from a source we own. The neighbouring lines predate the
            # rule and are left alone; this ship does not widen them.
            logger.info(
                "Playoff grid %s: skipped %d outcomes whose own book prices the "
                "stored price out (#6532)",
                config.slug, _book_refuted_skipped,
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
                    FuturesMarket.market_tier.in_(GRID_COLUMN_TIERS),
                )
                .options(selectinload(FuturesMarket.outcomes))
                .limit(50)
            )
            resolved_result = await db.execute(resolved_stmt)
            resolved_markets = resolved_result.scalars().unique().all()
            logger.info("Grid %s: resolved backfill found %d markets", league_slug, len(resolved_markets))
            # 🔴 THIS LOOP HAS NEVER RUN A SINGLE ITERATION (#6250 found it,
            # #6413 owns it). ``league_patterns`` and ``league_exclude`` are
            # locals of ``_market_passes_league_filter`` and
            # ``_get_team_progression_for_event_uncached``; neither is assigned
            # in this function or at module level (AST-checked), so the first
            # iteration raises NameError straight into the ``except Exception``
            # below, which logs "resolved backfill failed (non-critical)" and
            # moves on. Every empty column this was written to fill has stayed
            # empty since it was written.
            #
            # DO NOT "fix" it by defining the two names. The loop has no
            # staleness cutoff and forces ``is_winner`` outcomes to 1.0, so
            # waking it would print LAST season's qualifiers at 100% in this
            # season's empty QF/SF/Final columns — a truth regression dressed
            # as a repair. Whoever revives it owes a season bound AND must call
            # ``_market_passes_league_filter`` rather than this two-of-five
            # copy, which is missing the gender refusal and the ticker
            # exclusion the live path applies.
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
    # #7821. The venue's own per-team ticker suffix, kept per grid key so that an
    # ambiguous prefix merge below can be settled by an id instead of by string
    # length. A key collects one suffix per round it appears in (all five rounds
    # of the bracket spell Florida `FLA`), hence the set.
    ticker_suffixes: dict[str, set[str]] = defaultdict(set)

    for col_key, entries in column_data.items():
        for market, outcome in entries:
            team_name = outcome.name
            if register is not None:
                # The register already decided which entity this outcome is.
                # Never re-derive it from the outcome text — that guess is the
                # bug class this queue removes.
                entity_key, entity_name = register_entities[outcome.id]
                norm = entity_key
                team_name = entity_name
            else:
                norm = _normalize_team_name(team_name)

            graded = leg_is_graded(outcome.is_winner, outcome.resolution_source)
            # A terminal cell publishes no number, so a graded leg that reached
            # the loop through the bid/ask fallback (``current_probability`` NULL)
            # must not be asked for one — `float(None)` would 500 the whole grid
            # for every league. Ungraded rows keep the existing expression
            # exactly, including that pre-existing hazard, which is #7387's
            # neighbour and not its business.
            _raw_p = outcome.current_probability
            _probability = 0.0 if graded and _raw_p is None else float(_raw_p)
            source_entry = {
                "source": market.source,
                "probability": _probability,
                "market_id": market.id,
                "outcome_id": outcome.id,
                "market_name": market.name,
                "volume_24h": market.volume_24h,
                # #7387. The verdict rides the ordinary entry rather than a
                # parallel map, so every alias override, prefix merge and
                # team_id merge below moves it with the row it belongs to. A
                # side map keyed on the pre-merge name would be looked up under
                # a name that no longer exists.
                #
                # `terminal`, not `graded`: only a graded leg AT THE RAIL is one
                # the old filter deleted, and only that population may change.
                # A graded leg the grid already served keeps its number.
                "terminal": _grid_leg_is_terminal(graded, _probability),
                "is_winner": outcome.is_winner is True,
            }

            grid_raw[norm][col_key].append(source_entry)
            _suffix = _ticker_suffix(outcome.external_id, market.external_id)
            if _suffix:
                ticker_suffixes[norm].add(_suffix)
            if not graded:
                # A graded leg stops being written the moment it is graded
                # (`futures_liveness`: the writer refuses it), so its 24h "move"
                # is an artefact of the grading write, not a market movement.
                # Terminal cells publish no trend, so this only keeps the
                # movers list honest.
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
                best = min(source_entries, key=_grid_dedup_rank)
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

    # Register-backed grids skip every heuristic merge below. Entities are
    # already canonical, so prefix / single-letter / word-subset / alias merging
    # can only do harm here (it is what collapsed distinct teams onto each other
    # in the first place).
    norm_names = [] if register is not None else sorted(
        grid_raw.keys(), key=len, reverse=True
    )  # longest first
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

    def _merge_arm_matches(short_name: str, long_name: str) -> bool:
        """Does any of the four name arms join these two keys?"""
        # 1. Prefix merge (location-modifier safe)
        if _should_prefix_merge(short_name, long_name):
            return True
        # 2. Single-letter abbreviation suffix
        # e.g., "los angeles l" → "los angeles lakers"
        if (
            len(short_name) >= 3
            and short_name[-2] == " "
            and short_name[-1].isalpha()
            and long_name.startswith(short_name[:-1])
            and len(long_name) > len(short_name)
            and long_name[len(short_name) - 1] == short_name[-1]
        ):
            return True
        # 3. Word subset merge (e.g., "michigan state" vs "michigan st spartans")
        if len(short_name.split()) >= 2:
            short_expanded = _expand_abbrevs(set(short_name.split()))
            if short_expanded.issubset(_expand_abbrevs(set(long_name.split()))):
                return True
        # 4. Alias-based merge (e.g., "connecticut" ↔ "uconn huskies")
        return _alias_matches(short_name, long_name)

    # #7821. Collect EVERY target a short name matches before binding one, rather
    # than binding the first (longest) and `continue`-ing past the rest. The old
    # loop could not tell "one candidate" from "several" — it just took the
    # longest — so `florida` silently became Florida Atlantic. `norm_names` is
    # still longest-first, so `merge_candidates[short][0]` is exactly what the
    # old loop bound, and a key with a single candidate is unchanged by
    # construction.
    merge_candidates: dict[str, list[str]] = {}
    for i, long_name in enumerate(norm_names):
        for short_name in norm_names[i + 1:]:
            if _merge_arm_matches(short_name, long_name):
                merge_candidates.setdefault(short_name, []).append(long_name)

    # Abbreviations are fetched only for the handful of names in contested
    # families — never for the whole grid, and never as a lookup that could
    # answer "who is `florida`?" on its own.
    _contested = {c for cs in merge_candidates.values() if len(cs) > 1 for c in cs}
    abbreviations = await _team_abbreviations(db, _contested) if _contested else {}

    for short_name, cands in merge_candidates.items():
        merge_map[short_name] = (
            cands[0] if len(cands) == 1
            else _resolve_ambiguous_merge(short_name, cands, ticker_suffixes, abbreviations)
        )

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
    for norm_name in ([] if register is not None else list(grid_raw.keys())):
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
    # entity/norm name -> the row we emitted for it, so register terminal states
    # can be attached later. Rows with no cells are skipped, so this cannot be
    # reconstructed by zipping teams against grid_raw.
    row_by_entity: dict[str, dict] = {}
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

        # Look up team metadata. Register grids key rows by the register's
        # canonical entity, which may not be spelled the way the Team table
        # normalizes, so fall back to the display name before giving up.
        meta = team_meta.get(norm_name) or {}
        if not meta and display_name:
            meta = team_meta.get(_normalize_team_name(display_name)) or {}

        cells = {}
        for col in config.columns:
            entries = col_map.get(col.key, [])
            if not entries:
                continue

            # #7387. A graded leg renders its RESULT and no number, the same
            # shape the register path emits below, which is the shape
            # `lib/gridCellState.ts` already turns into "Clinched"/"Eliminated"
            # on both /playoffs/[sport] and the team page's division race. No
            # client change is owed: the reader states are the frozen C108 five.
            terminal = _grid_terminal_state(entries)
            if terminal is not None:
                cells[col.key] = {
                    "merged_probability": None,
                    "sources": [],
                    "trend_24h": None,
                    "state": terminal,
                }
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
                # Explicit cell state. Additive — existing consumers keep reading
                # merged_probability. Register-backed grids additionally emit
                # "won"/"eliminated"/"missing" cells, which carry no probability.
                "state": "live",
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
            # #7387: a terminal cell carries no number. The Kalshi 0.45-0.65
            # noise test is about an illiquid QUOTE and has nothing to say about
            # a settled result — and `None` in the comparison below would 500.
            if prob is None:
                continue
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

        # Monotonicity: a round is capped at the round a team must already have
        # come through to reach it — `depends_on` where a league declares one,
        # the previous sequential column otherwise.
        #
        # #7076: this was a second, hand-inlined copy of `enforce_monotonicity`
        # (which runs again after normalization, further down). The two read the
        # prerequisite differently the moment one of them learned about
        # `depends_on`, and the copy that ran FIRST is the one that flattened
        # Boston's pennant onto their division cell. One implementation now.
        _grid_enforce_monotonicity([{"cells": cells}], config.columns)

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
        row_by_entity[norm_name] = team_row

    # -----------------------------------------------------------------------
    # 4r. Register terminal + missing states
    # -----------------------------------------------------------------------
    # "Settled means settled": a clinched or eliminated cell renders its result,
    # never a live-looking number. A registered cell whose source has gone away
    # renders an honest empty state and is counted. Both carry no probability,
    # so they are injected AFTER the blend and are invisible to it.
    if register is not None:
        rows_by_entity = row_by_entity
        entity_names = register.entity_names()

        for entry in register.entries:
            status = entry.get("status")
            if status not in ("settled", "missing"):
                continue
            entity_key = entry.get("entity_key")
            row = rows_by_entity.get(entity_key)
            if row is None:
                display = entity_names.get(entity_key, entity_key)
                meta = (
                    team_meta.get(entity_key)
                    or team_meta.get(_normalize_team_name(display))
                    or {}
                )
                row = {
                    "name": display,
                    "short_name": meta.get("short_name") or display,
                    "team_id": meta.get("team_id"),
                    "logo_url": meta.get("logo_url"),
                    "primary_color": meta.get("primary_color"),
                    "secondary_color": meta.get("secondary_color"),
                    "record": meta.get("record"),
                    "conference": meta.get("conference"),
                    "division": meta.get("division"),
                    "region": meta.get("region"),
                    "seed": meta.get("seed"),
                    "cells": {},
                }
                rows_by_entity[entity_key] = row
                teams.append(row)

            stage = entry.get("stage")
            # A live cell for this stage already won on merit; a terminal result
            # still supersedes it, because settled outranks trading.
            if status == "settled":
                row["cells"][stage] = {
                    "merged_probability": None,
                    "sources": [],
                    "trend_24h": None,
                    "state": entry.get("terminal_result"),
                }
            elif stage not in row["cells"]:
                row["cells"][stage] = {
                    "merged_probability": None,
                    "sources": [],
                    "trend_24h": None,
                    "state": "missing",
                }

    # -----------------------------------------------------------------------
    # 4b. Column-sum sanity check
    # -----------------------------------------------------------------------
    # Expected sums: championship ~100%, conference ~200% (2 winners),
    # make_playoffs ~N_spots × 100%. If any column sums to > 2× expected,
    # log a warning. For championship column specifically, reject teams
    # with > 50% single-source probability as likely misclassified.

    # -----------------------------------------------------------------------
    # 4s. ESPN standings — the clinch/elimination authority
    # -----------------------------------------------------------------------
    # D27: authority outranks inference. Until #7663 the only terminal state the
    # grid could know was a venue grade, so an ungraded market left Boston
    # priced at 99.7% the day after it clinched and the Twins priced a 0.8%
    # playoff path after ESPN had eliminated them. A price cannot express the
    # difference — Boston 99.7% (in) and the Cubs 99.5% (not in) sat in the same
    # column on the same morning.
    #
    # Before normalization so the columns are summed over what is actually
    # live, and before `propagate_elimination` so a club ESPN eliminates reaches
    # the pennant and championship cells down the existing ladder rather than a
    # second copy of it.
    standings_reading = await _espn_standings_reading(config)
    clinch_claims = standings_reading.get("claims") or {}
    espn_records = standings_reading.get("records") or {}

    # One `(espn_id, row)` list, shared by both overlays. Built only when ESPN
    # gave us something, so a dark authority costs nothing at all.
    espn_rows = (
        [
            ((team_meta.get(norm_name) or {}).get("espn_id"), row)
            for norm_name, row in row_by_entity.items()
        ]
        if (clinch_claims or espn_records)
        else []
    )

    if clinch_claims:
        from app.utils.espn_clinch import apply_clinch_overlay

        clinch_fixes = apply_clinch_overlay(espn_rows, clinch_claims, config.columns)
        if clinch_fixes:
            logger.info(
                "Playoff grid %s: %d cell(s) set from ESPN standings",
                config.slug, clinch_fixes,
            )

    # The RECORD beside the club's name comes from the same body (#7675). The
    # grid was printing a COMPLETED PRIOR SEASON for three EPL clubs in
    # matchweek 5 — Brighton `14-11-12` (37 games) next to seventeen clubs
    # printing five — because `_get_team_metadata` matches on a name, every one
    # of those clubs owns several `teams` rows, and the row that wins is not the
    # row the ESPN sync updates. Correcting the served value is a display-side
    # choice that does not wait on the duplicate rows being merged (#2693/D35).
    if espn_records:
        from app.utils.espn_clinch import apply_record_overlay

        record_fixes = apply_record_overlay(espn_rows, espn_records)
        if record_fixes:
            logger.info(
                "Playoff grid %s: %d record(s) set from ESPN standings",
                config.slug, record_fixes,
            )

    from app.utils.playoff_grid import (
        normalize_column_sums, enforce_monotonicity, propagate_elimination,
        propagate_division_complement,
    )

    # #7695: the complement of a clinch. The overlay above writes what ESPN says
    # and ESPN speaks only about the club that clinched, so a rival whose
    # division leg the venue has not graded keeps a live price for a division
    # that is already won. Not gated on `clinch_claims`: the winning cell is just
    # as often a venue grade, and this reads the grid rather than the authority.
    # Before normalization, for the reason given above.
    complement_fixes = propagate_division_complement(teams, config.columns)
    if complement_fixes:
        logger.info(
            "Playoff grid %s: %d cell(s) eliminated by a division already won",
            config.slug, complement_fixes,
        )

    # #7458: the trend chart publishes the championship column too, so it needs
    # the factor this actually applied — not a second computation of it.
    applied_column_scales = normalize_column_sums(teams, config.columns, config.slug)

    # Re-enforce monotonicity after normalization — normalize_column_sums can
    # scale conference probabilities upward (to sum to 200%), breaking the
    # per-team monotonicity that was enforced during cell building.
    mono_fixes = enforce_monotonicity(teams, config.columns)
    if mono_fixes:
        logger.info(
            "Playoff grid %s: fixed %d monotonicity violations after normalization",
            league_slug, mono_fixes,
        )

    # A settled cell carries no probability, so the numeric bound above cannot
    # see it: a team the register marks OUT at an earlier stage keeps whatever
    # a champion market still quotes for the later ones. Run the terminal half
    # of the same ladder. After normalization, not before — this removes a
    # false claim, it does not redistribute that team's mass onto the field.
    out_fixes = propagate_elimination(teams, config.columns)
    if out_fixes:
        # `config.slug`, not `league_slug`: the latter is the raw path parameter
        # and logging it is a `py/log-injection` sink (CodeQL flagged this exact
        # line). The config's own slug is the same league, from a literal.
        logger.info(
            "Playoff grid %s: %d cell(s) downstream of an eliminated stage",
            config.slug, out_fixes,
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

    # Collect championship outcome IDs for top N teams.
    trend_outcome_ids, trend_outcome_names = _collect_trend_outcomes(
        teams, grid_raw, championship_col, top
    )

    trend_chart = await _build_trend_chart(
        db,
        trend_outcome_ids,
        trend_outcome_names,
        hours=trend_hours,
        top_n=top,
        column_scale=applied_column_scales.get(championship_col, 1.0),
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
                # Derived display signal (#927): true when every team is decided
                # for this column, so the frontend can de-emphasize it instead
                # of showing dead "live" bars. Does not change probabilities/columns.
                # #6442: the column's own (market, outcome) entries go in too, so
                # the predicate can tell a settled grade from a 0.99 quote on a
                # market that is still trading.
                "resolved": _grid_column_resolved(
                    teams, col.key, entries=column_data.get(col.key)
                ),
            })

    # Group teams by conference if configured
    grouped_teams = None
    if config.conference_split:
        groups: dict[str, list] = defaultdict(list)
        ungrouped = []
        for team_row in teams:
            conf = team_row.get("conference")
            if conf:
                # #6246: the suffix rule that used to live here ("Eastern" →
                # "Eastern Conference", never "SEC" → "SEC Conference") now lives
                # in `canonical_conference` alongside the per-league aliases, so
                # the grid and the event page cannot drift apart. Behaviour for
                # leagues with no alias table is unchanged.
                conf_norm = _grid_conference_key(config.slug, conf)
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
        # #1844 acceptance 2: a partial mover read declares itself rather than
        # rendering as "no movement".
        "movers_degraded": getattr(old_probs, "degraded", False),
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
        # #1844 acceptance 2: a partial mover read declares itself rather than
        # rendering as "no movement".
        "movers_degraded": getattr(old_probs, "degraded", False),
    }
