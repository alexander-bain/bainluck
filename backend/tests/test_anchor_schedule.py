"""An anchored row may not disagree with its own anchor about the kickoff.

#2693 / #2697, lane1/066. The rule is `app/utils/anchor_schedule`; the rail
that runs it is `app/tasks/reconcile_anchor_schedule`.

WHAT THESE TESTS ARE DEFENDING, in the order it matters:

* **The write happens at all.** The charter rows (two NFL fixtures sitting in
  Week 1 wearing anchors for Week 6 and Week 15) must produce a move, or the
  ship — Week 1 showing 16 games instead of 18 — does not happen.
* **The write does NOT happen when the teams disagree.** That is the dangerous
  direction: dragging a real fixture onto another game's clock. A rail that
  corrects too eagerly is worse than the defect it corrects, because the
  corrupted row then looks authoritative.
* **Silence is never agreement** (gotcha #53). A dark ESPN and a healthy
  population return the same empty body, and a rail that cannot tell them
  apart reports health during an outage.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.anchor_schedule import (
    AGREES,
    AUTHORITY_MOVES_US,
    NO_ANSWER,
    REFUSED_COMPLETED,
    REFUSED_SETTLED,
    REFUSED_STATPAL,
    SAME_START_TOLERANCE_S,
    SCHEDULE_VERDICTS,
    TEAMS_DISAGREE,
    AnchoredRow,
    schedule_decision,
    summarize_decisions,
)
from app.utils.authority_id_collisions import AuthorityRecord

UTC = timezone.utc

#: The charter row, verbatim from production 2026-09-03: the anchor is right,
#: the team names are right, the kickoff belongs to Week 15.
CHARTER_OURS = datetime(2026, 9, 11, 0, 35, tzinfo=UTC)
CHARTER_THEIRS = datetime(2026, 12, 18, 1, 15, tzinfo=UTC)


def _row(**overrides) -> AnchoredRow:
    base = dict(
        event_id=14780595,
        sport_key="americanfootball_nfl",
        home_team_name="Los Angeles Chargers",
        away_team_name="San Francisco 49ers",
        espn_id="401873124",
        commence_time=CHARTER_OURS,
        status="scheduled",
        completed_at=None,
        commence_time_source="espn",
    )
    base.update(overrides)
    return AnchoredRow(**base)


def _record(**overrides) -> AuthorityRecord:
    base = dict(
        authority_id="401873124",
        home_names=frozenset({"los angeles chargers", "chargers"}),
        away_names=frozenset({"san francisco 49ers", "49ers"}),
        starts_at=CHARTER_THEIRS,
        label="Los Angeles Chargers v San Francisco 49ers",
    )
    base.update(overrides)
    return AuthorityRecord(**base)


class TestTheCharterCase:
    """The two rows this was built for, and the ship they block."""

    def test_the_authority_moves_a_misdated_row(self):
        decision = schedule_decision(_row(), _record())

        assert decision.verdict == AUTHORITY_MOVES_US
        assert decision.write == {
            "commence_time": CHARTER_THEIRS,
            "commence_time_source": "espn",
        }
        # 98 days. Recorded because the SIZE is what tells a reviewer this is a
        # wrong week and not a rescheduling.
        assert decision.delta_seconds == int(
            (CHARTER_THEIRS - CHARTER_OURS).total_seconds()
        )

    def test_it_writes_the_start_and_its_provenance_and_nothing_else(self):
        """One column plus its provenance — not status, not scores.

        A rail that starts fixing adjacent things is how a repair becomes an
        incident, and `commence_time_source` is in scope only because both
        charter rows ALREADY claimed 'espn' while disagreeing with ESPN by
        three months: a provenance column is worth nothing if the thing that
        sets it did not check.
        """
        assert set(schedule_decision(_row(), _record()).write) == {
            "commence_time",
            "commence_time_source",
        }

    def test_orientation_is_observed_and_does_not_change_the_verdict(self):
        # ESPN listing the sides the other way round is the same fixture.
        swapped = _record(
            home_names=frozenset({"san francisco 49ers"}),
            away_names=frozenset({"los angeles chargers"}),
        )
        decision = schedule_decision(_row(), swapped)
        assert decision.verdict == AUTHORITY_MOVES_US
        assert decision.orientation_inverted is True


class TestTheDangerousDirection:
    """Refusing to write is the whole safety argument. Each refusal, separately."""

    def test_teams_that_disagree_are_never_moved(self):
        """The real one, from production: E416569.

        Our row is Ohio State at Texas; the anchor it wears is Texas v Texas
        State. Moving the clock would drag a marquee fixture onto another
        game's time and make the mis-anchor look authoritative. The disagreement
        is about identity, and identity belongs to `authority-id-collisions`.
        """
        decision = schedule_decision(
            _row(
                home_team_name="Texas Longhorns", away_team_name="Ohio State Buckeyes"
            ),
            _record(
                home_names=frozenset({"texas longhorns"}),
                away_names=frozenset({"texas state bobcats"}),
                label="Texas Longhorns v Texas State Bobcats",
            ),
        )
        assert decision.verdict == TEAMS_DISAGREE
        assert decision.write == {}
        # The reason has to name the fixture the anchor actually points at, or
        # a reviewer cannot tell a vocabulary gap from a real mis-anchor.
        assert "Texas State Bobcats" in decision.reason

    def test_a_completed_row_is_never_re_dated(self):
        # `completed_at >= commence_time` is an invariant whose violation is a
        # P1 by standing rule (gotcha #46), and every chart that has drawn this
        # game drew it against the start we are being asked to move.
        decision = schedule_decision(
            _row(completed_at=datetime(2026, 9, 11, 3, 0, tzinfo=UTC)), _record()
        )
        assert decision.verdict == REFUSED_COMPLETED
        assert decision.write == {}

    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_a_settled_row_is_never_re_dated(self, status):
        decision = schedule_decision(_row(status=status), _record())
        assert decision.verdict == REFUSED_SETTLED
        assert decision.write == {}

    def test_statpal_outranks_espn_for_kickoff_times(self):
        # The existing precedence, stated in three places in `espn_helpers`. A
        # new rail that quietly reversed it would be a regression wearing a
        # fix's clothes.
        decision = schedule_decision(_row(commence_time_source="statpal"), _record())
        assert decision.verdict == REFUSED_STATPAL
        assert decision.write == {}

    def test_the_refusals_are_ordered_most_certain_first(self):
        """A finished row is refused for BEING FINISHED, not for its teams.

        Ordering is load-bearing for the reason string: a settled row whose
        teams also disagree must report the settlement, because that is the
        fact that decides it and the one an operator can act on.
        """
        decision = schedule_decision(
            _row(
                status="completed",
                home_team_name="Somebody Else",
                away_team_name="Nobody At All",
            ),
            _record(),
        )
        assert decision.verdict == REFUSED_SETTLED


class TestSilenceIsNeverAgreement:
    """Gotcha #53: an absent answer and a healthy row are not the same read."""

    def test_no_record_is_no_answer_not_agreement(self):
        decision = schedule_decision(_row(), None)
        assert decision.verdict == NO_ANSWER
        assert decision.write == {}

    def test_a_record_naming_only_one_side_decides_nothing(self):
        decision = schedule_decision(_row(), _record(away_names=frozenset()))
        assert decision.verdict == NO_ANSWER

    def test_a_record_with_no_start_time_decides_nothing(self):
        decision = schedule_decision(_row(), _record(starts_at=None))
        assert decision.verdict == NO_ANSWER

    def test_a_row_with_no_start_of_its_own_is_not_filled_in(self):
        # Correcting a disagreement and inventing a missing value are different
        # rails, and only one of them has an argument behind it here.
        decision = schedule_decision(_row(commence_time=None), _record())
        assert decision.verdict == NO_ANSWER
        assert decision.write == {}


