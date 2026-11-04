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

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session


@compiles(JSONB, "sqlite")
def _jsonb_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


@compiles(ARRAY, "sqlite")
def _array_on_sqlite(type_, compiler, **kw):  # pragma: no cover - DDL shim
    return "JSON"


from app.models.models import Base, Event, OddsSnapshot, Sport, Team  # noqa: E402
from app.routes.containers import _hydrate_event_cards, get_container  # noqa: E402
from app.utils.hero_probability import resolve_hero  # noqa: E402
from app.utils.roundup_containers import (  # noqa: E402
    ROUNDUP_PRODUCERS,
    RoundupRefusal,
    reset_roundup_cache_for_tests,
    roundup_container_id,
    roundup_feed_items,
    roundup_revision,
)
from app.utils.window_events_closest import (  # noqa: E402
    CLOSEST_GAMES_TONIGHT_DEFINITION,
    CLOSEST_GAMES_TONIGHT_PRODUCER,
    CLOSEST_GAMES_TONIGHT_SLUG,
    PRODUCER_KIND_WINDOW_EVENTS_CLOSEST,
    _extract_blended_leader,
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
    hero_source: str | None = "blend",
    hero_observed_at: str | None = "2026-11-03T22:15:00+00:00",
    home_crest: str | None = "https://cdn.example/home.png",
    away_crest: str | None = "https://cdn.example/away.png",
    home_score: int | None = None,
    away_score: int | None = None,
    captured_at: str = "2026-11-03T22:00:00+00:00",
) -> dict[str, Any]:
    card: dict[str, Any] = {
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
    if hero_source is not None:
        card["hero_probability_source"] = hero_source
    if hero_observed_at is not None:
        card["hero_probability_observed_at"] = hero_observed_at
    return card


def _card_loader_for(cards: Sequence[Mapping[str, Any]]):
    async def _load(_db: Any, _start: datetime, _end: datetime) -> Sequence[Mapping[str, Any]]:
        return list(cards)

    return _load


class _AsyncSessionAdapter:
    """Thin async wrapper around an in-memory SQLite ``Session`` for ``_hydrate_event_cards``."""

    def __init__(self, session: Session) -> None:
        self._s = session

    async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
        res = self._s.execute(statement, *args)
        for obj in list(self._s.identity_map.values()):
            for attr in ("commence_time", "captured_at", "completed_at"):
                val = getattr(obj, attr, None)
                if isinstance(val, datetime) and val.tzinfo is None:
                    setattr(obj, attr, val.replace(tzinfo=timezone.utc))
        return res


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
        CLOSEST_GAMES_TONIGHT_DEFINITION,
        None,
        now=now,
        load_cards=_card_loader_for(three_games),
    )
    assert isinstance(outcome, RoundupRefusal)

    # Register a test producer pinned to `now` on the closest-games slug and verify 404 unavailable.
    pinned_producer = build_window_events_closest_producer(
        CLOSEST_GAMES_TONIGHT_DEFINITION,
        enabled=lambda: True,
        now_fn=lambda: now,
        load_cards=_card_loader_for(three_games),
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, CLOSEST_GAMES_TONIGHT_SLUG, pinned_producer)

    with pytest.raises(HTTPException) as exc:
        await get_container(
            slug=CLOSEST_GAMES_TONIGHT_SLUG, db=None
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
        load_cards=_card_loader_for(five_games),
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
        load_cards=_card_loader_for(five_games),
    )
    monkeypatch.setitem(ROUNDUP_PRODUCERS, second_def["slug"], second_producer)

    # 1. All-sports closest games tonight picks [303 (0.60), 302 (0.56), 301 (0.52), 305 (0.51)] of 5 games.
    served_tonight = await get_container(slug=CLOSEST_GAMES_TONIGHT_SLUG, db=None)
    assert served_tonight["state"] == "published"
    assert served_tonight["slug"] == CLOSEST_GAMES_TONIGHT_SLUG
    assert served_tonight["subtitle"] == "Bain Luck blend · the 4 closest of 5 games tonight"
    assert served_tonight["container"]["id"] == roundup_container_id(CLOSEST_GAMES_TONIGHT_SLUG)
    assert served_tonight["container"]["kind"] == "roundup"
    assert [m["id"] for m in served_tonight["sections"][0]["members"]] == [303, 302, 301, 305]
    assert served_tonight["revision"] == roundup_revision([303, 302, 301, 305])

    # 2. NBA-only definition excludes NHL game 305 and picks [304 (0.64), 303 (0.60), 302 (0.56), 301 (0.52)] of 4 NBA games.
    served_nba = await get_container(slug=second_def["slug"], db=None)
    assert served_nba["state"] == "published"
    assert served_nba["subtitle"] == "Bain Luck blend · the 4 closest of 4 NBA games tonight"
    assert [m["id"] for m in served_nba["sections"][0]["members"]] == [304, 303, 302, 301]
    assert served_nba["revision"] == roundup_revision([304, 303, 302, 301])

    # 3. roundup_feed_items includes both definitions with matching collection_ref revisions and event items.
    feed_items = await roundup_feed_items(None)
    by_slug = {it["data"]["collection_ref"]["slug"]: it for it in feed_items}
    assert set(by_slug) == {CLOSEST_GAMES_TONIGHT_SLUG, second_def["slug"]}
    tonight_card = by_slug[CLOSEST_GAMES_TONIGHT_SLUG]
    assert tonight_card["data"]["collection_ref"]["revision"] == served_tonight["revision"]
    assert tonight_card["data"]["roundup"]["footer"] == served_tonight["subtitle"]
    assert [it["type"] for it in tonight_card["data"]["items"]] == ["event"] * 4
    assert [it["data"]["id"] for it in tonight_card["data"]["items"]] == [303, 302, 301, 305]


