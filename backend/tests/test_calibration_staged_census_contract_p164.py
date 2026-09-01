"""CAL-P164 (#1978): the statement's output columns ARE the merge's contract.

CERT-626 blocked CAL-P162 for emitting three columns — ``nxb_cell_esports``,
``nxb_cell_0``, ``nxb_cell_1`` — that no declaration mentioned. The staged
merge is fail-closed by design, so the effect was not a wrong number: it was
``UndeclaredColumnError`` on the FIRST unit that returned a row, and therefore
no banked unit, no finalization, and no published curve for as long as the
build ran. Every RULE E test passed, because every one of them tested the
rendered SQL or the pure predicate and none crossed the boundary.

**Why the existing pin did not catch it.** CAL-P034's characterization test
pins the two declarations — the frozen build's runtime ``census_columns`` and
the mirrored ``DECLARED_CENSUS_COLUMNS`` — against EACH OTHER. Both were
correct about each other and both were silent about the statement. Agreement
between two derivations is not coverage of the thing they derive from.

So this file pins the third edge, the one that was missing: the set of columns
the frozen statement actually EMITS must be exactly the set the merge is told
about. It reads the emitted set out of the rendered SQL with a real Postgres
parser rather than a regex, because ``AS <name>`` occurs all over the CTE
ladder and only the outer SELECT's projection is the contract.

The tests below cover both boundaries the row crosses — bank time
(``split_unit_rows`` / ``fold_unit_rows``, defaulting to
``DECLARED_CENSUS_COLUMNS``) and merge time (``merge_futures_rows``, passed the
build's runtime tuple) — and assert the per-cell counts SUM across units, since
a chunk-local ``COUNT(*) FILTER`` that is broadcast instead of summed reports
one unit's slice as the whole population's.
"""

from __future__ import annotations

import ast
import pathlib
from types import SimpleNamespace

import pytest
import sqlglot

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    NONEXCLUSIVE_BUNDLE_CELL_COLUMNS,
    _main_futures_sql,
    nonexclusive_bundle_cell_labels,
)
from app.utils.calibration_staged_futures import (
    ADDITIVE_COLUMNS,
    AVG_PROB_COLUMN,
    DECLARED_CENSUS_COLUMNS,
    DEFAULT_CENSUS_COLUMNS,
    GROUP_KEY_COLUMNS,
    INTEGER_ADDITIVE_COLUMNS,
    UndeclaredColumnError,
    merge_futures_rows,
    split_unit_rows,
)

_FROZEN = (
    pathlib.Path(__file__).resolve().parents[1] / "app" / "tasks" / "precompute_calibration.py"
)

#: Columns that must appear in any correct parse of the statement's projection.
#: The guard RAISES rather than passes when these are absent: a parser that
#: silently returned a short list would make every assertion below vacuous, and
#: "the emitted set is a subset of the declared set" is trivially true of the
#: empty set. A scan must fail on what it cannot read, not report clean.
_PARSE_SENTINELS = frozenset(
    {"bucket_idx", "n", "winners", "published_outcomes", "esports_bundle_excluded"}
)


def _emitted_columns(*, frozen: bool = True) -> frozenset[str]:
    """The outer projection of the rendered statement, via a Postgres parser."""
    sql = _main_futures_sql(frozen=frozen)
    names = frozenset(sqlglot.parse_one(sql, read="postgres").named_selects)
    missing = _PARSE_SENTINELS - names
    if missing:
        raise AssertionError(
            "the statement's projection could not be read — this guard is "
            f"vacuous until that is fixed; missing sentinels: {sorted(missing)}"
        )
    return names


def _runtime_census_columns() -> tuple[str, ...]:
    """The tuple ``_run_staged_futures`` actually hands to the merge.

    EVALUATED out of the frozen source, not restated here. It is a local, so
    it cannot be imported — and the first draft of this file reconstructed it
    instead, which made every merge-time assertion below vacuous: a mutation
    that reverted the build's real declaration left the tests green because
    they were reading the copy. Reading the expression is the difference
    between guarding the build and guarding a paraphrase of it.

    ``DEFAULT_CENSUS_COLUMNS`` is supplied explicitly because the build imports
    it inside the function, so it is not a module global. It is the same object
    the build binds. The ``COVERAGE_CENSUS_ENABLED`` branch is an ``AugAssign``
    and deliberately not evaluated; CAL-P034's pin asserts that switch is off.
    """
    tree = ast.parse(_FROZEN.read_text())
    assigns = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "census_columns" for t in node.targets)
    ]
    if len(assigns) != 1:
        raise AssertionError(
            "the build's census_columns assignment moved or multiplied — this "
            f"guard cannot read what the merge is told ({len(assigns)} found)"
        )
    namespace = {
        **vars(precompute_calibration),
        "DEFAULT_CENSUS_COLUMNS": DEFAULT_CENSUS_COLUMNS,
    }
    return tuple(
        eval(  # noqa: S307 - a pinned literal expression from our own source
            compile(ast.Expression(assigns[0].value), "<census_columns>", "eval"),
            namespace,
        )
    )


