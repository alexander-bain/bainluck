"""
Prediction market → Event matching for game-level win probability.

Detects game-level binary markets from Kalshi/Polymarket (e.g., "Will Warriors
beat Celtics?" or "Boston at Golden State") and matches them to Event records.
When matched, the prediction market's probability is written to win_prob_snapshots
so it appears as a trend line on the OddsChart alongside sportsbooks, ESPN, etc.
"""

import re
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.utils.name_normalization import normalize_name as _normalize_name
from app.utils.sport_keys import (
    KALSHI_GAME_TICKER_PREFIXES as _KALSHI_GAME_TICKER_PREFIXES,
    KALSHI_TICKER_TO_SPORT_KEY as _TICKER_TO_SPORT_PREFIX,
    LLM_CATEGORY_TO_SPORT_PREFIX as _SPORT_CATEGORY_TO_KEY_PREFIX,
    get_sport_key_from_ticker as get_sport_prefix_from_ticker,
    is_kalshi_game_ticker,
)

logger = logging.getLogger(__name__)


# ── Game-level market detection ──────────────────────────────────────────────

# "Team A at/vs/v/@ Team B" (bare matchup without stat — no colon separator)
# Case-insensitive to handle various capitalizations
_BARE_MATCHUP_RE = re.compile(
    r'^([\w][\w\s.\'\-()]+?)\s+(?:at|vs\.?|v\.?|@)\s+([\w][\w\s.\'\-()]+?)$',
    re.IGNORECASE,
)

# "Team A - Team B" (dash/hyphen separator, common in European sports)
_DASH_MATCHUP_RE = re.compile(
    r'^([\w][\w\s.\'\-()]{2,}?)\s+[-–—]\s+([\w][\w\s.\'\-()]{2,}?)$',
    re.IGNORECASE,
)

# "Will (the) Team A beat/win against Team B?"
_WILL_BEAT_RE = re.compile(
    r'^Will\s+(?:the\s+)?(.+?)\s+(?:beat|defeat|win\s+against)\s+(?:the\s+)?(.+?)\??$',
    re.IGNORECASE,
)

# "Team A to beat/defeat Team B"
_TO_BEAT_RE = re.compile(
    r'^(.+?)\s+to\s+(?:beat|defeat)\s+(?:the\s+)?(.+?)\??$',
    re.IGNORECASE,
)

# "Will (the) Team A win?" (single team, game context implied)
_WILL_WIN_RE = re.compile(
    r'^Will\s+(?:the\s+)?(.+?)\s+win\??$',
    re.IGNORECASE,
)

# "Will (the) Team A win against/over (the) Team B?"
_WILL_WIN_AGAINST_RE = re.compile(
    r'^Will\s+(?:the\s+)?(.+?)\s+win\s+(?:against|over)\s+(?:the\s+)?(.+?)\??$',
    re.IGNORECASE,
)

# Game prop pattern (Team at Team: Stat) — NOT a moneyline market
_GAME_PROP_RE = re.compile(
    r'^(.+?)\s+(?:at|vs\.?|v\.?|@)\s+(.+?):\s+(.+)$', re.IGNORECASE,
)

# Game prop with dash separator (Team - Team: Stat)
_DASH_PROP_RE = re.compile(
    r'^(.+?)\s+[-–—]\s+(.+?):\s+(.+)$', re.IGNORECASE,
)

# Category prefix pattern: "NBA:", "Pro Men's Basketball:", "Football:" etc.
# Kalshi often prefixes game titles with the category, e.g., "NBA: Warriors vs Celtics"
#
# Handles:
#   - League abbreviations: "NBA:", "NFL:", "NHL:", "MLB:", etc.
#   - Pro/Professional variants: "Pro Men's Basketball:", "Professional Basketball Game:", etc.
#   - College: "College Football:", "College Basketball:", etc.
#   - Bare sport names: "Basketball:", "Football:", "Hockey:", etc.
#   - Sport + Game/Match: "Basketball Game:", "Football Match:", etc.
_CATEGORY_PREFIX_RE = re.compile(
    r'^(?:'
    # League abbreviations (no dash-suffix support needed for these)
    r'NBA|NFL|NHL|MLB|MLS|WNBA|NCAAB?|NCAAF?|EPL|Ligue 1'
    r'|'
    # "Pro/Professional [Men's/Women's] <sport> [Game/Match]"
    # Matches: "Pro Men's Basketball", "Professional Basketball Game",
    #          "Professional Men's Hockey", "Pro Women's Soccer Match"
    r'(?:Pro(?:fessional)?)\s+[^:]{2,40}'
    r'|'
    # "College <sport> [Game/Match]"
    # Matches: "College Football", "College Basketball Game"
    r'College\s+[^:]{2,30}'
    r'|'
    # Bare sport names with optional "Game/Match"
    # Matches: "Basketball:", "Football Game:", "Hockey Match:"
    r'(?:Ice\s+Hockey|Basketball|Football|Hockey|Baseball|Soccer|Tennis|Golf|Boxing|MMA)'
    r'(?:\s+(?:Game|Match))?'
    r'|'
    # Olympics prefixes
    # Matches: "Winter Games 2026:", "Winter Olympics:", "Olympics:", "Summer Games 2028:"
    r'(?:Winter|Summer)\s+(?:Games|Olympics)(?:\s+\d{4})?'
    r'|Olympics(?:\s+\d{4})?'
    r'|'
    # Polymarket league names and competition names
    # Matches: "Six Nations:", "Super Rugby Pacific:", "United Rugby Championship:",
    #          "Champions League:", "Copa Libertadores:", "A-League:", "UFC 326:",
    #          "Serie A - Round 24:", "La Liga - Matchday 25:"
    r'(?:La Liga|Serie A|Bundesliga|Six Nations|Super Rugby\s*\w*|United Rugby Championship'
    r'|Champions League|Europa League|Copa (?:Libertadores|America|del Rey)'
    r'|A-League|J[.-]?League|K[.-]?League|Indian Super League'
    r'|Eredivisie|Primeira Liga|Scottish Premiership|Belgian Pro League'
    r'|Super Lig|Allsvenskan|Eliteserien'
    r'|UFC\s*\d*|Bellator\s*\d*|PFL\s*\d*|ONE\s*\d*'
    r'|ATP|WTA|Grand Slam|Australian Open|French Open|Wimbledon|US Open'
    r'|PGA|LIV Golf|DP World Tour'
    r'|Formula\s*1|F1|NASCAR|IndyCar'
    r'|Cricket|IPL|Big Bash|The Ashes'
    r'|Rugby|Top\s*14|Premiership Rugby'
    r')'
    r'(?:\s*-\s*[^:]{1,30})?'  # Optional suffix like "- Round 24", "- Matchday 25"
    r')\s*:\s*',
    re.IGNORECASE,
)


