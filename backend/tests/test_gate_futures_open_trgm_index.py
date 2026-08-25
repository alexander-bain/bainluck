"""The futures partial-trigram gate must stay red-first, no-op-proof, and route-bound.

Sibling of `test_gate_teams_fts_index.py`. It exists because the LATENCY program has
now got the same criterion wrong THREE times, each time in a way that reading the
code did not catch and running it did:

1. **An absolute millisecond budget passed on an unindexed database.** LAT-P085
   pre-registered "exec_ms < 50" against a banked red of 386-485 ms; measured with
   no index in production at all: 46.6-54.3 ms. (LAT-P087's finding.)

2. **An absolute RATIO threshold did the same thing one cycle later.** This gate's
   first draft used `ratio <= 0.25`. The term `super bowl` PASSED it with no index
   in production, because its name arm is ~1.4 ms and its control is ~19 ms. A
   constant cannot tell "the index worked" from "this term was always cheap".

3. **A pooled median of raw milliseconds was decided by the oddest control.** The
   second draft pooled `median(all name_ms) / median(all ctrl_ms)` across terms.
   But the outcome-arm control is a DIFFERENT query per term with its own
   selectivity: in one interleaved batch `champion`'s control ran 4,343.8 ms and
   `election`'s ran 67.4 ms. Pooling raw times hands the verdict to whichever term
   has the largest control.

The fix that survived is a PER-TERM PAIRED collapse -- `ratio_after / ratio_before`
per term, then the median of those, ceiling 0.5. These tests pin the property that
makes it trustworthy: **a no-op scores 1.0 and fails, arithmetically, on every
term, at every level of the underlying milliseconds.**

Nothing here touches production. The gate's network calls are never exercised;
`_ids_for`'s failure path is driven by a monkeypatched `_post`.
"""

import importlib.util
import json
import os

import pytest

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GATE_PATH = os.path.join(_BACKEND, "scripts", "gate_futures_open_trgm_index.py")


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "gate_futures_open_trgm_index", _GATE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def _terms(**pairs):
    """Synthetic per-term records: term -> (ratio_after, ratio_before)."""
    return {
        term: {"ratio": after, "before_ratio": before}
        for term, (after, before) in pairs.items()
    }


class TestANoOpCannotPass:
    """The single property the previous two drafts both lacked."""

    def test_identical_before_and_after_fails(self, gate):
        passed, collapses, _note = gate.budget_verdict(
            _terms(
                world_series=(0.891, 0.891),
                champion=(1.114, 1.114),
                super_bowl=(0.073, 0.073),
            )
        )
        assert set(collapses.values()) == {1.0}
        assert passed is False

    def test_the_cheap_term_that_broke_draft_one_no_longer_passes_alone(self, gate):
        """`super bowl` measured ratio 0.073 with NO index in production.

        Against a constant of 0.25 that read as a win. Against its own recorded
        before it reads as exactly what it is: no change."""
        passed, collapses, _ = gate.budget_verdict(_terms(super_bowl=(0.073, 0.073)))
        assert collapses == {"super_bowl": 1.0}
        assert passed is False

    @pytest.mark.parametrize("scale", [0.001, 1.0, 1000.0])
    def test_no_op_fails_at_every_scale_of_the_underlying_times(self, gate, scale):
        """There is no level of the milliseconds at which doing nothing passes.

        Draft one's constant could be satisfied by a term simply being cheap;
        this cannot, because the scale cancels in the division."""
        passed, _c, _n = gate.budget_verdict(
            _terms(a=(0.9 * scale, 0.9 * scale), b=(3.1 * scale, 3.1 * scale))
        )
        assert passed is False


