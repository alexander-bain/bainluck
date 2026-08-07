"""CAL-P002: a settled event's stored score MUST be the game's final score.

The forensic anchor (2026-08-05, identity-verified against ESPN finals):

    ev12080400  NHL   we stored BOS 3-1 MIN  · ESPN final BOS 6-3   (frozen mid-game)
    ev12080353  NBA   we stored MIN 45-56 DET · ESPN final 87-109   (a HALFTIME score)
    ev15182558  MLB   we stored SF 2-8 MIL   · ESPN final SF 16-3   (7/28's final on
                                                                     the 7/29 game)

Measured defect rates over identity-verified samples:
    closed  · NHL/NBA/MLB/WNBA   10/399 =  2.5%
    closed  · NCAA Baseball      43/388 = 11.1%
    completed · major 2-9d old   19/70  = 27.1%
    completed · major 30-60d     43/199 = 21.6%

This suite pins the two pure predicates and the sentinel detector. It is the
deliberate counterpart to ``test_espn_score_correction.py`` — see
``TestAuthorityBoundaryWithCorrectedFinalScore`` for why the two rules coexist.
"""

import pytest

from app.tasks.flow_sentinel import frozen_final_score_events
from scripts.repair_event_final_scores import (
    _identity_matches,
    espn_date_matches,
    resolved_home_from_score,
    score_is_stale,
)


class TestScoreIsStale:
    def test_frozen_mid_game_score_is_a_defect(self):
        # The BOS 3-1 / 6-3 anchor: a REAL, plausible, non-zero stored score that
        # is simply not the final. This is the case no existing rail could see.
        assert score_is_stale(3, 1, 6, 3, True) is True

    def test_halftime_score_is_a_defect(self):
        assert score_is_stale(45, 56, 87, 109, True) is True

    def test_wrong_game_from_same_series_is_a_defect(self):
        # ev15182558 held the neighbouring 7/28 game's final.
        assert score_is_stale(2, 8, 16, 3, True) is True

    def test_zero_zero_placeholder_is_a_defect(self):
        assert score_is_stale(0, 0, 9, 6, True) is True

    def test_matching_final_is_not_a_defect(self):
        # The overwhelming majority. Repair must be a no-op here (idempotence).
        assert score_is_stale(5, 4, 5, 4, True) is False
        assert score_is_stale(0, 0, 0, 0, True) is False

    def test_non_final_espn_reading_is_never_a_defect(self):
        # #980/#981: writing a non-final ESPN score is the original corruption.
        # An in-progress ESPN game can NEVER justify a write, however different.
        assert score_is_stale(3, 1, 6, 3, False) is False
        assert score_is_stale(0, 0, 9, 6, False) is False

    def test_missing_scores_are_not_a_defect(self):
        assert score_is_stale(3, 1, None, None, True) is False
        assert score_is_stale(3, 1, 6, None, True) is False
        assert score_is_stale(None, None, 6, 3, True) is False


class TestAuthorityBoundaryWithCorrectedFinalScore:
    """Why this repair may overwrite a real score when ``_corrected_final_score``
    may not — the two rules are complementary, not contradictory.

    ``_corrected_final_score`` runs UNATTENDED inside the box-score backfill on
    events of any age and freshness, so it takes the conservative branch of gotcha
    #21: only a 0-0 placeholder is safe to overwrite without a human in the loop.
    That left the larger half of the defect structurally uncorrectable — CAL-P002
    measured 2.5-27% of settled events holding a wrong, NON-zero final.

    This repair earns the wider authority with three constraints the backfill does
    not have: it is ATTENDED (dry-run first, explicit ``apply=true``), it writes
    only on an ESPN FINAL, and it writes only after a team-identity check proves
    the ESPN row describes the same fixture."""

    def test_corrected_final_score_still_refuses_real_scores(self):
        from app.tasks.espn_sync import _corrected_final_score

        # Unchanged: the unattended rail stays conservative.
        assert _corrected_final_score(3, 2, 5, 4) is None

    def test_this_repair_flags_exactly_what_the_backfill_cannot(self):
        from app.tasks.espn_sync import _corrected_final_score

        assert _corrected_final_score(3, 1, 6, 3) is None  # invisible to the backfill
        assert score_is_stale(3, 1, 6, 3, True) is True    # visible here

    def test_both_agree_a_non_final_is_untouchable(self):
        from app.tasks.espn_sync import _corrected_final_score

        assert _corrected_final_score(0, 0, 6, 3, espn_is_final=False) is None
        assert score_is_stale(0, 0, 6, 3, False) is False


