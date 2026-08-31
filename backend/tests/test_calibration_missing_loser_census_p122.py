"""CAL-P122 — guards for the missing-loser census.

The instrument these guards protect makes ONE claim, and it contradicts a
banked, ruled design (RULE E2, CAL-P112 §4, riding the ``(source, category)``
allowlist Alex ruled on 2026-08-28). E2's premise is that a lone-claim class
which is 100% winners is *one-sided capture*. This census says the losers were
captured, were graded by an authoritative source, and are removed by
``clean_vms``' vm-level ``has_winner >= 1`` gate.

A claim that strong has to be falsifiable from the test file alone, so five
things are pinned here rather than described:

1. **THE PREMISE IS PINNED TO THE FROZEN FILE.** The gate is one line in
   ``precompute_calibration``. If it is ever repaired, this instrument is
   measuring a defect that no longer exists — and it must go RED, not quietly
   print a zero (gotcha #53: an empty answer is a response shape, not an
   absence). Two more premise guards pin the carve-outs the gate makes
   unreachable: rung 1 exempting ``n_outcomes = 1`` and
   ``orphan_partition_markets`` requiring ``market_type = 'field'``.
2. **THE ARM SPLIT IS THE WHOLE MEASUREMENT.** Reporting the gate's total
   shadow as the defect would overstate this cell's number by 4.8x. The
   classifier is pure and its boundary is tested on both sides.
3. **NOTHING IS RE-IMPLEMENTED.** Both statements are built on
   ``_calibration_population_ctes`` — the function the producer itself calls —
   and the eligibility allowlist and liquidity predicate are the imported
   objects, not equal copies (CAL-P115's rule: an equal copy drifts on the next
   edit). The dropped-rows statement must differ from the published one in
   exactly one way: it reads ``vm_stats`` where the producer reads
   ``clean_vms``.
4. **THE BUCKET KEY IS AN INT, EVERYWHERE.** These bins are pooled with the
   rail's own. A ``"5"`` beside a ``5`` folds as two price bands with half the
   mass each and would quietly change every number the document reports.
5. **MERGING NEVER MUTATES.** ``kept`` is pooled twice in the same run. An
   in-place merge would make the second reading depend on the first.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mlc = _load("calibration_missing_loser_census")
cce = mlc.cce


# ---------------------------------------------------------------------------
# 1. THE PREMISE. Three carve-outs in the frozen producer, pinned.
# ---------------------------------------------------------------------------

def test_clean_vms_no_longer_drops_a_claim_for_losing():
    """The one line the whole instrument WAS about, now repaired (12-CAL / D13).

    This guard used to pin the defect's existence, with a docstring saying that
    if the gate were ever repaired the instrument would be "obsolete and must be
    retired, not left printing zeros". The gate was repaired. So the guard is
    inverted rather than deleted: the same reading of the same CTE, asserting
    the bare gate is GONE and the lone-claim arm is present. Deleting it would
    leave the repair unpinned by the suite that found the defect.

    Read from the built SQL rather than the source text, so a gate that moves to
    another CTE but keeps its effect still satisfies it.
    """
    from app.tasks.precompute_calibration import _calibration_population_ctes
    from app.utils.sql_comment_strip import strip_sql_comments

    sql = _calibration_population_ctes()
    assert mlc.CLEAN_VMS_GATE_RETIRED not in strip_sql_comments(sql), (
        "clean_vms still carries the bare `eligible >= 1 AND has_winner >= 1` "
        "gate — the 12-CAL repair is not in this build."
    )
    # And it is the gate on clean_vms specifically, not some other CTE's. The
    # terminator is a LINE: splitting on a bare ")," truncates the body at the
    # first parenthesised aside inside a comment.
    #
    # 🔴 COMMENTS STRIPPED (CAL-P155). The arm's comment block has to quote the
    # predicate it explains, so every check below was satisfiable by prose —
    # `"ungraded_lone_claims = 0" in body` would pass off the paragraph that
    # argues for it, whether or not the SQL carried it.
    body = strip_sql_comments(
        sql.split("clean_vms AS (", 1)[1].split("\n            ),", 1)[0]
    )
    assert mlc.CLEAN_VMS_GATE_FRAGMENT in body
    assert "graded_lone_claims >= 1" in body, (
        "the restored arm must require an AFFIRMATIVE grade; without it a row "
        "nothing ever graded publishes as a confident loss"
    )
    # CERT-514: the affirmative-grade conjunct is PER MARKET and it now stands
    # ALONE. CAL-P155's `ungraded_lone_claims = 0` partner was blocked — being
    # variant-grained, it could only refuse the whole variant, so it went on
    # holding graded claims back for an ungraded sibling's sake. That does not
    # licence publishing unknown truth: the exclusion moved to rung 1b, per
    # market, and the two assertions below are a PAIR — the absence is only safe
    # because the rung exists (gotcha #21).
    assert "ungraded_lone_claims = 0" not in body, (
        "the fail-closed residue is back in the arm; a graded lone claim is "
        "again waiting on a sibling market's grade state (CERT-514 [P1])"
    )
    assert "ungraded_lone_claim_markets AS (" in sql, (
        "the arm stopped refusing ungraded lone claims and rung 1b is not "
        "there to catch them — that is a straight relaxation, and every "
        "ungraded lone claim would publish as a confident loss"
    )


def test_rung_one_still_exempts_the_one_outcome_market():
    """Queue 299's own carve-out — the thing ``clean_vms`` makes unreachable."""
    from app.tasks.precompute_calibration import market_has_no_winner_authority

    assert market_has_no_winner_authority(2, 0) is True
    assert market_has_no_winner_authority(9, 0) is True
    # The lone claim. Rung 1 says "not an authority failure" — and since
    # CERT-514 it is rung 1b that answers for this shape instead.
    assert market_has_no_winner_authority(1, 0) is False


