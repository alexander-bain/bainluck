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


# ── Game-level market detection ──────────────────────────────────────────────

# "Team A at/vs Team B" (bare matchup without stat — no colon separator)
_BARE_MATCHUP_RE = re.compile(
    r'^([A-Z][\w\s.\'\-()]+?)\s+(?:at|vs\.?|@)\s+([A-Z][\w\s.\'\-()]+?)$',
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

# Game prop pattern (Team at Team: Stat) — NOT a moneyline market
_GAME_PROP_RE = re.compile(
    r'^(.+?)\s+(?:at|vs\.?|@)\s+(.+?):\s+(.+)$', re.IGNORECASE,
)


def is_game_level_market(
    market_name: str,
    category: Optional[str],
    num_outcomes: int,
) -> bool:
    """
    Check if a futures market represents a game-level binary outcome
    (e.g., "Which team wins this game?") rather than a championship/award future.

    Criteria:
    - Must be a single-outcome binary market (1 outcome with "Yes"/"No")
    - Must match a matchup pattern (bare matchup or "Will X beat Y?")
    - Must NOT be a game prop (those have stats like "Rebounds")
    """
    if num_outcomes > 2:
        return False

    # Skip game props (have ": stat" suffix)
    if _GAME_PROP_RE.match(market_name):
        return False

    # Check for matchup patterns
    if _BARE_MATCHUP_RE.match(market_name):
        return True
    if _WILL_BEAT_RE.match(market_name):
        return True
    if _TO_BEAT_RE.match(market_name):
        return True
    if _WILL_WIN_RE.match(market_name):
        # "Will X win?" is only game-level if it's a binary market in a sports context
        # (not "Will X win the championship?")
        name_lower = market_name.lower()
        if any(word in name_lower for word in (
            "championship", "title", "trophy", "award", "mvp",
            "cup", "series", "super bowl", "pennant", "division",
        )):
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


def extract_matchup(market_name: str) -> Optional[MatchupInfo]:
    """
    Extract team names and determine "Yes" team from a game-level market name.

    Returns MatchupInfo or None if not a recognized format.

    Conventions:
    - "Team A at Team B" → Yes = Team A (first listed team in "at" format)
    - "Team A vs Team B" → Yes = Team A (first listed team)
    - "Will Team A beat Team B?" → Yes = Team A
    - "Will Team A win?" → Yes = Team A (team_b will be empty)
    """
    # Skip game props
    if _GAME_PROP_RE.match(market_name):
        return None

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

    # "Team A at/vs Team B" (bare matchup)
    m = _BARE_MATCHUP_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        team_b = m.group(2).strip()
        # "at" format: first team is away, second is home
        # "Yes" = first listed team wins
        return MatchupInfo(team_a, team_b, yes_team=team_a, format_type="bare_matchup")

    # "Will Team A win?"
    m = _WILL_WIN_RE.match(market_name)
    if m:
        team_a = m.group(1).strip()
        # Check it's not a championship context
        name_lower = market_name.lower()
        if any(word in name_lower for word in (
            "championship", "title", "trophy", "award", "mvp",
            "cup", "series", "super bowl", "pennant", "division",
        )):
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


# ── Time window for event matching ───────────────────────────────────────────

# Maximum time difference between market commence_time and event commence_time
MAX_TIME_DELTA = timedelta(hours=48)

# Maximum time before game start to match (don't match markets for games
# that started long ago unless they're still live)
MAX_PAST_GAME_DELTA = timedelta(hours=6)
