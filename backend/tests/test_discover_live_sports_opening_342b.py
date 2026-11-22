"""Tests for Decision 342: B — live-game sports grouping seat in Discover's first ten."""

from __future__ import annotations

import asyncio
import copy
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
import pytest

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils import request_cache as rc
from app.utils.discover_opening_mix import (
    OPENING_MIX_LIVE_SPORTS_FLAG,
    PWM_SUBTOPIC_POLITICS_WORLD,
    TOPIC_ENTERTAINMENT,
    TOPIC_ODD,
    TOPIC_PWM,
    TOPIC_SPORTS,
    TOPIC_TECH_BUSINESS,
    apply_discover_opening_mix,
    classify_discover_opening_topic,
    classify_discover_pwm_subtopic,
    discover_opening_pwm_kind_for_date,
)
from app.utils.discover_opening_seating import (
    COMPLIANT,
    OPENING_SEATS,
    seat_opening,
)
from app.utils.feed_cache import (
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_TTL_LIVE_SECONDS,
    payload_contains_live_event,
)
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupMembers,
    RoundupProducer,
    _is_grouped_feed_card,
    _is_roundup_bundle_card,
    _roundup_local_cache,
)

# Sunday Nov 22, 2026 afternoon NFL window (1:57 PM PT = 21:57Z)
NFL_NOW = datetime(2026, 11, 22, 21, 57, tzinfo=timezone.utc)


def _single_future(
    mid: int,
    name: str,
    *,
    category: str,
    score: float,
) -> dict:
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
            "top_outcomes": [
                {"id": mid * 10, "name": "Yes", "probability": 0.42},
                {"id": mid * 10 + 1, "name": "No", "probability": 0.58},
            ],
        },
    }


def _theme_bundle(
    story_key: str,
    title: str,
    member_ids: list[int],
    *,
    score: float,
) -> dict:
    return {
        "type": "bundle",
        "score": score,
        "reason": title,
        "headline": title,
        "data": {
            "id": f"theme:{story_key}:{'-'.join(str(m) for m in member_ids)}",
            "title": title,
            "name": title,
            "kind": "theme",
            "story_key": story_key,
            "items": [
                {
                    "type": "futures",
                    "score": score,
                    "data": {"id": mid, "name": f"M{mid}", "status": "open"},
                }
                for mid in member_ids
            ],
        },
    }


def _event_child(
    eid: int,
    matchup: str,
    *,
    live: bool,
    status_override: str | None = None,
) -> dict:
    away, _, home = matchup.partition(" @ ")
    return {
        "type": "event",
        "score": 82.0 if live else 70.0,
        "reason": matchup,
        "headline": matchup,
        "data": {
            "id": eid,
            "name": matchup,
            "away_team": away or "Away",
            "home_team": home or "Home",
            "status": status_override or ("live" if live else "final"),
            "commence_time": (NFL_NOW - timedelta(minutes=35)).isoformat(),
            "away_score": 10 if live else 24,
            "home_score": 3 if live else 20,
            "is_major": False,
            "is_marquee": False,
            "event_tags": [],
        },
    }


def _roundup_bundle(
    slug: str,
    title: str,
    *,
    kicker: str,
    category: str,
    children: list[dict],
    score: float = 75.0,
    top_status: str | None = None,
    relations: list[str] | None = None,
) -> dict:
    member_ids = [
        int(c["data"]["id"])
        for c in children
        if isinstance(c.get("data"), dict) and isinstance(c["data"].get("id"), int)
    ]
    data: dict = {
        "id": f"roundup:{slug}",
        "title": title,
        "kind": "roundup",
        "story_key": f"roundup:{slug}",
        "category": category,
        "item_count": len(children),
        "member_ids": member_ids,
        "items": children,
        "roundup": {
            "kicker": kicker,
            "tag": category.upper(),
            "footer": "",
            "rows": [
                {"market_id": mid, "label": f"Row {mid}", "probability": 0.5}
                for mid in member_ids
            ],
            "relations": relations or ["same_subject"],
            "level": "member",
        },
    }
    if slug.startswith("machinery-"):
        data["collection_ref"] = {
            "slug": slug,
            "href": f"/collections/{slug}",
            "name": title,
            "revision": "1",
            "collection_count": len(children),
        }
    if top_status is not None:
        data["status"] = top_status
    return {
        "type": "bundle",
        "score": score,
        "reason": kicker,
        "headline": title,
        "data": data,
    }


