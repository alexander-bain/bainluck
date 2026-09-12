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
from typing import Iterable, Optional

# A leading league tag like "MLB: ", "NBA:", "NCAAB - " that Kalshi/Polymarket
# sometimes prepend to a matchup title. Stripped before bare-matchup detection.
_LEAGUE_TAG_RE = re.compile(
    r"^\s*(?:mlb|nba|nfl|nhl|wnba|mls|ncaab|ncaamb|ncaaf|epl|ucl|uefa|mma|ufc|"
    r"atp|wta|pga|f1)\s*[:\-]\s*",
    re.IGNORECASE,
)

# Team/participant token run: letters, spaces, and the punctuation that appears
# INSIDE names (period, apostrophe, ampersand, internal hyphen, and the
# parenthesised disambiguator US college teams carry — "Miami (OH)").
#
# THE LETTER CLASS IS UNICODE, NOT ASCII (#5041). It used to read
# `[A-Za-z0-9...]`, which silently answered "not a game winner" for every team
# name with a diacritic: `1. FC Köln vs. SV Werder Bremen`, `Club León FC vs.
# Atlético San Luis`, `Associação Chapecoense de Futebol vs. SC Internacional`,
# `SE Palmeiras vs. São Paulo FC`. Measured over every Polymarket market linked
# to an event commencing within 48h (1,096 markets / 210 events, 2026-09-11):
# 257 are a bare matchup carrying no sub-market qualifier, and 12 of them —
# across 12 distinct events, every one a real match winner — were refused for
# their accents alone. The bias was systematic and it ran one way: La Liga 2,
# Bundesliga, Liga MX, Brasileirão, Serie B, and college teams with a
# parenthesised state.
#
# Widening the CLASS does not widen what is admitted, because the qualifier is
# not rejected here — `is_bare_matchup` rejects ":" and " - " before this
# pattern is ever tried (see the guard there, and the test that deletes it).
# The shape is the original's, unchanged: one restricted opening character, then
# a non-greedy run. Only the two character classes moved — `[^\W_]` is "letter or
# digit, any script, never underscore", and the run adds "(" and ")".
_TEAM = r"[^\W_][\w .'&/()-]*?"

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

# An OUTCOME label that can only belong to a derivative book — a handicap, a
# total, a period, or a scoreline. Deliberately narrower than the market-name
# patterns above: this one is asked of an outcome, where the alternative is a
# bare competitor name, so it must fire on positive evidence only (see
# `outcomes_refute_game_winner` for why a false positive costs more than a
# false negative here).
#
# Every alternative is word-anchored for the "Winnipeg"/"Thunder" reason the
# `_WINNER_WORD_RE` comment records: `\bunder\b` must not fire on Oklahoma City
# Thunder, and it does not — the "under" inside it is preceded by a word
# character, so there is no boundary.
_DERIVATIVE_OUTCOME_RE = re.compile(
    r"(?:"
    r"\bo/u\b"                                    # "O/U 47.5"
    r"|\bover\b|\bunder\b"                        # "Over" / "Under"
    r"|\bspread\b|\bhandicap\b"                   # "Spread -13.5", "Set Handicap +/-1.5"
    r"|\brun ?line\b|\bpuck ?line\b"
    r"|\bnrfi\b|\byrfi\b"                         # "NRFI" alone, wearing the game's title
    r"|\bset \d+\b"                               # "Set 1 Winner", "Set 1 O/U 8.5"
    r"|\btotal (?:sets|games|points|runs|goals|corners)\b"
    r"|\((?:\+|-)\d"                              # "Venezia FC (-1.5)"
    r"|\b\d+ ?- ?\d+\b"                           # exact score "2 - 2"
    r")",
    re.IGNORECASE,
)


