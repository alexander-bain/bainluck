"""#12288 Pre-switch rulings: 252: A, 253: A, live-slate headings, and strict game-page pair parity.

Guards the four pre-switch requirements confirmed on #12288 (Wed Nov 18, 2026):
1. Ruling 252: A — website + iOS 1.0.7+ opt in via `machinery=1`; older apps
   (1.0.6's exact `/api/feed` query without `machinery=1`) NEVER receive any of
   the five machinery groupings even when `CONTAINER_MACHINERY_SLICE1_ENABLED=true`,
   while both share one single prewarmed base cache key (0 ms extra prewarm cost).
2. Ruling 253: A — "Toss-up" means neither side above 55%. One general rule in
   code (no per-grouping JSON edits). Headline counts ONLY games inside the band.
   With fewer than 2 inside the band, section becomes "Closest games", rows carry
   no TOSS-UP tag (`show_toss_up_tag=False`, `form_id="matchup_slate"`), and the
   headline drops the toss-up count.
3. Games-in-play dynamic section headings — all live -> "Live Now", live+upcoming
   -> "Live & Upcoming Matchups", all upcoming -> "Upcoming Matchups".
4. Exact game-page pair & strict parity check — Ravens at Panthers (14969890,
   0.435/0.565 -> 43%/57%) prints 43%/57% (never 44%/57%), populates
   `current_odds.away_rendered_percent` & `home_rendered_percent`, and
   `_compute_member_number_parity` FAILS when a row prints 44 against 43 or when
   `current_odds` omits `away_rendered_percent`/`home_rendered_percent`.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.routes import feed as feed_route
from app.utils import container_machinery as cm
from app.utils.feed_cache import (
    FEED_PAGE_BASE_CACHE_PREFIX,
    feed_page_base_cache_key,
    feed_response_cache_key,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupProducer,
    add_roundup_feed_items,
    compose_roundup_container,
    compose_roundup_feed_item,
)

CANDIDATES_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "groupings" / "candidates"
)


def _ev(
    eid: int,
    away: str,
    home: str,
    away_p: float,
    home_p: float,
    *,
    commence: str = "2026-11-22T18:00:00+00:00",
    status: str = "scheduled",
    sport: str = "americanfootball_nfl",
    include_rendered_in_odds: bool = True,
) -> dict[str, Any]:
    co: dict[str, Any] = {
        "home_probability": home_p,
        "away_probability": away_p,
    }
    if include_rendered_in_odds:
        from app.utils.draw_priced_winner import printable_away
        from app.utils.graded_card import rendered_duel_percents

        ap_c = printable_away(away_p, home_p, sport)
        a_pct, h_pct = rendered_duel_percents(ap_c, home_p)
        co["away_rendered_percent"] = int(a_pct)
        co["home_rendered_percent"] = int(h_pct)
    return {
        "id": eid,
        "sport": sport,
        "sport_name": "NFL" if "nfl" in sport else "NBA",
        "away_team": away,
        "home_team": home,
        "commence_time": commence,
        "status": status,
        "hero_probability": home_p,
        "hero_probability_away": away_p,
        "current_odds": co,
    }


def _nfl_aux_markets() -> list[dict[str, Any]]:
    return [
        {
            "id": 9101,
            "name": "NFL Passing Touchdowns Leader",
            "status": "open",
            "source": "kalshi",
            "category": "football",
            "top_outcomes": [
                {"id": 1, "name": "Josh Allen", "probability": 0.34, "rendered_percent": 34},
                {"id": 2, "name": "Lamar Jackson", "probability": 0.28, "rendered_percent": 28},
                {"id": 3, "name": "Jared Goff", "probability": 0.18, "rendered_percent": 18},
            ],
        },
        {
            "id": 9102,
            "name": "NFL Rushing Touchdowns Leader",
            "status": "open",
            "source": "kalshi",
            "category": "football",
            "top_outcomes": [
                {"id": 4, "name": "Derrick Henry", "probability": 0.42, "rendered_percent": 42},
                {"id": 5, "name": "Saquon Barkley", "probability": 0.26, "rendered_percent": 26},
                {"id": 6, "name": "Jahmyr Gibbs", "probability": 0.19, "rendered_percent": 19},
            ],
        },
        {
            "id": 9103,
            "name": "NFL MVP Winner",
            "status": "open",
            "source": "kalshi",
            "category": "football",
            "top_outcomes": [
                {"id": 7, "name": "Josh Allen", "probability": 0.38, "rendered_percent": 38},
                {"id": 8, "name": "Lamar Jackson", "probability": 0.31, "rendered_percent": 31},
                {"id": 9, "name": "Saquon Barkley", "probability": 0.14, "rendered_percent": 14},
            ],
        },
        {
            "id": 9104,
            "name": "NFC North Champion",
            "status": "open",
            "source": "kalshi",
            "category": "football",
            "top_outcomes": [
                {"id": 10, "name": "Detroit Lions", "probability": 0.56, "rendered_percent": 56},
                {"id": 11, "name": "Minnesota Vikings", "probability": 0.28, "rendered_percent": 28},
                {"id": 12, "name": "Green Bay Packers", "probability": 0.16, "rendered_percent": 16},
            ],
        },
        {
            "id": 9105,
            "name": "AFC North Champion",
            "status": "open",
            "source": "kalshi",
            "category": "football",
            "top_outcomes": [
                {"id": 13, "name": "Baltimore Ravens", "probability": 0.54, "rendered_percent": 54},
                {"id": 14, "name": "Pittsburgh Steelers", "probability": 0.36, "rendered_percent": 36},
                {"id": 15, "name": "Cincinnati Bengals", "probability": 0.10, "rendered_percent": 10},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# 1. Ruling 252: A — 1.0.6 exact feed shape gets ZERO machinery groupings
# ---------------------------------------------------------------------------


def test_252a_response_key_isolates_machinery_while_page_base_stays_single() -> None:
    """1.0.6 (machinery=False) keeps its byte-identical response key and shares
    one single page-base key with website/1.0.7+ (machinery=True)."""
    resp_106_default = feed_response_cache_key(limit=50, offset=0, mode="discover")
    resp_106_explicit = feed_response_cache_key(
        limit=50, offset=0, mode="discover", machinery=False
    )
    resp_107_optin = feed_response_cache_key(
        limit=50, offset=0, mode="discover", machinery=True
    )
    assert resp_106_default == resp_106_explicit
    assert resp_106_default != resp_107_optin
    # Base key has no machinery parameter at all -> 0 extra prewarm keys.
    base_entry = feed_page_base_cache_key(limit=50, mode="discover")
    assert base_entry.startswith("feed_cache:")


@pytest.mark.asyncio
async def test_252a_add_roundup_feed_items_hides_machinery_from_106_and_splices_for_107(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CONTAINER_MACHINERY_SLICE1_ENABLED=true, default add_roundup_feed_items
    (1.0.6 / prewarm base) emits zero machinery-* cards; include_machinery=True
    splices them in cleanly."""
    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")

    async def _fake_produce(db: Any, *, now: Any = None) -> RoundupMembers:
        return RoundupMembers(
            members=[
                {
                    "type": "market",
                    "id": 101,
                    "destination": "/futures/101",
                    "card": {"id": 101, "name": "Test Market"},
                }
            ],
            rows=[
                {
                    "market_id": 101,
                    "outcome_id": 1,
                    "label": "Outcome A",
                    "probability": 0.60,
                    "rendered_percent": 60,
                }
            ],
            title="Machinery NFL Test",
            kicker="NFL · THIS SLATE",
            destination_href="/collections/machinery-nfl-week",
        )

    fake_machinery_producer = RoundupProducer(
        slug="machinery-nfl-week",
        name="NFL Slate",
        kind="roundup",
        category="football",
        section_title="Closest games",
        footer="",
        produce=_fake_produce,
        membership="computed-produced",
        relations=("same_event",),
        level="member",
        rule={"producer": "container_machinery"},
        enabled=lambda: True,
    )
    saved = dict(ROUNDUP_PRODUCERS)
    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS["machinery-nfl-week"] = fake_machinery_producer
        monkeypatch.setattr(
            "app.utils.roundup_containers.ensure_optional_roundup_candidates",
            lambda: None,
        )

        base_items = [
            {"type": "futures", "id": f"f-{i}", "data": {"id": 500 + i}}
            for i in range(15)
        ]

        def _extract_machinery_slugs(feed_list: list[dict[str, Any]]) -> list[str]:
            found: list[str] = []
            for it in feed_list:
                d = it.get("data") if isinstance(it.get("data"), dict) else {}
                slug = (
                    (d.get("collection_ref") or {}).get("slug")
                    or (d.get("roundup") or {}).get("slug")
                    or ""
                )
                if str(slug).startswith("machinery-"):
                    found.append(str(slug))
            return found

        # 1.0.6 / prewarmed base: include_machinery=False -> ZERO machinery-* items
        feed_106 = await add_roundup_feed_items(
            None,
            list(base_items),
            include_machinery=False,
        )
        assert _extract_machinery_slugs(feed_106) == []

        # Website / iOS 1.0.7+: machinery=1 splice on top of the 1.0.6 base
        feed_107 = await add_roundup_feed_items(
            None,
            list(feed_106),
            include_machinery=True,
            machinery_only=True,
        )
        assert _extract_machinery_slugs(feed_107) == ["machinery-nfl-week"]
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved)


