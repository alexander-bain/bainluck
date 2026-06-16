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


# ── Geopolitics theme bundles (Phase 1, slice 1) ──────────────────────────────

from app.utils.discover_bundles import assemble_geopolitics_theme_bundles


def _geo_item(market_id: int, name: str, *, score: float | None = None) -> dict:
    return {
        "type": "futures",
        "score": 95 - market_id if score is None else score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "politics",
            "source": "kalshi",
        },
        "_sort_time": 1000 + market_id,
        "_quality_story_key": "internal-should-not-leak",
    }


def test_folds_scattered_middle_east_markets_into_one_bundle():
    items = [
        _geo_item(1, "Will Iran close the Strait of Hormuz?"),
        _geo_item(2, "Iran agrees to end enrichment of uranium by June?"),
        _geo_item(3, "Trump announces US x Iran ceasefire?"),
        _geo_item(4, "Will Iran close its airspace?"),
        {"type": "event", "score": 50, "data": {"id": 9}},
    ]

    result = assemble_geopolitics_theme_bundles(items)

    assert [it["type"] for it in result] == ["bundle", "event"]
    bundle = result[0]
    assert bundle["headline"] == "Middle East"
    assert bundle["data"]["kind"] == "theme"
    assert bundle["data"]["story_key"] == "story:middle_east_conflict"
    assert bundle["data"]["item_count"] == 4
    assert sorted(bundle["data"]["member_ids"]) == [1, 2, 3, 4]
    # Bundle competes for one slot scored by its best member (max score = id 1).
    assert bundle["score"] == 94
    # Internal underscore-prefixed fields must not leak into public members.
    assert all("_quality_story_key" not in m for m in bundle["data"]["items"])


def test_members_ranked_by_score_for_mini_peek():
    items = [
        _geo_item(1, "Iran enrichment deal?", score=30),
        _geo_item(2, "Hormuz closure?", score=70),
        _geo_item(3, "Iran ceasefire?", score=50),
    ]

    bundle = assemble_geopolitics_theme_bundles(items)[0]

    assert bundle["data"]["member_ids"] == [2, 3, 1]
    assert bundle["score"] == 70


def test_separate_conflicts_make_separate_bundles():
    items = [
        _geo_item(1, "Will Iran close the Strait of Hormuz?"),
        _geo_item(2, "Iran enrichment deal?"),
        _geo_item(3, "Will Russia capture Pokrovsk in Ukraine?"),
        _geo_item(4, "Russia Ukraine ceasefire by year end?"),
    ]

    result = assemble_geopolitics_theme_bundles(items)

    bundles = [it for it in result if it["type"] == "bundle"]
    keys = {b["data"]["story_key"] for b in bundles}
    assert keys == {"story:middle_east_conflict", "story:russia_ukraine"}


def test_singleton_conflict_left_as_individual_card():
    items = [
        _geo_item(1, "Will Iran close the Strait of Hormuz?"),
        _geo_item(2, "Will the Lakers make the playoffs?"),
    ]

    result = assemble_geopolitics_theme_bundles(items)

    assert [it["type"] for it in result] == ["futures", "futures"]
    assert result == items


def test_non_geopolitics_feed_untouched():
    items = [
        _geo_item(1, "Will the Lakers make the playoffs?"),
        {"type": "event", "score": 50, "data": {"id": 9}},
    ]

    assert assemble_geopolitics_theme_bundles(items) == items


# ── Awards / competition theme bundles (Phase 1, slice 3) ─────────────────────

from app.utils.discover_bundles import assemble_awards_theme_bundles


def _award_survivor(
    market_id: int,
    name: str,
    group_id: str,
    siblings: list[dict],
    *,
    score: float | None = None,
    category: str = "entertainment",
) -> dict:
    """A post-dedupe group survivor carrying its dropped siblings (slice-3 shape)."""
    return {
        "type": "futures",
        "score": 95 - market_id if score is None else score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "group_id": group_id,
            "source": "polymarket",
        },
        "_sort_time": 1000 + market_id,
        "_quality_story_key": "internal-should-not-leak",
        "_grouped_members": siblings,
    }


