"""CAL-P111 — the amended ruling-009 lift condition, pinned as a predicate.

Ruling 009's ORIGINAL clause 2 ("~13 consecutive clean beats") lived only in
prose, and the cost is on the record: it went unsatisfiable for nineteen days,
and the discovery was a side effect of a scorecard built for something else.
The amendment (Alex, MC, 2026-08-28, on #2248) replaced it with **22 of the last
24**, and this suite is the half that stops the replacement rotting the same
way — gotcha #35, one level up from a retention window.

What is pinned, and why each one:

* **The two constants ARE the ruling.** A change to either is an Alex decision,
  so the numbers are asserted literally here rather than read from the module
  and compared to themselves.
* **The definition of "clean".** The ring carries three fields that can
  disagree, and the amendment names ``outcome.published`` as the primary. A
  contradiction between them must read NOT CLEAN — the direction matters,
  because the other direction lifts a freeze on a producer that failed its own
  gate.
* **A short window is not a low score.** ``8/24`` because only eight beats have
  happened since the baseline is not the same fact as ``8/24`` after a full day,
  and collapsing the two is exactly gotcha #53's shape at the level of a
  verdict.
* **The real pre-fix record does NOT satisfy the condition.** This is the
  amendment's central empirical claim — that 22-of-24 is out of reach for the
  producer the freeze exists to exclude — and it is asserted against the
  measured week rather than restated.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "calibration_freeze_score",
    Path(__file__).resolve().parents[1] / "scripts" / "calibration_freeze_score.py",
)
freeze_score = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(freeze_score)


UTC = datetime.timezone.utc
BASE = datetime.datetime(2026, 8, 29, 0, 0, tzinfo=UTC)


def beat(index: int, *, clean: bool = True, at: datetime.datetime | None = None) -> dict:
    stamp = at if at is not None else BASE + datetime.timedelta(hours=index)
    return {
        "generation": str(1_800_000_000_000 + index),
        "generated_at": stamp.isoformat(),
        "terminal": "complete" if clean else "failed",
        "gate": "pass" if clean else "not_evaluated",
        "published": "true" if clean else "false",
    }


def run(pattern: str, **kwargs) -> dict:
    """``pattern`` is the report's own strip notation: ``#`` clean, ``.`` miss."""
    rows = [beat(i, clean=ch == "#") for i, ch in enumerate(pattern)]
    return freeze_score.score(rows, **kwargs)


class TestTheConditionIsTheRuling:
    def test_constants_are_22_of_24(self):
        """Alex ruled these on #2248. Changing either is a ruling, not a tune."""
        assert freeze_score.CLEAN_REQUIRED == 22
        assert freeze_score.WINDOW == 24

    def test_the_two_probabilities_the_amendment_must_state_are_carried(self):
        # The amendment is required to document reachability at BOTH rates, and
        # a reader meeting a 19/24 needs them to know whether it is bad luck.
        assert freeze_score.P_AT_BROKEN_RATE == pytest.approx(5.6e-6, rel=0.02)
        assert freeze_score.P_AT_HEALTHY_RATE == pytest.approx(0.884, rel=0.02)

    def test_exactly_22_clean_meets_it_and_21_does_not(self):
        assert run("#" * 22 + "..")["verdict"] == "CONDITION_MET"
        assert run("#" * 21 + "...")["verdict"] == "NOT_MET"

    def test_misses_are_budgeted_not_ordered(self):
        """The whole point of the shape change: WHERE the misses fall is irrelevant."""
        assert run("." + "#" * 22 + ".")["verdict"] == "CONDITION_MET"
        assert run("#" * 11 + ".." + "#" * 11)["verdict"] == "CONDITION_MET"
        # ...and a streak that would have satisfied the OLD clause does not
        # satisfy this one, which is the direction that matters: the amendment
        # is stricter against the broken producer, not looser.
        assert run("#" * 13 + "." * 11)["verdict"] == "NOT_MET"


class TestCleanIsTheProducersOwnVerdict:
    def test_published_true_with_a_passing_gate_is_clean(self):
        assert freeze_score.is_clean(beat(0, clean=True))

    @pytest.mark.parametrize(
        "override",
        [
            {"published": "false"},
            {"terminal": "cancelled"},
            {"gate": "not_evaluated"},
            {"gate": "refuse"},
        ],
    )
    def test_any_disagreement_reads_not_clean(self, override):
        """A contradiction in the producer's own ledger is NOT a clean beat.

        The other direction would lift a freeze on a producer that failed its
        own publish gate, which is the one outcome this condition exists to
        prevent.
        """
        row = beat(0, clean=True) | override
        assert not freeze_score.is_clean(row)

    def test_a_cancelled_beat_is_a_miss_whatever_caused_it(self):
        # No beat is excused. A deploy of an unrelated service that costs a
        # beat is charged to the budget — that is what a budget is.
        rows = [beat(i) for i in range(24)]
        rows[5]["terminal"] = "cancelled"
        rows[5]["published"] = "false"
        rows[5]["gate"] = "not_evaluated"
        assert freeze_score.score(rows)["clean"] == 23


