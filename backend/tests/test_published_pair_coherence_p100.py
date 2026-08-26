"""The published pair is incoherent while its opening pair is not (CAL-P100).

THE DEFECT, from evidence already on record rather than measured here.
``artifacts/subcohort2/SUBCOHORT_DIAGNOSIS.md`` item 2 check 2, on the 2,438
``baseball/quantity`` Over/Under pairs that are COHERENT at opening — the class
item 1's writer gate protects — truth-eligible:

    column                  leg     n      mean p   win rate   gap      corr
    opening_probability     over    2,438  0.3858   0.1715     +21.44   -0.583
    opening_probability     under   2,438  0.6143   0.8285     -21.43   -0.584
    published (COALESCE)    over    2,438  0.2992   0.1715     +12.77   -0.036
    published (COALESCE)    under   2,438  0.5757   0.8285     -25.28   -0.646

The two opening gaps are exactly equal and opposite, which one-winner coherent
pairs require — the fold's own check that it measured what it claims. The
opening means sum to **1.0001**. The published means sum to **0.8749**.

So a pair captured coherently is PUBLISHED as two numbers that cannot both be
forecasts of the same binary, and the platform is graded on them.
``calibration_probability`` is written per leg (Part A of
``_backfill_calibration_prices`` takes each outcome's own last snapshot before
the event's commence_time) with no pair constraint anywhere. That is the
"second, unguarded writer" the diagnosis names as this cell's next lead.

WHY EXCLUDE AND NOT REPAIR. Both legs fell from their openings (over -8.66 pp,
under -3.86 pp), so the arithmetic does not name a wrong leg and no measurement
on record names one either. Item 1's disposition doctrine forks exactly here:
REPAIR only where the direction is structurally certain (``identical_noncomp``,
where a measured 0.886 price/win-rate correlation established which leg carried
the real price), otherwise EXCLUDE read-side. Inventing a direction is the
"invented price becomes a published forecast" failure that
``app/utils/pair_opening_coherence.py`` exists to refuse.

WHAT THIS FILE DOES NOT CLAIM
-----------------------------
**No ECE number.** Under ruling 134 a build lane measures its own gates and
nothing else, so this change ships with its delta UNMEASURED. The instrument for
it is ``scripts/fold_published_pair_coherence.py``, which renders THIS predicate
rather than restating it, and the measurement is owed to the measurement lane.
A green here means the rule is the rule it says it is — never that it helps.
That distinction is the whole of CERT-403B and CERT-406B.
"""

from __future__ import annotations

import inspect
import re

import pytest

from app.tasks import precompute_calibration as pc
from app.tasks.precompute_calibration import (
    PUBLISHED_PAIR_CELL_CATEGORY,
    PUBLISHED_PAIR_CELL_MARKET_TYPE,
    PUBLISHED_PAIR_CELL_SOURCE,
    PUBLISHED_PAIR_RULE_TEXT,
    TERMINAL_PUBLISHED_PRICE_SQL,
    _calibration_population_ctes,
    half_spike_pair_market_predicate,
    published_pair_incoherent_market_predicate,
    published_pair_shape_columns,
    published_row_predicate,
    two_leg_over_under_shape_clauses,
)
from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE


def _population_sql() -> str:
    return _calibration_population_ctes()


