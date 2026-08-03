"""Single shared classifier for per-game market CLASS (moneyline / spread / …).

WHY THIS EXISTS (2026-08-03, program: calibration): there was NO persisted
market class anywhere (`futures_markets.market_type`/`group_type` are ~100%
NULL). Class was computed on read by three DIFFERENT non-shared classifiers
(`routes/events.py:_classify_game_market`, an admin CASE, `routes/golf.py`),
plus a fourth invented inline in a census SQL. A capture census then found the
impossible: only ~147 markets classed as "moneyline" across ~231 MLB games —
fewer game-winner markets than games. The cause was a read-side classifier that
keys on English words ("moneyline"/"winner"/"beat") that the DOMINANT real
game-winner phrasing does not contain: Kalshi/Polymarket name their winner
markets "<Team> at <Team>" / "<Team> vs. <Team>" (a bare matchup), and Kalshi
carries a `KX<LEAGUE>GAME-...` ticker.

This module is the ONE pure, per-sport-fixture-testable recognizer. It imports
NOTHING but stdlib (circular-import safe, like `sport_keys.py`) so every
consumer — the game-markets endpoint, the calibration cohorts, and the capture
census — can call it instead of re-implementing recognition and drifting.

Coarse taxonomy (what the capture census counts):
    moneyline | spread | total | player_prop | team_prop | other

Consumers that need a finer taxonomy (period winners/totals, h2h/3ball) can keep
their own logic and use `is_game_winner_market()` only to close the specific
bare-matchup leak.
"""

from __future__ import annotations

import re
from typing import Optional

# A leading league tag like "MLB: ", "NBA:", "NCAAB - " that Kalshi/Polymarket
# sometimes prepend to a matchup title. Stripped before bare-matchup detection.
_LEAGUE_TAG_RE = re.compile(
    r"^\s*(?:mlb|nba|nfl|nhl|wnba|mls|ncaab|ncaamb|ncaaf|epl|ucl|uefa|mma|ufc|"
    r"atp|wta|pga|f1)\s*[:\-]\s*",
    re.IGNORECASE,
)

# Team/participant token run: letters, spaces, and the punctuation that appears
# INSIDE names (period, apostrophe, ampersand, internal hyphen). Deliberately
# does NOT allow ":" or " - " (space-dash-space), which mark a sub-market
# qualifier ("... : Total Runs", "... - Player Props").
_TEAM = r"[A-Za-z0-9.'&][A-Za-z0-9 .'&/-]*?"

# "<Team> at|vs|v|@ <Team>" with nothing meaningful after the second team.
_BARE_MATCHUP_RE = re.compile(
    rf"^{_TEAM}\s+(?:at|vs\.?|v\.?|@)\s+{_TEAM}\s*$",
    re.IGNORECASE,
)

# "Will (the) A beat/defeat/... B?" question form.
_WILL_BEAT_RE = re.compile(
    r"^will\s+.+\s+(?:beat|defeat|top|upset|get past|win against|"
    r"take down|knock out)\s+.+\??\s*$",
    re.IGNORECASE,
)

# Explicit game-winner wording.
_MONEYLINE_WORD_RE = re.compile(
    r"\b(?:moneyline|money line|to win outright|to win the game|game winner|"
    r"match winner|which team will win|who will win)\b",
    re.IGNORECASE,
)
# Bare "winner" as a standalone word (avoid matching "Winnipeg" via substring).
_WINNER_WORD_RE = re.compile(r"\bwinner\b", re.IGNORECASE)

# Spread family (team-sport handicaps), any wording/source.
_SPREAD_RE = re.compile(
    r"(?:\brun ?line\b|\bpuck ?line\b|\bpoint ?spread\b|\bspread\b|\bhandicap\b|"
    r"\bmargin\b|by \d+(?:\.\d+)?\+? (?:run|goal|point)s?|[+-]\d+\.\d)",
    re.IGNORECASE,
)

# Totals family. "team total" is handled as team_prop below, so exclude it here.
_TOTAL_RE = re.compile(
    r"(?:\btotal (?:run|goal|point)s?\b|\bover/under\b|\bo/u\b|"
    r"\bcombined (?:run|goal|point)s?\b|\b(?:over|under)\b)",
    re.IGNORECASE,
)

