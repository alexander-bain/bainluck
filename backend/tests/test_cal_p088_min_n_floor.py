"""CAL-P088 (#2111, RULING 124) — the twin's key carries ``price_moved``, and the
in-scope miss rule gets a MIN-N FLOOR.

Two changes, one code path, and they are tested together because they interact:
the floor reads an ``n`` that #2111 was silently discarding.

#2111 — the collapsed dimension
-------------------------------
``reconcile`` keyed the published side on ``(source, category)`` + ``bucket_idx``.
The payload's bucket rows are keyed on FOUR dimensions; the fourth is
``price_moved``. MEASURED against the live payload 2026-08-23:

===============================================  =========  =========
key                                              distinct   collapsed
===============================================  =========  =========
``source, category, bucket_idx``                     1,483        455
``+ price_moved``                                    1,938          0
``+ is_nonexclusive_bundle``                         1,938          0
===============================================  =========  =========

So ``price_moved`` is the whole of the missing key — the producer merges the
bundle rows back on the original four keys in Python, which is why the served
payload carries no ``is_nonexclusive_bundle`` field at all. The 455 overwritten
rows took their ``n`` with them, which is why ``scope.outcomes_published`` read
**526,462 against a payload total of 869,978 — 39.5% short**.

RULING 124 — the floor
----------------------
CAL-P086B made an in-scope published cell with no twin row force ``disagrees``.
That was right: before it, a fold that produced NOTHING read as agreement, so
Gate 5 could be met by a timeout. But the rule is not tolerance-scaled, so one
thin bucket forces ``disagrees`` at any bound. The floor discounts ``n <= 2``
from the VERDICT while still REPORTING it.

The floor's legitimacy rests on one measured fact, pinned below: **159 of the
608 in-scope keys are thin, so 449 survive** and Gate 0 still reads RED. A floor
that could turn the gate green would be an escape hatch, not a threshold.
"""

from __future__ import annotations

import json
import pathlib

from app.utils.calibration_published_twin import (
    MIN_IN_SCOPE_N_FLOOR,
    VERDICT_AGREES,
    VERDICT_DISAGREES,
    fold_rows_to_cells,
    normalize_price_moved,
    reconcile,
)

# A disclosure earning a loose, definitely-not-None bound, so no assertion below
# is accidentally testing the tolerance path instead of the key/floor path.
STAGED_WIDE = {
    "measured": True,
    "units_banked": 100,
    "units_drifted": 100,
    "units_drift_unknown": 0,
}


def _cell(rate: float, n: int = 100) -> dict:
    return {"n": n, "winners": int(round(rate * n)), "sum_prob": rate * n}


def _pub(source, category, bucket, rate, *, price_moved=None, n=100) -> dict:
    return {
        "source": source,
        "category": category,
        "bucket_idx": bucket,
        "price_moved": price_moved,
        "n": n,
        "winners": int(round(rate * n)),
    }


