"""Unit tests for the offline Discover ranking replay runner (#142/RANK-2)."""

from app.utils.market_interestingness import DEFAULT_WEIGHTS, InterestingnessWeights
from scripts.replay_discover_ranking import (
    ReplayConfig,
    blend_rank,
    build_demo_labels,
    build_demo_snapshot,
    compare_configs,
    config_from_dict,
    dataset_split,
    default_configs,
    diff_vs_served,
    rerank,
)


def test_blend_rank_mirrors_feed_plus15_cap():
    # Any realistic interestingness score saturates the +15 uplift cap, matching
    # feed.py's UNCAPPED ordering blend.
    assert blend_rank(60.0, 50.0, 0.2) == 75.0  # 60 + 15 cap
    # Kill switch / no cache => unchanged.
    assert blend_rank(60.0, 50.0, 0.0) == 60.0
    assert blend_rank(60.0, None, 0.2) == 60.0


def test_dataset_split_matches_admin_judgments_source():
    # Kept in sync by hand; assert the algorithm agrees with the route module.
    from app.routes.admin_judgments import _dataset_split

    for market_id in (1, 42, 101, 999, 123456):
        assert dataset_split(market_id) == _dataset_split(market_id, None)


def test_rerank_orders_by_replay_score_desc():
    rows = build_demo_snapshot()
    reranked = rerank(rows, default_configs()[0])
    scores = [r["replay_rank_score"] for r in reranked]
    assert scores == sorted(scores, reverse=True)
    assert reranked[0]["replay_rank"] == 1


def test_interestingness_weights_do_not_change_ordering_due_to_saturation():
    # The core RANK-2 finding: two very different weight vectors produce the same
    # ordering because the +15 blend cap saturates. This locks in the diagnosis.
    rows = build_demo_snapshot()
    baseline, movement_heavy, _base = default_configs()
    a = [r["market_id"] for r in rerank(rows, baseline)]
    b = [r["market_id"] for r in rerank(rows, movement_heavy)]
    assert a == b


def test_base_override_does_change_ordering():
    rows = build_demo_snapshot()
    base_reshuffle = default_configs()[2]
    reordered = [r["market_id"] for r in rerank(rows, base_reshuffle)]
    baseline_order = [r["market_id"] for r in rerank(rows, default_configs()[0])]
    assert reordered != baseline_order
    # sports market (105) gets boosted from 18.5 -> 60 and jumps to the top.
    assert reordered[0] == 105


def test_diff_vs_served_reports_overlap_and_delta():
    rows = build_demo_snapshot()
    reranked = rerank(rows, default_configs()[2])
    diff = diff_vs_served(reranked, top_k=5)
    assert diff["top_k"] == 5
    assert 0 <= diff["top_k_overlap"] <= 5
    assert diff["mean_abs_rank_delta"] >= 0


def test_compare_configs_full_shape_with_labels():
    rows = build_demo_snapshot()
    labels = build_demo_labels()
    comparison = compare_configs(rows, default_configs(), labels, top_k=6, split=None)
    assert comparison["candidate_count"] == 10
    assert len(comparison["configs"]) == 3
    for result in comparison["configs"]:
        assert result["gold_set"]["labeled_candidates"] == 7
        assert "tapworthy_at_k" in result["gold_set"]
        assert "duplicate_family_rate" in result["classifier"]


def test_config_from_dict_parses_weights_and_overrides():
    config = config_from_dict(
        {
            "name": "custom",
            "weights": {"movement": 30.0, "volume": 5.0},
            "blend_weight": 0.3,
            "base_overrides": {"Sports": 55},
        }
    )
    assert isinstance(config, ReplayConfig)
    assert config.weights.movement == 30.0
    assert config.blend_weight == 0.3
    assert config.base_overrides == {"sports": 55.0}