def _strip_category_prefix(market_name: str) -> str:
    """
    Strip category prefixes like "NBA:", "Professional Basketball Game:" from market names.

    Kalshi often prefixes event titles with the sport/league category.
    This normalizes to just the matchup portion for pattern matching.
    """
    return _CATEGORY_PREFIX_RE.sub("", market_name).strip()


# Polymarket " - More Markets" suffix on related markets
_MORE_MARKETS_RE = re.compile(r'\s*-\s*More Markets\s*$', re.IGNORECASE)

# Trailing parenthetical context like "(Lightweight, Main Card)" or "(Round 5)"
# Common in Polymarket fight/UFC markets.
_TRAILING_PAREN_RE = re.compile(r'\s*\([^)]+\)\s*$')

# Championship context suffix like ": Gold Medal (M)" or ": Championship"
# These look like game props to _GAME_PROP_RE but are actually championship
# context on game-level markets (e.g., "USA vs Canada: Gold Medal (M)").
# Strip these BEFORE matchup extraction to avoid false prop detection.
_CHAMPIONSHIP_SUFFIX_RE = re.compile(
    r':\s*(?:.*?(?:gold|silver|bronze|medal|championship|title|final|winner'
    r'|trophy|crown|belt).*)$',
    re.IGNORECASE,
)


def _strip_more_markets(name: str) -> str:
    """Strip Polymarket ' - More Markets' suffix.

    Example: "CF Estrela da Amadora vs. FC Porto - More Markets" → "CF Estrela da Amadora vs. FC Porto"
    """
    return _MORE_MARKETS_RE.sub("", name).strip()


def _strip_trailing_paren(name: str) -> str:
    """Strip trailing parenthetical context from market names.

    Examples:
        "Oliveira vs. Holloway (Lightweight, Main Card)" → "Oliveira vs. Holloway"
        "Fighter A vs Fighter B (Prelims)" → "Fighter A vs Fighter B"
    """
    return _TRAILING_PAREN_RE.sub("", name).strip()


def _strip_championship_suffix(name: str) -> str:
    """Strip championship context suffixes that look like game props.

    Examples:
        "USA vs Canada: Gold Medal (M)" → "USA vs Canada"
        "Team A vs Team B: Championship" → "Team A vs Team B"
        "Lakers vs Celtics: Total Points" → "Lakers vs Celtics: Total Points" (NOT stripped — not championship)
    """
    return _CHAMPIONSHIP_SUFFIX_RE.sub("", name).strip()


# Sport name prefix WITHOUT colon — Kalshi sometimes uses bare sport names
# before the matchup: "Ice Hockey USA vs Canada: Gold Medal (M)"
# (note: no colon between "Ice Hockey" and "USA")
_SPORT_NAME_PREFIX_RE = re.compile(
    r'^(?:Ice\s+Hockey|Field\s+Hockey|Basketball|Football|Hockey|Baseball|Soccer'
    r'|Tennis|Golf|Boxing|MMA|Curling|Figure\s+Skating|Alpine\s+Skiing)\s+',
    re.IGNORECASE,
)


def _strip_sport_name_prefix(name: str) -> str:
    """Strip bare sport name prefix (without colon) from market names.

    Examples:
        "Ice Hockey USA vs Canada: Gold Medal (M)" → "USA vs Canada: Gold Medal (M)"
        "Basketball Team A vs Team B" → "Team A vs Team B"
    """
    return _SPORT_NAME_PREFIX_RE.sub("", name).strip()


# Championship/award keywords that disqualify "Will X win?" markets
_NON_GAME_KEYWORDS = (
    "championship", "title", "trophy", "award", "mvp",
    "cup", "series", "super bowl", "pennant", "division",
    "conference", "playoff", "world series", "stanley cup",
    "premier league", "la liga", "champions league",
    "grand slam", "open", "masters", "medal", "gold",
)

