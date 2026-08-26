"""The 0.5000 pair exclusion: one predicate, pair-scoped, cell-scoped, reported.

CERT-403B BLOCKED the staged exclusion on three P1s. This file is the executable
half of the answer to all three.

  P1#1  "the committed 12.14-pp evidence executes a broader single-leg filter
         than the proposed pair-scoped predicate"
  P1#2  "the proposal is unsafe unless explicitly cell-scoped; the first
         out-of-cell control moves in the wrong direction"
  P1#3  "all six author-written executable criteria remain absent ... the staged
         file is a build brief, not a certifiable change"

P1#1 IS A TESTABILITY PROBLEM, NOT A CARELESSNESS PROBLEM
---------------------------------------------------------
The blocked fold's filter was ``ROUND(opening_probability,4) <> 0.5000`` while
the rule it evidenced was pair-scoped. Nothing could have caught that, because
the fold and the builder shared no code — the fold restated a predicate the
builder did not yet have. Telling the next author to be careful would leave the
same hole.

So the predicate now has exactly one definition
(``HALF_SPIKE_PAIR_SHAPE_COLUMNS`` + ``half_spike_pair_market_predicate`` in
``app.tasks.precompute_calibration``), the shipping builder renders it, the fold
that measures it renders it, and ``TestOneDefinition`` below asserts the two
renderings are the same text modulo alias. A future fold that hand-rolls the
filter again fails ``test_the_fold_does_not_restate_the_predicate``.

THE MEASUREMENT, RE-DERIVED (CAL-P097, artifacts/cal-p097/half_spike_pair_bbq.json)
-----------------------------------------------------------------------------------
16 shards, 0 irreducible, one pass, three readings over the same tagged rows:

    baseline      ECE 15.86  n 6,778   (the cell today)
    proposed      ECE 12.74  n 4,982   (THIS rule — removes 1,796 legs)
    broad_filter  ECE 12.13  n 4,686   (what the blocked artifact measured)

The blocked artifact's 12.14 reproduces at 12.13 from this fold, which is what
proves the two rules differ by measurement rather than by assertion. The honest
delta for the proposed rule is **-3.12 pp**, not the -3.72 pp on record, because
the broad filter also swallowed **296 lone 0.5000 legs** that criterion 2 says
must survive. 1,796 + 296 = 2,092, the cert's own reconciled removal count.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

# ``backend/scripts`` on the path: the fold modules import their siblings by
# bare name (``from dbq_probe import run``), which is how every fold in that
# directory is written and how they are invoked. Importing one from a test
# therefore needs the same path the CLI gives them.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from app.tasks.precompute_calibration import (
    HALF_SPIKE_EXACT_VALUE,
    HALF_SPIKE_PAIR_CELL_CATEGORY,
    HALF_SPIKE_PAIR_CELL_MARKET_TYPE,
    HALF_SPIKE_PAIR_CELL_SOURCE,
    HALF_SPIKE_PAIR_RULE_TEXT,
    _calibration_population_ctes,
    half_spike_pair_market_predicate,
    half_spike_pair_shape_columns,
)


def _population_sql() -> str:
    return _calibration_population_ctes()


def _normalise(sql: str) -> str:
    """Collapse whitespace so indentation differences are not differences."""
    return re.sub(r"\s+", " ", sql).strip()


class TestOneDefinition:
    """P1#1's structural fix: the fold and the builder cannot disagree."""

    def test_the_fold_and_the_builder_render_the_same_shape_columns(self):
        from scripts.fold_half_spike_pair import shard_sql

        builder = _normalise(half_spike_pair_shape_columns("fo"))
        fold = _normalise(half_spike_pair_shape_columns("p"))
        # Same text once the alias is accounted for. Compared this way rather
        # than by eyeballing both call sites, because "they look the same" is
        # exactly the check that passed for the blocked artifact.
        assert builder.replace("fo.", "@.") == fold.replace("p.", "@.")
        assert _normalise(half_spike_pair_shape_columns("p")) in _normalise(
            shard_sql(HALF_SPIKE_PAIR_CELL_CATEGORY, HALF_SPIKE_PAIR_CELL_MARKET_TYPE)
        )

    def test_the_fold_and_the_builder_render_the_same_market_predicate(self):
        from scripts.fold_half_spike_pair import shard_sql

        fold_sql = _normalise(
            shard_sql(HALF_SPIKE_PAIR_CELL_CATEGORY, HALF_SPIKE_PAIR_CELL_MARKET_TYPE)
        )
        assert _normalise(half_spike_pair_market_predicate("shp")) in fold_sql
        assert _normalise(half_spike_pair_market_predicate("mrs")) in _normalise(
            _population_sql()
        )

    def test_the_fold_does_not_restate_the_predicate(self):
        """A hand-rolled filter is the whole of CERT-403B's first P1.

        Specifically bans the blocked artifact's own filter text. A fold that
        reintroduces it is measuring a different rule than the one it evidences,
        which is the defect, spelled exactly.
        """
        import ast
        import inspect

        from scripts import fold_half_spike_pair

        # DOCSTRINGS AND COMMENTS EXCLUDED, via the AST rather than by line
        # prefix. The fold's own module docstring QUOTES the blocked filter —
        # that quotation is the point of the docstring, and a guard that could
        # not tell a quotation from a use would force the next author to delete
        # the explanation of the defect in order to keep the guard for it green.
        tree = ast.parse(inspect.getsource(fold_half_spike_pair))
        for node in ast.walk(tree):
            if isinstance(
                node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and ast.get_docstring(node) is not None:
                node.body = node.body[1:]
        body = ast.unparse(tree)
        assert "<> 0.5000" not in body, (
            "the fold hand-rolls a bare per-leg 0.5000 filter — that is the "
            "broad predicate CERT-403B blocked, not the pair-scoped rule"
        )


class TestThePredicateIsPairScoped:
    """Criterion 2: a LONE 0.5000 leg is an ordinary price and must survive."""

    @staticmethod
    def _decide(n_outcomes: int, over: int, under: int, half_legs: int) -> bool:
        """Evaluate the shipped predicate in Python over one market's shape.

        The SQL is a boolean over four integers, so it can be evaluated exactly
        rather than approximated — the clause list is parsed out of the shipped
        string, so this helper cannot drift from it either.
        """
        expr = half_spike_pair_market_predicate("m")
        env = {
            "m": type(
                "S", (), {
                    "hs_n_outcomes": n_outcomes,
                    "hs_named_over": over,
                    "hs_named_under": under,
                    "hs_half_legs": half_legs,
                },
            )()
        }
        python_expr = expr.replace("\n", " ").replace("AND", "and").replace("=", "==")
        python_expr = python_expr.replace("<==", "<=").replace(">==", ">=")
        return bool(eval(python_expr, {"__builtins__": {}}, env))  # noqa: S307

    def test_a_both_legs_half_pair_is_excluded(self):
        assert self._decide(2, 1, 1, 2) is True

    def test_a_lone_half_leg_is_kept(self):
        """The 296-leg class the broad filter swallowed. Criterion 2."""
        assert self._decide(2, 1, 1, 1) is False

    def test_a_market_with_no_half_legs_is_kept(self):
        assert self._decide(2, 1, 1, 0) is False

    def test_a_three_leg_market_is_kept_even_if_two_legs_are_half(self):
        """The pair-size clause. A field is not a pair."""
        assert self._decide(3, 1, 1, 2) is False

    def test_an_unnamed_two_leg_market_is_kept(self):
        """Yes/No at 0.50/0.50 is a coin-flip claim, not the O/U writer defect.

        The named-leg clause is what ties the exclusion to the mechanism CAL-P094
        measured — the Over leg taking 0.5 from an untraded market and the Under
        leg written as its complement. Without it the predicate would be a bare
        value filter wearing a pair's clothes.
        """
        assert self._decide(2, 0, 0, 2) is False

    def test_two_overs_and_no_under_is_kept(self):
        assert self._decide(2, 2, 0, 2) is False


class TestTheBuilderAppliesIt:
    """P1#3: the predicate is in the SHARED payload builder, and it gates."""

    def test_the_flag_is_defined_once_in_the_population_ctes(self):
        sql = _population_sql()
        assert sql.count("AS is_half_spike_pair") == 1

    def test_the_flag_gates_every_published_set(self):
        """Three sites: both field_completeness counters and ``deduped``.

        A flag defined and not gated is a census column, not an exclusion — and
        it would report a count while changing nothing, which is worse than
        either.
        """
        sql = _population_sql()
        assert sql.count("AND NOT ro.is_half_spike_pair") == 3

    def test_the_exclusion_is_cell_scoped(self):
        """P1#2. soccer/quantity carries the same mass and gets WORSE (+0.41)."""
        sql = _population_sql()
        assert f"mi.source = '{HALF_SPIKE_PAIR_CELL_SOURCE}'" in sql
        assert f"mi.category = '{HALF_SPIKE_PAIR_CELL_CATEGORY}'" in sql
        assert f"mi.market_type = '{HALF_SPIKE_PAIR_CELL_MARKET_TYPE}'" in sql

    def test_the_predicate_is_the_exact_value_not_a_band(self):
        """Staged spec §5: 0.5005 has the same signature and is out of scope.

        Widening to a tolerance band turns a self-evidencing exact match into a
        judgement call, and this apply is not permitted to carry one.
        """
        assert HALF_SPIKE_EXACT_VALUE == "0.5000"
        assert f"= {HALF_SPIKE_EXACT_VALUE}" in _population_sql()

    def test_the_exclusion_lands_in_a_named_rung_not_the_catch_all(self):
        """``representative_not_selected`` is where an ungated filter hides.

        The rung table's own comment warns that a newly added ``deduped`` filter
        silently lands there. It is folded into ``phantom_liquidity`` — the same
        mechanism as the poly placeholder it sits beside.
        """
        from app.tasks.precompute_calibration import _COVERAGE_RUNG_PREDICATES

        rungs = dict(_COVERAGE_RUNG_PREDICATES)
        assert "is_half_spike_pair" in rungs["phantom_liquidity"]
        assert "is_half_spike_pair" not in rungs["representative_not_selected"]


class TestItIsReported:
    """Criterion 6: the excluded population is reported, not silently dropped."""

    def test_the_rule_text_names_the_lone_leg_carve_out_and_the_cell(self):
        text = HALF_SPIKE_PAIR_RULE_TEXT
        assert "LONE" in text and "KEPT" in text
        assert HALF_SPIKE_PAIR_CELL_CATEGORY in text
        assert "soccer" in text, "the +0.41 pp control belongs in the rule text"

    def test_the_payload_carries_a_count_and_a_reason(self):
        import inspect

        from app.tasks import precompute_calibration as pc

        src = inspect.getsource(pc)
        assert '"half_spike_pair_filter"' in src
        assert '"excluded": half_spike_pair_excluded' in src
        assert "COUNT(*) FILTER (WHERE is_half_spike_pair)" in src


class TestTheFoldMeasuresThePublishedPopulation:
    """CERT-406B's P1. The measurement must execute the population that ships.

        "It does not execute ``is_liquid``, ``is_poly_placeholder``,
         malformed/result-authority gates, field completeness, mode filtering,
         or the ``ELSE ro.rn = 1`` representative rule that define ``deduped``
         ... An executable SQL-token comparison found all six representative
         shipping gates present in ``_main_futures_sql()`` and absent from
         ``shard_sql()``."

    That comparison is the test below, inverted: the same six tokens, now
    required PRESENT in the published reading. Codex's falsifier becomes the
    regression guard, which is the cheapest possible way to keep a BLOCK closed.
    """

    #: The six the cert named, by the names it named them by.
    SHIPPING_GATES = (
        "is_liquid",
        "is_poly_placeholder",
        "is_malformed_binary",
        "is_field_incomplete",
        "mode_prices",
        "ELSE ro.rn = 1",
    )

    @staticmethod
    def _published(enabled: bool = True) -> str:
        from scripts.fold_half_spike_pair import published_reading_sql

        return published_reading_sql(
            HALF_SPIKE_PAIR_CELL_CATEGORY,
            HALF_SPIKE_PAIR_CELL_MARKET_TYPE,
            enabled=enabled,
        )

    @pytest.mark.parametrize("gate", SHIPPING_GATES)
    def test_the_published_reading_executes_every_shipping_gate(self, gate):
        assert gate in self._published(), (
            f"the published reading omits {gate!r} — it is measuring a raw "
            "eligible fold again, not the rows the payload publishes"
        )

    def test_it_aggregates_deduped_and_not_a_hand_rolled_select(self):
        """The structural version: the rows come FROM ``deduped``.

        A fold could contain all six tokens by pasting them and still select
        its own population. What makes that impossible here is that the chain
        is rendered by the shipping builder and the aggregate reads its last
        CTE.
        """
        sql = self._published()
        assert "FROM deduped d" in sql
        assert "_calibration_population_ctes" not in sql, "rendered, not quoted"

    def test_the_two_readings_differ_in_exactly_the_rule(self):
        """The before/after must be one edit, or it is not a before/after.

        If switching the rule off changed anything else about the population —
        a gate, a join, a bucket expression — the delta would not be
        attributable to the rule, and that is the whole claim being made.
        """
        import difflib

        on = self._published(True).splitlines()
        off = self._published(False).splitlines()
        changed = [
            line
            for line in difflib.unified_diff(on, off, lineterm="")
            if line[:1] in "+-" and line[:3] not in ("+++", "---")
        ]
        assert [(line[0], line[1:].strip()) for line in changed] == [
            ("-", "(hsp.market_id IS NOT NULL"),
            ("-", "AND ROUND(fo.opening_probability, 4)"),
            ("-", f"= {HALF_SPIKE_EXACT_VALUE})"),
            ("+", "false"),
        ], changed

    def test_the_candidate_shard_is_labelled_as_candidate_side(self):
        """The old reading is kept and demoted, not deleted.

        It reconciles CERT-403B's 266 lone legs, which is a real finding worth
        keeping. What it may not do is go on looking like a statement about the
        curve — the BLOCK was about the label as much as the SQL.
        """
        import inspect

        from scripts import fold_half_spike_pair

        src = inspect.getsource(fold_half_spike_pair)
        assert "scope_of_the_candidate_reading" in src
        assert "CANDIDATE-side" in src

    def test_a_timeout_is_a_named_refusal_and_never_a_zero(self):
        """gotcha #53. This fold does not fit the db-query rail, by design.

        The failure mode being closed: the statement times out, the runner
        records no rows, and the artifact reports a clean fold over an empty
        population — a zero that reads as "the exclusion removes nothing".
        """
        import inspect

        from scripts import fold_half_spike_pair

        src = inspect.getsource(fold_half_spike_pair.run_published_reading)
        assert '"measured": False' in src
        assert "NOT a zero" in src


class TestCriterionFourIsMeasured:
    """"published totals move by the excluded count and no more" — now measurable.

    CERT-406B: the payload's ``excluded`` is counted candidate-side from
    ``normalized`` while published totals come from ``deduped``, "therefore
    criterion 4 ... is neither measured nor structurally guaranteed."
    """

    def test_the_payload_reports_both_sides_separately(self):
        import inspect

        from app.tasks import precompute_calibration as pc

        src = inspect.getsource(pc)
        assert '"excluded": half_spike_pair_excluded' in src, "candidate side"
        assert (
            '"published_rows_removed": half_spike_pair_published_removed' in src
        ), "published side"

    def test_the_published_count_is_unknown_rather_than_zero_when_absent(self):
        """A census that predates the counter did not measure zero removals.

        Reporting 0 there would be the strongest possible claim about criterion
        4 made by the one code path that never looked.
        """
        import inspect

        from app.tasks import precompute_calibration as pc

        src = inspect.getsource(pc.compute_calibration_payload)
        assert "half_spike_pair_published_removed = int(_hspr) if _hspr is not None else None" in src

    def test_the_counter_shares_dedupeds_predicate_textually(self):
        """One text, two arms — the only closure for a two-copies defect.

        CERT-403B: the evidence executed a different PREDICATE. CERT-406B: the
        evidence executed a different POPULATION. Both are a hand-written second
        copy that agreed on the day it was written. A shared renderer makes a
        drift a syntax error instead of a number nobody re-checks.
        """
        from app.tasks.precompute_calibration import published_row_predicate

        published = published_row_predicate(half_spike_arm="NOT ro.is_half_spike_pair")
        removed = published_row_predicate(half_spike_arm="ro.is_half_spike_pair")
        assert published.replace(
            "AND NOT ro.is_half_spike_pair", "AND ro.is_half_spike_pair"
        ) == removed
        sql = _population_sql()
        assert published in sql and removed in sql

    def test_hoisting_the_predicate_did_not_drop_it_from_the_fingerprint(self):
        """The regression this rework very nearly shipped.

        ``_main_input_fingerprint`` hashes ``inspect.getsource`` of four named
        functions. Moving ``deduped``'s WHERE clause into a helper moved it OUT
        of that source — measured, before the fix: mutating the predicate left
        the digest unchanged. Hashing a function's source covers that function,
        never its callees, and a refactor is exactly when that gets forgotten.
        """
        import inspect

        from app.tasks import precompute_calibration as pc

        assert (
            "inspect.getsource(published_row_predicate)"
            in inspect.getsource(pc._main_input_fingerprint)
        )

    def test_the_shared_join_moves_the_fingerprint(self):
        """``PUBLISHED_ROW_JOIN`` is a module constant, in nobody's source."""
        from app.tasks import precompute_calibration as pc

        base = pc._main_input_fingerprint()
        original = pc.PUBLISHED_ROW_JOIN
        try:
            pc.PUBLISHED_ROW_JOIN = original + "\n                  AND true"
            assert pc._main_input_fingerprint() != base, (
                "the mode-price join can be edited without invalidating a "
                "carried read — the published population would change under a "
                "resumable cursor"
            )
        finally:
            pc.PUBLISHED_ROW_JOIN = original
        assert pc._main_input_fingerprint() == base


class TestNothingIsRegraded:
    """Criterion 3: read-side only. No UPDATE, no is_winner, no re-grade."""

    def test_the_predicate_touches_no_resolution_column(self):
        for sql in (
            half_spike_pair_shape_columns("fo"),
            half_spike_pair_market_predicate("mrs"),
        ):
            for column in ("is_winner", "resolution_source", "calibration_probability"):
                assert column not in sql

    @pytest.mark.parametrize("verb", ["UPDATE ", "INSERT ", "DELETE ", "TRUNCATE "])
    def test_the_population_sql_is_read_only(self, verb):
        # COMMENTS STRIPPED. The builder documents its exclusions in prose —
        # "it would DELETE 81% of hockey" is an explanation of why a rule was
        # NOT shipped, and a guard that cannot tell prose from a statement
        # would force the next author to delete the explanation to stay green.
        sql = "\n".join(
            line.split("--", 1)[0] for line in _population_sql().splitlines()
        )
        assert verb not in sql.upper()
