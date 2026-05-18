"""Tests for Discover feed candidate-pool filters."""

from sqlalchemy.dialects import postgresql

from app.routes.feed import (
    _discover_editorial_recall_filter,
    _discover_sports_editorial_recall_filter,
)


def test_editorial_recall_filter_targets_low_volume_public_interest_terms():
    compiled = str(
        _discover_editorial_recall_filter().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "aliens" in compiled
    assert "openai" in compiled
    assert "recession" in compiled
    assert "spotify" in compiled
    assert "billboard" in compiled
    assert "rotten tomatoes" in compiled
    assert "xi jinping" in compiled
    assert "eurovision" in compiled
    assert "hantavirus" in compiled


def test_sports_editorial_recall_filter_targets_mainstream_futures():
    compiled = str(
        _discover_sports_editorial_recall_filter().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "world cup" in compiled
    assert "fifa world cup" in compiled
    assert "super bowl" in compiled
    assert "nba finals" in compiled
