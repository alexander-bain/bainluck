"""Tests for Discover image truth policy, verified art register, and monogram fallback (#12659)."""

from __future__ import annotations

from app.routes.feed import _publish_feed_item
from app.utils.discover_image_policy import (
    BLOCKED_PEXELS_PHOTO_IDS,
    classify_market_visual_subject,
    compute_initials,
    dedup_discover_tournament_items,
    is_blocked_pexels_photo,
    resolve_discover_market_image,
    sanitize_feed_response_images,
)


def test_person_never_receives_stock_photo_and_uses_verified_portrait_or_monogram():
    # Verified person: Jensen Huang replaces sci-fi lab coat stock photo (#8728168)
    res_jensen = resolve_discover_market_image(
        name="Will Jensen Huang publicly testify before Congress by June 30?",
        category="tech",
        top_outcomes=[{"name": "Yes"}, {"name": "No"}],
        image_url="https://images.pexels.com/photos/11460276/pexels-photo-11460276.jpeg?h=350",
    )
    assert res_jensen["image_url"] is not None
    assert "wikimedia.org" in res_jensen["image_url"]
    assert "Jensen_Huang" in res_jensen["image_url"]
    assert res_jensen["image_presentation"] == "portrait"
    assert res_jensen["image_monogram"] is None

    # Unregistered person: stock photo cleared, deterministic initials on colour emitted
    res_unknown_person = resolve_discover_market_image(
        name="Will Jane Doe resign before December?",
        category="politics",
        top_outcomes=[{"name": "Yes"}, {"name": "No"}],
        image_url="https://images.pexels.com/photos/999999/pexels-photo-999999.jpeg?h=350",
    )
    assert res_unknown_person["image_url"] is None
    assert res_unknown_person["image_monogram"] is not None
    assert res_unknown_person["image_monogram"]["initials"] == "JD"
    assert res_unknown_person["image_monogram"]["kind"] == "person"


def test_song_never_wears_tmdb_film_backdrop_or_stock_photo():
    # Grammy Song of the Year led by Ella Langley gets Cover Art Archive sleeve
    res_grammy = resolve_discover_market_image(
        name="69th Annual Grammy Awards: Song of the Year?",
        category="entertainment",
        top_outcomes=[{"name": "Choosin' Texas - Ella Langley", "probability": 0.42}],
        image_url="https://images.pexels.com/photos/8044086/pexels-photo-8044086.jpeg?h=350",
    )
    assert res_grammy["image_url"] is not None
    assert "archive.org" in res_grammy["image_url"]
    assert res_grammy["image_presentation"] == "cover"

    # Unregistered music market wearing a TMDB movie backdrop drops it for song monogram
    res_gta_album = resolve_discover_market_image(
        name="Who will be featured on GTA VI: The Album?",
        category="entertainment",
        top_outcomes=[{"name": "Unknown Artist XYZ", "probability": 0.25}],
        image_url="https://image.tmdb.org/t/p/w780/wrong-movie-backdrop.jpg",
    )
    assert res_gta_album["image_url"] is None
    assert res_gta_album["image_monogram"] is not None
    assert res_gta_album["image_monogram"]["kind"] == "song"


def test_team_receives_official_crest_instead_of_stock_photo():
    res_nhl = resolve_discover_market_image(
        name="2026 NHL Stanley Cup Champion?",
        category="hockey",
        top_outcomes=[{"name": "Carolina Hurricanes", "probability": 0.21}],
        image_url="https://images.pexels.com/photos/12345/pexels-photo-12345.jpeg?h=350",
    )
    assert res_nhl["image_url"] == "https://a.espncdn.com/i/teamlogos/nhl/500/car.png"
    assert res_nhl["image_presentation"] == "logo"
    assert res_nhl["image_monogram"] is None


def test_film_without_verified_poster_drops_stock_for_initials_on_colour():
    res_odyssey = resolve_discover_market_image(
        name='"The Odyssey" Rotten Tomatoes score?',
        category="entertainment",
        top_outcomes=[{"name": "Above 85", "probability": 0.64}],
        image_url="https://images.pexels.com/photos/55555/pexels-photo-55555.jpeg?h=350",
    )
    assert res_odyssey["image_url"] is None
    assert res_odyssey["image_monogram"] is not None
    assert res_odyssey["image_monogram"]["kind"] == "film"
    assert res_odyssey["image_monogram"]["initials"] == "OD"


