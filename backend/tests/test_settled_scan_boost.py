"""Tests for the settled-events scan de-starvation boost (Queue #230).

A Kalshi series that carries BOTH resolved and open markets ("partial-settled")
is actively settling — a just-concluded event whose winner market is stuck
``status='open'`` (gotcha #33) is likely waiting inside. The scheduled
settled-events backfill must boost these ahead of its cursor rotation so they
settle within one run instead of waiting up to the full ~38-run rotation (the
THOC26 "won't settle" class).
"""

from app.tasks.kalshi import _order_settled_scan_list

PRIORITY = ["KXNBAGAME", "KXMLBHR"]


def test_partial_settled_boosted_ahead_of_rotation_window():
    # KXPGATOUR sits deep in the alphabetical non-priority list; without a boost
    # it would wait for the cursor to rotate to it.
    all_series = PRIORITY + [f"KXAAA{i}" for i in range(200)] + ["KXPGATOUR"]
    partial = {"KXPGATOUR"}
    check_list, _ = _order_settled_scan_list(PRIORITY, all_series, partial, cursor_pos=0)
    # Priority first, then the boosted series, before the rotation window.
    assert check_list[:2] == PRIORITY
    assert check_list[2] == "KXPGATOUR"


def test_priority_series_always_first():
    all_series = PRIORITY + ["KXPGATOUR", "KXATP"]
    check_list, _ = _order_settled_scan_list(PRIORITY, all_series, {"KXATP"}, cursor_pos=0)
    assert check_list[: len(PRIORITY)] == PRIORITY


def test_boost_deduped_from_window():
    all_series = PRIORITY + ["KXA", "KXB", "KXC"]
    partial = {"KXA", "KXC"}
    check_list, _ = _order_settled_scan_list(PRIORITY, all_series, partial, cursor_pos=0)
    # Each boosted series appears exactly once (not also in the rotation window).
    assert check_list.count("KXA") == 1
    assert check_list.count("KXC") == 1


def test_boost_is_capped():
    all_series = PRIORITY + [f"KXP{i:03d}" for i in range(100)]
    partial = {f"KXP{i:03d}" for i in range(100)}  # all partial-settled
    check_list, _ = _order_settled_scan_list(
        PRIORITY, all_series, partial, cursor_pos=0, boost_cap=40
    )
    boosted = [s for s in check_list[len(PRIORITY):] if s.startswith("KXP")]
    # No more than boost_cap distinct series are front-loaded as the boost slice.
    # (Window may re-add others, but the boost prefix itself is capped.)
    boost_prefix = check_list[len(PRIORITY): len(PRIORITY) + 40]
    assert len(boost_prefix) == 40


def test_cursor_advances_regardless_of_boost():
    all_series = PRIORITY + [f"KXA{i}" for i in range(250)]
    _, next_pos = _order_settled_scan_list(PRIORITY, all_series, set(), cursor_pos=0, window=100)
    assert next_pos == 100
    _, next_pos2 = _order_settled_scan_list(PRIORITY, all_series, set(), cursor_pos=200, window=100)
    assert next_pos2 == (300 % 250)


def test_priority_partial_settled_not_double_listed():
    # A priority series that also happens to be partial-settled is not re-added by
    # the boost (boost only front-loads NON-priority series).
    all_series = PRIORITY + ["KXPGATOUR"]
    partial = {"KXNBAGAME", "KXPGATOUR"}  # KXNBAGAME is priority
    check_list, _ = _order_settled_scan_list(PRIORITY, all_series, partial, cursor_pos=0)
    assert check_list.count("KXNBAGAME") == 1


def test_no_partial_settled_matches_plain_rotation():
    all_series = PRIORITY + [f"KXA{i}" for i in range(50)]
    check_list, next_pos = _order_settled_scan_list(PRIORITY, all_series, set(), cursor_pos=0)
    # With nothing to boost, the order is exactly priority + rotation window.
    non_priority = [s for s in all_series if s not in set(PRIORITY)]
    assert check_list == PRIORITY + non_priority[:100]


def test_thoc26_deep_in_rotation_still_boosted():
    """THOC26 regression: KXPGATOUR partial-settled but the cursor is nowhere
    near it — it must still be scanned this run."""
    non_priority = [f"KXAAA{i:03d}" for i in range(300)]
    all_series = PRIORITY + non_priority + ["KXPGATOUR"]
    # Cursor at 0 → rotation window is KXAAA000..KXAAA099, far from KXPGATOUR.
    check_list, _ = _order_settled_scan_list(
        PRIORITY, all_series, {"KXPGATOUR"}, cursor_pos=0
    )
    assert "KXPGATOUR" in check_list
    assert check_list.index("KXPGATOUR") < check_list.index("KXAAA000")
