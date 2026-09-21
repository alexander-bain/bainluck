"""#4680 — the longest-coherent-run DP keeps a frontier, so it stops naming a rung the ladder agrees with.

PILLAR: TRUTH. SHIP: a Discover ladder card stops deleting a bar whose price its
own neighbours agree with.

Filed by CERT-2451 while grading #4610, re-verified live on master before build.
`incoherent_ladder_verdict` names "every priced rung outside the longest coherent
run" — so the drop set is only as honest as the run is long. The run was computed
with ONE state per endpoint, `(best_length[i], bound[i])`, tie-broken longest-first.

`_LADDER_MONOTONE_TOLERANCE` is not transitive, so "longest" and "still joinable"
are independent axes: a rung can fit a SHORTER run and not a longer one, because
the longer run has already pulled its running extreme past it. One state per
endpoint has to pick an axis, and picking length discards the bound a later rung
needed. The complement is then over-broad, and the over-broad half is what a
reader loses: a bar is removed from a card because of an arithmetic contradiction
that is not there.

THE SPECIMEN (the grader's, reproduced against the live function at `51b387480`):

    Above 10  .10    <- the only rung that contradicts anything
    Above 20  .115
    Above 30  .13
    Above 40  .125
    Above 50  .12

    before: dropped {0, 1}, 3 bars drawn
    after : dropped {0},    4 bars drawn

Rungs 1-4 are a coherent run of four — fed to the same function ALONE they lose
nothing (`test_the_rescued_run_is_coherent_on_its_own`, the assertion that stops
this suite from simply encoding a preferred answer). The old code ended rung 1 on
the run `0->1`, whose running minimum is .10, so rung 2 at .13 could not join
(.13 > .12) and a run of three won.

═══ WHAT THIS SHIP IS NOT ═══

**The issue's second claim is INERT and is not tested here, because it cannot
happen.** #4680 says an over-broad drop set can also make a ladder refuse its own
treatment via `ladder_treatment_collapsed`. It cannot: survivors are exactly the
run length, `LADDER_MIN_DRAWN_RUNGS` is 2, and the one-state DP can only return a
run of 1 when NO pair of rungs fits at all — in which case the frontier returns 1
too. Measured over 400,000 random ladders (uniform, and near-monotone with
bid/ask noise), old-vs-new: **0 collapse-refusal flips**, 0 cases where the new
run is shorter, 0 where the named run is not genuinely coherent, and 4 where the
new run is strictly longer. Writing a collapse test would have been a test that
passes for the wrong reason.

That rarity is the honest scope: this is a correctness fix on a DEFENSIVE path,
not a population repair. Production incidence is unmeasured — a census belongs to
the measurement lane, and no ship is waiting to spend one.
"""

import random

import pytest

from app.utils.outcome_display import (
    LADDER_MIN_DRAWN_RUNGS,
    drop_incoherent_ladder_outcomes,
    incoherent_ladder_verdict,
    ladder_treatment_collapsed,
)

_TOLERANCE = 0.02

# The grader's counterexample. Falling ladder: a higher threshold is harder, so
# probability descends and `Above 10` at .10 under `Above 20` at .115 is the
# reversal a reader can point at.
_SPECIMEN = [
    ("Above 10", 0.10),
    ("Above 20", 0.115),
    ("Above 30", 0.13),
    ("Above 40", 0.125),
    ("Above 50", 0.12),
]


def _name(row):
    return row[0]


def _prob(row):
    return row[1]


def _verdict(rows):
    return incoherent_ladder_verdict(rows, _name, _prob)


def test_the_agreeing_rung_is_not_named_impossible():
    """The ship. Only rung 0 contradicts the ladder, so only rung 0 is named."""
    dropped, priced = _verdict(_SPECIMEN)

    assert priced == 5, "all five rungs are priced; a change here moves the denominator"
    assert dropped == {0}, (
        "the DP named a rung the ladder agrees with: "
        f"{sorted(dropped)}. Rungs 1-4 are a coherent run of four."
    )


