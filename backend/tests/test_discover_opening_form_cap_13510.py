"""Tests for Ruling 353: A (#13510) — <= 2 cards per visual form in Discover's first ten."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from httpx import ASGITransport
import pytest

from app.main import app
from app.routes import feed as feed_route
from app.services import get_db
from app.utils import request_cache as req_cache
from app.utils import roundup_containers as rc_mod
from app.utils import theme_collection_ref as theme_ref_mod
from app.utils.discover_opening_mix import (
    OPENING_MIX_MAX_PER_FORM,
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    TOPIC_PWM,
    TOPIC_SPORTS,
    TOPIC_TECH_BUSINESS,
    apply_discover_opening_mix,
    card_visual_form_id,
    classify_discover_opening_topic,
)
from app.utils.roundup_containers import RoundupMembers, RoundupProducer

NOW = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)


def _single(mid: int, name: str, *, category: str, score: float = 82.0) -> dict:
    return {
        "type": "futures",
        "score": score,
        "reason": name,
        "headline": name,
        "data": {
            "id": mid,
            "name": name,
            "status": "open",
            "category": category,
            "llm_sport_category": category,
            "top_outcomes": [{"id": mid * 10, "name": "Yes", "probability": 0.52}],
        },
    }


def _roundup(
    slug: str,
    title: str,
    *,
    category: str,
    kicker: str,
    member_id: int,
    form_id: str | None = None,
    score: float = 90.0,
) -> dict:
    roundup_block: dict = {
        "tag": "roundup",
        "level": "member",
        "kicker": kicker,
        "footer": "Test footer",
        "relations": ["same_subject"],
        "rows": [{"label": f"Option {member_id}", "percent": 55, "href": f"/futures/{member_id}"}],
    }
    if form_id is not None:
        roundup_block["machinery_card"] = {"form_id": form_id}
    return {
        "type": "bundle",
        "score": score,
        "reason": title,
        "headline": title,
        "data": {
            "id": slug,
            "kind": "roundup",
            "title": title,
            "category": category,
            "llm_sport_category": category,
            "roundup": roundup_block,
            "items": [
                {
                    "type": "futures",
                    "score": score,
                    "data": {
                        "id": member_id,
                        "name": title,
                        "status": "open",
                        "category": category,
                        "llm_sport_category": category,
                        "top_outcomes": [{"id": member_id * 10, "name": "Yes", "probability": 0.55}],
                    },
                }
            ],
        },
    }


def _concept(slug: str = "concept-world-cup", title: str = "World Cup 2026 Hub") -> dict:
    return {
        "type": "concept",
        "score": 99.0,
        "data": {
            "id": slug,
            "key": slug,
            "slug": slug,
            "name": title,
            "title": title,
            "status": "upcoming",
        },
    }


def _top10_form_counts(items: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for it in items[:10]:
        fid = card_visual_form_id(it)
        if fid is not None:
            counts[fid] += 1
    return counts


def test_cap_two_per_form_moves_third_down_and_preserves_topic_mix() -> None:
    items = [
        _roundup("machinery-elon-musk-side-quests", "Mars trip in 2026", category="Science", kicker="ODD", member_id=101, form_id="benchmark_strip", score=99),
        _roundup("machinery-who-gets-engaged", "Actor breakup market", category="Entertainment", kicker="CULTURE", member_id=102, form_id="benchmark_strip", score=98),
        _roundup("machinery-google-year-in-search-2026", "Most searched actor", category="Entertainment", kicker="ODD", member_id=103, form_id="benchmark_strip", score=97),
        _roundup("machinery-stage-and-cover", "Spotify top artist", category="Entertainment", kicker="CULTURE", member_id=104, form_id="benchmark_strip", score=96),
        _roundup("machinery-long-shots", "Aliens confirmed by 2029", category="Politics", kicker="ODD", member_id=105, form_id="benchmark_strip", score=95),
        _roundup("machinery-space-race", "Space race to Moon", category="Tech", kicker="TECH", member_id=106, form_id="benchmark_strip", score=94),
        _concept(),
        _single(9001, "NBA Champion 2027", category="Sports", score=93),
        _roundup("machinery-oscars-best-picture", "Best Picture front-runners", category="Entertainment", kicker="CULTURE", member_id=107, form_id="paired_stage_bars", score=90),
        _roundup("machinery-next-james-bond", "James Bond theme odds", category="Entertainment", kicker="CULTURE", member_id=108, form_id="sibling_fields_grid", score=89),
        _roundup("machinery-white-christmas", "White Christmas cities", category="Weather", kicker="ODD", member_id=109, form_id="paired_stage_bars", score=88),
        _roundup("machinery-big-championships-2027", "CFB title contenders", category="Sports", kicker="SPORTS", member_id=110, form_id="contender_spotlight", score=87),
        _roundup("machinery-ai-model-leaderboard-2026", "Open source AI release", category="Tech", kicker="TECH", member_id=111, form_id="sibling_fields_grid", score=86),
        _roundup("machinery-ai-and-big-tech-race", "AI hardware leaders", category="Tech", kicker="TECH", member_id=112, form_id="matchup_slate", score=85),
        _roundup("machinery-fed-and-macro", "January Fed decision", category="Economics", kicker="ECONOMY", member_id=113, form_id="contender_spotlight", score=84),
    ]
    before_ids = {it["data"]["id"] for it in items}

    result = apply_discover_opening_mix(items, now=NOW)

    assert len(result) == len(items)
    assert {it["data"]["id"] for it in result} == before_ids

    top10_forms = _top10_form_counts(result)
    assert max(top10_forms.values()) <= OPENING_MIX_MAX_PER_FORM
    assert top10_forms["benchmark_strip"] == 2

    top10_topics = Counter(classify_discover_opening_topic(it) for it in result[:10])
    assert top10_topics[TOPIC_ODD] == 3
    assert top10_topics[TOPIC_ENTERTAINMENT] >= 2
    assert top10_topics[TOPIC_SPORTS] == 2
    assert top10_topics[TOPIC_TECH_BUSINESS] >= 1
    assert top10_topics[TOPIC_PWM] <= 1
    assert all(it.get("type") != "concept" for it in result[:10])

    tail_benchmarks = [
        it["data"]["id"]
        for it in result[10:]
        if card_visual_form_id(it) == "benchmark_strip"
    ]
    assert len(tail_benchmarks) == 4


def test_seat10_pwm_form_counts_toward_cap_of_two() -> None:
    items = [
        _roundup("machinery-elon-musk-side-quests", "Mars trip", category="Science", kicker="ODD", member_id=201, form_id="contender_spotlight", score=99),
        _roundup("machinery-long-shots", "Alien confirmation", category="Science", kicker="ODD", member_id=202, form_id="contender_spotlight", score=98),
        _roundup("machinery-pop-culture-oddities", "Christmas song chart", category="Entertainment", kicker="ODD", member_id=203, form_id="paired_stage_bars", score=97),
        _roundup("machinery-white-christmas", "White Christmas forecast", category="Weather", kicker="ODD", member_id=204, form_id="sibling_fields_grid", score=96),
        _roundup("machinery-oscars-best-picture", "Best Picture", category="Entertainment", kicker="CULTURE", member_id=205, form_id="paired_stage_bars", score=95),
        _roundup("machinery-stage-and-cover", "Top Album", category="Entertainment", kicker="CULTURE", member_id=206, form_id="sibling_fields_grid", score=94),
        _roundup("machinery-big-championships-2027", "World Cup winner", category="Sports", kicker="SPORTS", member_id=207, form_id="matchup_slate", score=93),
        _roundup("machinery-ai-model-leaderboard-2026", "Next chip launch", category="Tech", kicker="TECH", member_id=208, form_id="benchmark_strip", score=92),
        _roundup("machinery-big-tech-deals-hardware", "Autonomous taxi city", category="Tech", kicker="TECH", member_id=209, form_id="benchmark_strip", score=91),
        _roundup("machinery-fed-and-macro", "Fed cuts rates", category="Economics", kicker="ECONOMY", member_id=210, form_id="contender_spotlight", score=90),
        _single(9002, "MLB World Series", category="Sports", score=89),
    ]

    result = apply_discover_opening_mix(items, now=NOW)
    top10_forms = _top10_form_counts(result)
    assert top10_forms["contender_spotlight"] <= OPENING_MIX_MAX_PER_FORM
    assert card_visual_form_id(result[9]) == "contender_spotlight"


def test_fewer_than_ten_cards_preserves_all_without_dropping() -> None:
    items = [
        _roundup("machinery-elon-musk-side-quests", "Mars trip", category="Science", kicker="ODD", member_id=301, form_id="benchmark_strip", score=99),
        _roundup("machinery-who-gets-engaged", "Actor market", category="Entertainment", kicker="CULTURE", member_id=302, form_id="benchmark_strip", score=98),
        _roundup("machinery-long-shots", "Aliens", category="Science", kicker="ODD", member_id=303, form_id="benchmark_strip", score=97),
        _roundup("machinery-ai-model-leaderboard-2026", "Claude release", category="Tech", kicker="TECH", member_id=304, form_id="benchmark_strip", score=96),
        _roundup("machinery-oscars-best-picture", "Best Picture", category="Entertainment", kicker="CULTURE", member_id=305, form_id="paired_stage_bars", score=95),
        _roundup("machinery-big-championships-2027", "Super Bowl", category="Sports", kicker="SPORTS", member_id=306, form_id="sibling_fields_grid", score=94),
        _single(9003, "NHL Playoffs", category="Sports", score=93),
    ]
    result = apply_discover_opening_mix(items, now=NOW)
    assert len(result) == len(items)
    assert [it["data"]["id"] for it in result] == [it["data"]["id"] for it in items]


def test_single_form_only_is_noop_and_does_not_empty_page() -> None:
    items = [
        _roundup("machinery-elon-musk-side-quests", "Mars trip", category="Science", kicker="ODD", member_id=401, form_id="benchmark_strip", score=99),
        _roundup("machinery-long-shots", "Aliens", category="Science", kicker="ODD", member_id=402, form_id="benchmark_strip", score=98),
        _roundup("machinery-google-year-in-search-2026", "Top searched", category="Novelty", kicker="ODD", member_id=403, form_id="benchmark_strip", score=97),
        _roundup("machinery-who-gets-engaged", "Top artist", category="Entertainment", kicker="CULTURE", member_id=404, form_id="benchmark_strip", score=96),
        _roundup("machinery-stage-and-cover", "Best Actor", category="Entertainment", kicker="CULTURE", member_id=405, form_id="benchmark_strip", score=95),
        _roundup("machinery-big-championships-2027", "Heisman race", category="Sports", kicker="SPORTS", member_id=406, form_id="benchmark_strip", score=94),
        _roundup("machinery-space-race", "Moon landing", category="Tech", kicker="TECH", member_id=407, form_id="benchmark_strip", score=93),
        _roundup("machinery-ai-model-leaderboard-2026", "AI leader", category="Tech", kicker="TECH", member_id=408, form_id="benchmark_strip", score=92),
        _roundup("machinery-fed-and-macro", "Fed decision", category="Economics", kicker="ECONOMY", member_id=409, form_id="benchmark_strip", score=91),
        _single(9004, "Stanley Cup", category="Sports", score=90),
        _single(9005, "Backup single", category="Entertainment", score=80),
    ]
    result = apply_discover_opening_mix(items, now=NOW)
    assert len(result) == len(items)
    assert len(result[:10]) == 10
    assert _top10_form_counts(result)["benchmark_strip"] == 9


def test_thin_two_form_supply_maximizes_variety_then_fills_without_dropping() -> None:
    items = [
        _roundup("machinery-elon-musk-side-quests", "Mars trip", category="Science", kicker="ODD", member_id=501, form_id="benchmark_strip", score=99),
        _roundup("machinery-long-shots", "Aliens", category="Science", kicker="ODD", member_id=502, form_id="benchmark_strip", score=98),
        _roundup("machinery-white-christmas", "Snow storm", category="Weather", kicker="ODD", member_id=503, form_id="benchmark_strip", score=97),
        _roundup("machinery-who-gets-engaged", "Celebrity news", category="Entertainment", kicker="CULTURE", member_id=504, form_id="benchmark_strip", score=96),
        _roundup("machinery-stage-and-cover", "Top artist", category="Entertainment", kicker="CULTURE", member_id=505, form_id="benchmark_strip", score=95),
        _roundup("machinery-big-championships-2027", "Heisman", category="Sports", kicker="SPORTS", member_id=506, form_id="benchmark_strip", score=94),
        _roundup("machinery-space-race", "Moon race", category="Tech", kicker="TECH", member_id=507, form_id="benchmark_strip", score=93),
        _roundup("machinery-fed-and-macro", "Fed rates", category="Economics", kicker="ECONOMY", member_id=508, form_id="benchmark_strip", score=92),
        _roundup("machinery-ai-model-leaderboard-2026", "AI release", category="Tech", kicker="TECH", member_id=509, form_id="contender_spotlight", score=85),
        _roundup("machinery-oscars-best-picture", "Best Picture", category="Entertainment", kicker="CULTURE", member_id=510, form_id="contender_spotlight", score=84),
        _single(9006, "World Series", category="Sports", score=80),
        _single(9007, "MVP futures", category="Sports", score=79),
    ]
    result = apply_discover_opening_mix(items, now=NOW)
    assert len(result) == len(items)
    top10_forms = _top10_form_counts(result)
    assert top10_forms["contender_spotlight"] == 2
    assert sum(1 for it in result[:10] if it.get("type") == "bundle") == 9


async def test_feed_endpoint_machinery_caps_visual_forms_at_two_e2e(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end HTTP proof through GET /api/feed?machinery=1 (1.0.7 rule)."""

    def _make_producer(
        slug: str,
        title: str,
        *,
        category: str,
        kicker: str,
        member_id: int,
        form_id: str,
        score: float,
    ) -> RoundupProducer:
        async def _produce(_db, *, now=None):
            return RoundupMembers(
                members=[
                    {
                        "type": "market",
                        "id": member_id,
                        "destination": f"/futures/{member_id}",
                        "card": {"id": member_id, "name": title},
                    }
                ],
                rows=[
                    {
                        "market_id": member_id,
                        "outcome_id": member_id * 10,
                        "label": title,
                        "probability": 0.55,
                    }
                ],
                title=title,
                kicker=kicker,
                footer="E2E test",
                destination_href=f"/collections/{slug}",
                machinery_card={"form_id": form_id},
                covered_market_ids=(member_id,),
            )

        return RoundupProducer(
            slug=slug,
            name=title,
            kind="roundup",
            category=category,
            section_title=title,
            footer="E2E test",
            kicker=kicker,
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            score=score,
            stage="public",
            enabled=lambda: True,
            produce=_produce,
        )

    synthetic_specs = [
        ("machinery-elon-musk-side-quests", "Mars trip by 2030", "Science", "ODD", 601, "benchmark_strip", 99.0),
        ("machinery-who-gets-engaged", "Celebrity wedding", "Entertainment", "CULTURE", 602, "benchmark_strip", 98.0),
        ("machinery-google-year-in-search-2026", "Most searched star", "Entertainment", "ODD", 603, "benchmark_strip", 97.0),
        ("machinery-stage-and-cover", "Spotify top artist", "Entertainment", "CULTURE", 604, "benchmark_strip", 96.0),
        ("machinery-long-shots", "UAP disclosure", "Politics", "ODD", 605, "benchmark_strip", 95.0),
        ("machinery-space-race", "Blue Origin Moon", "Tech", "TECH", 606, "benchmark_strip", 94.0),
        ("machinery-oscars-best-picture", "The Odyssey Best Picture", "Entertainment", "CULTURE", 607, "paired_stage_bars", 90.0),
        ("machinery-next-james-bond", "Bond Theme frontrunner", "Entertainment", "CULTURE", 608, "sibling_fields_grid", 89.0),
        ("machinery-white-christmas", "White Christmas forecast", "Weather", "ODD", 609, "paired_stage_bars", 88.0),
        ("machinery-big-championships-2027", "College Football playoff", "Sports", "SPORTS", 610, "contender_spotlight", 87.0),
        ("machinery-ai-model-leaderboard-2026", "Next frontier LLM", "Tech", "TECH", 611, "sibling_fields_grid", 86.0),
        ("machinery-ai-and-big-tech-race", "Big tech leaders", "Tech", "TECH", 612, "matchup_slate", 85.0),
        ("machinery-fed-and-macro", "January Fed decision", "Economics", "ECONOMY", 613, "contender_spotlight", 84.0),
    ]
    synthetic_producers = {
        spec[0]: _make_producer(
            spec[0],
            spec[1],
            category=spec[2],
            kicker=spec[3],
            member_id=spec[4],
            form_id=spec[5],
            score=spec[6],
        )
        for spec in synthetic_specs
    }

    plain_base_items = [
        _concept(),
        *[
            _single(9900 + i, f"2027 Season Futures Market {i}", category="Sports", score=92.0 - i)
            for i in range(1, 18)
        ],
    ]
    plain_base_payload = {
        "items": plain_base_items,
        "total": len(plain_base_items),
        "limit": 40,
        "offset": 0,
        "has_more": False,
        "built_at": time.time(),
        "cache": {"status": "hit", "live": False},
    }

    async def _fake_read_cache_pair(_client, _key):
        return req_cache.RedisResult(req_cache.MISS), req_cache.RedisResult(req_cache.MISS)

    async def _fake_read_shared(_client, key: str):
        if "machinery_pagebase" in key:
            return None, None
        return json.dumps(plain_base_payload), "shared_hit"

    class _DummyRedis:
        async def get(self, _k):
            return None

        async def mget(self, keys):
            return [None] * len(keys)

        async def set(self, *_a, **_kw):
            return True

        async def setex(self, *_a, **_kw):
            return True

    async def _dummy_db():
        yield SimpleNamespace(execute=AsyncMock(), scalars=AsyncMock())

    monkeypatch.setattr(feed_route, "_DISCOVER_OPENING_SEATING_SERVED", True)
    monkeypatch.setattr(feed_route, "feed_page_base_enabled", lambda: True)
    monkeypatch.setattr(feed_route, "_read_feed_cache_pair", _fake_read_cache_pair)
    monkeypatch.setattr(feed_route, "_read_shared_feed_cache", _fake_read_shared)
    monkeypatch.setattr(req_cache, "get_shared_async_redis", AsyncMock(return_value=_DummyRedis()))
    monkeypatch.setattr(
        req_cache,
        "schedule_background",
        lambda coro: coro.close() if hasattr(coro, "close") else None,
    )
    monkeypatch.setattr(theme_ref_mod, "read_published_themes", AsyncMock(return_value=None))
    async def _fake_eval(prod, _db, *, now=None, **_kw):
        return (
            rc_mod.compose_roundup_feed_item(prod, await prod.produce(_db, now=now)),
            {"slug": prod.slug},
        )

    monkeypatch.setattr(rc_mod, "ensure_optional_roundup_candidates", lambda: None)
    monkeypatch.setattr(rc_mod, "roundup_feed_enabled", lambda **_kw: True)
    monkeypatch.setattr(rc_mod, "evaluate_roundup_producer", _fake_eval)
    monkeypatch.setattr(rc_mod, "ROUNDUP_PRODUCERS", synthetic_producers)

    prior_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _dummy_db
    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            resp = await client.get("/api/feed", params={"machinery": "1", "limit": 40})
    finally:
        app.dependency_overrides = prior_overrides

    assert resp.status_code == 200, resp.text
    body = resp.json()
    served = body["items"]
    assert len(served) == 31  # 13 machinery roundups + 17 singles + 1 concept preserved

    top10_forms = _top10_form_counts(served)
    assert max(top10_forms.values()) <= OPENING_MIX_MAX_PER_FORM
    assert top10_forms["benchmark_strip"] == 2
    assert all(it.get("type") != "concept" for it in served[:10])

    displaced_benchmarks = [
        it for it in served[10:] if card_visual_form_id(it) == "benchmark_strip"
    ]
    assert len(displaced_benchmarks) == 4


