"""Route-harness bodies for the native #10238 decode tests (tooling only; nothing imports it).

Drives the merged producer (#10329) through the real route builders and
publishers — `_build_game_markets` → `_publish_game_markets` and
`_build_related_futures` → `_publish_related_futures` — with the producer
test's own mock sessions, and writes the served JSON the phone decodes.

    cd backend && python3 ../tools/gen-10238-route-harness.py "../ios/Bain Luck/BainLuckTests/Fixtures"

Writes `game-markets-10238-question-matrix.route-harness.json` and
`related-futures-10238-series-matrix.route-harness.json`. Captured on master
5509d7a579; a re-run is byte-identical except the publisher's wall-clock
`cache.created_at`. Re-run after a producer change; the native key-parity test fails
on any matrix key the decode neither reads nor names as ignored.
"""
import asyncio, json, sys
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
sys.path.insert(0, ".")
import tests.test_event_question_matrix_10238 as h
from app.utils import game_markets_cache as gmc, related_futures_cache as rfc

OUT = sys.argv[1]
mp = pytest.MonkeyPatch()
for mod in (gmc, rfc):
    mp.setattr(mod, "compute_watermark", AsyncMock(return_value=None))
    mp.setattr(mod, "write", lambda *a, **k: None)

M, O = h._route_market, h._route_outcome


def game_page():
    pin = {"pregame_mark": {"outcomes": {"3": 0.40}, "observed_at": "2026-05-17T22:00:00+00:00",
                            "captured_at": "2026-05-17T22:00:00+00:00"}}
    markets = [
        M(id=101, name="Celtics at Knicks: Total Points"),
        M(id=102, name="Celtics at Knicks: Spread", metadata=pin),
        M(id=104, name="Head-to-Head: Scheffler vs McIlroy"),
        M(id=106, name="Celtics at Warriors"),
        M(id=108, name="Celtics at Knicks: Result after 3 quarters"),
        M(id=109, name="Celtics at Knicks: Top scorer"),
        M(id=110, name="Celtics at Knicks: Spread 3"),
    ]
    markets[4].mutually_exclusive = True
    markets[5].mutually_exclusive = True
    outcomes = [
        O(id=2, market_id=101, name="Under 210.5", prob=0.48),
        O(id=3, market_id=102, name="Boston Celtics -3.5", prob=0.54),
        O(id=4, market_id=102, name="New York Knicks +3.5", prob=0.46),
        O(id=5, market_id=104, name="Scheffler", prob=0.55),
        O(id=6, market_id=104, name="McIlroy", prob=0.45),
        O(id=8, market_id=106, name="Yes", prob=0.70),
        O(id=13, market_id=108, name="Boston Celtics", prob=0.52),
        O(id=14, market_id=108, name="Tie", prob=0.0),
        O(id=19, market_id=108, name="New York Knicks", prob=0.47),
        O(id=15, market_id=109, name="Jayson Tatum", prob=0.55),
        O(id=16, market_id=109, name="Jalen Brunson", prob=0.25),
        O(id=17, market_id=109, name="Jaylen Brown", prob=0.22),
        O(id=18, market_id=110, name="Boston Celtics -3", prob=0.5),
    ]
    return markets, outcomes


def game():
    h._game_markets_cache.clear()
    markets, outcomes = game_page()
    response, _s, ids = asyncio.run(h.events_route._build_game_markets(42, h._route_db(markets, outcomes)))
    return asyncio.run(h.events_route._publish_game_markets(42, "live", response, ids, None))


def series():
    mp.setattr(h.events_route, "_related_futures_withheld_ids", AsyncMock(return_value={913}))
    def mk(id, name, ext):
        return SimpleNamespace(id=id, name=name, source="kalshi", status="open", resolution_date=None,
                               mutually_exclusive=True, market_metadata=None, probability_change_24h=None,
                               commence_time=None, external_id=ext)
    winner = mk(900, "Red Sox vs Yankees: Series Winner", "KXMLBSERIES-X")
    exact = mk(910, "Red Sox vs Yankees: Exact Series Result", "KXMLBSERIESEXACT-X")
    def leg(id, market, name, prob, is_winner=None, src=None):
        return SimpleNamespace(id=id, market_id=market.id, name=name, current_probability=prob,
                               probability_change_24h=None, is_winner=is_winner, resolution_source=src,
                               external_id=f"{market.external_id}-{id}", market=market)
    legs = [leg(901, winner, "Boston Red Sox", 0.70), leg(902, winner, "New York Yankees", 0.29),
            leg(911, exact, "Red Sox in 3", 0.0, is_winner=False, src="api_settlement"),
            leg(912, exact, "Red Sox in 4", 0.35), leg(913, exact, "Yankees in 4", 0.12),
            leg(914, exact, "Yankees in 3", None)]
    event = h._Row(
        id=55, sport=SimpleNamespace(id=7, key="baseball_mlb"), sport_id=7, status="completed",
        home_team_name="Boston Red Sox", away_team_name="New York Yankees",
        commence_time=h.datetime(2026, 10, 2, 23, 0, tzinfo=h.timezone.utc),
        home_team_id=None, away_team_id=None, period=None, game_clock=None,
        box_score_data=None, llm_league="MLB", home_score=5, away_score=3,
    )
    session = h._SeriesSession(event, [900, 910], legs)
    response, _s, ids, _c = asyncio.run(h.events_route._build_related_futures(55, session))
    return asyncio.run(h.events_route._publish_related_futures(55, "completed", response, ids, None))


FILES = {"game": "game-markets-10238-question-matrix.route-harness.json",
         "series": "related-futures-10238-series-matrix.route-harness.json"}
for name, body in (("game", game()), ("series", series())):
    with open(f"{OUT}/{FILES[name]}", "w") as f:
        json.dump(json.loads(json.dumps(body, default=str)), f, indent=2, sort_keys=True)
        f.write("\n")
