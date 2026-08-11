"""CAL-P032 — the C258 closure contract, as the PRODUCTION rail implements it.

CAL-P030 shipped the overlap-census walk with three mechanical holes, each of
which lets a walk that did not measure the population be reported as one:

1. **No ``cursor_in``.** Windows recorded where they ENDED (``next_offset``) and
   nothing about where they BEGAN, so a skipped region folded in looking exactly
   like a clean walk.
2. **No ``source_watermark``.** A walk over a table that changed underneath it is
   a *rolling* read, not a snapshot — and there was no way to tell which one you
   had, so every walk got described as the stronger of the two.
3. **``report()`` printed "PARTIAL — do not publish an N from this" and returned
   ZERO**, and ``main()`` discarded its return value on top of that. The banner
   reached a human; everything automated saw success.

All three are the same failure as gotcha #53 — an output whose emptier reading is
indistinguishable from a fact — and the third is its purest form: the process
exit code, the one signal a caller actually branches on, said the opposite of
the text printed directly above it.

These tests pin the contract by running the SHIPPED eight-case pack
(``scripts/evals/calibration_census_closure_contract``, fenced as C258) through
``census_overlap_trading.evaluate_closure``. The contract and the rail that has
to satisfy it are therefore checked against each other rather than maintained in
parallel — this lane's most-repeated defect being a second definition that
drifts from the first.
"""

from __future__ import annotations

import json

import pytest

from app.tasks import census_overlap_trading as cen
from app.tasks.census_overlap_trading import evaluate_closure
from scripts.evals.calibration_census_closure_contract import (
    evaluate as contract_evaluate,
    load_pack,
)


def _case_verdict(case: dict) -> dict:
    """Run one contract case through the production evaluator."""
    return evaluate_closure(
        case.get("windows", []),
        start_cursor=case.get("start_cursor", 0),
        chronology=case.get("chronology"),
    )


def _window(
    cursor_in: int,
    lo: int,
    hi: int,
    *,
    exhausted: bool = True,
    watermark: str | None = "w1",
    next_offset: int | None = None,
) -> dict:
    return {
        "cursor_in": cursor_in,
        "window": {"lo": lo, "hi": hi},
        "next_offset": hi if next_offset is None else next_offset,
        "exhausted": exhausted,
        "source_watermark": watermark,
        "rows_walked": 1,
        "cohorts": [],
    }


class TestTheShippedContractIsSatisfied:
    """The eight cases are codex's stated acceptance bar. They are the gate."""

    def test_the_pack_has_all_eight_cases(self):
        assert len(load_pack()["cases"]) == 8

    @pytest.mark.parametrize("case", load_pack()["cases"], ids=lambda c: c["id"])
    def test_production_matches_the_expected_verdict(self, case):
        assert _case_verdict(case) == case["expected"]

    @pytest.mark.parametrize("case", load_pack()["cases"], ids=lambda c: c["id"])
    def test_production_agrees_with_the_contract_reference(self, case):
        """Two implementations of one rule must not be allowed to disagree.

        The contract ships its own ``evaluate``; the rail ships
        ``evaluate_closure``. If these ever diverge, the eval passes while the
        thing it certifies is broken — which is the failure mode an eval exists
        to prevent, reintroduced by the eval itself.
        """
        assert _case_verdict(case) == contract_evaluate(case)


class TestSparseIdsAreValid:
    """The id space varies in density by two orders of magnitude.

    Requiring numeric adjacency (``lo == cursor_in + 1``) would fail every
    legitimate walk of a sparse region, so the rung is monotonic NON-OVERLAP.
    Getting this backwards would make the contract unsatisfiable in exactly the
    regions the census was built to reach.
    """

    def test_a_large_id_gap_between_windows_is_clean(self):
        windows = [
            _window(0, 10, 20, exhausted=False),
            _window(20, 100_000, 100_005),
        ]
        assert evaluate_closure(windows)["process_exit"] == 0
        assert evaluate_closure(windows)["reason_codes"] == []

    def test_adjacency_is_not_required(self):
        adjacent = [_window(0, 1, 20)]
        sparse = [_window(0, 5_000, 20_000)]
        assert evaluate_closure(adjacent) == evaluate_closure(sparse)


