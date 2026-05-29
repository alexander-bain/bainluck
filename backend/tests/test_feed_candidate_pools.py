"""Tests for Discover feed candidate-pool filters."""

from sqlalchemy.dialects import postgresql

from app.routes.feed import (
    _discover_editorial_recall_filter,
    _discover_sports_editorial_recall_filter,
)


def test_editorial_recall_filter_uses_precomputed_column():
    compiled = str(
        _discover_editorial_recall_filter().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "is_editorial_recall" in compiled

    from app.utils.editorial_patterns import matches_editorial_recall
    assert matches_editorial_recall("Will aliens visit Earth?")
    assert matches_editorial_recall("OpenAI releases GPT-5")
    assert matches_editorial_recall("US recession probability")
    assert matches_editorial_recall("Spotify top artist 2026")
    assert matches_editorial_recall("Billboard Hot 100")
    assert matches_editorial_recall("Rotten Tomatoes score")
    assert matches_editorial_recall("Xi Jinping visit")
    assert matches_editorial_recall("Eurovision winner")
    assert matches_editorial_recall("Hantavirus outbreak cases")
    assert not matches_editorial_recall("Regular market name")


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