# ── Dash matchup false positive prevention ───────────────────────────────────
# "English Premier League – 2nd Place" or "The Masters - Winner" are NOT matchups.
# These are standings/rankings/award markets that happen to use a dash separator.

# Ordinal placement: "1st Place", "2nd Place", "10th Place", etc.
_ORDINAL_PLACE_RE = re.compile(r'^\d+(?:st|nd|rd|th)\s+place\s*$', re.IGNORECASE)

# Known non-team terms that appear in dash-separated market names
_NON_TEAM_NAMES = frozenset({
    "winner", "loser", "champion", "champions", "mvp",
    "last place", "top scorer", "runner-up", "runners-up",
    "top 4", "top 6", "top 8", "top 10",
    "relegated", "promoted", "promotion", "relegation",
    "golden boot", "golden glove", "ballon d'or",
})


def _looks_like_team_name(name: str) -> bool:
    """
    Check if a name extracted from a dash matchup looks like a team name.

    Rejects ranking terms ("2nd Place"), award terms ("Winner"), and
    league names that are clearly not teams.
    """
    name_stripped = name.strip()
    if not name_stripped:
        return False
    name_lower = name_stripped.lower()
    # Check non-team terms
    if name_lower in _NON_TEAM_NAMES:
        return False
    # Check ordinal placements: "1st Place", "2nd Place", etc.
    if _ORDINAL_PLACE_RE.match(name_stripped):
        return False
    # League names used as market subjects (not as teams)
    # "English Premier League", "La Liga", "Champions League" etc.
    if any(kw in name_lower for kw in ("premier league", "champions league", "la liga",
                                        "serie a", "bundesliga", "ligue 1", "eredivisie")):
        return False
    return True


def is_game_level_market(
    market_name: str,
    category: Optional[str] = None,
    num_outcomes: int = 0,
    external_id: Optional[str] = None,
) -> bool:
    """
    Check if a futures market represents a game-level outcome
    (e.g., "Which team wins this game?") rather than a championship/award future.

    Detection uses multiple signals:
    1. Kalshi ticker pattern (most reliable): "KXNBAGAME-..." always = game
    2. Market NAME pattern matching (regex-based)
    3. Category prefix stripping for prefixed names

    Also handles category-prefixed names (e.g., "NBA: Warriors vs Celtics")
    by stripping the prefix before matching.

    Criteria:
    - Must match a matchup pattern (bare matchup, dash matchup, or "Will X beat Y?")
    - Must NOT be a game prop (those have stats like "Rebounds")
    - OR must have a Kalshi game ticker prefix
    """
    # Signal 1: Kalshi game ticker detection (most reliable)
    if external_id and is_kalshi_game_ticker(external_id):
        return True

    # Signal 2+3: Name pattern matching (with and without prefix/suffix stripping)
    # Uses the same normalization pipeline as extract_matchup() to ensure
    # consistent detection. Includes sport name prefix stripping (e.g.,
    # "Ice Hockey USA vs Canada") and championship suffix stripping (e.g.,
    # ": Gold Medal").
    for variant in _normalize_variants(market_name):
        if _check_game_level(variant):
            return True
    return False


def _check_game_level(name: str) -> bool:
    """Check if a (possibly prefix-stripped) market name is game-level."""
    if not name:
        return False

    # Game prop format ("Team A at Team B: Points") IS game-level — it's
    # tied to a specific game. Check it as a matchup pattern, not a skip.
    if _GAME_PROP_RE.match(name):
        return True
    if _DASH_PROP_RE.match(name):
        return True

    # Check for matchup patterns (order matters: more specific first)
    if _WILL_WIN_AGAINST_RE.match(name):
        return True
    if _WILL_BEAT_RE.match(name):
        return True
    if _TO_BEAT_RE.match(name):
        return True
    if _BARE_MATCHUP_RE.match(name):
        return True
    m = _DASH_MATCHUP_RE.match(name)
    if m:
        # Validate both sides look like team names, not rankings/awards
        # Prevents "English Premier League – 2nd Place" false positives
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        if _looks_like_team_name(team_a) and _looks_like_team_name(team_b):
            return True
        return False  # Dash pattern matched but sides aren't team names
    if _WILL_WIN_RE.match(name):
        # "Will X win?" is only game-level if it's not a championship context
        name_lower = name.lower()
        if any(word in name_lower for word in _NON_GAME_KEYWORDS):
            return False
        return True

    return False


class MatchupInfo:
    """Parsed matchup information from a game-level market."""

    __slots__ = ("team_a", "team_b", "yes_team", "format_type")

    def __init__(self, team_a: str, team_b: str, yes_team: str, format_type: str):
        self.team_a = team_a      # First team in market name
        self.team_b = team_b      # Second team (may be empty for "Will X win?")
        self.yes_team = yes_team  # Which team "Yes" refers to
        self.format_type = format_type  # "bare_matchup", "will_beat", "will_win"