@pytest.mark.asyncio
async def test_252a_get_feed_route_106_exact_query_never_receives_machinery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Route-level proof: 1.0.6's exact GET /api/feed query (no `machinery=1`)
    served from the shared prewarmed base carries NONE of the five groupings even
    when CONTAINER_MACHINERY_SLICE1_ENABLED=true, while `machinery=1` receives
    them off that same shared base."""
    import json
    from types import SimpleNamespace

    from fastapi import Response

    monkeypatch.setenv("CONTAINER_MACHINERY_SLICE1_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("FEED_PAGE_BASE_ENABLED", "1")

    base_items = [
        {"type": "futures", "id": f"fut-{i}", "data": {"id": 900 + i, "name": f"M{i}"}}
        for i in range(60)
    ]
    base_payload = {
        "items": base_items,
        "total": len(base_items),
        "_base_built_at": 1_800_000_000.0,
    }
    base_json = json.dumps(base_payload)
    store: dict[str, str] = {}
    base_keys_looked_up: list[str] = []

    class _FakeAsyncRedis:
        async def get(self, k: str):
            if k.startswith(f"{FEED_PAGE_BASE_CACHE_PREFIX}:") and not k.endswith(":stale") and not k.endswith(":last_good"):
                base_keys_looked_up.append(k)
                return base_json
            return store.get(k)

        async def mget(self, keys: list[str]):
            out = []
            for k in keys:
                if k.startswith(f"{FEED_PAGE_BASE_CACHE_PREFIX}:") and not k.endswith(":stale") and not k.endswith(":last_good"):
                    base_keys_looked_up.append(k)
                    out.append(base_json)
                else:
                    out.append(store.get(k))
            return out

        async def set(self, k: str, v: str, ex: int | None = None):
            store[k] = v
            return True

        async def hgetall(self, k: str):
            return {}

    fake_redis = _FakeAsyncRedis()

    async def _fake_get_shared_redis():
        return fake_redis

    monkeypatch.setattr(
        "app.utils.request_cache.get_shared_async_redis", _fake_get_shared_redis
    )
    monkeypatch.setattr(
        "app.utils.feed_collections.feed_collections_enabled", lambda **kwargs: False
    )
    monkeypatch.setattr(
        "app.utils.theme_collection_ref.theme_collection_refs_enabled",
        lambda **kwargs: False,
    )

    saved_producers = dict(ROUNDUP_PRODUCERS)

    async def _fake_add_roundups(db, items, **kwargs):
        if kwargs.get("include_machinery") and kwargs.get("machinery_only"):
            machinery_card = {
                "type": "bundle",
                "id": "roundup:machinery-nfl-week",
                "score": 88.0,
                "reason": "NFL Slate",
                "headline": "Bears at Lions headlines the Nov 19–22 slate",
                "data": {
                    "id": "roundup:machinery-nfl-week",
                    "title": "Bears at Lions headlines the Nov 19–22 slate",
                    "story_key": "roundup:machinery-nfl-week",
                    "items": [
                        {
                            "type": "futures",
                            "score": 88.0,
                            "reason": "NFL",
                            "headline": "NFL",
                            "data": {
                                "id": 9101,
                                "name": "NFL Passing Touchdowns Leader",
                                "status": "open",
                                "source": "kalshi",
                                "top_outcomes": [
                                    {"id": 1, "name": "Josh Allen", "probability": 0.34},
                                ],
                            },
                        }
                    ],
                    "collection_ref": {
                        "slug": "machinery-nfl-week",
                        "href": "/collections/machinery-nfl-week",
                        "name": "Bears at Lions headlines the Nov 19–22 slate",
                        "revision": 1,
                        "collection_count": 1,
                    },
                    "roundup": {
                        "kicker": "NFL · THIS SLATE",
                        "tag": "NFL",
                        "footer": "",
                        "rows": [
                            {
                                "event_id": 14969890,
                                "label": "Ravens at Panthers",
                                "probability": 0.565,
                                "rendered_percent": 57,
                            }
                        ],
                        "relations": ["same_event"],
                        "level": "member",
                    },
                },
            }
            return [machinery_card, *items]
        return items

    monkeypatch.setattr(
        "app.utils.roundup_containers.add_roundup_feed_items",
        _fake_add_roundups,
    )

    fake_request = SimpleNamespace(
        headers={},
        cookies={},
        query_params={},
        url=SimpleNamespace(path="/api/feed"),
    )

    try:
        # 1.0.6 exact Discover request shape: limit=50, offset=0, mode="discover", machinery=None
        resp_106 = await feed_route.get_feed(
            response=Response(),
            request=fake_request,
            limit=50,
            offset=0,
            sport=None,
            category=None,
            include_events=True,
            include_futures=True,
            my_teams_only=False,
            mode="discover",
            tags=None,
            event_pct=None,
            edition=None,
            debug=False,
            debug_ground_truth=False,
            debug_personalization=False,
            exclude_reviewed=False,
            reviewer=None,
            reviewed_surface=None,
            machinery=None,
            secret=None,
            db=AsyncMock(),
            user=None,
        )
        machinery_slugs_106 = [
            (it.get("data") or {}).get("collection_ref", {}).get("slug")
            for it in resp_106["items"]
            if str(
                (it.get("data") or {}).get("collection_ref", {}).get("slug") or ""
            ).startswith("machinery-")
        ]
        assert machinery_slugs_106 == []

        # Website / iOS 1.0.7+ exact request shape: same base + machinery=1
        resp_107 = await feed_route.get_feed(
            response=Response(),
            request=fake_request,
            limit=50,
            offset=0,
            sport=None,
            category=None,
            include_events=True,
            include_futures=True,
            my_teams_only=False,
            mode="discover",
            tags=None,
            event_pct=None,
            edition=None,
            debug=False,
            debug_ground_truth=False,
            debug_personalization=False,
            exclude_reviewed=False,
            reviewer=None,
            reviewed_surface=None,
            machinery=1,
            secret=None,
            db=AsyncMock(),
            user=None,
        )
        machinery_slugs_107 = [
            (it.get("data") or {}).get("collection_ref", {}).get("slug")
            for it in resp_107["items"]
            if str(
                (it.get("data") or {}).get("collection_ref", {}).get("slug") or ""
            ).startswith("machinery-")
        ]
        assert machinery_slugs_107 == ["machinery-nfl-week"]
        # Both 1.0.6 and website/1.0.7+ read the exact same single prewarmed base key.
        assert len(base_keys_looked_up) >= 2
        assert len(set(base_keys_looked_up)) == 1
    finally:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved_producers)


# ---------------------------------------------------------------------------
# 2. Ruling 253: A — Toss-up band <=55%, <2 -> "Closest games", no TOSS-UP tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_253a_zero_tossups_renames_section_drops_tag_and_headline_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This week's NFL slate (Ravens 43/57, Bears 44/56, Chargers 44/56 — 0 inside <=55%):
    - Section 0 becomes 'Closest games' with form_id='matchup_slate'
    - Zero rows carry show_toss_up_tag=True
    - Headline drops ', with N toss-up games'
    - Ravens at Panthers (14969890, 0.435/0.565) prints 43%/57% (never 44%/57%)."""
    defn = cm.load_machinery_definition(CANDIDATES_DIR / "machinery-nfl-week.json")
    events = [
        _ev(14969890, "Baltimore Ravens", "Carolina Panthers", 0.435, 0.565, commence="2026-11-22T18:00:00+00:00"),
        _ev(14969891, "Chicago Bears", "Detroit Lions", 0.44, 0.56, commence="2026-11-22T18:00:00+00:00"),
        _ev(14969892, "Los Angeles Chargers", "Denver Broncos", 0.44, 0.56, commence="2026-11-22T21:05:00+00:00"),
        _ev(14969893, "New York Jets", "Buffalo Bills", 0.25, 0.75, commence="2026-11-20T01:15:00+00:00"),
        _ev(14969894, "Miami Dolphins", "Kansas City Chiefs", 0.30, 0.70, commence="2026-11-22T21:25:00+00:00"),
    ]
    snapshot = {
        "events": events,
        "markets": _nfl_aux_markets(),
        "paired_sets": {},
        "market_histories": {},
    }
    monkeypatch.setattr(cm, "_load_snapshot_from_db", AsyncMock(return_value=snapshot))

    result = await cm.produce_container_machinery(
        None, defn, now=datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)
    )
    assert isinstance(result, RoundupMembers)
    assert "toss-up" not in result.title.lower()
    assert "Bears at Lions headlines the Nov 19–22 slate" == result.title

    sec0 = result.sections[0]
    assert sec0["title"] == "Closest games"
    assert "toss-up" not in str(sec0.get("note") or "").lower()
    assert sec0["visual_block"]["form_id"] == "matchup_slate"
    for item in sec0["visual_block"]["items"]:
        assert item["is_toss_up"] is False
        assert item["show_toss_up_tag"] is False

    ravens = next(
        it for it in sec0["visual_block"]["items"] if it["event_id"] == 14969890
    )
    assert ravens["away_pct"] == 43
    assert ravens["home_pct"] == 57
    assert ravens["away_pct"] + ravens["home_pct"] == 100

    ravens_member = next(m for m in sec0["members"] if m["id"] == 14969890)
    assert ravens_member["card"]["current_odds"]["away_rendered_percent"] == 43
    assert ravens_member["card"]["current_odds"]["home_rendered_percent"] == 57


