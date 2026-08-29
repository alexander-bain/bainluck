"""LAT-P118 — the origin channel, asserted OVER HTTP.

WHY THIS FILE EXISTS SEPARATELY FROM `tests/test_search_origin_channel_p118.py`.

That suite calls the route functions directly, which is the right way to pin the
guard's LOGIC — it can pass a hand-built `Request`, an empty header value, a
`None`. What it cannot prove is the thing the whole channel rests on: **that a
header set by a real client, arriving through a real ASGI stack, reaches the
guard at all.**

The distinction is not theoretical. `typeahead_search` had no `request`
parameter before this ship, and the obviously-correct annotation for the new one
— `Optional[Request] = None` — kills the app at import, because FastAPI
special-cases the Request type by `lenient_issubclass` and a `Union` fails it.
The unit suite asserts injection against FastAPI's own `get_dependant`, which is
the mechanism; this file asserts the OUTCOME, end to end, so the two failures
that would look identical from inside the unit suite —

    the header is never injected           -> nothing suppressed, table fills
    the header is injected and honoured    -> nothing written

are distinguished by the only witness that can tell them apart: a client that
actually sent one.

BOTH SINKS, BOTH DIRECTIONS. Four tests: `/search` writes and does not write,
`/typeahead` votes and does not vote. The negative half is load-bearing on its
own — a channel that suppresses everything would pass every "did not write"
assertion in the repo and would silently drain the warm head to nothing.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

HARNESS = {"X-Bainluck-Origin": "harness"}


async def _drain_search_log_tasks():
    """Await every in-flight fire-and-forget search-log task.

    Without this the assertions race the event loop: the response returns before
    the dispatched task has run, so an unsuppressed write would read as a
    suppressed one and the whole file would pass for the wrong reason.
    """
    from app.routes.events import _SEARCH_LOG_TASKS

    for _ in range(50):
        pending = [t for t in list(_SEARCH_LOG_TASKS) if not t.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)


# ---------------------------------------------------------------------------
# /search — the sink that elects the 40-slot head
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_declared_harness_request_writes_no_row(client):
    """THE SHIP, over HTTP. RED before LAT-P118.

    `cremonese` is the term the production census caught holding warm slot 40 of
    40 on 42 harness votes, so it is the query used here rather than a neutral
    one — the test names the incident it prevents.
    """
    with patch(
        "app.routes.events._log_search_query", new_callable=AsyncMock
    ) as mock_log:
        resp = await client.get(
            "/api/events/search?q=cremonese", headers=HARNESS
        )
        assert resp.status_code == 200
        await _drain_search_log_tasks()

    assert mock_log.await_count == 0, (
        "a request that declared itself machine traffic still wrote a "
        "search_query_logs row — the header never reached the guard"
    )


@pytest.mark.asyncio
async def test_an_ordinary_request_still_writes_its_row(client):
    """The complement, and the one that proves the test above means anything.

    A suppression that suppresses everything passes every negative assertion in
    the repo while draining the head to nothing. The two tests are a pair.
    """
    with patch(
        "app.routes.events._log_search_query", new_callable=AsyncMock
    ) as mock_log:
        resp = await client.get("/api/events/search?q=cremonese")
        assert resp.status_code == 200
        await _drain_search_log_tasks()

    assert mock_log.await_count == 1, (
        "an ordinary search stopped being counted — the head can no longer "
        "learn what people type"
    )


@pytest.mark.asyncio
async def test_an_explicit_user_origin_still_writes_its_row(client):
    """`user` over the wire, from a client that might title-case it."""
    with patch(
        "app.routes.events._log_search_query", new_callable=AsyncMock
    ) as mock_log:
        resp = await client.get(
            "/api/events/search?q=cremonese",
            headers={"X-Bainluck-Origin": "User"},
        )
        assert resp.status_code == 200
        await _drain_search_log_tasks()

    assert mock_log.await_count == 1, (
        "an explicit `user` origin was suppressed over HTTP"
    )


# ---------------------------------------------------------------------------
# /typeahead — the other half of the same head, and the harder injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_declared_harness_typeahead_call_casts_no_vote(client):
    """The route whose `request` parameter is the one FastAPI had to be proved on.

    Patching `app.utils.search_trending.record_query` rather than Redis:
    `_record_trending` imports it inside the function, so this is the exact
    symbol the route reaches for, and a miss here cannot be confused with a
    Redis double that quietly swallowed the call.
    """
    with patch("app.utils.search_trending.record_query") as mock_vote:
        resp = await client.get(
            "/api/events/typeahead?q=cremonese", headers=HARNESS
        )
        assert resp.status_code == 200

    assert mock_vote.call_count == 0, (
        "a probe that declared itself machine traffic voted into "
        "search:trending:24h — the rule has two consumers and one verdict "
        "(gotcha #128)"
    )


@pytest.mark.asyncio
async def test_an_ordinary_typeahead_call_still_votes(client):
    """The complement on the second sink. `/typeahead` supplies half the head."""
    with patch("app.utils.search_trending.record_query") as mock_vote:
        resp = await client.get("/api/events/typeahead?q=cremonese")
        assert resp.status_code == 200

    assert mock_vote.call_count == 1, (
        "an ordinary keystroke stopped voting — the mirror of #2117, arrived "
        "at by tidying"
    )