class TestIdentityGuard:
    """An ``espn_id`` pointing at a different game must BLOCK the write. The census
    found 3 such NCAA-Baseball rows; repairing off them would import a wrong score
    rather than remove one (that is an espn_id linkage defect, a different repair)."""

    def test_same_fixture_passes(self):
        assert _identity_matches(
            "Boston Bruins", "Minnesota Wild", "Boston Bruins", "Minnesota Wild"
        ) is True

    def test_partial_names_still_match(self):
        assert _identity_matches(
            "Boston Bruins", "Minnesota Wild", "Bruins", "Wild"
        ) is True

    def test_different_game_is_blocked(self):
        # ev12256979: ours California Baptist vs St. John's; espn_id pointed at
        # Dallas Baptist vs Oklahoma State.
        assert _identity_matches(
            "California Baptist", "St. John's",
            "Dallas Baptist Patriots", "Oklahoma State Cowboys",
        ) is False

    def test_swapped_home_away_is_blocked(self):
        # A swapped fixture is an orientation defect, not a score defect — writing
        # ESPN's home/away onto our reversed row would silently invert the game.
        assert _identity_matches(
            "West Virginia", "Penn State",
            "Penn State Nittany Lions", "West Virginia Mountaineers",
        ) is False

    def test_missing_espn_names_block(self):
        assert _identity_matches("Boston Bruins", "Minnesota Wild", "", "") is False


class TestEspnDateGuard:
    """The guard team-identity cannot provide. In a playoff series the same two
    teams meet repeatedly, so identity passes on EVERY game of the series.

    A simulated repair that trusted identity alone imported neighbouring games'
    finals and RAISED the KXNHLSPREAD disagreement count 8 -> 14. These are the
    exact production rows that regression came from."""

    def _et(self, s):
        from datetime import datetime, timezone

        return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)

    def test_same_day_game_passes(self):
        from datetime import date

        # 2026-03-28 21:00Z == 17:00 ET on 03-28.
        assert espn_date_matches(date(2026, 3, 28), self._et("2026-03-28T21:00:00")) is True

    def test_late_night_utc_rolls_back_to_prior_et_day(self):
        from datetime import date

        # 2026-04-30 02:00Z == 22:00 ET on 04-29 — a 7pm PT start. Our game_date is
        # computed on the same ET basis, so this must MATCH, not block.
        assert espn_date_matches(date(2026, 4, 29), self._et("2026-04-30T02:00:00")) is True

    @pytest.mark.parametrize(
        "our,espn",
        [
            ("2026-06-09", "2026-06-07T00:00:00"),  # ev14861878 -> 06-06 ET game
            ("2026-06-11", "2026-06-05T00:00:00"),  # ev14881094 -> 06-04 ET game
            ("2026-05-27", "2026-05-26T00:00:00"),  # ev14792938 -> 05-25 ET game
            ("2026-05-29", "2026-05-23T23:00:00"),  # ev14798909 -> 05-23 ET game
            ("2026-05-16", "2026-05-12T23:00:00"),  # ev14639101 -> 05-12 ET game
        ],
    )
    def test_same_series_neighbour_is_blocked(self, our, espn):
        from datetime import date

        assert espn_date_matches(date.fromisoformat(our), self._et(espn)) is False

    def test_adjacent_day_is_blocked_not_tolerated(self):
        from datetime import date

        # No +/-1 day slack: back-to-backs are a real NHL/NBA pattern, so a one-day
        # tolerance would wave through exactly the defect we are guarding.
        assert espn_date_matches(date(2026, 5, 27), self._et("2026-05-26T18:00:00")) is False

    def test_missing_inputs_block(self):
        from datetime import date

        assert espn_date_matches(None, self._et("2026-03-28T21:00:00")) is False
        assert espn_date_matches(date(2026, 3, 28), None) is False

    def test_naive_datetime_treated_as_utc(self):
        from datetime import date, datetime

        assert espn_date_matches(date(2026, 3, 28), datetime(2026, 3, 28, 21, 0)) is True


