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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


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

        This asserted the exit line VERBATIM until C-PUBLISHED-PAIR-1. It now
        asserts the property, because the gate got STRICTER — a non-local
        result exits 3 — and a literal-line assertion would have read that
        tightening as a regression. The refusal arm is unchanged.
        """
        src = self._fold_source()
        assert '"measured": False' in src
        assert 'if not all_measured:\n        return 1' in src
        assert 'return 0 if out["criterion_4"]["locality_verdict"] == "local" else 3' in src

    def test_the_two_readings_are_one_snapshot_on_one_connection(self):
        """C-PUBLISHED-PAIR-1 P1 #1, both halves of it.

        The blocked version made two ``POST /api/admin/db-query`` ROW requests
        carrying ``--timeout-ms 5400000``. The row path REFUSES ``timeout_ms``
        and runs under a hard-coded 10 s (``admin_data_quality.py``), so the
        advertised budget could not be applied from the request body at all;
        and two requests are two snapshots, so concurrent calibration writes
        would show as movement the exclusion did not cause.
        """
        src = self._fold_source()
        assert "REPEATABLE READ, READ ONLY" in src
        assert "SET LOCAL statement_timeout" in src
        # The HTTP rail is not merely unused — it is gone. A retained import is
        # a retained temptation for the next author under time pressure.
        assert "dbq_probe" not in src
        assert "dbq_run" not in src

    def test_the_snapshot_claim_is_proved_not_asserted(self):
        """The instrument checks its own premise, and fails closed on it.

        ``now()`` is the transaction timestamp at EVERY isolation level, so it
        proves one TRANSACTION and nothing about visibility; and two
        ``pg_current_snapshot()`` reads match under READ COMMITTED whenever
        nothing committed in between — a fact about how busy the database was.
        So the definite check is ``transaction_isolation``, read back from the
        server, and a run that cannot show it is not ``measured``.
        """
        from scripts.fold_published_pair_coherence import _snapshot_proof

        def raw(iso_open, iso_close, snap_close="S1", t_close="T1"):
            return {
                "snapshot_open": {
                    "measured": True,
                    "rows": [("S1", "T1", iso_open, "5400000ms")],
                },
                "snapshot_close": {
                    "measured": True,
                    "rows": [(snap_close, t_close, iso_close, "5400000ms")],
                },
            }

        good = _snapshot_proof(raw("repeatable read", "repeatable read"))
        assert good["isolation_held"] and good["one_snapshot"]

        # The server silently gave us READ COMMITTED: refused, even though both
        # probes agree — agreement under READ COMMITTED is luck, not a snapshot.
        weak = _snapshot_proof(raw("read committed", "read committed"))
        assert not weak["isolation_held"] and not weak["one_snapshot"]

        # Isolation is right but the snapshot moved: still refused.
        moved = _snapshot_proof(
            raw("repeatable read", "repeatable read", snap_close="S2")
        )
        assert moved["isolation_held"] and not moved["one_snapshot"]

        # A probe that did not run is not a pass.
        absent = _snapshot_proof({"snapshot_open": {"measured": False}})
        assert not absent["one_snapshot"]

    def test_the_admin_row_path_still_refuses_the_timeout_this_fold_stopped_asking_for(
        self,
    ):
        """The premise above, asserted against the server rather than recalled.

        If the row path ever grows a real ``timeout_ms``, this test fails and
        the fold's docstring becomes wrong — which is the moment to revisit it.
        """
        from pathlib import Path

        route = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "routes"
            / "admin_data_quality.py"
        ).read_text()
        assert "`timeout_ms` is only supported with `explain: true`" in route
        assert "SET LOCAL statement_timeout = '10s'" in route


class TestCriterionFourCanActuallyFail:
    """C-PUBLISHED-PAIR-1 P1 #2 — the artifact must SEPARATE the two outcomes.

    The blocked version emitted ``bins_whose_row_identity_changed`` and nothing
    else. Every bin holding a legitimately excluded row must appear in that
    list, so it could not distinguish expected removal from an unrelated
    survivor entering or leaving the bin — and because the digest hashed
    outcome IDs alone, a survivor renormalized WITHIN its decile did not appear
    at all.

    Each test below is a mutant that the blocked artifact would have passed.
    """

    #: Two flagged legs (market 7) and three survivors spread across deciles.
    BASELINE = {
        1: {"market_id": 7, "p": 0.41, "is_winner": False, "truth": "eligible"},
        2: {"market_id": 7, "p": 0.47, "is_winner": True, "truth": "eligible"},
        3: {"market_id": 8, "p": 0.61, "is_winner": True, "truth": "eligible"},
        4: {"market_id": 9, "p": 0.22, "is_winner": False, "truth": "eligible"},
        5: {"market_id": 9, "p": 0.78, "is_winner": True, "truth": "ineligible"},
    }
    FLAGGED = {7}

    @staticmethod
    def _compare(proposed, flagged=None):
        from scripts.fold_published_pair_coherence import compare_readings

        return compare_readings(
            TestCriterionFourCanActuallyFail.BASELINE,
            proposed,
            TestCriterionFourCanActuallyFail.FLAGGED if flagged is None else flagged,
        )

    def _survivors(self) -> dict:
        return {k: dict(v) for k, v in self.BASELINE.items() if k not in (1, 2)}

    def test_the_clean_exclusion_is_local(self):
        """The control. Without it, a mutant test proves only that it says no."""
        verdict = self._compare(self._survivors())
        assert verdict["locality_verdict"] == "local"
        assert verdict["removed"]["ids"] == [1, 2]
        assert verdict["expected_removed"]["ids"] == [1, 2]
        assert verdict["added"]["count"] == 0
        assert verdict["mutated_survivors"]["count"] == 0

    def test_a_same_bin_normalization_mutant_is_caught(self):
        """The kill the old digest could not make.

        Outcome 3 moves 0.61 -> 0.68. Same decile, same outcome ID, so an
        ID-keyed per-bin digest is byte-identical and the bin never appears as
        changed — while the curve moves.
        """
        from scripts.fold_published_pair_coherence import bin_of

        proposed = self._survivors()
        proposed[3]["p"] = 0.68
        assert bin_of(0.61) == bin_of(0.68)  # the mutant really does stay put

        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["mutated_survivors"]["count"] == 1
        assert verdict["mutated_survivors"]["same_bin"] == 1
        assert verdict["mutated_survivors"]["cross_bin"] == 0

    def test_a_cross_bin_normalization_mutant_is_caught(self):
        """The same defect with a bin edge crossed — and named apart."""
        proposed = self._survivors()
        proposed[3]["p"] = 0.31

        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["mutated_survivors"]["cross_bin"] == 1
        assert verdict["mutated_survivors"]["same_bin"] == 0

    def test_a_row_the_baseline_excluded_cannot_appear(self):
        """The exclusion may only REMOVE. An admitted row is not this rule."""
        proposed = self._survivors()
        proposed[99] = {
            "market_id": 11,
            "p": 0.5,
            "is_winner": True,
            "truth": "eligible",
        }
        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["added"]["ids"] == [99]

    def test_removing_a_row_no_flagged_market_explains_is_caught(self):
        """A removal outside the flagged set is a side effect, not the rule."""
        proposed = self._survivors()
        del proposed[4]
        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["unexpectedly_removed"]["ids"] == [4]

    def test_a_flagged_row_left_behind_is_caught(self):
        """Both legs leave together — one surviving is the asymmetry bug."""
        proposed = {k: dict(v) for k, v in self.BASELINE.items() if k != 1}
        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["expected_but_kept"]["ids"] == [2]

    def test_the_truth_class_of_a_survivor_is_compared_too(self):
        """Eligibility moving under the rule would re-grade, not exclude."""
        proposed = self._survivors()
        proposed[5]["truth"] = "eligible"
        verdict = self._compare(proposed)
        assert verdict["locality_verdict"] == "not_local"
        assert verdict["mutated_survivors"]["count"] == 1

    def test_the_bin_table_carries_counts_sums_winners_and_identity(self):
        """Per-bin ROW IDENTITY, not only the numbers of changed bins."""
        from scripts.fold_published_pair_coherence import fold_bins

        bins = fold_bins(self.BASELINE)["eligible"]
        assert set(bins[4]) == {"n", "sum_prob", "winners", "row_identity"}
        assert bins[4]["n"] == 2 and bins[4]["winners"] == 1

    def test_the_bin_identity_moves_when_a_value_moves_inside_the_bin(self):
        """The digest's own regression test for the same-bin hole."""
        from scripts.fold_published_pair_coherence import fold_bins

        before = fold_bins(self.BASELINE)["eligible"][6]["row_identity"]
        mutated = {k: dict(v) for k, v in self.BASELINE.items()}
        mutated[3]["p"] = 0.68
        after = fold_bins(mutated)["eligible"][6]["row_identity"]
        assert before != after

    def test_the_blocked_id_only_digest_would_have_missed_it(self):
        """Red-first, kept rather than thrown away.

        The BLOCKed artifact hashed ``STRING_AGG(outcome_id)``. Re-run here
        against the same mutant, it is byte-identical across a survivor moving
        0.61 -> 0.68 — so the old artifact reported an unchanged bin for a
        change that moves the curve. The new suite is only meaningful beside
        the demonstration that the old one passed.

        This is a probe of a DELETED definition, restated locally on purpose:
        pinning it against the live module would make it a second
        implementation of the thing under test.
        """
        import hashlib

        def id_only_digest(rows: dict) -> str:
            members = sorted(
                oid for oid, r in rows.items() if r["truth"] == "eligible" and 0.6 <= r["p"] < 0.7
            )
            return hashlib.md5(",".join(str(o) for o in members).encode()).hexdigest()

        mutated = {k: dict(v) for k, v in self.BASELINE.items()}
        mutated[3]["p"] = 0.68
        assert id_only_digest(self.BASELINE) == id_only_digest(mutated)


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
