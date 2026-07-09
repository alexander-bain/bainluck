"""#156 (gotcha #38/#995 playbook): backfill_kalshi_candlestick must stay under
its 600s soft limit AND make net forward progress across runs.

_backfill_candlestick_snapshots fetches settled events per series with nested
markets. The pre-#156 shape busted the wall two ways:

1. gotcha #38 — a 200-event `with_nested_markets` page holds the GIL for the
   entire C-level JSON decode (~67s), freezing the event loop so no deadline can
   fire → SoftTimeLimitExceeded@600s before anything commits. Fix: 200 → 50 so
   each decode is sub-second.
2. Starvation — the series list was recomputed in the SAME order every run and
   the task broke at the deadline, so the oldest (api_empty, past-the-cliff)
   series got re-ground first every run and later series never ran → 0 net
   successes. Fix: a resumable Redis cursor that rotates past the last finished
   series so every series is eventually reached, banking partial progress.

Guard the structure so it can't regress.
"""

import inspect

from app.tasks.kalshi import _backfill_candlestick_snapshots


def _src() -> str:
    return inspect.getsource(_backfill_candlestick_snapshots)


def test_nested_markets_page_is_small():
    """gotcha #38: the nested-markets fetch must use a small page (<=50) so the
    C-level JSON decode never holds the GIL long enough to freeze the loop."""
    src = _src()
    assert "with_nested_markets=True" in src, "fetch shape changed"
    assert "limit=200" not in src, (
        "200-event nested-markets page holds the GIL ~67s (gotcha #38) — must be 50"
    )
    assert "limit=50" in src


def test_resumable_series_cursor_present():
    """The cross-run Redis cursor rotates past the last finished series so the
    oldest dead cohort can't starve the rest of the backlog."""
    src = _src()
    assert '"kalshi:candlestick:series_cursor"' in src
    # reads the cursor and rotates the series list past it
    assert "series_list[_i + 1:]" in src
    # advances the cursor only when a series drained within budget
    assert "_within_budget" in src
    assert "_rc.set(_cursor_key" in src


def test_inner_page_loop_has_budget_guard():
    """The per-page loop must check BOTH the caller deadline and the local 540s
    cap so a deep series can't paginate past the 600s wall between series checks."""
    src = _src()
    assert "for page in range(50):" in src, "page loop shape changed"
    after_page = src.split("for page in range(50):", 1)[1]
    head = after_page.split("service.get_events", 1)[0]
    assert "_time.monotonic()" in head and "break" in head
    assert "540" in head


def test_soft_time_limit_handled_gracefully():
    """A soft-limit hit is a clean partial run (per-page commits already banked
    progress), not an error — it must be caught explicitly."""
    src = _src()
    assert "except SoftTimeLimitExceeded:" in src


def test_registration_carries_soft_limit():
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.backfill_kalshi_candlestick"]
    assert task.soft_time_limit == 600
    assert task.time_limit == 660
