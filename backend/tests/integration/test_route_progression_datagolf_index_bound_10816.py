"""#10816: the DataGolf sibling scan in `/api/futures/{id}/progression` names its source.

`external_id ILIKE 'datagolf:<tour>:<event>:%'` alone is not index-servable, so
production planned it as `ix_futures_markets_status` over every open futures row:
64,581 rows discarded, 1,104 ms (EXPLAIN ANALYZE 2026-10-10, market 64266838,
the golf page's own read), and 8-10 s under load in the slow-request ring. With
`source = 'datagolf'` the same statement read the 395 DataGolf rows in 3.4 ms and
returned the same 4 sibling ids. These guards pin that conjunct on the statement
the route actually executes, and that the ILIKE is still there beside it.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

pytestmark = pytest.mark.anyio


def _result_unique_all(values):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = values
    return result


def _result_scalar_one_or_none(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _market(market_id, name, external_id, outcomes):
    return SimpleNamespace(
        id=market_id,
        name=name,
        external_id=external_id,
        source="datagolf",
        market_tier=None,
        status="open",
        llm_sport_category="golf",
        canonical_market_key=None,
        resolution_date=datetime(2026, 10, 11, tzinfo=timezone.utc),
        event_id=None,
        outcomes=outcomes,
    )


def _outcome(oid, name, probability):
    return SimpleNamespace(
        id=oid,
        name=name,
        team_id=None,
        current_probability=probability,
        probability_change_24h=None,
    )


def _wire(mock_db):
    win = _market(
        64266838,
        "Open de Espana presented by Madrid - Winner",
        "datagolf:euro:2026139:win",
        [_outcome(1, "Jon Rahm", 0.21), _outcome(2, "Ludvig Aberg", 0.09)],
    )
    top5 = _market(
        64266839,
        "Open de Espana presented by Madrid - Top 5 Finish",
        "datagolf:euro:2026139:top_5",
        [_outcome(3, "Jon Rahm", 0.52), _outcome(4, "Ludvig Aberg", 0.31)],
    )
    # load market -> DataGolf prefix scan -> cross-source scan (no other source)
    mock_db.execute.side_effect = [
        _result_scalar_one_or_none(win),
        _result_unique_all([top5]),
        _result_unique_all([]),
    ]


def _datagolf_scan(mock_db):
    compiled = mock_db.execute.await_args_list[1].args[0].compile(
        dialect=postgresql.dialect()
    )
    return str(compiled), compiled.params


async def test_datagolf_sibling_scan_is_bounded_by_source(client, mock_db):
    _wire(mock_db)

    resp = await client.get("/api/futures/64266838/progression?top_n=40")
    assert resp.status_code == 200, resp.text

    sql, params = _datagolf_scan(mock_db)
    assert "futures_markets.source =" in sql, sql
    assert "datagolf" in params.values(), (
        f"the DataGolf sibling scan lost `source = 'datagolf'`, so it is a scan of "
        f"every open futures row again: {params}"
    )


async def test_the_ilike_is_still_the_authority(client, mock_db):
    _wire(mock_db)

    resp = await client.get("/api/futures/64266838/progression?top_n=40")
    assert resp.status_code == 200, resp.text

    sql, params = _datagolf_scan(mock_db)
    assert "ILIKE" in sql.upper()
    assert "datagolf:euro:2026139:%" in params.values(), params
    # and the sibling it found still becomes a stage
    stage_keys = [s["key"] for s in resp.json()["stages"]]
    assert {"top_5", "win"} <= set(stage_keys), stage_keys