class TestThePredicateIsTheRule:
    """The five clauses, each evaluated exactly rather than described."""

    @staticmethod
    def _decide(
        *,
        n_outcomes: int = 2,
        over: int = 1,
        under: int = 1,
        open_legs: int = 2,
        pub_legs: int = 2,
        open_sum: float = 1.0,
        pub_sum: float = 0.875,
    ) -> bool:
        """Evaluate the SHIPPED predicate in Python over one market's shape.

        The expression is parsed out of the shipped string, exactly as the
        half-spike suite does, so this helper cannot drift from the rule it is
        checking. A predicate that is a boolean over six numbers can be
        evaluated rather than approximated.
        """
        expr = published_pair_incoherent_market_predicate("m")
        shape = type(
            "S",
            (),
            {
                "hs_n_outcomes": n_outcomes,
                "hs_named_over": over,
                "hs_named_under": under,
                "pp_open_legs": open_legs,
                "pp_pub_legs": pub_legs,
                "pp_open_sum": open_sum,
                "pp_pub_sum": pub_sum,
            },
        )()
        py = expr.replace("\n", " ").replace("AND", "and").replace("ABS(", "abs(")
        py = py.replace("=", "==").replace("<==", "<=").replace(">==", ">=")
        return bool(eval(py, {"__builtins__": {"abs": abs}}, {"m": shape}))  # noqa: S307

    def test_the_measured_specimen_is_excluded(self):
        """Opening sums to 1.0001, published to 0.8749 — check 2's own numbers."""
        assert self._decide(open_sum=1.0001, pub_sum=0.8749) is True

    def test_a_pair_that_publishes_coherently_is_kept(self):
        """The rule is about incoherence, not about Over/Under markets."""
        assert self._decide(open_sum=1.0, pub_sum=1.0) is False

    def test_a_pair_incoherent_at_opening_is_NOT_this_rules_business(self):
        """The disjointness clause, and it is the one most worth having.

        Pairs already incoherent at capture are the ``other_noncomp`` class,
        whose read-side exclusion is a DIFFERENT staged rule
        (``QUEUE-STAGED-CAL-PAIR-OPENING-DISPOSITION.md``, 5,566 markets).
        Without the opening-coherence clause this predicate would swallow that
        population too — and a rule that removes more than it claims is exactly
        what CERT-403B blocked the half-spike apply for. Disjoint by
        construction beats disjoint by everyone remembering.
        """
        assert self._decide(open_sum=0.9059, pub_sum=0.875) is False

    def test_the_boundary_is_the_shared_tolerance_on_both_sides(self):
        """Inside and outside the tolerance, deliberately not ON it.

        ``1 + 0.02`` is not representable, so an assertion pinned to the exact
        boundary tests IEEE-754 rather than the rule — and it would then differ
        between this Python evaluator and PostgreSQL's numeric arithmetic, which
        is a disagreement about nothing that a future reader has to diagnose.
        """
        inside = 1 + PAIR_SUM_TOLERANCE * 0.5
        outside = 1 + PAIR_SUM_TOLERANCE * 1.5
        assert self._decide(open_sum=inside, pub_sum=outside) is True
        # Opening outside tolerance -> not captured coherently -> another rule's.
        assert self._decide(open_sum=outside, pub_sum=outside) is False
        # Published inside tolerance -> coherent enough -> kept.
        assert self._decide(open_sum=1.0, pub_sum=inside) is False

    def test_a_three_leg_market_is_kept(self):
        """A field is not a pair, however its prices sum."""
        assert self._decide(n_outcomes=3, pub_sum=0.875) is False

    def test_an_unnamed_two_leg_market_is_kept(self):
        """Yes/No is a different instrument from the Over/Under writer path."""
        assert self._decide(over=0, under=0) is False

    def test_a_half_priced_pair_is_kept_on_both_leg_counts(self):
        """gotcha #53 in an aggregate: SUM skips NULLs.

        One priced leg at 0.98 and one unpriced leg produce ``pp_pub_sum =
        0.98`` — indistinguishable from a genuinely off-sum pair without the
        leg counts. Excluding on that would be reading a fact about the world
        out of a fact about the aggregate.
        """
        assert self._decide(pub_legs=1, pub_sum=0.98) is False
        assert self._decide(open_legs=1, open_sum=1.0) is False


