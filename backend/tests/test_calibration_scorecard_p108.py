"""CAL-P108 — the published-curve scorecard, pinned where it can silently lie.

The scorecard reads the SERVED payload, so it cannot drift from the published
population the way a DB-direct rail can. What it CAN do is fold those rows
wrongly, and one particular wrong fold is both easy to write and invisible in
the output: it produces a plausible number for every cell, all of them high.

So the first test class proves the specimens SEPARATE the two folds before any
other test uses them (the CAL-P105 lesson — a pin whose fixture returns the same
number under every treatment is green for reasons unrelated to its claim).
"""

from __future__ import annotations

import json

import pytest

from scripts.calibration_scorecard import (
    BAR_PP,
    CLASS_A,
    CLASS_B,
    CLASS_BARS_PP,
    CLASS_C,
    MIN_CELL_N,
    SIGMA_GATE,
    VERDICT_EXEMPT,
    VERDICT_PASS,
    VERDICT_QUEUED,
    VERDICT_UNDER_SIGMA,
    bar_for,
    fold,
    needle,
    record,
    score,
    self_check,
)


def _bucket(source, category, idx, n, winners, avg_prob, price_moved=False):
    return {
        "bucket_idx": idx,
        "source": source,
        "category": category,
        "price_moved": price_moved,
        "n": n,
        "winners": winners,
        "avg_prob": avg_prob,
        "sum_prob": n * avg_prob,
    }


#: One category, one bucket index, two strata whose errors point OPPOSITE ways
#: and cancel exactly when pooled. Pooled ECE is 0.0; folded per-row it is 10.0.
#: This is the whole defect, in four numbers.
CANCELLING_BUCKETS = [
    _bucket("kalshi", "widgets", 5, 100, 60, 0.50, price_moved=False),
    _bucket("kalshi", "widgets", 5, 100, 40, 0.50, price_moved=True),
]


class TestTheSpecimensCanTellTheFoldsApart:
    def test_pooled_and_unpooled_folds_disagree_on_this_fixture(self):
        """If these coincide, every test below proves nothing."""
        pooled = fold({"buckets": CANCELLING_BUCKETS}, ("category",))[0]["ece"]
        unpooled = sum(
            abs(b["winners"] / b["n"] - b["avg_prob"]) * b["n"]
            for b in CANCELLING_BUCKETS
        ) / sum(b["n"] for b in CANCELLING_BUCKETS) * 100
        assert pooled == pytest.approx(0.0, abs=0.01)
        assert unpooled == pytest.approx(10.0, abs=0.01)
        assert pooled != pytest.approx(unpooled, abs=1.0)


class TestTheFoldPoolsToTenBins:
    def test_opposing_strata_in_one_bin_cancel(self):
        cells = fold({"buckets": CANCELLING_BUCKETS}, ("category",))
        assert len(cells) == 1
        assert cells[0]["ece"] == pytest.approx(0.0, abs=0.01)
        assert cells[0]["n"] == 200

    def test_gap_is_signed_and_ece_is_not(self):
        """Two cells at the same ECE, wrong in opposite directions.

        A table that prints only ECE cannot tell an over-predicting cell from an
        under-predicting one, and they are different defects.
        """
        over = fold(
            {"buckets": [_bucket("k", "a", 5, 100, 40, 0.50)]}, ("category",)
        )[0]
        under = fold(
            {"buckets": [_bucket("k", "b", 5, 100, 60, 0.50)]}, ("category",)
        )[0]
        assert over["ece"] == under["ece"] == pytest.approx(10.0, abs=0.01)
        assert over["gap"] == pytest.approx(10.0, abs=0.01)
        assert under["gap"] == pytest.approx(-10.0, abs=0.01)


