"""#7851 — a college football page does not offer a Canadian championship.

WHAT A READER SAW. Alex reports that during Stanford–Duke on Saturday morning,
2026-09-19, his son's friend saw Duke in contention for the Canadian Football
League championship. Reproduced on production 2026-09-21 19:58Z against the
named fixture, `GET /api/events/15311565/related-futures` (Duke Blue Devils vs
Stanford Cardinal, `americanfootball_ncaaf`, completed): the SECOND row of
`home_team_futures` was

    "2026 CFL Grey Cup Champion" || "Winnipeg Blue Bombers" || 0.125

market 33283475, and Duke's own ACC and NCAAF paths sat below it.

WHY. `_team_name_patterns("Duke Blue Devils")` emits the bare token `Blue`
(`len(parts) >= 3` adds every word of the city half that is >= 4 characters),
and `Blue` occupies WHOLE TOKENS of `Winnipeg Blue Bombers`. So #6806's boundary
rule — the seam that refuses `Lech` inside `Anderlecht` — cannot refuse this
one: the token really is there. The market reaches the candidate net because
`llm_sport_category = 'football'` is one arm of the route's sport filter and the
Grey Cup carries neither a US-league ticker (`KXGREYCUP-26`) nor a `sport_id`.

Measured the same day, the class is not the specimen: on the FCS page
`15313355` (Columbia Lions vs Lafayette Leopards) the same market served
`British Columbia Lions` to Columbia Lions.

THE REFUSAL IS ON THE LEAGUE, NOT THE TOKEN, because nothing in the token rule
can know Winnipeg is not Duke. `is_wrong_sport_leak` already refuses AHL into
NHL and College Baseball into MLB by exactly this shape.

═══ WHY THIS FILE EXISTS BESIDE THE UNIT GUARDS ═══

`tests/test_market_label_normalization.py` proves the predicate answers True.
It cannot prove the ROUTE consults it for this row: the outcome has to survive
the sport net, the ticker check and the game-specific filter first, and it is
`_build_related_futures` that decides whether a refused market still reaches a
card. This file exercises that path.

═══ SYNTHETIC ROWS, LABELLED ═══

Every `events` / `futures_markets` / `futures_outcomes` row is SYNTHETIC
(MagicMock, the harness `test_route_related_futures.py` uses and #6806 reuses).
Market id 33283475, its name, the outcome names and the probabilities 0.125 /
0.24 / 0.01 are QUOTED from production reads on 2026-09-21 (the served payload
for 15311565 and the `futures_outcomes` rows of market 33283475). Outcome ids
are invented; every outcome carries `team_id=None`, which is what production
holds for this market, so the name fallback is the path under test.

═══ WHAT IS NOT CLAIMED ═══

The token collision itself is untouched: `Blue` still reaches
`Winnipeg Blue Bombers` in the candidate net, and the same reach still assigns
`Arizona State Sun Devils` and `Delaware Blue Hens` to Duke on the NCAAF
championship market — measured on the same payload, filed separately, and NOT
fixed here. No pricing, ranking, dedup or settlement behaviour moves.
"""

import itertools
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw

from tests.integration.test_route_related_futures import (
    _make_event,
    _make_market,
    _make_outcome,
    _MockResult,
)

# A fresh event id per route call: the route memoises bodies per event id
# (`_related_futures_cache`), so a reused id would hand one test another
# test's body.
_EVENT_IDS = itertools.count(7851001)


def _fresh_event_id() -> int:
    return next(_EVENT_IDS)


def _football_event(id: int, home: str, away: str, *, sport_key: str):
    ev = _make_event(
        id=id,
        home_team=home,
        away_team=away,
        status="scheduled",
        sport_key=sport_key,
    )
    ev.sport.name = "American Football"
    ev.sport_id = 11
    return ev


def _outcome(id, market, name, probability, *, team_id=None):
    o = _make_outcome(
        id=id,
        market=market,
        name=name,
        probability=probability,
        probability_change_24h=0.0,
    )
    o.team_id = team_id
    return o