# Player-prop stat words (require a specific stat, not a bare team matchup).
_PLAYER_PROP_RE = re.compile(
    r"\b(?:strikeouts?|home ?runs?|\bhits\b|\brbis?\b|total bases|stolen bases?|"
    r"walks|points|assists|rebounds|steals|blocks|three.?pointers?|3.?pointers?|"
    r"turnovers|passing.?yards|rushing.?yards|receiving.?yards|touchdowns?|"
    r"first ?basket|to score|anytime|shots on goal|saves|goals?\b.*scorer|"
    r"double.?doubles?|triple.?doubles?|pra\b|outs recorded|pitching outs)\b",
    re.IGNORECASE,
)

# Team-scoped derivative props ("team total", first-to-score, innings, NRFI).
_TEAM_PROP_RE = re.compile(
    r"(?:\bteam total\b|\bfirst to score\b|\binning\b|\bnrfi\b|\bfirst (?:run|goal|point)\b|"
    r"\brace to \d+\b|\bwhich half\b|\bhighest scoring\b)",
    re.IGNORECASE,
)


def is_bare_matchup(name: str) -> bool:
    """True if ``name`` is ONLY a two-side matchup title (a game-winner market).

    Recognizes the dominant real phrasing that carries no "winner"/"moneyline"
    word: "Celtics at Warriors", "Yankees vs. Red Sox", "MLB: Yankees at
    Dodgers", "Will the Yankees beat the Red Sox?". Rejects titles with a
    sub-market qualifier ("... : Total Runs", "... - Player Props").
    """
    if not name:
        return False
    stripped = _LEAGUE_TAG_RE.sub("", name).strip()
    # A colon or a space-dash-space marks a sub-market qualifier, not a bare game.
    if ":" in stripped or " - " in stripped:
        return False
    if _WILL_BEAT_RE.match(stripped):
        return True
    return bool(_BARE_MATCHUP_RE.match(stripped))


def is_game_winner_market(
    name: str, external_id: Optional[str] = None, sport: Optional[str] = None
) -> bool:
    """True if this market decides the game winner (a moneyline).

    Covers three recognizers, in order of confidence:
      1. explicit moneyline/winner wording in the name,
      2. a bare matchup title (the leak the census exposed),
      3. a Kalshi game ticker (``KX<LEAGUE>GAME-...`` → contains "game", or a
         "winner" ticker) — for ALL leagues, not just the few hard-coded ones.
    """
    name = name or ""
    if _MONEYLINE_WORD_RE.search(name) or _WINNER_WORD_RE.search(name):
        return True
    if is_bare_matchup(name):
        return True
    if external_id:
        t = external_id.lower()
        # Only trust the game/winner ticker signal for Kalshi-style tickers,
        # never a Polymarket condition hash (which is opaque hex).
        if t.startswith("kx") and ("game" in t or "winner" in t):
            return True
    return False


def classify_game_market_class(
    name: str, external_id: Optional[str] = None, sport: Optional[str] = None
) -> str:
    """Classify a per-game market into the coarse census taxonomy.

    Returns one of: moneyline | spread | total | player_prop | team_prop | other.

    Order matters and mirrors the production read-side intent: the most specific
    tells (player/team props, totals, spreads) win before the game-winner
    catch, so a "Team at Team: Rebounds" prop is not miscounted as a moneyline.
    """
    name = name or ""
    lower = name.lower()

    # Team-scoped derivatives first ("team total", first-to-score, NRFI …) so a
    # "team total" is not swallowed by the totals branch.
    if _TEAM_PROP_RE.search(name):
        return "team_prop"
    # Totals before player props: "Total Points" is a game total, not a prop
    # (mirrors routes/events.py ordering). "Total bases" is NOT a total (no
    # run/goal/point token) so it correctly falls through to player_prop.
    if _TOTAL_RE.search(name):
        return "total"
    if _PLAYER_PROP_RE.search(name):
        return "player_prop"
    if _SPREAD_RE.search(name):
        return "spread"
    # Ticker-only spread/total MUST be checked before the bare-matchup moneyline
    # catch: a "Celtics at Warriors" title with a KXNBA2HSPREAD ticker is a
    # spread, not a game winner (the name alone looks like a bare matchup).
    if external_id:
        t = external_id.lower()
        if t.startswith("kx"):
            if "spread" in t:
                return "spread"
            if "total" in t:
                return "total"
    if is_game_winner_market(name, external_id, sport):
        return "moneyline"
    _ = lower  # reserved for future sport-specific disambiguation
    return "other"