def _query_shaped_row(**overrides):
    """A row carrying EXACTLY the columns the statement emits.

    Derived from the rendered SQL, so a column added to the statement lands in
    this fixture automatically and the boundary tests below start exercising
    it. That is the property CAL-P162 needed and did not have.
    """
    fields: dict[str, object] = {}
    for name in sorted(_emitted_columns()):
        if name in GROUP_KEY_COLUMNS:
            fields[name] = {
                "bucket_idx": 3,
                "source": "kalshi",
                "category": "economics",
                "price_moved": False,
                "is_nonexclusive_bundle": False,
            }[name]
        elif name in INTEGER_ADDITIVE_COLUMNS:
            fields[name] = 2
        elif name in ADDITIVE_COLUMNS or name == AVG_PROB_COLUMN:
            fields[name] = 0.5
        else:
            fields[name] = 7
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestTheStatementAndTheDeclarationAgree:
    def test_every_emitted_column_is_declared_at_bank_time(self):
        """The boundary CERT-626 found, on the side that fails FIRST.

        ``advance()`` takes ``DECLARED_CENSUS_COLUMNS`` by default and the build
        does not override it, so an undeclared column aborts the very first
        unit — before finalization is ever reached.
        """
        known = (
            set(DECLARED_CENSUS_COLUMNS)
            | set(ADDITIVE_COLUMNS)
            | set(GROUP_KEY_COLUMNS)
            | {AVG_PROB_COLUMN}
        )
        assert not (_emitted_columns() - known), (
            "the statement emits columns the bank-time guard would refuse: "
            f"{sorted(_emitted_columns() - known)}"
        )

    def test_every_emitted_column_is_declared_at_merge_time(self):
        """The same contract on the finalization side."""
        known = (
            set(_runtime_census_columns())
            | set(ADDITIVE_COLUMNS)
            | set(GROUP_KEY_COLUMNS)
            | {AVG_PROB_COLUMN}
        )
        assert not (_emitted_columns() - known), (
            "the statement emits columns the merge would refuse: "
            f"{sorted(_emitted_columns() - known)}"
        )

    def test_no_column_is_declared_that_the_statement_never_emits(self):
        """The other direction, which is a bug too, just a quieter one.

        A declared column nothing emits reports ``None`` — "unknown" — forever,
        and unknown is indistinguishable from a census that broke. Pinning both
        directions is gotcha #10's lesson.
        """
        declared_census = set(_runtime_census_columns())
        assert not (declared_census - _emitted_columns()), (
            "declared census columns the statement does not emit: "
            f"{sorted(declared_census - _emitted_columns())}"
        )

    def test_the_unfrozen_statement_emits_the_same_projection(self):
        """Freezing scopes the population, never the shape of the answer."""
        assert _emitted_columns(frozen=True) == _emitted_columns(frozen=False)

    def test_the_per_cell_columns_are_actually_in_the_projection(self):
        """Anchors the class guard to the specific columns that caused it."""
        emitted = _emitted_columns()
        for column in NONEXCLUSIVE_BUNDLE_CELL_COLUMNS:
            assert column in emitted, f"{column} is declared but not emitted"
        assert len(NONEXCLUSIVE_BUNDLE_CELL_COLUMNS) == len(
            nonexclusive_bundle_cell_labels()
        )


