"""CAL-P162 (#1978) — RULE E: the bundle test becomes STRUCTURAL, and rank 2 lands.

The design is banked in ``artifacts/cal-p112/RULE-DESIGN-polymarket-esports.md``
§4 (RULE E) and re-confirmed on the producer's own chain by CAL-P114 §5c. The
ruling that lands ``(kalshi, economics)`` is Alex's of 2026-08-28, option (b)
APPROVED WITH DISCLOSURE.

**The one thing this file exists to prevent.** The shipped bundle test was a
REALIZATION test (``>=2 winners``). The defect is a STRUCTURE: a genuine
partition sums to ~1 whatever it resolves to, while independent binaries packed
into one market sum to N x p. A bundle that landed on a single rung therefore
escaped the shipped test entirely — and that 1-winner tail is the whole
published residue of ``polymarket/esports`` (7.59 pp) and 13.4% of
``kalshi/economics`` (5.29 pp).

🔴 So the allowlist tuple and the sum arm are ONE deliverable. Excluding only
the multi-winner half of ``kalshi/economics`` takes the cell 5.29 -> **5.73** —
measurably WORSE THAN DOING NOTHING (scorecard §6b policy B, "RULE T alone").
``test_rank2_tuple_never_ships_without_the_structural_arm`` is that fact carried
by the suite instead of by a comment, because a comment cannot fail.
"""

from __future__ import annotations

import re

import pytest

from app.tasks import precompute_calibration as pc


def _esports_bundle_cte_body() -> str:
    """The rendered ``esports_multi_bundles`` CTE body, from the real producer.

    Rendered, never restated: a guard written against a copy of the SQL is
    satisfied by the copy and blind to the query that actually runs.
    """
    sql = pc._calibration_population_ctes()
    start = sql.index("esports_multi_bundles AS (")
    depth = 0
    for offset, char in enumerate(sql[start:], start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return sql[start : offset + 1]
    raise AssertionError("esports_multi_bundles CTE is unterminated")


# ---------------------------------------------------------------------------
# 1. The predicate, as a truth table.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "n_outcomes,n_winners,cp_sum,proved,expected,why",
    [
        # The shipped realization arm, preserved verbatim.
        (3, 2, None, False, True, "多-winner bundle: the arm that already shipped"),
        (73, 12, None, False, True, "an esports match bundle, as before"),
        # The new structural arm — the whole point of RULE E.
        (35, 1, 21.66, False, True, "the median KXDJI ladder: 1 winner, sum 21.66"),
        (3, 1, 1.16, False, True, "just past the threshold"),
        (3, 0, 3.0, False, True, "no winner at all, but structurally a bundle"),
        # A genuine partition is never touched by either arm.
        (10, 1, 1.0, False, False, "a partition sums to ~1 and resolves to one"),
        (3, 1, 1.15, False, False, "exactly AT the threshold is not PAST it"),
        # The disjointness clause.
        (40, 1, 30.75, True, False, "proved-exclusive: normalizer input, never excluded"),
        (5, 2, None, True, False, "proved-exclusive wins over the realization arm too"),
        # Shape floor and the fail-closed sum.
        (2, 2, 9.9, False, False, "two outcomes is never a bundle, whatever it sums to"),
        (3, 1, None, False, False, "no sum => cannot be shown structural => fails closed"),
    ],
)
def test_structural_bundle_truth_table(
    n_outcomes, n_winners, cp_sum, proved, expected, why
):
    assert (
        pc.market_is_nonexclusive_bundle_structural(
            n_outcomes, n_winners, cp_sum, exclusivity_proved=proved
        )
        is expected
    ), why


def test_the_threshold_is_the_normalizers_own_constant_not_a_fitted_one():
    """RULE E's sum bound is ``MEX_NORMALIZE_THRESHOLD``, and it is 1.15.

    CAL-P117 §4 is the reason this is pinned: the holdout REFUSED three fitted
    thresholds (>15, >5, all-props) and admitted the one that was already a
    constant in the codebase. A later queue that "tunes" 1.15 is re-fitting a
    bound the holdout chose.
    """
    assert pc.MEX_NORMALIZE_THRESHOLD == 1.15
    assert pc.market_is_nonexclusive_bundle_structural(
        3, 1, pc.MEX_NORMALIZE_THRESHOLD + 0.001, exclusivity_proved=False
    )
    assert not pc.market_is_nonexclusive_bundle_structural(
        3, 1, pc.MEX_NORMALIZE_THRESHOLD, exclusivity_proved=False
    )


