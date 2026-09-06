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
one carries the tournament key and the substance, the other carries neither. When
both look like ghosts, or both look canonical, the answer is
:data:`REFUSE_AMBIGUOUS` — reported, never acted on. Under-tagging is the intended
failure direction, exactly as in ``_proven_duplicates``: a duplicate we miss stays
visible and stays fixable; a real match we tag is a match the product stops
showing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

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
    #: rather than a bare tour key (``tennis_atp`` / ``tennis_wta``).
    is_tournament_keyed: bool
    #: Any linked prediction market, score, or probability — anything a user
    #: could read off the row. The caller computes it; see ``_has_substance``.
    has_substance: bool


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
    if ghost.has_substance:
        return TwinVerdict(
            REFUSE_AMBIGUOUS,
            reason="the bare-keyed row carries substance; it is not a ghost",
        )
    if not canonical.has_substance:
        return TwinVerdict(
            REFUSE_AMBIGUOUS,
            reason="the tournament-keyed row carries no substance either",
        )
    return TwinVerdict(
        TWIN_FOUND,
        ghost_id=ghost.event_id,
        canonical_id=canonical.event_id,
        reason="orientation swapped" if swapped and not straight else "participants agree",
    )
