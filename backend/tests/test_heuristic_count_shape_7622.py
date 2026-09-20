"""#7622: the heuristic-exclusion COUNT must obey D112's lone-claim shape.

The accuracy page renders `heuristic_filter.excluded_by_source` (summed) as a
reader-facing row — "Results an old process guessed at instead of settling — N".

q271 / D112 (#997, CAL-P1138) admitted the lone-claim pair: at exactly ONE
captured outcome no sibling's price can be grading the row, so `all_losers`
there is the venue's own answer and the row is PUBLISHED. The population
predicate learned that shape. This transparency counter did not, so 6,081 rows
(polymarket 3,497 / kalshi 2,584, measured on production 2026-09-20) were in the
curve AND counted on the page as results we had set aside.

WHAT THESE TESTS ARE FOR, and it is not the arithmetic. The defect was a
MISSING CONJUNCT, and what let it survive a ruled widening was that this counter
carried its own hand-written copy of the source list, in a query with no shape
column in scope. So the guard is a COUPLING guard: the counter must carry the
predicate the population carries, rendered from the one helper. A count that
merely happens to be right today is not what is being pinned.

WHY THESE ASSERT SOURCE TEXT RATHER THAN A RENDERED STRING. The obvious
improvement — hoist the SQL to a module constant so the test can read the
rendered predicate — is a trap this module has fallen into eight times and
documents at length in `_main_input_fingerprint`: the digest that invalidates a
carried phase read hashes `compute_calibration_payload`'s OWN source, so a
hoisted constant leaves only its name behind and a later edit to the SQL moves
no digest. The SQL stays inline where the fingerprint covers it, and the tests
read it the same way the fingerprint does.
"""

import inspect

import app.tasks.precompute_calibration as pc
from app.utils.resolution_authority import (
    LONE_CLAIM_N_OUTCOMES,
    LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES,
    calibration_truth_eligible_sql,
    is_calibration_truth_eligible,
)

#: The two heuristic classes this counter is about, as its own WHERE clause
#: names them. Written out here rather than imported so the test fails if the
#: counter's subject silently changes underneath it.
HEURISTIC_CLASSES = ("pass2_loser", "all_losers")


def _counter_source() -> str:
    """The heuristic-count query as the fingerprint sees it.

    Sliced to the statement rather than the whole function so an assertion
    cannot pass on a coincidental match somewhere else in a 1,500-line builder —
    `calibration_truth_eligible_sql` is called at several other sites in here,
    and an unsliced `in` check would read one of those as this one.
    """
    src = inspect.getsource(pc.compute_calibration_payload)
    start = src.index("Query 9:")
    end = src.index("heuristic_excluded = runner.reuse", start)
    return src[start:end]


def test_the_slice_the_other_tests_read_is_really_the_counter():
    """A helper that silently returned the wrong span would make every
    assertion below vacuous, so pin the span itself."""
    body = _counter_source()
    assert "heur_sql = text(" in body
    assert "COUNT(*) AS excluded" in body
    assert body.count("heur_sql = text(") == 1


def test_counter_negates_the_shape_aware_predicate_not_a_copy_of_it():
    """The count is rendered from `calibration_truth_eligible_sql` WITH a shape
    column — the same single source of truth the published population uses.

    This is the assertion that would have caught #7622 the day q271 landed: the
    shape-blind call is the one this site used to be entitled to, and it still
    reads plausibly. Only requiring the SHAPE-AWARE call fails.
    """
    body = _counter_source()

    assert "AND NOT {calibration_truth_eligible_sql(n_outcomes_col='mrs.n_outcomes')}" in body
    # The set must not be restated here. A literal source list next to the
    # helper is how the two copies drift apart again.
    assert "'clean_resolution'" not in body
    assert "LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES" not in body
    # And the helper really does have two distinct renderings, so the demand for
    # the shape-aware one is a demand for something.
    assert calibration_truth_eligible_sql(
        n_outcomes_col="mrs.n_outcomes"
    ) != calibration_truth_eligible_sql()


def test_the_shape_column_the_predicate_reads_is_actually_in_scope():
    """A predicate naming `mrs.n_outcomes` is inert unless something supplies it.

    The population scan gets this column from the `market_result_shape` CTE,
    which does not exist in this query — so the counter brings its own. Without
    this the SQL would not merely be wrong, it would fail to parse in
    production while a test that only greps the predicate passed.
    """
    body = _counter_source()

    assert "JOIN LATERAL (" in body
    assert "COUNT(*) AS n_outcomes" in body
    assert ") mrs ON TRUE" in body
    # The LATERAL must count the outcomes of THIS ROW'S market. A correlation on
    # anything else yields a number that is not this market's shape.
    assert "WHERE o2.market_id = fo.market_id" in body


def test_every_heuristic_class_d112_admits_is_dropped_from_the_count():
    """The counter and the population must agree, class by class.

    Expressed over the source sets rather than over one hard-coded name, so a
    later change to `LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES` cannot leave this test
    asserting yesterday's membership. `all_losers` is the overlap today; if the
    set ever grows a second heuristic class, this covers it with no edit.
    """
    overlap = set(HEURISTIC_CLASSES) & set(LONE_CLAIM_TRUTH_ELIGIBLE_SOURCES)
    assert overlap, (
        "no heuristic class is lone-claim-admissible — if D112's set changed, "
        "this counter's shape conjunct may now be dead code, not a fix"
    )

    for source in overlap:
        # Published at the lone-claim shape => must NOT be counted as excluded.
        assert is_calibration_truth_eligible(
            source, n_outcomes=LONE_CLAIM_N_OUTCOMES
        )
        # Still excluded at every other shape => must still be counted.
        assert not is_calibration_truth_eligible(source, n_outcomes=2)
        assert not is_calibration_truth_eligible(source, n_outcomes=None)


def test_pass2_loser_is_never_admitted_so_the_count_still_carries_it():
    """The fix must not quietly widen past what D112 ruled.

    `pass2_loser` (0.0% winrate at 0.5-0.9 prices, Lane-2 #754) is NOT in the
    lone-claim pair, so it stays counted at every shape including a lone claim.
    Without this, a fix that dropped the whole heuristic arm would pass the
    tests above.
    """
    for n in (LONE_CLAIM_N_OUTCOMES, 2, None):
        assert not is_calibration_truth_eligible("pass2_loser", n_outcomes=n)

    assert "'pass2_loser'" in _counter_source()


def test_the_counter_is_transparency_only_and_never_regrades():
    """Read-side only (gotcha #21): this query counts, it does not write.

    It also must not have become a population predicate — a change there needs a
    CALIBRATION_POPULATION_VERSION bump and a dark window, and #7622 bought
    neither.
    """
    upper = _counter_source().upper()
    for verb in ("UPDATE ", "INSERT ", "DELETE ", "SET IS_WINNER"):
        assert verb not in upper


def test_the_published_rule_prose_states_the_exception_it_now_applies():
    """The payload's own `rule` string must not describe the pre-q271 behaviour.

    Not a reader-facing string — notice 34 keeps this auditor prose off the page,
    and the page renders its own short label instead. It is asserted anyway
    because it is the sentence an auditor reads to decide whether the NUMBER is
    trustworthy, and for a week it said the opposite of what the code did.
    """
    src = inspect.getsource(pc)
    assert '"heuristic_filter": {' in src
    # The exception, named with the ruling that granted it.
    assert "lone-claim market (exactly one captured outcome)" in src
    assert "D112, #997" in src
    assert "a published row is not an excluded one" in src
