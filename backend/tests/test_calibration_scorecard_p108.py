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
    MIN_CELL_N,
    SIGMA_GATE,
    VERDICT_EXEMPT,
    VERDICT_PASS,
    VERDICT_QUEUED,
    VERDICT_UNDER_SIGMA,
    fold,
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
