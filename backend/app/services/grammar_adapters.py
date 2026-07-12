"""A2 (#1021) — Grammar adapters v1 (Layer 1 of the universal-matching plan).

Plan of record: ``.claude/handoff/strategy_universal_matching_and_surfaces.md``.

**Doctrine: adapters supply GRAMMAR; one ENGINE owns matching (A4); the AUDIT
owns truth (A6); the SENTINEL files gaps (A7).** This module is the grammar
layer. Each source gets ONE deterministic adapter that reads a market's native
shape and emits a :class:`MarketAnnotation`:

    entity mentions  +  market-type  +  line/threshold

confidence-tagged with source provenance. Adapters do NO matching — they never
touch the DB and never resolve a mention to an entity. A4's resolution engine
consumes these annotations and calls ``entity_registry.resolve_alias`` to turn a
:class:`EntityMention` into an :class:`~app.models.models.Entity`.

The three adapters:

* :func:`annotate_kalshi` — ticker/series grammar (KX* families; game tickers →
  team/person participants, series prefixes → competition/concept, threshold
  outcomes → line + direction per gotcha #17).
* :func:`annotate_polymarket` — event / negrisk structure (gotcha #18: nested
  sub-markets by ``condition_id``; ``group_item_title`` or the "Will X win…" →
  "X" question grammar → outcome mentions).
* :func:`annotate_odds_api` — structured h2h/spreads/totals + outrights mapper
  (team names live directly in ``outcome["name"]``; the line is ``point``).

Every mention's ``norm`` is produced by ``entity_registry.normalize_alias`` — the
SAME normalizer the A1 seed and read path use. That identity is load-bearing: a
mention normalized differently from an alias would never resolve. All three
adapters route through :func:`annotate` (the dispatcher) and, for measuring
coverage over already-stored rows, :func:`annotate_stored_market`.

A2 lands the grammar + tests against the A1 models; the ``market_entities``
write-hook (persisting these annotations at ingest time) is deferred to when A1
is deployed (per Queue #161 Item 1 — A1 is committed but held at push:review).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

from app.services.entity_registry import (
    ALIAS_ABBREVIATION,
    ALIAS_SOURCE_NAME,
    ALIAS_TICKER_TOKEN,
    KIND_COMPETITION,
    KIND_EVENT_CONCEPT,
    KIND_PERSON,
    KIND_TEAM,
    normalize_alias,
)
from app.utils.futures_categorization import detect_market_type
from app.utils.prediction_market_matching import (
    extract_matchup,
    extract_teams_from_ticker,
    extract_ticker_fragments,
)
from app.utils.sport_keys import (
    get_sport_key_from_ticker,
    is_kalshi_game_ticker,
)

# A mention with an unknown kind is still a mention (it satisfies the ≥1-mention
# acceptance bar and A4 can resolve it by alias regardless of kind). We only tag
# a kind when the grammar is confident.
KIND_UNKNOWN = "unknown"

# Roles describe WHAT the mention is to the market, so A4 can weight a signature.
ROLE_PARTICIPANT = "participant"   # a competitor in the market (team/fighter/player)
ROLE_OUTCOME = "outcome"           # a selectable outcome (nominee, championship pick)
ROLE_COMPETITION = "competition"   # the league/tour/promotion the market sits in
ROLE_CONCEPT = "concept"           # the event-concept (tournament/card/ceremony)

# Line direction (gotcha #17: a Kalshi threshold outcome is the OVER side unless
# it explicitly says Under/No).
DIR_OVER = "over"
DIR_UNDER = "under"

# Individual (non-team) sports — participants/outcomes are PEOPLE, not teams.
_INDIVIDUAL_SPORT_KEYS = {
    "golf",
    "tennis",
    "mma",
    "boxing",
    "athletics",
    "cycling",
    "motorsport",
    "formula1",
    "nascar",
    "swimming",
}
_INDIVIDUAL_SPORT_PREFIXES = ("golf", "tennis", "mma", "atp", "wta", "ufc", "pga", "liv")

# Numeric threshold in an outcome/label, e.g. "33°F or below", "Over 220.5",
# "220+ points", "wins 10 or more games". Captures the number.
_NUMBER_RE = re.compile(r"(-?\d+(?:\.\d+)?)")
_UNDER_PREFIX_RE = re.compile(r"^\s*(?:under|no|below|less|fewer|at most|<=?)\b", re.I)
_OVER_HINT_RE = re.compile(r"\b(?:over|above|more|at least|greater|>=?)\b", re.I)
_UNDER_HINT_RE = re.compile(r"\b(?:under|below|less|fewer|at most|or fewer|or less)\b", re.I)
_OU_RE = re.compile(r"\bo/?u\b|\bover/under\b", re.I)

# Polymarket "Will X win…" / "X to win…" outcome grammar (mirrors the ingest-time
# _extract_outcome_name in tasks/polymarket.py; reimplemented here so the grammar
# layer never imports a Celery task module).
_WILL_X_RE = re.compile(
    r"^will\s+(?:the\s+)?(.+?)\s+(?:win|be|become|make|reach|qualify|finish)\b",
    re.I,
)
_X_TO_WIN_RE = re.compile(r"^(.+?)\s+to\s+(?:win|be|become|make|reach)\b", re.I)
# Trailing "(Lightweight, Main Card)" / "(M)" style qualifiers on Poly names.
_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


@dataclass(frozen=True)
class EntityMention:
    """A single entity reference the grammar found in a market.

    ``text`` is the raw string as it appeared; ``norm`` is
    ``entity_registry.normalize_alias(text)`` — the key A4 resolves against.
    ``alias_type`` is the hint A4 uses when it wants to record this mention as an
    :class:`~app.models.models.EntityAlias` (source_name / ticker_token / …).
    """

    text: str
    norm: str
    kind: str
    role: str
    source: str
    alias_type: str
    confidence: float

    @classmethod
    def make(
        cls,
        text: str,
        *,
        kind: str,
        role: str,
        source: str,
        alias_type: str = ALIAS_SOURCE_NAME,
        confidence: float = 0.8,
    ) -> Optional["EntityMention"]:
        """Build a mention, or ``None`` if ``text`` normalizes to nothing."""
        norm = normalize_alias(text)
        if not norm:
            return None
        return cls(
            text=text.strip()[:300],
            norm=norm[:300],
            kind=kind,
            role=role,
            source=source,
            alias_type=alias_type,
            confidence=confidence,
        )


@dataclass(frozen=True)
class MarketAnnotation:
    """The grammar layer's output for one market — mentions + type + line.

    ``unparsed`` (no mentions produced) is the A7 sentinel's food: a market shape
    we could not read at all. ``notes`` carries diagnostics for the same tier.
    """

    source: str
    market_type: Optional[str] = None
    line: Optional[float] = None
    line_direction: Optional[str] = None
    competition: Optional[str] = None          # sport_key / league, if derivable
    concept_ref: Optional[str] = None          # series ticker / poly event id anchor
    mentions: tuple[EntityMention, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def unparsed(self) -> bool:
        return not self.mentions

    def mention_texts(self) -> list[str]:
        return [m.text for m in self.mentions]


def _dedupe(mentions: Iterable[Optional[EntityMention]]) -> tuple[EntityMention, ...]:
    """Drop ``None`` and collapse duplicate (norm, role, kind) mentions, keeping
    the highest-confidence one so a team seen in both ticker and title counts once.
    """
    best: dict[tuple[str, str, str], EntityMention] = {}
    for m in mentions:
        if m is None:
            continue
        key = (m.norm, m.role, m.kind)
        cur = best.get(key)
        if cur is None or m.confidence > cur.confidence:
            best[key] = m
    return tuple(best.values())


def _kind_for_sport(sport_key: Optional[str]) -> str:
    """Team vs person heuristic from a sport key. Unknown → ``KIND_UNKNOWN``."""
    if not sport_key:
        return KIND_UNKNOWN
    sk = sport_key.lower()
    if sk in _INDIVIDUAL_SPORT_KEYS:
        return KIND_PERSON
    if any(sk.startswith(p) or p in sk for p in _INDIVIDUAL_SPORT_PREFIXES):
        return KIND_PERSON
    # Recognized team-sport families.
    if any(
        t in sk
        for t in ("basketball", "baseball", "hockey", "football", "soccer", "nba",
                  "nfl", "mlb", "nhl", "epl", "ncaa", "wnba", "mls")
    ):
        return KIND_TEAM
    return KIND_UNKNOWN


def _extract_line(label: str | None) -> tuple[Optional[float], Optional[str]]:
    """Pull a numeric line + direction from a threshold/total label.

    gotcha #17: a Kalshi threshold outcome is the OVER side unless it explicitly
    says Under/No/below. Returns ``(None, None)`` when there is no number.
    """
    if not label:
        return None, None
    m = _NUMBER_RE.search(label)
    if not m:
        return None, None
    try:
        value = float(m.group(1))
    except ValueError:
        return None, None
    if _UNDER_PREFIX_RE.match(label) or _UNDER_HINT_RE.search(label):
        return value, DIR_UNDER
    if _OVER_HINT_RE.search(label):
        return value, DIR_OVER
    # Bare threshold with a number but no explicit direction → OVER (gotcha #17).
    return value, DIR_OVER


def _clean_person_name(name: str) -> str:
    """Strip trailing "(Lightweight, Main Card)"-style qualifiers from a name."""
    return _TRAILING_PAREN_RE.sub("", name or "").strip()


# ---------------------------------------------------------------------------
# Kalshi
# ---------------------------------------------------------------------------
_VS_SPLIT_RE = re.compile(r"\s+(?:vs\.?|v\.?|versus|@|at)\s+", re.I)


def _split_vs(title: str) -> Optional[tuple[str, str]]:
    """Split "Oliveira vs. Holloway" / "USA at Canada" into two participants."""
    if not title:
        return None
    parts = _VS_SPLIT_RE.split(title, maxsplit=1)
    if len(parts) == 2:
        a = _clean_person_name(parts[0])
        b = _clean_person_name(parts[1].split(":")[0])  # drop trailing ": Method"
        if a and b:
            return a, b
    return None


def annotate_kalshi(
    *,
    event_ticker: str,
    title: str = "",
    subtitle: Optional[str] = None,
    category: Optional[str] = None,
    markets: Optional[Sequence[dict]] = None,
) -> MarketAnnotation:
    """Annotate a Kalshi event (one ``FuturesMarket``) from its ticker + markets.

    ``markets`` is a list of the nested Kalshi market dicts (keys ``ticker``,
    ``yes_sub_title``, ``no_sub_title``, ``title``, ``subtitle``). The event maps
    1:1 to a ``FuturesMarket``; each nested market maps to a ``FuturesOutcome``.
    """
    markets = markets or []
    notes: list[str] = []
    mentions: list[Optional[EntityMention]] = []

    sport_key = get_sport_key_from_ticker(event_ticker)
    is_game = is_kalshi_game_ticker(event_ticker)
    ticker_prefix = _kalshi_prefix(event_ticker)
    competition = sport_key

    if is_game:
        market_type = "game"
        kind = _kind_for_sport(sport_key)
        # 1) Team abbreviations encoded in the ticker (best signal for team sports).
        teams = extract_teams_from_ticker(event_ticker)
        if teams:
            for name in teams:
                mentions.append(
                    EntityMention.make(
                        name,
                        kind=KIND_TEAM,
                        role=ROLE_PARTICIPANT,
                        source="kalshi",
                        alias_type=ALIAS_ABBREVIATION,
                        confidence=0.9,
                    )
                )
        else:
            # 1b) College/other with no abbrev map: raw ticker fragments (low conf).
            frags = extract_ticker_fragments(event_ticker)
            if frags:
                for token in frags[:2]:
                    mentions.append(
                        EntityMention.make(
                            token,
                            kind=KIND_TEAM,
                            role=ROLE_PARTICIPANT,
                            source="kalshi",
                            alias_type=ALIAS_TICKER_TOKEN,
                            confidence=0.5,
                        )
                    )
        # 2) UFC/tennis fights carry participants in the TITLE, not the ticker.
        if not teams:
            vs = _split_vs(title)
            if vs:
                pkind = KIND_PERSON if kind in (KIND_PERSON, KIND_UNKNOWN) else kind
                for name in vs:
                    mentions.append(
                        EntityMention.make(
                            name,
                            kind=pkind,
                            role=ROLE_PARTICIPANT,
                            source="kalshi",
                            alias_type=ALIAS_SOURCE_NAME,
                            confidence=0.8,
                        )
                    )
        # 3) Sub-market outcome labels (yes/no sub_title) — round/method/distance
        #    props carry the participant or a threshold.
        line, direction = _kalshi_scan_markets(markets, mentions, sport_key, is_game=True)
        # Prop sub-type refines game → e.g. mof/rounds/distance from ticker.
        prop_type = _kalshi_prop_type(ticker_prefix)
        if prop_type:
            market_type = prop_type
    else:
        # Futures / season / awards: series prefix → competition + concept.
        market_type = detect_market_type(title or subtitle or event_ticker)
        if sport_key:
            mentions.append(
                EntityMention.make(
                    sport_key,
                    kind=KIND_COMPETITION,
                    role=ROLE_COMPETITION,
                    source="kalshi",
                    alias_type=ALIAS_SOURCE_NAME,
                    confidence=0.7,
                )
            )
        # The event title is the concept anchor (e.g. "PGA Championship Winner").
        if title:
            mentions.append(
                EntityMention.make(
                    title,
                    kind=KIND_EVENT_CONCEPT,
                    role=ROLE_CONCEPT,
                    source="kalshi",
                    alias_type=ALIAS_SOURCE_NAME,
                    confidence=0.6,
                )
            )
        line, direction = _kalshi_scan_markets(markets, mentions, sport_key, is_game=False)

    if sport_key is None:
        notes.append(f"unknown_ticker_prefix:{ticker_prefix}")

    deduped = _dedupe(mentions)
    if not deduped:
        notes.append("kalshi:no_mentions")

    return MarketAnnotation(
        source="kalshi",
        market_type=market_type,
        line=line,
        line_direction=direction,
        competition=competition,
        concept_ref=event_ticker,
        mentions=deduped,
        notes=tuple(notes),
    )


def _kalshi_prefix(event_ticker: str) -> str:
    return (event_ticker or "").split("-", 1)[0].lower()


def _kalshi_prop_type(prefix: str) -> Optional[str]:
    """Refine a game ticker prefix into a prop market-type where recognizable."""
    mapping = {
        "kxufcmof": "method_of_victory",
        "kxufcmov": "method_of_victory",
        "kxufcrounds": "rounds",
        "kxufcvicround": "round_of_victory",
        "kxufcdistance": "distance",
        "kxatpsetwinner": "set_winner",
        "kxatpgamespread": "spread",
    }
    return mapping.get(prefix)


def _kalshi_scan_markets(
    markets: Sequence[dict],
    mentions: list[Optional[EntityMention]],
    sport_key: Optional[str],
    *,
    is_game: bool,
) -> tuple[Optional[float], Optional[str]]:
    """Scan nested Kalshi markets for outcome mentions + the first line found."""
    line: Optional[float] = None
    direction: Optional[str] = None
    outcome_kind = _kind_for_sport(sport_key)
    for mkt in markets:
        label = (
            mkt.get("yes_sub_title")
            or mkt.get("subtitle")
            or mkt.get("title")
            or ""
        )
        if not label:
            continue
        # A threshold label ("33 or above") yields a line, not an entity.
        cand_line, cand_dir = _extract_line(label)
        if cand_line is not None and line is None:
            line, direction = cand_line, cand_dir
        # Only treat as an entity mention if it isn't a pure Yes/No/threshold.
        stripped = label.strip().lower()
        if stripped in ("yes", "no") or cand_line is not None:
            continue
        mentions.append(
            EntityMention.make(
                label,
                kind=outcome_kind if not is_game else _kind_for_sport(sport_key),
                role=ROLE_OUTCOME if not is_game else ROLE_PARTICIPANT,
                source="kalshi",
                alias_type=ALIAS_SOURCE_NAME,
                confidence=0.75,
            )
        )
    return line, direction


# ---------------------------------------------------------------------------
# Polymarket
# ---------------------------------------------------------------------------
def _poly_outcome_name(question: str, event_title: str = "") -> str:
    """"Will the Lakers win…?" → "Lakers"; "X to win…" → "X"; else the question."""
    if not question:
        return ""
    m = _WILL_X_RE.match(question)
    if m:
        return _clean_person_name(m.group(1))
    m = _X_TO_WIN_RE.match(question)
    if m:
        return _clean_person_name(m.group(1))
    cleaned = question.rstrip("?").strip()
    return cleaned if len(cleaned) <= 60 else cleaned[:60]


def annotate_polymarket(
    *,
    event_id: str,
    title: str = "",
    tags: Optional[Sequence[str]] = None,
    neg_risk: bool = False,
    markets: Optional[Sequence[dict]] = None,
) -> MarketAnnotation:
    """Annotate a Polymarket event (gotcha #18: nested sub-markets).

    ``markets`` is the list of sub-market dicts (keys ``condition_id``,
    ``question``, ``group_item_title``, ``outcomes``, ``neg_risk``). A negrisk
    multi-market event is one question with candidate sub-markets; a game event is
    separate sub-markets; a single market is one binary.
    """
    markets = markets or []
    tags = tags or []
    notes: list[str] = []
    mentions: list[Optional[EntityMention]] = []
    line: Optional[float] = None
    direction: Optional[str] = None

    # Event title is the concept; tags hint the competition.
    if title:
        mentions.append(
            EntityMention.make(
                title,
                kind=KIND_EVENT_CONCEPT,
                role=ROLE_CONCEPT,
                source="polymarket",
                alias_type=ALIAS_SOURCE_NAME,
                confidence=0.55,
            )
        )
    competition = None
    for tag in tags:
        if not isinstance(tag, str):
            continue
        t = tag.strip()
        if not t or t.lower() in ("sports", "all", "trending"):
            continue
        competition = competition or t
        mentions.append(
            EntityMention.make(
                t,
                kind=KIND_COMPETITION,
                role=ROLE_COMPETITION,
                source="polymarket",
                alias_type=ALIAS_SOURCE_NAME,
                confidence=0.5,
            )
        )

    # 1) Game-shaped: the title is a "Team A vs Team B" matchup.
    matchup = extract_matchup(title)
    if matchup:
        for name in (matchup.team_a, matchup.team_b):
            if name:
                mentions.append(
                    EntityMention.make(
                        name,
                        kind=KIND_UNKNOWN,
                        role=ROLE_PARTICIPANT,
                        source="polymarket",
                        alias_type=ALIAS_SOURCE_NAME,
                        confidence=0.8,
                    )
                )
        market_type = "game"
    else:
        market_type = detect_market_type(title)

    # 2) Decompose sub-markets → outcome mentions.
    for mkt in markets:
        gi = mkt.get("group_item_title")
        question = mkt.get("question") or ""
        name = gi or _poly_outcome_name(question, title)
        if not name:
            continue
        cand_line, cand_dir = _extract_line(name if gi else question)
        if cand_line is not None and line is None:
            line, direction = cand_line, cand_dir
        if _OU_RE.search(question) and line is None:
            _l, _d = _extract_line(question)
            line, direction = _l, _d
        if name.strip().lower() in ("yes", "no"):
            continue
        # A pure threshold label ("33°F or below") is a line, not an entity, but
        # keep it as a low-confidence outcome mention so the market isn't unparsed.
        mentions.append(
            EntityMention.make(
                name,
                kind=KIND_UNKNOWN,
                role=ROLE_OUTCOME,
                source="polymarket",
                alias_type=ALIAS_SOURCE_NAME,
                confidence=0.7 if cand_line is None else 0.4,
            )
        )

    if neg_risk and not any(m and m.role == ROLE_OUTCOME for m in mentions):
        notes.append("polymarket:negrisk_no_outcomes")

    deduped = _dedupe(mentions)
    if not deduped:
        notes.append("polymarket:no_mentions")

    return MarketAnnotation(
        source="polymarket",
        market_type=market_type,
        line=line,
        line_direction=direction,
        competition=competition,
        concept_ref=str(event_id) if event_id else None,
        mentions=deduped,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Odds API
# ---------------------------------------------------------------------------
# Odds API market keys → our market-type vocabulary.
_ODDS_MARKET_TYPE = {
    "h2h": "moneyline",
    "spreads": "spread",
    "totals": "total",
    "outrights": "championship",
}


def annotate_odds_api(
    *,
    sport_key: Optional[str] = None,
    home_team: Optional[str] = None,
    away_team: Optional[str] = None,
    market_key: str = "h2h",
    point: Optional[float] = None,
    outcomes: Optional[Sequence[Any]] = None,
) -> MarketAnnotation:
    """Annotate an Odds API market — the easy one: entities are named directly.

    Two shapes:

    * **Game** (``h2h``/``spreads``/``totals``): pass ``home_team`` + ``away_team``
      (and ``point`` for spreads/totals). Team names ARE the entities.
    * **Outright/futures** (``outrights``): pass ``outcomes`` — a list of outcome
      names (or dicts with a ``name`` key). Each name is an entity.
    """
    notes: list[str] = []
    mentions: list[Optional[EntityMention]] = []
    market_type = _ODDS_MARKET_TYPE.get(market_key, market_key)
    kind = _kind_for_sport(sport_key)
    direction = None
    line = point

    if home_team or away_team:
        for name in (home_team, away_team):
            if name:
                mentions.append(
                    EntityMention.make(
                        name,
                        kind=KIND_TEAM if kind == KIND_UNKNOWN else kind,
                        role=ROLE_PARTICIPANT,
                        source="odds_api",
                        alias_type=ALIAS_SOURCE_NAME,
                        confidence=0.95,
                    )
                )

    for oc in outcomes or []:
        name = oc.get("name") if isinstance(oc, dict) else oc
        if not name or str(name).strip().lower() in ("over", "under", "yes", "no"):
            # Over/Under are line directions, not entities.
            if isinstance(name, str) and name.strip().lower() in ("over", "under"):
                direction = name.strip().lower()
                if isinstance(oc, dict) and oc.get("point") is not None and line is None:
                    line = oc.get("point")
            continue
        mentions.append(
            EntityMention.make(
                str(name),
                kind=kind if kind != KIND_UNKNOWN else KIND_TEAM,
                role=ROLE_OUTCOME,
                source="odds_api",
                alias_type=ALIAS_SOURCE_NAME,
                confidence=0.9,
            )
        )

    deduped = _dedupe(mentions)
    if not deduped:
        notes.append("odds_api:no_mentions")

    return MarketAnnotation(
        source="odds_api",
        market_type=market_type,
        line=line,
        line_direction=direction,
        competition=sport_key,
        mentions=deduped,
        notes=tuple(notes),
    )


# ---------------------------------------------------------------------------
# Dispatcher + stored-row measurement path
# ---------------------------------------------------------------------------
def annotate(source: str, payload: dict) -> MarketAnnotation:
    """Dispatch to the right adapter by source. ``payload`` mirrors that
    adapter's keyword arguments (a dict so callers can pass source-native dicts).
    """
    src = (source or "").lower()
    if src == "kalshi":
        return annotate_kalshi(**payload)
    if src == "polymarket":
        return annotate_polymarket(**payload)
    if src == "odds_api":
        return annotate_odds_api(**payload)
    return MarketAnnotation(source=src, notes=(f"unknown_source:{source}",))


def annotate_stored_market(
    *,
    source: str,
    external_id: str,
    name: str = "",
    category: Optional[str] = None,
    market_metadata: Optional[dict] = None,
    outcome_names: Optional[Sequence[str]] = None,
) -> MarketAnnotation:
    """Best-effort annotation of an ALREADY-STORED ``FuturesMarket`` row.

    The raw source payload is not persisted, so this reconstructs the adapter
    input from the stored scalar fields (``external_id``, ``name``, outcome
    names). It is the measurement path for the A2 acceptance bar ("% of new
    ingests with ≥1 mention") until the ingest-time write-hook lands. Prefer the
    native adapters at ingest time where the full payload is still in hand.
    """
    md = market_metadata or {}
    ocs = list(outcome_names or [])
    src = (source or "").lower()

    if src == "kalshi":
        ticker = md.get("kalshi_event_ticker") or external_id
        markets = [{"yes_sub_title": oc} for oc in ocs]
        return annotate_kalshi(event_ticker=ticker, title=name, markets=markets)
    if src == "polymarket":
        event_id = md.get("polymarket_event_id") or external_id
        neg = bool(md.get("neg_risk"))
        markets = [{"group_item_title": oc} for oc in ocs]
        return annotate_polymarket(
            event_id=event_id, title=name, neg_risk=neg, markets=markets
        )
    if src == "odds_api":
        return annotate_odds_api(
            sport_key=external_id, market_key="outrights", outcomes=ocs
        )
    return MarketAnnotation(source=src, notes=(f"unknown_source:{source}",))


def coverage(annotations: Iterable[MarketAnnotation]) -> dict[str, float]:
    """Coverage stats for the A2 acceptance bar / interim scoreboard.

    Returns ``total``, ``with_mention``, ``rate`` (fraction with ≥1 mention),
    ``with_market_type``, and ``with_line``.
    """
    total = with_mention = with_type = with_line = 0
    for ann in annotations:
        total += 1
        if ann.mentions:
            with_mention += 1
        if ann.market_type:
            with_type += 1
        if ann.line is not None:
            with_line += 1
    rate = (with_mention / total) if total else 0.0
    return {
        "total": total,
        "with_mention": with_mention,
        "rate": rate,
        "with_market_type": with_type,
        "with_line": with_line,
    }
