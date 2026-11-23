"""A graded golf outright beats an ungraded copy on every reader route."""

import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import sqlite

from app.models import FuturesMarket
from app.routes import golf
from app.utils import golf_base, golf_tournament_cache, request_cache
from tests.integration.conftest import _make_mock_result
from tests.integration.test_route_feed_prewarm import _RecordingRedis, _install_redis
from tests.integration.test_route_futures import (
    _market,
    _outcome,
    _result_scalar_one_or_none,
    _result_unique_all,
    _sport,
)


def _rsm_market(market_id, end, *, resolved=False):
    marco = _outcome(
        market_id * 100 + 1, "Marco Penge", probability=1.0 if resolved else 0.0135
    )
    greyserman = _outcome(
        market_id * 100 + 2, "Max Greyserman", probability=0.0 if resolved else 0.4555
    )
    hoejgaard = _outcome(
        market_id * 100 + 3, "Rasmus Hojgaard", probability=0.0 if resolved else 0.203
    )
    if resolved:
        marco.is_winner = True
        greyserman.is_winner = False
        hoejgaard.is_winner = False
        marco.resolution_source = greyserman.resolution_source = "api_settlement"
        hoejgaard.resolution_source = "api_settlement"
    market = _market(
        market_id,
        outcomes=[marco, greyserman, hoejgaard],
        sport=_sport("golf_pga", "PGA Tour"),
    )
    market.name = (
        "The RSM Classic Winner" if resolved else "PGA Tour: The RSM Classic Winner"
    )
    market.source = "kalshi" if resolved else "polymarket"
    market.external_id = "KXPGATOUR-THRC26" if resolved else "1387947"
    market.llm_sport_category = "golf"
    market.status = "resolved" if resolved else "open"
    market.market_metadata = None
    market.commence_time = end - timedelta(days=6)
    market.resolution_date = end + timedelta(days=14) if resolved else end
    market.settled_at = end + timedelta(days=1) if resolved else None
    return market


def _schedule(end):
    return {
        "key": "the_rsm_classic",
        "name": "The RSM Classic",
        "tour": "pga",
        "status": "upcoming",  # The stale schedule from the production defect.
        "start_date": (end - timedelta(days=3)).isoformat(),
        "end_date": end.isoformat(),
    }


@pytest.fixture
def tournament_end() -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


@pytest.mark.usefixtures("opening_seating_off")
async def test_tournament_futures_and_discover_agree_after_one_venue_grades(
    client, mock_db, monkeypatch, tournament_end
):
    end = tournament_end
    open_copy = _rsm_market(70502669, end)
    settled_board = _rsm_market(70709343, end, resolved=True)
    markets = {m.id: m for m in (open_copy, settled_board)}
    schedule = _schedule(end)
    monkeypatch.setattr(golf, "_get_golf_schedule", AsyncMock(return_value=[schedule]))
    monkeypatch.setattr(golf, "_fetch_24h_snapshots", AsyncMock(return_value={}))
    monkeypatch.setattr(golf, "_attach_pregame", AsyncMock())
    monkeypatch.setattr(golf_tournament_cache, "get_or_build", _build_without_cache)
    request_cache._reset_last_good_for_tests()
    _install_redis(monkeypatch, _RecordingRedis())

    async def base(db, *args, **kwargs):
        payload = await golf.get_golf(db)
        return golf_base.normalize_tournaments(payload["tournaments"]), "inline"

    monkeypatch.setattr(golf_base, "get_golf_base", base)

    # Run the market-selection predicate against stored rows. Other queries
    # (snapshots, the rest of Discover) have no rows in this fixture.
    with sqlite3.connect(":memory:") as db:
        db.executescript(
            """
            CREATE TABLE futures_markets (
                id INTEGER, status TEXT, mutually_exclusive BOOLEAN,
                resolution_date TEXT, settled_at TEXT,
                external_id TEXT, llm_sport_category TEXT
            );
            CREATE TABLE futures_outcomes (market_id INTEGER, is_winner BOOLEAN);
            """
        )
        for row in markets.values():
            db.execute(
                "INSERT INTO futures_markets VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    row.id,
                    row.status,
                    row.mutually_exclusive,
                    row.resolution_date.isoformat(" ")[:19],
                    row.settled_at.isoformat(" ")[:19] if row.settled_at else None,
                    row.external_id,
                    row.llm_sport_category,
                ),
            )
            db.executemany(
                "INSERT INTO futures_outcomes VALUES (?, ?)",
                [(row.id, option.is_winner) for option in row.outcomes],
            )

        async def select_rows(statement, *args, **kwargs):
            where = getattr(statement, "whereclause", None)
            if where is not None:
                criteria = str(where)
                if (
                    "futures_markets.external_id" in criteria
                    and "futures_markets.llm_sport_category" in criteria
                ):
                    predicate = select(FuturesMarket.id).where(where)
                    sql = str(
                        predicate.compile(
                            dialect=sqlite.dialect(),
                            compile_kwargs={"literal_binds": True},
                        )
                    )
                    return _result_unique_all(
                        [markets[mid] for mid, in db.execute(sql)]
                    )
            return _make_mock_result()

        mock_db.execute.side_effect = select_rows
        tournament = await client.get("/api/golf/tournaments/the-rsm-classic")
        discover = await client.get(
            "/api/feed?limit=20&offset=0&event_pct=0.15&include_futures=false"
        )
        mock_db.execute.side_effect = [
            _result_scalar_one_or_none(settled_board),
            _make_mock_result(),
        ]
        futures = await client.get("/api/futures/70709343")

    assert tournament.status_code == discover.status_code == futures.status_code == 200
    result = tournament.json()
    assert result["tournament"]["schedule_status"] == "completed"
    assert result["tournament"]["champion"] == "Marco Penge"
    assert result["evolution_market_id"] == 70709343
    assert result["markets"][0]["market_ids"] == [70709343]
    market = futures.json()
    assert market["status"] == "resolved"
    winner = next(outcome for outcome in market["outcomes"] if outcome["is_winner"])
    card = next(
        item
        for item in discover.json()["items"]
        if item["type"] == "tournament" and item["data"]["slug"] == "the-rsm-classic"
    )
    assert card["headline"] == "Final"
    assert card["data"]["schedule_status"] == "completed"
    assert card["data"]["champion"] == winner["name"] == "Marco Penge"
    assert card["data"]["market_ids"] == [70709343]
    for golfers in (result["golfers"], card["data"]["golfers"]):
        assert golfers[0]["name"] == winner["name"]
        assert golfers[0]["source_mark"] == winner["source_mark"]
        assert [g["probability"] for g in golfers] == [1.0, 0.0, 0.0]


async def _build_without_cache(slug, *, builder, **kwargs):
    return await builder(), "miss"


def test_a_grade_for_another_edition_or_a_placement_cannot_close_the_tournament(
    tournament_end,
):
    end = tournament_end
    old = _rsm_market(3, end - timedelta(days=365), resolved=True)
    placement = _rsm_market(4, end, resolved=True)
    placement.name = "The RSM Classic: Top 5 Finish"
    assert (
        golf._build_graded_tournament(
            "the_rsm_classic", [old, placement], _schedule(end)
        )
        is None
    )
