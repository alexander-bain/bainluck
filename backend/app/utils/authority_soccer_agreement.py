"""Soccer's join strategy for the D50 agreement row. #3366.

## Why soccer cannot use the default join, in one number

`authority_agreement.pair_by_normalized_key` is a KEY join: two sides meet when
`normalize(away)|normalize(home)` is character-for-character equal. That is
exactly the rule :mod:`app.utils.soccer_team_matching` was written because soccer
fails — measured over the pinned two-day corpus, equality after normalization
joins **17 of our 90** rows and the soccer rule joins **67**. A row published on
the key join would report soccer's identity at ~19% and call it a disagreement
with StatPal, when the disagreement is between our spelling and theirs.

So the strategy here joins on the SAME relation the stamper writes on:
:func:`app.utils.soccer_team_matching.soccer_pair_matches` in the same
orientation, within :data:`SOCCER_MATCH_WINDOW`. That coupling is the point and
not an accident — a ledger row measured by a looser or tighter rule than the one
that writes the links is measuring the gap between two definitions rather than
the gap between two providers.

## It refuses exactly what the stamper refuses

The stamper's contract (`soccer_team_matching`, "the caller's contract") is
*refuse anything but exactly one match*. A fixture that reaches two of our rows
is neither agreement nor disagreement: it is a claim nobody may make, and D35
says it is filed, not resolved. Dropping it into `statpal_only` would publish
*"StatPal has a match we do not"* about a match we have twice.

Both directions are refused, and they are counted apart because they are
different bugs with different owners:

  * :data:`REFUSAL_TWO_ROWS` — one StatPal fixture, two of our rows. A duplicate
    of ours (#2693, #3813).
  * :data:`REFUSAL_TWO_FIXTURES` — one of our rows, two StatPal fixtures. A
    duplicate on the board, or a name so short it reaches two clubs.

Measured on the live boards + production at 2026-09-07 06:30Z, both are **zero**
over 972 distinct fixtures against 108 of our rows — which is the expected
reading and is exactly why the names are declared in
:data:`SOCCER_REFUSAL_NAMES` rather than appearing only when they fire (#3275).

## It cannot answer `same_game_on_our_side`, and says so

`Join` requires a CONSERVATIVE bucket key alongside that predicate — a key that
never separates two rows the predicate would join. Soccer's relation is a token
SUBSET plus an initialism tier, and neither has one: `Wrexham` joins
`Wrexham AFC`, `PSG` joins `Paris Saint Germain`. Any key coarse enough to hold
those holds most of the board. Tennis is the standing precedent for a strategy
that leaves both `None`, and the published `null` reads as *not measured*, which
is the honest answer. Inventing zeros would read as *measured, no duplicates*
about a sport whose duplicates are a filed, open finding (#3813).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Sequence

from app.utils.authority_agreement import Join, Side
from app.utils.soccer_team_matching import (
    CLUB_FORM_TOKENS,
    soccer_pair_matches,
    soccer_tokens,
)

#: How far apart a StatPal kickoff and ours may be and still be one fixture.
#:
#: The same hour the stamper uses, and deliberately the same CONSTANT would be
#: wrong: `stamp_v1_statpal_fixtures.MATCH_WINDOW` is bounded by the closest two
#: meetings of one pair in the leagues IT serves, and soccer's binding case is
#: its own — the corpus carries `Liverpool U19 v Atl. Madrid U19` five hours
#: before `Liverpool v Atl. Madrid`, so the window is what stands between a
#: named reserve side and a wrong claim. Stated here so the argument is made for
#: soccer rather than inherited from basketball.
SOCCER_MATCH_WINDOW = timedelta(hours=1)

#: One StatPal fixture reached two of our rows. Ours is the duplicate.
REFUSAL_TWO_ROWS = "soccer_two_of_our_rows"
#: One of our rows was reached by two StatPal fixtures. Theirs is the duplicate,
#: or a name short enough to reach two clubs.
REFUSAL_TWO_FIXTURES = "soccer_two_statpal_fixtures"

#: Every refusal this strategy can EVER emit, declared whether or not today's
#: data made it emit one, so `excluded` is keyed by the vocabulary and a zero
#: means *measured, none* rather than *not reported* (#3275).
SOCCER_REFUSAL_NAMES: tuple[str, ...] = (REFUSAL_TWO_ROWS, REFUSAL_TWO_FIXTURES)

SOCCER_DENOMINATOR_IS = (
    "distinct fixtures under the union of both sides, joined where "
    "`soccer_pair_matches` holds in the same orientation and the kickoffs are "
    "within 1h; a fixture reaching two rows, or a row reached by two fixtures, "
    "is refused and excluded rather than counted either way"
)


def names_a_club(side: Side) -> bool:
    """Does this side name two clubs at all, or is it unusable?

    The same test `soccer_team_matches` applies before it compares anything: a
    name whose tokens are nothing but club-form words (`FC`, `AFC`, `de`)
    identifies no club, and neither does a blank. Asked here so an unusable side
    is published as `unusable_*` — a side silently dropped would move a
    denominator without leaving a count behind.
    """
    for name in (side.home, side.away):
        if not (set(soccer_tokens(name)) - CLUB_FORM_TOKENS):
            return False
    return True


def _receipt(side: Side, others: Sequence[Side]) -> dict[str, Any]:
    """One refusal, with enough in it to act on rather than only to count."""
    return {
        "ref": side.ref,
        "teams": [side.away, side.home],
        "start": side.start.isoformat() if side.start else None,
        "reached": [
            {
                "ref": o.ref,
                "teams": [o.away, o.home],
                "start": o.start.isoformat() if o.start else None,
                "held_id": o.held_id,
            }
            for o in others
        ],
    }


def pair_soccer_sides(
    fixtures: Sequence[Side],
    rows: Sequence[Side],
    normalize,  # accepted and ignored — see JoinStrategy
) -> Join:
    """Join soccer's two sides on the stamper's own rule. See the module docstring.

    `normalize` is in the signature because every join strategy has one call
    shape; this one does not use it, because the fold it would apply is already
    inside `soccer_tokens`.
    """
    usable_f = [f for f in fixtures if names_a_club(f)]
    usable_r = [r for r in rows if names_a_club(r)]

    #: Every (fixture, row) the relation admits, computed once. Quadratic in the
    #: usable sides, which is what the relation costs — it is not a key and
    #: cannot be bucketed (see the module docstring), so there is nothing to
    #: index on. Sized rather than assumed: the live boards carry ~970 fixtures
    #: against ~110 of our rows, so ~107k pair tests per pass, and the pass runs
    #: at most hourly.
    reach_f: dict[int, list[int]] = {i: [] for i in range(len(usable_f))}
    reach_r: dict[int, list[int]] = {j: [] for j in range(len(usable_r))}
    for i, f in enumerate(usable_f):
        if f.start is None:
            continue
        for j, r in enumerate(usable_r):
            if r.start is None:
                continue
            if abs(f.start - r.start) > SOCCER_MATCH_WINDOW:
                continue
            if soccer_pair_matches((f.home, f.away), (r.home, r.away)):
                reach_f[i].append(j)
                reach_r[j].append(i)

    refusals: dict[str, list[dict[str, Any]]] = {}
    left_out_f: set[int] = set()
    left_out_r: set[int] = set()

    for i, js in reach_f.items():
        if len(js) > 1:
            refusals.setdefault(REFUSAL_TWO_ROWS, []).append(
                _receipt(usable_f[i], [usable_r[j] for j in js])
            )
            left_out_f.add(i)
            left_out_r.update(js)
    for j, is_ in reach_r.items():
        if len(is_) > 1:
            refusals.setdefault(REFUSAL_TWO_FIXTURES, []).append(
                _receipt(usable_r[j], [usable_f[i] for i in is_])
            )
            left_out_r.add(j)
            left_out_f.update(is_)

    paired: list[tuple[Side, Side]] = []
    paired_f: set[int] = set()
    paired_r: set[int] = set()
    # Sorted rather than left to dict order so the receipts a pass publishes are
    # a function of the data and not of insertion order — #3628's lesson, which
    # cost three sports a stable receipt list.
    for i in sorted(reach_f):
        js = reach_f[i]
        if i in left_out_f or len(js) != 1:
            continue
        (j,) = js
        if j in left_out_r or len(reach_r[j]) != 1:
            continue
        paired.append((usable_f[i], usable_r[j]))
        paired_f.add(i)
        paired_r.add(j)

    return Join(
        fixtures=[f for i, f in enumerate(usable_f) if i not in left_out_f],
        rows=[r for j, r in enumerate(usable_r) if j not in left_out_r],
        paired=paired,
        statpal_only=[
            f
            for i, f in enumerate(usable_f)
            if i not in left_out_f and i not in paired_f
        ],
        ours_only=[
            r
            for j, r in enumerate(usable_r)
            if j not in left_out_r and j not in paired_r
        ],
        unusable_fixtures=[f for f in fixtures if not names_a_club(f)],
        unusable_rows=[r for r in rows if not names_a_club(r)],
        refusals=refusals,
        refusal_names=SOCCER_REFUSAL_NAMES,
        denominator_is=SOCCER_DENOMINATOR_IS,
        # `same_game_on_our_side` and `our_side_bucket_key` are BOTH left unset.
        # See the module docstring: soccer's relation is not a key, so no
        # conservative bucket exists, and `Join.__post_init__` refuses half the
        # contract. `null` reads as not measured, which is true.
    )
