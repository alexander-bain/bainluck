"""Missing rule evidence cannot certify that a multi-winner board cannot push.

These are classifier/producer controls, not proof of any venue's winner cap.
"""

from contextlib import asynccontextmanager
from copy import deepcopy
import json
import importlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.market_shape import CLASSIFIER_VERSION, classify_market_semantics

producer = importlib.import_module("app.tasks.backfill_market_shapes")


def classify(**kw):
    return classify_market_semantics(
        outcome_names=["A", "B", "C", "D"],
        source_kind="top_3",
        mutually_exclusive=False,
        **kw,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"push_possible": None},
        {"push_possible": "false"},
        {"push_possible": "unknown"},
        {"push_possible": 0},
        {"push_possible": 1},
        {"push_possible": []},
    ],
)
def test_missing_or_untyped_rule_stays_unknown(kwargs):
    value = classify(**kwargs)
    assert value["push_void_capable"] is None
    assert value["expected_winners"] == 3
    assert value["outcome_relation"] == "independent_participation"
    assert value["exhaustive"] is False


@pytest.mark.parametrize("push", [False, True])
def test_explicit_boolean_rule_is_preserved(push):
    assert classify(push_possible=push)["push_void_capable"] is push


def test_absence_and_false_keep_distinct_input_fingerprints():
    assert (
        classify()["input_fingerprint"]
        == classify(push_possible=None)["input_fingerprint"]
    )
    assert (
        classify()["input_fingerprint"]
        != classify(push_possible=False)["input_fingerprint"]
    )


def test_threshold_capability_remains_conservative_without_claiming_a_no_push_rule():
    for names in [["Over", "Under"], ["Above", "Below"]]:
        assert (
            classify_market_semantics(outcome_names=names)["push_void_capable"] is True
        )
        assert (
            classify_market_semantics(outcome_names=names, push_possible=False)[
                "push_void_capable"
            ]
            is False
        )


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("stored_version", [2, 3])
async def test_real_producer_distinguishes_unknown_and_false_in_versioned_json(
    monkeypatch, dry_run, stored_version
):
    """Execute the real backfill with DB/Redis doubles; never access a service."""
    session = AsyncMock()
    redis = MagicMock()
    redis.get.return_value = b"0"
    writes = []
    original = []
    for number, push in [(1, None), (2, False), (3, True)]:
        metadata = {"source_market_kind": "top_3"}
        if push is not None:
            metadata["push_possible"] = push
        shape = classify(source="kalshi", push_possible=push)
        # Same raw input, but the old producer collapsed unknown into false.
        metadata["shape"] = {
            **shape,
            "classifier_version": stored_version,
            "v": stored_version,
            "push_void_capable": bool(push) if stored_version == 2 else push,
        }
        original.append(
            (
                number,
                "kalshi",
                f"KX-TEST-{number}",
                None,
                None,
                None,
                False,
                "participation",
                metadata,
                "Top 3",
            )
        )
    rows = deepcopy(original)

    async def execute(statement, params=None):
        sql = str(statement)
        result = MagicMock()
        if "SELECT id, source" in sql:
            assert "status IS DISTINCT FROM 'resolved'" in sql
            result.all.return_value = rows
        elif "SELECT market_id, name" in sql:
            result.all.return_value = [
                (i, n) for i in [1, 2, 3] for n in ["A", "B", "C", "D"]
            ]
        elif "UPDATE futures_markets" in sql:
            writes.append(deepcopy(params))
            assert "futures_outcomes" not in sql
        else:
            raise AssertionError(sql)
        return result

    @asynccontextmanager
    async def task_session():
        yield session

    session.execute.side_effect = execute
    monkeypatch.setattr(producer, "get_task_session", task_session)
    monkeypatch.setattr(producer, "get_redis_client", lambda: redis)
    result = await producer._backfill_market_shapes(
        limit=3, batch_size=3, dry_run=dry_run
    )
    assert rows == original
    assert result["scanned"] == 3
    if dry_run:
        assert result["updated"] == 0
        assert writes == []
        session.commit.assert_not_awaited()
        redis.setex.assert_not_called()
    elif stored_version == CLASSIFIER_VERSION:
        assert result["updated"] == 0
        assert writes == []  # a current stamp does not get rewritten every beat
    else:
        assert result["updated"] == 3
        encoded = [json.loads(w["meta"]) for w in writes]
        assert [s["push_void_capable"] for s in encoded] == [None, False, True]
        assert all(
            s["classifier_version"] == s["v"] == CLASSIFIER_VERSION for s in encoded
        )
        assert CLASSIFIER_VERSION > 2  # old false stamps must not claim this contract
        session.commit.assert_awaited_once()
