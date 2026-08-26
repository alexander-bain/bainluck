"""CAL-P096 — the fold narrowing rewrite (C-FOLD-EXPLAIN-1 §3), guarded structurally.

WHAT THE REWRITE IS. ``_calibration_population_ctes`` used to compute
``ranked_outcomes``' two window functions over the rows produced by nine
row-preserving LEFT JOINs. C-FOLD-EXPLAIN-1 measured the cost against production:
the outer ``WindowAgg`` is 84.2% of the plan (4,330,606 of 5,143,141) and its child
Sort alone is 2,115,624, because the joins widen every one of ~1.5M sorted rows
from ~43 to ~652 bytes before the Sort. The rewrite computes the window over the
narrow ``fo ⋈ virtual_market ⋈ clean_vms`` row in ``ranked_outcomes_core`` and
joins the nine market-level slices after it, in ``ranked_outcomes``.

WHAT THESE TESTS ARE FOR. The rewrite's whole claim is ROW IDENTITY: the same
final rows with the same values. That claim rests on three premises, and a premise
that is only true today is a defect waiting for the next editor:

1. **The nine joined relations are at most one row per ``market_id``.** If any one
   of them fanned out, the pre-split window would have seen a different row
   multiset than the post-split window does, and ``rn`` would move. Guarded by
   :class:`TestDeferredJoinsAreRowPreserving` — by the SHAPE of each relation's
   definition, not by string-matching today's join list.
2. **No deferred column feeds either window.** Guarded by
   :class:`TestWindowsDependOnCoreOnly`.
3. **The emitted ``ranked_outcomes`` relation is unchanged.** Same columns, same
   order, and the rest of the CTE chain byte-identical to the pre-split SQL frozen
   in ``tests/fixtures/cal_p096_fused_population_ctes.sql``. Guarded by
   :class:`TestEmittedRelationIsUnchanged`, which is also the fixture's STALENESS
   alarm: change ``market_info`` and this goes red telling you to re-freeze, rather
   than letting the oracle quietly stop being the thing it claims to be.

Row identity against a real database — running both SQL forms and diffing the
``deduped`` rows — is
``tests/integration/test_calibration_fold_narrowing_row_identity_pg.py``. There is
no local Postgres in this sandbox, so that one is a CI gate; these are not.
"""

from __future__ import annotations

import pathlib
import re
from pathlib import Path

import pytest

from app.tasks.precompute_calibration import _calibration_population_ctes
from app.utils import fold_narrowing_gate as gate

FIXTURE = Path(__file__).parent / "fixtures" / "cal_p096_fused_population_ctes.sql"

#: The nine per-market slices deferred past the window, with the alias each is
#: joined under. Named explicitly so a tenth join added to ``ranked_outcomes``
#: without a soundness argument fails :meth:`TestDeferredJoinsAreRowPreserving
#: .test_no_undeclared_join`.
DEFERRED_JOINS: dict[str, str] = {
    "malformed_binaries": "mb",
    "esports_multi_bundles": "emb",
    "no_winner_markets": "nwm",
    "draw_authority_markets": "dam",
    "orphan_partition_markets": "opm",
    "nonexclusive_bundle_markets": "nbm",
    "golf_placeholder_markets": "gpm",
    "mex_field_candidates": "mfc",
    "mex_field_divisor": "mfd",
}

#: Columns ``ranked_outcomes`` projects from the deferred joins. None of these may
#: appear in ``ranked_outcomes_core``.
DEFERRED_COLUMNS: tuple[str, ...] = (
    "candidate_market_id",
    "mnm_cp_sum",
    "is_malformed_binary",
    "malformed_win_count",
    "is_esports_bundle",
    "is_no_winner_market",
    "is_draw_authority_missing",
    "is_orphan_partition",
    "is_nonexclusive_bundle",
    "is_golf_placeholder",
)


# ---------------------------------------------------------------------------
# SQL text helpers. Deliberately crude: they strip ``--`` comments and slice on
# CTE names. Nothing here parses SQL — a parser would be a second implementation
# of the thing under test.
# ---------------------------------------------------------------------------
def strip_comments(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.split("\n"))


def cte_body(sql: str, name: str) -> str:
    """The text of CTE ``name``, from its opening paren to its matching close."""
    marker = re.search(rf"\b{re.escape(name)}\s+AS\s+(MATERIALIZED\s+)?\(", sql)
    assert marker is not None, f"CTE {name!r} not found"
    start = sql.index("(", marker.start())
    depth = 0
    for i in range(start, len(sql)):
        if sql[i] == "(":
            depth += 1
        elif sql[i] == ")":
            depth -= 1
            if depth == 0:
                return sql[start + 1 : i]
    raise AssertionError(f"unbalanced parens in CTE {name!r}")


