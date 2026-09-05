"""D66 (#1978, CAL-P1002F) — `kalshi/entertainment` is excluded by RULE E's SUM
ARM ALONE, and the realization arm is WITHHELD.

Alex ruled A on 2026-09-04 08:55 PT ("d66:a") against the D66 block in
`YOUR-TURN-ARCHIVE-2026-09-04-0700.md` line 49. What he approved is the sum test
and its measured effect: *"when our copy of the prices doesn't add up, that
question doesn't count towards the score. It removes 14% of the entertainment
rows and takes the over-confidence from +3.5 points to +0.8."*

**The whole point of this file is that the obvious implementation is the wrong
one.** Adding `("kalshi", "entertainment")` to `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`
would have shipped BOTH of RULE E's arms, and the realization arm removes this
cell's BETTER half — measured off the served payload's own
`nonexclusive_bundle_census`:

    entertainment  published 12,330 | >=2-winner cohort 5,872 @ ECE 4.26
                                    | remainder        6,458 @ ECE 9.49

That change would have moved the published cell TOWARDS 9.49 while passing every
test in the suite, because nothing in the suite knew the two arms had to be
separable. These tests are what knows it.
"""

import ast
import inspect
from pathlib import Path

import pytest

from app.tasks import precompute_calibration as pc

_FROZEN = Path(inspect.getfile(pc))

#: The cell D66 ruled on. Spelled out rather than read from the constant: a test
#: that derives its subject from the thing under test cannot notice the subject
#: being swapped for another cell.
_D66_CELL = ("kalshi", "entertainment")

#: Above ``MEX_NORMALIZE_THRESHOLD`` (1.15). The specimen in the ruling —
#: `KXBBCHARTPOSITIONSONG-26SEP05BOS` — publishes 0.955 + 0.400 + 0.050 = 1.405
#: on a question where at most one rank can be true.
_SUM_OVER = 1.405
_SUM_UNDER = 1.02


# ---------------------------------------------------------------------------
# 1. The allowlist is a ledger of rulings, like its sibling.
# ---------------------------------------------------------------------------


def test_the_sum_arm_only_cells_are_exactly_the_ruled_cells():
    """Pinned as an exact set, for the reason its sibling gives.

    ``test_the_ruled_cells_are_exactly_the_ruled_cells`` (D12) pins
    ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS`` exactly because "every entry here
    removes a cell from the published board, so the list is a ledger of rulings
    and its length is part of the claim". Identical logic, identical pin:

      * ``(kalshi, entertainment)`` — D66, Alex 2026-09-04 08:55 PT ("d66:a"),
        on the D66 block in ``YOUR-TURN-ARCHIVE-2026-09-04-0700.md`` line 49 and
        the evidence in ``REPORT-calibration-1002-…`` §7b–§7d.

    An entry that cannot name its ruling does not belong in this tuple.
    """
    assert pc.SUM_ARM_ONLY_EXCLUDED_CELLS == (("kalshi", "entertainment"),)


def test_the_two_allowlists_are_disjoint():
    """A cell in both would be silently narrowed to the sum arm.

    ``market_is_esports_multi_bundle`` tests the sum-arm-only allowlist FIRST and
    returns from it, so a cell that appeared in both tuples would lose its
    realization arm without anyone editing the wider rule. That is a way to
    weaken a shipped exclusion by ADDING a line, which is the hardest kind of
    regression to see on a diff.
    """
    overlap = set(pc.SUM_ARM_ONLY_EXCLUDED_CELLS) & set(
        pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS
    )
    assert not overlap, (
        f"{overlap} is in both allowlists — the sum-arm branch runs first, so "
        "this silently strips the realization arm from a cell that was ruled "
        "onto both"
    )


def test_the_sum_arm_only_cells_are_never_the_esports_category():
    """Esports is category-scoped on every source and must keep both arms.

    Same failure mode as the disjointness test, one level up: the sum-arm branch
    returns before the esports check, so an esports-category entry here would
    narrow the OPS-557 rule (measured +9.2 pp) to its sum arm on that source.
    """
    for _src, cat in pc.SUM_ARM_ONLY_EXCLUDED_CELLS:
        assert cat != pc.ESPORTS_MULTI_BUNDLE_CATEGORY