class TestTheBuilderAppliesIt:
    """Criterion 1: in the SHARED payload builder, and it gates."""

    def test_the_flag_is_defined_once(self):
        assert _population_sql().count("AS is_published_pair_incoherent") == 1

    def test_the_flag_gates_every_published_set(self):
        """Four sites: both field_completeness counters, ``deduped``, and the
        half-spike counter, which holds this rule's arm in its NOT form.

        Counted, not merely present: this number rises when a rendering is added
        and falls when a gate is deleted, so a silent removal cannot pass by
        matching the substring somewhere else in a 57k-character statement.
        """
        assert _population_sql().count("AND NOT ro.is_published_pair_incoherent") == 4

    def test_the_exclusion_is_cell_scoped(self):
        """Same precedent as the half-spike rule's scope, same reason.

        CERT-403B's second P1 required a per-cell census before an unscoped
        exclusion, and CAL-P095 then produced the control that justified it: a
        rule worth -3.12 pp in one cell was +0.41 pp in another. This defect is
        a writer property and is very likely wider than one cell — but likely is
        not measured, and this lane may not measure it (ruling 134).
        """
        sql = _population_sql()
        assert f"mi.source = '{PUBLISHED_PAIR_CELL_SOURCE}'" in sql
        assert f"mi.category = '{PUBLISHED_PAIR_CELL_CATEGORY}'" in sql
        assert f"mi.market_type = '{PUBLISHED_PAIR_CELL_MARKET_TYPE}'" in sql

    def test_both_legs_leave_together(self):
        """Symmetric, like the opening gate — and for the same recorded reason.

        The flag is market membership with NO leg-value clause, so a flagged
        market removes both of its legs. Stamping or dropping only the side that
        looks wrong is how the 22.71% ``partial_open`` population came to exist,
        and here there is no measurement that says which side IS wrong.
        """
        assert pc._PUBLISHED_PAIR_FLAG_SQL == "(ppi.market_id IS NOT NULL)"
        assert "ROUND" not in pc._PUBLISHED_PAIR_FLAG_SQL

    def test_the_tolerance_is_imported_not_restated(self):
        """One tolerance for the writer gate and the read-side gate.

        ``pair_opening_coherence`` gives the reason in its own comment: a
        tolerance that drifted between two gates would let one disagree with the
        measurement that justified the other.
        """
        src = inspect.getsource(pc)
        assert "from app.utils.pair_opening_coherence import PAIR_SUM_TOLERANCE" in src
        assert f"<= {PAIR_SUM_TOLERANCE}" in published_pair_incoherent_market_predicate()


class TestItIsForwardOnlyAndReadSide:
    """Criterion 3 / gotcha #21: nothing here re-grades anything."""

    @pytest.mark.parametrize(
        "fn",
        [
            published_pair_incoherent_market_predicate,
            published_pair_shape_columns,
            two_leg_over_under_shape_clauses,
        ],
    )
    def test_no_write_verb_in_the_rules_own_sql(self, fn):
        rendered = fn().upper()
        for verb in ("UPDATE ", "INSERT ", "DELETE ", "SET "):
            assert verb not in rendered

    def test_the_population_chain_writes_nothing(self):
        """The whole rendered statement, not just this rule's fragment.

        Matched on statement VERBS, not on column names: ``fo.is_winner = true``
        appears throughout as a FILTER predicate, and an assertion that banned
        the substring would be banning a read. A grep that fires on correct code
        gets deleted by the next person in a hurry, and takes the real guard
        with it.
        """
        sql = _population_sql().upper()
        for verb in (r"\bUPDATE\s+\w", r"\bINSERT\s+INTO\b", r"\bDELETE\s+FROM\b"):
            assert not re.search(verb, sql), verb
        assert not re.search(r"\bSET\s+(IS_WINNER|RESOLUTION_SOURCE|CALIBRATION_)", sql)


class TestTheCostIsReported:
    """Criterion 6 / the standing rule against silent caps."""

    def test_four_renderings_with_two_arms_each(self):
        """``published_row_predicate`` is the single text; the arms differ.

        Three marginal counts plus the overlap, so the numbers SUM to the
        published rows the pair rules cost with nothing double-counted and
        nothing dropped between two counters that each said "not mine".
        """
        sql = _population_sql()
        arms = [
            ("NOT ro.is_half_spike_pair", "NOT ro.is_published_pair_incoherent"),
            ("ro.is_half_spike_pair", "NOT ro.is_published_pair_incoherent"),
            ("NOT ro.is_half_spike_pair", "ro.is_published_pair_incoherent"),
            ("ro.is_half_spike_pair", "ro.is_published_pair_incoherent"),
        ]
        rendered = [
            published_row_predicate(half_spike_arm=h, pair_incoherent_arm=p)
            for h, p in arms
        ]
        assert len(set(rendered)) == 4, "the four renderings must be distinct"
        for text_ in rendered:
            assert text_ in sql

    def test_the_counter_cte_exists_and_is_joined(self):
        sql = _population_sql()
        assert "published_pair_incoherent_removed AS (" in sql
        assert "both_exclusions_removed AS (" in sql

    def test_the_payload_declares_the_rule_and_its_basis(self):
        """The reason string names the mechanism, the cell, and the disjointness.

        A count with no reason is a number a reader cannot act on; a reason that
        omits the scope hides the finding, because the scope IS the finding.
        """
        src = inspect.getsource(pc)
        assert '"published_pair_coherence_filter"' in src
        assert '"published_rows_removed_basis"' in src
        assert '"also_removed_by_half_spike_pair"' in src
        for phrase in ("OPENING", "PUBLISHED", "Read-side only"):
            assert phrase in PUBLISHED_PAIR_RULE_TEXT

    def test_an_absent_published_count_reads_unknown_not_zero(self):
        """gotcha #53. A census predating the counter did not measure zero.

        Reporting 0 would assert "the exclusion removed nothing from the curve",
        which is the strongest possible claim about criterion 4 and the one
        nobody made.
        """
        src = inspect.getsource(pc)
        assert (
            "published_pair_incoherent_published_removed = (\n"
            "            int(_ppir) if _ppir is not None else None\n"
            "        )" in src
        )