def select_list(body: str) -> list[str]:
    """Output column NAMES of a CTE body's top-level SELECT, in order."""
    s = strip_comments(body)
    i = s.index("SELECT") + len("SELECT")
    depth, items, cur = 0, [], []
    j = i
    while j < len(s):
        ch = s[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif (
            depth == 0
            and s[j : j + 4].upper() == "FROM"
            and not s[j - 1].isalnum()
            and not s[j + 4].isalnum()
        ):
            break
        if depth == 0 and ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        j += 1
    items.append("".join(cur))

    names = []
    for item in items:
        text = " ".join(item.split())
        if not text:
            continue
        alias = re.search(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", text, re.I)
        names.append(alias.group(1) if alias else text.split(".")[-1])
    return names


@pytest.fixture(scope="module")
def sql() -> str:
    return _calibration_population_ctes()


@pytest.fixture(scope="module")
def frozen() -> str:
    return FIXTURE.read_text()


# ---------------------------------------------------------------------------
class TestTheSplitExists:
    """Red-first pins. Every one of these fails at the pre-split tree."""

    def test_core_cte_exists_and_is_materialized(self, sql: str) -> None:
        # MATERIALIZED is not decoration. ``ranked_outcomes_core`` has exactly one
        # referent, so PG12+ inlines it by default — which would push the nine
        # joins straight back underneath the window and silently undo the rewrite
        # while every row count stayed self-consistent.
        assert "ranked_outcomes_core AS MATERIALIZED (" in sql

    def test_outer_cte_is_still_materialized(self, sql: str) -> None:
        # Four referents (field_completeness, normalized, and the liq_summary /
        # published_summary counters ``compute_calibration_payload`` appends).
        assert "ranked_outcomes AS MATERIALIZED (" in sql

    def test_core_carries_no_join_at_all_beyond_its_three_relations(
        self, sql: str
    ) -> None:
        body = strip_comments(cte_body(sql, "ranked_outcomes_core"))
        assert "LEFT JOIN" not in body
        for relation in DEFERRED_JOINS:
            assert relation not in body, f"{relation} must not be in the core scan"

    def test_core_projects_no_deferred_column(self, sql: str) -> None:
        names = select_list(cte_body(sql, "ranked_outcomes_core"))
        assert not set(names) & set(DEFERRED_COLUMNS)

    def test_outer_reads_only_the_core_and_the_nine(self, sql: str) -> None:
        body = strip_comments(cte_body(sql, "ranked_outcomes"))
        assert "FROM ranked_outcomes_core core" in body
        assert "futures_outcomes" not in body, (
            "the outer CTE must not re-scan futures_outcomes — every base column "
            "it needs is projected by the core"
        )
        for relation, alias in DEFERRED_JOINS.items():
            assert f"LEFT JOIN {relation} {alias} ON {alias}.market_id = core.market_id" in body


class TestDeferredJoinsAreRowPreserving:
    """Premise 1 — the soundness argument, checked against each relation's shape.

    A LEFT JOIN that can produce two rows for one ``market_id`` would have made
    the pre-split window see a different multiset than the post-split window sees.
    Each of the nine is therefore either its own ``GROUP BY fo.market_id``, or a
    filter over ``market_result_shape`` — which is itself ``GROUP BY fo.market_id``
    against ``market_info``, and ``market_info`` is keyed on the ``futures_markets``
    primary key so it cannot fan the group out.
    """

    def test_market_result_shape_is_grouped_per_market(self, sql: str) -> None:
        body = strip_comments(cte_body(sql, "market_result_shape"))
        assert "GROUP BY fo.market_id" in body

    def test_market_info_is_one_row_per_market(self, sql: str) -> None:
        body = strip_comments(cte_body(sql, "market_info"))
        assert "SELECT fm.id AS market_id" in body
        assert "FROM futures_markets fm" in body
        assert "JOIN" not in body, (
            "market_info must stay a single-table scan on the futures_markets "
            "primary key — a join here could fan out market_result_shape and "
            "with it seven of the nine deferred relations"
        )

    @pytest.mark.parametrize("relation", sorted(DEFERRED_JOINS))
    def test_relation_is_at_most_one_row_per_market(
        self, sql: str, relation: str
    ) -> None:
        body = strip_comments(cte_body(sql, relation))
        grouped = "GROUP BY fo.market_id" in body
        from_shape = "FROM market_result_shape mrs" in body
        assert grouped or from_shape, (
            f"{relation} is joined to ranked_outcomes_core on market_id after the "
            "window. It must be provably at most one row per market_id — either a "
            "GROUP BY fo.market_id of its own, or a filter over "
            "market_result_shape. If it is neither, the window can no longer be "
            "computed before it and this rewrite is unsound."
        )

    def test_no_undeclared_join(self, sql: str) -> None:
        body = strip_comments(cte_body(sql, "ranked_outcomes"))
        joined = set(re.findall(r"LEFT JOIN\s+([A-Za-z_][A-Za-z0-9_]*)", body))
        assert joined == set(DEFERRED_JOINS), (
            "a join was added to or removed from ranked_outcomes without updating "
            "DEFERRED_JOINS — and therefore without a row-preservation argument"
        )


class TestWindowsDependOnCoreOnly:
    """Premise 2 — no deferred column reaches a PARTITION BY or ORDER BY."""

    def _window_clauses(self, body: str) -> list[str]:
        # Paren-BALANCED, because a lazy ``OVER\s*\((.*?)\)`` stops at the close
        # paren of ``ABS(...)`` inside the ORDER BY — it returns a clause that
        # ends mid-expression and every assertion against it is then vacuous.
        s = strip_comments(body)
        clauses = []
        for match in re.finditer(r"\bOVER\s*\(", s):
            depth, start = 0, s.index("(", match.start())
            for i in range(start, len(s)):
                if s[i] == "(":
                    depth += 1
                elif s[i] == ")":
                    depth -= 1
                    if depth == 0:
                        clauses.append(s[start + 1 : i])
                        break
        return clauses

    def test_both_windows_live_in_the_core(self, sql: str) -> None:
        core = cte_body(sql, "ranked_outcomes_core")
        assert "ROW_NUMBER() OVER (" in core
        assert "RANK() OVER (" in core
        outer = strip_comments(cte_body(sql, "ranked_outcomes"))
        assert "OVER (" not in outer

    def test_window_clauses_reference_no_deferred_alias(self, sql: str) -> None:
        clauses = self._window_clauses(cte_body(sql, "ranked_outcomes_core"))
        assert len(clauses) == 2
        for clause in clauses:
            for alias in DEFERRED_JOINS.values():
                assert not re.search(rf"\b{alias}\." , clause), (
                    f"window clause reads {alias}. — the window can no longer be "
                    "computed before the joins"
                )

    def test_rn_keeps_its_total_order(self, sql: str) -> None:
        # Queue 300D Item 1 / Alex's 2026-08-03 tie authority: distance from 50%
        # is not a total order, so the tie-break on the immutable outcome id is
        # what makes rn reproducible at all. Narrowing the window's input must not
        # be an excuse to lose it.
        core = strip_comments(cte_body(sql, "ranked_outcomes_core"))
        clause = self._window_clauses(core[core.index("ROW_NUMBER()") :])[0]
        assert "PARTITION BY cv.vm_id" in clause
        assert clause.rstrip().endswith("fo.id")


class TestEmittedRelationIsUnchanged:
    """Premise 3 — and the frozen oracle's staleness alarm."""

    def test_column_names_and_order_match_the_frozen_sql(
        self, sql: str, frozen: str
    ) -> None:
        assert select_list(cte_body(sql, "ranked_outcomes")) == select_list(
            cte_body(frozen, "ranked_outcomes")
        )

    def test_thirty_one_columns(self, sql: str) -> None:
        assert len(select_list(cte_body(sql, "ranked_outcomes"))) == 31

    def test_everything_outside_ranked_outcomes_is_byte_identical(
        self, sql: str, frozen: str
    ) -> None:
        """The fixture is the pre-split SQL. It is only an oracle while the rest of
        the chain still matches it.

        If this goes red, the fix is NOT to relax it: regenerate the fixture from
        the pre-split tree, or accept that the row-identity proof in the pg
        integration test is now comparing against something that is no longer the
        thing it certified.
        """
        tail = "            field_completeness AS ("
        new_head = sql[: sql.index("            -- CAL-P096 (C-FOLD-EXPLAIN-1 §3)")]
        old_head = frozen[: frozen.index("            ranked_outcomes AS MATERIALIZED (")]
        assert new_head == old_head
        assert sql[sql.index(tail) :] == frozen[frozen.index(tail) :]


class TestEveryCallPathSplits:
    """The horizon surface and the staged/frozen-roster build use the same body."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"frozen_vm_roster": True},
            {"market_info_extra": "AND MOD(fm.id, 97) = 0"},
            {
                "curve_price": "hp.snapshot_probability",
                "curve_price_join": "JOIN horizon_price hp ON hp.outcome_id = fo.id",
                "rn_order": "ABS(hp.snapshot_probability - 0.5)",
                "leading_ctes": "horizon_price AS (SELECT 1 AS outcome_id, 0.5 AS snapshot_probability),\n",
            },
        ],
        ids=["headline", "frozen_roster", "mod_sampled", "horizon"],
    )
    def test_split_survives(self, kwargs: dict) -> None:
        emitted = _calibration_population_ctes(**kwargs)
        assert "ranked_outcomes_core AS MATERIALIZED (" in emitted
        assert "LEFT JOIN" not in strip_comments(
            cte_body(emitted, "ranked_outcomes_core")
        )
        assert len(select_list(cte_body(emitted, "ranked_outcomes"))) == 31

    def test_the_horizon_price_join_stays_in_the_core(self) -> None:
        # The horizon join is an INNER join and therefore a FILTER: it decides
        # which outcomes exist at the snapshot. It must run BEFORE the window, or
        # rn would be ranked over rows the horizon does not contain.
        emitted = _calibration_population_ctes(
            curve_price="hp.snapshot_probability",
            curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
            rn_order="ABS(hp.snapshot_probability - 0.5)",
            leading_ctes="horizon_price AS (SELECT 1 AS outcome_id, 0.5 AS snapshot_probability),\n",
        )
        core = strip_comments(cte_body(emitted, "ranked_outcomes_core"))
        assert "JOIN horizon_price hp ON hp.outcome_id = fo.id" in core


# ===========================================================================
# CAL-P098 — the ruler itself.
#
# `C-FOLD-REWRITE-1` BLOCKed on four P1s, and three of them were about the
# INSTRUMENT rather than the rewrite: the row-identity harness compared two
# snapshots with an MD5, the named-node gate was never measured, and four of
# five mutation controls did not exist. The classes below are the DB-free half
# of the fix — they prove the harness is well-formed before CI's Postgres
# proves it runs, which matters because there is no local Postgres in this
# sandbox (``initdb`` dies on ``shmget``) and CI is the only executor.
# ===========================================================================


class TestTheFrozenResiduePlan:
    """G1 pins the sample. A plan that drifts off it is not this gate."""

    def test_at_least_eight_residues(self) -> None:
        assert len(gate.RESIDUE_PLAN) >= 8

    def test_spans_both_frozen_moduli(self) -> None:
        assert {mod for mod, _ in gate.RESIDUE_PLAN} == {64, 257}

    def test_includes_residue_zero_and_both_edges(self) -> None:
        by_mod: dict[int, set[int]] = {}
        for mod, residue in gate.RESIDUE_PLAN:
            by_mod.setdefault(mod, set()).add(residue)
        for mod, residues in by_mod.items():
            assert 0 in residues, f"MOD {mod} does not sample residue 0"
            assert mod - 1 in residues, f"MOD {mod} does not sample its edge residue"

    def test_residues_are_non_adjacent(self) -> None:
        assert gate.residues_are_non_adjacent(gate.RESIDUE_PLAN)

    def test_the_adjacency_check_can_fail(self) -> None:
        # A predicate that cannot say no is not a check.
        assert not gate.residues_are_non_adjacent([(64, 3), (64, 4)])

    def test_the_sample_predicate_targets_market_info_only(self) -> None:
        assert gate.sample_predicate(64, 0) == "AND MOD(fm.id, 64) = 0"
        assert gate.sample_predicate(None, 0) == ""
        with pytest.raises(ValueError):
            gate.sample_predicate(64, 64)


class TestTheComparatorIsTheFrozenOracle:
    """G1 asks for bilateral ``EXCEPT ALL``, duplicates, and buckets LAST."""

    @pytest.fixture(scope="class")
    def statement(self) -> str:
        return gate.g1_statement(old_chain="o AS (SELECT 1)", new_chain="n AS (SELECT 1)")

    def test_both_directions_of_except_all(self, statement: str) -> None:
        assert "SELECT * FROM old_rows EXCEPT ALL SELECT * FROM new_rows" in statement
        assert "SELECT * FROM new_rows EXCEPT ALL SELECT * FROM old_rows" in statement

    def test_duplicate_cardinality_is_compared_by_outcome_id(self, statement: str) -> None:
        assert "dup_old" in statement and "dup_new" in statement
        assert "GROUP BY outcome_id" in statement

    def test_buckets_are_present_as_the_secondary_check(self, statement: str) -> None:
        assert "buckets_old" in statement and "buckets_new" in statement
        assert "width_bucket(adj_opening_probability, 0, 1, 10)" in statement

    def test_no_digest_and_no_limit(self, statement: str) -> None:
        # The two shapes the BLOCK named: an MD5 cannot say WHICH rows differ,
        # and a LIMIT silently compares a prefix (the db-query 1000-row cap).
        assert "md5(" not in statement.lower()
        assert "limit" not in statement.lower()

    def test_each_chain_appears_exactly_once(self) -> None:
        statement = gate.g1_statement(
            old_chain="oldmarker AS (SELECT 1)", new_chain="newmarker AS (SELECT 1)"
        )
        assert statement.count("oldmarker") == 1
        assert statement.count("newmarker") == 1

    def test_the_returned_column_order_matches_G1_COLUMNS(self, statement: str) -> None:
        # The final projection block — the last SELECT that precedes the first
        # counter, not the last SELECT in the file (which is a scalar subquery).
        first = statement.index("AS n_old")
        tail = statement[statement.rindex("SELECT", 0, first) :]
        for name in gate.G1_COLUMNS:
            assert f"AS {name}" in tail, f"{name} is not projected"
        positions = [tail.index(f"AS {n}") for n in gate.G1_COLUMNS]
        assert positions == sorted(positions), (
            "G1_COLUMNS is zipped against the result row by POSITION; if the "
            "SELECT order and the constant disagree every counter is misread"
        )

    def test_every_g1_named_column_is_actually_projected_by_deduped(self) -> None:
        # ``deduped`` is ``normalized``'s ``ro.*`` plus three adds, and
        # ``normalized`` is ``ranked_outcomes``' ``ro.*`` plus three adds.
        emitted = _calibration_population_ctes()
        published = set(select_list(cte_body(emitted, "ranked_outcomes")))
        published |= {"is_mex_normalized", "is_field_incomplete", "adj_opening_probability"}
        missing = [c for c in gate.G1_REQUIRED_COLUMNS if c not in published]
        assert not missing, f"G1 names {missing}, which deduped does not publish"


class TestTheMutantsApplyOrRaise:
    """A mutation that silently no-ops turns a control into a rubber stamp."""

    @pytest.fixture(scope="class")
    def new_chain(self) -> str:
        return _calibration_population_ctes()

    @pytest.mark.parametrize(
        "name",
        ["global_rn1", "flag_flip", "narrow_population"],
    )
    def test_the_chain_mutants_change_the_sql(self, new_chain: str, name: str) -> None:
        mutated = getattr(gate, f"mutant_{name}")(new_chain)
        assert mutated != strip_comments(new_chain)
        assert mutated.count("(") == mutated.count(")"), "unbalanced parens"

    def test_global_rn1_lands_in_the_joined_cte_not_the_core(self, new_chain: str) -> None:
        mutated = gate.mutant_global_rn1(new_chain)
        assert "WHERE core.rn = 1" in cte_body(mutated, "ranked_outcomes")
        assert "WHERE core.rn = 1" not in cte_body(mutated, "ranked_outcomes_core")

    def test_flag_flip_touches_a_census_only_flag(self, new_chain: str) -> None:
        # It must be a flag ``deduped``'s WHERE does not read, or the mutant
        # changes MEMBERSHIP and stops being a value-parity control.
        mutated = gate.mutant_flag_flip(new_chain)
        assert "(nbm.market_id IS NULL) AS is_nonexclusive_bundle" in mutated
        assert "NOT ro.is_nonexclusive_bundle" not in strip_comments(
            cte_body(new_chain, "deduped")
        )

    def test_narrow_population_lands_in_the_core(self, new_chain: str) -> None:
        mutated = gate.mutant_narrow_population(new_chain)
        assert "AND MOD(fo.id, 2) = 0" in cte_body(mutated, "ranked_outcomes_core")

    def test_a_missing_anchor_raises_rather_than_returning_the_input(self) -> None:
        with pytest.raises(ValueError):
            gate.mutate_in_cte(
                _calibration_population_ctes(), "deduped", "no such text", "x"
            )

    def test_all_five_frozen_controls_are_named(self) -> None:
        assert set(gate.MUTANTS) == {
            "wide_shape",
            "global_rn1",
            "row_swap",
            "flag_flip",
            "narrow_population",
        }

    def test_row_swap_displaces_only_the_outcome_id(self) -> None:
        expr = gate.row_swap_expr(
            columns=["outcome_id", "source", "adj_opening_probability"],
            victim_outcome_id=42,
            offset=1000,
        )
        assert "outcome_id + 1000 AS outcome_id" in expr
        assert "WHERE outcome_id <> 42" in expr
        assert "source, adj_opening_probability" in expr


class TestCouldNotCheckIsNeverAgreement:
    """The kill criteria make rendering an unmeasured gate as green a BLOCK."""

    def test_an_empty_sample_is_not_a_pass(self) -> None:
        row = {k: 0 for k in gate.G1_COLUMNS}
        verdict, reasons = gate.g1_verdict(row)
        assert verdict == "NOT_MEASURED"
        assert reasons

    def test_a_real_agreement_is_a_pass(self) -> None:
        row = {k: 0 for k in gate.G1_COLUMNS}
        row.update(n_old=1200, n_new=1200, markets_old=90, markets_new=90)
        assert gate.g1_verdict(row)[0] == "PASS"

    def test_one_extra_row_fails(self) -> None:
        row = {k: 0 for k in gate.G1_COLUMNS}
        row.update(n_old=1200, n_new=1201, new_only_rows=1)
        assert gate.g1_verdict(row)[0] == "FAIL"

    def test_bucket_agreement_alone_does_not_rescue_a_row_difference(self) -> None:
        # The swapped-row shape: identical counts, identical buckets, different
        # identities. Aggregate-equal must not read as PASS.
        row = {k: 0 for k in gate.G1_COLUMNS}
        row.update(n_old=1200, n_new=1200, old_only_rows=1, new_only_rows=1)
        verdict, reasons = gate.g1_verdict(row)
        assert verdict == "FAIL"
        assert any("EXCEPT ALL" in r for r in reasons)

    def test_g3_with_one_unmeasured_sample_is_not_a_median(self) -> None:
        good = {
            "label": "MOD 64=0",
            "old": {"measured": True, "sort_plan_width": 652, "sort_input_rows": 10,
                    "windowagg_actual_total_ms": 100.0},
            "new": {"measured": True, "sort_plan_width": 90, "sort_input_rows": 10,
                    "windowagg_actual_total_ms": 40.0},
            "final_rows_old": 5,
            "final_rows_new": 5,
        }
        bad = {"label": "MOD 257=0", "old": {"measured": False}, "new": {"measured": False}}
        assert gate.g3_verdict([good])[0] == "PASS"
        assert gate.g3_verdict([good, bad])[0] == "NOT_MEASURED"

    def test_g3_fails_on_a_changed_window_population(self) -> None:
        sample = {
            "label": "MOD 64=0",
            "old": {"measured": True, "sort_plan_width": 652, "sort_input_rows": 1000,
                    "windowagg_actual_total_ms": 100.0},
            "new": {"measured": True, "sort_plan_width": 90, "sort_input_rows": 400,
                    "windowagg_actual_total_ms": 10.0},
            "final_rows_old": 5,
            "final_rows_new": 5,
        }
        verdict, reasons, _ = gate.g3_verdict([sample])
        assert verdict == "FAIL"
        assert any("input rows" in r for r in reasons)

    def test_g3_fails_a_wide_row_even_when_it_is_faster(self) -> None:
        sample = {
            "label": "MOD 64=0",
            "old": {"measured": True, "sort_plan_width": 652, "sort_input_rows": 1000,
                    "windowagg_actual_total_ms": 100.0},
            "new": {"measured": True, "sort_plan_width": 652, "sort_input_rows": 1000,
                    "windowagg_actual_total_ms": 1.0},
            "final_rows_old": 5,
            "final_rows_new": 5,
        }
        verdict, reasons, _ = gate.g3_verdict([sample])
        assert verdict == "FAIL"
        assert any("width" in r for r in reasons)

    def test_g3_fails_a_new_spill(self) -> None:
        sample = {
            "label": "MOD 64=0",
            "old": {"measured": True, "sort_plan_width": 652, "sort_input_rows": 1000,
                    "windowagg_actual_total_ms": 100.0, "sort_space_type": "Memory",
                    "temp_written_blocks": 0},
            "new": {"measured": True, "sort_plan_width": 90, "sort_input_rows": 1000,
                    "windowagg_actual_total_ms": 40.0, "sort_space_type": "Disk",
                    "temp_written_blocks": 900},
            "final_rows_old": 5,
            "final_rows_new": 5,
        }
        verdict, reasons, _ = gate.g3_verdict([sample])
        assert verdict == "FAIL"
        assert any("spill" in r or "temp blocks" in r for r in reasons)


class TestTheNamedNodeIsFoundByName:
    """G3 measures ONE node. Picking the wrong Sort is a number about nothing."""

    #: A minimal plan in EXPLAIN's own shape: two stacked WindowAggs over one
    #: Sort, inside a materialized CTE, exactly as this population plans.
    PLAN = {
        "Node Type": "Hash Join",
        "Actual Rows": 7,
        "Plans": [
            {
                "Node Type": "Sort",
                "Plan Width": 999,
                "Actual Rows": 1,
                "Actual Loops": 1,
            },
            {
                "Node Type": "WindowAgg",
                "Subplan Name": "CTE ranked_outcomes_core",
                "Total Cost": 4330606.0,
                "Actual Rows": 1500,
                "Actual Total Time": 900.0,
                "Plans": [
                    {
                        "Node Type": "WindowAgg",
                        "Actual Rows": 1500,
                        "Actual Total Time": 850.0,
                        "Plans": [
                            {
                                "Node Type": "Sort",
                                "Plan Width": 90,
                                "Actual Rows": 1500,
                                "Actual Loops": 1,
                                "Sort Method": "external merge",
                                "Sort Space Used": 2048,
                                "Sort Space Type": "Disk",
                                "Actual Total Time": 600.0,
                                "Temp Written Blocks": 256,
                            }
                        ],
                    }
                ],
            },
        ],
    }

    def test_it_reads_the_sort_under_the_named_cte_not_the_sibling(self) -> None:
        metrics = gate.named_node_metrics(self.PLAN, "ranked_outcomes_core")
        assert metrics["measured"]
        assert metrics["sort_plan_width"] == 90, "it grabbed the unrelated Sort"
        assert metrics["sort_input_rows"] == 1500
        assert metrics["sort_space_type"] == "Disk"
        assert metrics["temp_written_blocks"] == 256
        assert metrics["windowagg_nodes"] == 2
        assert metrics["windowagg_subtree_total_cost"] == 4330606.0

    def test_a_missing_cte_is_named_not_guessed(self) -> None:
        metrics = gate.named_node_metrics(self.PLAN, "ranked_outcomes")
        assert metrics["measured"] is False
        assert "ranked_outcomes" in metrics["reason"]

    def test_node_time_does_not_double_count_the_sort(self) -> None:
        metrics = gate.named_node_metrics(self.PLAN, "ranked_outcomes_core")
        # 850 is the inner WindowAgg's INCLUSIVE time; 850 + 600 would be a
        # number that does not exist.
        assert gate.node_time_ms(metrics) == 850.0

    #: CAL-P099. The plan the gate's FIRST CI execution actually produced (run
    #: 33003742148), reduced to its spine. The planner chose an Incremental
    #: Sort, the matcher required the literal string "Sort", and G3 came back
    #: NOT_MEASURED on both chains — reported as "the named node moved", which
    #: reads as a fault in the rewrite and was a fault in the ruler.
    CI_PLAN = {
        "Node Type": "Nested Loop",
        "Plans": [
            {
                "Node Type": "WindowAgg",
                "Subplan Name": "CTE ranked_outcomes",
                "Plan Width": 1032,
                "Total Cost": 5145793.0,
                "Plans": [
                    {
                        "Node Type": "WindowAgg",
                        "Plan Width": 1194,
                        "Plans": [
                            {
                                "Node Type": "Incremental Sort",
                                "Plan Width": 1186,
                                "Plans": [],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    def test_an_incremental_sort_is_the_windows_sort(self) -> None:
        """Both node types sort a window's input, so both are the named node.

        The width clause is the part of G3 that CI can grade, and Plan Width is
        present on either shape. Refusing one of them made the gate
        unmeasurable on the only Postgres this repo can reach.
        """
        metrics = gate.named_node_metrics(self.CI_PLAN, "ranked_outcomes")
        assert metrics["sort_plan_width"] == 1186
        assert metrics["sort_node_type"] == "Incremental Sort"

    def test_an_incremental_sorts_absent_spill_fields_are_null_not_zero(self) -> None:
        """It reports per-group figures, not one Sort Method / Space Used.

        Returning 0 would assert "this sort did not spill" on a node that does
        not answer that question in this shape (gotcha #53).
        """
        metrics = gate.named_node_metrics(self.CI_PLAN, "ranked_outcomes")
        assert metrics["sort_method"] is None
        assert metrics["sort_space_used_kb"] is None

    def test_a_node_that_is_not_a_sort_at_all_is_still_refused(self) -> None:
        """Widening the accepted set must not widen it to everything.

        The refusal also names what it DID see, because the first execution's
        message ('the named node moved') sent the reader looking at the rewrite
        instead of at the plan.
        """
        plan = {
            "Node Type": "WindowAgg",
            "Subplan Name": "CTE ranked_outcomes",
            "Plans": [
                {"Node Type": "WindowAgg", "Plans": [{"Node Type": "Seq Scan"}]}
            ],
        }
        metrics = gate.named_node_metrics(plan, "ranked_outcomes")
        assert metrics["measured"] is False
        assert "Seq Scan" in metrics["reason"]


class TestTheSeedAndTheOracleCannotDrift:
    """The per-fixture oracle must cover the seed exactly — checked without a DB."""

    @pytest.fixture(scope="class")
    def pg_module(self):
        import importlib.util

        path = (
            pathlib.Path(__file__).parent
            / "integration"
            / "test_calibration_fold_narrowing_row_identity_pg.py"
        )
        spec = importlib.util.spec_from_file_location("_p096_pg_gate", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_every_seeded_market_has_an_expectation(self, pg_module) -> None:
        assert set(pg_module.EXPECTED) == set(pg_module.ALL_MARKETS)

    def test_every_expected_outcome_exists_in_the_seed(self, pg_module) -> None:
        seeded = {
            mid: {mid + o[0] for o in spec["outcomes"]}
            for mid, spec in pg_module.SEED
        }
        for mid, spec in pg_module.EXPECTED.items():
            unknown = set(spec["published"]) - seeded[mid]
            assert not unknown, f"market {mid} expects unseeded outcomes {unknown}"

    def test_the_incomplete_field_specimen_exists_and_is_incomplete(self, pg_module) -> None:
        spec = dict(pg_module.SEED)[pg_module._m(140)]
        assert spec["market_type"] == "field" and spec["shape"]
        assert sum(1 for o in spec["outcomes"] if o[3]) == 1, "a field needs one winner"
        assert len(spec["outcomes"]) >= 3
        wide = [o for o in spec["outcomes"] if len(o) > 4 and o[4].get("yes_ask")]
        assert len(wide) == 1, "exactly one member may carry the wide book"
        override = wide[0][4]
        assert override["yes_ask"] - override["yes_bid"] >= 0.50
        assert override["snapshot"] == "bid_only", (
            "the excluded member must still be LIQUID, or it leaves the field "
            "roster and the field is complete-over-three instead of incomplete"
        )
        assert pg_module.EXPECTED[pg_module._m(140)]["published"] == []

    def test_the_two_evidence_pairs_differ_in_one_dimension(self, pg_module) -> None:
        seed = dict(pg_module.SEED)
        poly_no, poly_yes = seed[pg_module._m(110)], seed[pg_module._m(150)]
        assert poly_no["source"] == poly_yes["source"] == "polymarket"
        assert poly_no["outcomes"][0][2] == poly_yes["outcomes"][0][2] == 0.50
        assert poly_no.get("traded") is False and poly_yes.get("traded", True) is True

        k_no, k_yes = seed[pg_module._m(120)], seed[pg_module._m(160)]
        assert k_no["source"] == k_yes["source"] == "kalshi"
        assert k_no["outcomes"][0][2] == k_yes["outcomes"][0][2] == 0.30
        assert k_no.get("traded") is False
        assert k_yes["outcomes"][0][4]["snapshot"] == "bid_only"


class TestTheComposedStatementIsSendable:
    """The harness's output has to be ONE statement the read path will accept."""

    @pytest.fixture(scope="class")
    def real(self) -> str:
        return gate.g1_statement(
            old_chain=FIXTURE.read_text(),
            new_chain=_calibration_population_ctes(),
        )

    def test_parens_balance(self, real: str) -> None:
        assert real.count("(") == real.count(")")

    def test_it_is_a_single_statement(self, real: str) -> None:
        from app.utils.sql_comment_strip import count_statement_separators

        # A stray semicolon reads as multi-statement and is refused outright —
        # INT-121's class, and the reason the chain is comment-stripped first.
        assert count_statement_separators(real) == 0

    def test_comments_are_stripped(self, real: str) -> None:
        # A prose colon inside a `--` comment parses as a required bind
        # parameter under SQLAlchemy `text()` (gotcha #45 / INT-121 hotfix 3).
        assert "--" not in real

    def test_the_mutated_statements_are_equally_sendable(self) -> None:
        from app.utils.sql_comment_strip import count_statement_separators

        old, new = FIXTURE.read_text(), _calibration_population_ctes()
        for name in ("global_rn1", "flag_flip", "narrow_population"):
            mutated = getattr(gate, f"mutant_{name}")(new)
            statement = gate.g1_statement(old_chain=old, new_chain=mutated)
            assert statement.count("(") == statement.count(")"), name
            assert count_statement_separators(statement) == 0, name


class TestTheRunnerUsesTheFrozenPlan:
    """The script is the thing an operator actually types. Pin its defaults."""

    @pytest.fixture(scope="class")
    def source(self) -> str:
        return (
            pathlib.Path(__file__).parents[1]
            / "scripts"
            / "verify_fold_narrowing_row_identity.py"
        ).read_text()

    def test_it_defaults_to_the_frozen_residue_plan(self, source: str) -> None:
        assert "plan = list(RESIDUE_PLAN)" in source

    def test_it_opens_one_repeatable_read_read_only_transaction(self, source: str) -> None:
        assert 'isolation="repeatable_read", readonly=True' in source

    def test_it_does_not_go_through_the_admin_rail(self, source: str) -> None:
        # The finding: two HTTP POSTs are two snapshots. If this string ever
        # comes back, so does the defect.
        assert "db-query" not in source.split('"""', 2)[2]
        assert "urllib" not in source

    def test_it_never_exits_zero_on_an_unmeasured_gate(self, source: str) -> None:
        assert 'report["verdict"] = "NOT_MEASURED"' in source
        assert "code = 3" in source

    def test_every_statement_runs_inside_a_savepoint(self, source: str) -> None:
        # One timed-out residue must cost that residue and nothing else. In an
        # ABORTED transaction every later statement fails with
        # InFailedSQLTransaction, so without a savepoint per statement a single
        # slow sample would report the remaining seven as errors that never ran
        # — seven could-not-checks manufactured by the harness itself.
        # Three sites: the snapshot export, the G1 residue, the G3 plan.
        assert source.count("async with conn.transaction():") == 3