def extract_matchup(market_name: str, external_id: Optional[str] = None) -> Optional[MatchupInfo]:
    """
    Extract team names and determine "Yes" team from a game-level market name.

    Returns MatchupInfo or None if not a recognized format.
    Handles category-prefixed names (e.g., "NBA: Warriors vs Celtics").

    Conventions:
    - "Team A at Team B" → Yes = Team A (first listed team in "at" format)
    - "Team A vs Team B" → Yes = Team A (first listed team)
    - "Team A v Team B" → Yes = Team A (first listed team)
    - "Team A - Team B" → Yes = Team A (first listed team)
    - "Will Team A beat Team B?" → Yes = Team A
    - "Will Team A win against Team B?" → Yes = Team A
    - "Will Team A win?" → Yes = Team A (team_b will be empty)
    """
    # Try progressively more aggressive normalization:
    # 1. Raw name
    # 2. Prefix stripped
    # 3. Parenthetical stripped
    # 4. Both stripped
    for name in _normalize_variants(market_name):
        result = _extract_matchup_impl(name)
        if result:
            return result
    return None


def _normalize_variants(market_name: str) -> list:
    """Generate progressively normalized variants of a market name.

    Applies progressively more aggressive normalization:
    1. Raw name
    2. Category prefix stripped ("NBA: ..." → "...")
    3. Sport name prefix stripped ("Ice Hockey ..." → "...")
    4. Trailing parenthetical stripped ("... (M)" → "...")
    5. Championship suffix stripped (": Gold Medal" → "")
    6. All combinations of the above

    Example: "Ice Hockey USA vs Canada: Gold Medal (M)"
      → strip sport name: "USA vs Canada: Gold Medal (M)"
      → strip championship: "USA vs Canada"
      → matches _BARE_MATCHUP_RE!
    """
    # Strip " - More Markets" first — it's a suffix that pollutes team names
    base = _strip_more_markets(market_name)
    # Start with the cleaner base if different, then fall back to raw
    variants = [base] if base != market_name else [market_name]
    stripped_prefix = _strip_category_prefix(base)
    stripped_sport = _strip_sport_name_prefix(base)
    stripped_paren = _strip_trailing_paren(base)
    stripped_champ = _strip_championship_suffix(base)
    stripped_sport_champ = _strip_championship_suffix(stripped_sport)
    stripped_sport_paren = _strip_trailing_paren(stripped_sport)
    stripped_sport_both = _strip_championship_suffix(_strip_trailing_paren(stripped_sport))
    stripped_prefix_champ = _strip_championship_suffix(stripped_prefix)
    stripped_all = _strip_championship_suffix(_strip_trailing_paren(stripped_prefix))
    for v in (
        base,  # " - More Markets" stripped
        stripped_sport_both, stripped_sport_champ, stripped_sport_paren,
        stripped_sport, stripped_all, stripped_prefix_champ,
        stripped_prefix, stripped_paren, stripped_champ,
    ):
        if v and v != market_name and v not in variants:
            variants.append(v)
    return variants


def _extract_matchup_impl(market_name: str) -> Optional[MatchupInfo]:
    """Core matchup extraction logic."""
    if not market_name:
        return None

    # Game prop format: "Team A at/vs Team B: Stat Type"
    # Extract the matchup — these ARE game-level markets that need event linking.
    # The stat suffix (": Points", ": Spread", etc.) is irrelevant for matching.
    m = _GAME_PROP_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="game_prop")
    m = _DASH_PROP_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="game_prop")

    # "Will Team A win against/over Team B?" (check before will_win)
    m = _WILL_WIN_AGAINST_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="will_beat")

    # "Will Team A beat Team B?"
    m = _WILL_BEAT_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="will_beat")

    # "Team A to beat Team B"
    m = _TO_BEAT_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="to_beat")

    # "Team A at/vs/v Team B" (bare matchup)
    m = _BARE_MATCHUP_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="bare_matchup")

    # "Team A - Team B" (dash matchup)
    m = _DASH_MATCHUP_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        # Validate both sides are team names (not rankings like "2nd Place")
        if _looks_like_team_name(team_a) and _looks_like_team_name(team_b):
            return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="dash_matchup")

    # "Will Team A win?"
    m = _WILL_WIN_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        # Check it's not a championship context
        name_lower = market_name.lower()
        if any(word in name_lower for word in _NON_GAME_KEYWORDS):
            return None
        return MatchupInfo(team_a, "", yes_team=team_a, format_type="will_win")

    return None


def _fuzzy_team_match(market_team: str, event_team: str) -> bool:
    """
    Check if a team name from a prediction market matches an event team name.

    Handles common variations:
    - Full name match: "Boston Celtics" == "Boston Celtics"
    - Substring: "Celtics" in "Boston Celtics"
    - Normalized (accents, case): "lakers" == "Lakers"
    """
    mt = _normalize_name(market_team)
    et = _normalize_name(event_team)

    if not mt or not et:
        return False

    # Exact match
    if mt == et:
        return True

    # One contains the other (for short-form vs full-form)
    # Only if the shorter string is at least 4 chars to avoid "LA" false positives
    if len(mt) >= 4 and len(et) >= 4:
        if mt in et or et in mt:
            return True

    # Word-level matching: check if all words of the shorter name appear in the longer
    mt_words = set(mt.split())
    et_words = set(et.split())
    if len(mt_words) >= 2 and len(et_words) >= 2:
        shorter = mt_words if len(mt_words) <= len(et_words) else et_words
        longer = et_words if len(mt_words) <= len(et_words) else mt_words
        if shorter.issubset(longer):
            return True

    return False