def _future_child(mid: int) -> dict:
    return {
        "type": "futures",
        "score": 80.0,
        "data": {"id": mid, "name": f"Future {mid}", "status": "open"},
    }


def _nfl_window_deck(
    *,
    nfl_live_count: int = 3,
    closest_live_count: int = 1,
    nba_live_count: int = 1,
    closest_first: bool = True,
) -> list[dict]:
    """Mirror Sunday Nov 22 afternoon NFL-window Discover structure."""
    closest_card = _roundup_bundle(
        "closest-games-tonight",
        "The closest games tonight",
        kicker="Round-up",
        category="football",
        children=[
            *[
                _event_child(9100 + i, f"Live Club {i} @ Host {i}", live=True)
                for i in range(closest_live_count)
            ],
            _event_child(9190, "Seattle Redhawks @ UC San Diego Tritons", live=False, status_override="scheduled"),
        ],
        score=82.0,
    )
    nba_card = _roundup_bundle(
        "machinery-nba-night",
        "Mavericks at Jazz headlines the Nov 22 slate",
        kicker="NBA · THIS SLATE",
        category="basketball",
        children=[
            *[
                _event_child(9200 + i, f"Pistons {i} @ Hawks {i}", live=True)
                for i in range(nba_live_count)
            ],
            _event_child(9290, "Dallas Mavericks @ Utah Jazz", live=False, status_override="scheduled"),
        ],
        score=73.0,
        top_status="live" if nba_live_count > 0 else None,
    )
    nfl_card = _roundup_bundle(
        "machinery-nfl-week",
        "Bears at Lions headlines the Nov 22–29 slate",
        kicker="NFL · THIS SLATE",
        category="football",
        children=[
            *[
                _event_child(9300 + i, f"Jets {i} @ Chargers {i}", live=True)
                for i in range(nfl_live_count)
            ],
            _event_child(9390, "Chicago Bears @ Detroit Lions", live=False, status_override="scheduled"),
        ],
        score=73.0,
        top_status="live" if nfl_live_count > 0 else None,
    )
    sports_live_cards = (
        [closest_card, nba_card, nfl_card]
        if closest_first
        else [nba_card, closest_card, nfl_card]
    )
    return [
        _roundup_bundle("machinery-elon-musk-side-quests", "Musk side quests", kicker="ODD · SIDE QUESTS", category="entertainment", children=[_future_child(1001)], score=87.0, relations=["same_subject", "sibling"]),
        _roundup_bundle("machinery-2026-summed-up", "Bad Bunny top artist", kicker="CULTURE · 2026", category="entertainment", children=[_future_child(1002)], score=88.0),
        _roundup_bundle("machinery-google-year-in-search-2026", "Google search", kicker="ODD · SEARCH", category="entertainment", children=[_future_child(1003)], score=77.0),
        _single_future(68948432, "MLB Playoffs: Team to advance to 2027 World Series", category="baseball", score=95.0),
        _roundup_bundle("machinery-next-james-bond", "James Bond", kicker="ENTERTAINMENT · JAMES BOND", category="entertainment", children=[_future_child(1004)], score=82.0),
        _roundup_bundle("cfp-picture", "College Football Playoff picture", kicker="Round-up", category="football", children=[_future_child(1005)], score=28.0),
        _theme_bundle("story:ai", "AI", [1006, 1007], score=86.0),
        _roundup_bundle("machinery-long-shots", "Long shots", kicker="ODD · LONG SHOTS", category="entertainment", children=[_future_child(1008)], score=76.0, relations=["same_measure", "sibling"]),
        _theme_bundle("story:ipo_markets", "IPOs", [1009, 1010], score=68.0),
        _theme_bundle("story:middle_east_conflict", "Middle East", [1011, 1012], score=96.0),
        _theme_bundle("story:macro_rates", "Fed & Rates", [1013, 1014], score=90.0),
        _single_future(61380674, "Will Boston Bruins advance to Round 2?", category="hockey", score=63.0),
        _event_child(9991, "Miami Dolphins @ Buffalo Bills", live=True),
        {
            "type": "concept",
            "score": 99.0,
            "reason": "World Cup",
            "headline": "World Cup",
            "data": {
                "id": "concept:world-cup-2026",
                "key": "concept:world-cup-2026",
                "slug": "concept:world-cup-2026",
                "name": "FIFA World Cup 2026",
                "status": "upcoming",
            },
        },
        *sports_live_cards,
        _single_future(61380675, "Extra filler market 1", category="tech", score=51.0),
        _single_future(61380676, "Extra filler market 2", category="entertainment", score=49.0),
        _roundup_bundle("golf-this-week", "Golf This Week", kicker="GOLF · THIS WEEK", category="golf", children=[_future_child(1015)], score=45.0),
    ]


