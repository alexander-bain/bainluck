"""Which two Polymarket rows are one fixture, when the venue split it. #5821.

**SHIP: a match page stops hiding its spread and every total on a duplicate row
the page has already folded away.** (Pillar: MATCHING.)

This is the JUDGEMENT half of a sweep and it touches no database. It answers one
question and refuses everything else: *given the Polymarket markets hanging off
these rows, which row is a second copy of a fixture another row already holds?*

It is the sibling of :mod:`app.utils.soccer_ghost_twins` and reuses that
module's vocabulary and its discipline — a reversible label, no deleter,
under-tagging as the intended failure direction. It does NOT reuse its pairing.
That module separates two rows by *an authority fixture id on one side and none
on the other*; on this population **neither side is anchored**, so its rule
refuses every pair here. The structure that separates these two rows is the
venue's own: which of them holds the fixture's base-titled market.

WHAT THE DEFECT LOOKS LIKE
══════════════════════════

Polymarket publishes one fixture as SEVERAL Gamma events, not one. Lexington SC
v Orange County SC, 2026-09-19 23:00Z, is seven of them::

    1016178  Lexington SC vs. Orange County SC                  <- the base
    1016188  … - Halftime Result
    1016189  … - Second Half Result
    1016190  … - Exact Score
    1016191  … - First Team to Score
    1016286  … - Total Corners
    1016298  … - More Markets            (the spread and every O/U total)

Each is a separate Gamma event with its own id, so each arrives as its own
id-less claim. Five of the six derivatives never mint a row, because #2871's
:func:`~app.utils.prediction_market_matching.is_derivative_market_name` refuses
a dash-introduced market type as evidence that a game exists. **The container
suffixes are deliberately excluded from that refusal** — "the game's own
container market … does not match this and still creates the fixture normally" —
so the ``- More Markets`` event mints a SECOND row and takes the spread and the
totals with it.

Measured on production 2026-09-17 over every Polymarket market carrying
``venue_game_start``::

    distinct (base title, venue_game_start) keys           10,932
    …spanning more than one event                             183
    …with exactly one base-title holder                       180
    …with two base holders            (ambiguous, refused)      3
    …with no base holder                                        0
    …spanning three or more events                              0

WHY THE CARD IS ALREADY FOLDED AND THE MARKETS ARE STILL LOST
══════════════════════════════════════════════════════════════

``fold_twin_events`` keys on ``(sport_id, away, home, commence MINUTE)`` and
today both rows share a commence instant exactly, so the duplicate CARD is
already suppressed — ``/api/events/search?q=Lexington SC`` returns one row.
That is the whole of the improvement so far, and it is the smaller half: the
fold hides the card and **leaves the loser's markets on the loser**. The page a
reader gets is the surviving row's, and on 2026-09-17 it drew the halftime
result, the moneyline and the corners, and not one spread or total.

So this module does not decide which card to PRINT — that is settled and
working. It supplies the evidence that lets ``folded_event_ids`` serve the
hidden row's markets on the surviving row's page.

WHY THIS IS NOT A RELAXATION OF RULING 048
═══════════════════════════════════════════

Nothing is absorbed, merged, deleted or repointed. The duplicate keeps its row,
its id and its markets; one element is appended to ``event_tags`` and one
predicate reverts it. This is the distinction
:mod:`app.utils.proven_duplicates` draws in its own words — it is why ruling 048
permits a tag and "would not permit an ``UPDATE futures_markets SET event_id``".

Membership is decided by the venue's own structure (notice 40) and by TWO
independent venue-side signals, the same pair the forward fix
``_polymarket_container_sibling_event_id`` already ships on:

1. **The title.** Polymarket mints the companion's title as the base title plus
   a fixed suffix, so :func:`_strip_more_markets` recovers the base EXACTLY.
   String equality on a string the venue composed, not a fuzzy join.
2. **``venue_game_start``**, the kickoff Polymarket publishes for the fixture,
   which the ingest already stores in ``market_metadata``.

Refs #5821, #2693, CERT-2793's required repair
``5821-EXISTING-SPLIT-CONTAINERS-COLLAPSE``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping

from app.utils.prediction_market_matching import _strip_more_markets

__all__ = [
    "NOT_A_TWIN",
    "REFUSE_AMBIGUOUS",
    "REFUSE_ANCHORED",
    "REFUSE_MIXED_KICKOFF",
    "TWIN_FOUND",
    "ContainerMarket",
    "ContainerPlan",
    "ContainerRow",
    "ContainerTag",
    "family_key",
    "holds_base_title",
    "plan_container_tags",
]

#: A family resolved to exactly one canonical and at least one duplicate.
TWIN_FOUND = "TWIN_FOUND"

#: Two or more rows under one key hold the base title, so the venue's own
#: structure does not say which is the fixture. Refused: under-tagging is the
#: intended failure direction. 3 of 183 keys on 2026-09-17.
REFUSE_AMBIGUOUS = "REFUSE_AMBIGUOUS"

#: The row the key would call a duplicate is named by an authority that knows
#: the fixture independently of us, and the canonical is not. Tagging THAT row
#: as a copy of an id-less one is backwards under ruling 048, which argues for
#: keeping the anchored row. 7 of 180 families on 2026-09-17. Refused rather
#: than inverted: an inversion is a different decision with different evidence,
#: and this module's job is to be sure, not to be complete.
REFUSE_ANCHORED = "REFUSE_ANCHORED"

#: The candidate duplicate's own markets name two different venue kickoffs, so
#: folding them would carry a second fixture's markets onto this page. **Zero
#: rows on 2026-09-17** — this is here for the row that is not, which nothing
#: else in the system would catch.
#:
#: 🔴 Only NON-NULL kickoffs count. Coalescing the nulls to a sentinel reads 109
#: of 180 rows as mixed, every one of them a row holding one market the ingest
#: stamped and one it did not — a refusal that would take this sweep's reach
#: from 173 families to 64 for no defect at all.
REFUSE_MIXED_KICKOFF = "REFUSE_MIXED_KICKOFF"

#: The key names one event. The overwhelming majority: 10,749 of 10,932.
NOT_A_TWIN = "NOT_A_TWIN"


@dataclass(frozen=True)
class ContainerMarket:
    """One Polymarket market, reduced to what the judgement reads."""

    event_id: int
    name: str
    venue_game_start: str


@dataclass(frozen=True)
class ContainerRow:
    """What an event row contributes beyond its markets."""

    event_id: int
    espn_id: object = None
    statpal_fixture_id: object = None
    #: Every non-null ``venue_game_start`` on this row's markets, across ALL
    #: keys, not only the one under judgement. That is the point: the question
    #: :data:`REFUSE_MIXED_KICKOFF` asks is whether this row holds a SECOND
    #: fixture, which by construction lives under a different key.
    venue_game_starts: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ContainerTag:
    """One decision: ``duplicate_id`` is a second copy of ``canonical_id``."""

    duplicate_id: int
    canonical_id: int
    reason: str


@dataclass
class ContainerPlan:
    """Everything one pass decided, including what it refused and why."""

    tags: list[ContainerTag] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    #: Distinct (base title, venue kickoff) keys the pass looked at.
    keys_examined: int = 0
    #: Keys naming more than one event, i.e. every key that could yield a tag.
    #: Its own number rather than a ratio: a join that stops attaching markets
    #: takes this to zero while ``keys_examined`` stays healthy, and a total
    #: would report that as a quiet ordinary day.
    split_keys_examined: int = 0
    rows_considered: int = 0


def family_key(market: ContainerMarket) -> tuple[str, str]:
    """The venue-composed identity of the fixture this market belongs to.

    Both halves are the venue's, and neither is ours: the title with the
    container suffix removed by the one stripper the forward fix already uses,
    and the kickoff Polymarket published.
    """
    return (_strip_more_markets(market.name or "").strip(), market.venue_game_start)


def holds_base_title(market: ContainerMarket) -> bool:
    """Is this market the fixture's OWN market rather than a container of it?

    True exactly when stripping the container suffix changed nothing. Spelled as
    a comparison against :func:`_strip_more_markets` rather than a second regex
    so that a suffix added there cannot leave a second, staler test behind —
    the failure ``_POLYMARKET_CONTAINER_SUFFIXES`` warns about in its own note.
    """
    name = (market.name or "").strip()
    return bool(name) and _strip_more_markets(name).strip() == name


def _classify_family(
    key: tuple[str, str],
    event_ids: set[int],
    base_holders: set[int],
    rows: Mapping[int, ContainerRow],
) -> tuple[str, list[ContainerTag]]:
    """The whole decision for one key. Pure; returns a verdict and its tags."""
    if len(event_ids) < 2:
        return NOT_A_TWIN, []
    if len(base_holders) != 1:
        return REFUSE_AMBIGUOUS, []

    canonical_id = next(iter(base_holders))
    canonical = rows.get(canonical_id) or ContainerRow(canonical_id)
    canonical_anchored = _is_fixture_anchored(canonical)

    tags: list[ContainerTag] = []
    for duplicate_id in sorted(event_ids - base_holders):
        duplicate = rows.get(duplicate_id) or ContainerRow(duplicate_id)

        if _is_fixture_anchored(duplicate) and not canonical_anchored:
            return REFUSE_ANCHORED, []

        # Strictly more than one DISTINCT non-null kickoff on the row. A row
        # holding this key's kickoff and nothing else is the healthy case.
        if len(duplicate.venue_game_starts) > 1:
            return REFUSE_MIXED_KICKOFF, []

        tags.append(
            ContainerTag(
                duplicate_id=duplicate_id,
                canonical_id=canonical_id,
                reason=f"polymarket container split: {key[0]!r} @ {key[1]}",
            )
        )

    return (TWIN_FOUND, tags) if tags else (NOT_A_TWIN, [])


def _is_fixture_anchored(row: ContainerRow) -> bool:
    """Does an authority that knows this fixture independently of us name it?

    ``external_id`` is deliberately NOT read, for the reason
    :func:`app.utils.soccer_ghost_twins.row_is_fixture_anchored` gives: it is a
    per-ingest surrogate that anchors nothing. Measured here on 2026-09-17, all
    7 anchored duplicates carried ``espn_id`` and ``statpal_fixture_id`` and
    ``external_id`` together, so reading the surrogate would have changed no
    verdict and would have been right by luck.
    """
    return row.espn_id is not None or row.statpal_fixture_id is not None


def plan_container_tags(
    markets: Iterable[ContainerMarket],
    rows: Mapping[int, ContainerRow] | None = None,
) -> ContainerPlan:
    """Every duplicate this pass is sure about, and every refusal, in one object.

    A market with no ``venue_game_start`` is not judged at all — one of the two
    venue signals is missing, so the key cannot be formed and the row keeps
    exactly today's behaviour. That is the same fall-through the forward fix
    takes, and it is why rows minted before the ingest wrote the field are left
    alone rather than guessed at.
    """
    rows = rows or {}
    by_key: dict[tuple[str, str], set[int]] = {}
    base_by_key: dict[tuple[str, str], set[int]] = {}
    seen_events: set[int] = set()

    for market in markets:
        if not market.venue_game_start or not str(market.venue_game_start).strip():
            continue
        key = family_key(market)
        if not key[0]:
            continue
        by_key.setdefault(key, set()).add(market.event_id)
        seen_events.add(market.event_id)
        if holds_base_title(market):
            base_by_key.setdefault(key, set()).add(market.event_id)

    plan = ContainerPlan(
        keys_examined=len(by_key),
        rows_considered=len(seen_events),
    )

    for key in sorted(by_key):
        event_ids = by_key[key]
        if len(event_ids) < 2:
            continue
        plan.split_keys_examined += 1
        verdict, tags = _classify_family(
            key, event_ids, base_by_key.get(key, set()), rows
        )
        if verdict == TWIN_FOUND:
            plan.tags.extend(tags)
        elif verdict != NOT_A_TWIN:
            plan.refusals.append(f"{verdict}: {key[0]!r} @ {key[1]}")

    return plan