class TestSelfCheckIsTheWarrant:
    def _payload(self, by_category_ece):
        return {
            "buckets": CANCELLING_BUCKETS,
            "by_category": [{"category": "widgets", "ece": by_category_ece, "n": 200}],
            "by_source": [{"source": "kalshi", "ece": by_category_ece, "n": 200}],
        }

    def test_agrees_with_a_consistent_payload(self):
        assert self_check(self._payload(0.0))["ok"] is True

    def test_reds_when_the_payload_disagrees(self):
        """Red-first: the unpooled answer (10.0) must NOT pass the self-check."""
        report = self_check(self._payload(10.0))
        assert report["ok"] is False
        assert report["checks"][0]["mismatches"]

    def test_reds_when_n_disagrees_even_though_ece_matches(self):
        """An ECE that matches on a different row count is a coincidence."""
        payload = self._payload(0.0)
        payload["by_category"][0]["n"] = 999
        assert self_check(payload)["ok"] is False

    def test_reds_when_a_published_cell_is_absent_from_buckets(self):
        payload = self._payload(0.0)
        payload["by_category"].append({"category": "ghost", "ece": 1.0, "n": 10})
        report = self_check(payload)
        assert report["ok"] is False
        assert any(
            m.get("reason") == "absent_from_buckets"
            for m in report["checks"][0]["mismatches"]
        )

    def test_empty_payload_is_not_a_pass(self):
        """No cells compared must never read as agreement (gotcha #53)."""
        assert self_check({"buckets": [], "by_category": [], "by_source": []})["ok"] is False


class TestVerdicts:
    def _score_one(self, n, ece_pp):
        """One cell of size n whose pooled ECE is ece_pp, by construction."""
        winners = int(round(n * (0.5 - ece_pp / 100)))
        return score(
            {
                "buckets": [_bucket("kalshi", "c", 5, n, winners, 0.50)],
                "mce_closing_line": 1.0,
            }
        )["cells"][0]

    def test_small_cell_is_exempt_not_queued_however_bad(self):
        cell = self._score_one(MIN_CELL_N - 1, 40.0)
        assert cell["verdict"] == VERDICT_EXEMPT

    def test_under_bar_passes(self):
        assert self._score_one(50_000, BAR_PP - 1.0)["verdict"] == VERDICT_PASS

    def test_over_bar_but_within_noise_is_not_queued(self):
        """Distinct from EXEMPT on purpose: big enough to matter, too noisy to act."""
        # n=1000 -> SE = 50/sqrt(1000) = 1.58 pp; +1.0 pp excess is 0.63 sigma.
        cell = self._score_one(MIN_CELL_N, BAR_PP + 1.0)
        assert cell["sigma"] < SIGMA_GATE
        assert cell["verdict"] == VERDICT_UNDER_SIGMA

    def test_over_bar_and_established_is_queued(self):
        cell = self._score_one(50_000, BAR_PP + 2.0)
        assert cell["sigma"] >= SIGMA_GATE
        assert cell["verdict"] == VERDICT_QUEUED
        assert cell["excess_outcomes"] == pytest.approx(2.0 * 50_000, rel=0.02)


