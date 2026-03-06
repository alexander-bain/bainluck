"""
Market Grouping Utilities

Provides two grouping strategies for related futures markets:

1. **Canonical key grouping** — Markets sharing the same `canonical_market_key`
   (e.g., basketball:NBA:championship:2025-26) from different sources
   (Polymarket, Kalshi, Odds API) are logically the same market.

2. **Threshold variant detection** — Markets that differ only by a numeric
   threshold (e.g., "Will Bitcoin exceed $80,000?", "Will Bitcoin exceed
   $90,000?", "Will Bitcoin exceed $100,000?") are grouped into a
   threshold progression.

These utilities are used by:
- The admin backfill endpoint to discover and set group_id on existing markets
- The grouping API endpoints to assemble grouped market views
"""

import re
from typing import Optional

# ── THRESHOLD DETECTION ──

# Regex to extract numeric threshold from market names.
# Matches patterns like:
#   "exceed $80,000"     → ("80000", "$")
#   "above 33°F"         → ("33", "°F")
#   "over 100.5 points"  → ("100.5", "points")
#   "at least 250"       → ("250", "")
#   "reach 1,000,000"    → ("1000000", "")
_THRESHOLD_RE = re.compile(
    r"""
    (?:exceed|above|over|under|below|at\s+least|at\s+most|reach|hit|top|more\s+than|less\s+than|higher\s+than|lower\s+than)
    \s+
    (\$?)                          # optional dollar sign
    ([\d,]+(?:\.\d+)?)             # number (with optional commas and decimals)
    \s*
    (°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?)?  # optional unit
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Simpler pattern for "X or more", "X or below", "X+" etc.
_THRESHOLD_SIMPLE_RE = re.compile(
    r"""
    (\$?)                          # optional dollar sign
    ([\d,]+(?:\.\d+)?)             # number
    \s*
    (°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?)?  # optional unit
    \s*
    (?:or\s+(?:more|above|higher|greater|less|below|lower|fewer)|\+|-|\s+and\s+above|\s+and\s+below)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Player stat props: "PlayerName: 25+ Points" or "PlayerName: Points Over 25.5"
# Matches Kalshi-style stat prop markets
_STAT_PROP_RE = re.compile(
    r"""
    ^(.+?)                                           # player/team name (captured)
    :\s*
    (?:
        ([\d.]+)\+?\s*                               # threshold first: "25+ Points"
        (points?|rebounds?|assists?|steals?|blocks?|
         three\s*pointers?|3[-\s]?pointers?|threes?|
         strikeouts?|hits?|hrs?|home\s*runs?|rbis?|runs?|
         goals?|saves?|shots?|sacks?|
         passing\s*yards?|rushing\s*yards?|receiving\s*yards?|
         touchdowns?|tds?|completions?|interceptions?|
         aces?|double\s*faults?|kills?)
        |
        (points?|rebounds?|assists?|steals?|blocks?|
         three\s*pointers?|3[-\s]?pointers?|threes?|
         strikeouts?|hits?|hrs?|home\s*runs?|rbis?|runs?|
         goals?|saves?|shots?|sacks?|
         passing\s*yards?|rushing\s*yards?|receiving\s*yards?|
         touchdowns?|tds?|completions?|interceptions?|
         aces?|double\s*faults?|kills?)                # stat category first
        \s*
        (?:over|under|o|u)?\s*
        ([\d.]+)\+?                                   # then threshold: "Points Over 25.5"
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Playoff/tournament progression: "Team: Make Round 2" / "Team: Win Championship"
_PLAYOFF_STAGE_RE = re.compile(
    r"""
    ^(.+?)                                           # team/player name (captured)
    :\s*
    (make|win|reach|advance\s+to|qualify\s+for)      # action verb
    \s+
    (round\s*\d+|r\d+|                               # Round 1, Round 2, R1, R2
     playoffs?|postseason|                           # Make Playoffs
     championship|finals?|title|                     # Win Championship
     wcf|ecf|acf|nfc|afc|                           # Conference finals
     conference\s*(?:finals?|semis?|quarters?)|      # Conference rounds
     semis?|semifinals?|                             # Semifinals
     quarters?|quarterfinals?|                       # Quarterfinals
     sweet\s*16|elite\s*8|final\s*four|             # NCAA tournament
     divisional|wild\s*card|                         # NFL playoffs
     world\s*series|pennant|                         # MLB playoffs
     stanley\s*cup|                                  # NHL playoffs
     super\s*bowl)                                   # Super Bowl
    """,
    re.IGNORECASE | re.VERBOSE,
)


def extract_stat_prop(name: str) -> Optional[tuple[str, str, float, str]]:
    """
    Extract player stat prop information from a market name.
    
    Returns:
        Tuple of (player_name, stat_category, threshold, direction) or None.
        - player_name: e.g., "Jayson Tatum"
        - stat_category: e.g., "points", "rebounds"
        - threshold: numeric value (e.g., 25.5)
        - direction: "above" or "below"
    
    Examples:
        "Jayson Tatum: 25+ Points" → ("Jayson Tatum", "points", 25.0, "above")
        "LeBron James: Rebounds Over 8.5" → ("LeBron James", "rebounds", 8.5, "above")
    """
    if not name:
        return None
    
    m = _STAT_PROP_RE.match(name)
    if not m:
        return None
    
    player_name = m.group(1).strip()
    
    # Pattern 1: "25+ Points" (threshold then stat)
    if m.group(2) and m.group(3):
        threshold = float(m.group(2).replace(",", ""))
        stat_category = m.group(3).lower().strip()
        direction = "above"  # "+" implies above
    # Pattern 2: "Points Over 25.5" (stat then threshold)
    elif m.group(4) and m.group(5):
        stat_category = m.group(4).lower().strip()
        threshold = float(m.group(5).replace(",", ""))
        # Check for under/below
        full_match = name[m.start():m.end()].lower()
        direction = "below" if any(w in full_match for w in ("under", "u ")) else "above"
    else:
        return None
    
    # Normalize stat category
    stat_category = _normalize_stat_category(stat_category)
    
    return (player_name, stat_category, threshold, direction)


def _normalize_stat_category(stat: str) -> str:
    """Normalize stat category names to a canonical form."""
    stat = stat.lower().strip()
    
    # Pluralize if needed for consistency
    normalizations = {
        "point": "points",
        "rebound": "rebounds", 
        "assist": "assists",
        "steal": "steals",
        "block": "blocks",
        "three pointer": "threes",
        "3-pointer": "threes",
        "3 pointer": "threes",
        "three": "threes",
        "strikeout": "strikeouts",
        "hit": "hits",
        "hr": "home_runs",
        "home run": "home_runs",
        "rbi": "rbis",
        "run": "runs",
        "goal": "goals",
        "save": "saves",
        "shot": "shots",
        "sack": "sacks",
        "passing yard": "passing_yards",
        "rushing yard": "rushing_yards",
        "receiving yard": "receiving_yards",
        "touchdown": "touchdowns",
        "td": "touchdowns",
        "completion": "completions",
        "interception": "interceptions",
        "ace": "aces",
        "double fault": "double_faults",
        "kill": "kills",
    }
    
    for key, value in normalizations.items():
        if stat.startswith(key):
            return value
    
    # Default: return as-is with 's' suffix if singular
    if not stat.endswith("s"):
        stat = stat + "s"
    return stat


def extract_playoff_stage(name: str) -> Optional[tuple[str, str, int]]:
    """
    Extract playoff/tournament progression information from a market name.
    
    Returns:
        Tuple of (team_name, stage_name, stage_order) or None.
        - team_name: e.g., "Lakers"
        - stage_name: e.g., "Make Playoffs", "Win Championship"
        - stage_order: numeric order (higher = further in tournament)
    
    Examples:
        "Lakers: Make Playoffs" → ("Lakers", "Make Playoffs", 1)
        "Lakers: Make Round 2" → ("Lakers", "Make Round 2", 3)
        "Lakers: Win Championship" → ("Lakers", "Win Championship", 10)
    """
    if not name:
        return None
    
    m = _PLAYOFF_STAGE_RE.match(name)
    if not m:
        return None
    
    team_name = m.group(1).strip()
    action = m.group(2).lower()
    stage = m.group(3).lower().strip()
    
    # Normalize action verb
    action_normalized = "Win" if action == "win" else "Make"
    
    # Normalize stage name and assign order
    stage_name, stage_order = _normalize_playoff_stage(stage, action_normalized)
    
    return (team_name, stage_name, stage_order)


def _normalize_playoff_stage(stage: str, action: str) -> tuple[str, int]:
    """Normalize playoff stage name and assign order."""
    stage = stage.lower().strip()
    
    # Stage order mapping (higher = deeper in tournament)
    stage_mapping = {
        # Generic
        "playoffs": ("Playoffs", 1),
        "postseason": ("Playoffs", 1),
        "wild card": ("Wild Card", 2),
        "divisional": ("Divisional", 3),
        "round 1": ("Round 1", 2),
        "round1": ("Round 1", 2),
        "r1": ("Round 1", 2),
        "round 2": ("Round 2", 3),
        "round2": ("Round 2", 3),
        "r2": ("Round 2", 3),
        "quarters": ("Quarterfinals", 4),
        "quarterfinals": ("Quarterfinals", 4),
        "semis": ("Semifinals", 5),
        "semifinals": ("Semifinals", 5),
        "conference finals": ("Conference Finals", 6),
        "conference semis": ("Conference Semis", 5),
        "conference quarters": ("Conference Quarters", 4),
        # NBA specific
        "wcf": ("Western Conference Finals", 6),
        "ecf": ("Eastern Conference Finals", 6),
        # NFL specific
        "nfc": ("NFC Championship", 6),
        "afc": ("AFC Championship", 6),
        "super bowl": ("Super Bowl", 10),
        # MLB specific
        "pennant": ("Pennant", 6),
        "world series": ("World Series", 10),
        # NHL specific
        "stanley cup": ("Stanley Cup", 10),
        # NCAA specific
        "sweet 16": ("Sweet 16", 4),
        "elite 8": ("Elite 8", 5),
        "final four": ("Final Four", 6),
        # Championship (generic)
        "championship": ("Championship", 10),
        "finals": ("Finals", 10),
        "title": ("Championship", 10),
    }
    
    for key, (name, order) in stage_mapping.items():
        if key in stage:
            return (f"{action} {name}", order)
    
    # Default: try to extract round number
    import re as re_inner
    round_match = re_inner.search(r"round\s*(\d+)", stage)
    if round_match:
        round_num = int(round_match.group(1))
        return (f"{action} Round {round_num}", round_num + 1)
    
    # Fallback
    return (f"{action} {stage.title()}", 1)


def extract_threshold(name: str) -> Optional[tuple[float, str, str]]:
    """
    Extract a numeric threshold from a market outcome or title name.

    Returns:
        Tuple of (threshold_value, unit, direction) or None.
        - threshold_value: numeric value (e.g., 80000.0)
        - unit: unit string (e.g., "$", "°F", "points", "")
        - direction: "above" or "below" or "exact"
    """
    if not name:
        return None

    # Try primary pattern first
    m = _THRESHOLD_RE.search(name)
    if m:
        dollar, num_str, unit = m.group(1), m.group(2), m.group(3)
        value = float(num_str.replace(",", ""))
        # Reject year-like numbers (2020-2099) without a unit or dollar sign
        if not dollar and not unit and 2020 <= value <= 2099:
            return None
        unit_str = (dollar + (unit or "")).strip()
        # Determine direction from keyword
        keyword = name[m.start():m.start() + 20].lower()
        if any(w in keyword for w in ("under", "below", "less", "lower", "at most")):
            direction = "below"
        else:
            direction = "above"
        return (value, unit_str, direction)

    # Try simpler pattern
    m = _THRESHOLD_SIMPLE_RE.search(name)
    if m:
        dollar, num_str, unit = m.group(1), m.group(2), m.group(3)
        value = float(num_str.replace(",", ""))
        # Reject year-like numbers without a unit or dollar sign
        if not dollar and not unit and 2020 <= value <= 2099:
            return None
        unit_str = (dollar + (unit or "")).strip()
        # Check the text AFTER the number for direction keywords
        after_text = name[m.end():].strip().lower() if m.end() < len(name) else ""
        # Also check the "or below/above" part which is captured in the match itself
        match_text = name[m.start():m.end()].lower()
        full_context = match_text + " " + after_text
        if any(w in full_context for w in ("below", "less", "lower", "fewer", "under")):
            direction = "below"
        else:
            direction = "above"
        return (value, unit_str, direction)

    return None


def compute_threshold_stem(name: str) -> Optional[str]:
    """
    Compute a "stem" from a market/outcome name by removing the numeric
    threshold. Markets sharing the same stem are threshold variants of
    each other.

    Example:
        "Will Bitcoin exceed $80,000?"  → "will bitcoin exceed $?"
        "Will Bitcoin exceed $90,000?"  → "will bitcoin exceed $?"
        (same stem → threshold group)
    """
    if not name:
        return None

    # Replace numeric values (with optional $ prefix and commas) with a placeholder
    # This normalizes "exceed $80,000" and "exceed $90,000" to the same stem
    stem = re.sub(
        r'\$?[\d,]+(?:\.\d+)?(?:\s*(?:°[FCK]|%|points?|goals?|runs?|yards?|mph|mm|inches|feet|degrees?))?',
        '#',
        name,
    )
    # Normalize whitespace and case
    stem = re.sub(r'\s+', ' ', stem).strip().lower()
    return stem if stem != name.lower().strip() else None


# ── CANONICAL KEY GROUPING ──


def compute_canonical_groups(
    markets: list[dict],
) -> dict[str, list[dict]]:
    """
    Group markets by their canonical_market_key.

    Each market dict should have at minimum:
        - id: int (market ID)
        - canonical_market_key: Optional[str]
        - source: str

    Returns:
        Dict mapping canonical_market_key → list of market dicts
        (only groups with 2+ markets from different sources).
    """
    by_key: dict[str, list[dict]] = {}
    for m in markets:
        key = m.get("canonical_market_key")
        if not key:
            continue
        by_key.setdefault(key, []).append(m)

    # Only return groups with 2+ markets (cross-source or same-source siblings)
    return {
        k: v for k, v in by_key.items()
        if len(v) >= 2
    }


def detect_threshold_groups(
    outcomes: list[dict],
) -> dict[str, list[dict]]:
    """
    Detect threshold variant groups among a list of outcomes.

    Each outcome dict should have at minimum:
        - id: int (outcome ID)
        - name: str (outcome name like "33°F or below")
        - market_id: int (parent market ID)

    Returns:
        Dict mapping threshold_stem → sorted list of outcome dicts
        (only groups with 2+ outcomes sharing the same stem).
        Each outcome dict gets additional keys:
        - threshold_value: float
        - threshold_unit: str
        - threshold_direction: str
    """
    by_stem: dict[str, list[dict]] = {}

    for o in outcomes:
        name = o.get("name", "")
        stem = compute_threshold_stem(name)
        if not stem:
            continue

        threshold = extract_threshold(name)
        if not threshold:
            continue

        value, unit, direction = threshold
        enriched = {
            **o,
            "threshold_value": value,
            "threshold_unit": unit,
            "threshold_direction": direction,
        }
        by_stem.setdefault(stem, []).append(enriched)

    # Only return groups with 2+ outcomes, sorted by threshold value
    result = {}
    for stem, group in by_stem.items():
        if len(group) >= 2:
            group.sort(key=lambda x: x["threshold_value"])
            result[stem] = group

    return result


def detect_stat_prop_groups(
    markets: list[dict],
) -> dict[str, list[dict]]:
    """
    Detect stat prop groups among a list of markets.
    
    Groups markets by player + stat category (e.g., all "Jayson Tatum Points" lines).
    
    Each market dict should have at minimum:
        - id: int (market ID)
        - name: str (market name like "Jayson Tatum: 25+ Points")
    
    Returns:
        Dict mapping group_key → sorted list of market dicts.
        Group key format: "stat_prop:{player_name}:{stat_category}"
        Each market dict gets additional keys:
        - player_name: str
        - stat_category: str
        - threshold_value: float
        - threshold_direction: str
    """
    by_key: dict[str, list[dict]] = {}
    
    for m in markets:
        name = m.get("name", "")
        stat_prop = extract_stat_prop(name)
        if not stat_prop:
            continue
        
        player_name, stat_category, threshold, direction = stat_prop
        group_key = f"stat_prop:{player_name.lower()}:{stat_category}"
        
        enriched = {
            **m,
            "player_name": player_name,
            "stat_category": stat_category,
            "threshold_value": threshold,
            "threshold_direction": direction,
            "group_type": "stat_prop",
        }
        by_key.setdefault(group_key, []).append(enriched)
    
    # Only return groups with 2+ markets, sorted by threshold
    result = {}
    for key, group in by_key.items():
        if len(group) >= 2:
            group.sort(key=lambda x: x["threshold_value"])
            result[key] = group
    
    return result


def detect_playoff_progression_groups(
    markets: list[dict],
) -> dict[str, list[dict]]:
    """
    Detect playoff/tournament progression groups among a list of markets.
    
    Groups markets by team (e.g., all "Lakers" playoff stages).
    
    Each market dict should have at minimum:
        - id: int (market ID)
        - name: str (market name like "Lakers: Make Round 2")
    
    Returns:
        Dict mapping group_key → sorted list of market dicts.
        Group key format: "playoff_progression:{team_name}"
        Each market dict gets additional keys:
        - team_name: str
        - stage_name: str
        - stage_order: int
    """
    by_key: dict[str, list[dict]] = {}
    
    for m in markets:
        name = m.get("name", "")
        playoff_stage = extract_playoff_stage(name)
        if not playoff_stage:
            continue
        
        team_name, stage_name, stage_order = playoff_stage
        group_key = f"playoff_progression:{team_name.lower()}"
        
        enriched = {
            **m,
            "team_name": team_name,
            "stage_name": stage_name,
            "stage_order": stage_order,
            "group_type": "playoff_progression",
        }
        by_key.setdefault(group_key, []).append(enriched)
    
    # Only return groups with 2+ markets, sorted by stage order
    result = {}
    for key, group in by_key.items():
        if len(group) >= 2:
            group.sort(key=lambda x: x["stage_order"])
            result[key] = group
    
    return result


def detect_all_groups(
    markets: list[dict],
) -> dict[str, dict]:
    """
    Detect all types of market groups: threshold, stat prop, and playoff progression.
    
    Returns a dict with group_type → {group_key → list of markets}.
    
    Example return:
    {
        "threshold": {
            "will bitcoin exceed $#?": [...],
        },
        "stat_prop": {
            "stat_prop:jayson tatum:points": [...],
        },
        "playoff_progression": {
            "playoff_progression:lakers": [...],
        },
    }
    """
    # Extract outcomes from markets for threshold detection
    # (threshold detection works on outcomes, not markets)
    all_outcomes = []
    for m in markets:
        outcomes = m.get("outcomes", [])
        for o in outcomes:
            all_outcomes.append({**o, "market_id": m.get("id")})
    
    return {
        "threshold": detect_threshold_groups(all_outcomes),
        "stat_prop": detect_stat_prop_groups(markets),
        "playoff_progression": detect_playoff_progression_groups(markets),
    }


def compute_stat_prop_stem(name: str) -> Optional[str]:
    """
    Compute a stem for stat prop markets by normalizing player + category.
    
    Example:
        "Jayson Tatum: 25+ Points" → "jayson tatum:points"
        "Jayson Tatum: 30+ Points" → "jayson tatum:points"
        (same stem → stat prop group)
    """
    stat_prop = extract_stat_prop(name)
    if not stat_prop:
        return None
    
    player_name, stat_category, _, _ = stat_prop
    return f"{player_name.lower()}:{stat_category}"


def compute_playoff_stem(name: str) -> Optional[str]:
    """
    Compute a stem for playoff progression markets by normalizing team name.
    
    Example:
        "Lakers: Make Playoffs" → "lakers"
        "Lakers: Make Round 2" → "lakers"
        (same stem → playoff progression group)
    """
    playoff_stage = extract_playoff_stage(name)
    if not playoff_stage:
        return None
    
    team_name, _, _ = playoff_stage
    return team_name.lower()


def discover_group_id_for_market(
    source: str,
    external_id: str,
    canonical_market_key: Optional[str],
    name: str,
    market_id: int,
) -> Optional[tuple[str, str]]:
    """
    Compute a (group_id, group_type) for a market based on available data.

    Priority:
    1. Source-specific hierarchy (polymarket:X, kalshi:X) — set during ingestion
    2. Canonical key grouping — when canonical_market_key matches other markets
    3. Threshold stem detection — within same canonical group

    Returns:
        Tuple of (group_id, group_type) or None.
    """
    # Source-specific hierarchy (already set during ingestion)
    if source == "polymarket" and external_id:
        return (f"polymarket:{external_id}", "polymarket_event")
    if source == "kalshi" and external_id:
        return (f"kalshi:{external_id}", "kalshi_event")

    # Canonical key grouping
    if canonical_market_key:
        return (f"canonical:{canonical_market_key}", "canonical")

    return None
