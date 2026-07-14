"""Queue #189 Item 3(A.1): the finished-event chart end_cap must not trust an
inverted completed_at.

Event 14970335 (Sox-Mets Jul-12) had completed_at = Jul-11 00:46 — ~41h BEFORE
its commence_time of Jul-12 17:40 (a different, earlier game's data merged onto
it, gotcha #32; 439 such events in prod). The old logic capped the history window
at completed_at+30min, clipping the entire real game out of the chart (empty
settled chart). The cap must fall back to the commence-based window in that case.
"""

from datetime import datetime, timedelta, timezone

from app.routes.events import _finished_event_end_cap


COMMENCE = datetime(2026, 7, 12, 17, 40, tzinfo=timezone.utc)
COMMENCE_CAP = COMMENCE + timedelta(hours=5)  # commence + max_duration


def test_inverted_completed_at_falls_back_to_commence_cap():
    # completed_at ~41h before commence -> corrupt -> ignore it.
    bad_completed = datetime(2026, 7, 11, 0, 46, tzinfo=timezone.utc)
    assert _finished_event_end_cap(bad_completed, COMMENCE, COMMENCE_CAP) == COMMENCE_CAP


def test_valid_completed_at_is_trusted():
    good_completed = COMMENCE + timedelta(hours=3)
    assert _finished_event_end_cap(good_completed, COMMENCE, COMMENCE_CAP) == (
        good_completed + timedelta(minutes=30)
    )


def test_missing_completed_at_uses_commence_cap():
    assert _finished_event_end_cap(None, COMMENCE, COMMENCE_CAP) == COMMENCE_CAP


def test_no_commence_time_still_trusts_completed_at():
    # With no commence to compare against, completed_at is all we have.
    good_completed = datetime(2026, 7, 12, 20, 40, tzinfo=timezone.utc)
    assert _finished_event_end_cap(good_completed, None, None) == (
        good_completed + timedelta(minutes=30)
    )


def test_completed_at_equal_to_commence_is_not_trusted():
    # Exactly-equal is not "after" first pitch -> treat as suspect, use the cap.
    assert _finished_event_end_cap(COMMENCE, COMMENCE, COMMENCE_CAP) == COMMENCE_CAP