def test_the_tuple_is_scoped_by_source_as_well_as_category():
    """Inherited from CAL-P114 rather than re-derived.

    A bare category entry would also act on `polymarket/entertainment`, which
    nobody has folded. CAL-P112 item 3's standing warning is that RULE T's
    category-only widening moved `polymarket/tech` 8.04 -> 12.62 — WORSE — on a
    cell that was likewise unmeasured. A rule may not reach a cell nobody folded.
    """
    for entry in pc.SUM_ARM_ONLY_EXCLUDED_CELLS:
        assert isinstance(entry, tuple) and len(entry) == 2, (
            f"{entry!r} is not a (source, category) pair — a bare category "
            "string here silently widens the rule across every source"
        )
        assert all(isinstance(part, str) and part for part in entry)


# ---------------------------------------------------------------------------
# 2. THE CLAIM: the realization arm is withheld. This is the file's reason to
#    exist, and it is asserted on the mirror and on the SQL separately.
# ---------------------------------------------------------------------------


def test_a_multi_winner_entertainment_market_is_NOT_excluded_when_its_prices_sum_to_one():
    """The measured heart of D66.

    A `kalshi/entertainment` market that resolved with >=2 winners but whose
    published prices DO sum to a distribution is a member of the 5,872-row
    cohort that measures 4.26 against a 9.49 remainder. It must stay in the
    curve. If this ever goes green-to-red, the cell has been handed RULE E's
    realization arm and the published number will move the wrong way.
    """
    assert not pc.market_is_esports_multi_bundle(
        "entertainment",
        4,
        2,
        source="kalshi",
        cp_sum=_SUM_UNDER,
    )


def test_a_sum_past_the_threshold_IS_excluded_even_on_a_single_winner():
    """The arm that WAS ruled on: the stapled-questions shape.

    The specimen from the ruling — three separate "will this song be #N"
    questions packed into one market, published sum 1.405, exactly one of which
    can be true. The >=2-winner test can never see this row; the sum test is the
    only thing that can.
    """
    assert pc.market_is_esports_multi_bundle(
        "entertainment",
        4,
        1,
        source="kalshi",
        cp_sum=_SUM_OVER,
    )


def test_the_withheld_arm_is_withheld_only_for_the_ruled_cell():
    """The narrowing must not leak to the cells ruled onto both arms.

    `kalshi/economics` is the specimen: its own comment records that excluding
    only the multi-winner half takes it 5.29 -> 5.73, "measurably WORSE THAN
    DOING NOTHING". It needs BOTH arms, and D66 must not have cost it one.
    """
    assert pc.market_is_esports_multi_bundle(
        "economics", 4, 2, source="kalshi", cp_sum=_SUM_UNDER
    )
    assert pc.market_is_esports_multi_bundle(
        "economics", 4, 1, source="kalshi", cp_sum=_SUM_OVER
    )
    # And esports, on any source, keeps both arms too.
    assert pc.market_is_esports_multi_bundle(
        "esports", 4, 2, source="polymarket", cp_sum=_SUM_UNDER
    )


def test_the_rule_does_not_reach_entertainment_on_another_source():
    """`polymarket/entertainment` is unfolded and must be untouched."""
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", 4, 1, source="polymarket", cp_sum=_SUM_OVER
    )
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", 4, 2, source="polymarket", cp_sum=_SUM_UNDER
    )


def test_a_caller_that_did_not_say_the_source_cannot_trip_the_rule():
    """The keyword-only default is load-bearing, as it is for its sibling.

    ``source=None`` means "the caller did not say", and a caller that did not
    say must not be able to trip a (source, category) rule by accident.
    """
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", 4, 1, cp_sum=_SUM_OVER
    )


def test_a_market_with_no_price_sum_fails_closed():
    """``cp_sum is None`` cannot be shown to be structurally non-exclusive.

    It is the market that contributed no eligible priced outcome. In SQL the
    same row falls out because ``NULL > 1.15`` is NULL; the mirror has to agree
    or the Python and the statement disagree about a published row.
    """
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", 4, 1, source="kalshi", cp_sum=None
    )
    # ...and NOT via the realization arm either, which is the trap: without the
    # explicit `cp_sum is not None` this row reaches the >=2-winner arm.
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", 4, 2, source="kalshi", cp_sum=None
    )


def test_a_proved_exclusive_field_is_never_excluded_by_any_arm():
    """RULE E's disjointness clause, which the CTE now applies above all arms.

    Complete proved-exclusive fields are the normalizer's input and are
    NORMALIZED, never excluded; the two sets must not overlap or an exclusion
    silently eats the normalizer's input.
    """
    assert not pc.market_is_esports_multi_bundle(
        "entertainment",
        4,
        1,
        source="kalshi",
        cp_sum=_SUM_OVER,
        exclusivity_proved=True,
    )