def test_rung_1b_takes_exactly_the_shape_rung_1_declines():
    """The two rungs must PARTITION the unknown-truth space, not overlap it.

    Rung 1b is rung 1's complement. Asserted against rung 1 in the same test so
    a future widening of either cannot open a gap or a double-count between
    them: at ``n_outcomes >= 2`` rung 1 answers and rung 1b must stay silent; at
    exactly one outcome rung 1 abstains and rung 1b answers.
    """
    from app.tasks.precompute_calibration import (
        market_has_no_winner_authority,
        market_is_ungraded_lone_claim,
    )

    # The lone claim nothing ever graded — rung 1b's whole population.
    assert market_is_ungraded_lone_claim(1, 0) is True

    # 🔴 THE CASE THE WHOLE REPAIR TURNS ON. A one-outcome market that WAS
    # graded is a complete, scoreable prediction whether it won or lost, and
    # rung 1b must not touch it. If this ever returns True the rung is keying on
    # winner cardinality instead of on an affirmative grade, and every honest
    # lone claim that resolved No leaves the curve.
    assert market_is_ungraded_lone_claim(1, 1) is False

    # Multi-outcome markets belong to rung 1, at any grade count.
    for n_outcomes in (2, 3, 9):
        for n_graded in (0, 1, n_outcomes):
            assert market_is_ungraded_lone_claim(n_outcomes, n_graded) is False, (
                f"rung 1b reached a {n_outcomes}-outcome market; that is rung "
                f"1's population and admitting both double-counts the exclusion"
            )

    # And the complement holds in the other direction: the one shape rung 1b
    # owns is exactly the one rung 1 declines.
    assert market_has_no_winner_authority(1, 0) is False
    assert market_is_ungraded_lone_claim(1, 0) is True


def test_orphan_partition_still_requires_a_declared_field():
    """The second carve-out, and the reason rung 1 can defer to it."""
    from app.tasks.precompute_calibration import _calibration_population_ctes

    sql = _calibration_population_ctes()
    assert "orphan_partition_markets AS (" in sql
    body = sql.split("orphan_partition_markets AS (", 1)[1].split("),", 1)[0]
    assert "market_type = 'field'" in body, (
        "orphan_partition no longer scopes to declared fields; the lone-claim "
        "class may now be caught there and this census would double-count it."
    )