class TestTheBarIsPerCohort:
    """CAL-P115 — Alex ratified A 2.5 / B 3.0 / C 3.0 by MC on 2026-08-28, and
    this is where the ratification is actually LIVE. ``score()`` is what renders
    the page, so a test that only exercises the side-by-side renderer in
    ``calibration_threshold_table.py`` would have stayed green through the whole
    day this repo spent ratified-in-prose and rendering the old bar.
    """

    def _score_one(self, source, category, n, ece_pp):
        winners = int(round(n * (0.5 - ece_pp / 100)))
        return score(
            {
                "buckets": [_bucket(source, category, 5, n, winners, 0.50)],
                "mce_closing_line": 1.0,
            }
        )["cells"][0]

    def test_the_ratified_bars_are_the_numbers_alex_ruled(self):
        """A ratified threshold a lane can move without a second MC is not
        ratified. Changing one requires deleting this line."""
        assert CLASS_BARS_PP == {CLASS_A: 2.5, CLASS_B: 3.0, CLASS_C: 3.0}

    def test_bar_for_is_structural_not_numeric(self):
        # odds_api* is class A whatever the sport — the class is about how the
        # PRICE is formed, so a cell can never drift class as its numbers move.
        assert bar_for("odds_api_bookmaker", "icehockey_nhl") == 2.5
        assert bar_for("odds_api_totals", "baseball_mlb") == 2.5
        assert bar_for("kalshi", "football") == BAR_PP        # exchange, contest
        assert bar_for("polymarket", "politics") == BAR_PP    # exchange, standalone

    def test_the_same_ece_is_queued_in_class_A_and_passes_in_class_C(self):
        """RED-first, and the whole decision in two rows.

        2.8 pp sits BETWEEN the two bars: +0.3 over class A, −0.2 under the
        reader bar. n is 150,000 because the sigma gate is not suspended for
        this test — a 0.3 pp excess only clears 2σ at that size (2.32σ), and a
        specimen that failed the gate instead of the bar would prove nothing
        about which bar was applied. If these two ever return the same verdict,
        the ratification has been un-wired and the page is back to a flat bar
        under a per-cohort headline."""
        a = self._score_one("odds_api_bookmaker", "icehockey_nhl", 150_000, 2.8)
        c = self._score_one("polymarket", "politics", 150_000, 2.8)
        assert a["bar_pp"] == 2.5 and a["verdict"] == VERDICT_QUEUED
        assert c["bar_pp"] == 3.0 and c["verdict"] == VERDICT_PASS

    def test_each_cell_carries_the_bar_that_judged_it(self):
        """A queued row that prints only its excess cannot be checked without
        knowing which of three bars produced it."""
        cell = self._score_one("odds_api", "basketball_nba", 50_000, 5.0)
        assert cell["class"] == CLASS_A
        assert cell["bar_pp"] == 2.5
        assert cell["excess_pp"] == pytest.approx(2.5, abs=0.05)

    def test_thresholds_no_longer_publish_a_single_bar_pp(self):
        """Removed rather than repointed. A consumer still reading
        ``thresholds['bar_pp']`` would now be reading one of three bars as
        though it were the bar — a silently-wrong threshold, where a KeyError
        is a story someone has to read (gotcha #53)."""
        thresholds = score(
            {"buckets": CANCELLING_BUCKETS, "mce_closing_line": 1.0}
        )["thresholds"]
        assert "bar_pp" not in thresholds
        assert thresholds["class_bars_pp"] == CLASS_BARS_PP
        assert thresholds["reader_bar_pp"] == BAR_PP

    def test_cells_at_bar_is_material_minus_queued(self):
        """The NEEDLE numerator and the DONE verdict must come off the same
        count, or Fable copies a number the page disagrees with."""
        result = score(
            {
                # 2.8 pp each — between the two bars, at 2.32 sigma.
                "buckets": [
                    _bucket("odds_api_bookmaker", "icehockey_nhl", 5, 150_000, 70_800, 0.50),
                    _bucket("polymarket", "politics", 5, 150_000, 70_800, 0.50),
                ],
                "mce_closing_line": 1.0,
            }
        )
        c = result["counts"]
        assert c["cells_material"] == 2
        assert c["cells_queued"] == 1
        assert c["cells_at_bar"] == 1
        assert needle(result).startswith("NEEDLE: calibration 1/2 cells-at-bar @ ")

    def test_per_class_breakdown_partitions_the_material_cells(self):
        result = score(
            {
                "buckets": [
                    _bucket("odds_api", "basketball_nba", 5, 20_000, 9_500, 0.50),
                    _bucket("kalshi", "football", 5, 20_000, 9_500, 0.50),
                    _bucket("kalshi", "tech", 5, 20_000, 9_500, 0.50),
                    _bucket("kalshi", "tiny", 5, 100, 47, 0.50),  # exempt
                ],
                "mce_closing_line": 1.0,
            }
        )
        per_class = result["per_class"]
        assert sum(p["cells"] for p in per_class.values()) == 3
        assert sum(p["at_bar"] + p["queued"] for p in per_class.values()) == 3
        assert per_class[CLASS_A]["bar_pp"] == 2.5
        assert per_class[CLASS_A]["outcomes"] == 20_000


class TestDoneVerdict:
    def test_not_done_while_a_cell_is_queued(self):
        result = score(
            {
                "buckets": [_bucket("kalshi", "c", 5, 50_000, 22_500, 0.50)],
                "mce_closing_line": 1.0,
            }
        )
        assert result["counts"]["cells_queued"] == 1
        assert result["done"] is False

    def test_not_done_on_a_passing_headline_alone(self):
        """The headline passing must never carry the verdict by itself.

        This is the §2 finding as a guard: a pooled average over cancelling
        cells can sit under target while cells are badly wrong.
        """
        result = score(
            {
                "buckets": [
                    _bucket("kalshi", "over", 5, 50_000, 20_000, 0.50),
                    _bucket("kalshi", "under", 5, 50_000, 30_000, 0.50),
                ],
                "mce_closing_line": 0.0,
            }
        )
        assert result["headline_pass"] is True
        assert result["counts"]["cells_queued"] == 2
        assert result["done"] is False