def match_teams_to_event(
    matchup: MatchupInfo,
    event_home_team: str,
    event_away_team: str,
) -> Optional[dict]:
    """
    Determine how a matchup's teams map to an event's home/away teams.

    Returns a dict with:
        - "yes_is_home": True if "Yes" outcome = home team wins
        - "matched_team": which market team matched (for logging)
    Or None if teams can't be matched.
    """
    yes_team = matchup.yes_team

    # Check which event team the "Yes" team matches
    yes_matches_home = _fuzzy_team_match(yes_team, event_home_team)
    yes_matches_away = _fuzzy_team_match(yes_team, event_away_team)

    if yes_matches_home and not yes_matches_away:
        return {"yes_is_home": True, "matched_team": yes_team}
    if yes_matches_away and not yes_matches_home:
        return {"yes_is_home": False, "matched_team": yes_team}

    # If yes_team matches both (rare edge case like "New York" matching both
    # Knicks and Nets), try the other team for disambiguation
    if matchup.team_b:
        other_team = matchup.team_b
        other_matches_home = _fuzzy_team_match(other_team, event_home_team)
        other_matches_away = _fuzzy_team_match(other_team, event_away_team)

        if other_matches_home and not other_matches_away:
            # Other team is home, so yes_team is away
            return {"yes_is_home": False, "matched_team": yes_team}
        if other_matches_away and not other_matches_home:
            # Other team is away, so yes_team is home
            return {"yes_is_home": True, "matched_team": yes_team}

    return None


def _is_prop_or_spread_outcome(name: str) -> bool:
    """
    Check if an outcome name looks like a prop, spread, total, or O/U — NOT moneyline.

    These should be skipped in find_moneyline_outcome() to prevent fuzzy matching
    "Stanford vs Cal: O/U 148.5" as a "Stanford Cardinal" moneyline outcome.

    Catches:
    - Over/Under totals: "O/U 148.5", "Over 220.5", "Under 220.5"
    - Totals/Spreads: "Total Points", "Celtics -3.5", "+4.5"
    - Player props: "Rebounds", "Points", "Assists", "Touchdowns", "Yards", etc.
    """
    if not name:
        return False
    # Colon indicates a prop/stat suffix (e.g., "Celtics vs Warriors: O/U 229.5")
    if ":" in name:
        return True
    name_lower = name.strip().lower()
    # O/U and Over/Under patterns
    if _PROP_OUTCOME_RE.search(name_lower):
        return True
    return False


# Regex patterns that identify prop/spread/total outcomes (not moneyline)
_PROP_OUTCOME_RE = re.compile(
    r'(?:'
    # O/U patterns
    r'o/u\s*\d'
    r'|over\s+\d'
    r'|under\s+\d'
    r'|\btotal\b'
    # Spread patterns: "+4.5", "-3.5" (standalone or after team name)
    r'|[+-]\d+\.?\d*\s*$'
    # Player prop keywords
    r'|\brebounds?\b'
    r'|\bpoints?\s*(?:scored|over|under|\d)'
    r'|\bassists?\b'
    r'|\bstrikeouts?\b'
    r'|\btouchdowns?\b'
    r'|\byards?\b'
    r'|\bgoals?\s*(?:scored|over|under|\d)'
    r'|\bsacks?\b'
    r'|\binterceptions?\b'
    r'|\bthree.?pointers?\b'
    r'|\bhome\s*runs?\b'
    r'|\bhits?\s*(?:over|under|\d)'
    r'|\bblocks?\b'
    r'|\bsteals?\b'
    r'|\bshots?\s*on\s*(?:target|goal)\b'
    r'|\bcorners?\b'
    r'|\bcards?\b'
    r'|\baces?\b'
    r'|\bdouble.?faults?\b'
    r')',
    re.IGNORECASE,
)


def find_moneyline_outcome(
    outcomes: list,
    matchup: MatchupInfo,
    event_home_team: str,
    event_away_team: str,
) -> Optional[tuple]:
    """
    Find the moneyline outcome for the "yes" team from a list of FuturesOutcome objects.

    Polymarket game events may bundle moneyline, spread, and totals as separate
    outcomes under one market. This function identifies the correct moneyline
    outcome by matching outcome names against team names.

    Returns (outcome, yes_is_home) tuple, or None if no moneyline outcome found.

    Strategy:
    1. Try to find an outcome whose name fuzzy-matches either event team
    2. Among matched outcomes, pick the one matching the yes_team
    3. Fall back to first outcome by rank if only 1-2 outcomes exist
    """
    # Build list of outcomes that match a team name
    home_outcomes = []
    away_outcomes = []

    for outcome in outcomes:
        if not outcome.name or outcome.current_probability is None:
            continue
        prob = float(outcome.current_probability)
        if prob <= 0 or prob >= 1:
            continue

        # Skip prop/spread/total outcomes before fuzzy matching
        if _is_prop_or_spread_outcome(outcome.name):
            continue

        if _fuzzy_team_match(outcome.name, event_home_team):
            home_outcomes.append(outcome)
        elif _fuzzy_team_match(outcome.name, event_away_team):
            away_outcomes.append(outcome)

    # Determine yes_is_home from matchup
    team_mapping = match_teams_to_event(matchup, event_home_team, event_away_team)
    if not team_mapping:
        return None

    yes_is_home = team_mapping["yes_is_home"]

    # Pick the outcome matching the "yes" team
    if yes_is_home and home_outcomes:
        return (home_outcomes[0], True)
    elif not yes_is_home and away_outcomes:
        return (away_outcomes[0], False)

    # If we found any team-matched outcome, use it with correct mapping
    if home_outcomes:
        return (home_outcomes[0], True)
    if away_outcomes:
        return (away_outcomes[0], False)

    # Fallback: outcome name is the full matchup (Polymarket pattern)
    # e.g., outcome named "Pistons vs. Bulls" instead of a single team name
    if matchup.team_a and matchup.team_b:
        a_lower = matchup.team_a.lower()
        b_lower = matchup.team_b.lower()
        for outcome in outcomes:
            if not outcome.name or outcome.current_probability is None:
                continue
            prob = float(outcome.current_probability)
            if prob <= 0 or prob >= 1:
                continue
            name_lower = outcome.name.lower()
            # Must contain both teams and NOT have ":" (props/totals/spreads)
            if a_lower in name_lower and b_lower in name_lower and ":" not in outcome.name:
                return (outcome, yes_is_home)

    # Last resort: if 1-2 outcomes with generic names (e.g., "Yes"),
    # fall back to first valid outcome (original behavior for simple binary markets)
    _GENERIC_OUTCOME_NAMES = {"yes", "no", ""}
    if len(outcomes) <= 2:
        for outcome in outcomes:
            if (outcome.name or "").lower().strip() not in _GENERIC_OUTCOME_NAMES:
                continue  # Skip non-generic names (e.g., "Over 220.5")
            if outcome.current_probability is not None:
                prob = float(outcome.current_probability)
                if 0 < prob < 1:
                    return (outcome, yes_is_home)

    return None