class TestTheFingerprintCannotMissIt:
    """The regression CAL-P099 nearly shipped, re-run against the new inputs.

    ``inspect.getsource`` returns the literal text ``{PUBLISHED_PAIR_CELL_...}``,
    never ``baseball``. Every value below shapes the emitted statement and none
    of them lives inside a hashed function's source, so each is hashed BY VALUE
    or the digest would stay put while the published population moved — a
    carried read banked under one population, resumed by code publishing
    another.
    """

    @pytest.mark.parametrize(
        "attr,mutate",
        [
            ("PUBLISHED_PAIR_CELL_CATEGORY", lambda v: "soccer"),
            ("PUBLISHED_PAIR_CELL_SOURCE", lambda v: "kalshi"),
            ("PUBLISHED_PAIR_CELL_MARKET_TYPE", lambda v: "container_member"),
            ("_PUBLISHED_PAIR_FLAG_SQL", lambda v: "(false)"),
            ("PAIR_SUM_TOLERANCE", lambda v: 0.25),
        ],
    )
    def test_mutating_a_shaping_input_moves_the_digest(self, attr, mutate):
        base = pc._main_input_fingerprint()
        original = getattr(pc, attr)
        try:
            setattr(pc, attr, mutate(original))
            assert pc._main_input_fingerprint() != base, (
                f"{attr} shapes the published population but does not move the "
                "fingerprint — every edit to it would be invisible to a carried read"
            )
        finally:
            setattr(pc, attr, original)

    def test_the_shared_shape_clause_is_hashed_on_its_own(self):
        """It is a callee of BOTH pair predicates, so it moves two rules at once."""
        assert "two_leg_over_under_shape_clauses(\"mrs\")" in inspect.getsource(
            pc._main_input_fingerprint
        )


class TestTheRefactorDidNotMoveTheOtherRule:
    """Hoisting the shared O/U shape must not perturb the half-spike rule.

    Its predicate text is shared verbatim with ``scripts/fold_half_spike_pair.py``
    and pinned by that suite; a rendering change here would silently re-point a
    cert that is currently in flight (CERT-406B).
    """

    def test_the_half_spike_predicate_text_is_unchanged(self):
        assert half_spike_pair_market_predicate("mrs") == (
            "(mrs.hs_n_outcomes = 2\n"
            "                  AND mrs.hs_named_over = 1\n"
            "                  AND mrs.hs_named_under = 1\n"
            "                  AND mrs.hs_half_legs = 2)"
        )

    def test_both_predicates_render_the_same_shape_clause(self):
        shape = two_leg_over_under_shape_clauses("mrs")
        assert shape in half_spike_pair_market_predicate("mrs")
        assert shape in published_pair_incoherent_market_predicate("mrs")


