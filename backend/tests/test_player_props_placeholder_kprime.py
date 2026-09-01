"""CAL-P168 (#1978) — RANK 1, `polymarket/baseball`. K' = R1 + R2 + R3 + M1.

Design + ruling: `artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md` (Alex,
2026-08-28: **EXCLUDE NOW + FIX WRITER**). Prediction recorded before the code:
`artifacts/cal-p168/PREDICTION.md`.

WHAT THIS FILE IS FOR. The rule removes ~2.7% of the entire published curve, so
the expensive failures are not "it does not run" — they are:

  1. it acts on a cell it was never ruled onto;
  2. it quietly becomes RULE E, whose predicate on this cell was MEASURED at
     8.35 against a 4.71 control;
  3. an arm is pruned because it looks inert alone (dropping R2 puts the cell
     back over the bar at 3.10);
  4. it re-grades instead of excluding (gotcha #21);
  5. it removes ordinary line movement along with the manufactured coin flips;
  6. the page stops saying the exclusion is temporary while it still is.

Every test below targets one of those. The SQL is asserted against the rendered
statement rather than a database because the population CTEs are pure text at
this level — and where a claim needs real rows, it is stated as a claim about
the emitted predicate and named as such rather than dressed up as an execution.
"""

import ast
import re

import pytest
import sqlglot

from app.tasks import precompute_calibration as pc
from app.utils.calibration_staged_futures import NONEXCLUSIVE_BUNDLE_CELL_COLUMNS


@pytest.fixture(scope="module")
def ctes() -> str:
    return pc._calibration_population_ctes()


@pytest.fixture(scope="module")
def props_cte(ctes: str) -> str:
    """Just the `player_props_placeholder_markets` CTE body."""
    start = ctes.index("player_props_placeholder_markets AS (")
    depth = 0
    for i in range(ctes.index("(", start), len(ctes)):
        if ctes[i] == "(":
            depth += 1
        elif ctes[i] == ")":
            depth -= 1
            if depth == 0:
                return ctes[start : i + 1]
    raise AssertionError("the CTE is unbalanced")


# ---------------------------------------------------------------------------
# 1. Scope — the rule acts on the ruled cell and nowhere else.
# ---------------------------------------------------------------------------


def test_the_allowlist_is_exactly_the_ruled_cell():
    """Alex ruled ONE cell. Widening beyond baseball is UNMEASURED (design §6.2).

    The writer defect is a writer property and is very likely wider — `Player
    Props` containers exist in basketball and football too — but "likely" is not
    measured, and ruling 134 puts that census in the measurement lane. A cell
    added here without its own fold is a rule shipped on a guess.
    """
    assert pc.PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS == (("polymarket", "baseball"),)


def test_the_scope_is_source_and_category_never_category_alone(props_cte: str):
    """CAL-P114 measured what category-only scoping costs: `polymarket/economics`
    3.91 -> 17.75. One extra column in a tuple is the difference between crossing
    a rank off and silently destroying another one.
    """
    assert "(mi.source, mrs.category)" in props_cte
    assert "('polymarket', 'baseball')" in props_cte


def test_the_row_level_arm_is_cell_scoped_too(ctes: str):
    """M1 does not travel through the CTE, so it needs its OWN scope.

    This is the arm most likely to leak: R1/R2/R3 are gated by the CTE's WHERE,
    but M1 is evaluated inline in `ranked_outcomes` against every row in the
    build. Without the tuple test beside it, "published into [0.45,0.55] from
    more than 0.25 away" would delete rows in every sport on every source.
    """
    flag = _flag_expression(ctes)
    assert "(cv.source, cv.category)" in flag
    assert "('polymarket', 'baseball')" in flag


def _flag_expression(ctes: str) -> str:
    start = ctes.index("ppp.market_id IS NOT NULL")
    end = ctes.index("AS is_player_props_placeholder", start)
    return ctes[start:end]