class TestAShortWindowIsNotALowScore:
    def test_eight_post_baseline_beats_report_window_not_full(self):
        result = run("#" * 8)
        assert result["verdict"] == "WINDOW_NOT_FULL"
        assert result["beats_in_window"] == 8
        # A perfect-so-far window must never read as a failing one.
        assert result["clean"] == 8

    def test_a_filling_window_reports_what_is_still_reachable(self):
        result = run("#" * 6 + "..")
        assert result["verdict"] == "WINDOW_NOT_FULL"
        # 6 clean + 16 beats still to come = 22, still exactly reachable.
        assert result["reachable_if_all_remaining_clean"] == 22

    def test_a_full_window_reports_no_reachability_number(self):
        # Under a rolling window it would always be 24 and therefore say nothing.
        assert run("#" * 24)["reachable_if_all_remaining_clean"] is None

    def test_a_filling_window_is_scored_against_the_beats_that_exist(self):
        """`4/24` and `4/6` are different facts and may not share a denominator.

        A filling window printed against 24 reads as a catastrophic producer
        when it means "it is early" — the same collapse the WINDOW_NOT_FULL
        verdict exists to prevent, arriving through the headline instead.
        """
        text = freeze_score.render(run("..####"))
        assert "4/6 clean so far (window 24)" in text
        assert "4/24" not in text
        # ...and a FULL window still reads against 24.
        assert "22/24 clean" in freeze_score.render(run("#" * 22 + ".."))


class TestTheBaselineExcludesPreFixBeats:
    def test_pre_baseline_beats_are_excluded_and_counted(self):
        pre = [beat(i, clean=True, at=BASE - datetime.timedelta(hours=30 - i)) for i in range(6)]
        post = [beat(100 + i, clean=True) for i in range(24)]
        result = freeze_score.score(pre + post, baseline=BASE)
        assert result["excluded_pre_baseline"] == 6
        assert result["beats_in_window"] == 24
        assert result["verdict"] == "CONDITION_MET"

    def test_a_clean_pre_fix_run_cannot_lift_the_freeze(self):
        """The baseline is the load-bearing half of the amendment.

        Without it, the 24 beats already sitting in the ring from before the
        producer repair would be scored — and a lucky pre-fix day would lift a
        freeze on a producer that had not been fixed.
        """
        pre = [beat(i, clean=True, at=BASE - datetime.timedelta(hours=24 - i)) for i in range(24)]
        assert freeze_score.score(pre, baseline=BASE)["verdict"] == "WINDOW_NOT_FULL"
        # ...and the same rows with no baseline DO satisfy it, which is why the
        # report shouts when --baseline-at is absent.
        assert freeze_score.score(pre)["verdict"] == "CONDITION_MET"


class TestAgainstTheMeasuredPreFixWeek:
    """The amendment's central empirical claim, asserted rather than restated.

    This is the real 166-beat publish sequence from
    ``calibration:beat_gauge_history``, 2026-08-21T18:37Z -> 2026-08-28T15:34Z,
    read on 2026-08-28: 79 clean of 166, per-beat publish rate 0.476, longest
    clean run 9, best 24-beat window 19/24.
    """

    RECORD = (
        ".1.11..11..11.1.11.11111"
        ".1.11..11111111.11..1111"
        "1.1111.11.11............"
        "...................111.1"
        "...............111111111"
        ".1.111.1111..1111111.11."
        ".....1..1.1...1.1..111"
    )

    def _rows(self):
        return [beat(i, clean=ch == "1") for i, ch in enumerate(self.RECORD)]

    def test_the_record_is_the_one_that_was_measured(self):
        assert len(self.RECORD) == 166
        assert self.RECORD.count("1") == 79

    def test_no_24_beat_window_in_the_pre_fix_week_reaches_22(self):
        """22-of-24 is out of reach for the producer the freeze excludes."""
        flags = [ch == "1" for ch in self.RECORD]
        best = max(
            sum(flags[i:i + freeze_score.WINDOW])
            for i in range(len(flags) - freeze_score.WINDOW + 1)
        )
        assert best == 19
        assert best < freeze_score.CLEAN_REQUIRED

    def test_21_of_24_would_have_been_within_reach_and_22_is_not(self):
        """Why 22 and not 21 — the margin is empirical, not aesthetic.

        The best measured window is 19, so 21 clears it by two and 22 by three.
        The bootstrap that decided between them is in the ruling; what a test
        can pin is that the chosen threshold is the stricter of the pair.
        """
        assert freeze_score.CLEAN_REQUIRED > 21

    def test_scoring_the_tail_of_the_real_record_reads_not_met(self):
        result = freeze_score.score(self._rows())
        assert result["verdict"] == "NOT_MET"
        assert result["beats_in_window"] == 24
        assert result["ring_observations"] == 166


class TestTheReportSaysWhatItMeasured:
    def test_the_strip_is_readable_and_ordered_oldest_first(self):
        text = freeze_score.render(run("#" * 22 + ".."))
        assert "#" * 22 + ".." in text
        assert "oldest ... newest" in text

    def test_a_met_condition_still_says_the_freeze_is_not_lifted(self):
        """Ruling 009 is not lifted by a script and not by a lane's judgment."""
        text = freeze_score.render(run("#" * 24, baseline=BASE - datetime.timedelta(days=1)))
        assert "CONDITION_MET" in text
        assert "freeze is NOT yet lifted" in text
        assert "WRITES THE NUMBERS INTO THE CALIBRATION" in text

    def test_a_missing_baseline_is_shouted_not_assumed(self):
        text = freeze_score.render(run("#" * 24))
        assert "NO --baseline-at GIVEN" in text
        assert "not a verdict on the freeze" in text