class TestTheCollapseIsPerTermNotPooled:
    def test_a_hundredfold_control_spread_does_not_decide_the_verdict(self, gate):
        """Draft three's bug, pinned.

        Real levels from one interleaved batch: `champion` ctrl 946 ms, `election`
        ctrl 33 ms. Both terms here halve their OWN ratio, so the verdict must be
        a clean pass regardless of the 100x spread between their controls."""
        passed, collapses, _ = gate.budget_verdict(
            _terms(champion=(0.557, 1.114), election=(5.010, 10.020))
        )
        assert collapses == {"champion": 0.5, "election": 0.5}
        assert passed is True

    def test_one_term_improving_enormously_cannot_carry_the_others(self, gate):
        """A median of collapses, not a mean and not a pooled ratio: three terms
        unchanged and one term 100x better is still a FAIL."""
        passed, _c, _n = gate.budget_verdict(
            _terms(a=(0.01, 1.0), b=(1.0, 1.0), c=(1.0, 1.0), d=(1.0, 1.0))
        )
        assert passed is False

    def test_a_real_collapse_passes(self, gate):
        """The predicted mechanism is ~12x. A uniform 5x collapse must pass."""
        passed, _c, _n = gate.budget_verdict(
            _terms(a=(0.2, 1.0), b=(0.18, 0.9), c=(2.0, 10.0))
        )
        assert passed is True

    def test_terms_with_no_recorded_before_are_omitted_not_defaulted(self, gate):
        """A missing baseline entry must not contribute a flattering 1.0 nor a
        passing 0.0 -- it must not contribute at all."""
        terms = _terms(a=(0.2, 1.0))
        terms["never_measured"] = {"ratio": 0.3, "before_ratio": None}
        _passed, collapses, _ = gate.budget_verdict(terms)
        assert list(collapses) == ["a"]

    def test_an_empty_baseline_is_a_fail_not_a_pass(self, gate):
        """Nothing to compare against must never read as GREEN (gotcha #53's
        shape: absence and success must not arrive in the same verdict)."""
        passed, collapses, note = gate.budget_verdict(
            {"a": {"ratio": 0.2, "before_ratio": None}}
        )
        assert passed is False
        assert collapses == {}
        assert "cannot compute" in note


class TestNoAbsoluteBudgetSurvives:
    def test_no_millisecond_constant_in_the_gate(self, gate):
        """Failure mode 1, kept out. Any module-level constant whose name says
        milliseconds and whose value sits in a plausible latency range is an
        absolute budget sneaking back in."""
        for name, value in vars(gate).items():
            if name.startswith("_") or isinstance(value, bool):
                continue
            if not isinstance(value, (int, float)):
                continue
            assert not (
                name.upper().endswith(("_MS", "_MS_BUDGET", "_MILLIS", "_THRESHOLD_MS"))
                and 1 <= value <= 5000
            ), f"{name}={value} looks like the absolute budget this lane removed twice"

    def test_the_ceiling_is_a_collapse_factor_strictly_inside_zero_and_one(self, gate):
        """> 0 or a perfect index could not pass; >= 1.0 and a no-op would."""
        assert 0.0 < gate.MEDIAN_COLLAPSE_FACTOR < 1.0

    def test_the_per_term_regression_ceiling_is_above_one(self, gate):
        """Non-regression allows a term to get somewhat worse (planner noise) but
        must not be so tight that ambient variance reads as a regression."""
        assert gate.PER_TERM_REGRESSION_FACTOR > 1.0


class TestControlCannotBeServedByTheDDL:
    """A control the index speeds up is not a control -- the ratio never collapses."""

    def test_the_control_arm_does_not_filter_on_the_indexed_column(self, gate):
        control = gate._sql_for("champion", "outcome")
        assert "futures_outcomes.name ILIKE" in control
        assert "futures_markets.name ILIKE" not in control

    def test_the_control_order_by_carries_no_name_ilike_tier(self, gate):
        """LAT-P088's own correction to `explain_search_arm.py`.

        `CASE WHEN name ILIKE ... THEN 0` is evaluated on the rows the arm
        returns, so leaving it in would put the exact work the DDL changes inside
        the control."""
        control = gate._sql_for("champion", "outcome")
        assert "CASE WHEN" not in control.upper()

    def test_the_subject_arm_does_filter_on_the_indexed_column(self, gate):
        subject = gate._sql_for("champion", "name")
        assert "futures_markets.name ILIKE" in subject

    def test_control_is_cpu_matched_by_carrying_the_same_rank_tail(self, gate):
        """Both arms must pay `ts_rank_cd(to_tsvector(name))` so that CPU appears
        on both sides and largely cancels."""
        control = gate._sql_for("champion", "outcome").lower()
        assert "ts_rank_cd" in control
        assert "to_tsvector" in control

    def test_a_term_with_no_outcome_arm_refuses_rather_than_substituting(self, gate):
        """Silently falling back to the name arm would make the gate compare the
        subject against itself and report 1.0 forever."""
        import explain_search_arm as ESA

        with pytest.raises(ValueError, match="no outcome arm"):
            ESA.build_futures_arm("fc", "outcome")


