"""Tests for Ruling 317: B — White Christmas server-rendered U.S. snow-chance map."""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.routes.containers import _MAP_PNG_CACHE, get_container_map_png
from app.utils.container_machinery import (
    load_machinery_definition,
)
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


def test_white_christmas_definition_stays_preview_and_points_to_map() -> None:
    defn = load_machinery_definition(
        "data/groupings/candidates/machinery-white-christmas.json"
    )
    assert defn["stage"] == "preview"
    assert defn["rule"]["card_image_url"] == WHITE_CHRISTMAS_MAP_URL
    assert defn["rule"]["suppress_card_photo"] is True


@pytest.mark.asyncio
async def test_container_map_png_route_serves_png_and_404s_unknown_slug() -> None:
    from fastapi import HTTPException

    _MAP_PNG_CACHE.clear()
    with pytest.raises(HTTPException) as exc:
        await get_container_map_png(slug="machinery-fed-and-macro", db=AsyncMock())
    assert exc.value.status_code == 404

    with patch(
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
    ):
        resp = await get_container_map_png(
            slug="machinery-white-christmas", db=AsyncMock()
        )
    assert resp.media_type == "image/png"
    assert resp.headers.get("Cache-Control") == "public, max-age=300"
    img = Image.open(io.BytesIO(resp.body))
    assert img.size == (1080, 540)
