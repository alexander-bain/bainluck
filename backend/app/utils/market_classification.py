"""Single source of truth for futures market classification.

Given a market (name + metadata), returns the league it belongs to and
the stage/column it represents. Used by every surface that groups markets
by playoff stage:

- Championship grid (``routes/playoffs.py``)
- Event detail TeamPlayoffCard (``routes/events.py`` → team-progression)
- Event detail RelatedFutures / Bigger Picture (``routes/events.py`` →
  related-futures, via ``compute_playoff_stage``)

The classifier uses ``LEAGUE_CONFIGS`` as truth when the market can be
resolved to a specific league; otherwise it falls back to sport-agnostic
patterns so long-tail markets (international soccer, tennis, esports)
still get a reasonable classification.

Importantly, this module imports **only** from ``league_configs`` and
``tournament_stages`` (both zero-dependency). That keeps it free of
circular-import risk so any other module can call it safely.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.config.league_configs import LEAGUE_CONFIGS, LeagueConfig
from app.utils.tournament_stages import classify_market_stage, get_stages_for_sport


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketClassification:
    """Structured classification for a futures market."""

    league_slug: Optional[str]     # "mlb", "nba", None if no league resolved
    stage_key: Optional[str]       # Grid-specific key: "pennant", "division", ...
    stage_label: Optional[str]     # Display label (from LeagueConfig.columns)
    stage_order: Optional[int]     # Sort order within the grid

    @classmethod
    def empty(cls) -> "MarketClassification":
        return cls(None, None, None, None)


# ---------------------------------------------------------------------------
# Gender filtering (shared with the grid builder)
# ---------------------------------------------------------------------------

_WOMENS_RE = re.compile(r"\bWomen.?s\b|\bWNCAA\b|\bWNCAAB\b|\(W\)", re.IGNORECASE)
_MENS_RE = re.compile(r"\bMen.?s\b", re.IGNORECASE)

_MENS_LEAGUES = frozenset({
    "ncaa-basketball", "ncaa-football", "nba", "nhl", "nfl", "mlb",
})
_WOMENS_LEAGUES = frozenset({
    "wnba", "ncaa-women-basketball",
})


def _gender_filter_passes(config: LeagueConfig, name: str) -> bool:
    """Reject women's markets from men's leagues and vice versa."""
    if config.slug in _MENS_LEAGUES and _WOMENS_RE.search(name):
        return False
    if (config.slug in _WOMENS_LEAGUES
            and _MENS_RE.search(name)
            and not _WOMENS_RE.search(name)):
        return False
    return True


# ---------------------------------------------------------------------------
# League resolution
# ---------------------------------------------------------------------------


def resolve_league_config(
    market_name: str,
    external_id: Optional[str] = None,
    llm_sport_category: Optional[str] = None,
) -> Optional[LeagueConfig]:
    """Match a futures market to its ``LeagueConfig``, or None if no league.

    Resolution order mirrors the filtering logic in ``playoffs.py``:

    1. External ID starts with one of the league's ``sport_keys`` (Odds API).
    2. External ID starts with one of the league's ``external_id_prefixes``
       (Kalshi tickers like ``KXMARMADROUND``).
    3. Market name matches one of the league's ``league_name_patterns``.

    A gender filter rejects women's markets from men's leagues and vice
    versa. When ``llm_sport_category`` is known, leagues in a different
    category are skipped.
    """
    name = market_name or ""
    eid = external_id or ""
    eid_lower = eid.lower()

    for config in LEAGUE_CONFIGS.values():
        # Sport category hint: skip leagues that definitely don't match.
        # Only enforce when llm_sport_category is known AND differs —
        # allow unknown/None through so name-based resolution still works.
        if (llm_sport_category
                and config.sport_category
                and llm_sport_category != config.sport_category):
            continue

        if not _gender_filter_passes(config, name):
            continue

        # 1. Odds API sport_key prefix
        if eid_lower and any(
            eid_lower.startswith(sk.lower()) for sk in config.sport_keys
        ):
            return config

        # 2. Kalshi ticker prefix
        if eid and config.external_id_prefixes:
            if any(eid.startswith(pfx) for pfx in config.external_id_prefixes):
                return config

        # 3. League name patterns in the market name
        if config.league_name_patterns and name:
            for pat in config.league_name_patterns:
                if re.search(pat, name, re.IGNORECASE):
                    return config

    return None


# ---------------------------------------------------------------------------
# Core classification (delegates to LeagueConfig matching rules)
# ---------------------------------------------------------------------------


def classify_in_league(
    name: str,
    external_id: Optional[str],
    market_tier: Optional[int],
    config: LeagueConfig,
) -> Optional[str]:
    """Return the grid column key for a market known to belong to ``config``.

    Applies the same rule ordering the grid builder uses: tier-matched
    rules (with name-pattern gating) take precedence, then name patterns,
    then the ``tournament_stages`` fallback scoped to the league's columns.
    """
    # 1. LeagueConfig matching rules
    for rule in config.matching_rules:
        # Tier match — only accept when a name pattern also matches (to
        # prevent false positives from generic tier classification).
        if rule.tier is not None and market_tier == rule.tier:
            if any(c.key == rule.column for c in config.columns):
                if rule.name_patterns:
                    for pat in rule.name_patterns:
                        if re.search(pat, name, re.IGNORECASE):
                            return rule.column
                else:
                    return rule.column

        # Name pattern match (regardless of tier)
        for pat in rule.name_patterns:
            if re.search(pat, name, re.IGNORECASE):
                return rule.column

    # 2. tournament_stages fallback (scoped to the league's columns)
    stages = get_stages_for_sport(config.sport_category, league=None)
    if stages:
        stage_key = classify_market_stage(
            market_name=name,
            external_id=external_id,
            market_tier=None,  # Name-pattern gating already applied above
            stages=stages,
        )
        if stage_key and any(c.key == stage_key for c in config.columns):
            return stage_key

    return None


def classify_market(
    name: str,
    external_id: Optional[str] = None,
    market_tier: Optional[int] = None,
    llm_sport_category: Optional[str] = None,
) -> MarketClassification:
    """Classify a futures market.

    Returns a :class:`MarketClassification` with the resolved league and
    the grid-specific stage key (e.g. ``"pennant"`` for MLB), along with
    the display label and sort order from the ``LeagueConfig`` column.
    """
    config = resolve_league_config(name, external_id, llm_sport_category)
    if not config:
        return MarketClassification.empty()

    stage_key = classify_in_league(name, external_id, market_tier, config)
    if not stage_key:
        return MarketClassification(config.slug, None, None, None)

    col = next((c for c in config.columns if c.key == stage_key), None)
    return MarketClassification(
        league_slug=config.slug,
        stage_key=stage_key,
        stage_label=col.label if col else stage_key,
        stage_order=col.order if col else None,
    )


# ---------------------------------------------------------------------------
# Generic fallback (used when no LeagueConfig resolves)
# ---------------------------------------------------------------------------
# Sport-agnostic rules, ordered most-specific → least-specific. Division
# is checked BEFORE conference so "NFC East" / "AL East" / "American
# League Central" resolve to division rather than being captured by the
# conference rule. This is the same bug class the per-league classifier
# fixes; repeating it here keeps the long tail (tennis, international
# soccer, esports, markets without a configured LeagueConfig) correct.

_GENERIC_STAGE_RULES: list[tuple[re.Pattern, str, int]] = [
    # #1 Seed / Best Record — checked first; most specific regular-season
    # rank markets that must not fall through to "conference".
    (re.compile(r"#1\s+seed|top\s+seed|first\s+seed|best\s+record", re.I),
     "top_seed", 6),

    # Play-In (NBA) — specific wording, checked before conference so
    # "Play-In Tournament" doesn't get confused with anything else.
    (re.compile(r"play[- ]?in", re.I), "play_in", 2),

    # Division (checked BEFORE conference). Literal "division" plus the
    # sport-specific team-league+region forms that silently misclassified
    # as conference in the old rule order.
    (re.compile(
        r"\bdivision\b"
        r"|\b(?:afc|nfc)\s+(?:east|north|south|west)\b"            # NFL
        r"|\b(?:al|nl)\s+(?:east|central|west)\b"                  # MLB
        r"|\b(?:american|national)\s+league\s+(?:east|central|west)\b"  # MLB spelled
        r"|\batlantic\b|\bmetropolitan\b|\bcentral\s+division\b|\bpacific\s+division\b",  # NHL
        re.I,
    ), "division", 3),

    # Conference / pennant. MLB pennant collapses to "conference" here
    # because RelatedFutures uses a sport-agnostic taxonomy where the
    # penultimate round is always "conference" (order 4).
    (re.compile(
        r"\bconference\b"
        r"|\beastern\b|\bwestern\b"
        r"|\bafc\b|\bnfc\b"
        r"|american\s+league|national\s+league"
        r"|\bAL\b\s+champ|\bNL\b\s+champ",
        re.I,
    ), "conference", 4),

    # Championship (broadest — checked near last to avoid stealing from
    # division/conference/pennant markets that also contain "champion").
    (re.compile(
        r"championship|champion|title|finals"
        r"|world\s+series|super\s+bowl|stanley\s+cup",
        re.I,
    ), "championship", 5),

    # Make Playoffs — broadest; includes "postseason" vocabulary.
    (re.compile(
        r"make\s+playoffs|make\s+(?:the\s+)?postseason"
        r"|playoff\s+berth|playoff\s+qualifiers"
        r"|postseason\s+(?:berth|qualif)"
        r"|playoffs$",
        re.I,
    ), "playoffs", 1),
]


def classify_generic(text: str) -> tuple[Optional[str], Optional[int]]:
    """Sport-agnostic fallback classification.

    Returns ``(stage_type, stage_order)`` or ``(None, None)``. Used by
    ``compute_playoff_stage`` when no ``LeagueConfig`` resolves for the
    market (long-tail sports / markets missing metadata).
    """
    if not text:
        return None, None
    lowered = text.lower()
    for pattern, stage_type, order in _GENERIC_STAGE_RULES:
        if pattern.search(lowered):
            return stage_type, order
    return None, None


# ---------------------------------------------------------------------------
# Grid stage key → RelatedFutures generic stage type mapping
# ---------------------------------------------------------------------------
# The grid uses sport-specific stage keys ("pennant" for MLB, "conference"
# for NBA/NHL/NFL); RelatedFutures uses a sport-agnostic taxonomy where
# both collapse into "conference" so the generic UI treats them the same.
# Order numbers align with ``_GENERIC_STAGE_RULES`` above.

_GRID_TO_RELATED_FUTURES: dict[str, tuple[str, int]] = {
    # Team sports (common)
    "make_playoffs": ("playoffs", 1),
    "play_in":       ("play_in", 2),
    "division":      ("division", 3),
    "conference":    ("conference", 4),
    "pennant":       ("conference", 4),   # MLB pennant == generic conference
    "championship":  ("championship", 5),

    # NCAA men's bracket
    "round_of_32":   ("playoffs", 1),
    "sweet_16":      ("playoffs", 1),
    "elite_eight":   ("division", 3),
    "final_four":    ("conference", 4),
    "title_game":    ("championship", 5),

    # NCAA football
    "quarterfinal":  ("division", 3),
    "semifinal":     ("conference", 4),

    # European soccer league-position grids
    "top_4":         ("division", 3),
    "relegation":    ("playoffs", 1),

    # Champions League / cup knockouts
    "final":         ("championship", 5),
    "make_final":    ("conference", 4),
    "group_stage":   ("playoffs", 1),

    # Golf
    "win":           ("championship", 5),
    "top_5":         ("championship", 5),
    "top_10":        ("conference", 4),
    "top_20":        ("division", 3),
    "make_cut":      ("playoffs", 1),
}


def to_related_futures_stage(
    stage_key: Optional[str],
) -> tuple[Optional[str], Optional[int]]:
    """Map a grid stage key to the RelatedFutures generic (type, order)."""
    if not stage_key:
        return None, None
    return _GRID_TO_RELATED_FUTURES.get(stage_key, (None, None))