# Segment-scope words that can head a title and mean "a PART of the match":
# "Map 1: A vs B", "Period 2: A vs B", "1st Round Head-to-Head: Åberg vs
# Fleetwood". Consulted ONLY against a leading prefix (see
# `_matchup_behind_competition_prefix`), never against a whole title, so its
# only possible effect is to leave a prefixed title classed exactly as it is
# classed today.
#
# MEASURED INERT, AND KEPT AS THE FAIL-CLOSED MARGIN (#5660). Over every
# Polymarket/Kalshi market linked to an event commencing within ±7 days
# (1,752 distinct names, 2026-09-12), this pattern blocked nothing that the
# module's existing vocabulary did not already block: all 441 refused prefixes
# were caught by `_DERIVATIVE_OUTCOME_RE`/`_WINNER_WORD_RE` ("Set 1 Winner: …",
# 439) or `_TEAM_PROP_RE` ("Will there be a run scored in the first inning?: …",
# 2). It is here because the esports rows DO carry these scopes today — as a
# SUFFIX ("Counter-Strike: 1WIN vs B8 - Map 1 Winner", 151 rows, refused by the
# " - " test) — and a venue that moves one to the front must not thereby
# publish a map winner as the match winner. Its failure mode is today's
# behaviour, so an over-broad token costs a missed match, never a wrong price.
_DERIVATIVE_SCOPE_RE = re.compile(
    r"\b(?:map|period|quarter|half|frame|leg|set|game|round|inning|innings)\b",
    re.IGNORECASE,
)

# Every pattern that disqualifies a leading prefix from being read as a
# competition name. Reuses the module's own vocabulary rather than inventing a
# second one, so a derivative word learned anywhere is learned here too.
_PREFIX_DISQUALIFIERS = (
    _SPREAD_RE,
    _TOTAL_RE,
    _PLAYER_PROP_RE,
    _TEAM_PROP_RE,
    _DERIVATIVE_OUTCOME_RE,
    _WINNER_WORD_RE,
    _MONEYLINE_WORD_RE,
    _DERIVATIVE_SCOPE_RE,
)


def _matchup_behind_competition_prefix(stripped: str) -> bool:
    """True if ``stripped`` is a bare matchup wearing a competition PREFIX.

    THE OLD TEST COULD NOT TELL A PREFIX FROM A SUFFIX (#5660). It asked
    whether a ":" or a " - " appeared ANYWHERE and answered "not a bare game"
    if one did. That is right for a qualifier hung off the END — "Yankees at
    Dodgers: Total Runs" — and wrong for a competition hung off the FRONT, which
    is how Polymarket titles most of its tennis, rugby, cricket, pickleball and
    doubles fixtures and how Kalshi titles its fight cards: "US Open ATP:
    Alexander Zverev vs Ben Shelton", "PPA - Women's Singles: Hannah Blatt vs
    Polina Libo", "Fight Night: Aldrich vs Tarin", "M25 Sintra: Dino Molokova
    Ferreira vs Lucas Nunez". Gamma calls the PPA row `sportsMarketType=
    moneyline`; we called it "other" for its prefix alone.

    DIRECTION IS THE WHOLE DISCRIMINATOR, and it is read structurally rather
    than guessed: the market's own qualifier — if it has one — trails the
    matchup, where the unchanged ":"/" - " test still refuses it
    ("Counter-Strike: 1WIN vs B8 - Map 1 Winner"). Only when the tail is a clean
    two-side matchup is the head examined at all, and then it must carry no
    derivative word (`_PREFIX_DISQUALIFIERS`), because a head is free to name a
    segment instead of a competition — "Set 1 Winner: Aboian vs Martin" is a
    set, not the match.

    THE SPLIT IS AT THE LAST COLON SO THAT THE WHOLE HEAD IS TESTED. On the
    single-colon titles that are 100% of the measured window the two splits are
    indistinguishable; they differ only on a multi-segment head
    ("US Open ATP: Qualification: Carole Monnet vs Julia Garcia"), which a
    first-colon split refuses outright and this one admits — but only after
    reading every segment of the head for a derivative word, so the extra reach
    cannot admit a segment market. Multi-colon titles are UNOBSERVED in the
    measured window; the case is pinned by test rather than left to whichever
    split someone edits in later.

    A " - " with no colon is left exactly as it was: that shape is a trailing
    qualifier in every row measured, and widening it has no evidence behind it.

    MEASURED BOTH DIRECTIONS before shipping, over every market linked to an
    event commencing within ±7 days (1,752 distinct names, production
    2026-09-12): 408 names move "other" → "moneyline" and **zero** move the
    other way. Every one of the 408 wears a competition, venue or card name —
    the US Open ATP/WTA singles and doubles draws, 30-odd ITF/challenger venues
    (M15/M25/W15/W50 …), Top 14, United Rugby Championship, Premiership Rugby,
    the T20/Test cricket series, UFC 331, Kalshi's Fight Night and MMA cards,
    and the three PPA pickleball draws this issue was filed on. 441 are refused
    by the prefix test and 898 by the structural tests.
    """
    prefix, sep, tail = stripped.rpartition(":")
    if not sep:
        return False
    tail = _LEAGUE_TAG_RE.sub("", tail.strip()).strip()
    # The market's own qualifier lives in the tail — refuse it exactly as before.
    if not tail or ":" in tail or " - " in tail:
        return False
    if any(pattern.search(prefix) for pattern in _PREFIX_DISQUALIFIERS):
        return False
    if _WILL_BEAT_RE.match(tail):
        return True
    return bool(_BARE_MATCHUP_RE.match(tail))


