"""Tests for Discover feed candidate-pool filters."""

import inspect

from sqlalchemy.dialects import postgresql

import app.routes.feed as feed_mod
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


def test_editorial_recall_pool_folds_flag_no_global_materialization():
    """Queue 273 (#1475): the editorial-recall pool must fold the
    ``is_editorial_recall`` flag directly into its WHERE clause, NOT first
    materialize every open/active editorial id via a helper that seq-scanned the
    1.6GB / 588K-row futures_markets table (no index, no LIMIT) on every cold
    build — the single largest measured cold-feed query.

    Regression guards:
    1. The unbounded materialization helper is gone for good.
    2. The Discover futures pool wires the folded filter, and never rebuilds a
       pre-materialized ``id IN (editorial_ids)`` lane.
    """
    # 1. The unbounded helper must not exist (its reintroduction would restore
    #    the seq-scan-every-cold-build cost).
    assert not hasattr(feed_mod, "_get_editorial_recall_ids"), (
        "_get_editorial_recall_ids reintroduces the unbounded editorial "
        "global-ID materialization removed in Queue 273"
    )

    # 2. The scoring source folds the flag and drops the id-list intersection.
    src = inspect.getsource(feed_mod._score_futures)
    assert "nonsports_editorial_recall_query" in src
    assert (
        "_discover_editorial_recall_filter()" in src
    ), "editorial pool must fold the is_editorial_recall filter directly"
    assert (
        "_editorial_ids" not in src
    ), "editorial pool must not pre-materialize an id list to intersect"

    # 3. The folded filter compiles to the precomputed boolean column.
    compiled = str(
        _discover_editorial_recall_filter().compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert "is_editorial_recall" in compiled
