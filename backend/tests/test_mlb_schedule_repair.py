"""#239 Item 2 / #1201/#1193 — MLB inverted-row repair classification.

Guards the pure decision boundary that routes a SCORED inverted MLB row (settled
but violating ``completed_at >= commence_time``, gotcha #32/#46) to the right
ground-truth-gated repair: re-date commence, fix the corrupt completed_at, or
skip as ambiguous. No DB / MLB service needed — these are pure-logic assertions."""

from datetime import datetime, timedelta, timezone

from app.tasks.schedule_coverage import (
    _classify_scored_inverted,
    _repair_as_utc,
    _repair_teams_match,
)

_UTC = timezone.utc


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=_UTC)


class TestClassifyScoredInverted:
    def test_commence_wrong_redate(self):
        # completed_at is a real post-game time; the Final started before it, so the
        # future commence is the wrong field -> re-date commence.
        completed = _dt(2026, 7, 18, 20, 0)
        commence = _dt(2026, 7, 20, 17, 10)  # future / wrong
        new_start = _dt(2026, 7, 18, 17, 10)
        assert _classify_scored_inverted(completed, commence, new_start) == "redate"

    def test_completed_at_wrong_fix_end(self):
        # The real-world standing class (event 15020436): commence matches the
        # confirmed Final start exactly; completed_at was set ~12h BEFORE first
        # pitch -> completed_at is the corrupt field, fix it.
        completed = _dt(2026, 7, 18, 4, 40)   # pre-first-pitch (corrupt)
        commence = _dt(2026, 7, 18, 17, 10)   # correct
        new_start = _dt(2026, 7, 18, 17, 10)  # MLB-confirmed
        assert _classify_scored_inverted(completed, commence, new_start) == "fix_end"

    def test_null_completed_at_redate(self):
        # future-settled with no completed_at -> re-date commence to the real start.
        commence = _dt(2026, 7, 25, 17, 10)  # future
        new_start = _dt(2026, 7, 18, 17, 10)
        assert _classify_scored_inverted(None, commence, new_start) == "redate"

    def test_ambiguous_review(self):
        # Final start is after completed_at AND far from commence -> unsafe, review.
        completed = _dt(2026, 7, 18, 4, 40)
        commence = _dt(2026, 7, 10, 17, 10)  # >6h from the Final start
        new_start = _dt(2026, 7, 18, 17, 10)
        assert _classify_scored_inverted(completed, commence, new_start) == "review"

    def test_fix_end_tolerance_boundary(self):
        # commence within the 6h tolerance of the confirmed start still -> fix_end.
        commence = _dt(2026, 7, 18, 12, 0)
        new_start = _dt(2026, 7, 18, 17, 10)  # 5h10m later, inside 6h
        completed = _dt(2026, 7, 18, 4, 40)
        assert _classify_scored_inverted(completed, commence, new_start) == "fix_end"


class TestRepairHelpers:
    def test_teams_match_either_orientation(self):
        assert _repair_teams_match("Cleveland Guardians", "Pittsburgh Pirates",
                                   "Cleveland Guardians", "Pittsburgh Pirates")
        # home/away swapped in our row still matches.
        assert _repair_teams_match("Pittsburgh Pirates", "Cleveland Guardians",
                                   "Cleveland Guardians", "Pittsburgh Pirates")
        assert not _repair_teams_match("New York Yankees", "Boston Red Sox",
                                       "Cleveland Guardians", "Pittsburgh Pirates")

    def test_as_utc_coerces_naive(self):
        naive = datetime(2026, 7, 18, 17, 10)
        assert _repair_as_utc(naive).tzinfo == _UTC
        aware = datetime(2026, 7, 18, 17, 10, tzinfo=_UTC)
        assert _repair_as_utc(aware) == aware