class TestTheHorizonPathIsNotSilentlyRescoped:
    """The rule is defined on the TERMINAL published price, structurally.

    The horizon surface passes ``curve_price="hp.horizon_prob"`` with a join
    injected into ``ranked_outcomes`` and NOT into ``market_result_shape``, where
    these aggregates live. Rendering the parameter there is a SQL error on that
    path — and quietly re-pointing a terminal-price rule at a snapshot price
    would be the worse of the two outcomes, because it would run.
    """

    def test_the_headline_path_arms_the_rule(self):
        assert "(ppi.market_id IS NOT NULL)" in _population_sql()

    def test_a_non_terminal_curve_price_disarms_it(self):
        sql = _calibration_population_ctes(
            curve_price="hp.horizon_prob",
            curve_price_join="JOIN horizon_price hp ON hp.outcome_id = fo.id",
        )
        assert "(ppi.market_id IS NOT NULL)" not in sql
        assert "false\n                        AS is_published_pair_incoherent" in sql

    def test_the_aggregates_still_use_the_terminal_expression_off_path(self):
        """They must not reference the horizon alias, which is not in scope."""
        rendered = published_pair_shape_columns("fo")
        assert TERMINAL_PUBLISHED_PRICE_SQL.format(o="fo") in rendered
        assert "hp." not in rendered

    def test_the_explicit_kwarg_also_disarms_it(self):
        sql = _calibration_population_ctes(published_pair_coherence_enabled=False)
        assert "(ppi.market_id IS NOT NULL)" not in sql


class TestTheFoldCannotDisagreeWithTheBuilder:
    """CERT-403B's structural fix, applied to this rule's instrument.

    The blocked half-spike artifact came from a fold that RESTATED a filter the
    builder did not share. Telling the next author to be careful would leave the
    hole open, so the fold imports the predicate instead — and this asserts it
    still does, which is the only form of the discipline that closes it.
    """

    @staticmethod
    def _fold_source() -> str:
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "fold_published_pair_coherence.py"
        )
        return path.read_text()

    def test_the_fold_exists_and_is_named_by_the_shipped_docs(self):
        """The rule text and this suite both promise this instrument by name."""
        assert "def published_reading_sql" in self._fold_source()

    def test_the_fold_imports_the_predicate_rather_than_restating_it(self):
        src = self._fold_source()
        assert "published_pair_incoherent_market_predicate" in src
        assert "_calibration_population_ctes" in src
        # The signature of a hand-rolled copy: the rule's own arithmetic
        # appearing in the fold's SQL rather than arriving from the builder.
        assert "pp_pub_sum" not in src.split('"""', 2)[-1] or "predicate" in src

    def test_the_fold_switches_the_rule_at_its_single_definition(self):
        """Baseline vs proposed must be the shipped switch, not a second query."""
        src = self._fold_source()
        assert "published_pair_coherence_enabled=enabled" in src

    def test_a_refused_reading_is_not_a_zero(self):
        """gotcha #53, and the reason this fold can be trusted when it fails.

        A timeout and "the exclusion removed nothing" are the same response
        shape and opposite facts. The fold must carry ``measured: false`` and
        must not exit 0 on a refusal.
        """
        src = self._fold_source()
        assert '"measured": False' in src
        assert 'return 0 if all(r.get("measured") for r in readings.values()) else 1' in src


class TestTheOffSwitchIsConfinedToThisRule:
    """Baseline vs proposed differ in this rule's expressions and NOWHERE else.

    CERT-406B's requirement, and the property that makes a before/after reading
    attributable at all: if anything else about the population moved between the
    two renderings, the measured delta is not this rule's delta. Proved by
    masking the two expressions out of the armed chain and requiring byte
    equality with the disarmed one — not by reading the diff and judging it
    small.
    """

    def test_masking_the_rules_expressions_reproduces_the_disarmed_chain(self):
        armed = _calibration_population_ctes()
        disarmed = _calibration_population_ctes(published_pair_coherence_enabled=False)
        masked = armed.replace(
            published_pair_incoherent_market_predicate("mrs"), "false"
        ).replace(pc._PUBLISHED_PAIR_FLAG_SQL, "false")
        assert masked == disarmed

    def test_the_half_spike_switch_is_still_independent(self):
        """Turning this rule off must not move the other rule's rendering.

        CERT-406B is in flight against the half-spike switch. If the two rules
        shared a switch, its before/after reading would silently become a
        reading about both.
        """
        off_here = _calibration_population_ctes(published_pair_coherence_enabled=False)
        assert pc._HALF_SPIKE_FLAG_SQL in off_here