def test_342b_nfl_window_replay_places_most_live_sports_grouping_in_first_ten() -> None:
    deck = _nfl_window_deck(nfl_live_count=3, closest_live_count=1, nba_live_count=1)
    mixed = apply_discover_opening_mix(copy.deepcopy(deck), now=NFL_NOW)
    seating = seat_opening(mixed, now=NFL_NOW)
    assert seating.status == COMPLIANT, seating.detail

    top10 = seating.items[:10]
    top10_ids = [(c.get("data") or {}).get("id") for c in top10]

    # Most-live-games grouping (3 live NFL games) wins one sports seat;
    # 1-live siblings, single event cards, and concepts stay out of seats 1..10.
    assert "roundup:machinery-nfl-week" in top10_ids
    assert "roundup:closest-games-tonight" not in top10_ids
    assert "roundup:machinery-nba-night" not in top10_ids
    assert 9991 not in top10_ids
    assert "concept:world-cup-2026" not in top10_ids

    # 9 grouped + 1 single + topic mix + Seat 10 (333: A)
    assert sum(1 for c in top10 if _is_grouped_feed_card(c)) == 9
    assert sum(1 for c in top10 if c.get("type") == "futures") == 1
    assert sum(1 for c in top10 if c.get("type") in ("concept", "event")) == 0
    topics = Counter(classify_discover_opening_topic(c) for c in top10)
    assert topics[TOPIC_ODD] == 3
    assert 2 <= topics[TOPIC_ENTERTAINMENT] <= 3
    assert topics[TOPIC_SPORTS] == 2
    assert 1 <= topics[TOPIC_TECH_BUSINESS] <= 2
    assert topics[TOPIC_PWM] == 1
    assert classify_discover_pwm_subtopic(top10[9]) == PWM_SUBTOPIC_POLITICS_WORLD
    assert discover_opening_pwm_kind_for_date(NFL_NOW) == PWM_SUBTOPIC_POLITICS_WORLD

    # Only the winning live sports card carries the internal exemption flag.
    nfl_card = next(c for c in top10 if c["data"]["id"] == "roundup:machinery-nfl-week")
    assert nfl_card["data"][OPENING_MIX_LIVE_SPORTS_FLAG] is True
    for card in seating.items[10:]:
        if isinstance(card.get("data"), dict):
            assert OPENING_MIX_LIVE_SPORTS_FLAG not in card["data"]

    # Decision 123-A non-adjacency from seat 11 onward
    for idx in range(OPENING_SEATS + 1, len(seating.items)):
        assert not (
            _is_roundup_bundle_card(seating.items[idx - 1])
            and _is_roundup_bundle_card(seating.items[idx])
        ), f"Adjacent round-up at seat {idx + 1}"

    # Strict idempotency
    twice = apply_discover_opening_mix(copy.deepcopy(seating.items), now=NFL_NOW)
    assert [(c["type"], c["data"]["id"]) for c in twice[:10]] == [
        (c["type"], c["data"]["id"]) for c in top10
    ]