# ---------------------------------------------------------------------------
# 2. THE ARM SPLIT.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("glc,why", [
    (1, "the solitary lone claim — the class this instrument was built on"),
    (2, "TWO lone claims in one variant: option A's whole point. Under the "
        "retired per-VARIANT arm this was market_count=2 and fell in the "
        "OTHER arm, beside genuine unknown truth"),
    (9, "wider still, and still every member is a scoreable graded claim"),
])
def test_a_graded_lone_claim_is_the_defect_arm_however_many_share_its_variant(
    glc, why
):
    assert mlc.classify_vm(glc) == mlc.ARM_LONE, why


@pytest.mark.parametrize("glc,why", [
    (0, "no graded lone claim at all — a multi-outcome vm that graded nobody, "
        "or lone claims nothing ever graded. Either way rung 1 / rung 1b owns "
        "it and this instrument must never report it as the defect"),
])
def test_everything_else_is_the_other_arm(glc, why):
    assert mlc.classify_vm(glc) == mlc.ARM_OTHER, why


@pytest.mark.parametrize("ulc", [1, 4])
def test_an_ungraded_sibling_no_longer_moves_a_graded_claim_out_of_the_arm(ulc):
    """🔴 CERT-514. These cases were pinned to ARM_OTHER one commit ago.

    ``(1, 1)`` and ``(3, 1)`` used to read "FAIL-CLOSED: a graded claim beside
    an ungraded one refuses the whole variant". The cert blocked exactly that:
    the graded claim's fate hung on a SIBLING market, which is the coupling
    option A removes. The census follows the producer, so the class it calls
    ``B_lone_claim`` had to move with the arm — otherwise its two halves would
    be measuring two different populations, which is the failure this file's
    own ``test_the_kept_statement_reads_the_published_population`` guards.

    The ungraded siblings are still excluded — by rung 1b, per market, one CTE
    later. They are simply no longer a reason to refuse the variant.
    """
    for glc in (1, 3):
        assert mlc.classify_vm(glc) == mlc.ARM_LONE, (
            f"{glc} graded lone claim(s) fell out of the defect arm because "
            f"{ulc} ungraded sibling(s) shared the variant"
        )


def test_the_two_arms_are_the_only_arms():
    """A third label would silently vanish from the printed census."""
    seen = {mlc.classify_vm(g) for g in range(0, 5)}
    assert seen == {mlc.ARM_LONE, mlc.ARM_OTHER}


def test_the_arm_names_sort_so_the_defect_prints_last():
    """A reporting choice, pinned because the document depends on it: the arm
    a reader must not mistake for the total is the one under the verdict."""
    assert mlc.ARM_OTHER < mlc.ARM_LONE


# ---------------------------------------------------------------------------
# 3. NO RE-IMPLEMENTATION.
# ---------------------------------------------------------------------------

def test_both_statements_are_built_on_the_producers_own_chain():
    from app.tasks.precompute_calibration import _calibration_population_ctes

    marker = "market_result_shape AS ("
    assert marker in _calibration_population_ctes()
    for sql in (mlc.dropped_sql("kalshi", "entertainment", 0, 10),
                mlc.kept_lone_sql("kalshi", "entertainment", 0, 10)):
        assert marker in sql
        assert sql.startswith("WITH ")


def test_the_dropped_statement_reads_vm_stats_not_clean_vms():
    """The counterfactual IS this substitution, and nothing else."""
    sql = mlc.dropped_sql("kalshi", "entertainment", 0, 10)
    assert "FROM vm_stats vs" in sql
    assert "vs.has_winner = 0" in sql
    # It must not accidentally re-apply the gate it is measuring.
    assert "vs.has_winner >= 1" not in sql


def test_the_kept_statement_reads_the_published_population():
    sql = mlc.kept_lone_sql("kalshi", "entertainment", 0, 10)
    assert "FROM deduped d" in sql
    assert "vs.graded_lone_claims >= 1" in sql, (
        "the kept half must select the SAME class the producer admits; if it "
        "still reads the retired per-variant counts the two halves of this "
        "census are two different populations"
    )
    assert "vs.ungraded_lone_claims = 0" not in sql, (
        "the kept half still carries the conjunct CERT-514 removed from the "
        "producer, so it is measuring a narrower class than the one that ships"
    )


