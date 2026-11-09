"""#12042: the matcher's result says which phase grew it to ~1 GB.

Measured Nov 9 on worker-heavy (1 GB, two slots): ``match_prediction_markets``
peaked at 1,021, 1,008 and 1,022 MB in one pass each (``heavy_memory_turn``,
#12398), from ~170 MB at the start. Nothing said where. ``mark_memory`` records
``[rss_mb, peak_mb]`` after each phase into the task result, and the peak is
the high-water mark, so the first phase whose peak jumps is the one to shrink.
"""
import inspect
from unittest.mock import patch

from app.tasks import heavy_memory_turns as turns
from app.tasks import prediction_market_matching as pmm

PHASES = [
    "start",
    "settled_sweep",
    "pass1_ticker_scan",
    "pass2_general_scan",
    "pass3_backlog_scan",
    "phase15_revalidate",
    "relink_and_reconcile",
    "phase2",
    "phase2b_2c",
    "phase3_backfill",
    "phantom_cleanup",
]


def test_mark_memory_records_rss_and_peak_rounded():
    stats: dict = {}
    with patch.object(turns, "rss_mb", return_value=171.4), patch.object(
        turns, "peak_rss_mb", return_value=1021.6
    ):
        turns.mark_memory(stats, "phase2")
    assert stats["memory_mb"] == {"phase2": [171, 1022]}


def test_mark_memory_keeps_order_and_unknowns():
    stats: dict = {}
    with patch.object(turns, "rss_mb", return_value=None), patch.object(
        turns, "peak_rss_mb", return_value=None
    ):
        turns.mark_memory(stats, "start")
        turns.mark_memory(stats, "phase2")
    assert list(stats["memory_mb"]) == ["start", "phase2"]
    assert stats["memory_mb"]["start"] == [None, None]


def test_mark_memory_never_raises():
    stats: dict = {}
    with patch.object(turns, "rss_mb", side_effect=OSError("no /proc")):
        turns.mark_memory(stats, "start")
    assert "memory_mb" not in stats


def test_the_matcher_marks_every_phase_in_order():
    src = inspect.getsource(pmm._match_prediction_markets)
    assert "from app.tasks.heavy_memory_turns import mark_memory as _mem" in src
    positions = [src.index(f'_mem(stats, "{name}")') for name in PHASES]
    assert positions == sorted(positions), "the marks must follow the phases"
    # Each phase is marked once, so a peak can be attributed to one span.
    for name in PHASES:
        assert src.count(f'_mem(stats, "{name}")') == 1, name
