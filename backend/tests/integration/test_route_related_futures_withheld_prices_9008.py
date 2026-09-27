"""#9008 — the Bigger Picture refuses what each market's own page refuses.

`/events/15315689` printed the Art Ross as "Kucherov 50%" and five players at
10% while `/api/futures/60473133` served all six `null` (`prices_withheld: 35`).
`_build_related_futures` read `current_probability` off the row and asked no
refusal. The fix routes both of its printed-price sites (the home/away rail and
the series cards) through `_page_withheld_outcome_ids`, #8972's composition of
the detail route's calls. That composition is #8972's guard; this file proves
the WIRING over the real route and a mock session: which rows leave, which stay,
and that one board that raises fails open without un-refusing the others.

SYNTHETIC ROWS, LABELLED: a football fixture so the harness's sport net
applies unchanged (the #8848 file's shape); every id and price is invented.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.integration.test_route_related_futures import _make_market, _MockResult
from tests.integration.test_route_related_futures_cfl_7851 import (
    _football_event,
    _get,
    _outcome,
)

HALF, SERIES = 90080001, 90080002
DUKE_HALF, STAN_HALF = 90081001, 90081002
DUKE_SERIES, STAN_SERIES = 90082001, 90082002
_EVENT_IDS = iter(range(9008001, 9008100))


def _market(id, name, event_id):
    m = _make_market(id=id, name=name, source="polymarket")
    m.event_id = event_id
    m.group_id = None
    m.external_id = f"0x{id}"
    m.market_metadata = {}
    m.mutually_exclusive = False
    return m


def _fixture(event_id):
    half = _market(HALF, "1st Half Winner: Duke vs Stanford", event_id)
    series = _market(SERIES, "Duke vs Stanford Series Winner", None)
    candidates = [
        _outcome(DUKE_HALF, half, "Duke Blue Devils", 0.61),
        _outcome(STAN_HALF, half, "Stanford Cardinal", 0.39),
    ]
    series_outcomes = [
        _outcome(DUKE_SERIES, series, "Duke Blue Devils", 0.70),
        _outcome(STAN_SERIES, series, "Stanford Cardinal", 0.30),
    ]
    return half, series, candidates, series_outcomes


def _session(event, boards, candidates, series_outcomes):
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "from events" in s:
            return _MockResult(scalar=event)
        if "select sports.id" in s:
            return _MockResult(rows=[SimpleNamespace(id=11)])
        if "from teams" in s:
            return _MockResult(rows=[], first=None)
        if "order by futures_outcomes.market_id" in s:
            return _MockResult(scalar_rows=list(series_outcomes))
        if "from futures_outcomes" in s:
            return _MockResult(scalar_rows=list(candidates))
        if "from futures_odds_snapshots" in s:
            return _MockResult(rows=[])
        if "from line_movement_analyses" in s:
            return _MockResult(scalar=None)
        # #9008's board read: whole rows, so it names a column the id reads never do.
        if "futures_markets.mutually_exclusive" in s and "from futures_markets" in s:
            return _MockResult(scalar_rows=list(boards))
        if "select futures_markets.id" in s:
            if "order by futures_markets.market_tier" in s:
                return _MockResult(rows=[SimpleNamespace(id=HALF, market_tier=1)])
            if "limit" in s:  # the series detection read
                return _MockResult(rows=[SimpleNamespace(id=SERIES)])
            return _MockResult(rows=[])
        return _MockResult()

    session.execute = AsyncMock(side_effect=mock_execute)
    return session


def _patch_refusal(monkeypatch, withheld_by_board, raises=()):
    asked: list[int] = []

    async def fake(db, board):
        asked.append(board.id)
        if board.id in raises:
            raise RuntimeError("synthetic: this board cannot be evaluated")
        return set(withheld_by_board.get(board.id, ()))

    monkeypatch.setattr("app.routes.league_futures._page_withheld_outcome_ids", fake)
    return asked


async def _body(monkeypatch, withheld_by_board, raises=()):
    event_id = next(_EVENT_IDS)
    event = _football_event(
        event_id, "Duke Blue Devils", "Stanford Cardinal", sport_key="americanfootball_ncaaf"
    )
    half, series, candidates, series_outcomes = _fixture(event_id)
    asked = _patch_refusal(monkeypatch, withheld_by_board, raises)
    body = await _get(
        monkeypatch, _session(event, [half, series], candidates, series_outcomes), event_id
    )
    return body, asked


def _rail_ids(body):
    return {r["outcome_id"] for r in body["home_team_futures"] + body["away_team_futures"]}


def _series_prices(body):
    return {
        o["outcome_id"]: o["probability"]
        for m in body["series_markets"]
        for o in m["outcomes"]
    }


@pytest.mark.asyncio
async def test_control_nothing_refused_serves_both_rail_rows_and_both_series_prices(monkeypatch):
    """Without this, every assertion below could pass on a rail that is never built."""
    body, asked = await _body(monkeypatch, {})
    assert _rail_ids(body) == {DUKE_HALF, STAN_HALF}
    assert _series_prices(body) == {DUKE_SERIES: 0.70, STAN_SERIES: 0.30}
    assert HALF in asked and SERIES in asked


@pytest.mark.asyncio
async def test_a_refused_rail_leg_leaves_and_its_priced_sibling_stays(monkeypatch):
    body, _ = await _body(monkeypatch, {HALF: {DUKE_HALF}})
    assert _rail_ids(body) == {STAN_HALF}
    assert body["total_count"] == 1


@pytest.mark.asyncio
async def test_a_refused_series_leg_stays_named_with_its_price_keys_null(monkeypatch):
    body, _ = await _body(monkeypatch, {SERIES: {DUKE_SERIES}})
    legs = {o["outcome_id"]: o for m in body["series_markets"] for o in m["outcomes"]}
    assert legs[DUKE_SERIES]["name"] == "Duke Blue Devils"
    assert "probability" in legs[DUKE_SERIES] and legs[DUKE_SERIES]["probability"] is None
    assert legs[DUKE_SERIES]["probability_change_24h"] is None
    assert legs[STAN_SERIES]["probability"] == 0.30
    # The series board's refusal never reaches into the rail.
    assert _rail_ids(body) == {DUKE_HALF, STAN_HALF}


@pytest.mark.asyncio
async def test_a_board_that_raises_keeps_its_prices_and_the_other_board_is_still_refused(monkeypatch):
    body, _ = await _body(monkeypatch, {SERIES: {DUKE_SERIES}}, raises={HALF})
    assert _rail_ids(body) == {DUKE_HALF, STAN_HALF}
    assert _series_prices(body)[DUKE_SERIES] is None