def test_342b_tie_breaks_by_higher_deck_rank_and_payload_live_catches_standing_bundles() -> None:
    deck = _nfl_window_deck(
        nfl_live_count=1,
        closest_live_count=1,
        nba_live_count=1,
        closest_first=True,
    )
    mixed = apply_discover_opening_mix(copy.deepcopy(deck), now=NFL_NOW)
    seating = seat_opening(mixed, now=NFL_NOW)
    assert seating.status == COMPLIANT, seating.detail

    top10_ids = {(c.get("data") or {}).get("id") for c in seating.items[:10]}
    # Tied at 1 live game: closest-games-tonight ranked earlier in the deck wins.
    assert "roundup:closest-games-tonight" in top10_ids
    assert "roundup:machinery-nfl-week" not in top10_ids
    assert "roundup:machinery-nba-night" not in top10_ids

    # Even though closest-games-tonight has no top-level data["status"],
    # payload_contains_live_event still detects its live child event (60s bound).
    assert payload_contains_live_event({"items": list(seating.items[:10])}) is True


def test_342b_no_live_game_keeps_first_ten_identical_to_before() -> None:
    deck = _nfl_window_deck(nfl_live_count=0, closest_live_count=0, nba_live_count=0)
    # Also mark standalone event as final
    for c in deck:
        if c.get("type") == "event":
            c["data"]["status"] = "final"
    mixed = apply_discover_opening_mix(copy.deepcopy(deck), now=NFL_NOW)
    seating = seat_opening(mixed, now=NFL_NOW)
    assert seating.status == COMPLIANT

    top10_ids = [(c.get("type"), (c.get("data") or {}).get("id")) for c in seating.items[:10]]
    assert top10_ids == [
        ("bundle", "roundup:machinery-elon-musk-side-quests"),
        ("bundle", "roundup:machinery-2026-summed-up"),
        ("bundle", "roundup:machinery-google-year-in-search-2026"),
        ("futures", 68948432),
        ("bundle", "roundup:machinery-next-james-bond"),
        ("bundle", "roundup:cfp-picture"),
        ("bundle", "theme:story:ai:1006-1007"),
        ("bundle", "roundup:machinery-long-shots"),
        ("bundle", "theme:story:ipo_markets:1009-1010"),
        ("bundle", "theme:story:middle_east_conflict:1011-1012"),
    ]
    assert payload_contains_live_event({"items": list(seating.items[:10])}) is False
    for c in seating.items:
        if isinstance(c.get("data"), dict):
            assert OPENING_MIX_LIVE_SPORTS_FLAG not in c["data"]


def test_342b_last_live_game_ending_returns_seat_on_next_read() -> None:
    deck_live = _nfl_window_deck(nfl_live_count=1, closest_live_count=0, nba_live_count=0)
    read1 = seat_opening(apply_discover_opening_mix(copy.deepcopy(deck_live), now=NFL_NOW), now=NFL_NOW)
    assert read1.status == COMPLIANT
    assert "roundup:machinery-nfl-week" in [c["data"]["id"] for c in read1.items[:10]]
    read1_nfl = next(c for c in read1.items[:10] if c["data"]["id"] == "roundup:machinery-nfl-week")
    assert read1_nfl["data"][OPENING_MIX_LIVE_SPORTS_FLAG] is True

    # Transition the sole live child event from live -> final on the canonical
    # scored deck (mirroring the next feed rebuild after kickoff -> final).
    deck_after_final = copy.deepcopy(deck_live)
    for c in deck_after_final:
        if c.get("type") == "event" and c["data"].get("status") == "live":
            c["data"]["status"] = "final"
        if (c.get("data") or {}).get("id") == "roundup:machinery-nfl-week":
            c["data"]["status"] = "final"
            for child in c["data"].get("items") or []:
                if child.get("type") == "event" and child["data"].get("status") == "live":
                    child["data"]["status"] = "final"

    read2 = seat_opening(apply_discover_opening_mix(deck_after_final, now=NFL_NOW), now=NFL_NOW)
    assert read2.status == COMPLIANT
    read2_top10_ids = {c["data"]["id"] for c in read2.items[:10]}
    assert "roundup:machinery-nfl-week" not in read2_top10_ids
    assert "roundup:cfp-picture" in read2_top10_ids
    for c in read2.items:
        if isinstance(c.get("data"), dict):
            assert OPENING_MIX_LIVE_SPORTS_FLAG not in c["data"]


