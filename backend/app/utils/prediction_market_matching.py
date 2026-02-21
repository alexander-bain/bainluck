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
from datetime import timedelta

from app.utils.team_linking import _normalize_name

logger = logging.getLogger(__name__)


# ── Kalshi game ticker detection ─────────────────────────────────────────────

# Kalshi game-level event ticker prefixes.
# These reliably identify game-level markets regardless of the event title.
# e.g., "KXNBAGAME-26FEB19BOSGSW" → NBA game between BOS and GSW on Feb 19
_KALSHI_GAME_TICKER_PREFIXES = (
    "kxnbagame",     # NBA game
    "kxnflgame",     # NFL game
    "kxnhlgame",     # NHL game
    "kxmlbgame",     # MLB game
    "kxncaabgame",   # NCAAB (college basketball) game
    "kxncaafgame",   # NCAAF (college football) game
    "kxwnbagame",    # WNBA game
    "kxmlsgame",     # MLS game
    "kxsoccergame",  # Soccer game
    "kxufcfight",    # UFC fight
    "kxboxingfight", # Boxing fight
    "kxlolgame",     # League of Legends esports game
)


def is_kalshi_game_ticker(external_id: str) -> bool:
    """
    Check if a Kalshi external_id (event_ticker) indicates a game-level market.

    Kalshi uses structured tickers like "KXNBAGAME-26FEB19BOSGSW" for NBA games.
    This is the most reliable signal for game-level detection — more reliable
    than name pattern matching.
    """
    if not external_id:
        return False
    ext_lower = external_id.lower()
    return any(ext_lower.startswith(prefix) for prefix in _KALSHI_GAME_TICKER_PREFIXES)


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
    # League abbreviations
    r'NBA|NFL|NHL|MLB|MLS|WNBA|NCAAB?|NCAAF?|EPL|La Liga|Serie A|Ligue 1|Bundesliga'
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
    r'(?:Basketball|Football|Hockey|Baseball|Soccer|Tennis|Golf|Boxing|MMA)'
    r'(?:\s+(?:Game|Match))?'
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

    # Signal 2+3: Name pattern matching (with and without prefix stripping)
    return _check_game_level(market_name) or _check_game_level(_strip_category_prefix(market_name))


def _check_game_level(name: str) -> bool:
    """Check if a (possibly prefix-stripped) market name is game-level."""
    if not name:
        return False

    # Skip game props (have ": stat" suffix after matchup)
    if _GAME_PROP_RE.match(name):
        return False
    if _DASH_PROP_RE.match(name):
        return False

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
    # Try original name first, then with category prefix stripped
    result = _extract_matchup_impl(market_name)
    if result:
        return result

    stripped = _strip_category_prefix(market_name)
    if stripped != market_name:
        return _extract_matchup_impl(stripped)

    return None


def _extract_matchup_impl(market_name: str) -> Optional[MatchupInfo]:
    """Core matchup extraction logic."""
    if not market_name:
        return None

    # Skip game props
    if _GAME_PROP_RE.match(market_name):
        return None
    if _DASH_PROP_RE.match(market_name):
        return None

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


# ── Kalshi ticker → sport_key mapping for fallback matching ──────────────────
# When a Kalshi game market has a generic name (e.g., "Professional Basketball Game")
# and extract_matchup() fails, we can still match by sport + commence_time.
# This maps ticker prefixes to The Odds API sport_key prefixes.

_TICKER_TO_SPORT_PREFIX: dict[str, str] = {
    "kxnbagame": "basketball_nba",
    "kxnflgame": "americanfootball_nfl",
    "kxnhlgame": "icehockey_nhl",
    "kxmlbgame": "baseball_mlb",
    "kxncaabgame": "basketball_ncaab",
    "kxncaafgame": "americanfootball_ncaaf",
    "kxwnbagame": "basketball_wnba",
    "kxmlsgame": "soccer_usa_mls",
    "kxsoccergame": "soccer",
    "kxufcfight": "mma_mixed_martial_arts",
    "kxboxingfight": "boxing_boxing",
    "kxlolgame": "esports",
}


def get_sport_prefix_from_ticker(external_id: str) -> Optional[str]:
    """
    Get the sport_key prefix for a Kalshi game ticker.

    Returns a sport_key prefix (e.g., "basketball_nba") or None.
    Used for fallback matching when name-based extraction fails.
    """
    if not external_id:
        return None
    ext_lower = external_id.lower()
    for prefix, sport in _TICKER_TO_SPORT_PREFIX.items():
        if ext_lower.startswith(prefix):
            return sport
    return None


# ── Time window for event matching ───────────────────────────────────────────

# Maximum time difference between market commence_time and event commence_time
MAX_TIME_DELTA = timedelta(hours=48)

# Maximum time before game start to match (don't match markets for games
# that started long ago unless they're still live)
MAX_PAST_GAME_DELTA = timedelta(hours=6)