# =============================================================================
# #2111 — both sides carry price_moved
# =============================================================================
class TestThePriceMovedDimension:
    def test_two_strata_on_one_cell_are_two_buckets_not_one(self):
        """The charter fixture the issue asks for: both ``price_moved`` strata
        present on ONE cell. Keyed on three dimensions the second row overwrote
        the first — rate and n — and the comparison silently became
        pooled-DB-rate vs one-arbitrary-stratum."""
        db_cells = fold_rows_to_cells(
            [
                _row("kalshi", "nba", 5, price_moved=True, n=60, winners=30),
                _row("kalshi", "nba", 5, price_moved=False, n=40, winners=36),
            ]
        )
        assert set(db_cells) == {("kalshi", "nba")}
        assert set(db_cells[("kalshi", "nba")]) == {(5, True), (5, False)}

        out = reconcile(
            db_cells=db_cells,
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.50, price_moved=True, n=60),
                _pub("kalshi", "nba", 5, 0.90, price_moved=False, n=40),
            ],
            staged=STAGED_WIDE,
        )
        # Two comparisons, not one, and the CELL count is still 1 — the cell key
        # deliberately did not gain the dimension.
        assert out["compared"] == 2
        assert out["cells_db"] == 1 and out["cells_published"] == 1
        assert out["published_only"] == []
        assert out["db_only"] == []
        assert out["verdict"] == VERDICT_AGREES

    def test_the_two_strata_are_compared_against_their_OWN_twin_row(self):
        """The defect was not merely losing a row — it was comparing the wrong
        pair. Here the two strata have very different rates; if the key collapsed,
        one of them would be graded against the other's twin and the deltas would
        not both be ~0."""
        db_cells = fold_rows_to_cells(
            [
                _row("kalshi", "nba", 5, price_moved=True, n=60, winners=6),
                _row("kalshi", "nba", 5, price_moved=False, n=40, winners=36),
            ]
        )
        out = reconcile(
            db_cells=db_cells,
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.10, price_moved=True, n=60),
                _pub("kalshi", "nba", 5, 0.90, price_moved=False, n=40),
            ],
            staged=STAGED_WIDE,
        )
        # Each stratum matched its OWN twin, so every delta is 0. Had the key
        # collapsed, one of the two would have been graded against the other's
        # published rate and the worst delta would be 80 pp — this assertion is
        # the difference between "compared two things" and "compared the RIGHT
        # two things".
        assert out["compared"] == 2
        assert out["worst_delta_pp"] == 0.0
        assert out["outside"] == []

    def test_outcomes_published_matches_the_payload_total_with_no_shortfall(self):
        """Acceptance criterion 2. Under the old key the second row's ``n`` was
        discarded, so the scope census undercounted by that row's size."""
        published = [
            _pub("kalshi", "nba", 5, 0.50, price_moved=True, n=60),
            _pub("kalshi", "nba", 5, 0.90, price_moved=False, n=40),
            _pub("polymarket", "politics", 2, 0.20, price_moved=True, n=25),
        ]
        payload_total = sum(r["n"] for r in published)
        out = reconcile(
            db_cells={}, published_buckets=published, staged=STAGED_WIDE
        )
        assert out["scope"]["outcomes_published"] == payload_total == 125

    def test_the_collapse_is_counted_and_can_never_return_silently(self):
        """Acceptance criterion 3. Against a well-formed payload the collapse is
        0 BY CONSTRUCTION; the counter exists so that if it ever stops being 0 the
        artifact says so instead of overwriting a rate and an n."""
        out = reconcile(
            db_cells={},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.50, price_moved=True, n=60),
                _pub("kalshi", "nba", 5, 0.90, price_moved=False, n=40),
            ],
            staged=STAGED_WIDE,
        )
        assert out["scope"]["published_rows_read"] == 2
        assert out["scope"]["published_rows_collapsed"] == 0

        # ... and a genuinely duplicated four-dimension key is REPORTED, not
        # asserted away. A crash here would take the gate down; a number keeps it
        # readable.
        dup = reconcile(
            db_cells={},
            published_buckets=[
                _pub("kalshi", "nba", 5, 0.50, price_moved=True, n=60),
                _pub("kalshi", "nba", 5, 0.90, price_moved=True, n=40),
            ],
            staged=STAGED_WIDE,
        )
        assert dup["scope"]["published_rows_read"] == 2
        assert dup["scope"]["published_rows_collapsed"] == 1

    def test_price_moved_normalizes_the_same_from_json_and_from_a_driver(self):
        """The two sides arrive over different transports. A key is only a key if
        both spell it identically."""
        assert normalize_price_moved(True) is True
        assert normalize_price_moved(False) is False
        assert normalize_price_moved("true") is True
        assert normalize_price_moved("f") is False
        # None is a THIRD value, never folded into False: unknown movement is not
        # absent movement.
        assert normalize_price_moved(None) is None
        assert normalize_price_moved("banana") is None


def _row(source, category, bucket_idx, *, price_moved, n, winners):
    from types import SimpleNamespace

    return SimpleNamespace(
        source=source,
        category=category,
        bucket_idx=bucket_idx,
        price_moved=price_moved,
        n=n,
        winners=winners,
        sum_prob=n * 0.5,
    )


