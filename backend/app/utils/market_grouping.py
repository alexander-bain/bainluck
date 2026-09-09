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

import os
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
    (?:or\s+(?:more|above|higher|greater|less|below|lower|fewer)|\+|-(?!\s*\d)|\s+and\s+above|\s+and\s+below)
    """,
    re.IGNORECASE | re.VERBOSE,
)

# UX-1052 item 2 — an exact SCORELINE: two integers joined by a dash, with a
# non-digit on each side so a decimal ("2.5-3.5") or a longer run of digits
# cannot masquerade as one. Kept deliberately narrow: this pattern's only job
# is to tell "0 - 3" apart from a threshold, and a false positive here silently
# deletes a real threshold rung.
_SCORELINE_RE = re.compile(
    r"""
    (?<![\d.\-])     # not inside a longer number, a decimal, or an ISO date
    (\d{1,2})        # home goals / sets
    \s*[-–—]\s*      # hyphen, en dash or em dash
    (\d{1,2})        # away goals / sets
    (?![\d.\-])      # ditto on the trailing side ("2026-09-03" must not match)
    """,
    re.VERBOSE,
)

# The trailing verb that marks the text BEFORE a scoreline as the WINNER rather
# than as one side of a fixture: "Iva Jovic wins 2-1" (Polymarket tennis) vs
# "AC Milan 0 - 3 Benfica" (Polymarket soccer). Two different label problems —
# see `_scoreline_label`.
_SCORELINE_ACTOR_TAIL_RE = re.compile(
    r"\s*(?:to\s+win|wins|win|beats|def\.?|defeats)\s*[:\-–—]?\s*$",
    re.IGNORECASE,
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


def extract_scoreline(name: str) -> Optional[tuple[int, int]]:
    """
    Extract an exact SCORELINE from an outcome name, e.g.

        "AC Milan 0 - 3 Sport Lisboa e Benfica"  → (0, 3)
        "FC Emmen 1 - 1 FC Volendam"             → (1, 1)

    Returns (home_goals, away_goals) in the order they appear, or None.

    UX-1052 item 2. This exists because ``_THRESHOLD_SIMPLE_RE`` accepts a bare
    ``-`` as a threshold suffix, so every Polymarket "Exact Score" outcome
    parsed as a threshold on its FIRST number: "AC Milan 0 - 3 Benfica" became
    ``≥ 0``, "3 - 1" and "3 - 2" both became ``≥ 3``. Alex, shopping /sports on
    2026-09-03: the ladder showed "≥ 0, ≥ 1, ≥ 2, ≥ 2" — "rung labels are not
    the outcomes."

    A scoreline is not a threshold in either direction, so the parser must
    REFUSE it rather than pick one of its two numbers. The refusal is enforced
    at the top of `extract_threshold`; the parsed pair is what
    `detect_exact_score_groups` labels the rungs with.
    """
    if not name:
        return None
    m = _SCORELINE_RE.search(name)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)))


def _scoreline_label(name: str) -> Optional[str]:
    """
    The rung label for an exact-score outcome — UX-1052 item 2.

    Two shapes reach this, and only one of them is unambiguous from the score
    alone:

        "AC Milan 2 - 3 Sport Lisboa e Benfica"  → "2–3"
            Both sides are named IN the outcome, in the same order as the card
            title, so the bare score reads correctly.

        "Iva Jovic wins 2-1"                     → "Iva Jovic 2–1"
            The score alone would collide: "Magdalena Frech wins 2-1" is a
            different outcome with the same digits. Labelling both "2–1" would
            reproduce the exact defect this queue is fixing — duplicate rung
            labels that are not the outcomes — one layer down.

    Returns None when there is no scoreline.
    """
    if not name:
        return None
    m = _SCORELINE_RE.search(name)
    if not m:
        return None
    score = f"{int(m.group(1))}–{int(m.group(2))}"

    before = name[: m.start()].strip()
    after = name[m.end():].strip()
    # Text on BOTH sides ⇒ a fixture, and the score is the whole story.
    if after:
        return score
    actor = _SCORELINE_ACTOR_TAIL_RE.sub("", before).strip(" :·-–—")
    return f"{actor} {score}" if actor else score


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

    # UX-1052 item 2 — a SCORELINE is not a threshold. "2 - 1" carries two
    # numbers and no direction; reading either one as "≥ N" invents a claim the
    # market never made. Refuse before any pattern gets a chance to guess.
    if extract_scoreline(name):
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
    Optionally (strongly preferred — see #1102):
        - market_name: str (parent market name, carries player/game/entity)
        - group_id: str (shared real-world-question grouping)

    Returns:
        Dict mapping scope_key → sorted list of outcome dicts
        (only groups with 2+ outcomes belonging to the same real-world
        question). Each outcome dict gets additional keys:
        - threshold_value: float
        - threshold_unit: str
        - threshold_direction: str

    Scoping (#1102): outcome names alone are context-free (e.g. "Over 2.5"
    for one player and a different game share the stem "over #"). Grouping
    purely by that stem pooled unrelated markets into one card with no
    player/game attribution. We now scope each group to a single real-world
    question — an explicit ``group_id`` when present, else a stem of the
    parent ``market_name`` (which carries the entity), and only fall back to
    the bare outcome stem when neither is available (legacy callers).
    """
    by_scope: dict[str, list[dict]] = {}

    for o in outcomes:
        name = o.get("name", "")

        threshold = extract_threshold(name)
        if not threshold:
            continue

        group_id = o.get("group_id")
        market_name = o.get("market_name")
        if group_id:
            scope = f"group:{group_id}"
        elif market_name:
            # A market-name stem keeps the entity ("Jayson Tatum: Points")
            # while collapsing threshold variants ("25+" / "30+").
            scope = compute_threshold_stem(market_name) or market_name.strip().lower()
        else:
            # Legacy path: no parent context available, group by outcome stem.
            stem = compute_threshold_stem(name)
            if not stem:
                continue
            scope = stem

        value, unit, direction = threshold
        enriched = {
            **o,
            "threshold_value": value,
            "threshold_unit": unit,
            "threshold_direction": direction,
        }
        by_scope.setdefault(scope, []).append(enriched)

    # Only return groups with 2+ outcomes, sorted by threshold value
    result = {}
    for scope, group in by_scope.items():
        if len(group) >= 2:
            group.sort(key=lambda x: x["threshold_value"])
            result[scope] = group

    return result