# ── Kalshi ticker → team abbreviation extraction ──────────────────────────────
# Ticker format: KXNBAGAME-26FEB21DETCHI
#   - Sport prefix: "kxnbagame"
#   - Separator: "-"
#   - Date: "26FEB21" (YYMMMDD)
#   - Teams: "DETCHI" (concatenated abbreviations, 2-3 chars each)
#
# The date portion is always: 2-digit year + 3-letter month + 1-2 digit day
# After the date, the remaining characters are the team abbreviations.

_TICKER_DATE_RE = re.compile(
    r'^[a-z0-9]+-(\d{2}[a-z]{3}\d{1,2})(.+)$',
    re.IGNORECASE,
)

# Kalshi team abbreviation → team name fragments.
# These map ticker codes to substrings we can ILIKE match against event team names.
# Only need enough to disambiguate within a sport on a given day.
_KALSHI_TEAM_ABBREVS: dict[str, str] = {
    # NBA
    "atl": "Hawks", "bos": "Celtics", "bkn": "Nets", "cha": "Hornets",
    "chi": "Bulls", "cle": "Cavaliers", "dal": "Mavericks", "den": "Nuggets",
    "det": "Pistons", "gsw": "Warriors", "hou": "Rockets", "ind": "Pacers",
    "lac": "Clippers", "lal": "Lakers", "mem": "Grizzlies", "mia": "Heat",
    "mil": "Bucks", "min": "Timberwolves", "nop": "Pelicans", "nyk": "Knicks",
    "okc": "Thunder", "orl": "Magic", "phi": "76ers", "phx": "Suns",
    "por": "Trail Blazers", "sac": "Kings", "sas": "Spurs", "tor": "Raptors",
    "uta": "Jazz", "was": "Wizards",
    # NFL
    "sf": "49ers", "kc": "Chiefs", "buf": "Bills", "bal": "Ravens",
    "gb": "Packers", "ne": "Patriots", "pit": "Steelers", "sea": "Seahawks",
    "tb": "Buccaneers", "ari": "Cardinals", "car": "Panthers",
    "cin": "Bengals", "jax": "Jaguars", "ten": "Titans",
    "lar": "Rams", "lac_nfl": "Chargers", "nyg": "Giants", "nyj": "Jets",
    "no": "Saints", "lv": "Raiders",
    # NHL
    "bos_nhl": "Bruins", "nyr": "Rangers", "nyi": "Islanders",
    "njd": "Devils", "pit_nhl": "Penguins", "phi_nhl": "Flyers",
    "wsh": "Capitals", "car_nhl": "Hurricanes", "cbj": "Blue Jackets",
    "fla": "Panthers", "tbl": "Lightning", "tor_nhl": "Maple Leafs",
    "mtl": "Canadiens", "ott": "Senators", "buf_nhl": "Sabres",
    "det_nhl": "Red Wings", "chi_nhl": "Blackhawks", "stl": "Blues",
    "nsh": "Predators", "dal_nhl": "Stars", "min_nhl": "Wild",
    "wpg": "Jets", "col": "Avalanche", "ari_nhl": "Coyotes",
    "van": "Canucks", "cgy": "Flames", "edm": "Oilers",
    "sea_nhl": "Kraken", "vgk": "Golden Knights", "sjs": "Sharks",
    "ana": "Ducks", "lak": "Kings",
    "uta_nhl": "Utah Hockey", "la_nhl": "Kings",
    # MLB
    "nyy": "Yankees", "nym": "Mets", "bos_mlb": "Red Sox",
    "lad": "Dodgers", "hou_mlb": "Astros", "atl_mlb": "Braves",
    "phi_mlb": "Phillies", "tex": "Rangers", "ari_mlb": "Diamondbacks",
    "sd": "Padres", "chc": "Cubs", "chw": "White Sox", "cws": "White Sox",
    "det_mlb": "Tigers", "cle_mlb": "Guardians", "min_mlb": "Twins",
    "kc_mlb": "Royals", "stl_mlb": "Cardinals", "mil_mlb": "Brewers",
    "cin_mlb": "Reds", "pit_mlb": "Pirates", "sf_mlb": "Giants",
    "sea_mlb": "Mariners", "oak": "Athletics", "col_mlb": "Rockies",
    "tb_mlb": "Rays", "bal_mlb": "Orioles", "tor_mlb": "Blue Jays",
    "mia_mlb": "Marlins", "was_mlb": "Nationals", "laa": "Angels",
}

