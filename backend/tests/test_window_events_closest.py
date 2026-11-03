"""Tests for the reusable ``window_events_closest`` producer kind and the
``roundup-closest-games-tonight`` definition (#6 in ``docs/containers/catalog-2026-11.md``).

Covers Alex's rulings B, C, D on NOW #11852:
* Ruling B: ``containers.kind`` stays the subject type (``"roundup"``) while the
  stored definition carries ``membership: "time-boxed-tonight"``.
* Ruling C: ``window: "sports-day"`` is 6 AM–6 AM ET (``America/New_York``).
* Ruling D: built as a stored definition over the reusable ``window_events_closest``
  producer kind so another container of that shape is a definition, not a deploy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import HTTPException

from app.routes.containers import get_container
from app.utils.roundup_containers import (
    ROUNDUP_PRODUCERS,
    RoundupRefusal,
    reset_roundup_cache_for_tests,
    roundup_container_id,
    roundup_feed_items,
    roundup_revision,
)
from app.utils.window_events_closest import (
    CLOSEST_GAMES_TONIGHT_DEFINITION,
    CLOSEST_GAMES_TONIGHT_PRODUCER,
    CLOSEST_GAMES_TONIGHT_SLUG,
    PRODUCER_KIND_WINDOW_EVENTS_CLOSEST,
    build_window_events_closest_producer,
    produce_window_events_closest,
    select_closest_window_events,
    sports_day_window,
)


def _game_card(
    event_id: int,
    *,
    home: str = "Celtics",
    away: str = "Knicks",
    sport: str = "basketball_nba",
    status: str = "scheduled",
    commence_time: str = "2026-11-04T00:30:00+00:00",
    home_prob: float | None = 0.54,
    away_prob: float | None = 0.46,
    home_crest: str | None = "https://cdn.example/home.png",
    away_crest: str | None = "https://cdn.example/away.png",
    home_score: int | None = None,
    away_score: int | None = None,
    captured_at: str = "2026-11-03T22:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": event_id,
        "home_team": home,
        "away_team": away,
        "home_team_name": home,
        "away_team_name": away,
        "sport": sport,
        "status": status,
        "commence_time": commence_time,
        "home_score": home_score,
        "away_score": away_score,
        "home_team_data": {"short_name": home, "logo_small": home_crest} if home_crest else {},
        "away_team_data": {"short_name": away, "logo_small": away_crest} if away_crest else {},
        "hero_probability": home_prob,
        "hero_probability_away": away_prob,
        "current_odds": {
            "home_probability": home_prob,
            "away_probability": away_prob,
            "captured_at": captured_at,
        },
    }


class _FakeEventResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)

    def scalars(self) -> "_FakeEventResult":
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


class _FakeEventSession:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = list(rows)

    async def execute(self, _stmt: Any) -> _FakeEventResult:
        return _FakeEventResult(self.rows)


def test_stored_definition_carries_membership_and_kind_per_ruling_b():
    """Ruling B + D: stored definition has membership='time-boxed-tonight' and kind='roundup'."""
    defn = CLOSEST_GAMES_TONIGHT_DEFINITION
    assert defn["slug"] == CLOSEST_GAMES_TONIGHT_SLUG == "roundup-closest-games-tonight"
    assert defn["membership"] == "time-boxed-tonight"
    assert defn["kind"] == "roundup"
    assert defn["name"] == "The closest games tonight"
    assert defn["category"] == "sports"
    assert defn["section_title"] == "The 4 closest games"
    assert defn["footer"] == "Bain Luck blend · the 4 closest of {n} games tonight"
    assert defn["rule"]["producer"] == PRODUCER_KIND_WINDOW_EVENTS_CLOSEST
    assert defn["rule"]["window"] == "sports-day"
    assert defn["rule"]["minimum"] == 4
    assert defn["rule"]["count"] == 4
    assert defn["rule"]["relation"] == "exact"
    assert defn["rule"]["refusal"] == "all-or-nothing"

    assert CLOSEST_GAMES_TONIGHT_PRODUCER.slug == CLOSEST_GAMES_TONIGHT_SLUG
    assert CLOSEST_GAMES_TONIGHT_PRODUCER.membership == "time-boxed-tonight"
    assert CLOSEST_GAMES_TONIGHT_PRODUCER.kind == "roundup"
    assert ROUNDUP_PRODUCERS.get(CLOSEST_GAMES_TONIGHT_SLUG) is CLOSEST_GAMES_TONIGHT_PRODUCER


def test_sports_day_window_is_6am_to_6am_et_per_ruling_c():
    """Ruling C: the sports day runs 6 AM to 6 AM America/New_York."""
    # Tue Nov 3, 2026 at 7:00 PM EST (2026-11-04 00:00 UTC) -> Nov 3 06:00 EST to Nov 4 06:00 EST.
    evening_utc = datetime(2026, 11, 4, 0, 0, tzinfo=timezone.utc)
    start_utc, end_utc = sports_day_window(evening_utc)
    assert start_utc == datetime(2026, 11, 3, 11, 0, tzinfo=timezone.utc)
    assert end_utc == datetime(2026, 11, 4, 11, 0, tzinfo=timezone.utc)

    # Wed Nov 4, 2026 at 1:30 AM EST (06:30 UTC, still before 6 AM ET) -> same Nov 3 sports day.
    after_midnight_et = datetime(2026, 11, 4, 6, 30, tzinfo=timezone.utc)
    start_late, end_late = sports_day_window(after_midnight_et)
    assert (start_late, end_late) == (start_utc, end_utc)

    # Wed Nov 4, 2026 at 6:00 AM EST (11:00 UTC) -> rolls into Nov 4 sports day.
    next_morning_et = datetime(2026, 11, 4, 11, 0, tzinfo=timezone.utc)
    start_next, end_next = sports_day_window(next_morning_et)
    assert start_next == datetime(2026, 11, 4, 11, 0, tzinfo=timezone.utc)
    assert end_next == datetime(2026, 11, 5, 11, 0, tzinfo=timezone.utc)


def test_selects_four_lowest_blended_leaders_and_orders_highest_first():
    """#6 member rule: from tonight's eligible set, pick the 4 games with the lowest
    blended leader probability, shown highest first, and format '{n}' with the eligible count.
    """
    now = datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)  # 5:00 PM EST
    w_start, w_end = sports_day_window(now)

    cards = [
        # 7 eligible games in tonight's sports day (including a live game and a late 1:30 AM ET tipoff)
        _game_card(101, home="Lakers", away="Suns", home_prob=0.51, away_prob=0.49, commence_time="2026-11-04T03:00:00+00:00"),
        _game_card(102, home="Celtics", away="Bucks", home_prob=0.61, away_prob=0.39, commence_time="2026-11-04T00:30:00+00:00"),
        _game_card(103, home="Rangers", away="Devils", sport="icehockey_nhl", status="live", home_score=2, away_score=2, home_prob=0.46, away_prob=0.54, commence_time="2026-11-03T21:00:00+00:00"),
        _game_card(104, home="Nuggets", away="Timberwolves", home_prob=0.58, away_prob=0.42, commence_time="2026-11-04T06:30:00+00:00"),  # 1:30 AM ET (inside sports day!)
        _game_card(105, home="Thunder", away="Pistons", home_prob=0.78, away_prob=0.22, commence_time="2026-11-04T01:00:00+00:00"),
        _game_card(106, home="Bruins", away="Maple Leafs", sport="icehockey_nhl", home_prob=0.67, away_prob=0.33, commence_time="2026-11-04T00:00:00+00:00"),
        _game_card(107, home="Warriors", away="Kings", home_prob=0.73, away_prob=0.27, commence_time="2026-11-04T03:30:00+00:00"),
        # Ineligible games that must be excluded from both selection and '{n}':
        # 1) Tomorrow's sports day (after 6 AM ET Nov 4)
        _game_card(201, home="Heat", away="Bulls", home_prob=0.505, away_prob=0.495, commence_time="2026-11-04T12:00:00+00:00"),
        # 2) Finished game
        _game_card(202, home="Cavs", away="Magic", status="completed", home_prob=0.505, away_prob=0.495, commence_time="2026-11-03T18:00:00+00:00"),
        # 3) Missing away crest
        _game_card(203, home="Spurs", away="Rockets", away_crest=None, home_prob=0.505, away_prob=0.495, commence_time="2026-11-04T01:00:00+00:00"),
        # 4) pro_minor league
        _game_card(204, home="Bears", away="Wolf Pack", sport="icehockey_ahl", home_prob=0.505, away_prob=0.495, commence_time="2026-11-04T01:00:00+00:00"),
        # 5) Live game with null scores on both sides
        _game_card(205, home="Napoli", away="Juventus", status="live", home_score=None, away_score=None, home_prob=0.505, away_prob=0.495, commence_time="2026-11-03T21:00:00+00:00"),
        # 6) Three-way soccer game with withheld away_probability=None (#6960)
        _game_card(206, home="Arsenal", away="Chelsea", sport="soccer_epl", home_prob=0.505, away_prob=None, commence_time="2026-11-04T01:00:00+00:00"),
    ]

    result = select_closest_window_events(
        cards,
        now=now,
        window_start=w_start,
        window_end=w_end,
        count=4,
        minimum=4,
        footer_template="Bain Luck blend · the 4 closest of {n} games tonight",
    )
    assert not isinstance(result, RoundupRefusal)
    # 4 lowest leaders are 101 (0.51), 103 (0.54 Devils), 104 (0.58), 102 (0.61);
    # ordered highest leader first -> [102 (0.61), 104 (0.58), 103 (0.54), 101 (0.51)].
    assert [m["id"] for m in result.members] == [102, 104, 103, 101]
    assert [m["type"] for m in result.members] == ["event", "event", "event", "event"]
    assert [r["event_id"] for r in result.rows] == [102, 104, 103, 101]
    assert [r["probability"] for r in result.rows] == [0.61, 0.58, 0.54, 0.51]
    assert result.rows[0]["label"] == "Bucks at Celtics: Celtics"
    assert result.rows[2]["label"] == "Devils at Rangers: Devils"
    assert result.footer == "Bain Luck blend · the 4 closest of 7 games tonight"


@pytest.mark.asyncio
async def test_fewer_than_four_eligible_games_refuses_and_404s_unavailable(monkeypatch):
    """#6 minimum=4: fewer than 4 eligible games -> RoundupRefusal, no feed card, and 404 unavailable."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("CLOSEST_GAMES_TONIGHT_ENABLED", "true")
    reset_roundup_cache_for_tests()

    now = datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)
    three_games = [
        _game_card(101, home_prob=0.52, away_prob=0.48),
        _game_card(102, home_prob=0.55, away_prob=0.45),
        _game_card(103, home_prob=0.59, away_prob=0.41),
    ]
    outcome = await produce_window_events_closest(
        CLOSEST_GAMES_TONIGHT_DEFINITION, three_games, now=now
    )
    assert isinstance(outcome, RoundupRefusal)

    # Register a test producer pinned to `now` on the closest-games slug and verify 404 unavailable.
    pinned_producer = build_window_events_closest_producer(
        CLOSEST_GAMES_TONIGHT_DEFINITION,
        enabled=lambda: True,
        now_fn=lambda: now,
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, CLOSEST_GAMES_TONIGHT_SLUG, pinned_producer)

    with pytest.raises(HTTPException) as exc:
        await get_container(
            slug=CLOSEST_GAMES_TONIGHT_SLUG, db=_FakeEventSession(three_games)
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == {
        "state": "unavailable",
        "slug": CLOSEST_GAMES_TONIGHT_SLUG,
    }


@pytest.mark.asyncio
async def test_reusable_producer_serves_container_and_second_definition_without_new_code(
    monkeypatch,
):
    """Ruling D: a second definition using ``producer: window_events_closest`` works
    from its definition alone, and the served container matches the feed card's 4
    members and revision.
    """
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_CACHE_ENABLED", "false")
    monkeypatch.setenv("NFL_DIVISION_ROUNDUP_ENABLED", "false")
    reset_roundup_cache_for_tests()

    now = datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)
    five_games = [
        _game_card(301, home="Celtics", away="Knicks", sport="basketball_nba", home_prob=0.52, away_prob=0.48),
        _game_card(302, home="Lakers", away="Suns", sport="basketball_nba", home_prob=0.56, away_prob=0.44),
        _game_card(303, home="Bucks", away="Heat", sport="basketball_nba", home_prob=0.60, away_prob=0.40),
        _game_card(304, home="Nuggets", away="Warriors", sport="basketball_nba", home_prob=0.64, away_prob=0.36),
        _game_card(305, home="Rangers", away="Devils", sport="icehockey_nhl", home_prob=0.51, away_prob=0.49),
    ]

    pinned_tonight = build_window_events_closest_producer(
        CLOSEST_GAMES_TONIGHT_DEFINITION,
        enabled=lambda: True,
        now_fn=lambda: now,
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, CLOSEST_GAMES_TONIGHT_SLUG, pinned_tonight)

    # A second definition using the same reusable producer kind (filtered to NBA only):
    second_def = {
        "slug": "roundup-closest-nba-games-tonight",
        "membership": "time-boxed-tonight",
        "kind": "roundup",
        "name": "The closest NBA games tonight",
        "category": "nba",
        "tag": "NBA",
        "section_title": "The 4 closest NBA games",
        "footer": "Bain Luck blend · the 4 closest of {n} NBA games tonight",
        "rule": {
            "producer": "window_events_closest",
            "window": "sports-day",
            "league": "nba",
            "count": 4,
            "minimum": 4,
            "relation": "exact",
            "refusal": "all-or-nothing",
        },
    }
    second_producer = build_window_events_closest_producer(
        second_def,
        enabled=lambda: True,
        now_fn=lambda: now,
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, second_def["slug"], second_producer)

    session = _FakeEventSession(five_games)

    # 1. All-sports closest games tonight picks [303 (0.60), 302 (0.56), 301 (0.52), 305 (0.51)] of 5 games.
    served_tonight = await get_container(slug=CLOSEST_GAMES_TONIGHT_SLUG, db=session)
    assert served_tonight["state"] == "published"
    assert served_tonight["slug"] == CLOSEST_GAMES_TONIGHT_SLUG
    assert served_tonight["subtitle"] == "Bain Luck blend · the 4 closest of 5 games tonight"
    assert served_tonight["container"]["id"] == roundup_container_id(CLOSEST_GAMES_TONIGHT_SLUG)
    assert served_tonight["container"]["kind"] == "roundup"
    assert [m["id"] for m in served_tonight["sections"][0]["members"]] == [303, 302, 301, 305]
    assert served_tonight["revision"] == roundup_revision([303, 302, 301, 305])

    # 2. NBA-only definition excludes NHL game 305 and picks [304 (0.64), 303 (0.60), 302 (0.56), 301 (0.52)] of 4 NBA games.
    served_nba = await get_container(slug=second_def["slug"], db=session)
    assert served_nba["state"] == "published"
    assert served_nba["subtitle"] == "Bain Luck blend · the 4 closest of 4 NBA games tonight"
    assert [m["id"] for m in served_nba["sections"][0]["members"]] == [304, 303, 302, 301]
    assert served_nba["revision"] == roundup_revision([304, 303, 302, 301])

    # 3. roundup_feed_items includes both definitions with matching collection_ref revisions and event items.
    feed_items = await roundup_feed_items(session)
    by_slug = {it["data"]["collection_ref"]["slug"]: it for it in feed_items}
    assert set(by_slug) == {CLOSEST_GAMES_TONIGHT_SLUG, second_def["slug"]}
    tonight_card = by_slug[CLOSEST_GAMES_TONIGHT_SLUG]
    assert tonight_card["data"]["collection_ref"]["revision"] == served_tonight["revision"]
    assert tonight_card["data"]["roundup"]["footer"] == served_tonight["subtitle"]
    assert [it["type"] for it in tonight_card["data"]["items"]] == ["event"] * 4
    assert [it["data"]["id"] for it in tonight_card["data"]["items"]] == [303, 302, 301, 305]