def test_all_15_audited_bad_pexels_ids_blocked_even_on_topic_markets():
    assert len(BLOCKED_PEXELS_PHOTO_IDS) >= 15
    for pid in BLOCKED_PEXELS_PHOTO_IDS:
        bad_url = f"https://images.pexels.com/photos/{pid}/pexels-photo-{pid}.jpeg?h=350"
        assert is_blocked_pexels_photo(bad_url)
        res = resolve_discover_market_image(
            name="Generic macro topic",
            category="economics",
            top_outcomes=[{"name": "Yes"}],
            image_url=bad_url,
        )
        assert res["image_url"] is None


def test_non_blocked_topic_market_preserves_existing_photo_and_dimensions():
    topic_url = "https://images.pexels.com/photos/16082426/pexels-photo-16082426.jpeg?auto=compress&cs=tinysrgb&h=650&w=940"
    res = resolve_discover_market_image(
        name="Will the incumbent win the 2026 election?",
        category="politics",
        top_outcomes=[{"name": "Yes"}],
        image_url=topic_url,
        image_width=940,
        image_height=650,
    )
    assert res["image_url"] == topic_url
    assert res["image_width"] == 940
    assert res["image_height"] == 650
    assert res["image_monogram"] is None


def test_compute_initials_cleanly_handles_tickers_companies_and_noise():
    assert compute_initials("How high will Alphabet Inc. (GOOGL) go in 2026?") == "GOOGL"
    assert compute_initials("Will Apple (AAPL) close above $260?") == "AAPL"
    assert compute_initials("Kimi (Moonshot AI) IPO before 2027?") == "KM"
    assert compute_initials("Anthropic IPO Closing Market Cap") == "AN"
    assert compute_initials("Will Kroger beat Q3 2026 quarterly earnings?") == "KR"
    assert compute_initials("Next James Bond announced before 2027?", ticker_ok=False) == "JB"
    assert classify_market_visual_subject("Will Apple (AAPL) close above $260?", "economics", []).kind == "organization"


def test_twin_annika_golf_tournament_dedup_collapses_duplicate_cards():
    t1 = {
        "type": "tournament",
        "score": 48.0,
        "reason": "Hye-Jin Choi leads",
        "headline": "LPGA",
        "data": {
            "name": "The ANNIKA driven by Gainbridge at Pelican",
            "venue": "Pelican Golf Club",
            "source_count": 2,
            "start_date": "2026-11-12",
            "golfers": [{"name": "Hye-Jin Choi", "probability": 0.24}, {"name": "Nelly Korda", "probability": 0.19}],
        },
        "_blended_market_ids": frozenset({101}),
    }
    t2 = {
        "type": "tournament",
        "score": 46.5,
        "reason": "Hye-Jin Choi leads",
        "headline": "LPGA",
        "data": {
            "name": "The ANNIKA",
            "venue": None,
            "source_count": 1,
            "start_date": "2026-11-12",
            "golfers": [{"name": "Hye-Jin Choi", "probability": 0.24}, {"name": "Nelly Korda", "probability": 0.19}],
        },
        "_blended_market_ids": frozenset({102}),
    }
    deduped = dedup_discover_tournament_items([t1, t2])
    assert len(deduped) == 1
    assert deduped[0]["data"]["name"] == "The ANNIKA driven by Gainbridge at Pelican"
    assert deduped[0]["_blended_market_ids"] == frozenset({101, 102})


def test_publish_feed_item_and_response_sanitizer_enforce_image_truth():
    item = {
        "type": "futures",
        "score": 82.0,
        "reason": "Moved today",
        "headline": "",
        "_internal_flag": True,
        "data": {
            "id": 9001,
            "name": "Bloomberg IPO before 2027?",
            "llm_sport_category": "economics",
            "top_outcomes": [{"name": "Yes", "probability": 0.18}],
            "image_url": "https://images.pexels.com/photos/6289061/pexels-photo-6289061.jpeg?h=350",
            "image_width": 525,
            "image_height": 350,
        },
    }
    _publish_feed_item(item)
    assert "_internal_flag" not in item
    assert "Bloomberg_Tower" in (item["data"]["image_url"] or "")
    assert item["data"]["image_monogram"] is None

    cached_payload = {
        "items": [
            {
                "type": "tournament",
                "score": 50.0,
                "reason": "",
                "headline": "",
                "data": {
                    "name": "Butterfield Bermuda Championship",
                    "golfers": [{"name": "Trace Crowe", "probability": 0.16}],
                },
            }
        ],
        "total": 1,
    }
    sanitized = sanitize_feed_response_images(cached_payload)
    assert sanitized is not None
    assert sanitized["items"][0]["data"]["image_url"] == "https://a.espncdn.com/i/headshots/golf/players/full/11183.png"
    assert sanitized["items"][0]["data"]["image_presentation"] == "portrait"