def test_the_reader_gets_the_fourth_bar_back():
    """Why it matters: the drop set is a bar the card does or does not draw."""
    drawn = [_name(row) for row in drop_incoherent_ladder_outcomes(_SPECIMEN, _name, _prob)]

    assert drawn == ["Above 20", "Above 30", "Above 40", "Above 50"]
    assert "Above 20" in drawn, "the rescued rung must reach the reader, not just the verdict"
    assert "Above 10" not in drawn, "the genuinely impossible rung is still dropped"


def test_the_rescued_run_is_coherent_on_its_own():
    """Not a preferred answer — the survivors really are a coherent ladder.

    Fed back through the same function alone they lose nothing, which is the
    definition the verdict is supposed to be maximising. Without this, the suite
    above would pass just as well for an implementation that dropped fewer rungs
    by being wrong in the other direction.
    """
    survivors = drop_incoherent_ladder_outcomes(_SPECIMEN, _name, _prob)

    assert len(survivors) == 4
    assert _verdict(survivors)[0] == set(), (
        "the run the fix rescued is not actually coherent, so the fix traded an "
        "over-broad answer for an under-broad one"
    )


def test_a_rung_that_contradicts_every_run_is_still_named():
    """The control in the other direction: the filter still filters.

    CERT-2451's own specimen. `Above 10` at .20 under two rungs near .9 is a
    reversal of 70 points; the coherent run is one rung, so the verdict names the
    rest and `ladder_treatment_collapsed` refuses the bars rather than drawing an
    unattributable single rung.
    """
    grader = [("Above 10", 0.20), ("Above 20", 0.90), ("Above 30", 0.95)]
    dropped, priced = _verdict(grader)

    assert dropped, "a 70-point reversal must still be caught"
    assert priced - len(dropped) < LADDER_MIN_DRAWN_RUNGS
    assert ladder_treatment_collapsed(grader, _name, _prob) is True
    assert drop_incoherent_ladder_outcomes(grader, _name, _prob) == grader, (
        "a collapse drops NOTHING and lets the surface refuse the treatment (#4610)"
    )


def test_a_clean_ladder_is_untouched():
    """Vacuity guard: the function must still be capable of returning nothing."""
    clean = [("Above 10", 0.90), ("Above 20", 0.60), ("Above 30", 0.30)]

    assert _verdict(clean)[0] == set()
    assert drop_incoherent_ladder_outcomes(clean, _name, _prob) == clean


@pytest.mark.parametrize("seed", [4680, 46801, 46802])
def test_the_named_run_is_always_genuinely_coherent(seed):
    """The property, over random ladders: the verdict never names a rung that
    the survivors' own running extreme admits.

    This is the assertion that survives a future rewrite of the DP. It is
    deliberately a PROPERTY and not a second specimen: the failure this suite
    exists for was invisible to every specimen anyone had, and was found by
    reasoning about the tolerance rather than by looking at a card.
    """
    rng = random.Random(seed)

    exercised = 0
    for _ in range(400):
        count = rng.randint(3, 8)
        base = sorted((rng.uniform(0.02, 0.98) for _ in range(count)), reverse=True)
        rows = [
            (f"Above {10 * (index + 1)}", round(min(1.0, max(0.0, value + rng.uniform(-0.03, 0.03))), 3))
            for index, value in enumerate(base)
        ]

        dropped, priced = _verdict(rows)
        if not dropped:
            continue
        exercised += 1

        survivors = [row for index, row in enumerate(rows) if index not in dropped]
        if len(survivors) < LADDER_MIN_DRAWN_RUNGS:
            continue

        bound = None
        for _, probability in survivors:
            if bound is None:
                bound = probability
                continue
            assert probability <= bound + _TOLERANCE, (
                f"the surviving rungs are not a coherent run: {survivors}"
            )
            bound = min(bound, probability)

    assert exercised, "no ladder in this sample had a reversal — the property never ran"
