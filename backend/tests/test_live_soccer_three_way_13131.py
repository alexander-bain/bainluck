"""Regression tests for live soccer three-way chances (Home, Draw, Away) (#13131).

Verifies that live draw-priced soccer games (e.g. Brazil Serie A):
1. Serve Home, Draw, and Away summing to 100% on `/api/feed` and `/api/leagues/{sport}`,
   including scheduled games promoted to live right after kickoff and games where a
   stale or reversed bookmaker snapshot is present.
2. Never emit two chances summing to 100% with no draw (`away = 1 - home`) on
   `feed_scoring.format_event_data` when live three-way books are unavailable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.league_futures import _format_game_brief
from app.utils.draw_priced_winner import read_live_three_way_books
from app.utils.feed_scoring import format_event_data
from app.utils.hero_probability import HeroReading

FIXED_NOW = datetime(2025, 3, 10, 22, 0, 0, tzinfo=timezone.utc)


def test_live_soccer_feed_card_never_emits_two_way_complement_or_home_only_without_draw():
    hero = HeroReading(home_probability=0.62, away_probability=0.38, source="blend")
    data = format_event_data(
        event_id=15343915,
        external_id="br-15343915",
        sport_key="soccer_brazil_campeonato",
        sport_name="Brazil Serie A",
        home_team="Flamengo",
        away_team="Palmeiras",
        commence_time=FIXED_NOW - timedelta(minutes=30),
        status="live",
        home_score=1,
        away_score=0,
        current_home_prob=0.62,
        current_away_prob=0.38,
        current_draw_prob=None,
        opening_home_prob=0.45,
        opening_away_prob=0.28,
        opening_favorite="home",
        win_probability_sources={"espn": {"value": 0.62}},
        prob_source=None,
        game_clock="30'",
        period="1st Half",
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        hero=hero,
    )
    co = data["current_odds"]
    assert co["home_probability"] is None
    assert co["away_probability"] is None
    assert co["draw_probability"] is None
    assert data["hero_probability"] is None
    assert data["hero_probability_away"] is None
    assert data["hero_probability_draw"] is None


def test_live_soccer_feed_card_serves_home_draw_away_summing_to_100():
    hero = HeroReading(home_probability=0.52, away_probability=0.48, source="blend")
    data = format_event_data(
        event_id=15343915,
        external_id="br-15343915",
        sport_key="soccer_brazil_campeonato",
        sport_name="Brazil Serie A",
        home_team="Flamengo",
        away_team="Palmeiras",
        commence_time=FIXED_NOW - timedelta(minutes=30),
        status="live",
        home_score=1,
        away_score=0,
        current_home_prob=0.52,
        current_away_prob=0.22,
        current_draw_prob=0.26,
        opening_home_prob=0.45,
        opening_away_prob=0.28,
        opening_favorite="home",
        win_probability_sources={"betting_odds": {"value": 0.52}},
        prob_source=None,
        game_clock="30'",
        period="1st Half",
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        hero=hero,
    )
    co = data["current_odds"]
    assert co["home_rendered_percent"] + co["draw_rendered_percent"] + co["away_rendered_percent"] == 100
    assert data["hero_probability"] == pytest.approx(0.52)
    assert data["hero_probability_draw"] == pytest.approx(0.26)
    assert data["hero_probability_away"] == pytest.approx(0.22)


@pytest.mark.asyncio
async def test_read_live_three_way_books_filters_stale_pregame_snapshots():
    ev_live = SimpleNamespace(
        id=4001,
        status="live",
        commence_time=FIXED_NOW - timedelta(minutes=20),
        sport=SimpleNamespace(key="soccer_brazil_campeonato"),
    )
    snap_stale_pregame = SimpleNamespace(
        event_id=4001,
        bookmaker="book_old",
        home_win_probability=0.50,
        away_win_probability=0.50,  # stale 2-way pregame would break sum < 0.99 if kept
        captured_at=FIXED_NOW - timedelta(hours=3),
        valid_until=FIXED_NOW - timedelta(hours=2),
        home_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
    )
    snap_live_1 = SimpleNamespace(
        event_id=4001,
        bookmaker="draftkings",
        home_win_probability=0.55,
        away_win_probability=0.20,
        captured_at=FIXED_NOW - timedelta(minutes=2),
        valid_until=FIXED_NOW - timedelta(minutes=1),
        home_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
    )
    snap_live_2 = SimpleNamespace(
        event_id=4001,
        bookmaker="fanduel",
        home_win_probability=0.53,
        away_win_probability=0.22,
        captured_at=FIXED_NOW - timedelta(minutes=2),
        valid_until=FIXED_NOW - timedelta(minutes=1),
        home_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
    )

    class _FakeDB:
        async def execute(self, stmt):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(
                    all=lambda: [snap_stale_pregame, snap_live_1, snap_live_2]
                )
            )

    books = await read_live_three_way_books(_FakeDB(), [ev_live], FIXED_NOW)
    assert 4001 in books
    bh, ba = books[4001]
    assert bh == pytest.approx(0.54, abs=0.01)
    assert ba == pytest.approx(0.21, abs=0.01)
    assert bh + ba < 0.99


def test_league_game_brief_serves_three_way_for_live_brazil_soccer():
    now_utc = datetime.now(timezone.utc)
    ev = SimpleNamespace(
        id=15343915,
        external_id="br-15343915",
        home_team_name="Flamengo",
        away_team_name="Palmeiras",
        commence_time=now_utc - timedelta(minutes=40),
        completed_at=None,
        status="live",
        home_score=1,
        away_score=0,
        win_probability_sources={
            "betting": {"value": 0.54, "updated_at": now_utc.isoformat()}
        },
        opening_home_probability=0.45,
        opening_away_probability=0.28,
        period="40'",
        game_clock="40'",
        broadcast_info=None,
        espn_id="7001",
    )
    brief = _format_game_brief(
        ev,
        "soccer_brazil_campeonato",
        three_way_books=(0.54, 0.21),
    )
    co = brief["current_odds"]
    assert co["home_probability"] == pytest.approx(0.54)
    assert co["away_probability"] == pytest.approx(0.21)
    assert co["draw_probability"] == pytest.approx(0.25)
    assert co["home_rendered_percent"] + co["draw_rendered_percent"] + co["away_rendered_percent"] == 100
    assert brief["away_source_mark"]["state"] == "single"
    # Away source mark carries the away chance (0.21), never 1 - home (0.46).
    assert brief["away_source_mark"]["sources"][0]["probability"] == pytest.approx(0.21)


@pytest.mark.asyncio
async def test_read_live_three_way_books_folds_suppressed_twin_snapshots():
    """Cologne at Bayern Munich (15351899): live sportsbook rows sit on
    suppressed twin 15342140. Passing `absorbed_ids_by_event` lets feed and
    league rails resolve the exact same 90 / 7 / 3 as `/api/events/15351899`."""
    ev_canonical = SimpleNamespace(
        id=15351899,
        status="live",
        commence_time=FIXED_NOW - timedelta(minutes=30),
        sport=SimpleNamespace(key="soccer_germany_bundesliga"),
    )
    snap_twin_1 = SimpleNamespace(
        event_id=15342140,
        bookmaker="draftkings",
        home_win_probability=0.90,
        away_win_probability=0.03,
        captured_at=FIXED_NOW - timedelta(minutes=1),
        valid_until=FIXED_NOW,
        home_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
    )
    snap_twin_2 = SimpleNamespace(
        event_id=15342140,
        bookmaker="fanduel",
        home_win_probability=0.90,
        away_win_probability=0.03,
        captured_at=FIXED_NOW - timedelta(minutes=1),
        valid_until=FIXED_NOW,
        home_spread=None,
        over_under=None,
        projected_home_score=None,
        projected_away_score=None,
        home_moneyline=None,
        away_moneyline=None,
    )
    queried_ids: list[int] = []

    def _capture_query(ids):
        queried_ids.extend(ids)
        return ids

    class _FakeDB:
        async def execute(self, stmt):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [snap_twin_1, snap_twin_2])
            )

    books = await read_live_three_way_books(
        _FakeDB(),
        [ev_canonical],
        FIXED_NOW,
        latest_odds_query=_capture_query,
        absorbed_ids_by_event={15351899: (15342140,)},
    )
    assert set(queried_ids) == {15351899, 15342140}
    assert 15351899 in books
    bh, ba = books[15351899]
    assert bh == pytest.approx(0.90)
    assert ba == pytest.approx(0.03)


def test_cologne_at_bayern_away_source_mark_carries_away_chance_for_blended_sources():
    """On a 90 / 7 / 3 Bundesliga match with two blended sources (#13131 + #13269),
    Sportsbooks carries its own away chance (0.03, never 1 - 0.90 = 0.10) and a
    prediction venue without its own away quote is named with probability=None
    rather than shown a worked-out figure."""
    from app.utils.source_mark import blended_source_marks

    ev = SimpleNamespace(
        win_probability_sources={
            "betting": {"value": 0.90},
            "polymarket": {"value": 0.91},
            "betting_book_count": 10,
        }
    )
    home_mark, away_mark = blended_source_marks(
        ev,
        [("betting", 0.90), ("polymarket", 0.91)],
        method="weighted average",
        away_available=True,
        three_way_probs=(0.902, 0.0294, 0.0686),
        books_three_way=(0.90, 0.03),
    )
    home_by_key = {s["key"]: s["probability"] for s in home_mark["sources"]}
    away_by_key = {s["key"]: s["probability"] for s in away_mark["sources"]}
    assert home_by_key == {"betting": 0.90, "polymarket": 0.91}
    assert away_by_key["betting"] == pytest.approx(0.03, abs=1e-4)
    assert away_by_key["polymarket"] is None
    assert away_by_key["betting"] < 0.05  # definitely not 1 - 0.90 = 0.10