def test_the_realization_arm_is_a_strict_superset_and_nothing_it_caught_is_lost():
    """Every market the OLD test caught, the new test still catches.

    RULE E widens; it must not move. A structural test that quietly stopped
    catching a multi-winner bundle would be a regression wearing an improvement's
    name.
    """
    for n_outcomes in (3, 4, 12, 73):
        for n_winners in (2, 3, 11):
            assert pc.market_is_nonexclusive_bundle(n_outcomes, n_winners)
            assert pc.market_is_nonexclusive_bundle_structural(
                n_outcomes, n_winners, None, exclusivity_proved=False
            ), "the shipped realization arm must survive inside the structural test"


# ---------------------------------------------------------------------------
# 2. 🔴 The tuple and the sum arm are one deliverable.
# ---------------------------------------------------------------------------

def test_rank2_tuple_never_ships_without_the_structural_arm():
    """``(kalshi, economics)`` on the allowlist WITHOUT the sum arm = 5.29 -> 5.73.

    86.3% of the cell is ``bundle_multiwin`` and the 13.4% remainder is the same
    ladders on a day the index landed on one rung. Excluding only the first half
    is measurably worse than doing nothing (scorecard §6b policy B). This guard
    reds if a later change removes the sum arm while the tuple stays, or ships
    the tuple in a build whose CTE has only the realization test.
    """
    body = _esports_bundle_cte_body()
    assert ("kalshi", "economics") in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS

    # The realization arm and the structural arm, disjunctively joined.
    assert "mrs.win_count >= 2" in body, "the shipped realization arm went missing"
    assert re.search(r"bps\.cp_sum\s*>\s*1\.15", body), (
        "RULE E's structural sum arm is absent from the CTE that runs — the "
        "allowlist tuple alone takes kalshi/economics 5.29 -> 5.73"
    )
    realization = body.index("mrs.win_count >= 2")
    structural = body.index("bps.cp_sum")
    between = body[realization:structural]
    assert re.search(r"\bOR\b", between), (
        "the two arms must be OR-joined; an AND would narrow the shipped rule "
        "to the intersection and silently un-exclude the esports cell"
    )


def test_the_sum_is_computed_over_the_published_population():
    """The bundle sum must be summed over the rows the CURVE publishes.

    A structure judged on a population the reader never sees is not the
    structure of the published market. ``bundle_price_sum`` therefore carries
    the same eligibility predicate as ``mex_field_divisor``: priced, strictly
    between 0 and 1, truth-eligible resolution source, and liquidity-evidenced.
    """
    sql = pc._calibration_population_ctes()
    start = sql.index("bundle_price_sum AS (")
    body = sql[start : sql.index("esports_multi_bundles AS (")]
    assert "fo.opening_probability > 0 AND fo.opening_probability < 1" in body
    assert "fo.resolution_source IN" in body
    assert "CALIBRATION_TRUTH_ELIGIBLE" not in body, "the tuple must be interpolated, not named"
    # It must NOT be scoped to the normalizer's candidates — that is precisely
    # the population RULE E may never touch, so reusing mex_field_divisor would
    # have made the sum arm unreachable.
    assert "mex_field_candidates" not in body


def test_proved_exclusive_fields_are_excluded_from_the_exclusion():
    """The disjointness clause is in the CTE, not only in the Python mirror.

    Proved-exclusive fields are ``mex_field_candidates`` — the normalizer's
    INPUT. If the exclusion could reach them it would eat the rows the
    normalizer is meant to fix, and the two sets are asserted disjoint by
    construction rather than by hope.
    """
    body = _esports_bundle_cte_body()
    assert "NOT (" in body
    assert "shape_exhaustive" in body and "shape_expected_winners" in body, (
        "the proved-exclusivity test must be rendered inside the bundle CTE"
    )


# ---------------------------------------------------------------------------
# 3. One rendering of the exclusivity predicate, not two.
# ---------------------------------------------------------------------------

def test_exclusivity_proved_sql_mirrors_python():
    """The SQL helper names exactly the four columns the Python mirror reads."""
    rendered = pc.exclusivity_proved_sql("mi", "mrs")
    for fragment in (
        "mi.market_type = 'field'",
        "mi.shape_exhaustive = 'true'",
        "mi.shape_expected_winners = '1'",
        "mi.shape_relation IN",
        "mrs.win_count = 1",
    ):
        assert fragment in rendered, fragment
    for relation in pc.EXCLUSIVITY_PROVED_RELATIONS:
        assert f"'{relation}'" in rendered


