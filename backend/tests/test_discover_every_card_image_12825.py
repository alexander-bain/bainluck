"""Tests for #12825: Discover cards carry verified imagery without mismatched catch-all photos."""

from __future__ import annotations

from app.utils.discover_image_policy import (
    resolve_discover_market_image,
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


def test_domain_fallback_is_positive_match_only_and_never_mismatches_unclassified_or_crypto():
    # Unclassified / crypto / synthetic entities NEVER receive the U.S. Capitol or mismatched stock art
    btc = resolve_discover_market_image(
        name="Will Bitcoin hit 100k?",
        category="crypto",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert btc["image_url"] is None
    assert btc["image_monogram"] is not None

    zorblax = resolve_discover_market_image(
        name="Will Zorblax win the Quizbowl?",
        category=None,
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert zorblax["image_url"] is None
    assert zorblax["image_monogram"] is not None

    # Unregistered person NEVER gets a generic venue photo even on Discover feed serving
    unknown_person = resolve_discover_market_image(
        name="Will Jane Doe resign before December?",
        category="politics",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert unknown_person["image_url"] is None
    assert unknown_person["image_monogram"]["initials"] == "JD"

    # Team matchup in title resolves to the official ESPN team crest, not a generic college arena
    lakers = resolve_discover_market_image(
        name="Will the Lakers beat the Celtics?",
        category="basketball",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert lakers["image_url"] == "https://a.espncdn.com/i/teamlogos/nba/500/lal.png"
    assert lakers["image_presentation"] == "logo"

    # Weather keyword on `unknown` category resolves to weather backdrop (not U.S. Capitol),
    # marked as `"backdrop"` with no entity-art `image_credit`
    rain = resolve_discover_market_image(
        name="Will it rain in NYC on Friday?",
        category="unknown",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert rain["image_url"] is not None
    assert "Lightning_in_Dallas" in rain["image_url"]
    assert rain["image_presentation"] == "backdrop"
    assert "image_credit" not in rain

    # Country-level politics resolves to national flag
    spain = sanitize_discover_feed_item(
        {
            "type": "futures",
            "data": {
                "id": 2001,
                "name": "Next Prime Minister of Spain?",
                "llm_sport_category": "politics",
                "top_outcomes": [{"name": "Alberto Núñez Feijóo", "probability": 0.48}],
            },
        }
    )
    assert spain["data"]["image_url"] == "https://flagcdn.com/w320/es.png"
    assert spain["data"]["image_presentation"] == "logo"

    # Unregistered golfer leader keeps honest golfer monogram rather than generic golf course photo
    golf_card = sanitize_discover_feed_item(
        {
            "type": "tournament",
            "data": {
                "name": "Unseen PGA Classic",
                "golfers": [{"name": "Unregistered Golfer", "probability": 0.14}],
            },
        }
    )
    assert golf_card["data"]["image_url"] is None
    assert golf_card["data"]["image_monogram"]["initials"] == "UG"
    assert golf_card["data"]["image_monogram"]["kind"] == "person"

    # Positively matched generic domain topic gets `"backdrop"` presentation without entity credit
    generic_macro = sanitize_feed_response_images(
        {
            "items": [
                {
                    "type": "futures",
                    "data": {
                        "id": 3001,
                        "name": "U.S. Q4 GDP growth above 2.5%?",
                        "llm_sport_category": "economics",
                        "top_outcomes": [{"name": "Yes", "probability": 0.52}],
                    },
                }
            ]
        }
    )
    assert generic_macro is not None
    gdp = generic_macro["items"][0]["data"]
    assert gdp["image_url"] is not None
    assert gdp["image_presentation"] == "backdrop"
    assert "image_credit" not in gdp


def test_non_sports_place_and_common_word_titles_never_get_team_crests_or_wrong_flags():
    # Weather in Buffalo -> NOAA weather backdrop, NEVER Buffalo Bulls NCAA crest
    buffalo_snow = resolve_discover_market_image(
        name="Will it snow in Buffalo this week?",
        category="weather",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert buffalo_snow["image_url"] is not None
    assert "espncdn.com" not in buffalo_snow["image_url"]
    assert buffalo_snow["image_presentation"] == "backdrop"

    # Politics in Indiana / Toledo -> politics backdrop (or candidate monogram), NEVER Hoosiers / Rockets crests
    indiana_gov = resolve_discover_market_image(
        name="Indiana governor race winner?",
        category="politics",
        top_outcomes=[{"name": "Democratic"}],
        allow_domain_fallback=True,
    )
    assert "espncdn.com" not in (indiana_gov["image_url"] or "")

    toledo_mayor = resolve_discover_market_image(
        name="Mayor of Toledo election",
        category="politics",
        top_outcomes=[{"name": "Incumbent"}],
        allow_domain_fallback=True,
    )
    assert "espncdn.com" not in (toledo_mayor["image_url"] or "")

    # Science / wildlife "bald eagles" -> NEVER Philadelphia Eagles NFL crest
    bald_eagles = resolve_discover_market_image(
        name="Will bald eagles be delisted?",
        category="science",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert "espncdn.com" not in (bald_eagles["image_url"] or "")

    # Economics "China's GDP" with empty category -> economics backdrop, NEVER national flag
    china_gdp = resolve_discover_market_image(
        name="Will China's GDP grow above 5% in 2026?",
        category="",
        top_outcomes=[{"name": "Yes"}],
        allow_domain_fallback=True,
    )
    assert "flagcdn.com" not in (china_gdp["image_url"] or "")
    assert china_gdp["image_presentation"] == "backdrop"

