"""UX-P028 — the external-curator corpus freshness policy.

Guards the thing the UX-P027 census found in production: a live Discover
recall+rank lane running on a corpus that had stopped aging months earlier, with
nothing anywhere saying so.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.external_curator_freshness import (
    CORPUS_CURRENT,
    CORPUS_EMPTY,
    CORPUS_STALE,
    CORPUS_UNKNOWN,
    RECALL_MAX_AGE_DAYS,
    classify_corpus,
    corpus_age_days,
    recall_cutoff,
)

# Fixed clock — never seed relative to a live `now` across a date boundary
# (gotcha #44).
NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)


def test_cutoff_is_max_age_days_before_now():
    assert recall_cutoff(NOW) == NOW - timedelta(days=RECALL_MAX_AGE_DAYS)


def test_fresh_corpus_is_current_and_usable():
    verdict = classify_corpus(NOW - timedelta(days=1), NOW, row_count=3)
    assert verdict["state"] == CORPUS_CURRENT
    assert verdict["usable"] is True
    assert verdict["age_days"] == pytest.approx(1.0)


def test_the_production_corpus_that_prompted_this_is_stale():
    """The real specimen: 3 accepted rows last imported 2026-05-19.

    82 days old on the day this shipped. It must be stale, and the lane must
    refuse to use it — that is the entire point of the change.
    """
    verdict = classify_corpus(
        datetime(2026, 5, 19, 23, 50, 59, tzinfo=timezone.utc), NOW, row_count=3
    )
    assert verdict["state"] == CORPUS_STALE
    assert verdict["usable"] is False
    assert verdict["age_days"] > 80


def test_boundary_is_inclusive_on_the_fresh_side():
    """Exactly at the bound is still usable; a hair past it is not."""
    at_bound = classify_corpus(NOW - timedelta(days=RECALL_MAX_AGE_DAYS), NOW, row_count=1)
    just_past = classify_corpus(
        NOW - timedelta(days=RECALL_MAX_AGE_DAYS, seconds=1), NOW, row_count=1
    )
    assert at_bound["state"] == CORPUS_CURRENT
    assert just_past["state"] == CORPUS_STALE


def test_empty_corpus_is_empty_not_stale():
    verdict = classify_corpus(None, NOW, row_count=0)
    assert verdict["state"] == CORPUS_EMPTY
    assert verdict["usable"] is False


def test_missing_timestamp_is_unknown_and_fails_closed():
    verdict = classify_corpus(None, NOW, row_count=5)
    assert verdict["state"] == CORPUS_UNKNOWN
    assert verdict["usable"] is False


def test_naive_timestamp_is_read_as_utc_not_local():
    """A naive datetime must not shift the age by the reader's offset."""
    naive = classify_corpus(datetime(2026, 8, 7, 12, 0), NOW, row_count=1)
    aware = classify_corpus(datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc), NOW, row_count=1)
    assert naive["age_days"] == aware["age_days"] == pytest.approx(1.0)


def test_age_of_unusable_timestamp_is_none():
    assert corpus_age_days("not-a-datetime", NOW) is None
    assert corpus_age_days(None, NOW) is None


def test_stale_reason_says_the_lane_is_contributing_nothing():
    """The operator-facing string has to name the consequence, not just the age."""
    verdict = classify_corpus(NOW - timedelta(days=60), NOW, row_count=3)
    assert "contributing nothing" in verdict["reason"]