@pytest.mark.asyncio
async def test_253a_two_plus_tossups_counts_only_in_band_games(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When 2 games are inside <=55% and 1 is at 57%, Coin-Flip Matchups includes
    ONLY the 2 inside-band games and the headline says 'with 2 toss-up games'."""
    defn = cm.load_machinery_definition(CANDIDATES_DIR / "machinery-nfl-week.json")
    events = [
        _ev(2001, "Team A", "Team B", 0.49, 0.51, commence="2026-11-22T18:00:00+00:00"),
        _ev(2002, "Team C", "Team D", 0.45, 0.55, commence="2026-11-22T18:00:00+00:00"),
        _ev(2003, "Team E", "Team F", 0.43, 0.57, commence="2026-11-22T21:05:00+00:00"),
        _ev(2004, "Team G", "Team H", 0.25, 0.75, commence="2026-11-23T01:20:00+00:00"),
    ]
    snapshot = {
        "events": events,
        "markets": _nfl_aux_markets(),
        "paired_sets": {},
        "market_histories": {},
    }
    monkeypatch.setattr(cm, "_load_snapshot_from_db", AsyncMock(return_value=snapshot))

    result = await cm.produce_container_machinery(
        None, defn, now=datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)
    )
    assert isinstance(result, RoundupMembers)
    assert "with 2 toss-up games" in result.title
    sec0 = result.sections[0]
    assert sec0["title"] == "Coin-Flip Matchups"
    assert sec0["visual_block"]["form_id"] == "coin_flip_matchups"
    assert [it["event_id"] for it in sec0["visual_block"]["items"]] == [2001, 2002]
    assert all(it["show_toss_up_tag"] is True for it in sec0["visual_block"]["items"])


# ---------------------------------------------------------------------------
# 3. Games-in-play dynamic section headings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "statuses,expected_title",
    [
        (["live", "live"], "Live Now"),
        (["live", "scheduled"], "Live & Upcoming Matchups"),
        (["scheduled", "scheduled"], "Upcoming Matchups"),
    ],
)
async def test_games_in_play_dynamic_section_headings(
    monkeypatch: pytest.MonkeyPatch,
    statuses: list[str],
    expected_title: str,
) -> None:
    defn = cm.load_machinery_definition(CANDIDATES_DIR / "machinery-nfl-week.json")
    events = [
        _ev(3001, "Ravens", "Panthers", 0.435, 0.565, status="scheduled"),
        _ev(3002, "Bears", "Lions", 0.44, 0.56, status="scheduled"),
        _ev(3003, "Jets", "Bills", 0.28, 0.72, status=statuses[0]),
        _ev(3004, "Dolphins", "Chiefs", 0.30, 0.70, status=statuses[1]),
    ]
    snapshot = {
        "events": events,
        "markets": _nfl_aux_markets(),
        "paired_sets": {},
        "market_histories": {},
    }
    monkeypatch.setattr(cm, "_load_snapshot_from_db", AsyncMock(return_value=snapshot))

    result = await cm.produce_container_machinery(
        None, defn, now=datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)
    )
    assert isinstance(result, RoundupMembers)
    slate_sec = next(s for s in result.sections if s["class"] == "week_slate")
    assert slate_sec["title"] == expected_title


# ---------------------------------------------------------------------------
# 4. Strict game-page pair parity (Ravens 14969890: 43/57 vs 44/57 failure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_member_number_parity_fails_on_44_vs_43_and_missing_current_odds_rendered_percents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression fixture: Ravens at Panthers (14969890, 0.435/0.565 -> 43%/57%).
    1. Clean build passes parity with 43%/57%.
    2. Mutating a row to 44% (the independent half-up bug) FAILS parity.
    3. Stripping `away_rendered_percent` from `current_odds` FAILS parity."""
    defn = cm.load_machinery_definition(CANDIDATES_DIR / "machinery-nfl-week.json")
    events = [
        _ev(14969890, "Baltimore Ravens", "Carolina Panthers", 0.435, 0.565),
        _ev(14969891, "Chicago Bears", "Detroit Lions", 0.44, 0.56),
        _ev(14969892, "New York Jets", "Buffalo Bills", 0.25, 0.75),
        _ev(14969893, "Miami Dolphins", "Kansas City Chiefs", 0.30, 0.70),
    ]
    snapshot = {
        "events": events,
        "markets": _nfl_aux_markets(),
        "paired_sets": {},
        "market_histories": {},
    }
    monkeypatch.setattr(cm, "_load_snapshot_from_db", AsyncMock(return_value=snapshot))

    producer = cm.build_container_machinery_producer(defn, enabled=lambda: True)
    members = await producer.produce(
        None, now=datetime(2026, 11, 19, 1, 0, tzinfo=timezone.utc)
    )
    feed_item = compose_roundup_feed_item(producer, members)
    container_payload = compose_roundup_container(producer, members)

    # 1. Clean build passes
    card_p, page_p = cm._compute_member_number_parity(feed_item, container_payload)
    assert card_p["passes"] is True and card_p["mismatch_count"] == 0
    assert page_p["passes"] is True and page_p["mismatch_count"] == 0

    # 2. Row printing 44% against canonical 43% FAILS both card and page parity
    bad_feed = copy.deepcopy(feed_item)
    bad_page = copy.deepcopy(container_payload)
    for row in bad_feed["data"]["roundup"]["machinery_card"]["rows"]:
        if row["event_id"] == 14969890:
            row["away_pct"] = 44
    for item in bad_page["sections"][0]["visual_block"]["items"]:
        if item["event_id"] == 14969890:
            item["away_pct"] = 44

    bad_card_p, bad_page_p = cm._compute_member_number_parity(bad_feed, bad_page)
    assert bad_card_p["passes"] is False
    assert any(
        m["event_id"] == 14969890 and m["shown"] == 44 and m["member_page"] == 43
        for m in bad_card_p["mismatches"]
    )
    assert bad_page_p["passes"] is False
    assert any(
        m["event_id"] == 14969890 and m["shown"] == 44 and m["member_page"] == 43
        for m in bad_page_p["mismatches"]
    )

    # 3. Missing away_rendered_percent in card.current_odds FAILS parity
    missing_odds_page = copy.deepcopy(container_payload)
    ravens_m = next(
        m for m in missing_odds_page["sections"][0]["members"] if m["id"] == 14969890
    )
    ravens_m["card"]["current_odds"].pop("away_rendered_percent", None)
    _, missing_p = cm._compute_member_number_parity(feed_item, missing_odds_page)
    assert missing_p["passes"] is False
    assert any(
        m["event_id"] == 14969890
        and m["shown"] is None
        and m["member_page"] == 43
        for m in missing_p["mismatches"]
    )


# ---------------------------------------------------------------------------
# 5. Fable 9:38 PM PT review fixes on #13039
# ---------------------------------------------------------------------------


def test_252a_fresh_build_stored_base_runs_publish_feed_item_even_on_folded_cards() -> None:
    """Fable review #1: cards folded out of `feed_items` by machinery groupings must
    still pass through `_publish_feed_item` (promoting `data.story_key` and stripping
    internal keys) so the base stored by a `machinery=1` fresh build equals, item for
    item, the base stored by the same build without `machinery=1`."""
    import copy
    import inspect

    from app.routes.feed import _publish_feed_item, get_feed

    src = inspect.getsource(get_feed)
    # 1. `_base_feed_items_without_machinery` is captured ONLY inside `if _include_machinery_feed:`
    #    (Fable review #2: non-machinery builds, including edition-pinned builds with switches off,
    #    never diverge from the existing base-storage path).
    inc_idx = src.index("if _include_machinery_feed:")
    cap_idx = src.index("_base_feed_items_without_machinery = list(feed_items)")
    assert cap_idx > inc_idx

    # 2. The publish loop runs `_publish_feed_item` on folded-out base items (never manual pops).
    pub_idx = src.index("for item in feed_items:\n            _publish_feed_item(item)")
    base_pub_idx = src.index("_publish_feed_item(_b_item)")
    assert base_pub_idx > pub_idx
    assert '_b_item.pop("_rank_score"' not in src

    # 3. Direct behavioral equivalence: a folded-out card published via the base loop
    #    equals item-for-item the exact same card published on a non-machinery build.
    raw_items_no_mach = [
        {
            "type": "futures",
            "_rank_score": 81.2,
            "_quality_story_key": "nfl:mvp",
            "_debug_meta": {"tier": 1},
            "data": {"id": 9101, "name": "NFL MVP"},
        },
        {
            "type": "futures",
            "_rank_score": 74.5,
            "_quality_story_key": "nfl:passing_td",
            "_debug_meta": {"tier": 1},
            "data": {"id": 9102, "name": "NFL Passing TD Leader"},
        },
    ]
    raw_items_with_mach = copy.deepcopy(raw_items_no_mach)

    # Without machinery=1: every item stays in feed_items and runs _publish_feed_item.
    for item in raw_items_no_mach:
        _publish_feed_item(item)

    # With machinery=1: base snapshot taken before machinery folds out item[0].
    base_without_mach = list(raw_items_with_mach)
    served_with_mach = [
        {"type": "bundle", "data": {"id": "roundup:machinery-nfl-week"}},
        raw_items_with_mach[1],  # item[0] was folded out into the machinery card
    ]
    for item in served_with_mach:
        _publish_feed_item(item)
    published_ids = {id(item) for item in served_with_mach}
    for b_item in base_without_mach:
        if id(b_item) not in published_ids:
            _publish_feed_item(b_item)

    assert base_without_mach == raw_items_no_mach
    assert base_without_mach[0]["data"]["story_key"] == "nfl:mvp"
    assert "_rank_score" not in base_without_mach[0]
    assert "_quality_story_key" not in base_without_mach[0]
    assert "_debug_meta" not in base_without_mach[0]


@pytest.mark.asyncio
async def test_closeness_to_50_excludes_started_games_and_never_uses_coin_flip_for_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fable review #3: no row may show a started game with only its scheduled time.
    - When >= min_items unstarted games exist, Coin-Flip Matchups holds ONLY unstarted
      games, and started games (e.g. live Jazz at Lakers) render under Live & Upcoming
      Matchups with live status/score.
    - If fewer than min_items unstarted games exist, choose_section_form forces
      `matchup_slate` (never `coin_flip_matchups`) so web and iOS 1.0.7 draw LIVE cards."""
    defn = cm.load_machinery_definition(CANDIDATES_DIR / "machinery-nfl-week.json")
    events = [
        _ev(4001, "Utah Jazz", "Los Angeles Lakers", 0.53, 0.47, status="live"),
        _ev(4002, "New York Knicks", "Minnesota Timberwolves", 0.52, 0.48, status="scheduled"),
        _ev(4003, "Washington Wizards", "Chicago Bulls", 0.48, 0.52, status="scheduled"),
        _ev(4004, "Boston Celtics", "Denver Nuggets", 0.17, 0.83, status="live"),
        _ev(4005, "LA Clippers", "San Antonio Spurs", 0.11, 0.89, status="scheduled"),
    ]
    snapshot = {
        "events": events,
        "markets": _nfl_aux_markets(),
        "paired_sets": {},
        "market_histories": {},
    }
    monkeypatch.setattr(cm, "_load_snapshot_from_db", AsyncMock(return_value=snapshot))

    result = await cm.produce_container_machinery(
        None, defn, now=datetime(2026, 11, 19, 5, 0, tzinfo=timezone.utc)
    )
    assert isinstance(result, RoundupMembers)
    sec0 = result.sections[0]
    assert sec0["visual_block"]["form_id"] == "coin_flip_matchups"
    sec0_ids = [it["event_id"] for it in sec0["visual_block"]["items"]]
    assert 4001 not in sec0_ids
    assert sec0_ids == [4002, 4003]
    assert all(it["status"] == "scheduled" for it in sec0["visual_block"]["items"])

    slate_sec = next(s for s in result.sections if s["class"] == "week_slate")
    assert slate_sec["title"] == "Live & Upcoming Matchups"
    assert 4001 in [it["event_id"] for it in slate_sec["visual_block"]["items"]]

    # Structural guard: choose_section_form NEVER selects coin_flip_matchups when any game is live
    assert (
        cm.choose_section_form(
            "events",
            [
                {"fav_prob": 0.52, "status": "live"},
                {"fav_prob": 0.51, "status": "scheduled"},
            ],
        )
        == "matchup_slate"
    )

