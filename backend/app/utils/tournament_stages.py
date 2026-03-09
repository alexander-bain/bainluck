"""Sport-specific tournament stage definitions for progression tables.

Each sport defines an ordered list of stages from easiest to hardest.
Used by the /api/futures/{market_id}/progression endpoint to discover
sibling markets at different stages and assemble a cross-stage pivot.
"""

import re
from typing import Optional


# Matches game-level markets that should never be included in progression tables
_GAME_MARKET_RE = re.compile(
    r"""
    \bvs\.?\b       |   # "Team A vs Team B"
    \bat\b.*:       |   # "Team A at Team B: ..."
    first.half      |   # "First Half Winner"
    second.half     |   # "Second Half Winner"
    \bmoneyline\b   |   # "Game Moneyline"
    \bspread\b      |   # "Game Spread"
    \btotal\b       |   # "Game Total"
    \bover.under\b  |   # "Over/Under"
    \bquarter\b     |   # "1st Quarter Winner"
    \binning\b      |   # "1st Inning"
    \bperiod\b          # "1st Period"
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Stage suffix patterns to strip when extracting tournament names
_STAGE_SUFFIX_RE = re.compile(
    r"""
    \s*[-:]\s*(
        winner\??                   |
        to\s+win\??                 |
        top\s+\d+\s+finisher\??    |
        make\s+the\s+cut\??        |
        to\s+make\s+the\s+cut\??   |
        end\s+of\s+round\s+\d+\s+leader\?? |
        round\s+\d+\s+leader\??
    )\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Also strip trailing stage suffixes without a separator (colon/dash)
_TRAILING_STAGE_RE = re.compile(
    r"\s+(winner|to win|to make the cut|end of round \d+ leader|round \d+ leader)\??\s*$",
    re.IGNORECASE,
)


SPORT_STAGES: dict[str, list[dict]] = {
    "golf": [
        {
            "key": "make_cut",
            "label": "Make Cut",
            "order": 1,
            "datagolf_suffix": ":make_cut",
            "patterns": [r"make.cut"],
        },
        {
            "key": "top_20",
            "label": "Top 20",
            "order": 2,
            "datagolf_suffix": ":top_20",
            "patterns": [r"top.20"],
        },
        {
            "key": "top_10",
            "label": "Top 10",
            "order": 3,
            "datagolf_suffix": ":top_10",
            "patterns": [r"top.10"],
        },
        {
            "key": "top_5",
            "label": "Top 5",
            "order": 4,
            "datagolf_suffix": ":top_5",
            "patterns": [r"top.5"],
        },
        {
            "key": "win",
            "label": "Win",
            "order": 5,
            "datagolf_suffix": ":win",
            "patterns": [r"\bwinner\b", r"\bchampionship\b", r"\bwin\b"],
        },
    ],
    "football": [
        {
            "key": "make_playoffs",
            "label": "Make Playoffs",
            "order": 1,
            "patterns": [r"make.playoffs", r"make\b.*\bplayoffs", r"playoff.berth", r"playoff.appearance"],
        },
        {
            "key": "division",
            "label": "Win Division",
            "order": 2,
            "patterns": [r"\bdivision\b"],
        },
        {
            "key": "conference",
            "label": "Win Conference",
            "order": 3,
            "patterns": [r"\bconference\b", r"afc.champion", r"nfc.champion"],
        },
        {
            "key": "championship",
            "label": "Win Super Bowl",
            "order": 4,
            "patterns": [r"super.bowl", r"\bchampionship\b", r"\bchampion\b"],
        },
    ],
    "basketball": [
        {
            "key": "make_playoffs",
            "label": "Make Playoffs",
            "order": 1,
            "patterns": [r"make.playoffs", r"make\b.*\bplayoffs", r"playoff.berth"],
        },
        {
            "key": "conference",
            "label": "Win Conference",
            "order": 2,
            "patterns": [
                r"\bconference\b",
                r"\bastern\b",
                r"\bestern\b",
                r"\bwestern\b",
            ],
        },
        {
            "key": "championship",
            "label": "Win Championship",
            "order": 3,
            "patterns": [
                r"\bchampionship\b",
                r"\bchampion\b",
                r"nba.finals",
                r"ncaa.champion",
                r"march.madness",
            ],
        },
    ],
    "baseball": [
        {
            "key": "make_playoffs",
            "label": "Make Playoffs",
            "order": 1,
            "patterns": [r"make.playoffs", r"make\b.*\bplayoffs", r"playoff.berth"],
        },
        {
            "key": "division",
            "label": "Win Division",
            "order": 2,
            "patterns": [
                r"\bdivision\b",
                r"\bal.east\b",
                r"\bnl.west\b",
                r"\bal.central\b",
                r"\bnl.central\b",
                r"\bal.west\b",
                r"\bnl.east\b",
            ],
        },
        {
            "key": "pennant",
            "label": "Win Pennant",
            "order": 3,
            "patterns": [
                r"\bpennant\b",
                r"american.league.champion",
                r"national.league.champion",
                r"\balcs\b",
                r"\bnlcs\b",
            ],
        },
        {
            "key": "championship",
            "label": "Win World Series",
            "order": 4,
            "patterns": [r"world.series", r"\bchampionship\b", r"\bchampion\b"],
        },
    ],
    "hockey": [
        {
            "key": "make_playoffs",
            "label": "Make Playoffs",
            "order": 1,
            "patterns": [r"make.playoffs", r"make\b.*\bplayoffs", r"playoff.berth"],
        },
        {
            "key": "division",
            "label": "Win Division",
            "order": 2,
            "patterns": [r"\bdivision\b"],
        },
        {
            "key": "conference",
            "label": "Win Conference",
            "order": 3,
            "patterns": [r"\bconference\b", r"\bastern\b", r"\bestern\b", r"\bwestern\b"],
        },
        {
            "key": "championship",
            "label": "Win Stanley Cup",
            "order": 4,
            "patterns": [r"stanley.cup", r"\bchampionship\b", r"\bchampion\b"],
        },
    ],
    "soccer": [
        {
            "key": "group_stage",
            "label": "Advance from Group",
            "order": 1,
            "patterns": [r"\bgroup\b", r"\badvance\b"],
        },
        {
            "key": "championship",
            "label": "Win Tournament",
            "order": 2,
            "patterns": [r"\bchampionship\b", r"\bwinner\b", r"\bchampion\b"],
        },
    ],
    "tennis": [
        {
            "key": "make_final",
            "label": "Make Final",
            "order": 1,
            "patterns": [r"make.final", r"reach.final"],
        },
        {
            "key": "championship",
            "label": "Win Tournament",
            "order": 2,
            "patterns": [r"\bwinner\b", r"\bchampion\b"],
        },
    ],
    # NCAA Tournament (March Madness) — 6 rounds
    "ncaa_basketball": [
        {
            "key": "round_of_32",
            "label": "Round of 32",
            "order": 1,
            "patterns": [
                r"round.of.32",
                r"second.round",
                r"2nd.round",
                r"make.round.of.32",
                r"win.first.round",
            ],
        },
        {
            "key": "sweet_16",
            "label": "Sweet 16",
            "order": 2,
            "patterns": [r"sweet.16", r"sweet.sixteen", r"make.sweet"],
        },
        {
            "key": "elite_eight",
            "label": "Elite Eight",
            "order": 3,
            "patterns": [r"elite.eight", r"elite.8", r"make.elite"],
        },
        {
            "key": "final_four",
            "label": "Final Four",
            "order": 4,
            "patterns": [r"final.four", r"make.final.four"],
        },
        {
            "key": "title_game",
            "label": "Title Game",
            "order": 5,
            "patterns": [
                r"title.game",
                r"championship.game",
                r"make.championship",
                r"make.the.final",
                r"reach.the.final",
            ],
        },
        {
            "key": "championship",
            "label": "Champion",
            "order": 6,
            "patterns": [
                r"\bchampion\b",
                r"\bchampionship\b",
                r"win.ncaa",
                r"ncaa.*winner",
                r"march.madness.*winner",
                r"\bwinner\b",
            ],
        },
    ],
    # College Football Playoff — 4 rounds (12-team format)
    "ncaa_football": [
        {
            "key": "make_playoffs",
            "label": "Make Playoff",
            "order": 1,
            "patterns": [r"make.playoff", r"playoff.berth", r"cfp.berth"],
        },
        {
            "key": "quarterfinal",
            "label": "Quarterfinal",
            "order": 2,
            "patterns": [r"quarter.?final", r"make.quarter"],
        },
        {
            "key": "semifinal",
            "label": "Semifinal",
            "order": 3,
            "patterns": [r"semi.?final", r"make.semi"],
        },
        {
            "key": "championship",
            "label": "Champion",
            "order": 4,
            "patterns": [
                r"\bchampion\b",
                r"\bchampionship\b",
                r"national.champion",
                r"cfp.champion",
                r"\bwinner\b",
            ],
        },
    ],
}


# League → sport stage override map
# When a league is specified, prefer league-specific stages over sport-generic ones
_LEAGUE_STAGE_OVERRIDES: dict[str, str] = {
    "NCAAB": "ncaa_basketball",
    "NCAAF": "ncaa_football",
    "NCAA": "ncaa_basketball",
}


def get_stages_for_sport(
    llm_sport_category: str, league: str | None = None
) -> list[dict] | None:
    """Return ordered stage definitions for a sport, or None if not configured.

    If league is specified and has custom stages (e.g., NCAAB → March Madness rounds),
    those take precedence over the generic sport stages.
    """
    if league:
        override_key = _LEAGUE_STAGE_OVERRIDES.get(league.upper())
        if override_key and override_key in SPORT_STAGES:
            return SPORT_STAGES[override_key]
    return SPORT_STAGES.get(llm_sport_category)


def is_game_level_market(market_name: str) -> bool:
    """Return True if the market name looks like a game-level market.

    Game-level markets (moneylines, spreads, totals, first-half props) should
    never appear in progression tables.
    """
    return bool(_GAME_MARKET_RE.search(market_name))


def extract_tournament_name(market_name: str) -> str:
    """Extract the base tournament name from a market name by stripping stage suffixes.

    Examples:
        "Joburg Open Winner?" → "Joburg Open"
        "Joburg Open: To Make the Cut" → "Joburg Open"
        "Puerto Rico Open Top 5 Finisher" → "Puerto Rico Open"
        "Arnold Palmer Invitational presented by Mastercard Top 10 Finisher"
            → "Arnold Palmer Invitational presented by Mastercard"
        "NBA Championship Winner 2025-26" → "NBA Championship"
    """
    name = market_name.strip()

    # Strip "... : Winner?" / "... - Top 5 Finisher" style suffixes
    name = _STAGE_SUFFIX_RE.sub("", name)

    # Strip trailing year/season (e.g., "2025-26", "2026") — before stage words
    # so "NBA Championship Winner 2025-26" → "NBA Championship Winner" → "NBA Championship"
    name = re.sub(r"\s+\d{4}(-\d{2,4})?\s*$", "", name)

    # Strip trailing "Winner?" / "to win" / "end of round N leader" without separator
    name = _TRAILING_STAGE_RE.sub("", name)

    # Strip trailing "Top N Finisher" without separator
    name = re.sub(r"\s+top\s+\d+\s+finisher\??\s*$", "", name, flags=re.IGNORECASE)

    # Strip trailing year/season again (catches "PGA Championship 2026 Winner?" → after
    # "Winner?" stripped, "PGA Championship 2026" still has trailing year)
    name = re.sub(r"\s+\d{4}(-\d{2,4})?\s*$", "", name)

    # Strip trailing "?"
    name = name.rstrip("? ").strip()

    return name


def tournament_names_match(name_a: str, name_b: str) -> bool:
    """Check if two tournament names refer to the same tournament.

    Uses word-set overlap scoring similar to ESPN team matching.
    Requires >60% overlap in both directions.
    """
    words_a = set(name_a.lower().split())
    words_b = set(name_b.lower().split())

    # Remove common stopwords
    stopwords = {"the", "of", "a", "an", "by", "presented", "at", "in", "and"}
    words_a -= stopwords
    words_b -= stopwords

    if not words_a or not words_b:
        return False

    overlap = len(words_a & words_b)
    score_a = overlap / len(words_a)
    score_b = overlap / len(words_b)

    # Require meaningful overlap in both directions
    return min(score_a, score_b) > 0.6


def classify_market_stage(
    market_name: str,
    external_id: str | None,
    market_tier: int | None,
    stages: list[dict],
) -> str | None:
    """Determine which stage a market represents.

    Tries DataGolf suffix matching first (fastest), then pattern matching
    on market name, then falls back to market_tier heuristic.

    Returns None for game-level markets (moneylines, spreads, etc.).
    """
    # Reject game-level markets
    if is_game_level_market(market_name):
        return None

    name_lower = market_name.lower()
    ext_lower = (external_id or "").lower()

    # 1. DataGolf suffix match (exact, fastest)
    for stage in stages:
        suffix = stage.get("datagolf_suffix")
        if suffix and ext_lower.endswith(suffix):
            return stage["key"]

    # 2. Pattern match on market name (most specific first → highest order)
    # Check from most specific (highest order) to least specific
    for stage in sorted(stages, key=lambda s: s["order"], reverse=True):
        for pattern in stage["patterns"]:
            if re.search(pattern, name_lower, re.IGNORECASE):
                return stage["key"]

    # 3. market_tier heuristic fallback
    if market_tier is not None:
        tier_map = {1: "championship", 2: "conference", 4: "division"}
        tier_key = tier_map.get(market_tier)
        if tier_key:
            for stage in stages:
                if stage["key"] == tier_key:
                    return tier_key

    return None


def get_datagolf_prefix(external_id: str) -> Optional[str]:
    """Extract DataGolf tournament prefix from external_id.

    Example: "datagolf:pga:masters_2026:win" → "datagolf:pga:masters_2026"
    """
    if not external_id or not external_id.startswith("datagolf:"):
        return None
    parts = external_id.rsplit(":", 1)
    if len(parts) == 2:
        return parts[0]
    return None