class TestWindowBounds:
    def test_a_window_that_reaches_back_over_the_cursor_is_invalid(self):
        """``lo <= cursor_in`` means the window re-walks rows already folded.

        Double-counting inflates the population, and an inflated population
        reads as a bigger sample rather than as a mistake.
        """
        verdict = evaluate_closure([_window(100, 100, 200)])
        assert verdict["process_exit"] == 1
        assert cen.WINDOW_BOUNDS_INVALID in verdict["reason_codes"]

    def test_an_inverted_window_is_invalid(self):
        verdict = evaluate_closure([_window(0, 500, 100)])
        assert verdict["process_exit"] == 1
        assert cen.WINDOW_BOUNDS_INVALID in verdict["reason_codes"]

    def test_the_empty_tail_window_has_no_bounds_to_check(self):
        """The rail's end-of-space window carries ``window: None``. That is the
        normal terminal shape, not a defect."""
        windows = [
            _window(0, 1, 20, exhausted=False),
            {
                "cursor_in": 20,
                "window": None,
                "next_offset": None,
                "exhausted": True,
                "source_watermark": "w1",
                "rows_walked": 0,
                "cohorts": [],
            },
        ]
        assert evaluate_closure(windows)["process_exit"] == 0


class TestTheChain:
    def test_a_gap_between_windows_breaks_the_chain(self):
        verdict = evaluate_closure(
            [_window(0, 10, 20, exhausted=False), _window(50, 51, 60)]
        )
        assert verdict["process_exit"] == 1
        assert cen.CURSOR_CHAIN_BROKEN in verdict["reason_codes"]

    def test_a_walk_that_did_not_start_at_the_beginning_is_not_the_population(self):
        verdict = evaluate_closure([_window(9_000, 9_001, 9_100)], start_cursor=0)
        assert verdict["process_exit"] == 1
        assert cen.START_CURSOR_MISMATCH in verdict["reason_codes"]

    def test_a_deliberate_partial_fold_can_declare_its_own_start(self):
        """Folding a resumed tail on purpose is legitimate — it just has to say
        so, which is what ``start_cursor`` is for."""
        verdict = evaluate_closure([_window(9_000, 9_001, 9_100)], start_cursor=9_000)
        assert verdict["reason_codes"] == []

    def test_a_missing_cursor_in_cannot_certify_a_walk(self):
        """CAL-P030's own JSONL has no ``cursor_in``. Folding it must not be
        silently accepted, and must not crash either."""
        legacy = {
            "window": {"lo": 1, "hi": 20},
            "next_offset": 20,
            "exhausted": True,
            "source_watermark": "w1",
            "rows_walked": 1,
            "cohorts": [],
        }
        verdict = evaluate_closure([legacy])
        assert verdict["process_exit"] == 1
        assert cen.START_CURSOR_MISMATCH in verdict["reason_codes"]


class TestTheTail:
    def test_an_unexhausted_tail_is_partial(self):
        verdict = evaluate_closure([_window(0, 1, 20, exhausted=False)])
        assert verdict["process_exit"] == 1
        assert verdict["walk_evidence"] == "partial"
        assert cen.TAIL_NOT_EXHAUSTED in verdict["reason_codes"]

    def test_the_tail_rung_is_the_shared_predicate(self):
        """``is_complete_walk`` stays the ONE definition of "the tail closed"."""
        windows = [_window(0, 1, 20, exhausted=False)]
        assert cen.is_complete_walk(windows) is False
        assert cen.TAIL_NOT_EXHAUSTED in evaluate_closure(windows)["reason_codes"]