# ---------------------------------------------------------------------------
# 2. It is not RULE E, and it must not become RULE E.
# ---------------------------------------------------------------------------


def test_the_flag_is_distinct_from_the_bundle_flag(ctes: str):
    """Two flags, two joins, two rules. The measured cost of conflating them is
    the cell going 4.71 -> 8.35."""
    assert "is_player_props_placeholder" in ctes
    assert "is_esports_bundle" in ctes
    assert "LEFT JOIN player_props_placeholder_markets ppp" in ctes
    assert "LEFT JOIN esports_multi_bundles emb" in ctes


def test_the_props_cte_never_tests_the_bundle_shape(props_cte: str):
    """RULE E's arms are `win_count >= 2` and the price sum past 1.15 over ANY
    market of >=3 outcomes. K''s only use of that sum is R3, and R3 additionally
    requires the container's NAME. A bare sum test appearing here would mean the
    bundle rule had been extended to this cell by the back door.
    """
    assert "win_count" not in props_cte
    # The sum appears exactly once, and only inside R3's conjunction with the
    # name test — never as a standalone arm.
    sum_clauses = re.findall(r"bps\.cp_sum\s*>", props_cte)
    assert len(sum_clauses) == 1, props_cte
    assert "ILIKE" in props_cte


def test_the_bundle_cell_columns_count_their_own_flag():
    """A per-cell disclosure column that counted the wrong flag would publish a
    number produced by a rule that was never applied to the cell it names."""
    columns = pc.nonexclusive_bundle_cell_columns_sql()
    for line in columns.split(",\n"):
        if "pp_cell_" in line:
            assert "is_player_props_placeholder" in line
            assert "is_esports_bundle" not in line
        elif "nxb_cell_" in line:
            assert "is_esports_bundle" in line
            assert "is_player_props_placeholder" not in line


# ---------------------------------------------------------------------------
# 3. Every arm is present, and each is the arm the design measured.
# ---------------------------------------------------------------------------


def test_r1_requires_both_legs_at_the_exact_spike(props_cte: str):
    """`pp_half_legs = 2` with `n_outcomes = 2` says EVERY leg is exactly 0.5000.

    🔴 A market with ONE 0.5000 leg is an ordinary even-money price and is KEPT.
    That criterion is the difference between naming the writer's complement pair
    (the Under leg written as 1 - a price the Over leg never traded) and
    deleting every coin-flip market in the cell.
    """
    r1 = pc.half_spike_pair_predicate("mrs")
    assert "mrs.n_outcomes = 2" in r1
    assert "mrs.pp_named_over = 1" in r1 and "mrs.pp_named_under = 1" in r1
    assert "mrs.pp_half_legs = 2" in r1
    assert r1 in props_cte


def test_r1_is_an_exact_value_and_not_a_band(props_cte: str):
    """Scoped to 0.5000 deliberately: the neighbouring 0.5005 has the identical
    signature at 1/18th the size, and widening to a band turns a self-evidencing
    exact match into a judgement call. That widening is a separate ruling with
    its own census (CAL-P094).
    """
    assert pc.PLAYER_PROPS_HALF_SPIKE_EXACT_VALUE == "0.5000"
    assert "ROUND(fo.opening_probability, 4) = 0.5000" in pc._calibration_population_ctes()
    # No tolerance band anywhere near the spike test.
    assert "pp_half_legs >" not in props_cte
    assert "BETWEEN 0.49" not in props_cte


def test_r2_requires_a_coherent_open_and_an_incoherent_publication(props_cte: str):
    """R2 is a statement about OUR publication, not about the market.

    The opening pair summing to 1 is what makes it so: the market quoted a
    consistent two-sided price and our published copy of it does not add up.
    Both legs leave.
    """
    r2 = pc.published_pair_coherence_predicate("mrs")
    assert "mrs.pp_open_legs = 2" in r2 and "mrs.pp_pub_legs = 2" in r2
    assert f"ABS(mrs.pp_open_sum - 1) <= {pc.PAIR_SUM_TOLERANCE}" in r2
    assert f"ABS(mrs.pp_pub_sum - 1) > {pc.PAIR_SUM_TOLERANCE}" in r2
    assert r2 in props_cte


