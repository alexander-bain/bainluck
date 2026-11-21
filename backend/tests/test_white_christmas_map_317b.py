"""Tests for Ruling 317: B — White Christmas server-rendered U.S. snow-chance map."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.routes.containers import (
    _MAP_PNG_CACHE,
    get_container_card_art_jpg,
    get_container_map_png,
)
from app.utils.container_machinery import (
    build_container_machinery_producer,
    load_machinery_definition,
    produce_container_machinery,
)
from app.utils.discover_image_policy import sanitize_discover_feed_item
from app.utils.roundup_containers import compose_roundup_feed_item
from app.utils.white_christmas_map import (
    WHITE_CHRISTMAS_CITIES,
    WHITE_CHRISTMAS_MAP_URL,
    extract_white_christmas_city_probs,
    load_us_outline,
    match_city_key,
    render_white_christmas_map_png,
)


def test_us_outline_is_public_domain_natural_earth_with_valid_polygon() -> None:
    outline = load_us_outline()
    assert "Natural Earth" in outline["source"]
    assert "Public Domain" in outline["license"]
    poly = outline["polygon"]
    assert len(poly) >= 150
    lons = [p[0] for p in poly]
    lats = [p[1] for p in poly]
    assert -126.0 < min(lons) < -123.0
    assert -68.5 < max(lons) < -66.0
    assert 24.0 < min(lats) < 26.0
    assert 48.5 < max(lats) < 50.0


def test_all_11_white_christmas_cities_match_and_render_dynamic_shading() -> None:
    assert len(WHITE_CHRISTMAS_CITIES) == 11
    sample_titles = [
        ("Will it snow in Pittsburgh on Christmas?", "pittsburgh", 0.44),
        ("Will it snow in Minneapolis on Christmas?", "minneapolis", 0.42),
        ("Will it snow in Milwaukee on Christmas?", "milwaukee", 0.40),
        ("Will it snow in Detroit on Christmas?", "detroit", 0.38),
        ("Will it snow in Chicago on Christmas?", "chicago", 0.35),
        ("Will it snow in Denver on Christmas?", "denver", 0.30),
        ("Will it snow in Boston on Christmas?", "boston", 0.22),
        ("Will it snow in NYC on Christmas?", "nyc", 0.20),
        ("Will it snow in Philadelphia on Christmas?", "philadelphia", 0.16),
        ("Will it snow in DC on Christmas?", "dc", 0.13),
        ("Will it snow in Seattle on Christmas?", "seattle", 0.10),
    ]
    members = []
    for title, expected_key, prob in sample_titles:
        assert match_city_key(title) == expected_key
        members.append(
            {
                "card": {
                    "name": title,
                    "top_outcomes": [{"name": "Above 0 inches", "probability": prob}],
                }
            }
        )

    extracted = extract_white_christmas_city_probs(members)
    assert len(extracted) == 11
    assert extracted["pittsburgh"] == pytest.approx(0.44)
    assert extracted["seattle"] == pytest.approx(0.10)

    png_a = render_white_christmas_map_png(extracted)
    img_a = Image.open(io.BytesIO(png_a))
    assert img_a.format == "PNG"
    assert img_a.size == (1080, 540)

    # Changing probabilities changes marker shading bytes.
    flipped = {k: (0.10 if v > 0.30 else 0.45) for k, v in extracted.items()}
    png_b = render_white_christmas_map_png(flipped)
    assert png_a != png_b


def test_white_christmas_definition_is_public_and_points_to_map() -> None:
    defn = load_machinery_definition(
        "data/groupings/candidates/machinery-white-christmas.json"
    )
    assert defn["stage"] == "public"
    assert defn["rule"]["card_image_url"] == WHITE_CHRISTMAS_MAP_URL
    assert defn["rule"]["suppress_card_photo"] is True


@pytest.mark.asyncio
async def test_container_map_png_route_serves_png_and_404s_unknown_slug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException
    from app.utils.roundup_containers import ROUNDUP_PRODUCERS

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "1")
    _MAP_PNG_CACHE.clear()
    with pytest.raises(HTTPException) as exc:
        await get_container_map_png(slug="machinery-fed-and-macro", db=AsyncMock())
    assert exc.value.status_code == 404

    with (
        patch.dict(ROUNDUP_PRODUCERS, dict(ROUNDUP_PRODUCERS), clear=True),
        patch(
            "app.utils.roundup_containers._load_last_good_roundup_copy",
            new=AsyncMock(
                return_value=(
                    {},
                    {
                        "sections": [
                            {
                                "members": [
                                    {
                                        "card": {
                                            "name": "Will it snow in Pittsburgh on Christmas?",
                                            "top_outcomes": [
                                                {"name": "Above 0 inches", "probability": 0.44}
                                            ],
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    5.0,
                    1800.0,
                )
            ),
        ),
    ):
        resp = await get_container_map_png(
            slug="machinery-white-christmas", db=AsyncMock()
        )
    assert resp.media_type == "image/png"
    assert resp.headers.get("Cache-Control") == "public, max-age=300"
    assert "machinery-white-christmas" in _MAP_PNG_CACHE
    img = Image.open(io.BytesIO(resp.body))
    assert img.size == (1080, 540)


def test_fallback_map_omits_lower_higher_legend_bar() -> None:
    """When no live snow chances are supplied, leave the qualitative scale bar off."""
    live_png = render_white_christmas_map_png({"pittsburgh": 0.44, "seattle": 0.10})
    fallback_png = render_white_christmas_map_png({})

    live_img = Image.open(io.BytesIO(live_png))
    fallback_img = Image.open(io.BytesIO(fallback_png))

    # Bottom-left legend bar band (1080x540 coordinates: x=145..268, y=500..512).
    # In live mode the gradient bar is brightly drawn; in fallback mode it is plain ocean background.
    live_band = [
        live_img.getpixel((x, 506)) for x in range(150, 265, 5)
    ]
    fallback_band = [
        fallback_img.getpixel((x, 506)) for x in range(150, 265, 5)
    ]
    # Bright cyan/snow pixels appear on the live gradient bar, never on the fallback ocean strip.
    assert max(r + g + b for r, g, b in live_band) > 550
    assert max(r + g + b for r, g, b in fallback_band) < 200


@pytest.mark.asyncio
async def test_fallback_map_is_not_cached_and_returns_no_store() -> None:
    """Fallback draws must not be kept in memory or HTTP caches for 5 minutes."""
    _MAP_PNG_CACHE.clear()
    with (
        patch(
            "app.utils.roundup_containers._load_last_good_roundup_copy",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.utils.roundup_containers.ROUNDUP_PRODUCERS",
            {"machinery-white-christmas": AsyncMock(load=AsyncMock(return_value=None))},
        ),
    ):
        resp = await get_container_map_png(
            slug="machinery-white-christmas", db=AsyncMock()
        )
    assert resp.media_type == "image/png"
    assert resp.headers.get("Cache-Control") == "no-store"
    assert "machinery-white-christmas" not in _MAP_PNG_CACHE


@pytest.mark.asyncio
async def test_who_gets_engaged_ring_candidate_b_wired_with_source_and_licence() -> None:
    """Decision 318 (Candidate B): Rawpixel #5906428 CC0 ring wired on Who Gets Engaged."""
    from datetime import datetime, timezone
    from fastapi import HTTPException

    defn = load_machinery_definition(
        "data/groupings/candidates/machinery-who-gets-engaged.json"
    )
    assert defn["stage"] == "public"
    assert (
        defn["rule"]["card_image_url"]
        == "https://api.bainluck.com/api/containers/machinery-who-gets-engaged/card-art.jpg"
    )
    assert defn["rule"]["card_image_license"] == "CC0 1.0 Public Domain"
    assert (
        defn["rule"]["card_image_source_page"]
        == "https://www.rawpixel.com/image/5906428/ring-free-public-domain-cc0-photo"
    )

    resp = await get_container_card_art_jpg(slug="machinery-who-gets-engaged")
    assert resp.media_type == "image/jpeg"
    assert resp.headers.get("Cache-Control") == "public, max-age=86400"
    img = Image.open(io.BytesIO(resp.body))
    assert img.format == "JPEG"
    assert img.size == (1024, 683)

    with pytest.raises(HTTPException) as exc:
        await get_container_card_art_jpg(slug="machinery-white-christmas")
    assert exc.value.status_code == 404

    db = {
        "events": [],
        "markets": [
            {
                "id": 109618,
                "name": "Sydney Sweeney and Scooter Braun: Engaged this year?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "image_url": "https://images.pexels.com/photos/123/pexels-photo-123.jpeg",
                "outcomes": [{"id": 1, "name": "Yes", "probability": 0.35}],
            },
            {
                "id": 109385,
                "name": "Timothée Chalamet and Kylie Jenner: Engaged in 2026?",
                "status": "open",
                "source": "kalshi",
                "category": "entertainment",
                "outcomes": [{"id": 2, "name": "Yes", "probability": 0.13}],
            },
            {
                "id": 113658,
                "name": "Katy Perry and Justin Trudeau engaged by end of 2026?",
                "status": "open",
                "source": "polymarket",
                "category": "other",
                "outcomes": [{"id": 3, "name": "Yes", "probability": 0.07}],
            },
        ],
        "paired_sets": {},
        "market_histories": {},
    }
    prod = build_container_machinery_producer(defn)
    res = await produce_container_machinery(
        db, defn, now=datetime(2026, 11, 21, 14, 0, tzinfo=timezone.utc)
    )
    assert res.machinery_card["image_url"] == defn["rule"]["card_image_url"]
    assert res.machinery_card["image_license"] == "CC0 1.0 Public Domain"
    assert res.machinery_card["image_source_page"] == defn["rule"]["card_image_source_page"]
    assert res.sections[0]["visual_block"]["hero_image_url"] == defn["rule"]["card_image_url"]
    assert res.sections[0]["visual_block"]["hero_image_license"] == "CC0 1.0 Public Domain"

    feed_item = compose_roundup_feed_item(prod, res)
    sanitized = sanitize_discover_feed_item(feed_item)
    assert sanitized["data"]["image_url"] == defn["rule"]["card_image_url"]
    assert sanitized["data"]["image_license"] == "CC0 1.0 Public Domain"
    assert sanitized["data"]["image_source_page"] == defn["rule"]["card_image_source_page"]
    for sub in sanitized["data"]["items"]:
        assert sub["data"]["image_url"] is None