# Sport-specific abbreviation subsets (no suffix needed for primary sport)
# The abbreviation lookup tries exact first, then sport-specific suffixed keys.
# Derived from KALSHI_TICKER_TO_SPORT_KEY to cover ALL game/prop ticker prefixes.
_SPORT_KEY_TO_ABBREV_SUFFIX: dict[str, str] = {
    "americanfootball_nfl": "_nfl",
    "americanfootball_ncaaf": "_nfl",
    "icehockey_nhl": "_nhl",
    "baseball_mlb": "_mlb",
    "baseball_ncaa": "_mlb",
}
_SPORT_ABBREV_SUFFIX: dict[str, str] = {
    prefix: _SPORT_KEY_TO_ABBREV_SUFFIX.get(sport_key, "")
    for prefix, sport_key in _TICKER_TO_SPORT_PREFIX.items()
}


def extract_teams_from_ticker(external_id: str) -> Optional[tuple[str, str]]:
    """
    Extract team name fragments from a Kalshi game ticker.

    Example: "KXNBAGAME-26FEB21DETCHI" → ("Pistons", "Bulls")

    Returns (team_a_name, team_b_name) tuple, or None if parsing fails.
    The names are team name fragments suitable for ILIKE matching.
    """
    if not external_id:
        return None

    m = _TICKER_DATE_RE.match(external_id)
    if not m:
        return None

    teams_str = m.group(2).lower()
    # Strip optional time component (e.g., "1910" in KXMLBGAME-26MAR281910CWSMIL)
    # MLB tickers embed game time as 4 digits between date and team abbreviations.
    teams_str = teams_str.lstrip('0123456789')
    if len(teams_str) < 4:  # Need at least 2+2 chars for two teams
        return None

    # Determine sport suffix for disambiguation
    ext_lower = external_id.lower()
    sport_suffix = ""
    for prefix, suffix in _SPORT_ABBREV_SUFFIX.items():
        if ext_lower.startswith(prefix):
            sport_suffix = suffix
            break

    # Try all possible split points (2+2, 2+3, 3+2, 3+3)
    best_pair = None
    for split_at in (2, 3):
        if split_at >= len(teams_str):
            continue
        abbrev_a = teams_str[:split_at]
        abbrev_b = teams_str[split_at:]

        if len(abbrev_b) < 2 or len(abbrev_b) > 3:
            continue

        # Look up both abbreviations (sport-suffixed first for disambiguation)
        if sport_suffix:
            name_a = _KALSHI_TEAM_ABBREVS.get(abbrev_a + sport_suffix) or _KALSHI_TEAM_ABBREVS.get(abbrev_a)
            name_b = _KALSHI_TEAM_ABBREVS.get(abbrev_b + sport_suffix) or _KALSHI_TEAM_ABBREVS.get(abbrev_b)
        else:
            name_a = _KALSHI_TEAM_ABBREVS.get(abbrev_a)
            name_b = _KALSHI_TEAM_ABBREVS.get(abbrev_b)

        if name_a and name_b:
            best_pair = (name_a, name_b)
            break  # First valid split wins

    return best_pair


# Month abbreviation → month number for ticker date parsing
_MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def extract_game_date_from_ticker(external_id: str) -> Optional[datetime]:
    """
    Extract the game date from a Kalshi game ticker.

    Example: "KXNBAGAME-26FEB21DETCHI" → datetime(2026, 2, 21, tzinfo=UTC)

    This is critical because Kalshi's commence_time on game markets is the
    market RESOLUTION date (often weeks after the game), not the actual game
    date. The ticker embeds the real game date as YYMMMDD.

    Returns a timezone-aware datetime at midnight UTC, or None if parsing fails.
    """
    if not external_id:
        return None

    m = _TICKER_DATE_RE.match(external_id)
    if not m:
        return None

    date_str = m.group(1)  # e.g., "26FEB21"

    # Parse: 2-digit year + 3-letter month + 1-2 digit day
    try:
        year = 2000 + int(date_str[:2])
        month_str = date_str[2:5].lower()
        day = int(date_str[5:])
        month = _MONTH_MAP.get(month_str)
        if not month:
            return None
        return datetime(year, month, day, tzinfo=timezone.utc)
    except (ValueError, IndexError):
        return None