def test_the_exclusivity_predicate_has_exactly_one_rendering():
    """``mex_field_candidates`` and the bundle CTE share one helper.

    Two hand-maintained copies of one predicate in one query is how a mirror
    stops mirroring — the defect D12's own comment describes. Both call sites
    must go through :func:`exclusivity_proved_sql`.
    """
    import inspect

    source = inspect.getsource(pc._calibration_population_ctes)
    # Anchored on calls WITH arguments: a prose mention of the helper in a
    # comment must not be able to satisfy — or inflate — this count.
    calls = re.findall(r"exclusivity_proved_sql\(\s*['\"]", source)
    assert len(calls) == 2, (
        "both the normalizer's candidate gate and RULE E's disjointness clause "
        f"must render from the one helper; found {len(calls)} call site(s)"
    )
    assert "mi.shape_exhaustive = 'true'" not in source, (
        "an inline copy of the exclusivity predicate has reappeared"
    )


# ---------------------------------------------------------------------------
# 4. The disclosure — a clause of the ruling, not a nicety.
# ---------------------------------------------------------------------------

def test_the_per_cell_labels_are_derived_from_the_allowlist():
    """A new ruled tuple adds a column AND a payload key together, or neither."""
    labels = pc.nonexclusive_bundle_cell_labels()
    assert labels[0] == (pc.ESPORTS_MULTI_BUNDLE_CATEGORY, "nxb_cell_esports")
    # CAL-P168: the map is rendered from TWO allowlists behind one disclosure —
    # RULE E's bundle cells, then K''s player-props cells. The ORDER is asserted
    # because the column suffixes are positional (`nxb_cell_{idx}` /
    # `pp_cell_{idx}`): a cell inserted rather than appended would renumber the
    # columns under a banked cursor that still carries the old ones.
    # CAL-P1002F (D66): a THIRD allowlist behind the same disclosure — the
    # sum-arm-only cells — and it is asserted in its emission position, between
    # the two that were already here. The positional argument above is why it
    # got its own `nxb_sum_cell_{idx}` prefix rather than the next `nxb_cell_`
    # index: sharing the prefix would mean adding a both-arms cell renumbers a
    # sum-arm cell's column under a banked cursor still carrying the old one.
    assert [label for label, _ in labels[1:]] == [
        f"{src}/{cat}" for src, cat in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS
    ] + [
        f"{src}/{cat}" for src, cat in pc.SUM_ARM_ONLY_EXCLUDED_CELLS
    ] + [
        f"{src}/{cat}" for src, cat in pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS
    ]
    columns = pc.nonexclusive_bundle_cell_columns_sql()
    for _, column in labels:
        assert f"AS {column}" in columns
    for src, cat in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert f"source = '{src}'" in columns and f"category = '{cat}'" in columns
    # Each half must count its OWN flag. The whole design refuses RULE E's
    # predicate on K''s cell (measured 8.35 vs a 4.71 control), so a per-cell
    # column that counted `is_esports_bundle` for polymarket/baseball would
    # publish a number produced by a rule that was never applied to it.
    for src, cat in pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS:
        assert (
            "COUNT(*) FILTER (WHERE is_player_props_placeholder "
            f"AND source = '{src}' AND category = '{cat}')" in columns
        )


def test_the_per_cell_columns_survive_into_the_query_that_runs():
    """Rendered in BOTH the inner aggregate and the outer pass-through.

    A column defined in the inner scan and dropped by the outer aggregate reads
    as a missing attribute at runtime and a silently empty per-cell map on the
    page — the disclosure failing open.
    """
    for frozen in (False, True):
        sql = pc._main_futures_sql(frozen=frozen)
        assert "nonexclusive_bundle_cell_columns_sql" not in sql, (
            "the helper call is sitting in a NON-f string and shipping as literal SQL"
        )
        for _, column in pc.nonexclusive_bundle_cell_labels():
            assert f"AS {column}" in sql
            assert f"MAX(ls.{column})" in sql


def test_the_backend_does_not_carry_a_second_copy_of_the_page_copy():
    """Clause 3 of the ruling lives in ONE place, and it is the page.

    "nobody later reads the smaller curve as a fixed one" is hard-coded in
    ``frontend/app/calibration/page.tsx`` and pinned by
    ``calibrationNonexclusiveBundleDisclosure.test.tsx``. A backend constant
    holding the same sentence would be a second hand-maintained rendering of one
    fact — and the one nobody notices has drifted, because nothing renders it.
    """
    assert not hasattr(pc, "NONEXCLUSIVE_BUNDLE_FILTER_DISCLOSURE")


def test_the_rule_text_states_both_arms_and_the_per_cell_scoping():
    """A published rule text that describes only the shipped half is a false
    disclosure — the same defect class as an exclusion whose stated cause is
    wrong."""
    text = pc.NONEXCLUSIVE_BUNDLE_FILTER_RULE_TEXT
    assert ">=2 winners" in text
    assert "1.15" in text
    assert "sum" in text.lower()
    assert "never by " in text and "category alone" in text


