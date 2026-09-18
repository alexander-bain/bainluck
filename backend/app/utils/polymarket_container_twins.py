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

from app.utils.event_completion import is_retired_event_status
from app.utils.prediction_market_matching import _strip_more_markets

__all__ = [
    "NOT_A_TWIN",
    "REFUSE_AMBIGUOUS",
    "REFUSE_ANCHORED",
    "REFUSE_DEAD_CANONICAL",
    "REFUSE_MIXED_KICKOFF",
    "REFUSE_NO_ELECTION",
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

#: The fold's election named a canonical whose page a reader cannot open, so
#: the markets this tag would move there are served to nobody. #6904.
#:
#: 🔴 THE TAG'S ENTIRE PAYOFF IS A PAGE. ``folded_event_ids`` serves the
#: duplicate's markets on the canonical's page; ``GET /api/events/{id}`` answers
#: **410** for a row whose status is in
#: :data:`app.utils.event_completion.RETIRED_STATUSES`, and the client turns that
#: into *"This event is no longer listed"*. So a tag naming a retired canonical
#: moves markets onto a page that renders no markets, and additionally hands
#: ``not_a_proven_duplicate`` a reason to stop printing the row that is still
#: playable. This is the same judgement :func:`fold_is_live` already makes one
#: layer up — *"the tag is inert without ``folded_event_ids``, so writing it is
#: not a partial win"* — asked of the destination rather than of the mechanism.
#:
#: Measured over every row this sweep has written (2026-09-18 08:55Z, 226 of
#: them): **74 would have been refused** — 70 where both rows were already
#: retired, so the tag delivered nothing in either direction, and **4 where the
#: duplicate's own page still renders**, two of them `scheduled` fixtures that
#: had not kicked off. Both destinations were confirmed by hand: `GET
#: /api/events/15304969` and `/api/events/15305781` each answer 410.
#:
#: 🔴 AND IT REFILLS. The same cross-tab read 220 rows with ONE live-onto-dead
#: pair at 08:15Z; the 08:28Z beat banked a second (`15313072` Borussia
#: Mönchengladbach v 1. FSV Mainz 05, 8 markets onto voided `15305781`). This is
#: not a historical artifact to tidy — it is a write the sweep is still making.
#:
#: Refused rather than INVERTED, for the reason :data:`REFUSE_ANCHORED` gives:
#: preferring the live row would mean overriding ``twin_identity_rank``, which
#: is shared with ``fold_twin_events`` and with the COMMITTING caller
#: ``reconcile_shared_fixture_ids`` — a ranking change with its own blast radius
#: and its own measurement. Refusing costs the family its tag and nothing else.
#:
#: 🔴 The vocabulary is IMPORTED, never re-spelled as ``status == "voided"``.
#: :data:`~app.utils.event_completion.RETIRED_STATUSES` holds ``merged`` as well,
#: and its own note says a word is added there when it means "stop showing this"
#: — so a hand-copied literal would silently go on tagging into whichever word
#: was added next. We ask the question the 410 gate asks, so we cannot disagree
#: with the page.
REFUSE_DEAD_CANONICAL = "REFUSE_DEAD_CANONICAL"

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

#: At least one member of the family has no `twin_identity_rank`, so the fold's
#: election cannot be reproduced here. Refused rather than defaulted: an absent
#: rank sorts as the empty tuple, smaller than every real one, so defaulting
#: would quietly tag whichever row failed to load as the duplicate.
REFUSE_NO_ELECTION = "REFUSE_NO_ELECTION"

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
    #: ``events.status``, read for exactly one question: can a reader open this
    #: row's page at all? See :data:`REFUSE_DEAD_CANONICAL`. Supplied by the
    #: caller like every other field here so the module stays pure.
    #:
    #: A row that never set it defaults to ``None``, which
    #: :func:`~app.utils.event_completion.is_retired_event_status` reads as NOT
    #: retired — and that is the correct fall-through rather than a fail-open
    #: hole, because the 410 gate asks the identical question of the identical
    #: value: a row whose status is null renders, so it is reachable.
    status: object = None
    #: ``app.utils.event_twin_fold.twin_identity_rank`` for this row — biggest
    #: wins. Supplied by the caller rather than computed here so this module
    #: stays pure, and IMPORTED from the serving layer rather than re-spelled so
    #: it cannot drift from the election the fold actually runs.
    #:
    #: 🔴 THIS, NOT THE BASE TITLE, DECIDES WHICH ROW IS CANONICAL, and the
    #: distinction is the whole safety of the sweep. See
    #: :func:`_classify_family`.
    identity_rank: tuple = ()


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
    """The whole decision for one key. Pure; returns a verdict and its tags.

    🔴 **THE BASE TITLE CONFIRMS THE FAMILY; IT DOES NOT CHOOSE THE SURVIVOR.**
    Those are two different questions and conflating them is a live defect, not
    a tidiness point. Exactly one row holding the base-titled market is the
    evidence that these rows are one fixture the venue split. WHICH of them the
    reader should be sent to is decided by
    ``app.utils.event_twin_fold.twin_identity_rank`` — the fold's own election,
    supplied on :attr:`ContainerRow.identity_rank`.

    `repair_5821_split_container_markets.py` measured the cost of getting this
    wrong: of 125 families, **96 are won by the base and 29 by the companion**.
    A sweep that always made the base canonical would tag the fold's own
    survivor as a duplicate in 29 of 125, and ``not_a_proven_duplicate`` — which
    runs BEFORE the fold — would then suppress the better row and send the
    reader to the worse one. That is a new reader-facing defect traded for the
    one being fixed, and it is why this module defers rather than deciding, for
    the same reason that script gives: "a repair that picked its own winner
    would move markets onto the row the fold then hides".
    """
    if len(event_ids) < 2:
        return NOT_A_TWIN, []
    if len(base_holders) != 1:
        return REFUSE_AMBIGUOUS, []

    members = {eid: (rows.get(eid) or ContainerRow(eid)) for eid in event_ids}

    # Fail closed on a missing election. An absent rank sorts as `()` — smaller
    # than every real tuple — so a row whose rank failed to load would silently
    # LOSE the election and be tagged a duplicate of a row that may be worse.
    if any(not member.identity_rank for member in members.values()):
        return REFUSE_NO_ELECTION, []

    canonical_id = max(members, key=lambda eid: (members[eid].identity_rank, -eid))
    canonical = members[canonical_id]

    # The destination has to be a page. Checked on the ELECTED canonical and
    # before any tag is built, because this is a property of where the markets
    # are going, not of any one duplicate: a family cannot be half-refused.
    #
    # `twin_identity_rank` cannot catch this itself. It consults `status` at
    # exactly one rung — `completed` over anything else — and never penalises a
    # retired row, so a voided row carrying more sources outranks a scheduled
    # one and wins. `REFUSE_ANCHORED` cannot catch it either: on the measured
    # specimen neither row is fixture-anchored, so that guard never fires.
    if is_retired_event_status(canonical.status):
        return REFUSE_DEAD_CANONICAL, []

    canonical_anchored = _is_fixture_anchored(canonical)

    tags: list[ContainerTag] = []
    for duplicate_id in sorted(event_ids - {canonical_id}):
        duplicate = members[duplicate_id]

        # Belt and braces, and expected to read ZERO: `twin_identity_rank`
        # already ranks an ESPN id and then any provider id above source count,
        # so an anchored row wins its own election and cannot reach here. It is
        # kept because the day that ordering changes, the honest answer is to
        # refuse rather than to tag an authority-named row as a copy.
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