class TestTheTolerance:
    """Where "already agrees" ends and "the authority moves us" begins."""

    def test_inside_the_tolerance_agrees_and_writes_nothing(self):
        decision = schedule_decision(
            _row(),
            _record(starts_at=CHARTER_OURS + timedelta(seconds=SAME_START_TOLERANCE_S)),
        )
        assert decision.verdict == AGREES
        assert decision.write == {}

    def test_one_second_beyond_the_tolerance_moves(self):
        decision = schedule_decision(
            _row(),
            _record(
                starts_at=CHARTER_OURS + timedelta(seconds=SAME_START_TOLERANCE_S + 1)
            ),
        )
        assert decision.verdict == AUTHORITY_MOVES_US

    def test_the_tolerance_matches_what_the_live_pass_already_uses(self):
        # `espn_helpers` corrects a commence_time when the gap exceeds 300s, in
        # three places. If this rail disagreed with that number the two would
        # fight over the same rows on alternate passes.
        assert SAME_START_TOLERANCE_S == 300

    def test_the_authority_moving_a_start_EARLIER_is_still_a_move(self):
        # Direction-blind on purpose: `abs()` in the delta. A rule that only
        # corrected forward would silently keep every start that ESPN pulled in.
        decision = schedule_decision(
            _row(), _record(starts_at=CHARTER_OURS - timedelta(days=3))
        )
        assert decision.verdict == AUTHORITY_MOVES_US
        assert decision.write["commence_time"] == CHARTER_OURS - timedelta(days=3)


class TestTheSummary:
    """What a reviewer decides to apply on."""

    def test_every_verdict_is_present_as_a_zero_rather_than_omitted(self):
        # A missing key and a measured zero read identically to a consumer.
        summary = summarize_decisions([])
        assert set(summary["by_verdict"]) == set(SCHEDULE_VERDICTS)
        assert set(summary["by_verdict"].values()) == {0}
        assert summary["examined"] == 0

    def test_only_moves_are_listed_as_moves(self):
        decisions = [
            schedule_decision(_row(), _record()),
            schedule_decision(_row(event_id=2), None),
            schedule_decision(_row(event_id=3), _record(starts_at=CHARTER_OURS)),
        ]
        summary = summarize_decisions(decisions)
        assert summary["examined"] == 3
        assert [m["event_id"] for m in summary["moves"]] == [14780595]
        assert summary["moves"][0]["delta_days"] == pytest.approx(98.03, abs=0.01)
