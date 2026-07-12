"""A4 (#1023) — Resolution engine v1 (Layer 2 of the universal-matching plan).

Plan of record: ``.claude/handoff/strategy_universal_matching_and_surfaces.md``.

**Doctrine: adapters supply GRAMMAR (A2); ONE engine owns matching (here); the
AUDIT owns truth (A6); the SENTINEL files gaps (A7).** This module is that one
engine. It never contains per-sport matching logic — a new sport/format gets a
grammar adapter, and the engine matches it via the same signature machinery.

## The signature
Every market becomes a :class:`MarketSignature` built from an A2
:class:`~app.services.grammar_adapters.MarketAnnotation` (mentions + market-type +
line) plus A1 entity resolution (a mention's ``norm`` → an :class:`Entity`, when
resolvable). A match is **entity-signature agreement**:

    participants  ∧  competition/concept  ∧  market-type  ∧  line/threshold  ∧  date-window

with the **L2-62 negative-case discipline**: a Challenger match must NEVER join
Wimbledon. That discipline is enforced structurally — participant sets must
*agree as sets* (event linkage) or a match's participants must be a *subset* of a
concept's entrant field (concept grouping); a shared date-window or competition is
never sufficient on its own.

## The strategy registry
Existing matching mechanisms become **strategies**, not per-sport code:

* :class:`TickerParticipantStrategy` — market→event: a game market's participant
  set equals an event's participant set within the date-window (absorbs the
  ticker-derived / matchup mechanisms in ``utils/prediction_market_matching``).
* :class:`EntrantSetStrategy` — market→concept: both of a match's participants are
  in a concept's entrant field (absorbs ``utils/event_matcher`` — L2-62).
* :class:`QuestionNormalizationStrategy` — cross-source pairs: two markets from
  different sources with agreeing normalized questions + market-type + line
  (absorbs ``utils/cross_source_matching``).
* :class:`ContainerStrategy` — family/dedup keys: markets sharing a source
  container (Polymarket event id / Kalshi series) collapse to one family key
  (absorbs group_id container inheritance).

## What it emits
One code path emits ALL four of the product's link types
(:data:`LINK_MARKET_EVENT`, :data:`LINK_MARKET_CONCEPT`, :data:`LINK_CROSS_SOURCE`,
:data:`LINK_FAMILY`) as :class:`ResolvedLink` records — each carrying the strategy,
a confidence, and the signature evidence.

**v1 is shadow-mode only.** The engine RESOLVES and REPORTS; it writes nothing.
Cutover per link-type happens (in later queues) only when the shadow-agreement
audit (``scripts/audit_resolution_engine.py``) proves the engine reproduces the
existing links with no regression against the 100% L1-L4 game matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Optional, Protocol, Sequence

from app.services.entity_registry import normalize_alias
from app.services.grammar_adapters import (
    MarketAnnotation,
    ROLE_CONCEPT,
    ROLE_COMPETITION,
    ROLE_OUTCOME,
    ROLE_PARTICIPANT,
)
from app.utils.event_matcher import player_key

# ---------------------------------------------------------------------------
# Link types — the four the product needs, emitted from this one place.
# ---------------------------------------------------------------------------
LINK_MARKET_EVENT = "market_event"      # a market → a game Event (the win-prob blend)
LINK_MARKET_CONCEPT = "market_concept"  # a market → an event-concept (tournament/card)
LINK_CROSS_SOURCE = "cross_source"      # two markets, different sources, same question
LINK_FAMILY = "family"                  # markets sharing a dedup/family key

# Default date-window for event linkage. Kalshi commence_time is often the close
# time, not the game start (gotcha #14), so the window is generous but finite —
# a shared window is NEVER sufficient alone (participants must also agree).
DEFAULT_DATE_WINDOW = timedelta(hours=28)


# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------
def _entity_key(norm: str, entity_id: Optional[int]) -> str:
    """A participant/outcome key: the resolved entity id when A1 resolved it,
    else the normalized-name fallback. Same-entity mentions from two sources
    collapse to the same key ONLY when both resolved to the same entity — the
    name fallback still matches teams because their aliases are their names."""
    return f"e:{entity_id}" if entity_id is not None else f"n:{norm}"


@dataclass(frozen=True)
class MarketSignature:
    """The engine's canonical view of one market — the thing it matches on.

    Built by :func:`build_signature` from an A2 annotation + optional A1
    resolution. ``participants`` / ``outcomes`` are frozensets of entity keys
    (see :func:`_entity_key`); ``surnames`` mirrors ``participants`` as
    entrant-set player keys for the L2-62 concept strategy.
    """

    source: str
    external_id: str
    market_type: Optional[str] = None
    competition: Optional[str] = None       # normalized sport_key / league
    concept_ref: Optional[str] = None       # source container anchor (series / poly event id)
    concept_norm: Optional[str] = None      # normalized concept name (for question matching)
    line: Optional[float] = None
    line_direction: Optional[str] = None
    event_date: Optional[date] = None
    participants: frozenset[str] = frozenset()
    outcomes: frozenset[str] = frozenset()
    surnames: frozenset[str] = frozenset()  # participant player-keys (entrant-set matching)
    question_norm: Optional[str] = None     # normalized question for cross-source pairing

    @property
    def is_game(self) -> bool:
        """A game/match signature has exactly two participants."""
        return len(self.participants) == 2


def build_signature(
    annotation: MarketAnnotation,
    *,
    external_id: str,
    event_date: Optional[date] = None,
    resolved: Optional[dict[str, int]] = None,
    question: Optional[str] = None,
) -> MarketSignature:
    """Turn an A2 :class:`MarketAnnotation` into a :class:`MarketSignature`.

    ``resolved`` maps a mention's ``norm`` → an ``Entity.id`` (the A1 read path
    output); mentions absent from it fall back to their normalized name so a team
    still matches by alias. ``question`` is the raw market name used for the
    cross-source normalized-question key (defaults to the concept mention text).
    """
    resolved = resolved or {}
    participants: set[str] = set()
    outcomes: set[str] = set()
    surnames: set[str] = set()
    concept_norm: Optional[str] = None
    competition: Optional[str] = annotation.competition

    for m in annotation.mentions:
        key = _entity_key(m.norm, resolved.get(m.norm))
        if m.role == ROLE_PARTICIPANT:
            participants.add(key)
            pk = player_key(m.text)
            if pk:
                surnames.add(pk)
        elif m.role == ROLE_OUTCOME:
            outcomes.add(key)
        elif m.role == ROLE_CONCEPT and concept_norm is None:
            concept_norm = m.norm
        elif m.role == ROLE_COMPETITION and not competition:
            competition = m.norm

    q = question if question is not None else (concept_norm or "")
    return MarketSignature(
        source=(annotation.source or "").lower(),
        external_id=external_id,
        market_type=annotation.market_type,
        competition=normalize_alias(competition) if competition else None,
        concept_ref=annotation.concept_ref,
        concept_norm=concept_norm,
        line=annotation.line,
        line_direction=annotation.line_direction,
        event_date=event_date,
        participants=frozenset(participants),
        outcomes=frozenset(outcomes),
        surnames=frozenset(surnames),
        question_norm=normalize_question(q) if q else None,
    )


@dataclass(frozen=True)
class EventSignature:
    """A game Event as the engine sees it — participants + date + competition.

    ``participants`` are entity keys (same space as a market signature) so the
    ticker strategy compares them directly. Built by the caller from an Event's
    home/away team names (resolved through A1 where possible).
    """

    event_id: int
    participants: frozenset[str]
    event_date: Optional[date] = None
    competition: Optional[str] = None
    surnames: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ConceptSignature:
    """An event-concept (tournament/card/ceremony) with its entrant field.

    ``entrant_keys`` are player-keys (surnames) of the concept's field — the
    winner-field outcomes. The L2-62 strategy links a match iff BOTH its players
    are in this set. ``concept_ref`` is the concept's source anchor.
    """

    concept_ref: str
    entrant_keys: frozenset[str]
    competition: Optional[str] = None
    event_date: Optional[date] = None
    date_window_start: Optional[date] = None
    date_window_end: Optional[date] = None


@dataclass(frozen=True)
class ResolvedLink:
    """One link the engine emits. ``left`` is always the subject market's
    ``external_id``; ``right`` is the target (event id, concept ref, or the other
    market's external_id). Evidence records why the strategy fired."""

    link_type: str
    left: str
    right: str
    strategy: str
    confidence: float
    evidence: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agreement predicates — the signature algebra (pure).
# ---------------------------------------------------------------------------
def normalize_question(q: str) -> str:
    """Normalized question key for cross-source pairing (mirrors
    ``utils.cross_source_matching.normalize_question`` so the engine reproduces
    that mechanism's keys exactly)."""
    import re

    return re.sub(r"[^a-z0-9 ]+", "", (q or "").lower()).strip()


def participants_agree(a: frozenset[str], b: frozenset[str]) -> bool:
    """Two game signatures agree iff their participant sets are equal and
    non-empty. Set-equality (not overlap) is the negative-case discipline: a
    two-team market only links to the event with THOSE two teams."""
    return bool(a) and a == b


def line_agrees(
    a_line: Optional[float],
    a_dir: Optional[str],
    b_line: Optional[float],
    b_dir: Optional[str],
) -> bool:
    """Lines agree if both absent, or equal value with compatible direction.

    A missing direction is treated as compatible (grammar can't always read it);
    two *explicit opposite* directions (over vs under) never agree — gotcha #17's
    over/under sign is load-bearing for spreads/totals."""
    if a_line is None and b_line is None:
        return True
    if a_line is None or b_line is None:
        return False
    if abs(a_line - b_line) > 1e-6:
        return False
    if a_dir and b_dir and a_dir != b_dir:
        return False
    return True


def dates_within_window(
    a: Optional[date], b: Optional[date], window: timedelta = DEFAULT_DATE_WINDOW
) -> bool:
    """Date-window agreement. Two unknown dates don't block (a shared window is
    never sufficient on its own — participants carry the match); one known and
    one unknown is permissive; two known must be within ``window``."""
    if a is None or b is None:
        return True
    return abs((a - b).days) <= max(1, window.days)


def competition_agrees(a: Optional[str], b: Optional[str]) -> bool:
    """Competitions agree unless BOTH are known and differ. When both are known
    a mismatch blocks (an NBA market never links to an NHL event)."""
    if a and b:
        return a == b
    return True


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------
class Strategy(Protocol):
    """A resolution strategy proposes links for a subject signature against a
    universe. Strategies are pure and stateless; the registry runs them all."""

    name: str

    def propose(
        self, subject: MarketSignature, universe: "MatchUniverse"
    ) -> list[ResolvedLink]:  # pragma: no cover - protocol
        ...


@dataclass
class MatchUniverse:
    """The candidate space a subject signature is matched against."""

    events: Sequence[EventSignature] = ()
    concepts: Sequence[ConceptSignature] = ()
    markets: Sequence[MarketSignature] = ()


class TickerParticipantStrategy:
    """market→event via participant-set + date-window agreement.

    Absorbs the ticker-map / matchup-extraction mechanisms: A2 already turned a
    Kalshi ticker or a "A vs B" title into participant mentions, so this strategy
    is source-agnostic — it just compares participant sets to events."""

    name = "ticker_participant"

    def propose(self, subject: MarketSignature, universe: MatchUniverse) -> list[ResolvedLink]:
        if not subject.is_game:
            return []
        links: list[ResolvedLink] = []
        for ev in universe.events:
            if not participants_agree(subject.participants, ev.participants):
                continue
            if not competition_agrees(subject.competition, ev.competition):
                continue
            if not dates_within_window(subject.event_date, ev.event_date):
                continue
            links.append(
                ResolvedLink(
                    link_type=LINK_MARKET_EVENT,
                    left=subject.external_id,
                    right=str(ev.event_id),
                    strategy=self.name,
                    confidence=0.95,
                    evidence={
                        "participants": sorted(subject.participants),
                        "event_date": str(ev.event_date) if ev.event_date else None,
                    },
                )
            )
        return links


class EntrantSetStrategy:
    """market→concept via entrant-set overlap (L2-62 discipline).

    A match market joins a concept iff BOTH its player-keys are in the concept's
    entrant field. A concurrent Challenger match (players not in the field) never
    joins — this is the whole point of the negative-case discipline."""

    name = "entrant_set"

    def propose(self, subject: MarketSignature, universe: MatchUniverse) -> list[ResolvedLink]:
        players = subject.surnames
        if len(players) < 2:
            return []
        links: list[ResolvedLink] = []
        for concept in universe.concepts:
            if not concept.entrant_keys:
                continue
            if not competition_agrees(subject.competition, concept.competition):
                continue
            if not players <= concept.entrant_keys:
                continue
            links.append(
                ResolvedLink(
                    link_type=LINK_MARKET_CONCEPT,
                    left=subject.external_id,
                    right=concept.concept_ref,
                    strategy=self.name,
                    confidence=0.9,
                    evidence={"players": sorted(players)},
                )
            )
        return links


class QuestionNormalizationStrategy:
    """cross-source pairs via normalized-question + market-type + line agreement.

    Two markets from DIFFERENT sources pair when their normalized questions match
    and their market-type / line agree. Absorbs
    ``utils/cross_source_matching.normalize_question``; the conservative
    near-match paraphrase pass is intentionally left to the existing utility for
    v1 (the exact-normalized key is what we shadow-verify here)."""

    name = "question_normalization"

    def propose(self, subject: MarketSignature, universe: MatchUniverse) -> list[ResolvedLink]:
        if not subject.question_norm:
            return []
        links: list[ResolvedLink] = []
        for other in universe.markets:
            if other.source == subject.source or not other.question_norm:
                continue
            if other.question_norm != subject.question_norm:
                continue
            if subject.market_type and other.market_type and subject.market_type != other.market_type:
                continue
            if not line_agrees(
                subject.line, subject.line_direction, other.line, other.line_direction
            ):
                continue
            links.append(
                ResolvedLink(
                    link_type=LINK_CROSS_SOURCE,
                    left=subject.external_id,
                    right=other.external_id,
                    strategy=self.name,
                    confidence=0.8,
                    evidence={"question_norm": subject.question_norm},
                )
            )
        return links


class ContainerStrategy:
    """family/dedup keys via a shared source container.

    Markets that share a source container (Polymarket event id / Kalshi series
    anchor in ``concept_ref``) belong to one family. Absorbs the group_id
    container-inheritance mechanism: the family key IS the container ref."""

    name = "container"

    def propose(self, subject: MarketSignature, universe: MatchUniverse) -> list[ResolvedLink]:
        if not subject.concept_ref:
            return []
        return [
            ResolvedLink(
                link_type=LINK_FAMILY,
                left=subject.external_id,
                right=family_key(subject.source, subject.concept_ref),
                strategy=self.name,
                confidence=0.85,
                evidence={"container": subject.concept_ref},
            )
        ]


def family_key(source: str, concept_ref: str) -> str:
    """Deterministic family key for a source container."""
    return f"{(source or '').lower()}:{concept_ref}"


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
DEFAULT_STRATEGIES: tuple[Strategy, ...] = (
    TickerParticipantStrategy(),
    EntrantSetStrategy(),
    QuestionNormalizationStrategy(),
    ContainerStrategy(),
)


class ResolutionEngine:
    """The one engine. Holds a strategy registry; resolves a signature (or a
    batch) to :class:`ResolvedLink` records across all link types."""

    def __init__(self, strategies: Optional[Sequence[Strategy]] = None):
        self.strategies: tuple[Strategy, ...] = tuple(
            strategies if strategies is not None else DEFAULT_STRATEGIES
        )

    def resolve(
        self, subject: MarketSignature, universe: MatchUniverse
    ) -> list[ResolvedLink]:
        """Run every strategy against one subject signature."""
        links: list[ResolvedLink] = []
        for strat in self.strategies:
            links.extend(strat.propose(subject, universe))
        return links

    def resolve_all(
        self, subjects: Iterable[MarketSignature], universe: MatchUniverse
    ) -> list[ResolvedLink]:
        """Resolve a batch of subjects against a shared universe."""
        out: list[ResolvedLink] = []
        for sig in subjects:
            out.extend(self.resolve(sig, universe))
        return out

    def links_by_type(
        self, subject: MarketSignature, universe: MatchUniverse
    ) -> dict[str, list[ResolvedLink]]:
        """Convenience: the subject's links bucketed by link type."""
        buckets: dict[str, list[ResolvedLink]] = {
            LINK_MARKET_EVENT: [],
            LINK_MARKET_CONCEPT: [],
            LINK_CROSS_SOURCE: [],
            LINK_FAMILY: [],
        }
        for link in self.resolve(subject, universe):
            buckets.setdefault(link.link_type, []).append(link)
        return buckets
