"""Which two tennis rows are one match, and which of the two is the ghost. #2878.

**SHIP: tomorrow's US Open semi-final appears once on the tour page, not twice.**
(Pillar: MATCHING.)

This module is the JUDGEMENT half of #2693's drain and it deliberately touches no
database. It answers two questions and refuses everything else:

1. Are these two rows the same fixture, written twice?
2. If so, which one is the **ghost** — the bare row safe to stop printing?

WHY THE EXISTING RAILS CANNOT SEE THESE PAIRS
═════════════════════════════════════════════

``event_registry._proven_duplicates`` is the ingest-time tagger and every one of
the 24 measured US Open pairs fails it twice over:

* Guards 1-3 are **id-anchored** (ruling 048 arm B, ESPN alone). lane1/154
  measured **zero** shared ``(source, source_id)`` between any twin and its
  canonical, so there is no id correspondence to anchor on.
* Guard 4 requires the candidate within ``_SAME_FIXTURE_MAX_SEPARATION``
  (30 minutes). authority/048 measured that the ghost and its canonical **never**
  share a kickoff: the ghost carries ``00:00:00`` or a round ``18:00:00``.

And it fires only at ingest, on a live multi-match. The 24 pairs are already in
the table, so even a repaired predicate would not reach them. This needs a sweep.

``reconcile_unanchored_events`` already counts these rows — they are its
``ANCHORED_TWIN_UNSEEN`` bucket, "a duplicate whose two halves share no provider
id, invisible to the key and plainly visible to a human". That module carries a
warning this one is written to obey:

    *That predicate is a METER and must never become a MERGE.*

**This module does not merge and must never be wired to one.** The distinction is
the one ``proven_duplicates`` draws: a merge DELETEs and is irreversible, so it
needs an id; declining to PRINT a second card is reversible by reverting one
predicate, and it is the whole of what the user is complaining about. The output
here feeds ``provenance:duplicate-of:``, a label with an existing reader
(:func:`app.utils.proven_duplicates.not_a_proven_duplicate`) and no deleter.

WHY NOT authority/048'S ``sorted(surname, surname)`` KEY
═════════════════════════════════════════════════════════

Their census key — ``fold_tennis_name(n).split()[-1]``, sorted into a pair —
found all 24 on the first pass and is the reason this is buildable. It is used
here as the coarse BLOCK key and nothing more, because as a decision it drops the
given name, and ``authority_tennis_names`` exists to record what that costs:
``('damm', None)`` is claimed by both Martin Damm and Martin Damm Jr, two players
who have both been in ATP draws. The confirm step therefore runs the module's own
``keys_agree``, which keeps the initial when both sides have one.

That module's guards are inherited rather than re-implemented — ``_NOT_A_PLAYER``
(futures titles like ``Black Desert Resort (Men's Doubles) Winner`` sit in the
team-name column and fold to keys that collide with nothing real) and the
doubles-never-matches-singles rule (doubles outnumber singles better than 2:1 on
a US Open day, so conflating the draws manufactures phantom pairs).

THE ASYMMETRY IS THE SAFETY, NOT THE TIME WINDOW
═════════════════════════════════════════════════

A tighter time window is not available: the ghost's kickoff is the very field
that is wrong. What replaces it is a structural asymmetry authority/048 measured
and that holds 240/240 — **only tournament-keyed rows are ever linked** (48/48
``tennis_*_us_open`` linked, 192/192 generic-tour-key rows unlinked).

So a pair is only actionable when the two rows disagree in the right direction:
one carries the tournament key and the settled result, the other carries neither.
When both look like ghosts, or both look canonical, the answer is
:data:`REFUSE_AMBIGUOUS` — reported, never acted on. Under-tagging is the intended
failure direction, exactly as in ``_proven_duplicates``: a duplicate we miss stays
visible and stays fixable; a real match we tag is a match the product stops
showing.

WHAT "THE SUBSTANCE" IS, AND WHAT IT IS NOT
════════════════════════════════════════════

**It is the final score and nothing else.** The first draft of this module said
"any linked prediction market, score, or probability — anything a user could read
off the row", which is the intuitive reading and is measurably wrong. Running the
predicate over production's own rows (2026-09-06, 172 candidate pairs) is what
showed it:

    ghosts carrying a score                    0 / 172
    ghosts carrying at least one market      110 / 172
    ghosts carrying MORE markets than their
      own canonical                           63 / 172

The Kalshi-minted ghost is not an empty row. It has prices, a probability, and
often a bigger market book than the odds_api row that will actually be settled —
``Cerundolo/Blockx`` is 17 markets on the ghost against 1 on the canonical. A
sweep built on the intuitive reading tags **zero of the pairs the tour page is
blocked on** and reports success, which is gotcha #53 written out in full.

The consequence runs the other way too, and it is the honest limit of this ship:
because the score is what separates them, **an unsettled pair cannot be
separated at all** and :func:`plan_twin_tags` refuses it. See
:func:`row_has_settled_result`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional

from app.utils.authority_tennis_names import (
    doubles_key,
    fold_tennis_name,
    is_doubles_name,
    keys_agree,
    looks_like_a_player,
    our_tennis_keys,
)

#: Generational suffixes, as a TRAILING token. See :func:`_generational_suffix`.
_SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv)$")


def _generational_suffix(name: object) -> Optional[str]:
    """The trailing ``jr``/``sr``/``ii``/``iii``/``iv``, or ``None``.

    ``authority_tennis_names`` records, from a sweep over the real field, that
    ``('damm', None)`` is claimed by both Martin Damm and Martin Damm Jr, and
    that **stripping the suffix fuses exactly the two people the suffix exists to
    tell apart**. It keeps the suffix for that reason — but keeping it is not
    enough here, and only running the pair through the code showed why:

        ``our_tennis_keys('Damm Jr')`` is ``{('damm', 'j'), ('jr', 'd')}``.

    The surname-FIRST reading — the one that exists so ``Wu Yibing`` can join
    ``Yibing Wu`` — reads ``Jr`` as the given name and ``Damm`` as the surname,
    producing ``('damm', 'j')``, which ``keys_agree`` then matches against the
    suffix-less ``('damm', None)`` because a ``None`` initial cannot disagree.
    So the two Damms fuse through the very reading that protects Chinese and
    Korean name order.

    Rather than weaken that reading for every name, the suffix is compared
    directly: a name that carries one and a name that does not are different
    people. Absent on both sides is agreement, which is the overwhelming case.
    """
    folded = fold_tennis_name(name)
    m = _SUFFIX.search(folded)
    # A bare suffix and nothing else is not a suffix, it is an unreadable name;
    # `our_tennis_keys` already declines to key it and this must not claim
    # otherwise.
    return m.group(1) if m and folded != m.group(1) else None

#: Tennis sport keys that are a TOUR (or the unclassified bucket) rather than a
#: tournament. Everything else beginning ``tennis_`` is minted per tournament as
#: the tournament appears (``tennis_atp_us_open``,
#: ``tennis_wta_monterrey_open``, …), so the tournament set cannot be enumerated
#: — the bare set can, and it is three long. Measured over the 1,430 tennis rows
#: in the ±15-day window on 2026-09-06: 637 ``tennis_other``, 375
#: ``tennis_atp``, 167 ``tennis_wta``, and 251 rows across six tournament keys.
BARE_TOUR_KEYS = frozenset({"tennis_atp", "tennis_wta", "tennis_other"})


def is_tournament_key(sport_key: str) -> bool:
    """Is this a per-tournament tennis key rather than a bare tour key?

    Stated as "not in the bare set" rather than as a prefix or underscore-count
    rule, because the tournament keys are minted from tournament names and their
    shape is not ours to predict — ``tennis_atp_aus_open_singles`` has five
    segments and ``tennis_atp_dubai`` has three.
    """
    return sport_key not in BARE_TOUR_KEYS


def row_has_settled_result(*, home_score: object, away_score: object) -> bool:
    """Has this row been settled — i.e. does it carry a final score?

    **This is the one input a caller gets wrong, so it is a named function and
    not a lambda at the call site.** The intuitive reading of "substance" — any
    linked prediction market, any probability, anything a user could read off
    the row — is measurably WRONG, and building the sweep on it produces a
    tagger that finds nothing and reports success (gotcha #53).

    Measured on production 2026-09-06 over the 172 candidate ghost→canonical
    pairs in the ±15-day tennis window:

        ghosts carrying a score                  0 / 172
        ghosts that ever reached 'completed'     0 / 172
        canonicals completed or closed         164 / 172   (the other 8 are future)
        ghosts carrying at least one market    110 / 172
        ghosts carrying MORE markets than
          their own canonical                   63 / 172

    So markets and probabilities do not separate the two rows — they point the
    WRONG WAY two times in five. The Kalshi-minted ghost for
    ``Cerundolo/Blockx`` carries 17 markets against its canonical's 1. The score
    separates them 172/172, and it is the only field that does.

    That asymmetry also gives the sweep its refusal for free: before a match is
    settled NEITHER row has a score, :func:`classify_pair` returns
    :data:`REFUSE_AMBIGUOUS`, and the pair is left alone. That is the correct
    answer and not a shortcoming — see :func:`plan_twin_tags`.
    """
    return home_score is not None or away_score is not None


#: The two rows are one fixture and `ghost_id` is safe to stop printing.
TWIN_FOUND = "TWIN_FOUND"
#: The two rows are one fixture, but which is the ghost cannot be decided.
REFUSE_AMBIGUOUS = "REFUSE_AMBIGUOUS"
#: Not the same fixture. The common answer.
NOT_A_TWIN = "NOT_A_TWIN"


def players_agree(ours: object, theirs: object) -> bool:
    """Do two of OUR names denote the same player (or doubles team)?

    The symmetric counterpart to ``authority_tennis_names.tennis_names_agree``,
    which cannot be reused here: that one reads its second argument with
    ``statpal_tennis_key``, i.e. as StatPal's initials-then-surname shape. Both
    sides here are our own column, so both are read with ``our_tennis_keys``.

    Agreement is "some reading of one matches some reading of the other".
    ``our_tennis_keys`` is permissive on purpose — it returns surname-first *and*
    surname-last for every cut, because our column does not record which one it
    stored — and that permissiveness is safe here only because a caller must also
    clear :func:`classify_pair`'s asymmetry guard before anything is hidden.
    """
    if is_doubles_name(ours) or is_doubles_name(theirs):
        # A doubles name never matches a singles name; a malformed pair matches
        # nothing rather than half-matching.
        a, b = doubles_key(ours), doubles_key(theirs)
        return a is not None and a == b
    if _generational_suffix(ours) != _generational_suffix(theirs):
        return False
    return any(
        keys_agree(k, j)
        for k in our_tennis_keys(ours)
        for j in our_tennis_keys(theirs)
    )


def block_key(home: object, away: object) -> Optional[tuple[str, ...]]:
    """A coarse, hashable bucket for candidate pairs — authority/048's key.

    ``None`` when either side is unreadable or is not a player, so a caller
    bucketing a whole table drops the futures-title rows without a second pass.

    This is a BLOCK key: rows sharing it are *candidates*, and every candidate
    pair must still be confirmed by :func:`classify_pair`. It exists so a sweep
    over a few hundred rows is a grouping rather than a quadratic scan, and it is
    intentionally looser than the confirm step — a block key that could refuse a
    true pair would hide the pair from the careful predicate downstream.
    """
    if not looks_like_a_player(home) or not looks_like_a_player(away):
        return None

    def side(name: object) -> Optional[str]:
        if is_doubles_name(name):
            pair = doubles_key(name)
            # Fold a doubles team to its two surnames so the block key of a
            # doubles fixture is stable under either side's spelling.
            return "/".join(sorted(p.split()[-1] for p in pair)) if pair else None
        toks = fold_tennis_name(name).split()
        return toks[-1] if toks else None

    a, b = side(home), side(away)
    if not a or not b:
        return None
    return tuple(sorted((a, b)))


@dataclass(frozen=True)
class TwinRow:
    """The fields a twin decision reads. A plain snapshot, never a live ORM row.

    Copied to scalars by the caller because a rollback boundary expires ORM
    attributes and a ``getattr`` on an expired attribute lazy-loads in a sync
    context (gotcha #6, memory: feedback_orm_lazy_load). A judgement that reads
    the database is a judgement nobody can test.
    """

    event_id: int
    home_team_name: object
    away_team_name: object
    sport_key: str
    #: True when the row carries a tournament sport key (``tennis_*_us_open``)
    #: rather than a bare tour key (``tennis_atp`` / ``tennis_wta`` /
    #: ``tennis_other``). See :data:`BARE_TOUR_KEYS`.
    is_tournament_keyed: bool
    #: **A FINAL SCORE, AND NOTHING ELSE.** Not markets, not a probability, not
    #: a status. Read :func:`row_has_settled_result` before you compute this —
    #: the obvious reading is measurably wrong and silently ships a no-op.
    has_settled_result: bool


@dataclass(frozen=True)
class TwinVerdict:
    """What :func:`classify_pair` decided, and enough to explain it in a receipt."""

    outcome: str
    ghost_id: Optional[int] = None
    canonical_id: Optional[int] = None
    reason: str = ""


def classify_pair(a: TwinRow, b: TwinRow) -> TwinVerdict:
    """Are these one fixture, and if so which one is safe to stop printing?

    Returns :data:`TWIN_FOUND` only when BOTH hold:

    * the participants agree in one orientation or the other, and
    * exactly one row is tournament-keyed **and** exactly one row has substance,
      and they are the same row.

    The second clause is the whole safety argument. It is not a heuristic about
    which row looks nicer; it is authority/048's 240/240 structural finding —
    only tournament-keyed rows are ever linked — restated as a precondition, so
    that a population which stops obeying it stops being tagged instead of being
    tagged wrongly.

    Orientation is checked both ways because a twin can be stored flipped, and
    ``event_registry._find_structured_matches`` already treats a swapped
    orientation as a match for exactly that reason.
    """
    if a.event_id == b.event_id:
        return TwinVerdict(NOT_A_TWIN, reason="same row")
    if a.sport_key.split("_")[0] != b.sport_key.split("_")[0]:
        # `tennis_atp` and `tennis_wta_us_open` share a discipline; a tennis row
        # and a basketball row do not. Cheap, and it stops a mis-classified row
        # (#3559) from pairing across sports.
        return TwinVerdict(NOT_A_TWIN, reason="different discipline")

    straight = players_agree(a.home_team_name, b.home_team_name) and players_agree(
        a.away_team_name, b.away_team_name
    )
    swapped = players_agree(a.home_team_name, b.away_team_name) and players_agree(
        a.away_team_name, b.home_team_name
    )
    if not (straight or swapped):
        return TwinVerdict(NOT_A_TWIN, reason="participants disagree")

    # Exactly one tournament-keyed, exactly one with substance, same row.
    if a.is_tournament_keyed == b.is_tournament_keyed:
        return TwinVerdict(
            REFUSE_AMBIGUOUS,
            reason=(
                "both tournament-keyed"
                if a.is_tournament_keyed
                else "neither tournament-keyed"
            ),
        )
    canonical, ghost = (a, b) if a.is_tournament_keyed else (b, a)
    if ghost.has_settled_result:
        return TwinVerdict(
            REFUSE_AMBIGUOUS,
            reason="the bare-keyed row carries a result; it is not a ghost",
        )
    if not canonical.has_settled_result:
        return TwinVerdict(
            REFUSE_AMBIGUOUS,
            reason="neither row has been settled; which is the ghost is not yet decidable",
        )
    return TwinVerdict(
        TWIN_FOUND,
        ghost_id=ghost.event_id,
        canonical_id=canonical.event_id,
        reason="orientation swapped" if swapped and not straight else "participants agree",
    )


# ════════════════════════════════════════════════════════════════════════════
# The sweep planner — still pure, still no database
# ════════════════════════════════════════════════════════════════════════════

#: How far apart two rows may be stamped and still be one fixture.
#:
#: NOT a precision instrument, and not the 30 minutes ``_proven_duplicates``
#: uses: the ghost's kickoff is the field that is wrong, so a tight window is
#: unavailable. 145 of 172 measured ghosts are stamped exactly ``00:00:00`` on
#: the day the DRAW was published rather than the day the match was played, so
#: real pairs are legitimately days apart — the measured spread is
#: min 0.5h / median 25h / p90 67h.
#:
#: This is a plan-drift bound, and it is set where it excludes exactly the two
#: pairs on production that a human should look at rather than tag:
#:
#:     fence  72h keeps 164/172      fence 120h keeps 170/172
#:     fence  96h keeps 170/172      fence 168h keeps 172/172
#:
#: The two it excludes are both bare rows dated 2026-08-28 — US Open QUALIFYING
#: week — pointing at a main-draw match played 2026-09-03 (``15294924`` and
#: ``15295192`` → ``15301184``, Bonzi/Buse). A qualifying meeting and a
#: main-draw meeting between the same two players is a REAL pair of distinct
#: matches, and it has exactly the shape a twin has. The fence does not decide
#: that case; it declines to, and reports it.
MAX_TWIN_SEPARATION = timedelta(hours=96)


@dataclass(frozen=True)
class TwinTag:
    """One reversible label the sweep intends to write."""

    ghost_id: int
    canonical_id: int
    reason: str


@dataclass(frozen=True)
class TwinSweepPlan:
    """What a sweep would do, and everything it declined to do and why.

    ``refusals`` is not diagnostics. Under-tagging is this sweep's intended
    failure direction, so the refused pairs ARE the population somebody has to
    look at next, and a plan that dropped them on the floor would make the
    sweep's own honesty unmeasurable.
    """

    tags: tuple[TwinTag, ...]
    refusals: tuple[str, ...]
    rows_considered: int
    blocks_examined: int


def plan_twin_tags(
    rows: Iterable[TwinRow],
    *,
    commence_times: dict[int, datetime],
    max_separation: timedelta = MAX_TWIN_SEPARATION,
) -> TwinSweepPlan:
    """Decide every ``provenance:duplicate-of:`` label a sweep should write.

    Pure: it takes row snapshots and returns intentions. Nothing here reads or
    writes a database, so the whole judgement is testable without one.

    Three gates beyond :func:`classify_pair`, each of which exists because the
    production population showed it was needed:

    1. **The block key groups, it does not decide.** Rows are bucketed by
       :func:`block_key` — a global ``(surname, surname)`` pair with no time
       component at all — and every candidate within a bucket is then confirmed
       pair by pair.

    2. **The separation fence** (:data:`MAX_TWIN_SEPARATION`), because the block
       key is global: without it, two genuinely different meetings between the
       same two players are a candidate pair.

    3. **A ghost may be claimed by exactly ONE canonical.** Measured 0 violations
       on production, and the guard is here anyway — it is the one that catches
       the block key having fused two real fixtures, and a guard that only exists
       once it has failed in production is a guard that arrived late. The reverse
       is NOT refused: one canonical with several ghosts is a real and common
       shape (12 of them on production; ``Li/Ruzic`` exists as two bare rows and
       one tournament row), and every ghost in such a star names the same
       canonical, so the label stays coherent.

    A row that is both a ghost in one pair and a canonical in another is
    structurally impossible — a ghost has no settled result and a canonical must
    have one — so there is no chain to unwind, and :func:`classify_pair` is what
    guarantees that rather than a check here.
    """
    rows = list(rows)
    buckets: dict[tuple[str, ...], list[TwinRow]] = defaultdict(list)
    for row in rows:
        key = block_key(row.home_team_name, row.away_team_name)
        if key is not None:
            buckets[key].append(row)

    found: list[TwinTag] = []
    refusals: list[str] = []
    for bucket in buckets.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                verdict = classify_pair(a, b)
                if verdict.outcome == REFUSE_AMBIGUOUS:
                    refusals.append(
                        f"{a.event_id}/{b.event_id}: {verdict.reason}"
                    )
                    continue
                if verdict.outcome != TWIN_FOUND:
                    continue
                ghost_at = commence_times.get(verdict.ghost_id)
                canon_at = commence_times.get(verdict.canonical_id)
                if ghost_at is None or canon_at is None:
                    refusals.append(
                        f"{verdict.ghost_id}/{verdict.canonical_id}: no kickoff on "
                        f"record for one side, so the separation fence cannot be applied"
                    )
                    continue
                apart = abs(canon_at - ghost_at)
                if apart > max_separation:
                    refusals.append(
                        f"{verdict.ghost_id}/{verdict.canonical_id}: stamped "
                        f"{apart.total_seconds() / 3600:.0f}h apart, beyond the "
                        f"{max_separation.total_seconds() / 3600:.0f}h fence — this is "
                        f"the shape of a qualifying meeting and a main-draw meeting "
                        f"between the same two players, and it is not ours to decide"
                    )
                    continue
                found.append(
                    TwinTag(verdict.ghost_id, verdict.canonical_id, verdict.reason)
                )

    claimed_by: dict[int, set[int]] = defaultdict(set)
    for tag in found:
        claimed_by[tag.ghost_id].add(tag.canonical_id)

    tags: list[TwinTag] = []
    for tag in found:
        rivals = claimed_by[tag.ghost_id]
        if len(rivals) > 1:
            refusals.append(
                f"{tag.ghost_id}: claimed as a duplicate by {len(rivals)} different "
                f"canonicals {sorted(rivals)} — the block key has fused two fixtures "
                f"and no label can be written without choosing between them"
            )
            continue
        tags.append(tag)

    return TwinSweepPlan(
        tags=tuple(sorted(tags, key=lambda t: t.ghost_id)),
        refusals=tuple(sorted(set(refusals))),
        rows_considered=len(rows),
        blocks_examined=len(buckets),
    )
