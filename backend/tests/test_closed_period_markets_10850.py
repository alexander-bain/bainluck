"""#10850 — a finished 1st half's ungraded rows are served under
``closed_period_markets``: no price, ``window_closed``, the half's line-score
result. ``period_markets`` keeps the #1588 suppression unchanged.

UNIT — ``closed_period_markets`` / ``first_half_score`` over hand-built rows.
ROUTE — the real ``_build_game_markets`` + ``_publish_game_markets`` at
Halftime (closed) and in the 2nd quarter (control: nothing closed).

The specimen is Bowling Green–Sacramento State (15324326) at Halftime on
2026-10-10: line score home ``[0, 17]`` / away ``[3, 0]``, scoreboard 17–3.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_route
from app.routes.events import _game_markets_cache
from app.utils.closed_period_markets import closed_period_markets, first_half_score

BOX = {"home_period_scores": [0, 17], "away_period_scores": [3, 0]}
PRICE_FIELDS = ("over_probability", "opening_over_probability", "movement")


def _row(outcome, *, market_type="half_spread", period="1H", **extra):
    row = {
        "market_name": "1H Spread: Bowling Green (-3.5)",
        "outcome_name": outcome,
        "threshold": None,
        "source": "polymarket",
        "market_type": market_type,
        "period": period,
        "contributor_outcome_ids": [7],
        "probability": 0.62,
        "_market_id": 9,
    }
    row.update(extra)
    return row


def _serve(rows, *, league="NCAAF", box=BOX, home=17, away=3):
    return closed_period_markets(
        rows, league=league, box_score_data=box, home_score=home, away_score=away
    )


class TestTheServedRow:
    def test_a_closed_first_half_row_carries_the_half_score_and_no_price(self):
        [row] = _serve([_row("Bowling Green")])
        assert row["probability"] is None
        assert row["window_closed"] is True
        assert row["period_score"] == {"home": 17, "away": 3}
        assert row["market_type"] == "half_spread" and row["period"] == "1H"
        assert row["outcome_name"] == "Bowling Green"
        assert row["contributor_outcome_ids"] == [7]

    def test_a_half_total_row_loses_every_price_field(self):
        total = _row(
            "Over", market_type="half_total", threshold=20.5,
            over_probability=0.9, opening_over_probability=0.5, movement=0.4,
        )
        total.pop("probability")
        [row] = _serve([total])
        assert row["probability"] is None
        for field in PRICE_FIELDS:
            assert field not in row
        assert row["threshold"] == 20.5

    def test_v1_scope_is_the_first_half_only(self):
        rows = [
            _row("Bowling Green"),
            _row("Bowling Green", period="2H"),
            _row("Bowling Green", market_type="quarter_spread", period="1Q"),
        ]
        assert [r["period"] for r in _serve(rows)] == ["1H"]


class TestEvidence:
    def test_the_line_score_is_evidence_when_it_matches_the_scoreboard(self):
        assert first_half_score("NCAAF", BOX, 17, 3) == {"home": 17, "away": 3}
        # Q3 under way: three entries, the first two are the half.
        q3 = {"home_period_scores": [7, 0, 0], "away_period_scores": [0, 3, 0]}
        assert first_half_score("NCAAF", q3, 7, 3) == {"home": 7, "away": 3}

    def test_a_line_score_behind_the_scoreboard_is_refused(self):
        # A Q3 touchdown the line score has not caught up with.
        assert first_half_score("NCAAF", BOX, 24, 3) is None
        assert _serve([_row("Bowling Green")], home=24) == []

    @pytest.mark.parametrize("box", [
        None,
        {},
        {"home_period_scores": [17], "away_period_scores": [3]},
        {"home_period_scores": [0, 17], "away_period_scores": [3]},
        {"home_period_scores": [0, "17"], "away_period_scores": [3, 0]},
        {"home_period_scores": [0, True], "away_period_scores": [3, 0]},
        {"home_period_scores": [0, 16.5], "away_period_scores": [3, 0]},
    ])
    def test_no_evidence_no_row(self, box):
        assert _serve([_row("Bowling Green")], box=box, home=17 if box else 17) == []

    def test_a_missing_scoreboard_is_refused(self):
        assert _serve([_row("Bowling Green")], home=None) == []

    @pytest.mark.parametrize("league", ["NCAAB", "EPL", "MLB", None, ""])
    def test_leagues_not_indexed_in_quarters_are_refused(self, league):
        assert _serve([_row("Bowling Green")], league=league) == []

    @pytest.mark.parametrize("league", ["NFL", "NCAAF", "NBA", "WNBA", " ncaaf "])
    def test_quarter_indexed_leagues_are_served(self, league):
        assert len(_serve([_row("Bowling Green")], league=league)) == 1


# ── the route ─────────────────────────────────────────────────────────────

NOW = datetime(2026, 10, 10, 17, 40, tzinfo=timezone.utc)


@pytest.fixture
def _clean_game_cache():
    _game_markets_cache.clear()
    yield
    _game_markets_cache.clear()


def _result(scalar=None, rows=None, all_rows=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = rows or []
    result.all.return_value = all_rows if all_rows is not None else []
    return result


def _market(*, id, name):
    market = MagicMock()
    market.id, market.name, market.external_id = id, name, None
    market.event_id, market.category, market.status = 42, "game_prop", "open"
    market.source, market.sport_id = "polymarket", 1
    market.llm_sport_category = "american_football"
    market.commence_time = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)
    market.group_id = market.group_type = None
    market.market_metadata = None
    market.mutually_exclusive = None
    market.market_tier = 5
    return market


def _outcome(*, id, market_id, name, prob):
    outcome = MagicMock()
    outcome.id, outcome.market_id, outcome.name = id, market_id, name
    outcome.current_probability = prob
    outcome.opening_probability = 0.5
    outcome.is_winner = outcome.resolution_source = None
    outcome.last_updated = NOW
    return outcome


def _event(period):
    event = MagicMock()
    event.id, event.status, event.sport_id = 42, "live", 1
    event.sport = MagicMock()
    event.sport.key = "americanfootball_ncaaf"
    event.llm_league = "NCAAF"
    event.home_team_name, event.away_team_name = "Bowling Green Falcons", "Sacramento State Hornets"
    event.home_score, event.away_score = 17, 3
    event.commence_time = datetime(2026, 10, 10, 16, 0, tzinfo=timezone.utc)
    event.completed_at = None
    event.box_score_data = dict(BOX)
    event.period, event.game_clock = period, "0:00"
    event.score_observed_at = event.score_source = None
    return event


def _page():
    markets = [
        _market(id=201, name="1H Spread: Bowling Green (-3.5)"),
        _market(id=202, name="2H Spread: Bowling Green (-3.5)"),
    ]
    outcomes = [
        _outcome(id=11, market_id=201, name="Bowling Green", prob=0.90),
        _outcome(id=12, market_id=201, name="Sacramento State", prob=0.10),
        _outcome(id=13, market_id=202, name="Bowling Green", prob=0.505),
        _outcome(id=14, market_id=202, name="Sacramento State", prob=0.495),
    ]
    return markets, outcomes


def _db(period):
    markets, outcomes = _page()
    rows = [SimpleNamespace(id=o.id, observed_at=NOW - timedelta(minutes=1),
                            price_changed_at=None, resolution_source=None, current_probability=None)
            for o in outcomes]
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _result(scalar=_event(period)),
        _result(),
        _result(rows=[]),
        _result(rows=markets),
        _result(all_rows=[]),
        _result(rows=[]),
        _result(rows=outcomes),
        _result(all_rows=rows),
    ])
    return db


def _build(period):
    response, _status, ids = asyncio.run(events_route._build_game_markets(42, _db(period)))
    return response, ids


def _periods(rows):
    return sorted({(r["market_type"], r["period"]) for r in rows})


@pytest.mark.usefixtures("_clean_game_cache")
class TestTheRoute:
    def test_at_halftime_the_first_half_moves_to_the_closed_list_without_a_price(self):
        response, _ = _build("Halftime")
        # #1588 is unchanged: the 1H rows are not in period_markets.
        assert _periods(response["period_markets"]) == [("half_spread", "2H")]
        closed = response["closed_period_markets"]
        assert _periods(closed) == [("half_spread", "1H")]
        assert {r["outcome_name"] for r in closed} == {"Bowling Green", "Sacramento State"}
        for row in closed:
            assert row["probability"] is None
            assert row["window_closed"] is True
            assert row["period_score"] == {"home": 17, "away": 3}

    def test_control_in_the_second_quarter_nothing_is_closed(self):
        response, _ = _build("4:10 - 2nd Quarter")
        assert response["closed_period_markets"] == []
        assert ("half_spread", "1H") in _periods(response["period_markets"])
        priced = [r for r in response["period_markets"] if r["period"] == "1H"]
        assert all(r["probability"] is not None for r in priced)

    def test_the_key_reaches_the_served_json_through_the_publisher(self, monkeypatch):
        from app.utils import game_markets_cache as gmc

        monkeypatch.setattr(gmc, "compute_watermark", AsyncMock(return_value=None))
        monkeypatch.setattr(gmc, "write", lambda *a, **k: None)
        response, ids = _build("Halftime")
        served = asyncio.run(events_route._publish_game_markets(42, "live", response, ids, None))
        closed = json.loads(json.dumps(served, default=str))["closed_period_markets"]
        assert _periods(closed) == [("half_spread", "1H")]
        assert all(r["probability"] is None for r in closed)

    def test_a_builder_failure_never_fails_the_page(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("synthetic")

        monkeypatch.setattr(events_route, "closed_period_markets", boom)
        response, _ = _build("Halftime")
        assert response["closed_period_markets"] == []
        assert _periods(response["period_markets"]) == [("half_spread", "2H")]