def detect_exact_score_groups(
    outcomes: list[dict],
) -> dict[str, list[dict]]:
    """
    Detect EXACT SCORE groups among a list of outcomes — UX-1052 item 2.

    An exact-score market ("AC Milan vs. Benfica - Exact Score") is a discrete
    distribution over scorelines, not a ladder of cumulative thresholds. Before
    this existed the outcomes fell into `detect_threshold_groups`, which read
    the first integer of "AC Milan 2 - 3 Benfica" as a threshold and printed
    "≥ 2" — a label that is not the outcome, and that collides with every other
    scoreline sharing a home score.

    Each outcome dict should have at minimum:
        - id: int
        - name: str (e.g. "AC Milan 2 - 3 Sport Lisboa e Benfica")
        - market_id: int
    Optionally (strongly preferred, same scoping rules as thresholds):
        - market_name: str
        - group_id: str
        - probability: float | None

    Returns:
        Dict mapping scope_key → list of outcome dicts, MOST LIKELY FIRST
        (only groups with 2+ scoreline outcomes). Each dict gains:
        - score_home: int
        - score_away: int
        - score_label: str  — the rung label, e.g. "2–3" (en dash)

    Ordering is by probability descending, not by scoreline. On a 16-rung
    exact-score market the glance card shows the first four rungs, and the four
    most likely scorelines are the story; the first four in scoreline order are
    "0–0, 0–1, 0–2, 0–3", which is an alphabetisation, not a reading.
    """
    by_scope: dict[str, list[dict]] = {}

    for o in outcomes:
        name = o.get("name", "")
        score = extract_scoreline(name)
        if not score:
            continue

        group_id = o.get("group_id")
        market_name = o.get("market_name")
        if group_id:
            scope = f"group:{group_id}"
        elif market_name:
            scope = market_name.strip().lower()
        else:
            # No parent context: a bare scoreline cannot be scoped to a game,
            # and pooling scorelines across unrelated matches is the #1102
            # defect. Refuse rather than guess.
            continue

        home, away = score
        by_scope.setdefault(scope, []).append({
            **o,
            "score_home": home,
            "score_away": away,
            "score_label": _scoreline_label(name) or f"{home}–{away}",
        })

    result = {}
    for scope, group in by_scope.items():
        if len(group) >= 2:
            group.sort(
                key=lambda x: (
                    -(x.get("probability") or 0.0),
                    x["score_home"],
                    x["score_away"],
                )
            )
            result[scope] = group

    return result