class TestTheWatermarkSetsEvidenceNotExitCode:
    """The separation this rung exists for, in both directions.

    A moving source does not make a walk incomplete, and an incomplete walk is
    not rescued by a stable one. Collapsing the three classes into two is how a
    rolling read got published as a snapshot.
    """

    def test_a_stable_watermark_is_a_snapshot(self):
        windows = [_window(0, 1, 20, exhausted=False), _window(20, 25, 30)]
        assert evaluate_closure(windows)["walk_evidence"] == "snapshot"

    def test_drift_is_rolling_and_still_exits_zero(self):
        windows = [
            _window(0, 1, 20, exhausted=False, watermark="w1"),
            _window(20, 25, 30, watermark="w2"),
        ]
        verdict = evaluate_closure(windows)
        assert verdict["walk_evidence"] == "rolling"
        assert verdict["process_exit"] == 0
        assert cen.SOURCE_WATERMARK_DRIFT in verdict["reason_codes"]

    def test_an_absent_watermark_is_rolling_never_snapshot(self):
        verdict = evaluate_closure([_window(0, 1, 20, watermark=None)])
        assert verdict["walk_evidence"] == "rolling"
        assert verdict["process_exit"] == 0
        assert cen.SOURCE_WATERMARK_ABSENT in verdict["reason_codes"]

    def test_a_stable_watermark_does_not_rescue_a_broken_chain(self):
        verdict = evaluate_closure(
            [_window(0, 10, 20, exhausted=False), _window(50, 51, 60)]
        )
        assert verdict["walk_evidence"] == "partial"

    def test_no_watermark_code_is_ever_blocking(self):
        assert cen.SOURCE_WATERMARK_DRIFT not in cen._CLOSURE_BLOCKING
        assert cen.SOURCE_WATERMARK_ABSENT not in cen._CLOSURE_BLOCKING


class TestChronologyAloneAdjudicatesTiming:
    """Density is not evidence about WHEN a quote was taken.

    This is the rung behind downgrading the entertainment stamped-settlement
    rival from REFUTED to UNKNOWN: a 6.58% single-quote share is evidence
    against a *single-quote-only* mechanism and says nothing at all about
    settlement timing, which needs two timestamps.
    """

    def test_no_chronology_is_unknown_not_clean(self):
        assert evaluate_closure([_window(0, 1, 20)])["timing_verdict"] == "unknown"

    def test_a_half_present_chronology_is_unknown(self):
        for chrono in ({"settlement_at": 100}, {"final_quote_at": 99}):
            verdict = evaluate_closure([_window(0, 1, 20)], chronology=chrono)
            assert verdict["timing_verdict"] == "unknown"

    def test_a_quote_before_settlement_is_pre_settlement(self):
        verdict = evaluate_closure(
            [_window(0, 1, 20)], chronology={"settlement_at": 100, "final_quote_at": 99}
        )
        assert verdict["timing_verdict"] == "pre_settlement"

    def test_a_quote_at_or_after_settlement_is_contaminated(self):
        for final in (100, 101):
            verdict = evaluate_closure(
                [_window(0, 1, 20)],
                chronology={"settlement_at": 100, "final_quote_at": final},
            )
            assert verdict["timing_verdict"] == "contaminated"

    def test_density_does_not_enter_the_timing_verdict(self):
        """Passing a density share must not move it — there is no path for it to."""
        base = evaluate_closure([_window(0, 1, 20)])
        assert base["timing_verdict"] == "unknown"
        assert set(base) == {
            "process_exit",
            "walk_evidence",
            "timing_verdict",
            "reason_codes",
        }


