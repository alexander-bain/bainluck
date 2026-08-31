"""CAL-P143 — the 12-CAL repair: the curve stops dropping a claim for losing.

LANDS AT ``backend/tests/test_calibration_lost_losses_12cal.py`` together with
``artifacts/cal-p143/12cal-lost-losses.patch``. It is RED against the producer
as it stands today and GREEN against the patched one — which is the only honest
shape for a pre-built regression suite, and is proved both ways by
``artifacts/cal-p143/verify-12cal-suite.py`` (see ``suite-verification.txt``).

WHAT IT GUARDS, AND WHY EACH ONE IS HERE
----------------------------------------
The repair widens ``clean_vms``. Everything that can go wrong with widening a
population gate is a way of admitting a row whose truth we do not have:

* admitting a >=2-outcome virtual market that graded nobody — Queue 299 rung 1's
  UNKNOWN-truth class, which must stay excluded;
* admitting a row whose ``is_winner`` was never written, because ``is_winner``
  is nullable with a False default and "not a winner" therefore spans a graded
  loss and an ungraded row (gotcha #21);
* silently changing what a GROUPED virtual market does, which is the half of
  the gate that was never broken.

So the suite pins the boundary from both sides, in one place
(:func:`assert_repaired_population`), and pins the pure mirror of the SQL arm
against the census instrument's own arm classifier so the producer and the
instrument that measures it cannot drift.

CAL-P155 — THE ARM WENT PER-MARKET, AND THE SUITE'S JOB DID NOT CHANGE
----------------------------------------------------------------------
Alex ruled option A (``alex-inbox/calibration-919``, 2026-08-30), reversing
CAL-P151's option B: the arm now reads ``graded_lone_claims >= 1 AND
ungraded_lone_claims = 0`` over PER-MARKET counts, so two independently-graded
lone claims sharing one virtual variant are each admitted instead of both being
refused for having been counted together.

Every hazard listed above still applies unchanged — the ruling widens the gate
again, and widening a population gate is still exactly the operation that can
admit a row whose truth we do not have. Two additions:

* ``ungraded_lone_claims = 0`` is the fail-closed conjunct that replaces the
  retired ``graded >= 1``, and it is pinned as hard as its predecessor was.
  Nothing downstream can catch a single-outcome market nothing ever graded:
  rung 1 requires ``n_outcomes >= 2`` on purpose.
* The change must be a pure WIDENING. Every variant the retired per-variant arm
  admitted must still be admitted, or option A is not "more correct by D13's own
  argument", it is a different rule that also drops rows
  (:func:`test_option_a_only_widens_it_never_takes_a_variant_away`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import calibration_missing_loser_census as mlc  # noqa: E402

from app.tasks.precompute_calibration import (  # noqa: E402
    _calibration_population_ctes,
    _main_input_fingerprint,
    market_has_no_winner_authority,
)

#: Ruling 054: a change that moves the published number declares the movement
#: BEFORE it lands. Two of the three are certain by construction — the repair
#: only ever ADDS rows, and every row it adds is a loss.
#:
#: The third is NOT, and saying so is the point. "It makes our number worse" is
#: the sentence that held 12-CAL from CAL-P122 to CAL-P143, and it is true on
#: one cell and false on the next: kalshi/entertainment 5.21 -> 6.30 (worse by
#: 1.09), polymarket/economics 3.90 -> 3.68 (better by 0.22). Two cells, two
#: sources, opposite signs. Declaring a direction here would be declaring a
#: guess, so the declaration is that the direction is unknown and the landing
#: must MEASURE it — see artifacts/cal-p143/GENERALITY-12CAL.md.
DECLARED_MOVEMENT = {
    "published_rows": "increase",
    "restored_class_win_rate": 0.0,
    "headline_ece": "unknown_direction",
}


#: A CTE terminates on its own line at the chain's twelve-space indent. Splitting
#: on a bare ``"),"`` — which is what the CAL-P122 suite does — truncates the
#: body at the first parenthesised aside inside a COMMENT, and it did: it cut
#: ``vm_stats`` off above the column this repair adds and reported the column
#: missing. The terminator is a line, so match a line.
_CTE_END = "\n            ),"


def _cte_body(sql: str, name: str) -> str:
    """The EXECUTABLE text of one CTE, so a predicate is pinned to ITS OWN clause.

    A whole-string search cannot tell ``clean_vms``'s gate from the identical
    words in another CTE — that exact mutation survived the first draft of the
    CAL-P122 suite and is why this helper exists.

    🔴 COMMENTS ARE STRIPPED, AND CAL-P155 LEARNED WHY THE HARD WAY. This helper
    used to return the raw slice, so every assertion below was satisfiable by
    PROSE. The arm's own comment block necessarily quotes the predicate it is
    explaining — both the shipped one and the retired one — so
    ``"ungraded_lone_claims = 0" in gate`` passed off the paragraph describing
    it, and ``"market_count = 1" not in gate`` FAILED against a correct
    implementation because the comment says what the retired arm used to read.
    A guard over commented SQL is a guard over the documentation.

    ``strip_sql_comments`` is the repo's own scanner (built for #2076): it knows
    a ``--`` inside a string literal is data and that block comments nest, so it
    is safe on this chain in a way a regex is not.
    """
    from app.utils.sql_comment_strip import strip_sql_comments

    assert f"{name} AS (" in sql, f"{name} is gone from the population chain"
    return strip_sql_comments(sql.split(f"{name} AS (", 1)[1].split(_CTE_END, 1)[0])


def assert_repaired_population(sql: str) -> None:
    """Every structural claim the repair makes, over a built population chain.

    Taken as a function rather than a test so the pre-landing verifier can run
    the identical assertions against the PATCHED producer while the suite in
    the tree still reads the real one.
    """
    gate = _cte_body(sql, "clean_vms")

    # 1. The grouped carrier is untouched: one winner anywhere in a virtual
    #    market still carries its losers onto the curve.
    assert "has_winner >= 1" in gate

    # 2. The bare gate is GONE. Pinned as absence, not as presence of the new
    #    text: a partial revert that restores the old line while leaving the new
    #    comment block behind would pass a presence-only check. Over the
    #    EXECUTABLE chain for the same reason `_cte_body` strips — an absence
    #    check against commented SQL fails on prose that merely quotes the thing
    #    it is telling you was removed.
    from app.utils.sql_comment_strip import strip_sql_comments

    assert mlc.CLEAN_VMS_GATE_RETIRED not in strip_sql_comments(sql), (
        "clean_vms still carries the bare `eligible >= 1 AND has_winner >= 1` "
        "gate — the 12-CAL repair is not in this build."
    )

    # 3. The restored arm is present, in clean_vms, spelled the way the census
    #    instrument's mirror says it is.
    assert mlc.RESTORED_ARM_SQL in gate
    assert mlc.CLEAN_VMS_GATE_FRAGMENT in gate

    # 4. BOTH conjuncts. CAL-P155 / D13 option A (Alex 2026-08-30) replaced the
    #    three per-VARIANT conjuncts with two PER-MARKET ones; dropping either is
    #    a different, wider and wrong rule, and each failure mode is named.
    assert "graded_lone_claims >= 1" in gate, (
        "would admit a variant with no scoreable lone claim in it at all"
    )
    assert "ungraded_lone_claims = 0" in gate, (
        "would publish never-graded lone claims as losses — no downstream rung "
        "catches a single-outcome market (rung 1 requires n_outcomes >= 2)"
    )
    # 4b. And the retired per-VARIANT conjuncts are GONE from the arm. Pinned as
    #     absence for the same reason clause 2 is: a partial revert that leaves
    #     the old counts in an OR beside the new ones re-creates neither rule.
    assert "market_count = 1" not in gate, (
        "the per-VARIANT count is back in the arm — that is option B, and Alex "
        "ruled option A (alex-inbox/calibration-919)"
    )

    # 5. The two counts are PER MARKET and mean what the arm needs.
    #    `graded` (per-variant, affirmative) still exists and is still correct;
    #    it is simply no longer what the arm reads.
    stats = _cte_body(sql, "vm_stats")
    assert "COUNT(*) FILTER (WHERE fo.is_winner IS NOT NULL) AS graded" in stats, (
        "graded must be the is_winner-IS-NOT-NULL count; anything else lets a "
        "row nothing ever graded publish as a confident loss"
    )
    for col, grade in (("graded_lone_claims", "fo.is_winner IS NOT NULL"),
                       ("ungraded_lone_claims", "fo.is_winner IS NULL")):
        frag = (
            "COUNT(DISTINCT fo.market_id) FILTER (\n"
            "                        WHERE mrs.n_outcomes = 1\n"
            f"                          AND {grade}) AS {col}"
        )
        assert frag in stats, (
            f"{col} must be a PER-MARKET count over `mrs.n_outcomes = 1`. A "
            f"variant-grained count cannot express 'this variant holds a lone "
            f"claim' without also asserting nothing else shares the variant, "
            f"which is exactly the coupling option A removes."
        )
    # And the join that supplies `mrs` cannot change which rows vm_stats
    # aggregates (ruling 125: a join added to a population CTE must not be able
    # to delete a row).
    assert "LEFT JOIN market_result_shape mrs ON mrs.market_id = vm.market_id" in stats

    # 6. Queue 299 rung 1 is untouched and still owns the UNKNOWN-truth class,
    #    and the publish filter still applies it. The repair defers to rung 1;
    #    it does not replace it.
    nwm = _cte_body(sql, "no_winner_markets")
    assert "n_outcomes >= 2" in nwm and "win_count = 0" in nwm
    assert "NOT ro.is_no_winner_market" in sql
    assert "NOT ro.is_orphan_partition" in sql


# ---------------------------------------------------------------------------
# 1. The producer
# ---------------------------------------------------------------------------

def test_the_lone_claim_gate_is_repaired():
    assert_repaired_population(_calibration_population_ctes())


def test_the_repair_is_in_the_headline_chain_and_every_horizon():
    """The population builder is called with several price expressions; the
    repair must not be conditional on any of them."""
    for kwargs in ({}, {"market_info_extra": "AND fm.source = 'kalshi'"}):
        assert_repaired_population(_calibration_population_ctes(**kwargs))


# ---------------------------------------------------------------------------
# 2. The boundary, as a pure function — the producer and the instrument that
#    measures it, held to ONE definition.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "glc,ulc,restorable,why",
    [
        (1, 0, True, "the solitary lone claim: one market, one graded outcome"),
        (2, 0, True, "🔴 OPTION A. Two independently-graded lone claims sharing "
                     "one variant. The retired per-VARIANT arm saw "
                     "market_count = 2 and refused BOTH; each is individually "
                     "'a complete, scoreable prediction' by this arm's own "
                     "argument (Alex 2026-08-30)"),
        (7, 0, True, "the count of scoreable claims is not a reason to refuse"),
        (0, 0, False, "no lone claim at all"),
        (0, 1, False, "never graded — not a loss, UNKNOWN (gotcha #21)"),
        (1, 1, False, "FAIL-CLOSED: one ungraded member refuses the variant. "
                      "Refusing a scoreable row costs coverage; publishing "
                      "unknown truth as a loss corrupts the curve"),
        (5, 2, False, "and it is `= 0`, not a ratio"),
    ],
)
def test_the_restored_arm_boundary(glc, ulc, restorable, why):
    assert mlc.lone_claim_is_restorable(glc, ulc) is restorable, why


def test_the_restored_arm_is_exactly_the_censuss_defect_arm():
    """The class the instrument called ``B_lone_claim`` is the class the
    producer now publishes — the same boundary, not a similar one.

    If these two ever disagree, the measured 432 stops being the number that
    lands, and the CAL-P122 fold stops predicting the curve.
    """
    for glc in range(0, 5):
        for ulc in range(0, 5):
            arm = mlc.classify_vm(glc, ulc)
            restorable = mlc.lone_claim_is_restorable(glc, ulc)
            assert (arm == mlc.ARM_LONE) is restorable, (glc, ulc, arm)


def test_option_a_only_widens_it_never_takes_a_variant_away():
    """The retired arm's whole population must survive the ruling.

    The retired arm was ``market_count = 1 AND total_outcomes = 1 AND
    graded >= 1``. Those three conjuncts describe exactly one shape: a variant of
    ONE member market carrying ONE captured outcome, and that outcome graded. In
    the new columns that shape is ``graded_lone_claims = 1`` and
    ``ungraded_lone_claims = 0`` — ``mrs.n_outcomes`` and ``total_outcomes``
    count the same outcomes for a single-market variant.

    So the retired population maps to a single point, and the new arm must admit
    it. If it ever does not, option A stopped being a widening and started being
    a swap, and the declared movement below ("increase") would be a false
    statement about a change that also removes published rows.
    """
    assert mlc.lone_claim_is_restorable(1, 0) is True

    # The other direction is the ruling itself, and it is asserted as a
    # DIFFERENCE so the two arms cannot quietly become the same rule again.
    assert mlc.lone_claim_is_restorable(2, 0) is True, (
        "two graded lone claims in one variant is precisely the population the "
        "retired arm refused; if this is False the ruling was not applied"
    )


def test_the_arm_reads_a_variant_as_a_bag_of_markets_not_as_one_unit():
    """The single behavioural difference option A makes, stated as a property.

    Per-VARIANT counting made a lone claim's admission depend on how many OTHER
    markets happened to land in the same virtual variant. Per-MARKET counting
    must not: adding more graded lone claims can never turn admission off.
    """
    for extra in range(0, 6):
        assert mlc.lone_claim_is_restorable(1 + extra, 0) is True, (
            f"admission flipped off after {extra} graded siblings were added — "
            f"that is the per-variant coupling Alex ruled out"
        )


def test_rung_one_still_declines_the_lone_claim_and_still_owns_the_rest():
    """The carve-out that was a dead letter is now reachable — and it still
    says the same thing it always said."""
    assert market_has_no_winner_authority(1, 0) is False
    assert market_has_no_winner_authority(2, 0) is True
    assert market_has_no_winner_authority(9, 0) is True


# ---------------------------------------------------------------------------
# 3. What landing costs, declared in advance
# ---------------------------------------------------------------------------

def test_landing_invalidates_the_banked_futures_units():
    """Ruling 054's other half: the operator must not be surprised.

    ``_calibration_population_ctes`` is hashed into ``_main_input_fingerprint``,
    and a fingerprint change is ``REASON_INPUT_FINGERPRINT`` — 'THE one that
    fires in practice ... costs every banked unit'. So this repair discards the
    staged futures bank and the next census promotion is a full rebuild away.
    This test does not prevent that; it makes it impossible to land without
    having read it.
    """
    import inspect

    src = inspect.getsource(_main_input_fingerprint)
    assert "_calibration_population_ctes" in src
    assert _main_input_fingerprint()  # non-empty digest


def test_the_declared_movement_is_an_addition_of_losses():
    assert DECLARED_MOVEMENT["published_rows"] == "increase"
    assert DECLARED_MOVEMENT["restored_class_win_rate"] == 0.0
    assert DECLARED_MOVEMENT["headline_ece"] == "unknown_direction", (
        "measured worse on kalshi/entertainment and better on "
        "polymarket/economics — a declared direction here would be a guess"
    )


# ---------------------------------------------------------------------------
# 4. The instrument the repair obsoletes says so, loudly
# ---------------------------------------------------------------------------

def test_the_census_now_reads_as_a_reconciliation():
    """gotcha #53: an instrument whose defect is fixed must not print a zero as
    though it were a measurement."""
    assert mlc.CENSUS_MODE_AFTER_REPAIR == "reconciliation"
    assert mlc.CLEAN_VMS_GATE_FRAGMENT != "AND has_winner >= 1"
