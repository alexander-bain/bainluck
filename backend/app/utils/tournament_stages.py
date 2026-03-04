"""Sport-specific tournament stage definitions for progression tables.

Each sport defines an ordered list of stages from easiest to hardest.
Used by the /api/futures/{market_id}/progression endpoint to discover
sibling markets at different stages and assemble a cross-stage pivot.
"""

import re
from typing import Optional


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
            "patterns": [r"make.playoffs", r"playoff.appearance", r"playoff.berth"],
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
            "patterns": [r"make.playoffs", r"playoff.berth"],
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
            "patterns": [r"make.playoffs", r"playoff.berth"],
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
            "patterns": [r"make.playoffs", r"playoff.berth"],
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
}


def get_stages_for_sport(llm_sport_category: str) -> list[dict] | None:
    """Return ordered stage definitions for a sport, or None if not configured."""
    return SPORT_STAGES.get(llm_sport_category)


def classify_market_stage(
    market_name: str,
    external_id: str | None,
    market_tier: int | None,
    stages: list[dict],
) -> str | None:
    """Determine which stage a market represents.

    Tries DataGolf suffix matching first (fastest), then pattern matching
    on market name, then falls back to market_tier heuristic.
    """
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
