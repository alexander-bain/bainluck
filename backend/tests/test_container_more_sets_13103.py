"""Tests for #13103 Part 3 item 3 — server-picked `more_sets` below a container page."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
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

FIXED_NOW = datetime(2026, 11, 20, 2, 0, 0, tzinfo=timezone.utc)
FRESH_ISO = (FIXED_NOW - timedelta(hours=2)).isoformat()
OLD_ISO = (FIXED_NOW - timedelta(hours=26)).isoformat()


def _published_payload(
    slug: str,
    name: str,
    *,
    category: str = "sports",
    subtitle: str = "Why these markets belong together.",
    member_type: str = "market",
    card: dict[str, Any] | None = None,
    extra_members: list[dict[str, Any]] | None = None,
    member_count: int = 3,
    state: str = "published",
) -> dict[str, Any]:
    if card is None:
        card = {
            "id": 101,
            "name": "Oscars Best Picture Winner",
            "status": "open",
            "price_observed_at": FRESH_ISO,
            "top_outcomes": [
                {"id": 2, "name": "Dune: Messiah", "probability": 0.21},
                {"id": 1, "name": "The Odyssey", "probability": 0.535},
            ],
        }
    members: list[dict[str, Any]] = [
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
    ]
    if extra_members:
        members.extend(extra_members)
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
                "count": len(members),
                "members": members,
            }
        ],
    }


def test_summarize_more_set_card_extracts_fresh_highest_outcome_and_date() -> None:
    card = summarize_more_set_card(
        _published_payload("roundup-oscars-best-picture", "Oscars Best Picture", category="entertainment"),
        now=FIXED_NOW,
    )
    assert card is not None
    assert card["slug"] == "roundup-oscars-best-picture"
    assert card["name"] == "Oscars Best Picture"
    assert card["href"] == "/collections/roundup-oscars-best-picture"
    assert card["destination"]["web"] == "/collections/roundup-oscars-best-picture"
    assert card["member_count"] == 3
    # Highest-probability outcome from first row, not unsorted index 0
    assert card["lead_label"] == "The Odyssey"
    assert card["lead_probability"] == 0.535
    assert card["as_of"] == FRESH_ISO


def test_summarize_more_set_card_rejects_old_or_undated_first_row_and_never_skips_to_row_two() -> None:
    old_first_card = {
        "id": 101,
        "name": "Old First Market",
        "status": "open",
        "price_observed_at": OLD_ISO,
        "top_outcomes": [{"id": 1, "name": "Yes", "probability": 0.50}],
    }
    fresh_second_member = {
        "id": 102,
        "type": "market",
        "card": {
            "id": 102,
            "name": "Fresh Second Market",
            "status": "open",
            "price_observed_at": FRESH_ISO,
            "top_outcomes": [{"id": 2, "name": "Yes", "probability": 0.78}],
        },
        "destination": {"kind": "market", "id": 102, "web": "/futures/102", "api": "/api/futures/102"},
    }
    # Row 0 is 26h old while row 1 is 2h old -> must NOT skip to row 1; set is not offered.
    assert (
        summarize_more_set_card(
            _published_payload(
                "by-november-30",
                "By November 30",
                card=old_first_card,
                extra_members=[fresh_second_member],
            ),
            now=FIXED_NOW,
        )
        is None
    )

    # Undated first row -> must NOT be offered.
    undated_card = {
        "id": 103,
        "name": "Undated Market",
        "status": "open",
        "top_outcomes": [{"id": 3, "name": "Jeeno Thitikul", "probability": 0.21}],
    }
    assert (
        summarize_more_set_card(
            _published_payload("golf-this-week", "Golf this week", card=undated_card),
            now=FIXED_NOW,
        )
        is None
    )


def test_summarize_more_set_card_uses_yes_probability_with_market_name_for_binary_markets() -> None:
    binary_card = {
        "id": 202,
        "name": "Next Claude Opus (5.6+) released by December 31, 2026?",
        "status": "open",
        "price_observed_at": FRESH_ISO,
        "top_outcomes": [
            {"id": 11, "name": "No", "probability": 0.22},
            {"id": 10, "name": "Yes", "probability": 0.78},
        ],
    }
    card = summarize_more_set_card(
        _published_payload(
            "by-december-31",
            "By December 31",
            category="cross-topic",
            card=binary_card,
        ),
        now=FIXED_NOW,
    )
    assert card is not None
    assert card["lead_label"] == "Next Claude Opus (5.6+) released by December 31, 2026?"
    assert card["lead_probability"] == 0.78
    assert card["as_of"] == FRESH_ISO


def test_summarize_more_set_card_reads_event_hero_probability_and_rejects_unpublished() -> None:
    event_card = {
        "id": 303,
        "home_team": "Sacramento Kings",
        "away_team": "Boston Celtics",
        "status": "scheduled",
        "commence_time": "2026-11-22T03:00:00+00:00",
        "hero_probability": 0.1175,
        "hero_probability_away": 0.8825,
        "hero_probability_observed_at": FRESH_ISO,
    }
    card = summarize_more_set_card(
        _published_payload(
            "celtics-next-3-games",
            "Celtics' next 3 games",
            category="nba",
            member_type="event",
            card=event_card,
            member_count=3,
        ),
        now=FIXED_NOW,
    )
    assert card is not None
    assert card["lead_label"] == "Boston Celtics"
    assert card["lead_probability"] == 0.8825
    assert card["as_of"] == FRESH_ISO

    assert (
        summarize_more_set_card(
            _published_payload("unpublished-set", "Hidden", state="unpublished"),
            now=FIXED_NOW,
        )
        is None
    )
    assert (
        summarize_more_set_card(
            _published_payload("empty-set", "Empty", member_count=0) | {"sections": []},
            now=FIXED_NOW,
        )
        is None
    )


@pytest.mark.asyncio
async def test_select_more_sets_respects_machinery_gate_freshness_and_diversity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_roundup_cache_for_tests()
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        fake_db = object()
        now_ts = FIXED_NOW.timestamp()

        specs = [
            ("set-sports-current", "Current sports set", "sports", FRESH_ISO),
            ("set-sports-parent", "Parent sports set", "sports", FRESH_ISO),
            ("set-economics", "Fed & inflation watch", "economics", FRESH_ISO),
            ("set-stale-old", "Old stale set", "weather", OLD_ISO),
            ("machinery-fed-and-macro", "Fed & Macro", "politics", FRESH_ISO),
            ("for-scale-snow-dc", "For scale internal", "weather", FRESH_ISO),
        ]
        for slug, name, cat, obs in specs:
            ROUNDUP_PRODUCERS[slug] = RoundupProducer(
                slug=slug,
                name=name,
                category=cat,
                section_title=name,
                footer="",
                produce=lambda _db: RoundupMembers(()),
            )
            c = {
                "id": 101,
                "name": name,
                "status": "open",
                "price_observed_at": obs,
                "top_outcomes": [{"id": 1, "name": "Leader", "probability": 0.62}],
            }
            payload = _published_payload(slug, name, category=cat, card=c)
            _roundup_local_cache[(slug, id(fake_db))] = (now_ts, {"type": "roundup"}, payload)

        # With machinery switch OFF: machinery-fed-and-macro is excluded; only 1 fresh non-excluded set exists.
        monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "false")
        picked_off = await select_more_sets(
            fake_db,
            exclude_slugs={"set-sports-current", "set-sports-parent"},
            current_slug="set-sports-current",
            current_category="sports",
            now=FIXED_NOW,
        )
        assert [p["slug"] for p in picked_off] == ["set-economics"]

        # With machinery switch ON: machinery-fed-and-macro becomes eligible and fills slot 2.
        monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
        picked_on = await select_more_sets(
            fake_db,
            exclude_slugs={"set-sports-current", "set-sports-parent"},
            current_slug="set-sports-current",
            current_category="sports",
            now=FIXED_NOW,
        )
        assert set(p["slug"] for p in picked_on) == {"set-economics", "machinery-fed-and-macro"}
        assert "set-stale-old" not in [p["slug"] for p in picked_on]
        assert "for-scale-snow-dc" not in [p["slug"] for p in picked_on]
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
            current_slug="any-set",
            budget_seconds=0.06,
            now=FIXED_NOW,
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
        now_ts = FIXED_NOW.timestamp()
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

        served = await serve_roundup("set-main", fake_db, now=FIXED_NOW)
        assert isinstance(served.get("more_sets"), list)
        assert [m["slug"] for m in served["more_sets"]] == ["set-other"]
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)
        reset_roundup_cache_for_tests()