class TestHistoryCannotFakeATrend:
    def _result(self, generated_at):
        result = score(
            {
                "buckets": [_bucket("kalshi", "c", 5, 50_000, 22_500, 0.50)],
                "mce_closing_line": 1.0,
            }
        )
        result["generated_at"] = generated_at
        return result

    def test_same_curve_recorded_twice_banks_once(self, tmp_path):
        """The producer stalls; re-running must not mint a second datapoint.

        On 2026-08-20 fourteen hourly samples carried one ``generated_at``.
        Keyed on the wall clock, that is a fourteen-point flat trend line drawn
        out of a single measurement.
        """
        path = tmp_path / "history.jsonl"
        assert record(self._result("2026-08-27T16:33:50Z"), path) == "recorded"
        assert (
            record(self._result("2026-08-27T16:33:50Z"), path)
            == "duplicate_curve_generated_at"
        )
        assert len(path.read_text().strip().splitlines()) == 1

    def test_a_new_curve_banks_a_new_point(self, tmp_path):
        path = tmp_path / "history.jsonl"
        record(self._result("2026-08-27T16:33:50Z"), path)
        assert record(self._result("2026-08-27T17:33:50Z"), path) == "recorded"
        assert len(path.read_text().strip().splitlines()) == 2

    def test_the_same_curve_at_a_NEW_bar_banks_a_new_point(self, tmp_path):
        """The one case the stall guard must NOT swallow.

        2026-08-28's `20:37Z` curve was banked at the flat 3.0 pp bar hours
        before Alex's ratification was wired. Keyed on the curve alone, the
        ratified re-score of that same curve — the needle series' FIRST point —
        would have been silently refused as a duplicate, and the series would
        have opened at a number nothing in the file could explain."""
        path = tmp_path / "history.jsonl"
        flat = self._result("2026-08-28T20:37:41Z")
        flat["thresholds"] = dict(flat["thresholds"], class_bars_pp={
            CLASS_A: 3.0, CLASS_B: 3.0, CLASS_C: 3.0
        })
        assert record(flat, path) == "recorded"
        assert record(self._result("2026-08-28T20:37:41Z"), path) == "recorded"
        assert len(path.read_text().strip().splitlines()) == 2
        # ...and the stall guard is untouched: same curve AND same bars.
        assert (
            record(self._result("2026-08-28T20:37:41Z"), path)
            == "duplicate_curve_generated_at"
        )

    def test_a_pre_ratification_line_is_keyed_as_the_flat_bar_it_used(self, tmp_path):
        """The six points already in ``history.jsonl`` carry no ``thresholds``
        key — they predate it. They must read as the flat bar they were actually
        scored against, so a ratified re-score of the same curve is a new point
        and a flat re-score of it is still a duplicate."""
        path = tmp_path / "history.jsonl"
        path.write_text(
            json.dumps({
                "generated_at": "2026-08-27T16:33:50Z",
                "counts": {"cells_material": 49, "cells_queued": 19},
            })
            + "\n"
        )
        # ratified re-score of that curve: a NEW reading, banked
        assert record(self._result("2026-08-27T16:33:50Z"), path) == "recorded"
        # a FLAT re-score of it is still the stalled-producer duplicate
        flat = self._result("2026-08-27T16:33:50Z")
        flat["thresholds"] = dict(flat["thresholds"], class_bars_pp={
            CLASS_A: 3.0, CLASS_B: 3.0, CLASS_C: 3.0
        })
        assert record(flat, path) == "duplicate_curve_generated_at"

    def test_banked_point_says_which_bar_scored_it(self, tmp_path):
        """The series changes DEFINITION on 2026-08-28: points before the
        ratification were scored at a flat 3.0, points after at 2.5/3.0/3.0.

        A trend line drawn across a threshold change that its own datapoints
        cannot describe is a chart lying about its units — the same failure as
        the wall-clock keying above, one level up."""
        path = tmp_path / "history.jsonl"
        record(self._result("2026-08-28T20:37:41Z"), path)
        banked = json.loads(path.read_text().strip())
        assert banked["thresholds"]["class_bars_pp"] == CLASS_BARS_PP
        assert banked["counts"]["cells_at_bar"] is not None

    def test_banked_point_carries_material_cells_only(self, tmp_path):
        path = tmp_path / "history.jsonl"
        result = self._result("2026-08-27T16:33:50Z")
        result["cells"].append(
            {
                "cell": "kalshi/tiny",
                "ece": 40.0,
                "n": 5,
                "verdict": VERDICT_EXEMPT,
                "excess_outcomes": 0,
            }
        )
        record(result, path)
        banked = json.loads(path.read_text().strip())
        assert "kalshi/tiny" not in banked["material_cells"]
        assert "kalshi/c" in banked["material_cells"]