def is_bare_matchup(name: str) -> bool:
    """True if ``name`` is ONLY a two-side matchup title (a game-winner market).

    Recognizes the dominant real phrasing that carries no "winner"/"moneyline"
    word: "Celtics at Warriors", "Yankees vs. Red Sox", "MLB: Yankees at
    Dodgers", "Will the Yankees beat the Red Sox?", and — since #5660 — a bare
    matchup behind a competition prefix ("US Open ATP: Zverev vs Shelton").
    Rejects titles with a sub-market qualifier ("... : Total Runs", "... -
    Player Props", "Set 1 Winner: Aboian vs Martin").
    """
    if not name:
        return False
    stripped = _LEAGUE_TAG_RE.sub("", name).strip()
    # A colon or a space-dash-space marks a sub-market qualifier — UNLESS the
    # colon is a competition prefix and the real matchup is behind it (#5660).
    if ":" in stripped or " - " in stripped:
        return _matchup_behind_competition_prefix(stripped)
    if _WILL_BEAT_RE.match(stripped):
        return True
    return bool(_BARE_MATCHUP_RE.match(stripped))


def outcomes_refute_game_winner(outcome_names: Optional[Iterable[Optional[str]]]) -> bool:
    """True if this market's OWN outcomes say it is not the match winner.

    THE NAME IS NOT ENOUGH, AND THE ROW ALREADY CARRIES THE REFUTATION (#5273).
    Polymarket mints an event-level container whose title is the bare matchup —
    "Cowboys vs. Giants", "Duquesne vs. Youngstown State" — and hangs the
    derivative books off it as OUTCOMES: `Spread -16.5 | Duquesne`,
    `Spread -20.5 | O/U 57.5 | Cal Poly`, `NRFI` alone. Every one of those
    passes `is_bare_matchup` on its title, so `classify_game_market_class`
    answers "moneyline" and the blend admits it; `find_moneyline_outcome` then
    resolves the one competitor-shaped outcome by containment and publishes a
    HANDICAP's price as the match winner. Measured on production 2026-09-12
    over the (-6h, +48h) window: of 314 Polymarket markets the name gate
    admits, 88 are refuted by their own outcomes, and the eligibility record
    (#5311) names three of them as the live speaker — including US Open ATP
    Tiafoe vs Shelton, whose Polymarket leg read 0.165 off a basket of
    `Set 1 O/U 8.5` / `Set Handicap +/-1.5` outcomes against Kalshi's 0.01.

    COUNTING OUTCOMES CANNOT DO THIS JOB, which is why the predicate reads the
    vocabulary instead. The legitimate winner shapes are two outcomes
    (`Yes | No`) and THREE (soccer's `Tijuana | Draw (…) | Querétaro`), while
    the broken containers span one to twenty — `Duquesne | Spread -16.5` has
    exactly two and `Spread -20.5 | O/U 57.5 | Cal Poly` exactly three. Any
    arity test either keeps them or takes soccer's draw down with them.

    ANY derivative outcome refutes, rather than a majority: a real match-winner
    book never lists a handicap beside its competitors, so one is already the
    whole signal, and requiring a majority would keep `Duquesne | Spread -16.5`.

    Fail-open on absence. An empty or unloaded outcome list is NO EVIDENCE, not
    evidence of innocence — and the asymmetry is deliberate, because the two
    errors do not cost the same. A false positive retires a real winner and can
    empty a card; a false negative leaves today's behaviour exactly as it is.
    So the predicate only ever answers True on something it has actually read.
    Measured against that bar on the same window: the 88 refusals re-point 25
    events to a genuine winner in the same group, retire 57 wrong legs, and
    blank **zero** cards — every affected event keeps a number from another
    source.
    """
    if not outcome_names:
        return False
    return any(
        _DERIVATIVE_OUTCOME_RE.search(name)
        for name in outcome_names
        if name
    )


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
