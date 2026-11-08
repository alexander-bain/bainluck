"""#4437 Decide 89-A: the rules that let a request read `open_futures_outcomes`.

The real-Postgres half (the maintainer's SQL and both routes answering the same
with and without the copy) is `tests/integration/test_open_futures_outcomes_pg_4437.py`.
These pin the gate: the copy is read only while its maintainer is current, only
for name predicates, and never without the direct arm for newer outcomes.
"""

import json
import time

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.models import FuturesMarket, FuturesOutcome
from app.utils import open_futures_outcomes as ofo


def _sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def _state(**kw):
    base = {"watermark": 900, "reader_floor": 800, "pass_at": time.time(), "cycle_complete": True}
    base.update(kw)
    return base


@pytest.fixture
def state(monkeypatch):
    """Serve ``holder["state"]`` as the maintainer's state; no Redis."""
    holder = {"state": None}
    monkeypatch.setattr(ofo, "_fetch_state", lambda: holder["state"])
    ofo._memo["at"] = None
    yield holder
    ofo._memo["at"] = None


@pytest.mark.parametrize(
    "value, servable",
    [
        (None, False),
        ({}, False),
        (_state(cycle_complete=False), False),
        (_state(pass_at=time.time() - ofo.STALE_AFTER_SECONDS - 1), False),
        (_state(reader_floor="800"), False),
        (_state(), True),
    ],
)
def test_only_a_current_complete_state_is_servable(value, servable):
    assert ofo.state_is_servable(value) is servable


def test_no_state_means_the_original_lookup(state):
    assert ofo.open_outcomes_floor() is None
    assert ofo.market_ids_with_outcome(FuturesOutcome.name.ilike("%chi%")) is None
    assert ofo.outcome_ids_named(FuturesOutcome.name.op("~*")("chi")) is None


def test_the_operator_switch_turns_reading_off(state, monkeypatch):
    state["state"] = _state()
    monkeypatch.setenv("OPEN_FUTURES_OUTCOMES_READ", "0")
    assert ofo.open_outcomes_floor() is None


def test_a_current_state_reads_the_copy_and_newer_outcomes_directly(state):
    state["state"] = _state()
    sql = _sql(ofo.market_ids_with_outcome(FuturesOutcome.name.ilike("%chi%")))
    assert "FROM open_futures_outcomes" in sql
    assert "open_futures_outcomes.name ILIKE '%%chi%%'" in sql
    # The direct arm: outcomes above the reader floor, on the real table.
    assert "futures_outcomes.id > 800" in sql
    assert "futures_outcomes.name ILIKE '%%chi%%'" in sql
    assert "UNION ALL" in sql


def test_a_predicate_on_more_than_the_name_keeps_the_original(state):
    state["state"] = _state()
    assert ofo.on_open_outcomes(FuturesOutcome.current_probability > 0.1) is None
    assert (
        ofo.market_ids_with_outcome(
            FuturesOutcome.name.ilike("%chi%"), FuturesOutcome.team_id.isnot(None)
        )
        is None
    )


def test_the_memo_asks_redis_at_most_once_per_window(monkeypatch):
    calls = []

    def _fetch():
        calls.append(1)
        return _state()

    monkeypatch.setattr(ofo, "_fetch_state", _fetch)
    ofo._memo["at"] = None
    for _ in range(5):
        ofo.open_outcomes_floor()
    assert calls == [1]
    ofo._memo["at"] = None


def test_an_unreadable_redis_is_no_state(monkeypatch):
    import app.tasks.redis_state as rs

    def _boom(**kw):
        raise RuntimeError("redis down")

    monkeypatch.setattr(rs, "get_redis_client", _boom)
    assert ofo._fetch_state() is None


# ── the route's four lookups go through one helper ──────────────────────────


def test_every_outcome_name_lookup_uses_the_one_helper():
    import inspect

    from app.routes import events

    assert "_outcome_market_ids(*outcome_where)" in inspect.getsource(events._market_has_outcome)
    assert "outcome_ids_named(named)" in inspect.getsource(events._headline_contender_outcome_clause)
    probe = inspect.getsource(events._resolve_typeahead_outcome_arm)
    assert "_outcome_market_ids(" in probe
    assert "select(FuturesOutcome.market_id)" not in probe
    route = inspect.getsource(events.typeahead_search)
    assert "_outcome_market_ids(_ta_outcome_cond)" in route


def test_the_search_arm_reads_the_copy_only_when_current(state):
    from app.routes.events import _market_has_outcome

    off = _sql(select(FuturesMarket.id).where(_market_has_outcome(FuturesOutcome.name.ilike("%mid%"))))
    assert "open_futures_outcomes" not in off
    state["state"] = _state()
    ofo._memo["at"] = None
    on = _sql(select(FuturesMarket.id).where(_market_has_outcome(FuturesOutcome.name.ilike("%mid%"))))
    assert "open_futures_outcomes" in on and "futures_outcomes.id > 800" in on


def test_the_headline_lane_narrows_by_the_copy_and_still_judges_real_rows(state):
    from app.routes.events import _headline_contender_outcome_clause

    off = _sql(select(FuturesMarket.id).where(_headline_contender_outcome_clause("\\mchi\\M")))
    assert "open_futures_outcomes" not in off
    state["state"] = _state()
    ofo._memo["at"] = None
    on = _sql(select(FuturesMarket.id).where(_headline_contender_outcome_clause("\\mchi\\M")))
    assert "open_futures_outcomes.outcome_id" in on
    # The price floor and team anchor are still read from futures_outcomes.
    assert "futures_outcomes.current_probability" in on and "teams.name" in on


# ── the maintainer ──────────────────────────────────────────────────────────


class _Redis:
    def __init__(self, held=False):
        self.data = {"bainluck:open_futures_outcomes:lock": "1"} if held else {}

    def get(self, k):
        return self.data.get(k)

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.data:
            return False
        self.data[k] = v
        return True

    def setex(self, k, ttl, v):
        self.data[k] = v

    def delete(self, k):
        self.data.pop(k, None)


@pytest.mark.asyncio
async def test_a_second_pass_never_runs_beside_the_first(monkeypatch):
    import app.tasks.redis_state as rs
    from app.tasks.open_futures_outcomes import _refresh_open_futures_outcomes

    r = _Redis(held=True)
    monkeypatch.setattr(rs, "get_redis_client", lambda **kw: r)
    out = await _refresh_open_futures_outcomes()
    assert out["terminal"] == "partial" and "lock" in out["skipped"]


@pytest.mark.asyncio
async def test_a_failed_pass_withdraws_the_state_so_readers_fall_back(monkeypatch):
    import app.services.database as database
    import app.tasks.redis_state as rs
    from app.tasks.open_futures_outcomes import _refresh_open_futures_outcomes

    r = _Redis()
    r.data[ofo.STATE_KEY] = json.dumps(_state())
    monkeypatch.setattr(rs, "get_redis_client", lambda **kw: r)

    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("database went away")

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(database, "async_session_maker", lambda: _Boom())
    with pytest.raises(RuntimeError):
        await _refresh_open_futures_outcomes()
    assert ofo.STATE_KEY not in r.data
    assert "bainluck:open_futures_outcomes:lock" not in r.data, "the lock outlived its pass"


def test_the_state_expires_on_its_own_if_the_maintainer_stops():
    import inspect

    from app.tasks import open_futures_outcomes as task

    src = inspect.getsource(task._refresh_open_futures_outcomes)
    assert "rc.setex(STATE_KEY, STALE_AFTER_SECONDS," in src