def test_r2_reuses_the_shipped_write_side_tolerance():
    """Imported, never restated: the read-side exclusion and the write-side
    coherence rule must not be able to disagree about what "sums to 1" means."""
    from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE as shipped

    assert pc.PAIR_SUM_TOLERANCE is shipped
    assert shipped == 0.02


def test_r3_matches_the_container_name_AND_the_sum(props_cte: str):
    """Both halves, and the threshold is RULE E's own constant.

    🔴 THE HOLDOUT REFUSED EVERY FITTED ALTERNATIVE AND ADMITTED THE ONE THAT
    WAS ALREADY IN THE CODEBASE: sum > 15 passes pooled at 2.94 and fails BOTH
    halves; sum > 5 leaves OLD at 3.06; no sum test at all leaves NEW at 3.10
    and deletes 1,077 rows measured at 2.15/2.61. 1.15 is not a tuned number and
    must never be replaced by one.
    """
    r3 = pc.player_props_container_predicate("mi.market_name", "bps.cp_sum")
    assert "ILIKE '%player props%'" in r3
    assert f"bps.cp_sum > {pc.MEX_NORMALIZE_THRESHOLD}" in r3
    assert pc.MEX_NORMALIZE_THRESHOLD == 1.15
    assert r3 in props_cte


def test_m1_is_the_band_and_the_drift_floor_the_control_earned(ctes: str):
    """🔴 THE DRIFT FLOOR IS WHAT SEPARATES THIS FROM DELETING LINE MOVEMENT.

    Measured (design §3): rows forced INTO [0.45,0.55] from an open >0.25 away
    read ECE 44.36 with ECE == gap — every bin errs one way, published at ~0.50
    and losing. Rows that moved just as far and landed ELSEWHERE read 12.62 with
    a two-sided -2.92 gap: ordinary line movement, and they are KEPT.

    Widening the band or dropping the floor collapses that distinction, so both
    numbers are pinned here and not merely rendered.
    """
    assert pc.PLAYER_PROPS_MIDPOINT_BAND_LO == 0.45
    assert pc.PLAYER_PROPS_MIDPOINT_BAND_HI == 0.55
    assert pc.PLAYER_PROPS_FORCED_DRIFT_MIN == 0.25
    m1 = pc.forced_midpoint_predicate("fo")
    assert "BETWEEN 0.45 AND 0.55" in m1
    assert "> 0.25" in m1
    assert m1 in ctes


def test_m1_reads_calibration_probability_not_the_curve_price(ctes: str):
    """Whether OUR WRITER overwrote a price is a property of that column.

    Two consequences, both load-bearing. M1 is horizon-invariant — a row's
    membership cannot change because the curve is re-expressed at a different
    snapshot. And a row with NO `calibration_probability` was never overwritten:
    it is the `opening_probability` fallback (design §3's 123-row class, ECE
    2.78), a NULL yields NULL from BETWEEN, and it is KEPT.
    """
    m1 = pc.forced_midpoint_predicate("fo")
    assert "fo.calibration_probability BETWEEN" in m1
    assert "COALESCE" not in m1
    assert "raw_cp" not in m1 and "adj_opening_probability" not in m1


def test_all_four_arms_reach_the_statement_that_runs(ctes: str):
    """An arm defined and never rendered is an arm that measured nothing.

    Dropping R2 alone puts the cell at 3.10 — over its bar — even though R2's
    solo delta is -0.11 pp. Only the conjunction passes, so all four are
    asserted present in the SQL the build actually emits.
    """
    for arm in (
        pc.half_spike_pair_predicate("mrs"),
        pc.published_pair_coherence_predicate("mrs"),
        pc.player_props_container_predicate("mi.market_name", "bps.cp_sum"),
        pc.forced_midpoint_predicate("fo"),
    ):
        assert arm in ctes


