"""OPS-137 / #805-adjacent: the ESPN box-score backfill must correct finished
games stuck at a 0-0 placeholder using the authoritative ESPN final, while
leaving postponed/scoreless games and real non-zero scores untouched.

Verified vs ESPN during Batch 0 (Lane 2 L2-14):
  espn 401815890 = STL 4 - ARI 9  (we stored 0-0)  -> fix
  espn 401815887 = WSH 4 - PHI 5  (we stored 0-0)  -> fix
  espn 401815854 = STATUS_POSTPONED 0-0            -> leave alone
"""

from app.tasks.espn_sync import _corrected_final_score


class TestCorrectedFinalScore:
    def test_corrects_zero_zero_placeholder_to_espn_final(self):
        # The bug: finished game stuck at 0-0, ESPN has the real final.
        assert _corrected_final_score(0, 0, 4, 9) == (4, 9)
        assert _corrected_final_score(0, 0, 4, 5) == (4, 5)

    def test_fills_missing_score(self):
        assert _corrected_final_score(None, None, 4, 5) == (4, 5)

    def test_low_scoring_final_still_written(self):
        assert _corrected_final_score(0, 0, 1, 0) == (1, 0)

    def test_postponed_or_scoreless_left_untouched(self):
        # ESPN total 0 (postponed / not played) -> never invent a score.
        assert _corrected_final_score(0, 0, 0, 0) is None
        assert _corrected_final_score(None, None, 0, 0) is None

    def test_never_overwrites_a_real_score(self):
        # gotcha #21: a real non-zero stored score is never clobbered.
        assert _corrected_final_score(3, 2, 5, 4) is None
        assert _corrected_final_score(1, 0, 9, 9) is None

    def test_no_espn_data_is_noop(self):
        assert _corrected_final_score(0, 0, None, None) is None
