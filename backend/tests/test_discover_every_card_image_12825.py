"""Tests for #12825: every Discover card carries a verified image (TMDB, logos, Commons, domain fallback)."""

from __future__ import annotations

from app.utils.discover_image_policy import (
    sanitize_discover_feed_item,
    sanitize_feed_response_images,
)


def test_grammys_story_bundle_uses_tmdb_backdrop_and_nominee_portraits():
    grammys_bundle = {
        "type": "bundle",
        "score": 88.0,
        "data": {
            "id": "theme:story:grammys:1-2-3",
            "title": "Grammys",
            "kind": "theme",
            "story_key": "story:grammys",
            "shared_question": "Where do the Grammys races stand?",
            "item_count": 3,
            "member_ids": [1, 2, 3],
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 1,
                        "name": "Grammys 2027: Best Musica Urbana Album Winner",
                        "llm_sport_category": "entertainment",
                        "top_outcomes": [{"name": "Do Not Disturb - Young Miko", "probability": 0.44}],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 2,
                        "name": "Grammys 2027: Best Latin Pop Album Winner",
                        "llm_sport_category": "entertainment",
                        "top_outcomes": [{"name": "No Me Arrepiento de Sentir Tanto - KAROL G", "probability": 0.51}],
                    },
                },
                {
                    "type": "futures",
                    "data": {
                        "id": 3,
                        "name": "Grammys 2027: Best Rap Performance Winner",
                        "llm_sport_category": "entertainment",
                        "top_outcomes": [
                            {"name": "ErrTime - Cardi B", "probability": 0.31},
                            {"name": "Body - Don Toliver", "probability": 0.29},
                        ],
                    },
                },
            ],
        },
    }
    out = sanitize_discover_feed_item(grammys_bundle)
    data = out["data"]
    assert data["image_url"] == "https://image.tmdb.org/t/p/w780/11QwqK3hUCWkLJclPUPzd6tgtxL.jpg"
    assert data["image_credit"] == "TMDB"
    assert data["image_presentation"] == "photo"
    for child in data["items"]:
        assert child["data"]["image_url"] is not None
        assert "wikimedia.org" in child["data"]["image_url"]


def test_coinbase_super_bowl_ad_and_mac_football_cards_carry_verified_images():
    coinbase = sanitize_discover_feed_item(
        {
            "type": "futures",
            "data": {
                "id": 201,
                "name": "Will Coinbase run an Ad during Super Bowl LXI?",
                "llm_sport_category": "football",
                "top_outcomes": [{"name": "Yes", "probability": 0.34}, {"name": "No", "probability": 0.66}],
            },
        }
    )
    assert "SoFi_Stadium" in (coinbase["data"]["image_url"] or "")
    assert coinbase["data"]["image_presentation"] == "photo"
    assert coinbase["data"]["image_author"] == "Prayitno Photography"

    mac = sanitize_discover_feed_item(
        {
            "type": "futures",
            "data": {
                "id": 202,
                "name": "College Football MAC Championship Winner",
                "llm_sport_category": "football",
                "top_outcomes": [{"name": "Western Michigan", "probability": 0.38}, {"name": "Toledo", "probability": 0.31}],
            },
        }
    )
    assert mac["data"]["image_url"] == "https://a.espncdn.com/i/teamlogos/ncaa/500/2711.png"
    assert mac["data"]["image_presentation"] == "logo"


def test_every_discover_domain_guarantees_non_null_image_url_even_for_unseen_markets():
    categories = [
        "football",
        "basketball",
        "baseball",
        "hockey",
        "soccer",
        "golf",
        "mma",
        "entertainment",
        "politics",
        "geopolitics",
        "economics",
        "tech",
        "weather",
        "health",
    ]
    payload = {
        "items": [
            {
                "type": "futures",
                "data": {
                    "id": 1000 + idx,
                    "name": f"Unseen {cat} outlook before December 2027?",
                    "llm_sport_category": cat,
                    "top_outcomes": [{"name": "Yes", "probability": 0.5}],
                },
            }
            for idx, cat in enumerate(categories)
        ]
        + [
            {
                "type": "futures",
                "data": {
                    "id": 2001,
                    "name": "Next Prime Minister of Spain?",
                    "llm_sport_category": "politics",
                    "top_outcomes": [{"name": "Unregistered Candidate One", "probability": 0.48}],
                },
            },
            {
                "type": "tournament",
                "data": {
                    "name": "Unseen PGA Classic",
                    "golfers": [{"name": "Unregistered Golfer Name", "probability": 0.14}],
                },
            },
        ]
    }
    clean = sanitize_feed_response_images(payload)
    assert clean is not None
    for item in clean["items"]:
        img = item["data"].get("image_url")
        assert img and img.startswith("https://"), f"Missing image on {item['data']}"
    spain_card = [it for it in clean["items"] if it["data"].get("id") == 2001][0]
    assert spain_card["data"]["image_url"] == "https://flagcdn.com/w320/es.png"
