"""#994 recover-first: DataGolf survivorship fix.

Phase 0g's retags VOID every loser absent from the STORED (often partial)
leaderboard as did_not_play, deleting players who PLAYED and lost → the datagolf
calibration curve floats above the diagonal (survivorship; ops round-85 Q1-Q4
confirmed). The recovery pass fetches the FULL field from the historical API and
reclassifies genuine played-and-lost DNPs back into the curve as real losses
('datagolf_played_lost', NOT voided), keeping true non-participants voided and
symmetrically excluding markets the API can't verify. Guard the structure +
the void-membership contract so the fix can't silently regress.
"""

import importlib
import inspect

# NB: `from app.tasks import backfill_winners` resolves to the celery TASK
# (re-exported in app/tasks/__init__.py), which shadows the module. Import the
# actual submodule explicitly so we can read its functions/constants.
backfill_winners = importlib.import_module("app.tasks.backfill_winners")
from app.tasks import precompute_calibration


class TestPlayedLostReentersCurve:
    """A recovered played-and-lost outcome must COUNT as a real loss — i.e. NOT
    be treated as a calibration void — or the recovery does nothing."""

    def test_played_lost_source_constant(self):
        assert backfill_winners.DATAGOLF_PLAYED_LOST_SOURCE == "datagolf_played_lost"

    def test_played_lost_is_not_void(self):
        assert "datagolf_played_lost" not in precompute_calibration.VOID_RESOLUTION_SOURCES
        assert precompute_calibration.outcome_is_calibration_void(
            "datagolf_played_lost"
        ) is False

    def test_did_not_play_still_void(self):
        # true non-participants must STILL be excluded (blanket-restore undershoots)
        assert precompute_calibration.outcome_is_calibration_void("did_not_play") is True
        assert precompute_calibration.outcome_is_calibration_void("withdrew") is True


class TestRecoveryStructure:
    def _src(self):
        return inspect.getsource(backfill_winners._recover_datagolf_participation)

    def test_recovery_function_exists_and_is_bounded_resumable(self):
        src = self._src()
        # resumable cursor + quota-polite sleep + deadline bound
        assert "bainluck:datagolf_recovery_cursor" in src
        assert "asyncio.sleep(0.5)" in src
        assert "deadline" in src

    def test_recovery_matches_by_dg_id_and_sets_played_lost(self):
        src = self._src()
        assert "get_historical_results(" in src
        # matches the outcome's dg_id (external_id[4:]) against the real field
        assert "SUBSTRING(fo.external_id FROM 4) = ANY(:ids)" in src
        assert "datagolf_played_lost" in src or "DATAGOLF_PLAYED_LOST_SOURCE" in src

    def test_recovery_never_touches_is_winner(self):
        # gotcha #21: recovery only changes resolution_source, never is_winner.
        src = self._src()
        assert "is_winner =" not in src.replace("fo.is_winner = false", "")

    def test_recovery_flags_residual_for_symmetric_exclusion(self):
        src = self._src()
        assert "datagolf_recovery_residual" in src

    def test_recovery_wired_into_pipeline(self):
        # must be CALLED in the main backfill pipeline so it drains each cycle
        main = inspect.getsource(backfill_winners._backfill_all_winners)
        assert "_recover_datagolf_participation(" in main


class TestRetagLeavesRecoveredAlone:
    """retag1 must NOT re-clobber a recovered 'datagolf_played_lost' back to DNP
    on the next cycle (idempotency)."""

    def test_retag1_excludes_played_lost(self):
        mod = inspect.getsource(backfill_winners)
        # the retag1 NOT IN guard must list datagolf_played_lost
        assert "'did_not_play', 'withdrew', 'datagolf_played_lost'" in mod


class TestPrecomputeSymmetricExclusion:
    def test_main_query_excludes_residual_markets(self):
        src = inspect.getsource(precompute_calibration._precompute_calibration_main)
        assert "datagolf_recovery_residual" in src
