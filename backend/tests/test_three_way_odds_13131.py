"""#13131 — Three-way games serve Home, Draw, and Away adding to 100%, never one orphan number.

Specimen: Philadelphia Union at New England Revolution (`15345867`, `soccer_usa_mls`).
All 11 sportsbooks price home ~0.31 and away ~0.43 (leaving ~0.26 for the draw).
Previously the server overwrote away with `1 - home`, then `printable_away` wiped
it to `None`, leaving only `31%` for New England Revolution and nothing for
Philadelphia Union or Draw.

Rules pinned here:
1. When sportsbooks give both home and away summing strictly below 1 on a
   draw-priced sport, `/api/events/{id}`, `/api/events` (and search), and
   `/api/feed` all serve `home_probability`, `away_probability`, and
   `draw_probability` summing to 1.0, plus whole rendered percents summing to 100.
2. When a draw-priced game has only one leg (no 3-way books, e.g. Kalshi/Polymarket
   home-only, or 2-way complement books), non-settled cards get nothing for chance
   (`None` across `current_odds` and `hero_probability*`) — never one orphan number.
3. Two-way sports (NBA, NFL) and settled soccer results (`1.0/0.0`, `0.5/0.5`)
   are untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Event, Sport
from app.routes import events as events_route
from app.utils.draw_priced_winner import (
    rendered_three_way_percents,
    resolve_three_way_probabilities,
)
from app.utils.feed_scoring import format_event_data
from app.utils.hero_probability import HeroReading
from tests.test_event_payload_draw_priced_away_6238 import (
    _event as _detail_event,
    _payload as _detail_payload,
    _snapshot as _detail_snapshot,
)


def _utc_offset(hours: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Pure math: resolve_three_way_probabilities & rendered_three_way_percents
# ---------------------------------------------------------------------------


class TestResolveThreeWayProbabilities:
    def test_union_at_revolution_specimen_15345867(self):
        res = resolve_three_way_probabilities(
            0.31,
            books_home=0.3106,
            books_away=0.4307,
            sport_key="soccer_usa_mls",
        )
        assert res is not None
        home, away, draw = res
        assert home == pytest.approx(0.31, abs=1e-6)
        assert away == pytest.approx(0.4311, abs=1e-3)
        assert draw == pytest.approx(0.2589, abs=1e-3)
        assert home + away + draw == pytest.approx(1.0, abs=1e-6)

        hp, dp, ap = rendered_three_way_percents(home, draw, away)
        assert (hp, dp, ap) == (31, 26, 43)
        assert hp + dp + ap == 100

    def test_wolves_draw_forest_premier_league_control(self):
        res = resolve_three_way_probabilities(
            0.28,
            books_home=0.28,
            books_away=0.46,
            sport_key="soccer_epl",
        )
        assert res == (0.28, 0.46, 0.26)
        hp, dp, ap = rendered_three_way_percents(res[0], res[2], res[1])
        assert (hp, dp, ap) == (28, 26, 46)
        assert hp + dp + ap == 100

    @pytest.mark.parametrize(
        ("home", "draw", "away"),
        [
            (0.3333, 0.3334, 0.3333),
            (0.3100, 0.2589, 0.4311),
            (0.7050, 0.1653, 0.1297),
            (0.2800, 0.2600, 0.4600),
            (0.4950, 0.2550, 0.2500),
            (0.8550, 0.0950, 0.0500),
            (0.0550, 0.1450, 0.8000),
        ],
    )
    def test_rendered_three_way_percents_always_sum_to_100_and_match_ios_draw(
        self, home, draw, away
    ):
        hp, dp, ap = rendered_three_way_percents(home, draw, away)
        assert hp + dp + ap == 100
        assert all(0 <= p <= 100 for p in (hp, dp, ap))
        # Matches iOS 1.0.7 formatProbability(draw, renderedPercent: nil)
        import math

        assert dp == int(math.floor(draw * 100.0 + 0.5))

    def test_blend_shift_preserves_home_and_stays_in_unit_simplex(self):
        # Fulham @ Man City: blend 0.705 vs books (0.6874, 0.1374)
        res = resolve_three_way_probabilities(
            0.705,
            books_home=0.6874,
            books_away=0.1374,
            sport_key="soccer_epl",
        )
        assert res is not None
        home, away, draw = res
        assert home == pytest.approx(0.705)
        assert 0 < away < 1 and 0 < draw < 1
        assert home + away + draw == pytest.approx(1.0, abs=1e-6)
        hp, dp, ap = rendered_three_way_percents(home, draw, away)
        assert hp + dp + ap == 100

    def test_refuses_two_way_sports_and_incomplete_or_complement_books(self):
        assert resolve_three_way_probabilities(
            0.55, books_home=0.55, books_away=0.45, sport_key="basketball_nba"
        ) is None
        assert resolve_three_way_probabilities(
            0.31, books_home=0.31, books_away=None, sport_key="soccer_usa_mls"
        ) is None
        assert resolve_three_way_probabilities(
            0.31, books_home=0.31, books_away=0.69, sport_key="soccer_usa_mls"
        ) is None


# ---------------------------------------------------------------------------
# Detail route (/api/events/{id}) + List/Search formatter agreement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_and_list_agree_on_15345867_three_way_books():
    ev_detail = _detail_event(
        sport_key="soccer_usa_mls",
        home_prob=0.31,
        event_id=15345867,
        status="scheduled",
        home_score=None,
        away_score=None,
        opening_home=0.3106,
        opening_away=0.4307,
    )
    ev_detail.commence_time = _utc_offset(48)
    snaps = [
        _detail_snapshot(0.3164, 0.4243, bookmaker="betmgm"),
        _detail_snapshot(0.3100, 0.4307, bookmaker="betonlineag"),
        _detail_snapshot(0.3054, 0.4371, bookmaker="betrivers"),
    ]
    detail_payload = await _detail_payload(ev_detail, snapshots=snaps)

    co = detail_payload["current_odds"]
    assert co["home_probability"] == pytest.approx(0.31, abs=1e-4)
    assert co["away_probability"] == pytest.approx(0.431, abs=1e-2)
    assert co["draw_probability"] == pytest.approx(0.259, abs=1e-2)
    assert co["home_probability"] + co["away_probability"] + co["draw_probability"] == pytest.approx(1.0, abs=1e-5)
    assert (
        co["home_rendered_percent"]
        + co["draw_rendered_percent"]
        + co["away_rendered_percent"]
        == 100
    )
    assert detail_payload["hero_probability"] == co["home_probability"]
    assert detail_payload["hero_probability_away"] == co["away_probability"]
    assert detail_payload["hero_probability_draw"] == co["draw_probability"]
    assert detail_payload["away_source_mark"]["state"] != "none"

    # List / Search arm on the same fixture
    ev_list = Event(
        id=15345867,
        sport_id=1,
        home_team_name="New England Revolution",
        away_team_name="Philadelphia Union",
        commence_time=_utc_offset(48),
        status="scheduled",
        win_probability_sources={"betting": {"value": 0.31, "type": "market"}},
        opening_home_probability=0.3106,
        opening_away_probability=0.4307,
    )
    ev_list.sport = Sport(id=1, key="soccer_usa_mls", name="MLS")
    odds_data = {
        "aggregated": {
            "home_probability": 0.3106,
            "away_probability": 0.4307,
            "home_spread": 0.5,
            "over_under": 2.9,
            "projected_home_score": 1.2,
            "projected_away_score": 1.7,
            "bookmaker_count": 11,
        },
        "captured_at": _utc_offset(-0.1),
        "snapshots": [],
    }
    list_payload = events_route._format_event_with_aggregated_odds(ev_list, odds_data)
    lco = list_payload["current_odds"]
    assert lco["home_probability"] == pytest.approx(co["home_probability"], abs=1e-3)
    assert lco["away_probability"] == pytest.approx(co["away_probability"], abs=1e-3)
    assert lco["draw_probability"] == pytest.approx(co["draw_probability"], abs=1e-3)
    assert (
        lco["home_rendered_percent"]
        + lco["draw_rendered_percent"]
        + lco["away_rendered_percent"]
        == 100
    )
    assert list_payload["hero_probability"] == lco["home_probability"]
    assert list_payload["hero_probability_away"] == lco["away_probability"]
    assert list_payload["hero_probability_draw"] == lco["draw_probability"]


@pytest.mark.asyncio
async def test_one_leg_soccer_match_serves_nothing_for_chance_on_detail_and_list():
    """Step 3: Polymarket-only soccer match with zero books -> no orphan percent."""
    ev_detail = _detail_event(
        sport_key="soccer_other",
        home_prob=0.31,
        event_id=15347782,
        status="scheduled",
        home_score=None,
        away_score=None,
        opening_home=None,
        opening_away=None,
    )
    ev_detail.commence_time = _utc_offset(48)
    detail_payload = await _detail_payload(ev_detail, snapshots=[])

    co = detail_payload["current_odds"]
    assert co["home_probability"] is None
    assert co["away_probability"] is None
    assert co["draw_probability"] is None
    assert detail_payload["hero_probability"] is None
    assert detail_payload["hero_probability_away"] is None
    assert detail_payload["hero_probability_draw"] is None
    assert detail_payload["source_mark"]["state"] == "none"

    ev_list = Event(
        id=15347782,
        sport_id=1,
        home_team_name="Garuda Yaksa",
        away_team_name="Madura United",
        commence_time=_utc_offset(48),
        status="scheduled",
        win_probability_sources={"polymarket": {"value": 0.31, "type": "market"}},
    )
    ev_list.sport = Sport(id=1, key="soccer_other", name="Other Soccer")
    list_payload = events_route._format_event_with_aggregated_odds(ev_list, None)
    assert list_payload["hero_probability"] is None
    assert list_payload["hero_probability_away"] is None
    assert list_payload["hero_probability_draw"] is None
    assert list_payload["source_mark"]["state"] == "none"


# ---------------------------------------------------------------------------
# Feed serializer (format_event_data)
# ---------------------------------------------------------------------------


def test_feed_format_event_data_serves_three_way_and_suppresses_one_leg():
    now = datetime.now(timezone.utc)
    hero = HeroReading(home_probability=0.31, away_probability=0.69, source="blend")

    card_3 = format_event_data(
        event_id=15345867,
        external_id="mls-15345867",
        sport_key="soccer_usa_mls",
        sport_name="MLS",
        home_team="New England Revolution",
        away_team="Philadelphia Union",
        commence_time=now + timedelta(days=2),
        status="scheduled",
        home_score=None,
        away_score=None,
        current_home_prob=0.31,
        current_away_prob=0.431,
        current_draw_prob=0.259,
        opening_home_prob=0.3106,
        opening_away_prob=0.4307,
        opening_favorite="away",
        win_probability_sources={"betting": {"value": 0.31}},
        prob_source=None,
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        hero=hero,
    )
    co3 = card_3["current_odds"]
    assert co3["home_probability"] == pytest.approx(0.31)
    assert co3["away_probability"] == pytest.approx(0.431)
    assert co3["draw_probability"] == pytest.approx(0.259)
    assert (
        co3["home_rendered_percent"]
        + co3["draw_rendered_percent"]
        + co3["away_rendered_percent"]
        == 100
    )
    assert card_3["hero_probability"] == pytest.approx(0.31)
    assert card_3["hero_probability_away"] == pytest.approx(0.431)
    assert card_3["hero_probability_draw"] == pytest.approx(0.259)

    # One-leg draw-priced card (current_draw_prob=None) -> nothing for chance
    card_1 = format_event_data(
        event_id=15347782,
        external_id="other-15347782",
        sport_key="soccer_other",
        sport_name="Other Soccer",
        home_team="Garuda Yaksa",
        away_team="Madura United",
        commence_time=now + timedelta(days=2),
        status="scheduled",
        home_score=None,
        away_score=None,
        current_home_prob=None,
        current_away_prob=None,
        current_draw_prob=None,
        opening_home_prob=None,
        opening_away_prob=None,
        opening_favorite=None,
        win_probability_sources={"polymarket": {"value": 0.31}},
        prob_source="aggregate",
        game_clock=None,
        period=None,
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=None,
        hero=hero,
    )
    co1 = card_1["current_odds"]
    assert co1["home_probability"] is None
    assert co1["away_probability"] is None
    assert co1["draw_probability"] is None
    assert card_1["hero_probability"] is None
    assert card_1["hero_probability_away"] is None
    assert card_1["hero_probability_draw"] is None

    # Settled soccer card keeps settled 1.0/0.0 result untouched
    settled = HeroReading(
        home_probability=1.0, away_probability=0.0, source="settled", settled_result="home"
    )
    card_settled = format_event_data(
        event_id=15345868,
        external_id="mls-15345868",
        sport_key="soccer_usa_mls",
        sport_name="MLS",
        home_team="New England Revolution",
        away_team="Philadelphia Union",
        commence_time=now - timedelta(hours=3),
        status="completed",
        home_score=2,
        away_score=1,
        current_home_prob=1.0,
        current_away_prob=0.0,
        current_draw_prob=None,
        opening_home_prob=0.3106,
        opening_away_prob=0.4307,
        opening_favorite="away",
        win_probability_sources={"betting": {"value": 1.0}},
        prob_source=None,
        game_clock=None,
        period="FT",
        broadcast_info=None,
        highlight_label=None,
        raw_ei=None,
        inline_tags=[],
        ended_at=now - timedelta(hours=1),
        hero=settled,
    )
    assert card_settled["hero_probability"] == 1.0
    assert card_settled["hero_probability_away"] == 0.0
    assert card_settled["hero_settled_result"] == "home"
