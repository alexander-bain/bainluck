"""#2722 — one 429 on the settled feed's head page no longer costs a cadence.

Measured 2026-10-14 (#2722 comment 6165557468): the 09:13Z beat met a 429 on
its first ``GET /markets?status=settled`` page, made no head progress and read
``partial``. ``futures_markets`` 65703979 (settled at the venue 09:11:56Z) was
closed by the 09:23Z beat, 11m04s later: outside the ten-minute promise.

:func:`fetch_settled_event_tickers` now re-asks a 429'd page from one run-wide
:class:`RateLimitBudget`, honouring ``Retry-After``. Only the head and relist
walks are handed the budget; the trail and backlog stop at their first 429.
``KalshiAPIService.get_markets`` is untouched.

The venue, the clock, Redis and the sleep are doubled; the statements run on
the seeded SQLite table of the main feed suite. Clocks are literals (gotcha #44).
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from app.tasks import kalshi_resolution_sweep as sweep
from tests import test_kalshi_settled_feed_2722 as feed_suite
from tests.test_kalshi_settled_feed_2722 import (
    CEILING,
    EARLY_BAND,
    EARLY_UNDATED,
    LAST_RUN,
    NOW,
    _feed,
    _feed_state,
    _seed,
    _state,
    _Venue,
)

#: The main feed suite's in-memory Redis, shared rather than copied.
redis_state = feed_suite.redis_state


def _429(retry_after=None) -> httpx.HTTPStatusError:
    """What ``get_markets``'s ``raise_for_status()`` raises for a 429."""
    request = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets")
    headers = {} if retry_after is None else {"Retry-After": str(retry_after)}
    response = httpx.Response(429, headers=headers, request=request)
    return httpx.HTTPStatusError(
        "Client error '429 Too Many Requests'", request=request, response=response
    )


def _500() -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets")
    response = httpx.Response(500, request=request)
    return httpx.HTTPStatusError(
        "Server error '500 Internal Server Error'", request=request, response=response
    )


class _ThrottledVenue(_Venue):
    """The feed suite's venue, answering some page reads with an exception.

    ``throttle(n, ask)`` sees the call's index and its bounds/cursor and returns
    the exception to raise, or None to answer normally.
    """

    def __init__(self, throttle, **kw):
        super().__init__(**kw)
        self.throttle = throttle
        self.calls: list[dict] = []

    async def get_markets(self, **kw):
        ask = dict(min=kw.get("min_settled_ts"), max=kw.get("max_settled_ts"),
                   cursor=kw.get("cursor"))
        exc = self.throttle(len(self.calls), ask)
        self.calls.append(dict(ask, throttled=exc is not None))
        if exc is not None:
            raise exc
        return await super().get_markets(**kw)


@pytest.fixture
def waits(monkeypatch):
    """Every 429 wait the feed takes, in order; nothing really sleeps."""
    taken: list[float] = []

    async def fake_sleep(seconds):
        taken.append(seconds)

    monkeypatch.setattr(sweep, "_settled_feed_sleep", fake_sleep)
    return taken


def _first_only(exc):
    return lambda n, ask: exc if n == 0 else None