def test_m2_is_not_an_arm(ctes: str):
    """🔴 M2 (the >0.10 rung) pushes the OLD holdout half back over at 3.06.

    It is measured, it is documented, and it is deliberately NOT shipped. It
    would be an easy "while we are here" addition — the softer rung of an arm
    that is already in — so its absence is asserted rather than assumed.
    """
    assert "> 0.10" not in ctes.replace("> 0.100", "")


# ---------------------------------------------------------------------------
# 4. It excludes; it never re-grades. (gotcha #21)
# ---------------------------------------------------------------------------


def test_the_rule_is_read_side_only(props_cte: str, ctes: str):
    """The rows are dropped from the curve, never re-graded.

    `is_winner` is TRUTH and stays untouched: what is wrong is the price WE
    published, and the market's own quote is still sitting intact in
    `opening_probability`. A rule that wrote to resolutions would destroy the
    only copy of the thing that proves the diagnosis.
    """
    assert "is_winner" not in props_cte
    # Checked on the PARSED statement, not the text. A substring scan reads the
    # word "delete" out of an explanatory comment ("it would delete 81% of
    # hockey") and passes for the wrong reason — or fails for one, which is how
    # this assertion was first written and what it taught.
    tree = sqlglot.parse_one(
        "WITH " + ctes + " SELECT 1 FROM deduped", dialect="postgres"
    )
    for dml in (sqlglot.exp.Update, sqlglot.exp.Delete, sqlglot.exp.Insert):
        assert not list(tree.find_all(dml)), f"{dml.__name__} node in the population"


def test_the_flag_gates_the_curve_and_the_field_completeness_scan(ctes: str):
    """Both, or a partition is normalized over survivors it should not have.

    A field that loses a member to this exclusion is PARTIAL and must be dropped
    whole rather than published summing to less than 1 — the C14 defect. Every
    other per-outcome exclusion appears in all three places; this one must too.
    """
    gate = "NOT ro.is_player_props_placeholder"
    assert ctes.count(gate) == 3, (
        "expected the gate in `deduped` plus BOTH `field_completeness` filters"
    )


# ---------------------------------------------------------------------------
# 5. The disclosure — the half a reader actually sees.
# ---------------------------------------------------------------------------


def test_the_cell_is_declared_to_the_fail_closed_merger():
    """🔴 THIS IS THE CAL-P162 FAILURE, AND IT COST A WHOLE GENERATION.

    CAL-P162 emitted the per-cell columns and declared them to neither consumer,
    so the first unit that returned a row raised `UndeclaredColumnError` and no
    generation could bank — a fail-closed merge doing exactly its job. A new
    cell adds a column, and the column must be declared in the same commit.
    """
    labels = dict(pc.nonexclusive_bundle_cell_labels())
    assert labels["polymarket/baseball"] == "pp_cell_0"
    assert "pp_cell_0" in NONEXCLUSIVE_BUNDLE_CELL_COLUMNS
    assert tuple(pc.NONEXCLUSIVE_BUNDLE_CELL_COLUMNS) == NONEXCLUSIVE_BUNDLE_CELL_COLUMNS


def test_the_revert_condition_is_a_real_condition():
    """The page renders "<cell> — returns when <condition>". The value has to
    complete that sentence, name the defect, and not end in punctuation the page
    supplies itself."""
    condition = pc.PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL["polymarket/baseball"]
    assert "writer" in condition
    assert not condition.rstrip().endswith(".")
    assert condition[0].islower(), "it continues a sentence rather than starting one"


