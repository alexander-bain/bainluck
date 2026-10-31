"""Review reproducer (#11842 R2): a red winner-coverage verdict must not turn the
cockpit tile GREEN on a run that deferred the coverage census."""
import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest

from app.utils import busy_db_defer


class _Result:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v

    def fetchall(self):
        return []

    def fetchone(self):
        return None


async def _run(monkeypatch, redis, below):
    from app.tasks import data_quality_watchdog as dq
    from app.tasks import redis_state, sentinel_filing

    by_query = {c["query"]: c["threshold"] for c in dq.CHECKS}

    class _Session:
        async def execute(self, stmt, *_a, **_k):
            sql = str(stmt)
            v = by_query.get(sql, 0)
            if sql in below:
                v = v - 10 if dq.CHECKS[[c["query"] for c in dq.CHECKS].index(sql)]["comparison"] == "gte" else v + 10
            return _Result(v)

        async def commit(self):
            return None

        async def rollback(self):
            return None

    @asynccontextmanager
    async def _session():
        yield _Session()

    monkeypatch.setattr(dq, "get_task_session", _session)
    monkeypatch.setattr(sentinel_filing, "fetch_open_alert_issues", lambda: [])
    monkeypatch.setattr(dq, "_check_redis_dedup", lambda *_a, **_k: True)
    monkeypatch.setattr(dq, "_has_open_canonical", lambda *_a, **_k: True)
    monkeypatch.setattr(dq, "_set_redis_dedup", lambda *_a, **_k: None)
    monkeypatch.setattr(dq, "reconcile_alert_issue", lambda *_a, **_k: {})
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *_a, **_k: redis)
    await dq._run_data_quality_watchdog()
    return dq


def _last(redis):
    calls = [c for c in redis.setex.call_args_list if c.args[0] == "bainluck:data_quality_watchdog:last"]
    return json.loads(calls[-1].args[2])


@pytest.mark.asyncio
async def test_a_red_coverage_verdict_survives_a_deferred_run(monkeypatch):
    from app.tasks import data_quality_watchdog as dq

    store = {}
    redis = MagicMock()
    redis.setex.side_effect = lambda k, ttl, v: store.__setitem__(k, v)
    redis.get.side_effect = lambda k: store.get(k)
    cov = {c["query"] for c in dq.CHECKS if c["name"] == "kalshi_winner_coverage"}

    # Run 1 (quiet hour / switch off): Kalshi coverage is below its P1 bar.
    monkeypatch.delenv(busy_db_defer.SWITCH_ENV, raising=False)
    await _run(monkeypatch, redis, below=cov)
    first = _last(redis)
    assert first["status"] == "red"

    # Run 2, two hours later inside the busy window: the census is deferred.
    monkeypatch.setenv(busy_db_defer.SWITCH_ENV, "1")
    monkeypatch.setattr(busy_db_defer, "in_busy_window", lambda now=None: True)
    await _run(monkeypatch, redis, below=set())
    second = _last(redis)
    assert second["status"] == "red", (
        "a deferred census re-measured nothing, yet the cockpit tile went "
        f"{second['status']!r} with failing={second['failing']}"
    )
