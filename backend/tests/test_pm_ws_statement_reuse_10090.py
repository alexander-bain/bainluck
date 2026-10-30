"""#10090: immutable writer shapes keep each execution's own inputs."""

from decimal import Decimal

import pytest
from sqlalchemy.dialects.postgresql.asyncpg import dialect

from app.tasks import polymarket_ws as task


def execution(chunk, force_ids=None, nowait=False):
    helper = getattr(task, "chunk_price_update_execution", None)
    assert callable(helper), "the PM writer still rebuilds its statement per chunk"
    return helper(chunk, force_ids=force_ids, nowait=nowait)


def rerank_execution(ids):
    helper = getattr(task, "pm_rerank_market_fields_execution", None)
    assert callable(helper), "the PM writer still rebuilds its rerank per chunk"
    return helper(ids)


@pytest.mark.parametrize("nowait", [False, True])
@pytest.mark.parametrize("count", [2, 100, 500])
def test_reused_shape_keeps_exact_current_arrays_and_lock_variant(nowait, count):
    chunk = {9_000_000 + i: (i + 1) / (count + 2) for i in range(count)}
    force_ids = set(list(chunk)[::2])
    statement, parameters = execution(chunk, force_ids, nowait)
    baseline = task.chunk_price_update_stmt(chunk, force_ids=force_ids, nowait=nowait)
    before = baseline.compile(dialect=dialect())
    after = statement.compile(dialect=dialect())
    assert str(before) == str(after)
    assert before.construct_params() == after.construct_params(parameters)
    assert parameters["chunk_ids"] == list(chunk)
    assert parameters["chunk_prices"] == list(chunk.values())
    assert parameters["chunk_compare"] == list(chunk.values())
    assert parameters["chunk_force"] == [oid in force_ids for oid in chunk]
    assert "ORDER BY given.ord" in str(after)
    assert ("NOWAIT" in str(after)) is nowait


def test_two_executions_share_only_shape_and_never_previous_quotes_or_arrays():
    first, p1 = execution({17: Decimal("0.0512345678"), 4: 0.9487654322}, {4})
    second, p2 = execution({4: 0.6, 17: 0.4}, set())
    assert first is second
    assert p1["chunk_ids"] == [17, 4]
    assert p1["chunk_prices"] == [Decimal("0.0512345678"), 0.9487654322]
    assert p1["chunk_force"] == [False, True]
    assert p2["chunk_ids"] == [4, 17]
    assert p2["chunk_prices"] == [0.6, 0.4]
    assert p2["chunk_force"] == [False, False]
    p2["chunk_ids"].append(99)
    assert p1["chunk_ids"] == [17, 4]
    for bind in first._generate_cache_key().bindparams:
        if bind.key.startswith("chunk_"):
            assert not bind.value, "cached template retains execution data"


def test_default_force_and_explicit_empty_force_keep_distinct_meanings():
    _, default = execution({7: 0.5, 8: 0.5})
    _, empty = execution({7: 0.5, 8: 0.5}, set())
    assert default["chunk_force"] == [True, True]
    assert empty["chunk_force"] == [False, False]


def test_lock_shapes_do_not_share_nowait_policy():
    blocking, _ = execution({1: 0.5}, nowait=False)
    probe, _ = execution({1: 0.5}, nowait=True)
    assert blocking is not probe
    assert "NOWAIT" not in str(blocking.compile(dialect=dialect()))
    assert "NOWAIT" in str(probe.compile(dialect=dialect()))


def test_rerank_reuses_shape_but_keeps_each_whole_market_population():
    first, p1 = rerank_execution([9, 4])
    second, p2 = rerank_execution([11])
    empty, p0 = rerank_execution([])
    assert first is second is empty
    assert p1 == {"market_ids": [9, 4]}
    assert p2 == {"market_ids": [11]}
    assert p0 == {"market_ids": []}
    compiled = first.compile(dialect=dialect())
    expanded = compiled.construct_expanded_state(p1)
    assert list(expanded.parameters.values()) == [9, 4]
    assert "PARTITION BY futures_outcomes.market_id" in expanded.statement
    assert "DESC NULLS LAST" in expanded.statement
    assert "IS DISTINCT FROM" in expanded.statement
    assert "last_updated" not in expanded.statement