# =============================================================================
# RULING 124 — the floor, tested on each side
# =============================================================================
class TestTheMinNFloor:
    def test_the_floor_is_two(self):
        assert MIN_IN_SCOPE_N_FLOOR == 2

    def test_an_in_scope_miss_AT_the_floor_is_reported_but_does_not_disagree(self):
        """n == 2. Below-or-at the floor: reported under its own key, discounted
        by the verdict."""
        out = reconcile(
            db_cells={},
            published_buckets=[
                _pub("polymarket", "politics", 7, 0.70, price_moved=True, n=2)
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_AGREES
        # REPORTED — the union still carries it, and the discounted subset names
        # it. A floor that removed the row would be indistinguishable from a fold
        # that found it.
        assert len(out["published_only_in_scope"]) == 1
        assert len(out["published_only_in_scope_below_floor"]) == 1
        assert out["scope"]["buckets_in_scope_missing"] == 1
        assert out["scope"]["buckets_in_scope_missing_below_floor"] == 1
        assert out["scope"]["buckets_in_scope_missing_above_floor"] == 0
        assert out["scope"]["outcomes_in_scope_missing_below_floor"] == 2
        assert out["scope"]["min_in_scope_n_floor"] == 2

    def test_an_in_scope_miss_ONE_ABOVE_the_floor_still_disagrees(self):
        """n == 3. The other side of the floor, and the property CAL-P086B
        bought: an in-scope cell the fold should have produced and did not is a
        population disagreement."""
        out = reconcile(
            db_cells={},
            published_buckets=[
                _pub("polymarket", "politics", 7, 0.70, price_moved=True, n=3)
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert len(out["published_only_in_scope"]) == 1
        assert out["published_only_in_scope_below_floor"] == []
        assert out["scope"]["buckets_in_scope_missing_above_floor"] == 1

    def test_one_thick_miss_carries_the_verdict_past_any_number_of_thin_ones(self):
        """The floor discounts thin cells; it does not let them dilute a real
        finding."""
        published = [
            _pub("polymarket", "politics", i, 0.50, price_moved=True, n=1)
            for i in range(9)
        ] + [_pub("kalshi", "nba", 9, 0.50, price_moved=True, n=500)]
        out = reconcile(
            db_cells={}, published_buckets=published, staged=STAGED_WIDE
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert out["scope"]["buckets_in_scope_missing_below_floor"] == 9
        assert out["scope"]["buckets_in_scope_missing_above_floor"] == 1

    def test_an_UNDISCLOSED_n_is_not_a_thin_cell_and_is_never_discounted(self):
        """The asymmetry ``tolerance_pp`` uses, one level down. A payload that
        does not say how big a bucket is has not said it is small, and letting an
        undisclosed size buy silence is the flattering direction this module
        exists to refuse (gotcha #53).

        This is not hypothetical — the CAL-P078 fixture that caught it publishes
        a bucket with no ``n`` at all."""
        out = reconcile(
            db_cells={},
            published_buckets=[
                {"source": "polymarket", "category": "politics",
                 "bucket_idx": 7, "actual_rate": 0.7}
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_DISAGREES
        assert out["published_only_in_scope_below_floor"] == []

    def test_the_floor_does_not_reach_out_of_scope_cells(self):
        """An out-of-scope cell was already excluded from the verdict by
        CAL-P086B. The floor must not start reporting it as a discounted in-scope
        miss — two different reasons for the same silence would be one bucket
        again."""
        out = reconcile(
            db_cells={},
            published_buckets=[
                _pub("odds_api", "nba", 5, 0.50, price_moved=True, n=1)
            ],
            staged=STAGED_WIDE,
        )
        assert out["verdict"] == VERDICT_AGREES
        assert len(out["published_only_out_of_scope"]) == 1
        assert out["published_only_in_scope"] == []
        assert out["published_only_in_scope_below_floor"] == []


# =============================================================================
# The floor's precondition, pinned to the measurement that justifies it
# =============================================================================
_ARTIFACT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "artifacts"
    / "cal-p087"
    / "ARTIFACT-CAL-P087-GATE0-SPLIT-PRE-READ.json"
)


def test_floor_cannot_resurrect_agrees_by_timeout():
    """🔴 THE RULING'S PRECONDITION, and the reason it is safe to write.

    A floor is only a threshold if the population it discounts is a MINORITY of
    the evidence. If ``n <= 2`` covered every in-scope miss, this change would
    hand Gate 5 back the ``agrees``-by-timeout it just lost — a fold that
    produced nothing would read green again.

    Measured 2026-08-22 on the served payload and frozen in CAL-P087's artifact:
    608 in-scope bucket keys, **159** of them thin. So **449 survive the floor**,
    and a fold producing zero rows leaves all 449 unmatched and above it.

    This test reads the pinned artifact rather than restating its numbers, so if
    the population ever shifts under the floor the test moves with it and the
    assertion below is the thing that fails.
    """
    census = json.loads(_ARTIFACT.read_text())["census_of_served_payload"]
    in_scope = census["bucket_keys_in_scope"]
    thin = census["in_scope_bucket_keys_with_n_le_2"]
    above = in_scope - thin

    assert in_scope == 608 and thin == 159, (
        "the pinned census moved; re-derive the floor before trusting it"
    )
    assert above == 449
    assert above > 0, (
        "RULING 124 IS UNSAFE AT THIS POPULATION: every in-scope miss is thin, "
        "so the floor would let a fold that produced nothing read `agrees` — "
        "which is precisely the defect CAL-P086B's split removed."
    )
    # And the shape of the claim, not just the arithmetic: an empty fold leaves
    # every in-scope key unmatched, so RED is reachable from the survivors alone.
    assert above >= thin, (
        "the discounted set has grown past the deciding set; the floor is no "
        "longer a tail rule and needs re-deriving"
    )