@pytest.mark.asyncio
async def test_row_probability_equals_event_page_hero_through_hydrate_event_cards_and_refuses_books_only(
    monkeypatch: pytest.MonkeyPatch,
):
    """Through ``_hydrate_event_cards`` on a fake session:
    1. Each round-up row probability comes from ``resolve_hero`` (``hero_probability`` /
       ``hero_probability_away`` on the hydrated event card — the same function that
       produces the event page's hero number), NOT from the books-only ``current_odds``.
    2. Each row's ``observed_at`` equals ``hero_probability_observed_at`` (the hero's
       blend stamp), NOT ``current_odds.captured_at``.
    3. Games whose ``hero_probability_source`` is ``"opening"``, ``"final_unresolved"``,
       ``"settled"``, or absent (books-only ``current_odds``) are refused while
       blended siblings survive.
    """
    now = datetime.now(timezone.utc)
    tipoff = now + timedelta(hours=2)
    hero_stamp = (now - timedelta(minutes=3)).isoformat()
    odds_captured_dt = now - timedelta(minutes=10)

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)

    sport_id = 41
    team_pairs = [
        (401, "Boston Celtics", "Celtics", "New York Knicks", "Knicks", 0.56, 0.72, "scheduled", None),
        (402, "Los Angeles Lakers", "Lakers", "Phoenix Suns", "Suns", 0.52, 0.68, "scheduled", None),
        (403, "Milwaukee Bucks", "Bucks", "Miami Heat", "Heat", 0.43, 0.65, "scheduled", None),
        (404, "Denver Nuggets", "Nuggets", "Minnesota Timberwolves", "Timberwolves", 0.60, 0.75, "scheduled", None),
        # Event 405 has NO win_probability_sources and no opening -> resolve_hero is None (absent):
        (405, "Golden State Warriors", "Warriors", "Sacramento Kings", "Kings", None, 0.505, "scheduled", None),
        # Event 406 has NO win_probability_sources and an opening line -> hero_probability_source == "opening":
        (406, "Dallas Mavericks", "Mavericks", "Houston Rockets", "Rockets", None, 0.501, "scheduled", 0.502),
        # Event 407 has a finished status with no scores and a blend -> hero_probability_source == "final_unresolved":
        (407, "Cleveland Cavaliers", "Cavaliers", "Orlando Magic", "Magic", 0.503, 0.503, "completed", None),
    ]

    def _portable_odds_query(event_ids):
        return select(OddsSnapshot).where(OddsSnapshot.event_id.in_(event_ids))

    defn = {
        **CLOSEST_GAMES_TONIGHT_DEFINITION,
        "rule": {
            **CLOSEST_GAMES_TONIGHT_DEFINITION["rule"],
            "window": {
                "start": (now - timedelta(hours=1)).isoformat(),
                "end": (now + timedelta(hours=6)).isoformat(),
            },
        },
    }

    with (
        patch("app.routes.events._load_gei_percentiles", new=AsyncMock(return_value={})),
        patch("app.routes.events.latest_odds_per_bookmaker_query", new=_portable_odds_query),
        patch("app.routes.events._team_cache", {}),
        patch("app.routes.events._team_cache_time", 0.0),
        Session(eng, expire_on_commit=False) as s,
    ):
        s.add(Sport(id=sport_id, key="basketball_nba", name="NBA", group="Basketball"))
        next_team_id = 1
        for (
            eid,
            home_full,
            home_short,
            away_full,
            away_short,
            blend_home,
            book_home,
            ev_status,
            opening_home,
        ) in team_pairs:
            for full_name, short_name in ((home_full, home_short), (away_full, away_short)):
                s.add(
                    Team(
                        id=next_team_id,
                        sport_id=sport_id,
                        name=full_name,
                        abbreviation=short_name[:3].upper(),
                        logo_url=f"https://cdn.example/{short_name.lower()}.png",
                        logo_url_small=f"https://cdn.example/{short_name.lower()}-sm.png",
                    )
                )
                next_team_id += 1
            sources = (
                {
                    "betting": {"value": blend_home, "updated_at": hero_stamp},
                    "kalshi": {"value": blend_home, "updated_at": hero_stamp},
                    "polymarket": {"value": blend_home, "updated_at": hero_stamp},
                }
                if blend_home is not None
                else {}
            )
            s.add(
                Event(
                    id=eid,
                    sport_id=sport_id,
                    home_team_name=home_full,
                    away_team_name=away_full,
                    commence_time=tipoff,
                    status=ev_status,
                    win_probability_sources=sources,
                    opening_home_probability=opening_home,
                    opening_away_probability=(round(1.0 - opening_home, 4) if opening_home is not None else None),
                )
            )
            s.add(
                OddsSnapshot(
                    event_id=eid,
                    bookmaker="fanduel",
                    home_win_probability=book_home,
                    away_win_probability=round(1.0 - book_home, 4),
                    captured_at=odds_captured_dt,
                )
            )
        s.commit()

        fake_db = _AsyncSessionAdapter(s)
        hydrated_cards, failed = await _hydrate_event_cards(
            fake_db, [401, 402, 403, 404, 405, 406, 407]
        )
        assert failed == {}
        # Event 405 has books-only current_odds (0.505) and no hero_probability:
        assert hydrated_cards[405]["current_odds"]["home_probability"] == pytest.approx(0.505)
        assert "hero_probability" not in hydrated_cards[405]
        # Event 406 has hero_probability_source == "opening" (0.502):
        assert hydrated_cards[406]["hero_probability_source"] == "opening"
        assert hydrated_cards[406]["hero_probability"] == pytest.approx(0.502)
        assert _extract_blended_leader(hydrated_cards[406]) is None
        # Event 407 has hero_probability_source == "final_unresolved" (0.503):
        assert hydrated_cards[407]["hero_probability_source"] == "final_unresolved"
        assert hydrated_cards[407]["hero_probability"] == pytest.approx(0.503)
        assert _extract_blended_leader(hydrated_cards[407]) is None

        outcome = await produce_window_events_closest(defn, fake_db, now=now)
        assert not isinstance(outcome, RoundupRefusal)
        # Events 405 (absent), 406 (opening), and 407 (final_unresolved) are all refused
        # while the 4 blended siblings [404, 403, 401, 402] survive:
        assert outcome.footer == "Bain Luck blend · the 4 closest of 4 games tonight"
        assert [r["event_id"] for r in outcome.rows] == [404, 403, 401, 402]

        # Every row's probability equals resolve_hero(event)'s leader and its observed_at
        # equals hero_probability_observed_at (not current_odds.captured_at):
        for row, member in zip(outcome.rows, outcome.members):
            eid = row["event_id"]
            ev = s.get(Event, eid)
            hero = resolve_hero(ev)
            assert hero is not None
            assert hero.source == "blend"
            expected_leader = max(hero.home_probability, hero.away_probability)
            card_leader = max(
                member["card"]["hero_probability"],
                member["card"]["hero_probability_away"],
            )
            assert row["probability"] == pytest.approx(expected_leader)
            assert row["probability"] == pytest.approx(card_leader)
            assert row["observed_at"] == member["card"]["hero_probability_observed_at"] == hero_stamp
            assert row["observed_at"] != hydrated_cards[eid]["current_odds"]["captured_at"]
        # Specifically for 403 (home=0.43, away=0.57 in blend vs 0.65 home in books):
        row_403 = next(r for r in outcome.rows if r["event_id"] == 403)
        assert row_403["probability"] == pytest.approx(0.57)
        assert row_403["label"] == "Miami Heat at Milwaukee Bucks: Miami Heat"

        # If any candidate event fails card hydration, produce_window_events_closest
        # refuses all-or-nothing rather than silently omitting the failed game:
        monkeypatch.setattr(
            "app.routes.containers._hydrate_event_cards",
            lambda _db, _ids: _async_return(
                (
                    {k: v for k, v in hydrated_cards.items() if k != 404},
                    {404: "hydration_error"},
                )
            ),
        )
        refused_on_hydration_failure = await produce_window_events_closest(
            defn, fake_db, now=now
        )
        assert isinstance(refused_on_hydration_failure, RoundupRefusal)
        assert refused_on_hydration_failure.reasons == (("window", "hydrate_failed_1"),)