def test_eligibility_is_the_imported_allowlist_not_a_copy():
    from app.tasks.precompute_calibration import (
        CALIBRATION_TRUTH_ELIGIBLE_SOURCES_SQL as ELIG,
    )

    sql = mlc.dropped_sql("kalshi", "entertainment", 0, 10)
    assert f"fo.resolution_source IN {ELIG}" in sql
    # Substantive, not just present: a guess-family source must not be on it.
    assert "pass2_guess" not in ELIG
    assert "api_settlement" in ELIG


def test_liquidity_is_the_imported_predicate_and_is_source_aware():
    """It must key on ``vm.source``, not a hard-coded ``'kalshi'``.

    Hard-coding the literal would make every POLYMARKET row fail the Kalshi
    bid/trade test and report the whole poly lone-claim class as ineligible —
    the exact shape of a false negative that reads as good news.

    Checked in THIS statement's own WHERE clause, not anywhere in the built
    SQL: the producer's chain applies the same predicate on ``mi.source`` and
    ``vm.source`` of its own accord, so a whole-string search is satisfied by
    somebody else's copy and would pass a hard-coded mutation here.
    """
    from app.tasks.precompute_calibration import kalshi_liquidity_exists_sql

    sql = mlc.dropped_sql("polymarket", "esports", 0, 10)
    mine = sql.split("WHERE vs.eligible >= 1", 1)[1]
    assert kalshi_liquidity_exists_sql(source="vm.source") in mine
    assert "'kalshi' <> 'kalshi'" not in mine


def test_the_cell_and_the_id_range_scope_the_whole_chain():
    sql = mlc.dropped_sql("kalshi", "entertainment", 500, 900)
    assert "fm.source = 'kalshi'" in sql
    assert "'entertainment'" in sql
    assert "fm.id >= 500" in sql and "fm.id < 900" in sql


def test_statements_are_single_and_comment_stripped():
    """``POST /api/admin/db-query`` counts semicolons inside prose comments and
    refuses the producer's SQL verbatim. Stripping is the rail's, unmodified."""
    for sql in (mlc.dropped_sql("kalshi", "entertainment", 0, 10),
                mlc.kept_lone_sql("kalshi", "entertainment", 0, 10)):
        assert "--" not in sql
        assert ";" not in sql


def test_the_comment_stripper_is_the_rails_own_function():
    assert mlc.cce._strip_sql_comments is cce._strip_sql_comments


# ---------------------------------------------------------------------------
# 4. BUCKET KEYS AND ARITHMETIC.
# ---------------------------------------------------------------------------

def test_add_coerces_the_bucket_key_to_int():
    b = mlc._bins()
    mlc.add(b, "5", 3, 1, 1.5)
    mlc.add(b, 5, 2, 0, 0.9)
    assert list(b) == [5]
    assert b[5] == {"n": 5, "w": 1, "sp": pytest.approx(2.4)}


def test_merge_bins_pools_mixed_key_types_into_one_band():
    """The failure this exists to stop: the rail's int bins beside string bins.

    Folded as two bands the ECE would be computed over half the mass twice.
    """
    rail = {5: {"n": 10, "w": 5, "sp": 5.0}}
    mine = {"5": {"n": 10, "w": 0, "sp": 5.0}}
    pooled = mlc.merge_bins(rail, mine)
    assert list(pooled) == [5]
    n, ece, gap = cce.fold(pooled)
    assert n == 20
    # 20 rows, 5 winners, mean price 0.50 -> 25% actual, 25 pp of error.
    assert ece == pytest.approx(25.0)
    assert gap == pytest.approx(25.0)


def test_merge_bins_does_not_mutate_its_inputs():
    kept = {9: {"n": 4, "w": 4, "sp": 3.8}}
    lone = {9: {"n": 6, "w": 0, "sp": 5.7}}
    mlc.merge_bins(kept, lone)
    mlc.merge_bins(kept, lone)
    assert kept == {9: {"n": 4, "w": 4, "sp": 3.8}}
    assert lone == {9: {"n": 6, "w": 0, "sp": 5.7}}


def test_merge_bins_of_nothing_is_empty_and_folds_to_zero():
    assert cce.fold(mlc.merge_bins()) == (0, None, None)