def test_the_rule_text_describes_the_arms_that_actually_ship():
    """The payload's `rule` is now one sentence over TWO rules, so it has to
    describe both. A reader given the bundle sentence alone would be told these
    rows were never competing answers to one question — which is the opposite of
    true here: they are real questions we priced wrong (design §9.1).
    """
    text = pc.PLAYER_PROPS_PLACEHOLDER_RULE_TEXT
    assert "0.5000" in text
    assert "Player Props" in text
    assert "1.15" in text
    assert "[0.45, 0.55]" in text and "0.25" in text
    # The honest frame, and the clause §9.1 exists to protect.
    assert "market's own quote is intact" in text
    assert "never mutates resolutions" in text


def test_the_disclosure_total_is_the_sum_of_both_rules():
    """The page prints one total then the per-cell map beneath it, so the cells
    must add up to the total. Asserted against the payload builder's SOURCE
    because computing it needs a database; what is checkable here is that the
    line adds the two counts rather than publishing one of them.
    """
    source = _payload_literal_source("nonexclusive_bundle_filter")
    assert "esports_bundle_excluded + player_props_placeholder_excluded" in source
    # ...and that the bundle-only key was NOT widened. It is a live public
    # contract about the bundle rule and must not silently start meaning more.
    esports = _payload_literal_source("esports_multi_bundle_filter")
    assert "player_props" not in esports