async def _async_return(val):
    return val


def test_opening_and_final_unresolved_refused_while_blended_sibling_survives():
    """``_extract_blended_leader`` and ``select_closest_window_events`` accept only
    ``hero_probability_source == "blend"`` and refuse ``opening``, ``final_unresolved``,
    ``settled``, and absent sources, reading ``observed_at`` from ``hero_probability_observed_at``.
    """
    now = datetime(2026, 11, 3, 22, 0, tzinfo=timezone.utc)
    w_start, w_end = sports_day_window(now)
    hero_stamp = "2026-11-03T22:19:45+00:00"
    odds_stamp = "2026-11-03T19:00:00+00:00"

    cards = [
        # Non-blend sources with closer numbers (0.501–0.504) that must be refused:
        _game_card(501, home="Mavs", away="Rockets", home_prob=0.501, away_prob=0.499, hero_source="opening", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(502, home="Cavs", away="Magic", home_prob=0.502, away_prob=0.498, hero_source="final_unresolved", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(503, home="Nets", away="Hawks", home_prob=1.0, away_prob=0.0, hero_source="settled", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(504, home="Pacers", away="Bulls", home_prob=0.504, away_prob=0.496, hero_source=None, hero_observed_at=hero_stamp, captured_at=odds_stamp),
        # 4 blended siblings that survive:
        _game_card(511, home="Celtics", away="Knicks", home_prob=0.52, away_prob=0.48, hero_source="blend", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(512, home="Lakers", away="Suns", home_prob=0.55, away_prob=0.45, hero_source="blend", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(513, home="Bucks", away="Heat", home_prob=0.58, away_prob=0.42, hero_source="blend", hero_observed_at=hero_stamp, captured_at=odds_stamp),
        _game_card(514, home="Nuggets", away="Warriors", home_prob=0.61, away_prob=0.39, hero_source="blend", hero_observed_at=hero_stamp, captured_at=odds_stamp),
    ]

    for refused_id in (501, 502, 503, 504):
        card = next(c for c in cards if c["id"] == refused_id)
        assert _extract_blended_leader(card) is None

    result = select_closest_window_events(
        cards,
        now=now,
        window_start=w_start,
        window_end=w_end,
        count=4,
        minimum=4,
    )
    assert not isinstance(result, RoundupRefusal)
    assert [r["event_id"] for r in result.rows] == [514, 513, 512, 511]
    assert result.footer == "Bain Luck blend · the 4 closest of 4 games tonight"
    for row in result.rows:
        assert row["observed_at"] == hero_stamp
        assert row["observed_at"] != odds_stamp

    # Exact 50/50 tie and whole-number-rounded 50/50 tie refuse to name a single
    # leader on the row (#11941):
    tie_card = _game_card(
        599,
        home="Celtics",
        away="Knicks",
        home_prob=0.5,
        away_prob=0.5,
        hero_source="blend",
        hero_observed_at=hero_stamp,
        captured_at=odds_stamp,
    )
    assert _extract_blended_leader(tie_card) == (
        0.5,
        "Knicks and Celtics",
        "Knicks at Celtics",
        hero_stamp,
    )
    rounded_tie_card = _game_card(
        600,
        home="Celtics",
        away="Knicks",
        home_prob=0.502,
        away_prob=0.498,
        hero_source="blend",
        hero_observed_at=hero_stamp,
        captured_at=odds_stamp,
    )
    assert _extract_blended_leader(rounded_tie_card) == (
        0.502,
        "Knicks and Celtics",
        "Knicks at Celtics",
        hero_stamp,
    )
