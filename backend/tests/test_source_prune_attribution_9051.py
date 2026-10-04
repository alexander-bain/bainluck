"""A held headline can correlate real source removal without treating a log as commit."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.tasks import prediction_market_matching as pmm


def unlink_session(remaining=0, sources=None):
    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalar=lambda: remaining),
        SimpleNamespace(scalar_one_or_none=lambda: sources if sources is not None else
                        {"kalshi": 0.7, "betting": 0.6}),
        None,
    ]
    return db


def cleanup_session():
    db = AsyncMock()
    # Each source has its own SELECT; the stale candidate with no source is a no-op.
    db.execute.side_effect = [
        SimpleNamespace(all=lambda: [(123, {"kalshi": 0.7, "betting": 0.6}),
                                      (456, {"betting": 0.6})]),
        None,
        SimpleNamespace(all=lambda: [(789, {"polymarket": 0.4})]),
        None,
    ]
    return db


@pytest.fixture
def emit(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(pmm, "logger", logger)
    return logger.info


@pytest.mark.asyncio
async def test_unlink_records_exact_identity_only_after_update_without_committing(emit):
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    emit.assert_called_once_with(
        "blend_source_prune_staged event_id=%s source=%s phase=unlink", 123, "kalshi")
    assert db.execute.await_count == 3
    db.commit.assert_not_awaited()


@pytest.mark.parametrize("remaining,sources", [(1, {"kalshi": 0.7}), (0, {"betting": 0.6})])
@pytest.mark.asyncio
async def test_surviving_or_absent_source_is_silent(emit, remaining, sources):
    db = unlink_session(remaining, sources)
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is False
    assert db.execute.await_count == 2
    emit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_update_never_emits_a_staged_prune(emit):
    db = unlink_session()
    responses = list(db.execute.side_effect)
    db.execute.side_effect = responses[:2] + [RuntimeError("write failed")]
    with pytest.raises(RuntimeError, match="write failed"):
        await pmm._prune_orphaned_blend_source(db, 123, "kalshi")
    emit.assert_not_called()


@pytest.mark.asyncio
async def test_logger_failure_cannot_change_unlink_result_or_transaction(emit):
    emit.side_effect = RuntimeError("handler failed")
    db = unlink_session()
    assert await pmm._prune_orphaned_blend_source(db, 123, "kalshi") is True
    assert db.execute.await_count == 3
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_logs_each_changed_event_source_and_keeps_one_commit(emit):
    db = cleanup_session()
    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    assert [call.args for call in emit.call_args_list] == [
        ("blend_source_prune_staged event_id=%s source=%s phase=cleanup", 123, "kalshi"),
        ("blend_source_prune_staged event_id=%s source=%s phase=cleanup", 789, "polymarket"),
    ]
    assert db.execute.await_count == 4
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_logger_failure_cannot_suppress_cleanup_commit(emit):
    emit.side_effect = RuntimeError("handler failed")
    db = cleanup_session()
    assert await pmm._cleanup_orphaned_blend_sources(db) == 2
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_commit_is_still_raised_and_logs_remain_only_staged(emit):
    db = cleanup_session()
    db.commit.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await pmm._cleanup_orphaned_blend_sources(db)
    assert len(emit.call_args_list) == 2
    assert all("_staged " in call.args[0] and "committed" not in call.args[0]
               for call in emit.call_args_list)