def _session(event, outcomes):
    """Mock DB session: the route's own queries, answered by statement text.

    `outcomes` is the CANDIDATE set — what the route's step-5 ILIKE net returns.
    No `teams` row for either side, so the name fallback is the path under test.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    market_ids = sorted({o.market.id for o in outcomes})

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from events" in stmt_str:
            return _MockResult(scalar=event)
        if "select sports.id" in stmt_str:
            return _MockResult(rows=[SimpleNamespace(id=11)])
        if "from teams" in stmt_str:
            return _MockResult(rows=[], first=None)
        if "from futures_outcomes" in stmt_str:
            return _MockResult(scalar_rows=list(outcomes))
        if "from futures_odds_snapshots" in stmt_str:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in stmt_str:
            return _MockResult(scalar=None)
        if "select futures_markets.id" in stmt_str:
            if "order by futures_markets.market_tier" in stmt_str:
                return _MockResult(
                    rows=[SimpleNamespace(id=m, market_tier=1) for m in market_ids]
                )
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


async def _get(monkeypatch, session, event_id):
    monkeypatch.setenv("BYPASS_RATE_LIMITS", "1")
    from app.main import app

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch(
                "app.services.league_context.enrich_event_with_context",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get(f"/api/events/{event_id}/related-futures")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return resp.json()


GREY_CUP_ID = 33283475
NCAAF_TITLE_ID = 6601311


def _grey_cup_market():
    return _make_market(id=GREY_CUP_ID, name="2026 CFL Grey Cup Champion", source="kalshi")


def _duke_candidates():
    """What production's ILIKE net returns for Duke Blue Devils vs Stanford.

    `Blue` reaches the Bombers; `Devils` reaches Duke's own NCAAF row. Both
    probabilities are the served ones.
    """
    grey_cup = _grey_cup_market()
    ncaaf = _make_market(id=NCAAF_TITLE_ID, name="NCAAF Championship Winner", source="kalshi")
    return [
        _outcome(78510001, grey_cup, "Winnipeg Blue Bombers", 0.125),
        _outcome(78510002, ncaaf, "Duke Blue Devils", 0.000981),
    ]


def _served(body):
    return body["home_team_futures"] + body["away_team_futures"]


class TestDukeIsNotInTheGreyCup:
    async def test_the_grey_cup_row_is_gone(self, monkeypatch):
        """RED ON BASE: `home_team_futures[1]` was the Grey Cup at 0.125."""
        eid = _fresh_event_id()
        event = _football_event(
            eid, "Duke Blue Devils", "Stanford Cardinal",
            sport_key="americanfootball_ncaaf",
        )
        body = await _get(monkeypatch, _session(event, _duke_candidates()), eid)
        assert all(r["market_id"] != GREY_CUP_ID for r in _served(body)), (
            "the CFL Grey Cup reached a college football card"
        )

    async def test_dukes_own_championship_row_survives(self, monkeypatch):
        """The other half of the ship: refusing the CFL must not cost Duke the
        NCAAF path the reader came for."""
        eid = _fresh_event_id()
        event = _football_event(
            eid, "Duke Blue Devils", "Stanford Cardinal",
            sport_key="americanfootball_ncaaf",
        )
        body = await _get(monkeypatch, _session(event, _duke_candidates()), eid)
        kept = [r for r in body["home_team_futures"] if r["market_id"] == NCAAF_TITLE_ID]
        assert len(kept) == 1, body["home_team_futures"]
        assert kept[0]["outcome_name"] == "Duke Blue Devils"
        assert kept[0]["probability"] == 0.000981

    async def test_columbia_lions_do_not_get_the_bc_lions(self, monkeypatch):
        """The second production specimen, event 15313355: `Lions` reaches
        `British Columbia Lions` on the same market."""
        eid = _fresh_event_id()
        event = _football_event(
            eid, "Columbia Lions", "Lafayette Leopards",
            sport_key="americanfootball_ncaaf_fcs",
        )
        grey_cup = _grey_cup_market()
        rows = [_outcome(78510003, grey_cup, "British Columbia Lions", 0.17)]
        body = await _get(monkeypatch, _session(event, rows), eid)
        assert _served(body) == []


class TestARealCflPageKeepsItsGreyCup:
    """The acceptance's control, and the half that can actually regress.

    Production 2026-09-21 20:00Z, `GET /api/events/15312374/related-futures`
    (Hamilton Tiger-Cats vs Montreal Alouettes, `americanfootball_cfl`) serves
    the Grey Cup to BOTH sides — Hamilton 0.01, Montreal 0.24. A league refusal
    that is not scoped takes this page's only championship path away.
    """

    async def test_both_cfl_sides_keep_the_grey_cup(self, monkeypatch):
        eid = _fresh_event_id()
        event = _football_event(
            eid, "Hamilton Tiger-Cats", "Montreal Alouettes",
            sport_key="americanfootball_cfl",
        )
        grey_cup = _grey_cup_market()
        rows = [
            _outcome(78510004, grey_cup, "Hamilton Tiger-Cats", 0.01),
            _outcome(78510005, grey_cup, "Montreal Alouettes", 0.24),
        ]
        body = await _get(monkeypatch, _session(event, rows), eid)

        (home,) = body["home_team_futures"]
        assert home["market_id"] == GREY_CUP_ID
        assert home["outcome_name"] == "Hamilton Tiger-Cats"
        assert home["probability"] == 0.01

        (away,) = body["away_team_futures"]
        assert away["market_id"] == GREY_CUP_ID
        assert away["outcome_name"] == "Montreal Alouettes"
        assert away["probability"] == 0.24