@pytest.mark.parametrize("n_outcomes", [0, 1, 2])
def test_the_three_outcome_floor_still_applies(n_outcomes):
    """A two-leg market is not a bundle at any sum."""
    assert not pc.market_is_esports_multi_bundle(
        "entertainment", n_outcomes, 1, source="kalshi", cp_sum=_SUM_OVER
    )


# ---------------------------------------------------------------------------
# 3. The SQL says what the mirror says. A mirror that has stopped mirroring is
#    the defect this whole queue keeps finding.
# ---------------------------------------------------------------------------


def _bundle_cte() -> str:
    sql = pc._calibration_population_ctes()
    return sql.split("esports_multi_bundles AS (", 1)[1].split("\n            ),", 1)[0]


def test_the_sum_arm_only_pair_reaches_the_statement():
    body = _bundle_cte()
    src, cat = _D66_CELL
    assert f"('{src}', '{cat}')" in body, (
        "D66's cell is not in the emitted statement — the mirror would exclude "
        "rows the curve still publishes"
    )
    assert "(mi.source, mrs.category)" in body, (
        "the exclusion is no longer scoped by source — it can now reach cells "
        "that were never folded"
    )


def test_the_sum_arm_only_branch_does_not_carry_the_win_count_arm():
    """The structural claim, read off the statement rather than trusted.

    The sum-arm-only branch is the LAST disjunct of the cell/arm predicate. It
    must mention the price sum and must NOT mention ``win_count`` — if it does,
    the realization arm came back and 5,872 well-calibrated rows leave the curve.
    """
    body = _bundle_cte()
    src, cat = _D66_CELL
    # The branch runs from the pair literal to the end of the predicate.
    branch = body.split(f"('{src}', '{cat}')", 1)[1]
    assert "cp_sum >" in branch, "the sum arm is missing from D66's own branch"
    assert "win_count" not in branch, (
        "D66's branch carries the >=2-winner arm — that arm removes "
        "kalshi/entertainment's BETTER half (5,872 rows @ ECE 4.26 against a "
        "6,458-row remainder @ 9.49) and moves the published cell the wrong way"
    )


def test_the_both_arms_branch_still_carries_both_arms():
    """The other side of the same coin: the wider rule was not narrowed."""
    body = _bundle_cte()
    assert "mrs.win_count >= 2" in body
    assert f"'{pc.ESPORTS_MULTI_BUNDLE_CATEGORY}'" in body
    for src, cat in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS:
        assert f"('{src}', '{cat}')" in body


def test_the_exclusivity_clause_still_guards_every_arm():
    """Hoisted above the arms by this change, so prove it did not get scoped in.

    If ``NOT (exclusivity_proved)`` ended up inside one branch, the other branch
    would start eating the normalizer's input.
    """
    body = _bundle_cte()
    assert body.count("AND NOT (") >= 1
    head = body.split("AND (", 1)[0]
    assert "NOT (" in head, (
        "the proved-exclusive guard is no longer above the arm/cell predicate — "
        "it now applies to some arms and not others"
    )


# ---------------------------------------------------------------------------
# 4. Disclosure and the fingerprint — the two things a silent version of this
#    change would have skipped.
# ---------------------------------------------------------------------------


def test_the_cell_is_disclosed_as_a_named_counted_exclusion():
    """Alex's 2026-08-28 clause: the removed rows are named and counted.

    A row removed by one arm is as removed as a row removed by two. A reader who
    finds `kalshi/entertainment` absent from the disclosure while 14% of its rows
    have left is being told something false.
    """
    labels = dict(pc.nonexclusive_bundle_cell_labels())
    src, cat = _D66_CELL
    assert f"{src}/{cat}" in labels
    assert labels[f"{src}/{cat}"] == "nxb_sum_cell_0"
    assert "nxb_sum_cell_0" in pc.NONEXCLUSIVE_BUNDLE_CELL_COLUMNS
    assert "AS nxb_sum_cell_0" in pc.nonexclusive_bundle_cell_columns_sql()


def test_the_published_rule_text_says_a_cell_may_be_ruled_onto_one_arm():
    """A reader cannot reconcile the count against a rule they were not told.

    The shipped text says the test is ">=2 winners OR sum past 1.15". On a
    sum-arm-only cell that sentence does not reconcile against the number, so
    the page has to say some cells are ruled onto one arm.
    """
    text = pc.ESPORTS_MULTI_BUNDLE_RULE_TEXT
    assert "SUM ARM ALONE" in text
    assert "withheld" in text


