"""Tests for #13103 Part 3 item 3 — server-picked `more_sets` below a container page."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupProducer,
    _roundup_local_cache,
    reset_roundup_cache_for_tests,
    select_more_sets,
    serve_roundup,
    summarize_more_set_card,
)


def _published_payload(
    slug: str,
    name: str,
    *,
    category: str = "sports",
    subtitle: str = "Why these markets belong together.",
    member_type: str = "market",
    card: dict[str, Any] | None = None,
    member_count: int = 3,
    state: str = "published",
) -> dict[str, Any]:
    if card is None:
        card = {
            "id": 101,
            "name": "College Football Playoff Qualifiers",
            "status": "open",
            "updated_at": "2026-11-19T18:00:00+00:00",
            "top_outcomes": [
                {"id": 1, "name": "Tennessee", "probability": 0.645},
                {"id": 2, "name": "Texas Tech", "probability": 0.515},
            ],
        }
    return {
        "slug": slug,
        "state": state,
        "revision": 1,
        "subtitle": subtitle,
        "member_count": member_count,
        "container": {
            "id": 1000,
            "slug": slug,
            "name": name,
            "kind": "roundup",
            "category": category,
            "status": "open",
        },
        "sections": [
            {
                "key": "0:roundup",
                "class": "roundup",
                "title": name,
                "count": 1,
                "members": [
                    {
                        "id": 101,
                        "type": member_type,
                        "card": card,
                        "destination": {
                            "kind": member_type,
                            "id": 101,
                            "web": f"/{'events' if member_type == 'event' else 'futures'}/101",
                            "api": f"/api/{'events' if member_type == 'event' else 'futures'}/101",
                        },
                    }
                ],
            }
        ],
    }


def test_summarize_more_set_card_extracts_real_lead_and_date() -> None:
    card = summarize_more_set_card(
        _published_payload("roundup-cfp-picture", "College Football Playoff picture", category="ncaaf")
    )
    assert card is not None
    assert card["slug"] == "roundup-cfp-picture"
    assert card["name"] == "College Football Playoff picture"
    assert card["href"] == "/collections/roundup-cfp-picture"
    assert card["destination"]["web"] == "/collections/roundup-cfp-picture"
    assert card["member_count"] == 3
    assert card["lead_label"] == "Tennessee"
    assert card["lead_probability"] == 0.645
    assert card["as_of"] == "2026-11-19T18:00:00+00:00"
    assert card["dek"] == "Why these markets belong together."


def test_summarize_more_set_card_uses_market_name_for_yes_no_outcome() -> None:
    binary_card = {
        "id": 202,
        "name": "Fed cuts rates in December",
        "status": "open",
        "updated_at": "2026-11-19T15:30:00+00:00",
        "top_outcomes": [
            {"id": 10, "name": "Yes", "probability": 0.72},
            {"id": 11, "name": "No", "probability": 0.28},
        ],
    }
    card = summarize_more_set_card(
        _published_payload(
            "roundup-this-weeks-economic-data",
            "This week's economic data",
            category="economics",
            card=binary_card,
        )
    )
    assert card is not None
    assert card["lead_label"] == "Fed cuts rates in December"
    assert card["lead_probability"] == 0.72
    assert card["as_of"] == "2026-11-19T15:30:00+00:00"


def test_summarize_more_set_card_extracts_event_favorite_and_rejects_unpublished() -> None:
    event_card = {
        "id": 303,
        "home_team": "Boston Celtics",
        "away_team": "New York Knicks",
        "status": "scheduled",
        "commence_time": "2026-11-20T00:30:00+00:00",
        "current_odds": {
            "home_win_probability": 0.61,
            "away_win_probability": 0.39,
            "updated_at": "2026-11-19T20:00:00+00:00",
        },
    }
    card = summarize_more_set_card(
        _published_payload(
            "roundup-closest-games-tonight",
            "Closest games tonight",
            category="nba",
            member_type="event",
            card=event_card,
            member_count=4,
        )
    )
    assert card is not None
    assert card["lead_label"] == "Boston Celtics"
    assert card["lead_probability"] == 0.61
    assert card["as_of"] == "2026-11-19T20:00:00+00:00"

    assert summarize_more_set_card(
        _published_payload("unpublished-set", "Hidden", state="unpublished")
    ) is None
    assert summarize_more_set_card(
        _published_payload("empty-set", "Empty", member_count=0) | {"sections": []}
    ) is None


@pytest.mark.asyncio
async def test_select_more_sets_prefers_diverse_categories_excludes_related_and_caps_at_two() -> None:
    reset_roundup_cache_for_tests()
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        fake_db = object()
        now_ts = time.time()

        specs = [
            ("set-sports-current", "Current sports set", "sports"),
            ("set-sports-parent", "Parent sports set", "sports"),
            ("set-sports-other", "Other sports set", "sports"),
            ("set-economics", "Fed & inflation watch", "economics"),
            ("set-entertainment", "Awards frontrunners", "entertainment"),
            ("machinery-preview-x", "Internal preview", "politics"),
            ("for-scale-snow-dc", "For scale internal", "weather"),
        ]
        for slug, name, cat in specs:
            ROUNDUP_PRODUCERS[slug] = RoundupProducer(
                slug=slug,
                name=name,
                category=cat,
                section_title=name,
                footer="",
                produce=lambda _db: RoundupMembers(()),
            )
            payload = _published_payload(slug, name, category=cat)
            _roundup_local_cache[(slug, id(fake_db))] = (now_ts, {"type": "roundup"}, payload)

        picked = await select_more_sets(
            fake_db,
            exclude_slugs={"set-sports-current", "set-sports-parent"},
            current_category="sports",
            now=now_ts,
        )
        assert len(picked) == 2
        slugs = [p["slug"] for p in picked]
        assert "set-sports-current" not in slugs
        assert "set-sports-parent" not in slugs
        assert "machinery-preview-x" not in slugs
        assert "for-scale-snow-dc" not in slugs
        assert set(slugs) == {"set-economics", "set-entertainment"}
        assert len({p["category"] for p in picked}) == 2
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()


@pytest.mark.asyncio
async def test_select_more_sets_fails_open_on_slow_or_broken_candidates() -> None:
    reset_roundup_cache_for_tests()
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        fake_db = object()

        async def _slow(_db: Any) -> Any:
            await asyncio.sleep(5.0)
            return None

        def _boom(_db: Any) -> Any:
            raise RuntimeError("boom")

        ROUNDUP_PRODUCERS["broken-a"] = RoundupProducer(
            slug="broken-a",
            name="Broken A",
            category="politics",
            section_title="Broken A",
            footer="",
            produce=_boom,
        )
        ROUNDUP_PRODUCERS["slow-b"] = RoundupProducer(
            slug="slow-b",
            name="Slow B",
            category="weather",
            section_title="Slow B",
            footer="",
            produce=_slow,
        )

        picked = await select_more_sets(
            fake_db,
            exclude_slugs=set(),
            budget_seconds=0.06,
            evaluate_uncached=True,
        )
        assert picked == []
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()


@pytest.mark.asyncio
async def test_serve_roundup_attaches_more_sets_excluding_self() -> None:
    reset_roundup_cache_for_tests()
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        fake_db = object()
        now_ts = time.time()
        p_main = _published_payload("set-main", "Main Set", category="sports")
        p_other = _published_payload("set-other", "Other Set", category="economics")

        for slug, name, cat, pl in [
            ("set-main", "Main Set", "sports", p_main),
            ("set-other", "Other Set", "economics", p_other),
        ]:
            ROUNDUP_PRODUCERS[slug] = RoundupProducer(
                slug=slug,
                name=name,
                category=cat,
                section_title=name,
                footer="",
                produce=lambda _db: RoundupMembers(()),
            )
            _roundup_local_cache[(slug, id(fake_db))] = (now_ts, {"type": "roundup"}, pl)

        served = await serve_roundup("set-main", fake_db, now=now_ts)
        assert isinstance(served.get("more_sets"), list)
        assert [m["slug"] for m in served["more_sets"]] == ["set-other"]
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()
