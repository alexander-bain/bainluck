"""#10028: a price-refusal check that times out no longer 500s a search page.

Sentry BAINLUCK-1GV, 6 events: `GET /api/events/search?q=heisman` (2026-10-01
07:20:20Z, 2026-10-02 07:40:53Z), `q=ohtani` and `q=freddie freeman` returned
HTTP 500. The trace runs `search_events` → `_search_withheld_price_ids` →
`_withheld_price_outcome_ids` → `_unsupported_price_outcome_ids` →
`_newest_kalshi_trades`, whose `futures_odds_snapshots` read was cancelled by the
search statement timeout. Nothing caught the `QueryCanceledError`.

The rule pinned here:

* a TIMEOUT fails closed: every UNGRADED row's price is withheld (no number we
  could not vouch for), graded rows keep their result, the market id is reported
  on ``shed`` so the route marks the answer degraded and never caches it;
* the read runs in a SAVEPOINT, so the timeout rolls back that statement only and
  the route's ORM rows are not expired (gotcha #6);
* any OTHER exception still raises: only the classified timeout is absorbed;
* the success path is unchanged and releases its savepoint.
"""

from types import SimpleNamespace

import pytest

import app.routes.events as events_module
from app.routes.events import _search_withheld_price_ids


class QueryCanceledError(Exception):
    """Named like asyncpg's, which is what `_is_query_timeout` keys on."""


class _Savepoint:
    def __init__(self, log):
        self.log = log

    async def commit(self):
        self.log.append("commit")

    async def rollback(self):
        self.log.append("rollback")


class _DB:
    def __init__(self):
        self.log = []

    async def begin_nested(self):
        self.log.append("begin_nested")
        return _Savepoint(self.log)

    async def execute(self, _stmt):  # `_fleet_newest_observation`'s read
        return SimpleNamespace(scalar_one_or_none=lambda: None)


def _market():
    return SimpleNamespace(
        id=60099001,
        name="Heisman Trophy Winner 2026",
        source="kalshi",
        status="open",
        updated_at=None,
        outcomes=[
            SimpleNamespace(id=1, resolution_source=None, is_winner=False,
                            last_updated=None, current_probability=0.31),
            SimpleNamespace(id=2, resolution_source=None, is_winner=False,
                            last_updated=None, current_probability=0.22),
            SimpleNamespace(id=3, resolution_source="api_settlement",
                            is_winner=False, last_updated=None,
                            current_probability=0.0),
        ],
    )


def _arms_raise(monkeypatch, exc):
    async def _boom(_db, _market):
        raise exc

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _boom)


@pytest.mark.asyncio
async def test_a_timeout_withholds_the_ungraded_prices_instead_of_raising(monkeypatch):
    _arms_raise(monkeypatch, QueryCanceledError("canceling statement due to statement timeout"))
    db, shed = _DB(), []
    withheld = await _search_withheld_price_ids(db, _market(), shed)
    assert withheld == {1, 2}  # the graded row keeps its result
    assert shed == [60099001]
    assert db.log == ["begin_nested", "rollback"]


@pytest.mark.asyncio
async def test_a_wrapped_timeout_is_recognised_through_orig(monkeypatch):
    # SQLAlchemy's DBAPIError carries the driver error on `.orig`.
    wrapper = Exception("DBAPIError")
    wrapper.orig = QueryCanceledError("timeout")
    _arms_raise(monkeypatch, wrapper)
    shed = []
    assert await _search_withheld_price_ids(_DB(), _market(), shed) == {1, 2}
    assert shed == [60099001]


@pytest.mark.asyncio
async def test_a_timeout_without_a_shed_list_still_answers(monkeypatch):
    _arms_raise(monkeypatch, QueryCanceledError("timeout"))
    assert await _search_withheld_price_ids(_DB(), _market()) == {1, 2}


@pytest.mark.asyncio
async def test_any_other_error_still_raises_and_releases_the_savepoint(monkeypatch):
    _arms_raise(monkeypatch, RuntimeError("not a timeout"))
    db, shed = _DB(), []
    with pytest.raises(RuntimeError):
        await _search_withheld_price_ids(db, _market(), shed)
    assert shed == []
    assert db.log == ["begin_nested", "rollback"]


@pytest.mark.asyncio
async def test_the_success_path_is_unchanged_and_commits_its_savepoint(monkeypatch):
    async def _two(_db, _market):
        return {2}

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _two)
    db, shed = _DB(), []
    assert await _search_withheld_price_ids(db, _market(), shed) == {2}
    assert shed == []
    assert db.log == ["begin_nested", "commit"]


def test_the_route_marks_a_shed_refusal_degraded_so_it_is_never_cached():
    """Both route call sites pass the shed list, and a shed joins `degraded`."""
    import inspect

    src = inspect.getsource(events_module.search_events)
    assert src.count("_search_withheld_price_ids(") == 2
    assert src.count("_withheld_shed") >= 4
    assert 'degraded.append("price_refusal")' in src


@pytest.mark.asyncio
async def test_after_one_timeout_later_markets_fail_closed_without_a_query(monkeypatch):
    """One timeout per request: the next market does not run into the spent deadline."""
    calls = []

    async def _boom(_db, market):
        calls.append(market.id)
        raise QueryCanceledError("timeout")

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _boom)
    db, shed = _DB(), []
    first, second = _market(), _market()
    second.id = 60099002
    assert await _search_withheld_price_ids(db, first, shed) == {1, 2}
    assert await _search_withheld_price_ids(db, second, shed) == {1, 2}
    assert calls == [60099001]  # the second market never queried
    assert shed == [60099001, 60099002]
    assert db.log == ["begin_nested", "rollback"]  # no second savepoint


@pytest.mark.asyncio
async def test_an_empty_shed_list_still_runs_the_check(monkeypatch):
    async def _two(_db, _market):
        return {2}

    monkeypatch.setattr(events_module, "_withheld_price_outcome_ids", _two)
    assert await _search_withheld_price_ids(_DB(), _market(), []) == {2}