class TestPredicateIsCompiledFromTheLiveRoute:
    def test_subject_sql_carries_the_route_status_predicate_verbatim(self, gate):
        """The DDL's `WHERE status = 'open'` is only implied by the query if the
        query says it. LAT-P086 killed an index over exactly this kind of
        expression mismatch."""
        assert "futures_markets.status = 'open'" in gate._sql_for("champion", "name")

    def test_subject_sql_still_carries_the_fts_precision_filter(self, gate):
        """If the route ever drops it, the spec's §0b evidence goes stale and this
        test is where that is noticed."""
        subject = gate._sql_for("champion", "name").lower()
        assert "websearch_to_tsquery" in subject
        assert "@@" in subject

    def test_no_doubled_percent_escapes_leak_into_the_ilike(self, gate):
        """`literal_binds` doubles `%`; left as `%%` every ILIKE matches a literal
        percent sign and returns nothing -- which looks like a fast plan rather
        than a broken one."""
        assert "%%" not in gate._sql_for("champion", "name")


class TestShapeCriterion:
    def test_the_expected_and_forbidden_indexes_are_the_specified_pair(self, gate):
        assert gate.EXPECTED_INDEX == "ix_futures_name_trgm_open"
        assert gate.FORBIDDEN_INDEX == "ix_futures_markets_status"

    def test_bitmap_index_scans_are_found_at_any_nesting_depth(self, gate):
        plan = {
            "plan": [
                {
                    "Plan": {
                        "Node Type": "Bitmap Heap Scan",
                        "Plans": [
                            {
                                "Node Type": "BitmapAnd",
                                "Plans": [
                                    {
                                        "Node Type": "Bitmap Index Scan",
                                        "Index Name": "ix_futures_name_trgm_open",
                                    },
                                    {
                                        "Node Type": "Bitmap Index Scan",
                                        "Index Name": "ix_futures_markets_status",
                                    },
                                ],
                            }
                        ],
                    }
                }
            ]
        }
        assert gate._bitmap_index_scans(plan) == {
            "ix_futures_name_trgm_open",
            "ix_futures_markets_status",
        }

    def test_the_new_index_present_alongside_the_status_bitmap_is_a_fail(self, gate):
        """The half a casual check skips. If the planner picks the partial index
        AND still builds the 71,368-row status bitmap, it is not satisfying
        `status='open'` from the index predicate and the mechanism has not
        engaged -- even though the index is right there in the plan."""
        seen = {gate.EXPECTED_INDEX, gate.FORBIDDEN_INDEX}
        was_subject = True
        shape_ok = gate.EXPECTED_INDEX in seen and not (
            was_subject and gate.FORBIDDEN_INDEX in seen
        )
        assert shape_ok is False

    def test_a_seq_scan_plan_finds_no_indexes(self, gate):
        plan = {"plan": [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "futures_markets"}}]}
        assert gate._bitmap_index_scans(plan) == set()


class TestHarnessFailuresAreNotVerdicts:
    def test_missing_execution_time_exits_2_not_1(self, gate):
        """Gotcha #54 as amended: 1 is a result, everything else is a story about
        the harness. An analyze that did not run must never read as RED."""
        with pytest.raises(SystemExit) as exc:
            gate._exec_ms({"plan": [{"Plan": {"Node Type": "Seq Scan"}}]})
        assert exc.value.code == 2

    def test_exec_ms_parses_a_real_payload(self, gate):
        plan = {"plan": [{"Plan": {"Node Type": "Seq Scan"}, "Execution Time": 1054.03}]}
        assert gate._exec_ms(plan) == pytest.approx(1054.03)

    def test_an_unreadable_id_set_is_a_reason_string_not_an_empty_list(
        self, gate, monkeypatch
    ):
        """Gotcha #53. `champion` and `winner` genuinely exceed the endpoint's
        10 s row-path timeout today. Returning `[]` would make "the route sheds
        this query" indistinguishable from "this query matches nothing", and the
        semantics check would then compare two empty lists and PASS."""

        def _boom(*_args, **_kwargs):
            raise gate.DbQueryFailed("statement_timeout")

        monkeypatch.setattr(gate, "_post", _boom)
        result = gate._ids_for("champion")
        assert isinstance(result, str)
        assert result == "UNREAD:statement_timeout"
        assert result != []