def _payload_literal_source(key: str) -> str:
    """The source text of one dict entry in `compute_calibration_payload`."""
    import inspect

    source = inspect.getsource(pc.compute_calibration_payload)
    tree = ast.parse(source.lstrip() if source.startswith(" ") else source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    return ast.get_source_segment(source, v) or ""
    raise AssertionError(f"payload key {key!r} not found")


# ---------------------------------------------------------------------------
# 6. The statement still parses, and the sum basis is stated rather than assumed.
# ---------------------------------------------------------------------------


def test_the_population_statement_still_parses_as_postgres(ctes: str):
    sqlglot.parse_one("WITH " + ctes + " SELECT 1 FROM deduped", dialect="postgres")


def test_r3_sums_over_the_shipped_published_sum_and_says_so(props_cte: str):
    """🔴 A DIVERGENCE FROM THE FOLD THAT MEASURED THE DESIGN, STATED IN THE OPEN.

    The design's rail summed `adj_opening_probability` over `deduped` — a
    post-dedup, post-normalization sum. That cannot be referenced from here
    without a cycle: `deduped` is downstream of this very flag. So R3 uses
    `bundle_price_sum`, the shipped rendering of "the per-market published price
    sum", which is also the quantity RULE E's 1.15 is defined against.

    The two bases genuinely differ. What bounds the difference is the margin: a
    Player Props container's measured published sum is 15-19 against a threshold
    of 1.15, so no plausible basis change moves a container across it. That
    reasoning is recorded HERE rather than left in a comment, because it is the
    one place this port is not a like-for-like transplant of what was measured.
    """
    assert "bundle_price_sum bps" in props_cte
    assert "FROM deduped" not in props_cte


# ---------------------------------------------------------------------------
# 7. CERT-647 — the temporary promise covers only the rows that come back.
#
# 🔴 WHAT WENT WRONG, because a guard that does not say it invites the revert.
# K' shipped with `temporary_excluded` carrying the full R1+R2+R3+M1 union and
# `temporary_by_cell` emitted unconditionally from a module constant. The page
# printed the per-cell total, then "Part of this is temporary by design", then
# "this exclusion empties itself" — over a population whose MAJORITY is the
# historical R1/R2 residue that a forward writer fix cannot reach. The branch's
# own constants block said so in prose while the payload said the opposite.
#
# The arms are now split. "Temporary" means held ONLY by arms that end.
# ---------------------------------------------------------------------------


def _bundle_filter_entry(key: str) -> str:
    """The source text of one entry INSIDE `nonexclusive_bundle_filter`.

    Scoped to that sub-dict rather than searched globally, so a same-named key
    in a neighbouring filter can never be graded here by accident. Raises on a
    key it cannot find: a disclosure guard that quietly grades nothing is the
    failure mode this whole section exists to catch.
    """
    outer = _payload_literal_source("nonexclusive_bundle_filter")
    tree = ast.parse(outer.strip())
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == key:
                    segment = ast.get_source_segment(outer.strip(), v)
                    if not segment:
                        raise AssertionError(f"{key!r} has no readable source")
                    return segment
    raise AssertionError(f"{key!r} is not a key of nonexclusive_bundle_filter")


def _eval_entry(key: str, *, temporary: int, total: int):
    """Evaluate a shipped payload expression against a specimen.

    This RUNS the expression the build ships rather than pattern-matching it.
    The two counts are deliberately different numbers so a expression that
    reaches for the wrong variable produces the wrong value instead of an
    accidental match.
    """
    namespace = {
        "dict": dict,
        "PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL": (
            pc.PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL
        ),
        "player_props_placeholder_temporary_excluded": temporary,
        "player_props_placeholder_temporary_markets": temporary,
        "player_props_placeholder_excluded": total,
        "player_props_placeholder_markets": total,
        "esports_bundle_excluded": 0,
    }
    # Parenthesised because a multi-line payload expression carries the
    # indentation it had in the source and `eval` rejects it otherwise.
    return eval("(" + _bundle_filter_entry(key) + ")", namespace)  # noqa: S307


def test_the_temporary_sentence_disappears_when_nothing_is_temporary():
    """🔴 THE CERT-647 SPECIMEN: zero temporary, non-zero historical.

    This is the state the page reaches the day the writer is repaired — M1 and
    R3 stop matching, the R1/R2 back catalogue stays excluded. The page gates
    the whole "part of this is temporary" block on this map being non-empty, so
    an empty map here IS the sentence leaving the page.

    The shipped expression was `dict(PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL)`
    — a constant, which returns the cell in this specimen and leaves the promise
    on the page forever. That is what this test kills.
    """
    assert _eval_entry("temporary_by_cell", temporary=0, total=1_284) == {}


def test_the_historical_rows_are_still_excluded_in_that_same_specimen():
    """...and the sentence disappearing must NOT be read as the rows returning.

    Same specimen. The exclusion total is untouched and the historical count
    carries the whole of it, so the reader still meets the removal — they just
    stop being told it is coming back.
    """
    assert _eval_entry("historical_excluded", temporary=0, total=1_284) == 1_284
    assert _eval_entry("temporary_excluded", temporary=0, total=1_284) == 0


def test_temporary_excluded_counts_the_temporary_cohort_not_the_union():
    """The field's NAME is the claim. It said "this many rows are coming back"
    while carrying a union whose majority is not.

    The two specimen numbers are distinct on purpose: an expression that
    published the union would return 1,284 here and this assertion names which
    number it actually got.
    """
    assert _eval_entry("temporary_excluded", temporary=26, total=1_284) == 26
    assert _eval_entry("temporary_excluded_markets", temporary=26, total=1_284) == 26


def test_the_two_cohorts_sum_to_the_exclusion_total():
    """The page prints the per-cell total and then splits it. A reader must be
    able to add the halves and land on the number above them — the same property
    the per-cell map has against `excluded`, one level down.
    """
    temporary = _eval_entry("temporary_excluded", temporary=26, total=1_284)
    historical = _eval_entry("historical_excluded", temporary=26, total=1_284)
    assert temporary + historical == 1_284


def test_the_temporary_cell_is_emitted_while_the_cohort_is_non_empty():
    """The other direction, so the gate is not satisfied by returning `{}`
    unconditionally — which would pass every test above and silently drop
    Alex's disclosure clause entirely."""
    assert _eval_entry("temporary_by_cell", temporary=26, total=1_284) == {
        "polymarket/baseball": pc.PLAYER_PROPS_PLACEHOLDER_TEMPORARY_BY_CELL[
            "polymarket/baseball"
        ]
    }


def _temporary_flag_expression(ctes: str) -> str:
    """The SQL of `is_player_props_placeholder_temporary`, or a loud failure."""
    marker = "AS is_player_props_placeholder_temporary"
    if marker not in ctes:
        raise AssertionError("the temporary flag is not emitted by the statement")
    end = ctes.index(marker)
    start = ctes.rindex("ppp.ppp_temporary_arm", 0, end)
    return ctes[start:end]


def test_the_temporary_flag_releases_nothing_the_historical_arms_still_hold(
    ctes: str,
):
    """🔴 THE LOAD-BEARING CONJUNCT.

    A row held by R3 or M1 *and also* by R1 or R2 does not come back: the
    temporary arms release it and the historical arms keep holding it. Counting
    it as temporary would promise a return that never happens — CERT-647's
    finding, one level down. Drop this `AND NOT` and the temporary count
    silently inflates toward the union it used to be.
    """
    flag = _temporary_flag_expression(ctes)
    assert "AND NOT COALESCE(ppp.ppp_historical_arm, false)" in flag


def test_the_arms_are_carried_out_of_the_cte_on_the_right_side(props_cte: str):
    """R1/R2 are historical, R3 is temporary, and the CTE must not swap them.

    Asserted on which PREDICATE lands in which column rather than on the column
    names, because the names are the easy half to get right.
    """
    historical = props_cte[
        props_cte.index("AS ppp_historical_arm") - 600 :
        props_cte.index("AS ppp_historical_arm")
    ]
    temporary = props_cte[
        props_cte.index("AS ppp_temporary_arm") - 400 :
        props_cte.index("AS ppp_temporary_arm")
    ]
    # R1's exact spike and R2's pair-coherence test are the historical arms.
    assert "pp_half_legs = 2" in historical
    assert "pp_open_sum" in historical
    # R3's name+sum container test is the temporary one, and R1/R2's shape
    # aggregates must NOT appear beside it.
    assert "ILIKE" in temporary
    assert "pp_half_legs = 2" not in temporary


def test_a_null_sum_does_not_read_as_a_temporary_match(props_cte: str):
    """`bps.cp_sum` arrives on a LEFT JOIN. Without the COALESCE a market with
    no price sum yields NULL, `NOT NULL` is NULL, and the row falls out of BOTH
    cohorts — the halves stop summing to the total and the page's arithmetic
    quietly breaks."""
    temporary = props_cte[: props_cte.index("AS ppp_temporary_arm")]
    assert "COALESCE(" in temporary


def test_the_temporary_columns_are_declared_to_the_fail_closed_merger():
    """CAL-P162's lesson, applied to the columns this repair adds. A census
    column emitted and undeclared raises `UndeclaredColumnError` at BANK time
    and no generation can publish."""
    from app.utils.calibration_staged_futures import (
        DEFAULT_CENSUS_COLUMNS,
        DISTINCT_CENSUS_COLUMNS,
    )

    assert "player_props_placeholder_temporary_excluded" in DEFAULT_CENSUS_COLUMNS
    assert "player_props_placeholder_temporary_markets" in DEFAULT_CENSUS_COLUMNS
    # The market count is COUNT(DISTINCT market_id) and sums across chunks only
    # because it is declared as one; the outcome count is a plain COUNT(*).
    assert "player_props_placeholder_temporary_markets" in DISTINCT_CENSUS_COLUMNS
    assert (
        "player_props_placeholder_temporary_excluded" not in DISTINCT_CENSUS_COLUMNS
    )


def test_the_temporary_flag_gates_no_curve_row_of_its_own(ctes: str):
    """The split is a DISCLOSURE change, not a population change. `deduped` and
    both field-completeness filters gate on the union flag; if the temporary
    flag ever appears in a gate, this repair has quietly changed which rows the
    published curve contains — a different ship, and a Tier 1 one.
    """
    assert "NOT ro.is_player_props_placeholder_temporary" not in ctes
    assert ctes.count("NOT ro.is_player_props_placeholder") == 3
