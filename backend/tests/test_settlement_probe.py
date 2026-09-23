"""The I/O half of the settlement capture, tested without a network.

Queue 396 (#2077). ``app/utils/settlement_truth`` — the pure classifier — already had
a suite; ``app/services/settlement_probe`` had none, and the defect these tests exist
for lived entirely in the untested half: the classifier's ladder was correct, and it
was fed the wrong request.

THE DEFECT, SO A LATER READER DOES NOT "SIMPLIFY" IT BACK
----------------------------------------------------------

``_kalshi_event_ticker`` strips the last hyphen-delimited segment to get a market
ticker's parent event. Its old docstring claimed a caller passing an EVENT ticker
"already gets the right thing" — false for any event ticker containing a hyphen,
which is all of them. ``KXMLBEXTRAS-26JUN171400SFATL`` became ``KXMLBEXTRAS``, a bare
series that 404s, so a purged-but-present event classified as ``NOT_FOUND``
("suspect our external_id") instead of ``PURGED`` ("retention took it").

Measured against production 2026-08-24: ~96% of the 24,739-row at-risk Kalshi cohort
carries the event shape, including 1,074 of the 1,096 rows in the terminal bucket.
``NOT_FOUND`` is terminal, so one sweep would have permanently excluded them while
blaming our own ingestion for Kalshi's clock.

Live confirmation on the same day:
    GET /events/KXMLBEXTRAS-26JUN171400SFATL -> 200, markets: []
    GET /events/KXMLBEXTRAS                  -> 404
"""

from __future__ import annotations

import httpx
import pytest

from app.services.settlement_probe import (
    KALSHI_BASE,
    _kalshi_event_ticker,
    probe_kalshi,
)
from app.utils.settlement_truth import Disposition

#: The real specimen. An EVENT ticker stored in ``futures_markets.external_id``.
EVENT_TICKER = "KXMLBEXTRAS-26JUN171400SFATL"
#: What stripping its last segment produces — a series, which Kalshi never serves.
SERIES_TICKER = "KXMLBEXTRAS"


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _json(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body if body is not None else {})


@pytest.mark.asyncio
async def test_event_shaped_external_id_reads_as_purged_not_not_found():
    """The regression. Event exists with markets:[] -> PURGED, and the series is never
    allowed to be the last word."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == f"/trade-api/v2/markets/{EVENT_TICKER}":
            return _json(404, {"error": {"code": "not_found"}})
        if request.url.path == f"/trade-api/v2/events/{EVENT_TICKER}":
            return _json(200, {"event": {"title": "San Francisco vs Atlanta"}, "markets": []})
        if request.url.path == f"/trade-api/v2/events/{SERIES_TICKER}":
            return _json(404, {"error": {"code": "not_found"}})
        raise AssertionError(f"unexpected request: {request.url}")

    async with _client(handler) as client:
        outcome = await probe_kalshi(EVENT_TICKER, client)

    assert outcome.disposition is Disposition.PURGED, outcome.reason
    # The series lookup must not even happen: the id we hold answered.
    assert f"/trade-api/v2/events/{SERIES_TICKER}" not in seen
    assert seen == [
        f"/trade-api/v2/markets/{EVENT_TICKER}",
        f"/trade-api/v2/events/{EVENT_TICKER}",
    ]


@pytest.mark.asyncio
async def test_market_shaped_external_id_still_falls_back_to_its_parent():
    """The fallback the strip was written for stays working: a genuine market ticker
    whose event only answers under the stripped parent."""
    market_ticker = f"{EVENT_TICKER}-T8.5"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/trade-api/v2/markets/{market_ticker}":
            return _json(404, {"error": {"code": "not_found"}})
        if request.url.path == f"/trade-api/v2/events/{market_ticker}":
            return _json(404, {"error": {"code": "not_found"}})
        if request.url.path == f"/trade-api/v2/events/{EVENT_TICKER}":
            return _json(200, {"event": {"title": "Extra Innings"}, "markets": []})
        raise AssertionError(f"unexpected request: {request.url}")

    async with _client(handler) as client:
        outcome = await probe_kalshi(market_ticker, client)

    assert outcome.disposition is Disposition.PURGED, outcome.reason


@pytest.mark.asyncio
async def test_both_lookups_404_is_the_only_route_to_not_found():
    """NOT_FOUND is terminal, so it must require the source to have denied BOTH ids."""

    def handler(request: httpx.Request) -> httpx.Response:
        return _json(404, {"error": {"code": "not_found"}})

    async with _client(handler) as client:
        outcome = await probe_kalshi(EVENT_TICKER, client)

    assert outcome.disposition is Disposition.NOT_FOUND


@pytest.mark.asyncio
async def test_a_throttled_event_lookup_never_becomes_not_found():
    """Gotcha #36: a 429 is not an answer about the market. It must stay retryable
    rather than being written off as a bad external_id."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/trade-api/v2/markets/"):
            return _json(404, {"error": {"code": "not_found"}})
        return _json(429, {"error": {"code": "rate_limited"}})

    async with _client(handler) as client:
        outcome = await probe_kalshi(EVENT_TICKER, client)

    assert outcome.disposition is Disposition.RATE_LIMITED
    assert outcome.disposition not in {
        Disposition.NOT_FOUND,
        Disposition.PURGED,
        Disposition.SETTLED,
    }


