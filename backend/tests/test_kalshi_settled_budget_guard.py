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
    # 720 (#107) -> 600 (#969) -> 420 (#969-Q109): the trigger test showed a
    # catch-up run overran the 600s guard by ~285s (61 sequential fetches), so
    # the margin was widened to keep the wall-clock comfortably under 900s.
    assert "_MAX_SECONDS = 420" in src
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


# ---- #969 (Queue #109): the inner-op fix — bound the FETCH span ----
# The page-top guard only bounds BETWEEN pages; the get_events fetch span
# (network + nested 429 backoff) was the single uninterrupted op overrunning
# the 900s wall. These cover the deadline plumbing end to end.

from unittest.mock import AsyncMock, MagicMock  # noqa: E402


async def test_get_events_returns_early_when_deadline_passed():
    """get_events must not hit the network once the deadline has passed — it
    returns ([], INPUT cursor) so the caller resumes/re-fetches this page next
    run (the deadline check is the first thing in the retry loop)."""
    import time as _time
    from app.services.kalshi_api import KalshiAPIService

    svc = object.__new__(KalshiAPIService)  # bypass __init__/creds
    svc.client = AsyncMock()
    svc.client.get = AsyncMock()  # must NOT be awaited

    events, cursor = await svc.get_events(
        status="settled", series_ticker="KXTEST",
        cursor="CUR123", deadline=_time.monotonic() - 1.0,
    )
    assert events == []
    assert cursor == "CUR123"  # input cursor returned for resume
    svc.client.get.assert_not_awaited()


async def test_get_events_429_does_not_sleep_past_deadline():
    """A 429 must not back off past the deadline — the call terminates with an
    empty result + the input cursor, never an unbounded retry/backoff span."""
    import time as _time
    from app.services.kalshi_api import KalshiAPIService

    svc = object.__new__(KalshiAPIService)
    resp = MagicMock()
    resp.status_code = 429
    svc.client = AsyncMock()
    svc.client.get = AsyncMock(return_value=resp)

    events, cursor = await svc.get_events(
        status="settled", cursor="C", deadline=_time.monotonic() + 0.05,
    )
    assert events == []
    assert cursor == "C"
    # bounded by the 4-attempt cap — never an unbounded loop
    assert svc.client.get.await_count <= 4


def test_caller_passes_deadline_into_fetch():
    """The settled-events caller passes its budget deadline INTO get_events and
    remembers this page's cursor for idempotent re-fetch."""
    src = inspect.getsource(_backfill_from_settled_events)
    assert "deadline=_deadline" in src, "caller must pass deadline into get_events"
    assert "_deadline = _start_time + _MAX_SECONDS" in src
    assert "_page_cursor = cursor" in src


def test_caller_breaks_before_heavy_sql_when_fetch_consumes_budget():
    """If the fetch span consumes the budget, the caller persists THIS page's
    cursor and breaks BEFORE the heavy per-page SQL (which has no inner guard)."""
    src = inspect.getsource(_backfill_from_settled_events)
    # the post-fetch budget check persists the page cursor and breaks
    assert "_rc.setex(_cursor_key, 86400 * 7, _page_cursor)" in src
    # and the caller's own 429 backoff is clamped to the remaining budget
    assert "min(5 * (_retry + 1), 10, _rem)" in src
