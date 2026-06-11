from app.utils.discover_card_archetypes import classify_discover_card_archetype


def test_ipo_market_cap_is_heatmap_and_bundle_candidate():
    result = classify_discover_card_archetype(
        name="SpaceX IPO Closing Market Cap",
        category="tech",
        outcomes=[
            {"name": "$1.5T-$2.0T", "probability": 0.24},
            {"name": "$2.0T-$2.5T", "probability": 0.31},
            {"name": "Above $2.5T", "probability": 0.18},
        ],
        outcome_count=3,
        group_id="kalshi:spacex-ipo-cap",
    )

    assert result["suggested_format"] == "threshold_heatmap"
    assert result["bundle_candidate"] is True
    assert result["comparison_theme"] == "ipo_valuation"
    assert len(result["threshold_points"]) >= 2


def test_commodity_range_market_is_heatmap_candidate():
    result = classify_discover_card_archetype(
        name="Oil Price (WTI) on Jun 10, 2026?",
        category="economics",
        outcomes=[
            {"name": "Above $83.99", "probability": 0.92},
            {"name": "$80.00 to $83.99", "probability": 0.06},
            {"name": "Below $80.00", "probability": 0.02},
        ],
        outcome_count=3,
    )

    assert result["suggested_format"] == "threshold_heatmap"
    assert result["comparison_theme"] == "commodity_ranges"
    assert result["bundle_candidate"] is True


def test_rotten_tomatoes_threshold_market_prefers_heatmap():
    result = classify_discover_card_archetype(
        name="Will Dune 3 have a Rotten Tomatoes score above 90%?",
        category="entertainment",
        outcomes=[
            {"name": "Yes", "probability": 0.36},
            {"name": "No", "probability": 0.64},
        ],
        outcome_count=2,
        canonical_market_key="rt:dune-3",
    )

    assert result["suggested_format"] == "threshold_heatmap"
    assert result["comparison_theme"] == "rotten_tomatoes_scores"
    assert result["threshold_points"][0]["source"] == "market_name"


def test_multi_source_signal_is_qa_only_not_public_disagreement():
    result = classify_discover_card_archetype(
        name="2028 U.S. Presidential Election winner?",
        category="politics",
        outcomes=[
            {"name": "Marco Rubio", "probability": 0.18},
            {"name": "Gavin Newsom", "probability": 0.17},
            {"name": "JD Vance", "probability": 0.16},
            {"name": "AOC", "probability": 0.09},
        ],
        outcome_count=12,
        source_count=2,
        sources=["kalshi", "polymarket"],
    )

    assert result["suggested_format"] == "outcome_distribution"
    assert [row["label"] for row in result["distribution_outcomes"][:2]] == [
        "Marco Rubio",
        "Gavin Newsom",
    ]
    assert result["remaining_outcome_count"] == 8
    assert result["public_source_disagreement"] is False
    assert result["qa_signals"] == ["multi_source_consistency_check"]


def test_recent_binary_movement_prefers_timeline():
    result = classify_discover_card_archetype(
        name="US-Iran nuclear deal by June 30?",
        category="geopolitics",
        outcomes=[
            {"name": "Yes", "probability": 0.43, "movement": 0.08},
            {"name": "No", "probability": 0.57, "movement": -0.08},
        ],
        outcome_count=2,
    )

    assert result["suggested_format"] == "probability_timeline"
    assert "recent_movement" in result["reasons"]
