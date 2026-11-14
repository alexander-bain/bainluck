"""#12659 — remove over-broad entertainment caps and false-positive demotions (zero quota, zero boost)."""

import pytest

from app.utils.discover_bundles import (
    AUTHORED_STORY_QUESTIONS,
    AUTHORED_STORY_TITLES,
    assemble_story_theme_bundles,
)
from app.utils.feed_market_quality import (
    classify_market_quality,
    diversify_quality_families,
)
from app.utils.theme_collection_ref import _page_members


def _feed_item(market_id: int, name: str, score: float, category: str = "entertainment") -> dict:
    q = classify_market_quality(name, sport_category=category)
    return {
        "type": "futures",
        "score": score,
        "_rank_score": score,
        "_sort_time": 1000.0 - market_id,
        "reason": name,
        "headline": name,
        "data": {
            "id": market_id,
            "name": name,
            "llm_sport_category": category,
            "canonical_market_key": None,
            "discover_card": {},
        },
        "_quality_class": q.quality_class,
        "_quality_family_key": q.family_key,
        "_quality_story_key": q.story_key,
    }


def test_major_ceremonies_have_independent_story_keys_and_caps():
    cohort = [
        _feed_item(1, "Oscar Winner: Best Picture", 93),
        _feed_item(2, "Oscars 2027: Best Costume Design Winner", 91),
        _feed_item(3, "Oscars 2027: Best Director Winner", 90),
        _feed_item(4, "Grammys 2027: Record of the Year Winner", 89),
        _feed_item(5, "Grammys 2027: Best Pop Solo Performance Winner", 88),
        _feed_item(6, "Grammys 2027: Best Pop Duo/Group Performance Nominations", 87),
        _feed_item(7, "Golden Globes: Best Motion Picture - Drama Winner", 86),
        _feed_item(8, "Golden Globes: Best Television Series - Drama Winner", 85),
        _feed_item(9, "Emmys 2027: Outstanding Drama Series Winner", 84),
        _feed_item(10, "Who will attend The Met Gala?", 83),
    ]

    capped = diversify_quality_families(cohort, exact_family_cap=1, story_family_cap=5)
    by_story: dict[str, list[int]] = {}
    for it in capped:
        by_story.setdefault(it["_quality_story_key"], []).append(it["data"]["id"])

    assert by_story == {
        "story:oscars": [1, 2],
        "story:grammys": [4, 5],
        "story:golden_globes": [7, 8],
        "story:emmys": [9],
        "story:met_gala": [10],
    }


def test_oscars_and_grammys_form_separate_bundles_preventing_62a_grammy_spill():
    """On production (#12659), lumping Oscars + Grammys under one story_key caused
    4 overflow Grammy rows to join the Oscars bundle and then get released as 4
    loose singles at seats #2-#5 when oscars-2027 projected via `_page_members`."""
    cohort = [
        _feed_item(6173044, "Oscar Winner: Best Picture", 93),
        _feed_item(65814225, "Oscars 2027: Best Costume Design Winner", 92),
        _feed_item(69851927, "Grammys 2027: Best Pop Duo/Group Performance Nominations", 88),
        _feed_item(58492245, "Grammys 2027: Record of the Year Winner", 88),
        _feed_item(69851819, "Grammys 2027: Best Pop Solo Performance Winner", 88),
        _feed_item(70244946, "Grammys 2027: Best R&B Collaboration Winner", 88),
    ]
    capped = diversify_quality_families(cohort, exact_family_cap=1, story_family_cap=5)
    bundled = assemble_story_theme_bundles(capped)

    bundles = [it for it in bundled if it["type"] == "bundle"]
    assert [b["data"]["story_key"] for b in bundles] == ["story:oscars", "story:grammys"]
    assert bundles[0]["data"]["title"] == "Oscars"
    assert bundles[1]["data"]["title"] == "Grammys"
    assert set(bundles[1]["data"]["member_ids"]) == {
        69851927,
        58492245,
        69851819,
        70244946,
    }

    # Projecting oscars-2027 onto the pure Oscars bundle releases zero Grammy singles.
    oscars_snapshot = {"shown_ids": [6173044, 65814225], "folded_ids": [], "withheld": {}}
    projected = _page_members(bundles[0], oscars_snapshot)
    assert len(projected) == 1
    assert projected[0]["type"] == "bundle"


def test_music_charts_split_by_chart_with_cap_one_each():
    cohort = [
        _feed_item(11, "#1 on the Billboard Hot 100 chart for the Week of Nov 21?", 90),
        _feed_item(12, "Will Sabrina Carpenter top the Billboard Hot 100?", 89),
        _feed_item(13, "#1 on the Billboard 200 chart this week?", 88),
        _feed_item(14, "Top USA Artist on Spotify on Nov 20, 2026?", 87),
    ]
    capped = diversify_quality_families(cohort, exact_family_cap=1, story_family_cap=5)
    assert [it["data"]["id"] for it in capped] == [11, 13, 14]
    assert [it["_quality_story_key"] for it in capped] == [
        "story:billboard_hot100",
        "story:billboard_200",
        "story:spotify_charts",
    ]


@pytest.mark.parametrize(
    "name",
    [
        "Top song on weekly Spotify Global chart?",
        "Top album on weekly Billboard 200?",
    ],
)
def test_weekly_top_one_song_or_album_winner_is_not_demoted_as_metric(name: str):
    q = classify_market_quality(name, sport_category="entertainment")
    assert q.quality_class == "normal"
    assert "entertainment_metric" not in q.reasons


@pytest.mark.parametrize(
    "name",
    [
        "Alberto Giacometti: Figure, demie grandeur (no. 2) (c. 1949; lot 8A) sale price?",
        "Agnes Martin: Untitled #6 (2002; lot 6) sale price?",
    ],
)
def test_auction_lot_artwork_edition_numbers_do_not_trigger_runner_up_rank(name: str):
    q = classify_market_quality(name, sport_category="entertainment")
    assert "runner_up_rank" not in q.reasons


def test_authored_titles_and_sentences_carry_no_banned_jargon():
    for key in (
        "story:oscars",
        "story:grammys",
        "story:emmys",
        "story:golden_globes",
        "story:met_gala",
        "story:billboard_hot100",
        "story:billboard_200",
        "story:spotify_charts",
    ):
        assert key in AUTHORED_STORY_TITLES
        assert key in AUTHORED_STORY_QUESTIONS
        combined = f"{AUTHORED_STORY_TITLES[key]} {AUTHORED_STORY_QUESTIONS[key]}".lower()
        assert "question" not in combined
        assert "venue" not in combined
        assert "stale" not in combined