class TestASingle429NoLongerStallsTheHead:
    def test_the_0913z_shape_one_429_on_page_one_still_finishes_the_head(
            self, redis_state, waits):
        """The 09:13Z beat, replayed: a 429 on the first head page. The page is
        re-asked once after the backoff, the head reaches the present and the
        early final settled 200 s ago is closed by THIS beat, not the next."""
        engine = _seed()
        venue = _ThrottledVenue(_first_only(_429()))
        report = _feed(engine, venue)

        assert report["head_caught_up"] is True
        assert report["head_windows"] >= 1
        assert report["head_stop"] is None
        assert redis_state.store["feed"]["head"] == CEILING
        assert _state(engine)[0][EARLY_BAND["id"]] == ("resolved", NOW.isoformat())
        assert report["terminal"] == "complete"
        # The SAME page was asked again, once, after one backoff.
        assert venue.calls[0]["throttled"] and not venue.calls[1]["throttled"]
        assert {k: venue.calls[1][k] for k in ("min", "max", "cursor")} == {
            k: venue.calls[0][k] for k in ("min", "max", "cursor")}
        assert waits == [sweep.SETTLED_FEED_429_BACKOFF_S]
        assert report["venue_429_retries"] == 1
        assert report["venue_429_waited_seconds"] == sweep.SETTLED_FEED_429_BACKOFF_S

    def test_a_429_mid_window_resumes_the_same_cursor(self, redis_state, waits):
        """A 429 on page 2 re-asks page 2, never page 1 and never page 3."""
        engine = _seed()
        venue = _ThrottledVenue(lambda n, ask: _429() if n == 1 else None, page_size=1)
        report = _feed(engine, venue)
        assert venue.calls[1]["throttled"] is True
        assert venue.calls[1]["cursor"] == venue.calls[2]["cursor"] == "1"
        assert report["head_caught_up"] is True
        assert _state(engine)[0][EARLY_UNDATED["id"]][0] == "resolved"

    def test_retry_after_is_the_wait(self, redis_state, waits):
        report = _feed(_seed(), _ThrottledVenue(_first_only(_429(retry_after=3))))
        assert waits == [3.0]
        assert report["head_caught_up"] is True

    def test_the_backoff_doubles_for_the_same_page(self, redis_state, waits):
        report = _feed(_seed(), _ThrottledVenue(lambda n, ask: _429() if n < 2 else None))
        assert waits == [sweep.SETTLED_FEED_429_BACKOFF_S, 2 * sweep.SETTLED_FEED_429_BACKOFF_S]
        assert report["head_caught_up"] is True


class TestA429PastTheCapIsStillFailClosed:
    def test_a_persistent_429_keeps_the_watermark_and_reports_the_error(
            self, redis_state, waits):
        """Today's fail-closed behaviour, unchanged once the budget is spent: the
        window is not walked, the head does not move, nothing is asked or
        written, the run reads ``partial`` and names the 429."""
        engine = _seed()
        venue = _ThrottledVenue(lambda n, ask: _429())
        report = _feed(engine, venue)

        assert redis_state.store["feed"]["head"] == LAST_RUN
        assert report["head_windows"] == 0
        assert report["terminal"] == "partial"
        assert "429" in report["head_stop"]
        assert "not retried: 429 retries spent" in report["head_stop"]
        assert "429" in report["terminal_reason"]
        assert venue.asked == []
        assert _state(engine)[0][EARLY_BAND["id"]] == ("open", None)
        assert report["venue_429_retries"] == sweep.SETTLED_FEED_429_RETRIES
        assert report["venue_429_not_retried"].startswith("429 retries spent")

    def test_a_retry_after_longer_than_one_wait_is_not_waited(self, redis_state, waits):
        """Asking before the venue's named wait only buys another 429, so a wait
        the run cannot afford is not taken: no sleep, the page error stands."""
        too_long = sweep.SETTLED_FEED_429_MAX_WAIT_S + 50
        venue = _ThrottledVenue(lambda n, ask: _429(retry_after=too_long))
        report = _feed(_seed(), venue)
        assert waits == []
        assert report["venue_429_retries"] == 0
        assert f"Retry-After {too_long:g}s" in report["head_stop"]
        assert redis_state.store["feed"]["head"] == LAST_RUN

    @pytest.mark.parametrize("exc", [_500(), RuntimeError("venue 502")],
                             ids=["http-500", "transport"])
    def test_an_error_that_is_not_a_429_is_never_retried(self, redis_state, waits, exc):
        venue = _ThrottledVenue(lambda n, ask: exc)
        report = _feed(_seed(), venue)
        assert waits == []
        assert report["venue_429_retries"] == 0
        assert report["terminal"] == "partial"
        assert "page error" in report["head_stop"]
        # One read per walk that had a window to read, none of them repeated.
        assert len(venue.calls) == len({(c["min"], c["max"]) for c in venue.calls})