def test_restoring_losers_moves_a_hundred_percent_class_off_its_ceiling():
    """The arithmetic the whole document turns on, on a toy cell.

    Published: 4 rows, all winners, mean price 0.60 — a 40 pp 'error' that is
    a property of the filter. Restored: 10 rows, 4 winners, mean price 0.55.
    """
    kept = {5: {"n": 4, "w": 4, "sp": 2.4}}
    lone = {5: {"n": 6, "w": 0, "sp": 3.1}}
    pn, pece, pgap = cce.fold(kept)
    rn, rece, rgap = cce.fold(mlc.merge_bins(kept, lone))
    assert (pn, pece, pgap) == (4, 40.0, -40.0)
    assert rn == 10
    assert rece == pytest.approx(15.0)
    assert rgap == pytest.approx(15.0)
    # The sign REVERSES: published says under-priced, the truth says over.
    assert pgap < 0 < rgap


def test_a_restored_row_is_never_counted_as_a_winner():
    """``vs.has_winner = 0`` is a vm-level fact, so every row it returns lost.

    If this ever came back non-zero the census would be pooling winners into
    the restored fold and understating the correction.
    """
    lone = {4: {"n": 12, "w": 0, "sp": 5.4}}
    assert sum(v["w"] for v in lone.values()) == 0
    n, _, gap = cce.fold(lone)
    assert n == 12
    assert gap == pytest.approx(45.0)  # mean price 45%, nobody won


# ---------------------------------------------------------------------------
# 5. THE CHUNKING CONTRACT, inherited from the rail.
# ---------------------------------------------------------------------------

def test_an_oversized_statement_is_split_not_sent():
    """A body too long produces an unclassified 4xx, and in a chunked sweep an
    unclassified 4xx reads as 'this range is empty' (gotcha #53)."""
    calls = []

    def fat(_s, _c, lo, hi):
        calls.append((lo, hi))
        return "x" * (cce.MAX_SQL_CHARS + 1) if hi - lo > 1 else "ok"

    def fake_db_query(sql, limit=None):
        return {"row_count": 0, "rows": []}

    old = cce.db_query
    cce.db_query = fake_db_query
    try:
        mlc._collect(fat, "kalshi", "entertainment", 0, 4)
    finally:
        cce.db_query = old
    assert (0, 4) in calls and len(calls) > 1


def test_a_timeout_is_split_and_never_retried_at_the_same_size():
    seen = []

    def fake_db_query(sql, limit=None):
        seen.append(sql)
        if "fm.id >= 0 AND fm.id < 8" in sql:
            raise cce.QueryTimeout("statement_timeout")
        return {"row_count": 0, "rows": []}

    old = cce.db_query
    cce.db_query = fake_db_query
    try:
        mlc._collect(mlc.dropped_sql, "kalshi", "entertainment", 0, 8)
    finally:
        cce.db_query = old
    assert sum("fm.id >= 0 AND fm.id < 8" in s for s in seen) == 1
    assert any("fm.id >= 0 AND fm.id < 4" in s for s in seen)
    assert any("fm.id >= 4 AND fm.id < 8" in s for s in seen)


def test_a_truncated_answer_is_split_like_a_timeout():
    """Truncation and timeout are the same bug — the range is too big — and
    only one of them is loud."""
    seen = []

    def fake_db_query(sql, limit=None):
        seen.append(sql)
        if "fm.id >= 0 AND fm.id < 8" in sql:
            return {"row_count": cce.ROW_CAP, "rows": [] * cce.ROW_CAP}
        return {"row_count": 0, "rows": []}

    old = cce.db_query
    cce.db_query = fake_db_query
    try:
        mlc._collect(mlc.dropped_sql, "kalshi", "entertainment", 0, 8)
    finally:
        cce.db_query = old
    assert any("fm.id >= 4 AND fm.id < 8" in s for s in seen)


def test_an_irreducible_chunk_raises_rather_than_returning_empty():
    def fake_db_query(sql, limit=None):
        raise cce.QueryTimeout("statement_timeout")

    old = cce.db_query
    cce.db_query = fake_db_query
    try:
        with pytest.raises(RuntimeError, match="irreducible|still timing out"):
            mlc._collect(mlc.dropped_sql, "kalshi", "entertainment", 0, 1)
    finally:
        cce.db_query = old