class _SeededRedis:
    def __init__(self, contents: dict[str, str] | None = None):
        self.contents = dict(contents or {})

    async def mget(self, keys):
        return [await self.get(k) for k in keys]

    async def get(self, key):
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        self.contents[key] = value
        return True

    async def delete(self, key):
        return 1 if self.contents.pop(key, None) is not None else 0


def _empty_async_session():
    session = AsyncMock()
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.first.return_value = None
    empty.scalar_one_or_none.return_value = None
    empty.scalar.return_value = 0
    empty.fetchall.return_value = []
    empty.all.return_value = []
    empty.first.return_value = None
    session.execute = AsyncMock(return_value=empty)
    session.rollback = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_342b_feed_route_end_to_end_live_then_final_and_aged_page_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real GET /api/feed?limit=20&event_pct=0.15&machinery=1 end-to-end verification."""
    import app.routes.feed as feed_mod
    from app.main import app

    assert feed_mod._DISCOVER_OPENING_SEATING_SERVED is True

    live_state = {"nfl_live": True, "closest_live": True}
    saved_producers = dict(ROUNDUP_PRODUCERS)

    def _make_futures_producer(slug: str, title: str, kicker: str, category: str, mid: int, *, rule=None, relations=("same_subject",)):
        async def _produce(db, *, now=None):
            return RoundupMembers(
                members=[{"type": "market", "id": mid, "destination": f"/futures/{mid}", "card": {"id": mid, "name": title}}],
                rows=[{"market_id": mid, "outcome_id": mid * 10, "label": title, "probability": 0.45}],
                title=title,
                kicker=kicker,
                destination_href=f"/collections/{slug}",
            )

        return RoundupProducer(
            slug=slug,
            name=title,
            kind="roundup",
            category=category,
            section_title=title,
            footer="",
            produce=_produce,
            membership="computed-produced",
            relations=relations,
            level="member",
            rule=rule or {},
            enabled=lambda: True,
        )

    async def _produce_closest(db, *, now=None):
        is_live = live_state["closest_live"]
        ev_card = {
            "id": 9101,
            "name": "FC Cincinnati @ Nashville SC",
            "away_team": "FC Cincinnati",
            "home_team": "Nashville SC",
            "status": "live" if is_live else "final",
            "commence_time": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
            "away_score": 1,
            "home_score": 0,
            "is_major": False,
            "is_marquee": False,
            "event_tags": [],
        }
        return RoundupMembers(
            members=[{"type": "event", "id": 9101, "destination": "/event/9101", "card": ev_card}],
            rows=[],
            title="The closest games tonight",
            kicker="Round-up",
            destination_href="/collections/roundup-closest-games-tonight",
        )

    async def _produce_nfl(db, *, now=None):
        is_live = live_state["nfl_live"]
        members = []
        for idx, (away, home) in enumerate((("Jets", "Chargers"), ("Raiders", "Broncos")), start=1):
            eid = 9300 + idx
            members.append(
                {
                    "type": "event",
                    "id": eid,
                    "destination": f"/event/{eid}",
                    "card": {
                        "id": eid,
                        "name": f"{away} @ {home}",
                        "away_team": away,
                        "home_team": home,
                        "status": "live" if is_live else "final",
                        "commence_time": (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat(),
                        "away_score": 10,
                        "home_score": 3,
                        "is_major": False,
                        "is_marquee": False,
                        "event_tags": [],
                    },
                }
            )
        return RoundupMembers(
            members=members,
            rows=[],
            title="Jets at Chargers headlines the Nov 22–29 slate",
            kicker="NFL · THIS SLATE",
            destination_href="/collections/machinery-nfl-week",
        )

    test_producers = {
        "roundup-cfp-picture": _make_futures_producer("roundup-cfp-picture", "College Football Playoff picture", "Round-up", "football", 8001),
        "roundup-closest-games-tonight": RoundupProducer(
            slug="roundup-closest-games-tonight",
            name="The closest games tonight",
            kind="roundup",
            category="sports",
            section_title="Tonight",
            footer="",
            produce=_produce_closest,
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            enabled=lambda: True,
        ),
        "machinery-elon-musk-side-quests": _make_futures_producer("machinery-elon-musk-side-quests", "Musk side quests", "ODD · SIDE QUESTS", "entertainment", 8002, rule={"producer": "container_machinery"}, relations=("same_subject", "sibling")),
        "machinery-long-shots": _make_futures_producer("machinery-long-shots", "Long shots", "ODD · LONG SHOTS", "entertainment", 8003, rule={"producer": "container_machinery"}, relations=("same_measure", "sibling")),
        "machinery-google-year-in-search-2026": _make_futures_producer("machinery-google-year-in-search-2026", "Google search", "ODD · SEARCH", "entertainment", 8004, rule={"producer": "container_machinery"}),
        "machinery-2026-summed-up": _make_futures_producer("machinery-2026-summed-up", "2026 summed up", "CULTURE · 2026", "entertainment", 8005, rule={"producer": "container_machinery"}),
        "machinery-next-james-bond": _make_futures_producer("machinery-next-james-bond", "Next James Bond", "ENTERTAINMENT · JAMES BOND", "entertainment", 8006, rule={"producer": "container_machinery"}),
        "machinery-ai-and-big-tech-race": _make_futures_producer("machinery-ai-and-big-tech-race", "AI & Big Tech Race", "TECH · AI", "tech", 8007, rule={"producer": "container_machinery"}),
        "machinery-space-race": _make_futures_producer("machinery-space-race", "Space Race", "TECH · SPACE", "tech", 8008, rule={"producer": "container_machinery"}),
        "machinery-2028-presidential": _make_futures_producer("machinery-2028-presidential", "2028 Presidential", "POLITICS · 2028", "politics", 8009, rule={"producer": "container_machinery"}),
        "machinery-fed-rates": _make_futures_producer("machinery-fed-rates", "Fed interest rate cuts", "MONEY · FED", "economics", 8010, rule={"producer": "container_machinery"}),
        "machinery-nfl-week": RoundupProducer(
            slug="machinery-nfl-week",
            name="NFL This Slate",
            kind="roundup",
            category="football",
            section_title="NFL",
            footer="",
            produce=_produce_nfl,
            membership="computed-produced",
            relations=("same_subject",),
            level="member",
            rule={"producer": "container_machinery"},
            enabled=lambda: True,
        ),
    }

    scored_futures = [
        _single_future(68948432, "MLB Playoffs: Team to advance to 2027 World Series", category="baseball", score=95.0),
        _single_future(61380674, "Will Boston Bruins advance to Round 2?", category="hockey", score=72.0),
        _single_future(61380675, "Oscar Best Picture 2027", category="entertainment", score=70.0),
        _single_future(61380676, "OpenAI IPO in 2027", category="tech", score=69.0),
        _single_future(61380677, "Next UK Prime Minister", category="politics", score=65.0),
        _single_future(61380678, "NBA Western Conference Champion 2027", category="basketball", score=64.0),
        _single_future(61380679, "Premier League Top Scorer", category="soccer", score=62.0),
        _single_future(61380680, "Grammy Album of the Year 2027", category="culture", score=60.0),
        _single_future(61380681, "SpaceX Starship orbital flight", category="science", score=58.0),
        _single_future(61380682, "Top App Store app of 2027", category="tech", score=56.0),
        _single_future(61380683, "White Christmas in Boston", category="weather", score=54.0),
        _single_future(61380684, "FIFA World Cup 2030 host", category="sports", score=52.0),
    ]

    redis = _SeededRedis()
    session = _empty_async_session()

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    async def _get_redis():
        return redis

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    try:
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(test_producers)
        rc._reset_last_good_for_tests()
        _roundup_local_cache.clear()

        monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
        monkeypatch.setattr("app.utils.roundup_containers.ensure_optional_roundup_candidates", lambda: None)
        monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)
        monkeypatch.setattr(rc, "schedule_background", lambda coro: asyncio.ensure_future(coro))
        monkeypatch.setattr(
            "app.routes.feed._score_futures",
            AsyncMock(side_effect=lambda *a, **k: copy.deepcopy(scored_futures)),
        )
        monkeypatch.setattr("app.routes.feed._score_sports_mode_futures", AsyncMock(return_value=[]))

        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                # Read 1: Live NFL games active -> machinery-nfl-week in seats 1..10, <= 60s live bound.
                resp1 = await ac.get("/api/feed?limit=20&event_pct=0.15&machinery=1")
                assert resp1.status_code == 200
                assert "private" in resp1.headers.get("cache-control", "")
                assert "no-store" in resp1.headers.get("cache-control", "")
                body1 = resp1.json()
                top10_1 = body1["items"][:10]
                top10_ids_1 = [it["data"]["id"] for it in top10_1]
                assert "roundup:machinery-nfl-week" in top10_ids_1
                assert "roundup:closest-games-tonight" not in top10_ids_1
                assert sum(1 for it in top10_1 if _is_grouped_feed_card(it)) == 9
                assert sum(1 for it in top10_1 if it.get("type") == "futures") == 1
                assert sum(1 for it in top10_1 if it.get("type") in ("concept", "event")) == 0
                assert body1["cache"]["live"] is True
                assert body1["cache"]["ttl_seconds"] <= FEED_RESPONSE_TTL_LIVE_SECONDS
                assert body1["cache"]["stale_ttl_seconds"] <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

                await asyncio.sleep(0)
                await asyncio.sleep(0)

                # Verify expired (>=60s) live machinery page_base is refused rather than served stale.
                mach_pb_keys = [k for k in redis.contents if k.startswith("feed:machinery_pagebase:") and not k.endswith((":stale", ":last_good"))]
                assert mach_pb_keys, f"expected machinery page_base key in {list(redis.contents)}"
                mach_pb_key = mach_pb_keys[0]
                stale_base = json.loads(redis.contents[mach_pb_key])
                stale_base[FEED_PAGE_BASE_BUILT_AT_FIELD] = datetime.now(timezone.utc).timestamp() - 90.0
                redis.contents.clear()
                redis.contents[mach_pb_key] = json.dumps(stale_base)
                resp_expired = await ac.get("/api/feed?limit=20&event_pct=0.15&machinery=1")
                assert resp_expired.status_code == 200
                body_exp = resp_expired.json()
                assert body_exp["cache"]["status"] not in ("page_base_hit", "page_base_stale_hit")
                assert "roundup:machinery-nfl-week" in [it["data"]["id"] for it in body_exp["items"][:10]]

                # Read 1b: Standing live bundle only (no top-level status) still enters seats 1..10
                # and enforces cache.live == True & <= 30s / <= 60s end-to-end.
                live_state["nfl_live"] = False
                live_state["closest_live"] = True
                redis.contents.clear()
                rc._reset_last_good_for_tests()
                _roundup_local_cache.clear()
                resp1b = await ac.get("/api/feed?limit=20&event_pct=0.15&machinery=1")
                assert resp1b.status_code == 200
                body1b = resp1b.json()
                assert "roundup:closest-games-tonight" in [it["data"]["id"] for it in body1b["items"][:10]]
                assert body1b["cache"]["live"] is True
                assert body1b["cache"]["ttl_seconds"] <= FEED_RESPONSE_TTL_LIVE_SECONDS
                assert body1b["cache"]["stale_ttl_seconds"] <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

                # Read 2: Last live game ends between reads -> seat returns to cfp-picture, live=False.
                live_state["nfl_live"] = False
                live_state["closest_live"] = False
                redis.contents.clear()
                rc._reset_last_good_for_tests()
                _roundup_local_cache.clear()

                resp2 = await ac.get("/api/feed?limit=20&event_pct=0.15&machinery=1")
                assert resp2.status_code == 200
                body2 = resp2.json()
                top10_2 = body2["items"][:10]
                top10_ids_2 = [it["data"]["id"] for it in top10_2]
                assert "roundup:machinery-nfl-week" not in top10_ids_2
                assert "roundup:closest-games-tonight" not in top10_ids_2
                assert "roundup:cfp-picture" in top10_ids_2
                assert body2["cache"]["live"] is False
    finally:
        app.dependency_overrides.clear()
        ROUNDUP_PRODUCERS.clear()
        ROUNDUP_PRODUCERS.update(saved_producers)
        rc._reset_last_good_for_tests()
        _roundup_local_cache.clear()