def test_the_allowlist_is_hashed_into_the_input_fingerprint_by_name():
    """The sixth instance of the hole this file keeps re-teaching.

    ``SUM_ARM_ONLY_EXCLUDED_CELLS`` is INTERPOLATED into the emitted SQL, so
    ``inspect.getsource`` hashes the f-string TEMPLATE and never the value.
    Without an explicit by-name entry, adding or removing a sum-arm-only cell
    changes which rows the curve publishes while leaving the digest identical,
    and a cursor banked under one allowlist stays resumable by code with a
    different one — two populations merged into one payload.
    """
    source = inspect.getsource(pc._main_input_fingerprint)
    assert "sum_arm_only_cells=" in source
    assert "SUM_ARM_ONLY_EXCLUDED_CELLS" in source


def test_changing_the_allowlist_moves_the_fingerprint():
    """Non-vacuity for the test above: prove the digest actually responds.

    Asserting the string is in the source only proves someone typed it. This
    mutates the constant and re-derives, which is the same measurement the file's
    own comment prescribes ("found by asking what would happen if the value
    changed").
    """
    before = pc._main_input_fingerprint()
    original = pc.SUM_ARM_ONLY_EXCLUDED_CELLS
    try:
        pc.SUM_ARM_ONLY_EXCLUDED_CELLS = original + (("kalshi", "mutation_probe"),)
        after = pc._main_input_fingerprint()
    finally:
        pc.SUM_ARM_ONLY_EXCLUDED_CELLS = original
    assert before != after, (
        "the fingerprint did not move when the sum-arm allowlist changed — a "
        "cursor banked under the old population would stay resumable"
    )
    assert pc._main_input_fingerprint() == before, "the probe did not clean up"


# ---------------------------------------------------------------------------
# 5. The mistake this file exists to prevent, stated as a test.
# ---------------------------------------------------------------------------


def test_entertainment_is_deliberately_absent_from_the_both_arms_allowlist():
    """The one-line change that looks right and is measurably wrong.

    Moving `('kalshi','entertainment')` into ``NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS``
    is the obvious way to ship D66. It hands the cell RULE E's realization arm,
    which removes 5,872 rows measuring ECE 4.26 and leaves 6,458 measuring 9.49.
    It also removes ~48% of the cell rather than the 14% Alex was quoted, so it
    does not deliver the +3.5 -> +0.8 he ruled on either.
    """
    assert _D66_CELL not in pc.NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS, (
        "kalshi/entertainment has been given RULE E's realization arm; D66 "
        "ruled on the sum arm alone and the realization arm removes this "
        "cell's better half"
    )


def test_the_ruling_is_recorded_beside_the_constant():
    """An entry that cannot name its ruling does not belong in the tuple.

    The sibling allowlists both carry their ruling in a comment block; a future
    reader deciding whether a cell may be added has to be able to find out on
    what evidence the last one was. Read as TEXT so a deleted comment reds.
    """
    source = _FROZEN.read_text()
    block = source.split("SUM_ARM_ONLY_EXCLUDED_CELLS = (", 1)[0]
    header = block.rsplit("# ---------------------------------------------------------------------------", 1)[-1]
    assert "D66" in header
    assert "d66:a" in header, "the ruling keystroke is not recorded"
    assert "4.26" in header and "9.49" in header, (
        "the measurement that withheld the realization arm is not on file "
        "beside the constant it justifies"
    )


def test_the_constant_is_a_module_level_tuple_literal():
    """Read by the staged-fold mirror via ``ast.literal_eval`` on the source.

    ``test_the_mirrored_cell_columns_match_the_frozen_builds_own_cell_tuple``
    parses this file as text because ruling 009 bars importing it there. If this
    ever becomes a computed expression that parse raises instead of reding
    usefully, so pin the shape here where the message can say why.
    """
    tree = ast.parse(_FROZEN.read_text())
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(t, ast.Name) and t.id == "SUM_ARM_ONLY_EXCLUDED_CELLS"
            for t in node.targets
        )
    ]
    assert len(found) == 1, "SUM_ARM_ONLY_EXCLUDED_CELLS moved or multiplied"
    assert ast.literal_eval(found[0].value) == pc.SUM_ARM_ONLY_EXCLUDED_CELLS