class TestTheRailEmitsTheMechanicalFields:
    """The contract cannot be evaluated at all unless the rail records these."""

    @pytest.mark.asyncio
    async def test_a_full_window_carries_cursor_in_and_watermark(self):
        rows = [
            {
                "source": "kalshi",
                "category": "entertainment",
                "volume_state": "absent",
                "density_band": "1",
                "move_band": "0",
                "n": 3,
                "snapshot_rows": 3,
                "observations": 3,
                "moves": 0,
            }
        ]

        class _Session:
            async def execute(self, statement, params=None):
                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {
                                    "lo": 501,
                                    "hi": 900,
                                    "n": 1,
                                    "watermark": 987_654,
                                }

                            def all(self_m):
                                return rows

                        return _M()

                return _R()

        out = await cen.census(_Session(), offset=500)
        assert out["cursor_in"] == 500
        assert out["source_watermark"] == "987654"
        assert out["window"] == {"lo": 501, "hi": 900}

    @pytest.mark.asyncio
    async def test_the_empty_tail_also_carries_them(self):
        """The terminal window is part of the chain; omitting its fields there
        would break closure at exactly the window that proves it closed."""

        class _Session:
            async def execute(self, statement, params=None):
                class _R:
                    def mappings(self_inner):
                        class _M:
                            def first(self_m):
                                return {
                                    "lo": None,
                                    "hi": None,
                                    "n": 0,
                                    "watermark": 987_654,
                                }

                            def all(self_m):  # pragma: no cover - not reached
                                return []

                        return _M()

                return _R()

        out = await cen.census(_Session(), offset=777)
        assert out["cursor_in"] == 777
        assert out["source_watermark"] == "987654"
        assert out["exhausted"] is True

    def test_the_watermark_is_read_in_the_bounds_statement(self):
        """One statement, so the bounds and the watermark describe one instant.

        Read separately they could straddle a write, and the walk would claim a
        table state that never existed.
        """
        assert "watermark" in cen._BOUNDS_SQL
        assert cen._BOUNDS_SQL.count("SELECT MAX(id) FROM futures_outcomes") == 1


class TestTheDriverExitCodeAgreesWithItsBanner:
    """The defect in one sentence: it printed "do not publish this" and exited 0."""

    @staticmethod
    def _write(tmp_path, windows):
        path = tmp_path / "windows.jsonl"
        path.write_text("".join(json.dumps(w) + "\n" for w in windows))
        return str(path)

    def test_a_partial_fold_exits_nonzero(self, tmp_path, capsys):
        from scripts.walk_overlap_census import report

        path = self._write(tmp_path, [_window(0, 1, 20, exhausted=False)])
        assert report(path) == 1
        assert "PARTIAL" in capsys.readouterr().out

    def test_a_broken_chain_exits_nonzero_even_though_the_tail_exhausted(
        self, tmp_path, capsys
    ):
        """The case a tail-only check cannot see, and the reason ``report`` had
        to stop asking ``is_complete_walk`` on its own."""
        from scripts.walk_overlap_census import report

        path = self._write(
            tmp_path, [_window(0, 10, 20, exhausted=False), _window(50, 51, 60)]
        )
        assert report(path) == 1
        assert cen.CURSOR_CHAIN_BROKEN in capsys.readouterr().out

    def test_a_clean_fold_exits_zero_and_names_its_evidence_class(
        self, tmp_path, capsys
    ):
        from scripts.walk_overlap_census import report

        path = self._write(
            tmp_path, [_window(0, 1, 20, exhausted=False), _window(20, 25, 30)]
        )
        assert report(path) == 0
        assert "WALK EVIDENCE: snapshot" in capsys.readouterr().out

    def test_a_rolling_fold_exits_zero_but_says_so(self, tmp_path, capsys):
        from scripts.walk_overlap_census import report

        path = self._write(
            tmp_path,
            [
                _window(0, 1, 20, exhausted=False, watermark="w1"),
                _window(20, 25, 30, watermark="w2"),
            ],
        )
        assert report(path) == 0
        out = capsys.readouterr().out
        assert "WALK EVIDENCE: rolling" in out
        assert "not a snapshot" in out

    def test_main_does_not_discard_the_fold_verdict(self):
        """``report``'s return value was dropped on the floor by ``main``.

        Pinned on source because the alternative is driving a live HTTP walk.
        """
        import inspect

        from scripts import walk_overlap_census

        source = inspect.getsource(walk_overlap_census.main)
        assert "rc_report = report(" in source
        assert "return rc or rc_report" in source
