from app.utils.discover_bundles import assemble_discover_comparison_bundles


def _futures_item(
    market_id: int,
    name: str,
    *,
    theme: str = "ipo_valuation",
    public_source_disagreement: bool = False,
    threshold_count: int = 3,
) -> dict:
    return {
        "type": "futures",
        "score": 95 - market_id,
        "reason": "reason",
        "headline": name,
        "context_summary": None,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "tech",
            "source": "kalshi",
            "discover_card": {
                "suggested_format": "threshold_heatmap",
                "bundle_candidate": True,
                "comparison_theme": theme,
                "threshold_points": [
                    {"label": f"${index}B", "value": index, "probability": 0.2}
                    for index in range(threshold_count)
                ],
                "public_source_disagreement": public_source_disagreement,
            },
        },
        "_sort_time": 1000 + market_id,
        "_quality_family_key": "internal",
    }


def test_assembles_safe_comparison_bundle_and_suppresses_members():
    items = [
        _futures_item(1, "SpaceX IPO Closing Market Cap"),
        _futures_item(2, "Stripe IPO Closing Market Cap"),
        {"type": "event", "score": 80, "data": {"id": 9}},
    ]

    result = assemble_discover_comparison_bundles(items)

    assert [item["type"] for item in result] == ["bundle", "event"]
    bundle = result[0]
    assert bundle["headline"] == "IPO valuation ranges"
    assert bundle["data"]["comparison_theme"] == "ipo_valuation"
    assert bundle["data"]["member_ids"] == [1, 2]
    assert bundle["data"]["debug_bundles"]["grouped_by"] == (
        "discover_card.comparison_theme"
    )
    assert "_quality_family_key" not in bundle["data"]["items"][0]


def test_keeps_singleton_candidate_as_individual_card():
    item = _futures_item(1, "SpaceX IPO Closing Market Cap")

    assert assemble_discover_comparison_bundles([item]) == [item]


def test_excludes_source_disagreement_from_public_bundles():
    items = [
        _futures_item(
            1,
            "SpaceX IPO Closing Market Cap",
            public_source_disagreement=True,
        ),
        _futures_item(2, "Stripe IPO Closing Market Cap"),
    ]

    assert assemble_discover_comparison_bundles(items) == items


def test_requires_multiple_threshold_points_per_member():
    items = [
        _futures_item(
            1,
            "Will Dune 3 have a Rotten Tomatoes score above 90%?",
            theme="rotten_tomatoes_scores",
            threshold_count=1,
        ),
        _futures_item(
            2,
            "Will Wicked 2 have a Rotten Tomatoes score above 90%?",
            theme="rotten_tomatoes_scores",
            threshold_count=1,
        ),
    ]

    assert assemble_discover_comparison_bundles(items) == items


def test_dedupes_same_entity_inside_bundle():
    items = [
        _futures_item(1, "SpaceX IPO Closing Market Cap"),
        _futures_item(2, "SpaceX IPO Valuation"),
        _futures_item(3, "Stripe IPO Closing Market Cap"),
    ]

    result = assemble_discover_comparison_bundles(items)

    assert result[0]["type"] == "bundle"
    assert result[0]["data"]["member_ids"] == [1, 3]
    assert result[1]["data"]["id"] == 2