class TestTheRetryBudgetIsBounded:
    def test_one_run_retries_at_most_the_cap_across_every_walk(self, redis_state, waits):
        """Every page of every walk answering 429: the run still re-asks at most
        ``SETTLED_FEED_429_RETRIES`` pages and waits at most the wait budget,
        and each other walk reads once and stops."""
        floor = int((NOW - timedelta(days=sweep.SETTLED_FEED_BACKLOG_DAYS)).timestamp())
        redis_state.store["feed"] = _feed_state(back=floor, back_end=LAST_RUN - 3600)
        venue = _ThrottledVenue(lambda n, ask: _429())
        report = _feed(_seed(), venue)

        assert report["venue_429_retries"] == sweep.SETTLED_FEED_429_RETRIES
        assert len(waits) == sweep.SETTLED_FEED_429_RETRIES
        assert sum(waits) <= sweep.SETTLED_FEED_429_WAIT_BUDGET_S
        assert max(waits) <= sweep.SETTLED_FEED_429_MAX_WAIT_S
        walks = 4  # head, relist, trail, backlog: one first read each
        assert len(venue.calls) == walks + sweep.SETTLED_FEED_429_RETRIES
        for name in ("head_stop", "relist_stop", "trail_stop", "backlog_stop"):
            assert "429" in report[name], name

    def test_the_budget_itself_refuses_past_its_counts(self):
        budget = sweep.RateLimitBudget()
        granted = [budget.take(_429(), attempt) for attempt in range(10)]
        assert sum(w is not None for w in granted) == sweep.SETTLED_FEED_429_RETRIES
        assert granted[sweep.SETTLED_FEED_429_RETRIES:] == [None] * (
            10 - sweep.SETTLED_FEED_429_RETRIES)
        assert budget.waited_s <= sweep.SETTLED_FEED_429_WAIT_BUDGET_S

        named = sweep.RateLimitBudget()
        waited = [named.take(_429(retry_after=sweep.SETTLED_FEED_429_MAX_WAIT_S), 0)
                  for _ in range(3)]
        # Two full waits fit the run's wait budget; the third does not.
        assert waited == [sweep.SETTLED_FEED_429_MAX_WAIT_S] * 2 + [None]
        assert "exceeds" in named.refused

    def test_the_worst_case_stays_well_inside_the_soft_limit(self):
        """Each re-ask can also spend the client's 25 s read timeout
        (``KalshiAPIService``: ``httpx.Timeout(read=25.0)``). Retries plus waits
        stay under half the beat's soft limit, leaving the other half for the
        page and row budgets that ran before them."""
        from app.tasks import celery_app

        soft = celery_app.tasks["app.tasks.settle_kalshi_settled_feed"].soft_time_limit
        assert soft == 240
        worst = sweep.SETTLED_FEED_429_RETRIES * 25.0 + sweep.SETTLED_FEED_429_WAIT_BUDGET_S
        assert worst < soft / 2


class TestTheHeadIsProtectedFromTheBacklog:
    def test_the_trail_and_backlog_stop_at_their_first_429_and_spend_no_retry(
            self, redis_state, waits):
        """Only the windows a day behind (trail) and history (backlog) are
        throttled. Each reads once, stops, and leaves the whole budget unspent
        for the next head window; the head and relist finish untouched."""
        floor = int((NOW - timedelta(days=sweep.SETTLED_FEED_BACKLOG_DAYS)).timestamp())
        redis_state.store["feed"] = _feed_state(back=floor, back_end=LAST_RUN - 3600)
        old_only = lambda n, ask: _429() if ask["max"] <= CEILING - 3600 else None  # noqa: E731
        engine = _seed()
        venue = _ThrottledVenue(old_only)
        report = _feed(engine, venue)

        assert report["head_caught_up"] is True
        assert report["relist_stop"] is None
        assert _state(engine)[0][EARLY_BAND["id"]][0] == "resolved"
        assert waits == []
        assert report["venue_429_retries"] == 0
        assert "429" in report["trail_stop"] and "429" in report["backlog_stop"]
        assert sum(c["throttled"] for c in venue.calls) == 2
        assert redis_state.store["feed"]["back"] == floor

    def test_the_walks_that_may_retry_are_the_head_and_the_relist(self):
        assert sweep.SETTLED_FEED_RETRYING_WALKS == ("head", "relist")