def test_every_temporary_cell_is_excluded_and_every_excluded_cell_is_declared():
    """🔴 CAL-P168 REWRITES THIS GUARD, AND THE REASON IS THE POINT.

    It shipped as ``test_temporary_by_cell_is_empty_because_no_temporary_cell_
    shipped``, asserting ``('polymarket','baseball')`` was absent from
    ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`` and promising it would red "when rank
    1 lands, and updating it is the reminder that the revert condition has to be
    named". **Rank 1 landed and it stayed green.** The design REFUSES RULE E's
    predicate on this cell (measured 8.35 against a 4.71 control), so rank 1
    correctly shipped on its OWN allowlist — and the guard was watching the one
    tuple the cell was never going to join. It would have stayed green forever
    while the disclosure it protects went unwritten.

    Generalisable, and the reason this docstring is long: **a guard that names
    the mechanism it expects rather than the OUTCOME it requires goes vacuous
    the moment the mechanism is implemented differently.** The old assertion
    tested "is the cell in this list"; what the ruling requires is "if the cell
    is excluded anywhere, is the promise on the page". So that is what is tested
    now, in BOTH directions and over BOTH allowlists.
    """
    temporary = pc.PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL
    excluded_labels = {
        f"{src}/{cat}"
        for src, cat in (
            tuple(pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS)
            + tuple(pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS)
        )
    }

    # Direction 1: a cell cannot promise to come back unless it actually left.
    # A stale entry here renders "returns when ..." for rows still in the curve.
    assert set(temporary) <= excluded_labels, (
        f"temporary_by_cell names cells that are not excluded: "
        f"{sorted(set(temporary) - excluded_labels)}"
    )

    # Direction 2 — the clause of Alex's ruling. Rank 1's exclusion is TEMPORARY
    # BY DESIGN: the rows are real questions whose published price WE wrote
    # wrong, so the page must never let it read as permanent. If the cell is
    # excluded, the map must carry it AND name the condition that ends it.
    for src, cat in pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS:
        label = f"{src}/{cat}"
        assert label in temporary, (
            f"{label} is excluded by K' — its exclusion is TEMPORARY BY DESIGN, "
            "so temporary_by_cell must carry it with the condition that ends it"
        )
        condition = temporary[label]
        # The page renders "<cell> — returns when <condition>", so an empty or
        # placeholder condition produces a sentence that promises a return
        # without saying what would cause it. That is worse than silence.
        assert isinstance(condition, str) and len(condition.split()) >= 5, (
            f"{label}'s revert condition must be a real clause, got {condition!r}"
        )
        assert not condition.rstrip().endswith("."), (
            "the page appends its own punctuation after the condition"
        )

    # RULE E's cells are NOT temporary and must never acquire a condition: Alex
    # ruled rank 2 as a permanent structural exclusion and the page would
    # otherwise claim a return that no ruling promised (design §9.1).
    for src, cat in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert f"{src}/{cat}" not in temporary, (
            f"{src}/{cat} is a PERMANENT structural exclusion (ruled option (b), "
            "never 'EXCLUDE NOW + FIX WRITER') and must not promise a return"
        )


def test_the_two_allowlists_are_disjoint_so_no_row_is_counted_twice():
    """🔴 The payload SUMS two different rules into one ``excluded`` total.

    The page prints that total and then the per-cell map beneath it, so a reader
    must be able to add the cells up and get the total. That only holds while no
    row can be flagged by both rules — and the only structural guarantee of that
    is that the two allowlists share no ``(source, category)`` tuple.

    It is asserted rather than trusted because the failure is silent: a cell in
    both lists would be counted once by ``is_esports_bundle`` and once by
    ``is_player_props_placeholder``, and the disclosure would overstate the
    exclusion by the size of the overlap while every individual number still
    looked self-consistent.
    """
    overlap = set(pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS) & set(
        pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS
    )
    assert not overlap, (
        f"a cell in BOTH allowlists is double-counted in the disclosure: {overlap}"
    )
    # And the measured reason it must stay that way: RULE E on this cell reads
    # 8.35 / 9.02 against a 4.71 control. Adding the tuple to RULE E's list
    # would not merely double-count, it would nearly double the cell's error.
    assert ("polymarket", "baseball") not in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS, (
        "RULE E's bundle predicate on polymarket/baseball was MEASURED at 8.35 "
        "against a 4.71 control and is REFUSED by the design (§2)"
    )
