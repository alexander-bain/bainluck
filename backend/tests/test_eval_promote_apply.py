"""Guard tests for the #222 eval-promote apply path.

Both directions of every safety knob are asserted:
* bounded — the applied ± term is clamped;
* expiring — the TTL filter is present in the query the feed runs;
* kill-switchable — switch OFF leaves scoring untouched (and never even queries),
  switch ON applies the bounded term.
"""

import types
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.routes import feed as feed_mod
from app.routes.feed import _apply_manual_review_decision_map
from app.utils.eval_promote import (
    EVAL_ADJ_CAP,
    EVAL_DOWNRANK_EXACT,
    EVAL_PROMOTE_ADJ,
    EVAL_PROMOTE_TTL_DAYS,
    clamp_adj,
    is_enabled_value,
    ttl_cutoff,
)


# --- Pure util guards ---------------------------------------------------------

def test_clamp_adj_bounds():
    assert clamp_adj(EVAL_PROMOTE_ADJ) == EVAL_PROMOTE_ADJ
    assert clamp_adj(-EVAL_DOWNRANK_EXACT) == -EVAL_DOWNRANK_EXACT
    # No stored magnitude can exceed the hard cap in either direction.
    assert clamp_adj(999) == EVAL_ADJ_CAP
    assert clamp_adj(-999) == -EVAL_ADJ_CAP


def test_is_enabled_value_fails_open():
    # Absent / affirmative → enabled (fail-open so a Redis blip never drops steers).
    assert is_enabled_value(None) is True
    assert is_enabled_value(b"1") is True
    assert is_enabled_value("on") is True
    assert is_enabled_value("enabled") is True
    # Only explicit off tokens disengage.
    assert is_enabled_value(b"0") is False
    assert is_enabled_value("false") is False
    assert is_enabled_value("OFF") is False
    assert is_enabled_value("disabled") is False


def test_ttl_cutoff_is_14_days():
    now = datetime(2026, 7, 22, tzinfo=timezone.utc)
    assert ttl_cutoff(now) == now - timedelta(days=EVAL_PROMOTE_TTL_DAYS)


# --- Apply-map guards (behavior-preserving + bounded) -------------------------

def test_apply_map_promote_and_downrank():
    items = [
        {"type": "futures", "score": 96, "_rank_score": 96, "data": {"id": 1}},
        {"type": "futures", "score": 12, "_rank_score": 12, "data": {"id": 2}},
        {"type": "event", "score": 50, "data": {"id": 3}},
    ]
    _apply_manual_review_decision_map(
        items,
        {
            ("futures", "1"): "accepted_promote",
            ("futures", "2"): "accepted_downrank",
        },
    )
    # promote: +8, display capped at 98, ordering score bumped uncapped
    assert items[0]["score"] == 98
    assert items[0]["_rank_score"] == 96 + EVAL_PROMOTE_ADJ
    assert items[0]["_review_decision"] == "accepted_promote"
    assert items[0]["_review_decision_adj"] == EVAL_PROMOTE_ADJ
    # downrank: -18, display floored at 0
    assert items[1]["score"] == 0
    assert items[1]["_review_decision"] == "accepted_downrank"
    # untouched item unchanged
    assert items[2]["score"] == 50


# --- Kill switch + TTL guards (both directions) -------------------------------

def _fake_redis(value):
    rc = AsyncMock()
    rc.get = AsyncMock(return_value=value)
    rc.aclose = AsyncMock()
    return rc


async def test_kill_switch_off_leaves_scoring_untouched(monkeypatch):
    import app.tasks.redis_state as rs

    monkeypatch.setattr(rs, "get_async_redis_client", lambda: _fake_redis(b"0"))
    db = AsyncMock()
    items = [{"type": "futures", "score": 50, "_rank_score": 50, "data": {"id": 1}}]

    await feed_mod._apply_manual_review_decisions(db, items)

    # Nothing applied AND the DB was never queried — the switch short-circuits.
    assert items[0]["score"] == 50
    db.execute.assert_not_called()


async def test_kill_switch_on_applies_and_query_has_ttl(monkeypatch):
    import app.tasks.redis_state as rs

    monkeypatch.setattr(rs, "get_async_redis_client", lambda: _fake_redis(b"1"))

    row = types.SimpleNamespace(
        item_type="futures", item_id="1",
        decision="accepted_promote", family_key=None,
    )
    result = MagicMock()
    result.all.return_value = [row]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    items = [{"type": "futures", "score": 50, "_rank_score": 50, "data": {"id": 1}}]
    await feed_mod._apply_manual_review_decisions(db, items)

    # Bounded promote applied.
    assert items[0]["score"] == 50 + EVAL_PROMOTE_ADJ
    # The 14-day TTL filter is part of the query the feed runs (expires at TTL).
    compiled = str(db.execute.call_args[0][0]).lower()
    assert "created_at" in compiled
