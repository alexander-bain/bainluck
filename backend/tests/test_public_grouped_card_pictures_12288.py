"""Tests for public grouped card pictures (Fable #12288 Items 1 & 2).

Verifies:
- Next James Bond, Oscars Best Picture, 2028 Presidential, and Fed & Macro each
  carry a verified Public Domain or CC0 object/place picture with alt text,
  credit, author, license, and source page.
- First-party `/api/containers/machinery-2028-presidential/card-art.jpg` serves
  the cropped White House JPEG under 250 KB.
- NBA Night and NFL Week remain without a banner photo (their rows already
  carry team crests).
- No set's stage is changed by this PR.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.utils.container_machinery import (
    discover_machinery_candidate_paths,
    load_machinery_definition,
)
from app.utils.discover_image_policy import (
    _REGISTER_PATH,
    sanitize_discover_feed_item,
)

PICTURED_PUBLIC_SLUGS = (
    "machinery-next-james-bond",
    "machinery-oscars-best-picture",
    "machinery-2028-presidential",
    "machinery-fed-and-macro",
)

CREST_SLATE_SLUGS = (
    "machinery-nba-night",
    "machinery-nfl-week",
)


def test_four_public_grouped_cards_have_verified_pd_or_cc0_pictures_and_credits() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    register_doc = json.loads(_REGISTER_PATH.read_text(encoding="utf-8"))
    allowed_hosts = set(register_doc.get("allowed_hosts") or [])
    verified_urls = {
        str(entry.get("url") or "").strip()
        for entry in (register_doc.get("entries") or [])
        if isinstance(entry, dict)
    }
    fe_register = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "lib"
        / "discover"
        / "verifiedDiscoverArt.json"
    )
    assert fe_register.read_bytes() == _REGISTER_PATH.read_bytes()
    for slug in PICTURED_PUBLIC_SLUGS:
        assert slug in paths_by_slug
        defn = load_machinery_definition(paths_by_slug[slug])
        rule = defn["rule"]
        url = str(rule.get("card_image_url") or "").strip()
        assert url.startswith("https://")
        assert any(host in url for host in allowed_hosts)
        assert url in verified_urls, f"{slug} URL not in verified_discover_art.json: {url}"
        assert rule.get("suppress_card_photo") is True
        assert str(rule.get("card_image_alt") or "").strip()
        assert str(rule.get("card_image_credit") or "").strip()
        assert str(rule.get("card_image_author") or "").strip()
        lic = str(rule.get("card_image_license") or "").lower()
        assert "cc0" in lic or "public domain" in lic
        assert str(rule.get("card_image_source_page") or "").startswith(
            "https://commons.wikimedia.org/wiki/File:"
        )
        # Sanitizer must preserve the explicit verified card picture on Discover.
        fake_item = {
            "type": "bundle",
            "data": {
                "title": defn["name"],
                "image_url": url,
                "roundup": {
                    "machinery_card": {
                        "slug": slug,
                        "image_url": url,
                        "image_alt": rule["card_image_alt"],
                        "image_credit": rule["card_image_credit"],
                    }
                },
            },
        }
        sanitized = sanitize_discover_feed_item(fake_item)
        assert sanitized["data"]["image_url"] == url
        assert sanitized["data"]["roundup"]["machinery_card"]["image_url"] == url


def test_nba_night_and_nfl_week_keep_crest_rows_without_banner_picture() -> None:
    paths_by_slug = {p.stem: p for p in discover_machinery_candidate_paths()}
    for slug in CREST_SLATE_SLUGS:
        defn = load_machinery_definition(paths_by_slug[slug])
        assert not defn["rule"].get("card_image_url")


def test_2028_presidential_first_party_card_art_route_serves_jpeg_under_250kb() -> None:
    client = TestClient(app)
    resp = client.get("/api/containers/machinery-2028-presidential/card-art.jpg")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content.startswith(b"\xff\xd8\xff")
    assert len(resp.content) <= 250_000
    assert "max-age=" in resp.headers.get("cache-control", "")