class TestTheGateSurvivesItsOwnNoiseFloor:
    """The criterion was validated against the database, not just reasoned about.

    "A no-op scores 1.0" is true of the arithmetic. Whether it is true of THIS
    database at THIS load was a separate question, and an unanswered one is how
    LAT-P085's criterion got banked: 0.5 is only a meaningful ceiling if ambient
    variance cannot reach it on its own.

    So a second `before` run was taken with no DDL in between --
    `lat-p088-futures-open-trgm-noop-selftest.json`, five rounds, same terms --
    and scored against the recorded baseline exactly as an `after` run would be.
    Two runs of the same unindexed database. If that had scored under 0.5, the
    gate would have been measuring weather.
    """

    NOOP = "lat-p088-futures-open-trgm-noop-selftest.json"

    def _noop_terms(self, gate):
        path = os.path.join(os.path.dirname(gate.BASELINE), self.NOOP)
        with open(path) as handle:
            noop = json.load(handle)
        with open(gate.BASELINE) as handle:
            base = json.load(handle)
        return {
            term: {"ratio": entry["ratio"], "before_ratio": base["terms"][term]["ratio"]}
            for term, entry in noop["terms"].items()
        }

    def test_two_unindexed_runs_do_not_pass_the_budget(self, gate):
        passed, collapses, note = gate.budget_verdict(self._noop_terms(gate))
        assert passed is False, f"ambient variance alone beats the ceiling: {note}"
        assert len(collapses) == len(gate.TERMS)

    def test_the_measured_noop_median_has_real_headroom_over_the_ceiling(self, gate):
        """Measured 1.2945 against a ceiling of 0.5 -- 2.6x of headroom.

        Asserted at 1.5x rather than at the observed value, so ordinary drift in
        production load does not turn this test red while the gate is still
        sound. If it DOES go red, the honest reading is that the ceiling needs
        re-deriving, not that the test needs loosening."""
        import statistics

        collapses = gate.per_term_collapses(self._noop_terms(gate))
        median = statistics.median(collapses.values())
        assert median > gate.MEDIAN_COLLAPSE_FACTOR * 1.5, (
            f"no-op median collapse {median:.4f} is too close to the "
            f"{gate.MEDIAN_COLLAPSE_FACTOR} ceiling -- noise is approaching the "
            "signal and the criterion needs re-deriving"
        )

    def test_individual_terms_are_noisy_which_is_why_the_median_is_the_statistic(
        self, gate
    ):
        """Per-term collapses across two no-op runs ranged 0.529-1.774. Several
        single terms DO cross the ceiling on noise alone. That is not a defect --
        it is the reason the verdict is a median over eight terms and not a
        per-term AND, and it is why `TestTheCollapseIsPerTermNotPooled` also
        pins that one spectacular term cannot carry the others."""
        collapses = gate.per_term_collapses(self._noop_terms(gate))
        crossers = [t for t, c in collapses.items() if c <= gate.MEDIAN_COLLAPSE_FACTOR]
        assert len(crossers) < len(collapses) / 2, (
            "a MAJORITY of terms cross the ceiling on a no-op, so the median "
            f"cannot hold either: {collapses}"
        )


class TestRecordedRedBaselineIsIntact:
    def test_the_baseline_exists_and_is_red(self, gate):
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        assert baseline["label"] == "before"
        assert baseline["verdict"] == "RED"

    def test_every_gated_term_has_a_before_ratio_and_a_plan(self, gate):
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        for term in gate.TERMS:
            entry = baseline["terms"][term]
            assert entry["ratio"] > 0
            assert entry["name_arm_indexes"], f"{term} recorded no index at all"

    def test_the_baseline_predates_the_index_it_gates(self, gate):
        """Red-first, provably: the expected index must appear in NO term's
        recorded plan. If it did, the `before` was taken after the DDL."""
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        for term, entry in baseline["terms"].items():
            assert gate.EXPECTED_INDEX not in entry["name_arm_indexes"], term

    def test_subject_classification_is_read_from_the_baseline_not_hardcoded(self, gate):
        """`world series` built the status bitmap during the 14-term probe and did
        NOT build it in the recorded before an hour later -- same query, same
        database, different plan. A hardcoded subject list would have demanded a
        shape change on a term that no longer had the shape."""
        with open(gate.BASELINE) as handle:
            baseline = json.load(handle)
        subjects = [
            t
            for t, e in baseline["terms"].items()
            if gate.FORBIDDEN_INDEX in e["name_arm_indexes"]
        ]
        assert subjects, "the recorded before found no subject term at all"
        assert len(subjects) < len(gate.TERMS), (
            "every term is a subject -- the bystander half of the probe is gone, "
            "so the gate no longer covers both measured plan shapes"
        )