@pytest.mark.asyncio
async def test_a_live_market_answers_in_one_call():
    """The event call stays skipped when the market answered — the cost claim in the
    docstring is a claim about behaviour, so it gets a test."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return _json(
            200,
            {"market": {"ticker": EVENT_TICKER, "status": "settled", "result": "yes"}},
        )

    async with _client(handler) as client:
        outcome = await probe_kalshi(EVENT_TICKER, client)

    assert outcome.disposition is Disposition.SETTLED
    assert len(calls) == 1


def test_the_strip_helper_is_documented_as_a_fallback_only():
    """It is still correct for what it is for, and still wrong for an event ticker —
    which is why the caller may not lead with it."""
    assert _kalshi_event_ticker(f"{EVENT_TICKER}-T8.5") == EVENT_TICKER
    # The trap, asserted so nobody re-adopts it as "the event ticker".
    assert _kalshi_event_ticker(EVENT_TICKER) == SERIES_TICKER
    assert _kalshi_event_ticker("NOHYPHEN") == "NOHYPHEN"


def test_base_url_is_the_public_elections_host():
    assert KALSHI_BASE == "https://api.elections.kalshi.com/trade-api/v2"


# ---------------------------------------------------------------------------
# Clipping is a STORAGE concern and must not reach the parse (#2077)
# ---------------------------------------------------------------------------
#
# ``_clip`` replaces any body over ``MAX_RAW_CHARS`` with a ``_head`` STRING. That
# stand-in has no ``markets`` key, so a classifier handed the clipped body sees no
# legs — and the bodies that trip it are exactly the settled boards the per-leg
# reader exists for. Measured against the venue 2026-09-22:
#
#     GET /events/KXNASDAQ100U-26AUG17H1200 -> 200, 400 legs, 812,850 chars
#
# Forty times the ceiling. The probe therefore hands over the full body and passes
# ``clip=`` for the raw record.


def _oversized_board(ticker: str, legs: int = 400) -> dict:
    """An event body shaped like the real one and comfortably past MAX_RAW_CHARS.

    Padded per leg rather than by one big field, because a single fat key would
    be clipped by a reader that still parsed the legs correctly — the padding has
    to live where the real payload's bulk lives.
    """
    return {
        "event": {"title": "Nasdaq close", "category": "Financials"},
        "markets": [
            {
                "ticker": f"{ticker}-T{27999 + i}.99",
                "status": "finalized",
                "result": "yes" if i % 2 == 0 else "no",
                "rules_primary": "Resolves to the closing value of the index. " * 12,
            }
            for i in range(legs)
        ],
    }


@pytest.mark.asyncio
async def test_a_board_far_past_the_clip_ceiling_is_still_graded_per_leg():
    """The regression: clipping before the parse blinds the reader to big boards."""
    import json

    from app.services.settlement_probe import MAX_RAW_CHARS

    ticker = "KXNASDAQ100U-26AUG17H1200"
    body = _oversized_board(ticker)
    assert len(json.dumps(body)) > MAX_RAW_CHARS * 5, "specimen must exceed the ceiling"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/trade-api/v2/markets/{ticker}":
            return _json(404, {"error": {"code": "not_found"}})
        if request.url.path == f"/trade-api/v2/events/{ticker}":
            return _json(200, body)
        raise AssertionError(f"unexpected request: {request.url}")

    async with _client(handler) as client:
        outcome = await probe_kalshi(ticker, client)

    assert outcome.disposition is Disposition.SETTLED_PER_LEG
    assert len(outcome.leg_claims) == 400
    assert outcome.leg_claims[0].external_id == f"{ticker}-T27999.99"
    assert sum(1 for leg in outcome.leg_claims if leg.is_winner) == 200


@pytest.mark.asyncio
async def test_the_stored_body_is_still_clipped():
    """The other half, and the reason ``clip`` was not simply deleted.

    Without this a reader "fixes" the test above by dropping the truncator, and
    every capture row starts carrying 812KB of raw payload.
    """
    import json

    from app.services.settlement_probe import MAX_RAW_CHARS

    ticker = "KXNASDAQ100U-26AUG17H1200"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/trade-api/v2/markets/{ticker}":
            return _json(404, {"error": {"code": "not_found"}})
        return _json(200, _oversized_board(ticker))

    async with _client(handler) as client:
        outcome = await probe_kalshi(ticker, client)

    stored = outcome.raw["kalshi_event"]
    assert stored.get("_truncated") is True
    assert len(json.dumps(stored)) < MAX_RAW_CHARS * 2


@pytest.mark.asyncio
async def test_a_small_board_is_stored_whole():
    """The control for the clause above: clipping only fires past the ceiling."""
    ticker = "KXATPDOUBLES-26JUL30CASGLADOUREB"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/trade-api/v2/markets/{ticker}":
            return _json(404, {"error": {"code": "not_found"}})
        return _json(
            200,
            {"markets": [{"ticker": f"{ticker}-CASGLA", "status": "finalized", "result": "scalar"}]},
        )

    async with _client(handler) as client:
        outcome = await probe_kalshi(ticker, client)

    assert "_truncated" not in outcome.raw["kalshi_event"]
    assert outcome.raw["kalshi_event"]["markets"][0]["result"] == "scalar"
