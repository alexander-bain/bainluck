"""Guard tests for the #1163 phantom-blend-source fix (Queue #227 Item 1).

Invariant: a prediction-market source (kalshi/polymarket) may only appear in
Event.win_probability_sources while a linked market of that source backs it.
The unlink sites used to set event_id=None without pruning the key, leaving a
phantom blend input the aggregation averaged in forever (a night's MLB slate
carried a kalshi key with ZERO backing linked kalshi markets → matured-linkage
33%). These tests pin the prune helper (pure + async) and the write-path wiring.
"""

import inspect
from unittest.mock import AsyncMock

import pytest

from app.tasks.prediction_market_matching import (
    _PM_BLEND_SOURCES,
    prune_blend_source,
    _prune_orphaned_blend_source,
    _cleanup_orphaned_blend_sources,
)
import app.tasks.prediction_market_matching as pmm


# ── Pure: prune_blend_source ────────────────────────────────────────────────
class TestPruneBlendSourcePure:
    def test_pm_source_zero_remaining_is_removed(self):
        wps = {"kalshi": 0.93, "betting": 0.54}
        new, changed = prune_blend_source(wps, "kalshi", remaining_linked=0)
        assert changed is True
        assert "kalshi" not in new
        assert new["betting"] == 0.54  # non-PM sibling untouched

    def test_pm_source_with_remaining_is_kept(self):
        wps = {"kalshi": 0.93, "betting": 0.54}
        new, changed = prune_blend_source(wps, "kalshi", remaining_linked=1)
        assert changed is False
        assert new["kalshi"] == 0.93

    def test_non_pm_source_never_removed_even_at_zero(self):
        # betting/espn/mlb/stat_model come from their own pollers, not linked
        # markets — the invariant must never touch them.
        for src in ("betting", "espn", "mlb", "stat_model"):
            wps = {src: 0.5, "kalshi": 0.9}
            new, changed = prune_blend_source(wps, src, remaining_linked=0)
            assert changed is False
            assert new[src] == 0.5

    def test_polymarket_is_a_pm_source(self):
        new, changed = prune_blend_source({"polymarket": 0.4}, "polymarket", 0)
        assert changed is True and "polymarket" not in new

    def test_missing_key_is_noop(self):
        new, changed = prune_blend_source({"betting": 0.5}, "kalshi", 0)
        assert changed is False and new == {"betting": 0.5}

    def test_none_wps_is_safe(self):
        new, changed = prune_blend_source(None, "kalshi", 0)
        assert changed is False and new == {}

    def test_original_dict_not_mutated(self):
        wps = {"kalshi": 0.9}
        prune_blend_source(wps, "kalshi", 0)
        assert wps == {"kalshi": 0.9}  # caller's dict is preserved

    def test_pm_blend_sources_membership(self):
        assert "kalshi" in _PM_BLEND_SOURCES
        assert "polymarket" in _PM_BLEND_SOURCES
        assert "betting" not in _PM_BLEND_SOURCES


# ── Async: _prune_orphaned_blend_source ─────────────────────────────────────
class TestPruneOrphanedBlendSourceAsync:
    @pytest.mark.asyncio
    async def test_prunes_when_no_linked_market_remains(self):
        session = AsyncMock()
        # First execute() = count(remaining linked) -> 0; second = current wps.
        count_res = AsyncMock()
        count_res.scalar = lambda: 0
        wps_res = AsyncMock()
        wps_res.scalar_one_or_none = lambda: {"kalshi": 0.93, "betting": 0.54}
        session.execute = AsyncMock(side_effect=[count_res, wps_res, AsyncMock()])

        pruned = await _prune_orphaned_blend_source(session, 15175875, "kalshi")
        assert pruned is True
        # The third execute() is the UPDATE with the pruned dict.
        update_call = session.execute.await_args_list[2]
        assert update_call is not None

    @pytest.mark.asyncio
    async def test_keeps_when_linked_market_remains(self):
        session = AsyncMock()
        count_res = AsyncMock()
        count_res.scalar = lambda: 2  # a sibling kalshi market still linked
        wps_res = AsyncMock()
        wps_res.scalar_one_or_none = lambda: {"kalshi": 0.93}
        session.execute = AsyncMock(side_effect=[count_res, wps_res])
        pruned = await _prune_orphaned_blend_source(session, 1, "kalshi")
        assert pruned is False

    @pytest.mark.asyncio
    async def test_non_pm_source_short_circuits_no_query(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        pruned = await _prune_orphaned_blend_source(session, 1, "betting")
        assert pruned is False
        session.execute.assert_not_called()  # no DB work for a non-PM source

    @pytest.mark.asyncio
    async def test_none_event_id_short_circuits(self):
        session = AsyncMock()
        session.execute = AsyncMock()
        assert await _prune_orphaned_blend_source(session, None, "kalshi") is False
        session.execute.assert_not_called()


# ── Write-path wiring: every unlink site prunes ─────────────────────────────
class TestUnlinkSitesPrune:
    def test_all_unlink_sites_call_prune_helper(self):
        """Every place that sets event_id=None on a PM market must be paired with
        a _prune_orphaned_blend_source call, or a phantom source re-appears."""
        src = inspect.getsource(pmm)
        # The three unlink sites + the self-heal wiring reference the helper.
        assert src.count("_prune_orphaned_blend_source(") >= 4  # 3 sites + def
        assert "_cleanup_orphaned_blend_sources(" in src

    def test_match_task_runs_cleanup(self):
        src = inspect.getsource(pmm._match_prediction_markets)
        assert "_cleanup_orphaned_blend_sources(" in src
