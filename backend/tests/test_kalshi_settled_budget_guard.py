"""#969: backfill_kalshi_settled must not bust its 900s soft limit.

_backfill_from_settled_events paginates per-series (up to 200 pages/series). The
outer per-series time-budget check is not enough — a single deep series can
paginate past the 900s soft wall mid-loop (this kept the task in a ~5.5-day
SoftTimeLimitExceeded outage). The inner page loop MUST carry a _MAX_SECONDS
budget check that breaks mid-series; the per-series cursor is persisted each page
so the next cron resumes mid-pagination. Guard the structure so it can't regress.
"""

import inspect

from app.tasks.kalshi import _backfill_from_settled_events


def _page_loop_body() -> str:
    src = inspect.getsource(_backfill_from_settled_events)
    # the slice from the page loop header to the inner retry loop is where the
    # top-of-page guard must live
    assert "for page_num in range(200):" in src, "page loop shape changed"
    after_page = src.split("for page_num in range(200):", 1)[1]
    return after_page.split("for _retry in range(3):", 1)[0]


def test_page_loop_has_inner_time_budget_guard():
    head = _page_loop_body()
    assert "_MAX_SECONDS" in head, (
        "inner page loop has no _MAX_SECONDS budget check — a deep series will "
        "paginate past the 900s soft wall (SoftTimeLimitExceeded, the #969 outage)"
    )
    assert "_time.monotonic()" in head and "break" in head


def test_budget_and_cursor_machinery_present():
    src = inspect.getsource(_backfill_from_settled_events)
    # budget is comfortably under the task's 900s soft limit
    assert "_MAX_SECONDS = 720" in src
    # per-series cursor is persisted so a mid-series break resumes next cron
    assert 'f"bainluck:settled_cursor:{series}"' in src
    assert "_rc.setex(_cursor_key" in src
    # outer per-series guard still present (defense in depth)
    assert src.count("(_time.monotonic() - _start_time) > _MAX_SECONDS") >= 2


def test_registration_carries_soft_limit():
    """Sanity: the task itself records (not silent SIGKILL like #966/#967) — it
    already has a soft limit; this fix is about staying under it, not adding one."""
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.backfill_kalshi_settled"]
    assert task.soft_time_limit == 900
    assert task.time_limit == 960