def _award_member(market_id: int, name: str, group_id: str, *, score: float) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": "reason",
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": "entertainment",
            "group_id": group_id,
            "source": "polymarket",
        },
        "_sort_time": 1000 + market_id,
        "_quality_story_key": "internal-should-not-leak",
    }


def test_folds_award_race_group_into_one_bundle():
    gid = "polymarket:531533"
    siblings = [
        _award_member(2, "Will Andrew Scott be nominated for Best Actor?", gid, score=80),
        _award_member(3, "Will Brad Pitt be nominated for Best Actor?", gid, score=70),
    ]
    survivor = _award_survivor(
        1, "Will Adam Driver be nominated for Best Actor?", gid, siblings, score=90
    )
    items = [survivor, {"type": "event", "score": 50, "data": {"id": 9}}]

    result = assemble_awards_theme_bundles(items)

    assert [it["type"] for it in result] == ["bundle", "event"]
    bundle = result[0]
    assert bundle["data"]["kind"] == "theme"
    assert bundle["data"]["group_id"] == gid
    assert bundle["data"]["item_count"] == 3
    assert sorted(bundle["data"]["member_ids"]) == [1, 2, 3]
    # Bundle competes for one slot scored by its best member.
    assert bundle["score"] == 90
    # Members ranked by score for the mini-ranked-peek.
    assert bundle["data"]["member_ids"] == [1, 2, 3]
    # Internal underscore fields must not leak into public members.
    assert all("_quality_story_key" not in m for m in bundle["data"]["items"])
    assert all("_grouped_members" not in m for m in bundle["data"]["items"])


def test_award_bundle_score_is_max_member():
    gid = "polymarket:149775"
    siblings = [_award_member(2, "Will B win album of the year?", gid, score=88)]
    survivor = _award_survivor(1, "Will A win album of the year?", gid, siblings, score=40)
    bundle = assemble_awards_theme_bundles([survivor])[0]
    assert bundle["score"] == 88
    assert bundle["data"]["member_ids"] == [2, 1]  # ranked by score desc


def test_single_member_group_does_not_bundle():
    # No dropped siblings (group had only one feed-eligible member) -> untouched.
    survivor = _award_survivor(
        1, "Will A be nominated for Best Actor?", "polymarket:1", []
    )
    result = assemble_awards_theme_bundles([survivor])
    assert [it["type"] for it in result] == ["futures"]
    assert result == [survivor]


def test_non_entertainment_group_is_not_bundled():
    gid = "polymarket:777"
    siblings = [
        _award_member(2, "Team B to win", gid, score=80),
    ]
    survivor = _award_survivor(
        1, "Team A to win", gid, siblings, score=90, category="basketball"
    )
    result = assemble_awards_theme_bundles([survivor])
    assert [it["type"] for it in result] == ["futures"]


def test_separate_award_races_make_separate_bundles():
    g1, g2 = "polymarket:1", "polymarket:2"
    items = [
        _award_survivor(1, "Will A win Best Picture?", g1,
                        [_award_member(2, "Will B win Best Picture?", g1, score=80)]),
        _award_survivor(3, "Will C be Person of the Year?", g2,
                        [_award_member(4, "Will D be Person of the Year?", g2, score=60)]),
    ]
    result = assemble_awards_theme_bundles(items)
    bundles = [it for it in result if it["type"] == "bundle"]
    assert {b["data"]["group_id"] for b in bundles} == {g1, g2}


def test_dedupe_stashes_grouped_members_for_bundler():
    from app.routes.feed import _dedupe_futures_by_group_id

    gid = "polymarket:531533"
    items = [
        _award_member(1, "Will A be nominated?", gid, score=90),
        _award_member(2, "Will B be nominated?", gid, score=80),
        _award_member(3, "Will C be nominated?", gid, score=70),
    ]
    kept = _dedupe_futures_by_group_id(items)
    # Default-feed behavior unchanged: one survivor per group.
    assert len(kept) == 1
    survivor = kept[0]
    assert survivor["data"]["id"] == 1  # highest score survives
    # Dropped siblings preserved for the awards bundler.
    assert len(survivor["_grouped_members"]) == 2
    assert {m["data"]["id"] for m in survivor["_grouped_members"]} == {2, 3}