def extract_matchup_with_ticker_fallback(
    market_name: str,
    external_id: Optional[str] = None,
) -> Optional[MatchupInfo]:
    """
    Extract matchup from market name, falling back to Kalshi ticker parsing.

    This is the primary entry point for the matching task. It tries:
    1. Name-based extraction via extract_matchup()
    2. Ticker-based team extraction via extract_teams_from_ticker()

    For game props (format_type="game_prop"), the name-based extraction often
    yields abbreviated team names ("WSH Capitals") that fail SQL ILIKE matching
    against full event team names ("Washington Capitals"). When a ticker is
    available, we override with ticker-derived mascot names ("Capitals") which
    ILIKE-match reliably.
    """
    matchup = extract_matchup(market_name, external_id=external_id)

    if matchup and matchup.format_type == "game_prop" and external_id:
        ticker_teams = extract_teams_from_ticker(external_id)
        if ticker_teams:
            matchup.team_a = ticker_teams[0]
            matchup.team_b = ticker_teams[1]

    if matchup:
        return matchup

    # Fallback: parse team abbreviations from Kalshi ticker
    if external_id:
        ticker_teams = extract_teams_from_ticker(external_id)
        if ticker_teams:
            team_a, team_b = ticker_teams
            return MatchupInfo(
                team_a=team_a,
                team_b=team_b,
                yes_team=team_a,
                format_type="ticker_parsed",
            )

    return None


def _expand_team_search_terms(team: str) -> list[str]:
    """Generate multiple ILIKE-friendly search terms from a team name.

    For abbreviated names like "WSH Capitals", extracts the last word (mascot)
    as an additional search term. For city-only names like "Pittsburgh",
    the original already works as an ILIKE pattern since it's a substring of
    "Pittsburgh Pirates". Multi-word cities like "New York" also match
    "New York Yankees" via ILIKE '%New York%'.

    Returns [original] plus the mascot word if it's >= 5 chars.
    """
    terms = [team]
    words = team.split()
    if len(words) >= 2:
        mascot = words[-1]
        if len(mascot) >= 5 and mascot != team:
            terms.append(mascot)
    return terms


# ── Ticker fragment extraction for college team disambiguation ────────────
# Unlike extract_teams_from_ticker() which maps abbreviations to known pro
# team names, this function returns RAW abbreviation fragments for fuzzy
# matching against event team names. Useful for NCAAB/NCAAF where there are
# hundreds of teams and maintaining a complete abbreviation map is impractical.

_TICKER_FRAGMENT_RE = re.compile(
    r'^([a-z]+)-(\d{2}[a-z]{3}\d{1,2})\d*([a-z]+)$',
    re.IGNORECASE,
)


def extract_ticker_fragments(external_id: str) -> Optional[tuple[str, str, str]]:
    """
    Extract raw abbreviation fragments and sport prefix from a Kalshi game ticker.

    Unlike extract_teams_from_ticker() which maps to known team names, this
    returns the raw abbreviation strings for fuzzy matching against event team
    names. Useful for college sports where maintaining a full abbreviation map
    is impractical.

    Example: "KXNCAABGAME-26FEB21STACAL" → ("STA", "CAL", "basketball_ncaab")

    Returns (abbrev_a, abbrev_b, sport_prefix) or None if parsing fails.
    """
    if not external_id:
        return None

    # Must be a game ticker
    if not is_kalshi_game_ticker(external_id):
        return None

    m = _TICKER_FRAGMENT_RE.match(external_id)
    if not m:
        return None

    sport_ticker_prefix = m.group(1).lower()
    teams_str = m.group(3).upper()

    if len(teams_str) < 4:  # Need at least 2+2 chars
        return None

    # Get sport prefix from ticker
    sport_prefix = get_sport_prefix_from_ticker(external_id)
    if not sport_prefix:
        return None

    # Try splitting into two abbreviations (2+rest, 3+rest)
    # Prefer 3+3 for NCAAB/NCAAF, then 3+2, 2+3, 2+2
    for split_at in (3, 2):
        if split_at >= len(teams_str):
            continue
        abbrev_a = teams_str[:split_at]
        abbrev_b = teams_str[split_at:]
        if 2 <= len(abbrev_b) <= 4:
            return (abbrev_a, abbrev_b, sport_prefix)

    return None


def _score_fragment_match(
    abbrev_a: str, abbrev_b: str,
    home_team: str, away_team: str,
) -> int:
    """
    Score how well two ticker abbreviation fragments match event team names.

    Checks if each abbreviation matches the start of any word in either team
    name (case-insensitive). Returns 0, 1, or 2 (number of fragments matched).
    Both fragments must match DIFFERENT teams to score 2.
    """
    def _fragment_matches_team(abbrev: str, team_name: str) -> bool:
        abbrev_lower = abbrev.lower()
        words = team_name.lower().split()
        return any(w.startswith(abbrev_lower) for w in words)

    a_home = _fragment_matches_team(abbrev_a, home_team)
    a_away = _fragment_matches_team(abbrev_a, away_team)
    b_home = _fragment_matches_team(abbrev_b, home_team)
    b_away = _fragment_matches_team(abbrev_b, away_team)

    score = 0
    # Fragment A matches one team and fragment B matches the OTHER team
    if (a_home and b_away) or (a_away and b_home):
        score = 2
    elif a_home or a_away:
        score += 1
        if b_home or b_away:
            score += 1  # Both match but same team — still count
    elif b_home or b_away:
        score += 1

    return score


# ── Time window for event matching ───────────────────────────────────────────

# Maximum time difference between market commence_time and event commence_time
MAX_TIME_DELTA = timedelta(hours=48)

# Maximum time before game start to match (don't match markets for games
# that started long ago unless they're still live)
MAX_PAST_GAME_DELTA = timedelta(hours=6)