def test_sports_single_plus_grouped_never_exceeds_two_via_sparse_fallback() -> None:
    """#13542 / 329: A: a chosen sports single counts toward TOPIC_SPORTS <= 2, and
    when 353: A form caps leave <8 grouped seats after Pass 2, sparse fallback must
    not admit a 3rd sports card (`matchup_strip` / schedule) over non-sports groups."""
    deck = [
        # Three odd cards all using benchmark_strip -> 3rd blocks in Pass 1b/2 until form cap relaxes
        _roundup("machinery-elon-musk-side-quests", "Musk side quests", category="Science", kicker="ODD", member_id=101, form_id="benchmark_strip", score=99.0),
        _roundup("machinery-long-shots", "Long shots", category="Entertainment", kicker="ODD · LONG SHOTS", member_id=102, form_id="benchmark_strip", score=98.0),
        _roundup("machinery-white-christmas", "White Christmas forecast", category="Weather", kicker="WEATHER · CHRISTMAS", member_id=103, form_id="benchmark_strip", score=94.0),
        # Sports single chosen by chosen_singles -> sports=1
        _single(68948432, "Milwaukee Brewers NL West", category="Baseball", score=97.0),
        # Two entertainment cards (different forms)
        _roundup("machinery-next-james-bond", "Next James Bond", category="Entertainment", kicker="CULTURE", member_id=104, form_id="sibling_fields_grid", score=96.0),
        _roundup("machinery-oscars-best-picture", "Oscars Best Picture", category="Entertainment", kicker="CULTURE", member_id=105, form_id="paired_stage_bars", score=95.0),
        # First sports grouped card -> sports=2 (now at TOPIC_MAX_TOTAL[TOPIC_SPORTS] == 2)
        _roundup("machinery-grand-slam-tennis", "Grand Slam Tennis", category="Tennis", kicker="SPORTS", member_id=106, form_id="theme_compact_rows", score=93.0),
        # Second sports grouped card (distinct form matchup_strip) — MUST NOT push sports to 3!
        _roundup("celtics-next-3-games", "Boston Celtics: next 3 games", category="Basketball", kicker="SPORTS", member_id=107, form_id="matchup_strip", score=92.0),
        _roundup("lakers-next-3-games", "Los Angeles Lakers: next 3 games", category="Basketball", kicker="SPORTS", member_id=108, form_id="matchup_strip", score=91.0),
        # Tech & PWM groups (same theme_compact_rows form -> blocked until form cap relaxes)
        _roundup("machinery-tech-movers", "Tech movers", category="Tech", kicker="TECH", member_id=109, form_id="probability_history_chart", score=90.0),
        _roundup("story-ai-bundle", "AI leaders", category="Tech", kicker="TECH", member_id=110, form_id="theme_compact_rows", score=89.0),
        _roundup("story-middle-east", "Middle East conflict", category="Politics", kicker="WORLD", member_id=111, form_id="theme_compact_rows", score=88.0),
    ]
    mixed = apply_discover_opening_mix(deck, now=NOW)
    top10 = mixed[:10]
    sports_items = [it for it in top10 if classify_discover_opening_topic(it) == TOPIC_SPORTS]
    assert len(sports_items) == 2
    assert any((it.get("data") or {}).get("id") == 68948432 for it in sports_items)


def test_truly_empty_non_sports_deck_still_fills_ten_without_dropping_sports() -> None:
    """Only when no non-sports grouped cards exist at all may the final fallback admit a 3rd sports card."""
    deck = [
        _single(701, "Brewers NL West", category="Baseball", score=99.0),
        *[
            _roundup(f"sports-strip-{i}", f"Team Next 3 Games {i}", category="Basketball", kicker="SPORTS", member_id=710 + i, form_id="matchup_strip", score=95.0 - i)
            for i in range(9)
        ],
        _roundup("world-politics", "Middle East conflict", category="Politics", kicker="WORLD", member_id=730, form_id="theme_compact_rows", score=85.0),
    ]
    mixed = apply_discover_opening_mix(deck, now=NOW)
    assert len(mixed[:10]) == 10
