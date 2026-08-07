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


# ── UX-P008 (#1526 residual) — a FIELD must never be routed to a threshold card ──
#
# #1526's headline half was the frontend `slice(0, 4)` that dropped the leader.
# Its "not root-caused here" note carried a second card that nobody had traced:
# Grammy Best New Artist rendering exactly two rows, `PARTYOF2 1%` and
# `Rob49 1%`, with the real 68.5% leader nowhere on it.
#
# Traced 2026-08-07 against production market 56775571 (`KXGRAMBNA-69`, 67
# nominees). It was never a frontend defect and it was NOT the suspected
# `buildHeatmapRows` lowercase-Map collision — that Map never saw more than the
# two rows it was handed. `_compact_value_thresholds` matched a bare integer
# anywhere inside a name, and of 67 nominees exactly two contain one:
# PARTYOF2 -> 2.0 and Rob49 -> 49.0. Two rungs cleared `len >= 2`, the market
# became a `threshold_heatmap`, and the 65 nominees without a digit — the
# leader among them — produced no rung and vanished. The ascending value sort
# put PARTYOF2 (2) above Rob49 (49), which is the rendered card exactly.
#
# UX-P005's `_THRESHOLD_SHAPED_RE` closed that path as a side effect while
# fixing its own class (b). These tests pin it shut, because nothing named this
# card and a future widening of the shape gate would silently reopen it.


def _fmt(name, labels, *, category=None, outcome_count=None):
    return classify_discover_card_archetype(
        name=name,
        category=category,
        outcomes=[{"name": label, "probability": 0.01} for label in labels],
        outcome_count=outcome_count if outcome_count is not None else len(labels),
    )


def test_grammy_nominee_names_containing_digits_are_not_a_ladder():
    # The exact production specimen. A stage name is not a threshold.
    assert _points("Grammy Winner: Best New Artist", ["PARTYOF2", "Rob49"]) == []


def test_grammy_field_keeps_its_leader_and_renders_as_a_distribution():
    # The 10 highest-probability nominees of production market 56775571, real
    # names and real prices. The leader must survive classification.
    nominees = [
        ("Ella Langley", 0.685), ("SIENNA SPIRO", 0.185), ("Geese", 0.065),
        ("Rob49", 0.020), ("Dijon", 0.015), ("Megan Moroney", 0.015),
        ("Bella Kay", 0.015), ("Jane Handcock", 0.010), ("Celeste", 0.010),
        ("PARTYOF2", 0.010),
    ]
    result = classify_discover_card_archetype(
        name="Grammy Winner: Best New Artist",
        category="entertainment",
        outcomes=[{"name": n, "probability": p} for n, p in nominees],
        outcome_count=67,
    )

    assert result["threshold_points"] == []
    assert result["suggested_format"] == "outcome_distribution"
    # The card the user sees leads with the actual favourite, not a 1% name
    # that happened to contain a number.
    assert result["distribution_outcomes"][0]["label"] == "Ella Langley"


def test_a_multi_outcome_field_is_not_hijacked_by_a_number_in_its_title():
    # Production 2026-08-07, market 52755659: 32 NHL teams. "2026-27" scored a
    # rung at 27, so the card was a `threshold_heatmap` with ONE row. The
    # frontend needs two rows to draw a heatmap, so it fell through past the
    # distribution branch to the plain leader card and the 32-team field
    # disappeared behind a lone "Florida Panthers 11%".
    result = _fmt(
        "2026-27 Stanley Cup® Finals Winner",
        ["Florida Panthers", "Colorado Avalanche", "Carolina Hurricanes", "Dallas Stars"],
        outcome_count=32,
    )
    assert result["threshold_points"] == []
    assert result["suggested_format"] == "outcome_distribution"


def test_a_rejected_incoherent_ladder_is_not_resurrected_by_the_market_name():
    # Production 2026-08-07, market 58586182. The 13 outcome rungs span 1 to
    # 3e6 (esports team names: "100T", handicaps), so the scale-coherence guard
    # correctly binned the ladder — and the market-name fallback then handed it
    # a fresh rung at 7,000,000 parsed out of "W7M". The guard's comment says it
    # drops the threshold treatment ENTIRELY; this holds it to that.
    points = _points(
        "Counter-Strike: BIG vs Fluxo W7M (BO3) - Esports World Cup Open Qualifier",
        ["Map 1 Total Rounds: Over 26.5", "Map Handicap: 100T (-1.5)"],
    )
    assert points == []


def test_the_field_floor_matches_the_distribution_branch():
    # The suppression floor and the classifier's `count >= 4` distribution
    # branch must be the same number. If they drift apart, markets in the gap
    # get neither card: no rung (suppressed) and no distribution (below the
    # branch), which is how a field silently becomes a bare leader again.
    import inspect

    from app.utils.discover_card_archetypes import _FIELD_OUTCOME_FLOOR

    source = inspect.getsource(classify_discover_card_archetype)
    assert f"count >= {_FIELD_OUTCOME_FLOOR}" in source

    # And prove it at the boundary rather than trusting the string match: three
    # outcomes still take the market-name rung, four no longer do.
    assert len(_points("Will Bitcoin close above $150,000?", ["a", "b", "c"])) == 1
    assert _points("Will Bitcoin close above $150,000?", ["a", "b", "c", "d"]) == []


def test_binary_threshold_questions_keep_their_rung():
    # Both directions (gotcha #43). The suppression is scoped to FIELDS; the
    # two-outcome threshold question this fallback exists for is untouched.
    for labels in (["Yes", "No"], ["Above", "Below"]):
        points = _points("Will Bitcoin close above $150,000?", labels)
        assert len(points) == 1
        assert points[0]["source"] == "market_name"
        assert points[0]["value"] == 150_000
