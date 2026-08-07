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


# ---------------------------------------------------------------------------
# UX-P005 class (b) — ladders must not contradict themselves.
# Every case below is a production specimen captured from /api/feed 2026-08-06.
# ---------------------------------------------------------------------------

from app.utils.discover_card_archetypes import _threshold_points


def _points(name, labels):
    return _threshold_points(
        name=name,
        outcomes=[{"name": label, "probability": 0.1} for label in labels],
        outcome_count=len(labels),
    )


def _values(points):
    return [p["value"] for p in points]


def test_box_office_ladder_is_one_scale_and_monotonic():
    # BEFORE: [6000000, 7, 8, 9000000, 6] — "<6m" was multiplied to 6,000,000
    # while "7-8m" stayed 7, because two different parsers handled them.
    points = _points(
        '"Super Troopers 3" Opening Weekend Box Office',
        ["<6m", "6-7m", "7-8m", "8-9m", "9m+"],
    )
    values = _values(points)
    assert values == sorted(values), "box-office bars must not double back"
    assert all(v >= 1_000_000 for v in values), "every rung on the millions scale"


def test_range_label_suffix_governs_both_numbers():
    # "7-8m" means 7 million to 8 million, not 7 to 8 million.
    (value, _unit, _direction) = _outcome("7-8m")
    assert value == 7_000_000


def _outcome(label):
    from app.utils.discover_card_archetypes import _outcome_threshold_value

    resolved = _outcome_threshold_value(label)
    assert resolved is not None, f"{label!r} should parse as a threshold"
    return resolved


def test_parenthetical_second_number_does_not_create_a_second_rung():
    # BEFORE: "1 (25 bps)" emitted a rung at 1 AND a rung at 25, so the Fed
    # ladder read 0, 0, 1, 25, 2, 50, 3, 75, 12, 6, 150, 7.
    labels = ["0 (0 bps)", "1 (25 bps)", "2 (50 bps)", "3 (75 bps)", "6 (150 bps)"]
    points = _points("How many Fed rate cuts in 2026?", labels)
    assert len(points) == len(labels), "exactly one rung per outcome"
    assert _values(points) == [0, 1, 2, 3, 6]


def test_gold_ladder_sorts_numerically_not_by_arrival():
    # BEFORE: 15,000 was displayed before 12,000.
    points = _points(
        "What will Gold (GC) hit by end of December?",
        ["↑ $6,000", "↑ $7,000", "↑ $8,000", "↑ $10,000", "↑ $15,000", "↑ $12,000"],
    )
    assert _values(points) == [6000, 7000, 8000, 10000, 12000, 15000]


def test_entity_titles_are_not_a_threshold_ladder():
    # BEFORE: "The Bombing of Pan Am 103" scored 103.0 and sorted among the
    # 1s and 3s of a Netflix ladder.
    points = _points(
        "What will be the top global Netflix show this week?",
        [
            "The Idaho Murders",
            "The Bombing of Pan Am 103",
            "Little House on the Prairie",
            "Ransom Canyon: Season 2",
        ],
    )
    assert points == []


def test_date_labels_are_not_a_threshold_ladder():
    # BEFORE: "June 30, 2027" scored 30 (the day of month).
    points = _points(
        "Will Samuel Alito announce his retirement by...?",
        ["June 30, 2027", "December 31", "September 30"],
    )
    assert points == []


def test_real_numeric_ladders_still_render():
    # Both directions (gotcha #43): the suppression must not eat live ladders.
    points = _points(
        "SpaceX IPO Closing Market Cap",
        ["$1.5T-$2.0T", "$2.0T-$2.5T", "Above $2.5T"],
    )
    assert len(points) == 3
    assert _values(points) == sorted(_values(points))


def test_ordinal_in_the_question_is_not_a_rung():
    # The market-name fallback bypassed the shape guard, so "#2" in the
    # QUESTION became a lone threshold on a card whose outcomes are film titles.
    points = _points(
        "What will be the #2 global Netflix movie this week?",
        ["72 Hours", "Five Nights at Freddy's 2", "Kung Fu Panda 4"],
    )
    assert points == []


def test_market_name_fallback_still_works_for_real_thresholds():
    # Both directions: a genuinely numeric question must still yield its rung.
    points = _points("Will Bitcoin close above $150,000?", ["Yes", "No"])
    assert len(points) == 1
    assert points[0]["source"] == "market_name"
    assert points[0]["value"] == 150_000