class TestResolvedHomeFromScore:
    def test_home_win_away_win_tie(self):
        assert resolved_home_from_score(6, 3) == 1.0
        assert resolved_home_from_score(3, 6) == 0.0
        assert resolved_home_from_score(2, 2) == 0.5

    def test_winner_flip_is_detectable(self):
        # ev15182890: stored LAD 6-7 (away win) vs real LAD 6-2 (home win). The
        # staleness net had already graded the blend off the WRONG side.
        assert resolved_home_from_score(6, 7) != resolved_home_from_score(6, 2)


class TestFrozenFinalScoreDetector:
    """The sentinel detector is pure over the repair's dry-run ledger, so guard and
    repair share ONE definition of the defect."""

    def _ledger(self):
        return [
            {"action": "fix_score", "event_id": 12080400, "sport_key": "icehockey_nhl",
             "matchup": "Boston Bruins vs Minnesota Wild", "status": "closed",
             "stored_score": "3-1", "espn_final": "6-3", "winner_flip": False},
            {"action": "fix_completed_at_only", "event_id": 999, "sport_key": "baseball_mlb"},
            {"action": "skip_identity_mismatch", "event_id": 12256979,
             "sport_key": "baseball_ncaa"},
        ]

    def test_flags_only_score_defects(self):
        found = frozen_final_score_events(self._ledger())
        assert [f["event_id"] for f in found] == [12080400]
        assert found[0]["stored_score"] == "3-1"
        assert found[0]["espn_final"] == "6-3"

    def test_identity_blocked_rows_are_not_reported_as_frozen_scores(self):
        # They are an espn_id linkage defect; filing them here would mis-route the
        # issue and cry wolf on a class this repair deliberately refuses to touch.
        found = frozen_final_score_events(self._ledger())
        assert all(f["event_id"] != 12256979 for f in found)

    def test_clean_ledger_is_green(self):
        assert frozen_final_score_events([]) == []
        assert frozen_final_score_events(
            [{"action": "fix_completed_at_only", "event_id": 1}]
        ) == []

    def test_winner_flip_is_surfaced(self):
        found = frozen_final_score_events([
            {"action": "fix_score", "event_id": 15182890, "sport_key": "baseball_mlb",
             "matchup": "Los Angeles Dodgers vs Seattle Mariners", "status": "completed",
             "stored_score": "6-7", "espn_final": "6-2", "winner_flip": True},
        ])
        assert found[0]["winner_flip"] is True


class TestRepairIsRegisteredOnTheRail:
    def test_registered_and_signature_accepts_bounds(self):
        import inspect

        from app.routes.admin_repairs import _REPAIRS
        from scripts.repair_event_final_scores import repair

        assert _REPAIRS["event-final-scores"] == (
            "scripts.repair_event_final_scores", "repair",
        )
        params = inspect.signature(repair).parameters
        # The dispatcher passes these through only if declared; the repair is
        # unusable over 6k+ events without a bound and a resumable cursor.
        for p in ("limit", "sport", "newest_first"):
            assert p in params, f"{p} must stay in the signature (dispatcher passthrough)"

    def test_dry_run_is_the_default(self):
        import inspect

        from scripts.repair_event_final_scores import repair

        assert inspect.signature(repair).parameters["apply"].default is inspect.Parameter.empty
        # apply is positional-required on the rail contract fn(session, apply);
        # the ENDPOINT defaults it to False. Pin that here so it can't regress.
        from app.routes.admin_repairs import run_repair

        assert inspect.signature(run_repair).parameters["apply"].default.default is False


@pytest.mark.parametrize(
    "ours,espn,expected",
    [
        ((3, 1), (6, 3), True),    # NHL frozen mid-game
        ((2, 8), (16, 3), True),   # MLB wrong-game-from-series
        ((45, 56), (87, 109), True),  # NBA halftime
        ((5, 4), (5, 4), False),   # healthy
        ((1, 0), (1, 0), False),   # healthy low-scoring
    ],
)
def test_anchor_table(ours, espn, expected):
    assert score_is_stale(ours[0], ours[1], espn[0], espn[1], True) is expected