# ── PLACEMENT GRID DETECTION (UX-1052 item 3) ──

#: The placement questions a tournament asks about the SAME field of players,
#: in the order a reader climbs them: hardest first. `key` is the grid column
#: id, `label` is its header. Mirrors `FINISH_POSITION_COLUMNS` in
#: `frontend/lib/eventConceptDisplay.ts`, which is the concept page's version of
#: this same grid — the two are one design, and the ordering must not diverge.
PLACEMENT_COLUMNS: list[tuple[str, str]] = [
    ("winner", "Winner"),
    ("top_5", "Top 5"),
    ("top_10", "Top 10"),
    ("top_20", "Top 20"),
    ("top_40", "Top 40"),
    ("make_cut", "Make cut"),
]

_PLACEMENT_SUFFIX_RE = re.compile(
    r"""
    ^\s*(?:
        (?P<winner>winner|to\s+win|outright(?:\s+winner)?)
      | top\s*(?P<top>\d{1,2})(?:\s+finish)?
      | (?P<cut>make(?:\s+the)?\s+cut|to\s+make\s+the\s+cut)
    )\s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

#: Minimum distinct placement questions before a set of markets is worth a grid.
#: Alex: "Same for any tournament with ≥3 placement markets." Below that the
#: grid is a table with one column — worse than the cards it replaces.
PLACEMENT_GRID_MIN_COLUMNS = 3


def parse_placement_market(name: str) -> Optional[tuple[str, str]]:
    """
    Split a placement market name into (tournament, column_key) — UX-1052 item 3.

        "Omega European Masters - Top 10 Finish"  → ("Omega European Masters", "top_10")
        "Omega European Masters - Winner"         → ("Omega European Masters", "winner")
        "Omega European Masters - Make the Cut"   → ("Omega European Masters", "make_cut")

    Returns None when the name is not a recognised placement question, which is
    the common case — the refusal is what keeps unrelated "X - Y" markets (every
    Polymarket "A vs. B - Exact Score" on the same strip) out of the grid.
    """
    if not name or " - " not in name:
        return None
    tournament, _, suffix = name.rpartition(" - ")
    tournament = tournament.strip()
    if not tournament:
        return None
    m = _PLACEMENT_SUFFIX_RE.match(suffix)
    if not m:
        return None
    if m.group("winner"):
        return (tournament, "winner")
    if m.group("cut"):
        return (tournament, "make_cut")
    top = f"top_{int(m.group('top'))}"
    if top not in {k for k, _ in PLACEMENT_COLUMNS}:
        return None
    return (tournament, top)


def detect_placement_groups(
    markets: list[dict],
) -> dict[str, dict]:
    """
    Group a tournament's placement markets into ONE grid — UX-1052 item 3.

    Alex, shopping /sports on 2026-09-03: five near-identical cards for the
    Omega European Masters (Winner, Top 5, Top 10, Top 20, Make the Cut), each
    listing the same handful of golfers. "Group them into a beautiful grid …
    players down, markets across, the way the US Open bracket grid works."

    Each market dict should have at minimum:
        - id: int
        - name: str  ("Omega European Masters - Top 10 Finish")
        - outcomes: list of {id, name, probability}
    Optionally: source, sport, category.

    Returns:
        Dict mapping tournament key → a grid descriptor:
            {
              "tournament": str,
              "market_ids": [int, ...],
              "columns": [{"key": str, "label": str}, ...],   # ordered
              "rows": [{"name": str, "values": {col_key: prob|None}}, ...],
              "row_total": int,
              "sources": [str, ...],
            }
        Only tournaments with >= PLACEMENT_GRID_MIN_COLUMNS distinct columns.

    Rows are ordered by the WINNER column descending where it exists, else by
    the strongest value the player carries anywhere in the grid. A player with
    no odds in a column gets ``None`` — rendered as "—", never fabricated,
    which is the same rule the concept page's ladder already follows.
    """
    by_tournament: dict[str, dict] = {}

    for m in markets:
        parsed = parse_placement_market(m.get("name") or "")
        if not parsed:
            continue
        tournament, column = parsed
        key = tournament.lower()
        entry = by_tournament.setdefault(
            key,
            {"tournament": tournament, "market_ids": [], "columns": {},
             "players": {}, "sources": []},
        )
        if column in entry["columns"]:
            # Two sources for one question: keep the first and do not double the
            # column. Cross-source reconciliation is the blend's job, not the
            # grid's ("the blend is the product").
            continue
        entry["columns"][column] = True
        entry["market_ids"].append(m.get("id"))
        source = m.get("source")
        if source and source not in entry["sources"]:
            entry["sources"].append(source)
        for o in m.get("outcomes") or []:
            player = (o.get("name") or "").strip()
            if not player:
                continue
            prob = o.get("probability")
            if prob is None:
                continue
            entry["players"].setdefault(player, {})[column] = float(prob)

    result: dict[str, dict] = {}
    for key, entry in by_tournament.items():
        ordered_columns = [
            {"key": k, "label": label}
            for k, label in PLACEMENT_COLUMNS
            if k in entry["columns"]
        ]
        if len(ordered_columns) < PLACEMENT_GRID_MIN_COLUMNS:
            continue
        if not entry["players"]:
            continue

        column_keys = [c["key"] for c in ordered_columns]

        def _rank(item):
            _, values = item
            win = values.get("winner")
            best = max((v for v in values.values() if v is not None), default=0.0)
            # Winner-first, then the strongest number the player carries. A
            # player absent from the winner market still sorts sensibly instead
            # of sinking to the bottom of a grid they lead a column of.
            return (-(win if win is not None else -1.0), -best)

        rows = [
            {"name": player,
             "values": {c: values.get(c) for c in column_keys}}
            for player, values in sorted(entry["players"].items(), key=_rank)
        ]

        result[key] = {
            "tournament": entry["tournament"],
            "market_ids": [i for i in entry["market_ids"] if i is not None],
            "columns": ordered_columns,
            "rows": rows,
            "row_total": len(rows),
            "sources": entry["sources"],
        }

    return result


# ── CONTAINER-MEMBER FOLD (#4153) ──

#: The shortest shared wording that may be treated as one question's template.
#: The members of a Polymarket container group are minted from one sentence with
#: one slot swapped ("Will {player} advance to the Final …?"), so the shared
#: prefix+suffix is nearly the whole name. A group whose members share almost no
#: wording is not that shape, and folding it would put unrelated questions under
#: one title — so the fold refuses rather than guesses.
CONTAINER_FOLD_MIN_SHARED_AFFIX_CHARS = 8

#: A container fold needs a field to be a field. One priced member is a claim
#: about one entity and already has a correct card of its own.
CONTAINER_FOLD_MIN_MEMBERS = 2



def _shared_affixes(names: list[str]) -> tuple[str, str]:
    """The wording every one of ``names`` shares, snapped to word boundaries.

    Returns ``(prefix, suffix)``. Both are trimmed back to whitespace so a
    common run that stops mid-word ("Will Em" across Emma/Emily) can never eat
    half of the entity it is supposed to be leaving behind.
    """
    if not names:
        return ("", "")
    prefix = os.path.commonprefix(names)
    suffix = os.path.commonprefix([n[::-1] for n in names])[::-1]
    # A prefix that ends mid-word, or a suffix that starts mid-word, would slice
    # the entity. Back each one off to the nearest space.
    while prefix and not prefix.endswith(" "):
        prefix = prefix[:-1]
    while suffix and not suffix.startswith(" "):
        suffix = suffix[1:]
    # Degenerate case: one name is wholly contained in the affixes of another.
    for n in names:
        if len(prefix) + len(suffix) >= len(n):
            return ("", "")
    return (prefix, suffix)


def extract_container_member_entities(names: list[str]) -> Optional[list[str]]:
    """The entity each container member is about, or None if it cannot be told.

        ["Will Coco Gauff advance to the Final in Women's Singles at the 2026 US Open?",
         "Will Iga Swiatek advance to the Final in Women's Singles at the 2026 US Open?"]
        → ["Coco Gauff", "Iga Swiatek"]

    FAIL CLOSED. The caller is about to print these as the rows of one card, so
    a label it cannot derive must sink the whole fold — a row labelled with the
    leftovers of a bad split is worse than the repetition being fixed. Returns
    None when the members share too little wording to be one question, when any
    entity comes out empty, or when two members reduce to the same label (which
    would render one player twice and silently drop another).
    """
    if len(names) < CONTAINER_FOLD_MIN_MEMBERS:
        return None
    prefix, suffix = _shared_affixes(names)
    if len(prefix) + len(suffix) < CONTAINER_FOLD_MIN_SHARED_AFFIX_CHARS:
        return None
    entities = []
    for name in names:
        end = len(name) - len(suffix) if suffix else len(name)
        entity = name[len(prefix):end].strip().strip(":-–—,").strip()
        if len(entity) < 2:
            return None
        # THE SLOT IN A FIELD TEMPLATE IS A NAME.
        #
        # A colon, a bracket or a "vs" in the differing span means what varies
        # between these members is a QUESTION or a FIXTURE, not an entity — so
        # the wording they share was another coincidence. Three more of these
        # survived the template-length rule on production 2026-09-08:
        #
        #   polymarket:968290 → ["US Open WTA (Doubles)", "Set 1 Winner"]
        #   polymarket:982930 → ["Sintra, Qualifying: Completed Match", "Sintra"]
        #   polymarket:987752 → ["Topo (-1.5) vs Sachko", "Sachko (-1.5) vs Topo"]
        #
        # Digits are deliberately NOT banned here: "Schalke 04" is a real
        # entity, and refusing it would cost a legitimate soccer field to catch
        # cases these three characters already catch.
        if any(t in entity for t in (":", "(", ")")) or " vs " in entity.lower():
            return None
        entities.append(entity)
    if len(set(entities)) != len(entities):
        return None

    # THE TEMPLATE MUST BE LONGER THAN THE SLOT IT LEAVES BEHIND.
    #
    # The floor above measures the LENGTH of the shared run, not whether that run
    # is a template, and those are not the same test. Found on production
    # 2026-09-08 by running this splitter over the whole open tennis population
    # instead of over one night's pool:
    #
    #   polymarket:945776, parent "US Open WTA: Marta Kostyuk vs Sloane Stephens"
    #     "Set 2 Winner: Kostyuk vs Stephens"
    #     "US Open WTA: Marta Kostyuk vs Sloane Stephens"
    #
    # Two unrelated questions whose names happen to end on the same word. The
    # shared run is " Stephens" — 9 characters, past the floor — so the split
    # "succeeded" and produced the row labels "Set 2 Winner: Kostyuk vs" and
    # "US Open WTA: Marta Kostyuk vs Sloane". Having a `field` parent did not
    # save it: a two-player MATCH is also a `field`, and its group carries that
    # match's side-markets.
    #
    # "One sentence with one slot swapped" has an arithmetic consequence — the
    # sentence is longer than the slot. That refuses both specimens (9 shared
    # characters against a 36-character "entity") and costs the real fields
    # nothing: the US Open family shares 62 characters around a 14-character name.
    if len(prefix) + len(suffix) < max(len(e) for e in entities):
        return None
    return entities


def detect_container_field_groups(
    members_by_group: dict[str, list[dict]],
    parent_names: dict[str, str],
) -> dict[str, dict]:
    """Fold one Polymarket container group into the one question it really is.

    #4153. Alex, shopping /sports: the "Player Props & Projections" strip is "a
    wall of the same sentence with the names swapped" — twelve cards that are
    four questions. Measured on the served pool the same night: **84 of the 100
    candidate rows are ``container_member``, and they are 18 questions.** Each
    member is one player's Yes/No leg of a field ("Will Coco Gauff advance to
    the Final …?"), and the strip renders one card per leg.

    THE TITLE IS BORROWED, THE NUMBERS ARE NOT. Every one of these groups
    already has a parent row with ``market_type='field'`` carrying the venue's
    own wording ("US Open 2026: To Reach the Final (Women's Singles)"), which is
    why this fold does not have to invent a question from the members' grammar.
    It does NOT take that parent's prices: measured on production 2026-09-08 the
    parent of ``polymarket:910235`` prints ``0.000000`` for Belinda Bencic while
    her live member leg is ``0.833`` — the parent is stale where the members are
    polled, so promoting it wholesale would headline a field with a 0% leader
    (#4163). Titles are text; prices come from the members.

    ``members_by_group`` maps group_id → the group's FULL membership (not the
    slice that happened to land in the caller's pool), each dict carrying
    ``id``, ``name``, ``probability`` (the Yes leg) and optionally ``source``.
    Passing a partial roster here is the #2789 failure — a card headed "To Reach
    the Final" whose top row is not the leader because the leader was not loaded.

    Returns group_id → ``{"title", "market_ids", "entries", "sources",
    "member_total"}`` with ``entries`` ranked most-likely first. A group that
    cannot be titled, cannot be split into distinct entities, or has fewer than
    ``CONTAINER_FOLD_MIN_MEMBERS`` priced members is absent from the result and
    keeps the per-member cards it has today.
    """
    result: dict[str, dict] = {}

    for group_id, members in members_by_group.items():
        title = (parent_names.get(group_id) or "").strip()
        if not title:
            continue
        priced = [
            m for m in members
            if m.get("probability") is not None and (m.get("name") or "").strip()
        ]
        if len(priced) < CONTAINER_FOLD_MIN_MEMBERS:
            continue
        entities = extract_container_member_entities([m["name"] for m in priced])
        if entities is None:
            continue

        entries = [
            {
                "market_id": m.get("id"),
                "name": entity,
                "probability": float(m["probability"]),
                "source": m.get("source"),
            }
            for m, entity in zip(priced, entities)
        ]
        # Leader-first, and by entity name where two share a price so the order
        # is stable across rebuilds rather than following the query's whim.
        entries.sort(key=lambda e: (-e["probability"], e["name"]))

        sources = []
        for e in entries:
            if e["source"] and e["source"] not in sources:
                sources.append(e["source"])

        result[group_id] = {
            "title": title,
            "market_ids": [m.get("id") for m in members if m.get("id") is not None],
            "entries": entries,
            "sources": sources,
            "member_total": len(entries),
        }

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
