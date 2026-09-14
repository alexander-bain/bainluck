"""Which two soccer rows are one fixture, and which of the two is the ghost. #5896.

**SHIP: a La Liga match that finished yesterday stops being advertised as
tonight's kick-off.** (Pillar: MATCHING.)

This is the JUDGEMENT half of a sweep and it deliberately touches no database.
It answers one question and refuses everything else: *given these rows, which
one is a second copy of a fixture that has already been played, and which row is
the real one?*

It is the soccer sibling of :mod:`app.utils.tennis_twin_pairs` and it reuses that
module's vocabulary (``TWIN_FOUND`` / ``REFUSE_AMBIGUOUS`` / ``NOT_A_TWIN``) and
its discipline — a reversible label, no deleter, under-tagging as the intended
failure direction. It does NOT reuse its pairing, because the structure that
separates two tennis rows (a tournament sport key, a surname block) does not
exist in soccer, and the structure that separates two soccer rows (an authority
fixture id on one side and none on the other) is not what the tennis module
reads.

WHAT THE DEFECT LOOKS LIKE
══════════════════════════

Measured on production 2026-09-13, ten pairs, every one the same shape::

    ghost  15298125 Sevilla v Valencia  09-13 19:00Z  scheduled  no score  no anchor
    real   15298233 Sevilla v Valencia  09-11 19:00Z  completed  1-0       espn 401882878

The ghost is dated at a round placeholder hour on a later day, carries no score
and no authority id; the real row carries both. Both were written by the same
Odds API ingest 95 minutes apart on 2026-08-30 — the first pass published the
fixture before its kick-off was confirmed, the second published it again with
the real time, and ruling 048 correctly refused to absorb an id-less claim.
Nothing has ever drained the first row, so the site advertises a game that was
played two days ago.

The ESPN slate for 2026-09-13, read at the authority (notice 26/27), contains
none of the ten: four La Liga fixtures, five Argentine Primera, four Segunda,
two Brasileirão, and not one ghost among them.

WHAT "ANCHORED" MEANS HERE, AND WHY ``external_id`` IS NOT IT
══════════════════════════════════════════════════════════════

:func:`app.utils.tennis_twin_pairs.row_is_id_anchored` reads three columns —
``external_id``, ``espn_id``, ``statpal_fixture_id`` — and on the tennis
population all three move together. **On this population ``external_id`` is
worthless and reading it would refuse every pair.** Both halves of all ten pairs
carry one, because an Odds API row's ``external_id`` is a per-ingest surrogate
hash: the two passes minted two different hashes for one fixture, which is the
very reason there are two rows. A per-provider minted id re-encodes the claim
and anchors nothing.

So the anchor here is :func:`row_is_fixture_anchored` — ``espn_id`` or
``statpal_fixture_id``, an id assigned by an authority that knows the fixture
independently of us. Measured over the ten pairs: canonical anchored 10/10,
ghost anchored 0/10.

That asymmetry is also what puts this on the right side of ruling 048. The row
we decline to print is the id-less one and the row we keep is the id-anchored
one, which is the direction 048 argues for. Nothing is absorbed, deleted or
repointed; the ghost keeps its row, its markets and its id, and one predicate
reverts the label.

WHY THREE DAYS, AND WHAT IT COST TO CHOOSE IT
══════════════════════════════════════════════

Soccer, unlike tennis, gives a time window — the canonical's kick-off is a real
one. The window has to exclude a genuine rematch, and the question "do the same
two teams, in the same orientation, ever play twice within three days?" is
answerable. Measured on production over 365 days of soccer, both rows completed,
both carrying a final score, both fixture-anchored, identical
``lower(btrim(name))`` on BOTH sides::

    pairs within 3 days                                    1
    …of which the pair shares one statpal_fixture_id
      and one kick-off instant (i.e. is itself a twin)     1
    genuine rematches                                      0

Orientation is load-bearing in that count and is not a detail: a two-legged tie
swaps home and away, so it can never collide with this key. A replay is at the
same venue but weeks later.

:data:`MAX_GHOST_LAG` is therefore three days, and it is a measured bound rather
than a guess. Widening it is not a free parameter — it is a new measurement.

THE GHOST DOES NOT STOP BEING A GHOST AT ITS OWN FAKE KICK-OFF
═══════════════════════════════════════════════════════════════

This module's first cut required the ghost's advertised kick-off to be in the
FUTURE, reasoning that "a row nobody is being shown as upcoming is not this
defect". That premise is false, and it was refuted by our own screenshot before
it ever ran: on the league page a ``scheduled`` row with no score whose kick-off
has passed is not gone, it is PROMOTED — it leaves *Upcoming* and renders under
**Live & Paused** reading "No result reported", while the real result sits one
rail below (lane1/288's 17:02Z production shot for #5918, and on 2026-09-13 the
served La Liga payload carried three such rows: 15310513, 15308732, 15308726).

So the rule cost the ten measured ghosts of 2026-09-13 nothing at 18:00Z and
everything at 19:01Z, and it did it silently: they would have aged out of the
selector into a *worse* card and stayed on the page for the rest of the -5d
population window. What makes a row a ghost is that a scored, fixture-anchored
twin of it exists within :data:`MAX_GHOST_LAG` — a fact about two rows, not
about the hour. The clock now buys only :data:`GHOST_KICKOFF_GRACE`, which is
the one thing it was ever actually protecting.

None of the three gates that keep a real fixture visible moved: the ghost must
still carry no score and no authority fixture id, the canonical must still carry
both, the pair must still sit inside the measured three-day window, and a block
that cannot resolve to exactly one of each is still refused.

THE NAME KEY IS DELIBERATELY THE NARROW ONE
════════════════════════════════════════════

The block key folds case and surrounding whitespace and nothing else. It does
NOT strip diacritics and does not normalise punctuation, even though
``app.utils.name_normalization`` is right there and the canonical spells its
clubs the same way the ghost does today.

That is on purpose. The precision evidence above — zero genuine rematches in a
year — was measured with ``lower(btrim())`` on both sides, and a looser key
matches rows that measurement never examined. The cost of the narrow key is a
ghost whose two halves are spelled differently and which we therefore miss; that
is under-tagging, which leaves a duplicate card visible and fixable. The cost of
the loose key is a real fixture we stop printing. The failure directions are not
symmetric, so the key stays where the measurement is.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: The two rows are one fixture and ``ghost_id`` is safe to stop printing.
#: Same vocabulary as :mod:`app.utils.tennis_twin_pairs`, on purpose — an
#: operator reading a refusal should not have to learn two words for one state.
TWIN_FOUND = "TWIN_FOUND"
#: The rows in this block cannot be resolved to exactly one ghost and one real
#: row. Reported, never acted on.
REFUSE_AMBIGUOUS = "REFUSE_AMBIGUOUS"
#: Nothing in this block pairs. The common answer.
NOT_A_TWIN = "NOT_A_TWIN"

#: The greatest gap between the real kick-off and the ghost's advertised time
#: that this module will call a twin. Measured, not chosen — see the module
#: docstring: zero genuine same-orientation rematches inside this window in 365
#: days of production soccer.
MAX_GHOST_LAG = timedelta(days=3)

#: How long after its own advertised kick-off a row is left alone before it may
#: be judged a ghost. A REAL fixture reads ``scheduled`` with no score for the
#: first minutes of its first half, until live ingest catches it, and there is
#: no urgency whatsoever to relabel anything in that window. It is deliberately
#: generous: the cost of waiting is half an hour of a card nobody has looked at
#: yet, and the cost of not waiting is a kicked-off match called a duplicate.
GHOST_KICKOFF_GRACE = timedelta(minutes=30)

#: A row in one of these states has been played and can be a canonical.
#: ``closed`` is StatPal's definitive completion and ``completed`` is everyone
#: else's; both mean the same thing to a reader.
SETTLED_STATUSES = ("completed", "closed")

#: The only state a ghost may be in. Deliberately not ``suspended`` (a live
#: state, live/048) and not ``voided``/``merged`` (already unprintable). Note
#: that ``scheduled`` is a claim the row makes about itself and not a statement
#: about the clock — a ``scheduled`` row whose hour has passed is still being
#: printed, which is the whole of the section on the fake kick-off above.
GHOST_STATUS = "scheduled"


def row_is_fixture_anchored(
    *, espn_id: object, statpal_fixture_id: object
) -> bool:
    """Does an authority that knows this fixture independently of us name it?

    A named function and not a lambda at the call site, because the reading a
    caller reaches for first is wrong in a way that silently refuses every pair:
    ``external_id`` looks like an anchor, is present on both halves of all ten
    measured pairs, and is a per-ingest surrogate that anchors nothing. The
    module docstring carries the measurement; this is the one line that must not
    drift from it.
    """
    return espn_id is not None or statpal_fixture_id is not None


def row_has_final_score(*, home_score: object, away_score: object) -> bool:
    """Has this row been played to a result?

    Both sides, because a soccer row can carry a lone ``home_score`` of 0 mid-
    ingest and 0 is falsy — ``if home_score`` is the bug this exists to prevent.
    """
    return home_score is not None and away_score is not None


def block_key(sport_key: object, home: object, away: object) -> tuple[str, str, str]:
    """The coarse key grouping rows that MIGHT be the same fixture.

    Ordered (home, away), so a two-legged tie's second leg lands in a different
    block and can never pair with its first. Case and surrounding whitespace are
    folded; nothing else is — see the module docstring for why the narrow key is
    the measured one.
    """
    return (
        str(sport_key or "").strip().lower(),
        str(home or "").strip().lower(),
        str(away or "").strip().lower(),
    )


@dataclass(frozen=True)
class SoccerRow:
    """One row's judgement inputs, copied to scalars.

    Frozen scalars rather than an ORM object: the sweep's writer commits per row,
    and an ORM object read across a commit boundary lazy-loads in a sync context
    (gotcha #6). A judgement that reads the database is also a judgement nobody
    can test.
    """

    event_id: int
    sport_key: str
    home_team_name: str
    away_team_name: str
    commence_time: datetime
    status: str
    has_final_score: bool
    is_fixture_anchored: bool


@dataclass(frozen=True)
class GhostTag:
    """One decision: ``ghost_id`` is a second copy of ``canonical_id``."""

    ghost_id: int
    canonical_id: int
    reason: str


@dataclass
class GhostPlan:
    """Everything one pass decided, including what it refused and why."""

    tags: list[GhostTag] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)
    blocks_examined: int = 0
    rows_considered: int = 0


def classify_block(
    rows: list[SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> tuple[str, GhostTag | None, str]:
    """Decide one block. Returns ``(outcome, tag_or_None, explanation)``. Pure.

    The two roles are read off the row, never off the clock alone:

    * a CANONICAL is settled, carries a final score AND is fixture-anchored;
    * a GHOST is ``scheduled``, carries no score, is NOT fixture-anchored, and
      is not inside :data:`GHOST_KICKOFF_GRACE` of its own advertised kick-off.

    The clock decides ONE thing here and it is not whether the row is a ghost.
    A row that is refuted by a scored, fixture-anchored twin of its own within
    :data:`MAX_GHOST_LAG` is a ghost at every hour of the day; the grace exists
    only so that a real match which has just kicked off, and is briefly still
    ``scheduled`` with no score, is never the row we stop printing.

    Anything other than exactly one of each, among the rows that actually pair
    within ``max_lag``, is :data:`REFUSE_AMBIGUOUS`. Two ghosts and one
    canonical is a shape this module has never measured, and guessing which of
    two rows to stop printing is precisely the call it must not make.
    """
    canonicals = [
        r
        for r in rows
        if r.status in SETTLED_STATUSES and r.has_final_score and r.is_fixture_anchored
    ]
    ghosts = [
        r
        for r in rows
        if r.status == GHOST_STATUS
        and not r.has_final_score
        and not r.is_fixture_anchored
        and not (now - GHOST_KICKOFF_GRACE < r.commence_time <= now)
    ]
    if not canonicals or not ghosts:
        return NOT_A_TWIN, None, "no ghost/canonical pair in this block"

    pairs = [
        (ghost, canonical)
        for ghost in ghosts
        for canonical in canonicals
        if timedelta(0) < ghost.commence_time - canonical.commence_time <= max_lag
    ]
    if not pairs:
        return (
            NOT_A_TWIN,
            None,
            f"no ghost sits within {max_lag.days}d after a played row",
        )

    paired_ghosts = {ghost.event_id for ghost, _ in pairs}
    paired_canonicals = {canonical.event_id for _, canonical in pairs}
    if len(paired_ghosts) != 1 or len(paired_canonicals) != 1:
        return (
            REFUSE_AMBIGUOUS,
            None,
            (
                f"{len(paired_ghosts)} candidate ghost(s) and "
                f"{len(paired_canonicals)} candidate real row(s) pair in this "
                f"block — which to stop printing is not decidable"
            ),
        )

    ghost, canonical = pairs[0]
    lag_hours = (ghost.commence_time - canonical.commence_time).total_seconds() / 3600
    return (
        TWIN_FOUND,
        GhostTag(
            ghost_id=ghost.event_id,
            canonical_id=canonical.event_id,
            reason=(
                f"{ghost.home_team_name} v {ghost.away_team_name}: advertised "
                f"{lag_hours:.0f}h after the played row, no score, no fixture id"
            ),
        ),
        "twin",
    )


def plan_ghost_tags(
    rows: list[SoccerRow],
    *,
    now: datetime,
    max_lag: timedelta = MAX_GHOST_LAG,
) -> GhostPlan:
    """Every label this population supports, plus every refusal. Pure.

    Blocks with a single row — the overwhelming majority — cost one dictionary
    insert and are never classified, so the plan's ``blocks_examined`` counts the
    blocks that could conceivably hold a pair. That number, not the number of
    tags, is how this sweep proves it still reaches its population: soccer
    ghosts are episodic (ten on 2026-09-13, zero in the preceding thirty days),
    so a floor on the tag count would refuse the healthy quiet day. The tennis
    sibling can floor its plan because a Slam fortnight always has twins.
    """
    blocks: dict[tuple[str, str, str], list[SoccerRow]] = defaultdict(list)
    for row in rows:
        blocks[block_key(row.sport_key, row.home_team_name, row.away_team_name)].append(
            row
        )

    plan = GhostPlan(rows_considered=len(rows))
    for key, members in sorted(blocks.items()):
        if len(members) < 2:
            continue
        plan.blocks_examined += 1
        outcome, tag, explanation = classify_block(members, now=now, max_lag=max_lag)
        if outcome == TWIN_FOUND and tag is not None:
            plan.tags.append(tag)
        elif outcome == REFUSE_AMBIGUOUS:
            plan.refusals.append(f"{key[0]} {key[1]} v {key[2]}: {explanation}")
    return plan