class TestAQueryShapedRowSurvivesBothBoundaries:
    def test_a_query_shaped_row_banks(self):
        """Bank time, driving the real splitter with the real column set."""
        mass, carriers = split_unit_rows([_query_shaped_row()])
        assert mass, "the row was dropped instead of banked"
        assert carriers, "the census carrier was lost"

    def test_a_query_shaped_row_finalizes(self):
        """Merge time — the exact call CERT-626 showed aborting."""
        merged = merge_futures_rows(
            [[_query_shaped_row()]], census_columns=_runtime_census_columns()
        )
        assert len(merged) == 1

    def test_the_per_cell_counts_sum_across_units(self):
        """A chunk-local COUNT must be SUMMED, never broadcast.

        Each unit sees only its own markets, so ``nxb_cell_*`` is a slice. Take
        the max, or the first, and the published disclosure understates the
        exclusion by however many units it ignored — the disclosure Alex's
        rank-2 ruling requires to be the real count.
        """
        unit_a = _query_shaped_row(nxb_cell_esports=5, nxb_cell_0=11, nxb_cell_1=13)
        unit_b = _query_shaped_row(nxb_cell_esports=2, nxb_cell_0=3, nxb_cell_1=17)
        merged = merge_futures_rows(
            [[unit_a], [unit_b]], census_columns=_runtime_census_columns()
        )
        assert len(merged) == 1
        assert merged[0].nxb_cell_esports == 7
        assert merged[0].nxb_cell_0 == 14
        assert merged[0].nxb_cell_1 == 30

    def test_the_payload_consumer_reads_the_summed_totals(self):
        """The line in the payload builder, driven off a MERGED row.

        The consumer reads each cell off ``rows[0]`` by the label map. Merge
        broadcasts the census total onto every row precisely so that read is
        the population's number and not the first unit's.
        """
        # CAL-P168: `pp_cell_0` is rank 1's per-cell count. It is given DISTINCT
        # values here rather than left on the fixture default, so the assertion
        # below proves it is summed across units like every other census column
        # — a chunk-local count that got broadcast instead would understate the
        # temporary exclusion on the page by however many units it ignored.
        unit_a = _query_shaped_row(
            nxb_cell_esports=5, nxb_cell_0=11, nxb_cell_1=13, pp_cell_0=19
        )
        unit_b = _query_shaped_row(
            bucket_idx=4, nxb_cell_esports=2, nxb_cell_0=3, nxb_cell_1=17, pp_cell_0=23
        )
        rows = merge_futures_rows(
            [[unit_a], [unit_b]], census_columns=_runtime_census_columns()
        )
        by_cell = {
            label: int(getattr(rows[0], column))
            for label, column in nonexclusive_bundle_cell_labels()
        }
        assert by_cell == {
            "esports": 7,
            "kalshi/crypto": 14,
            "kalshi/economics": 30,
            "polymarket/baseball": 42,
        }
        # Broadcast, not per-row: the consumer's rows[0] read is only honest if
        # every merged row carries the same total.
        assert {int(getattr(row, "nxb_cell_1")) for row in rows} == {30}


class TestTheMergeIsStillFailClosed:
    def test_an_undeclared_column_still_aborts(self):
        """The fix DECLARES three columns; it must not widen the guard.

        If this ever passes, the repair became "accept anything" and the next
        column to arrive unannounced will be silently dropped from the payload
        instead of stopping the build.
        """
        row = _query_shaped_row()
        setattr(row, "some_column_nobody_declared", 1)
        with pytest.raises(UndeclaredColumnError) as excinfo:
            merge_futures_rows([[row]], census_columns=_runtime_census_columns())
        assert "some_column_nobody_declared" in str(excinfo.value)

    def test_bank_time_is_still_fail_closed_too(self):
        row = _query_shaped_row()
        setattr(row, "another_undeclared_column", 1)
        with pytest.raises(UndeclaredColumnError):
            split_unit_rows([row])

    def test_the_regression_reproduces_when_the_cells_are_undeclared(self):
        """CERT-626's exact failure, pinned as the thing being prevented.

        Dropping the per-cell columns from the declared tuple must bring back
        ``UndeclaredColumnError`` naming all three. A guard that cannot state
        the defect it prevents is not guarding it.
        """
        without_cells = tuple(DEFAULT_CENSUS_COLUMNS) + ("representative_tie_broken",)
        with pytest.raises(UndeclaredColumnError) as excinfo:
            merge_futures_rows([[_query_shaped_row()]], census_columns=without_cells)
        message = str(excinfo.value)
        for column in NONEXCLUSIVE_BUNDLE_CELL_COLUMNS:
            assert column in message


class TestTheGuardCannotGoVacuous:
    def test_the_parser_finds_a_real_projection(self):
        """The whole file rests on this parse. Assert it is substantial."""
        emitted = _emitted_columns()
        assert len(emitted) > 30, f"projection looks truncated: {sorted(emitted)}"
        assert _PARSE_SENTINELS <= emitted

    def test_a_projection_that_cannot_be_read_raises(self, monkeypatch):
        """Proves the sentinel check is load-bearing, not decoration."""
        monkeypatch.setattr(
            "tests.test_calibration_staged_census_contract_p164._main_futures_sql",
            lambda **_: "SELECT 1 AS bucket_idx",
        )
        with pytest.raises(AssertionError, match="missing sentinels"):
            _emitted_columns()

    def test_the_cell_columns_are_generated_not_hand_listed_in_the_frozen_file(self):
        """A hand-listed tuple is how the mirror drifts on the next cell."""
        tree = ast.parse(_FROZEN.read_text())
        assigns = [
            node
            for node in ast.walk(tree)
            # Annotated (``: tuple[str, ...] =``) as well as plain: filtering on
            # ast.Assign alone silently finds nothing and the assertion below
            # would then be checking an empty list.
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(
                isinstance(t, ast.Name) and t.id == "NONEXCLUSIVE_BUNDLE_CELL_COLUMNS"
                for t in (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
            )
        ]
        assert len(assigns) == 1
        assert "nonexclusive_bundle_cell_labels()" in ast.unparse(assigns[0].value), (
            "the frozen build's cell columns must be generated from the label "
            "function, so a new ruled cell adds its column automatically"
        )
