"""Board sync guard (#1153).

The FIRST test here is the artifact that produced the queue that commissioned
this code: three separate numbers ("238 of 416 open issues off-board", "346
missing", "the board's highest item is #1243") all came from one unpaginated
read of a 1,278-item board, and put a false premise into a staged queue. A
truncated read must fail loudly — never be reported as a gap, never as a pass.
"""

import pytest

from app.tasks.board_sync import (
    BLOCKED,
    BoardReadIncomplete,
    DONE,
    INBOX,
    IN_PROGRESS,
    NEEDS_USER,
    PARKED,
    READY,
    REVIEW,
    desired_status,
    summarize,
    verify_complete_read,
)


class TestTruncatedReadFailsLoudly:
    """A short read is not a fact about the board."""

    def test_complete_read_passes(self):
        verify_complete_read(fetched=1278, total_count=1278, pages=13)

    def test_unpaginated_prefix_raises(self):
        # The exact shape of the original artifact: one page of a 13-page board.
        with pytest.raises(BoardReadIncomplete) as exc:
            verify_complete_read(fetched=100, total_count=1278, pages=1)
        assert "TRUNCATED READ" in str(exc.value)

    def test_truncated_read_is_not_reported_as_a_gap(self):
        """The failure mode that invents work: 1,178 'missing' issues."""
        with pytest.raises(BoardReadIncomplete):
            verify_complete_read(fetched=100, total_count=1278, pages=1)

    def test_missing_total_count_raises(self):
        # No totalCount = no way to prove completeness = refuse.
        with pytest.raises(BoardReadIncomplete):
            verify_complete_read(fetched=100, total_count=None, pages=1)

    def test_overfetch_also_raises(self):
        with pytest.raises(BoardReadIncomplete):
            verify_complete_read(fetched=1300, total_count=1278, pages=13)


class TestGuardNeverFightsTheHuman:
    """The two things the guard must never do."""

    def test_never_unparks(self):
        # Parked is deliberate human state, authoritative over every label.
        for labels in ({"needs-user"}, {"blocked"}, {"in-progress"}, {"needs-agent"}):
            assert desired_status(labels, PARKED, "OPEN") is None

    def test_needs_agent_never_demotes_ready(self):
        # The commissioning brief's flat "else Inbox" rule would have demoted 17
        # Ready issues. needs-agent is true in Ready too; it contradicts nothing.
        assert desired_status({"needs-agent"}, READY, "OPEN") is None

    def test_needs_agent_never_demotes_review(self):
        assert desired_status({"needs-agent"}, REVIEW, "OPEN") is None

    def test_unlabelled_issue_in_a_human_column_is_left_alone(self):
        assert desired_status(set(), READY, "OPEN") is None
        assert desired_status(set(), REVIEW, "OPEN") is None
        assert desired_status(set(), IN_PROGRESS, "OPEN") is None


class TestStatusDrift:
    """The live half — 41 open issues in a column their labels contradict."""

    def test_needs_user_in_inbox_moves(self):
        # The acceptance sample: a needs-user P0 in Inbox is invisible to the
        # one column that exists to say "Alex must act".
        assert desired_status({"needs-user"}, INBOX, "OPEN") == NEEDS_USER

    def test_needs_user_in_review_moves(self):
        # #1279 — a P0 security issue labelled needs-user, sitting in Review.
        assert desired_status({"needs-user", "priority:p1"}, REVIEW, "OPEN") == NEEDS_USER

    def test_needs_user_already_correct_is_a_noop(self):
        assert desired_status({"needs-user"}, NEEDS_USER, "OPEN") is None

    def test_blocked_in_progress_moves(self):
        # #1453 / #1497 — labelled blocked while reading as active work.
        assert desired_status({"blocked"}, IN_PROGRESS, "OPEN") == BLOCKED

    def test_needs_user_outranks_blocked(self):
        assert desired_status({"blocked", "needs-user"}, INBOX, "OPEN") == NEEDS_USER

    def test_in_progress_label_promotes_from_inbox(self):
        assert desired_status({"in-progress"}, INBOX, "OPEN") == IN_PROGRESS

    def test_in_progress_label_does_not_demote_review(self):
        assert desired_status({"in-progress"}, REVIEW, "OPEN") is None

    def test_statusless_card_defaults_to_inbox(self):
        # A promotion out of nothing, not a demotion.
        assert desired_status(set(), None, "OPEN") == INBOX


class TestClosedCards:
    def test_closed_card_moves_to_done(self):
        assert desired_status(set(), INBOX, "CLOSED") == DONE

    def test_closed_card_leaves_parked(self):
        # Closure is a fact, not a triage opinion — it outranks even Parked.
        assert desired_status(set(), PARKED, "CLOSED") == DONE

    def test_closed_card_already_done_is_a_noop(self):
        assert desired_status(set(), DONE, "CLOSED") is None


class TestIdempotence:
    def test_second_pass_over_repaired_state_moves_nothing(self):
        board = [
            ({"needs-user"}, INBOX),
            ({"blocked"}, IN_PROGRESS),
            ({"in-progress"}, INBOX),
            ({"needs-agent"}, READY),
            (set(), PARKED),
        ]
        first = [desired_status(labels, col, "OPEN") for labels, col in board]
        assert sum(1 for t in first if t) == 3

        repaired = [
            (labels, target or col)
            for (labels, col), target in zip(board, first)
        ]
        second = [desired_status(labels, col, "OPEN") for labels, col in repaired]
        assert all(t is None for t in second), f"not idempotent: {second}"


def test_summarize_reports_the_page_count():
    # A zero from a truncated read is the same bug in the other direction, so
    # the summary always carries the page count alongside the counters.
    line = summarize(
        {
            "open_issues": 392,
            "board_items": 1278,
            "pages": 13,
            "missing": 0,
            "added": 0,
            "status_drift": 41,
            "status_fixed": 41,
            "closed_cards_moved": 0,
        }
    )
    assert "13 page(s)" in line
    assert "missing=0" in line
    assert "status_drift=41" in line
