"""The I/O half of the settlement-truth capture: ask the source, keep the status.

Queue 389 Item 1 (#2077). ``app.utils.settlement_truth`` decides what an answer
MEANS; this module's only job is to obtain that answer without destroying the
information the classifier needs.

WHY THIS DOES NOT REUSE THE EXISTING CLIENTS
--------------------------------------------

``KalshiAPIService.get_market`` and friends return ``Optional[dict]``. That return
type cannot carry the distinction the capture is built on:

    async def get_market(self, ticker) -> Optional[dict]:
        \"\"\"Get a single market by ticker. Returns None only for 404.\"\"\"
        ...
        except Exception:
            ...
            return None          # <- 429, 503, timeout, DNS failure, all -> None

The docstring says "None only for 404"; the body says otherwise. That is gotcha #36
verbatim, and it is not a defect worth routing around at the call site — a caller
holding ``None`` has already lost the fact it needed. So the probe issues its own
requests and hands the classifier **the status code and the body, separately**,
including for the failure paths. ``-1`` is reserved for "no HTTP response at all"
(timeout, connection error), which the classifier maps to ``TRANSPORT_ERROR``.

This module is deliberately thin. Everything that could be wrong about a *reading*
lives in the pure classifier, where it is testable without a network.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.utils.settlement_truth import (
    Disposition,
    ProbeOutcome,
    classify_kalshi,
    classify_polymarket,
)

logger = logging.getLogger(__name__)

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

#: Gamma rejects the default urllib/httpx agent with 403 (C-WINNER-TRUTH-2 lost 9
#: of 30 probes to this before re-probing with a browser agent).
_UA = "Mozilla/5.0 (compatible; bainluck-settlement-capture/1)"

#: Bodies are stored raw (constraint (a)), but a runaway payload must not become a
#: row-size problem. Truncation is RECORDED rather than silent — a reader must be
#: able to tell a short body from a clipped one.
MAX_RAW_CHARS = 20_000


def _clip(body: Any) -> Any:
    """Return the body, or a marked stand-in when it is too large to store."""
    import json

    if body is None:
        return None
    try:
        encoded = json.dumps(body)
    except (TypeError, ValueError):
        return {"_unserialisable": True, "_repr": repr(body)[:MAX_RAW_CHARS]}
    if len(encoded) <= MAX_RAW_CHARS:
        return body
    return {
        "_truncated": True,
        "_original_chars": len(encoded),
        "_head": encoded[:MAX_RAW_CHARS],
    }


async def _get(
    client: httpx.AsyncClient, url: str, **params: Any
) -> tuple[int, Any]:
    """One request. Returns ``(status, parsed_body)`` and NEVER raises.

    ``-1`` means no HTTP response was obtained at all. The distinction between
    ``-1`` and ``503`` matters to nobody today — both are ``TRANSPORT_ERROR`` — but
    collapsing them at the source is how the next reader loses the ability to tell
    "the service answered badly" from "we never reached it".
    """
    try:
        response = await client.get(url, params=params or None, headers={"User-Agent": _UA})
    except Exception as exc:  # noqa: BLE001 - deliberately broad; recorded, not swallowed
        logger.debug("settlement probe transport failure for %s: %s", url, exc)
        return -1, None
    try:
        return response.status_code, response.json()
    except Exception:  # noqa: BLE001 - a 200 that is not JSON is still a status
        return response.status_code, None


async def probe_kalshi(ticker: str, client: httpx.AsyncClient) -> ProbeOutcome:
    """Kalshi protocol: market, then the event iff the market 404s.

    The event call is not a retry — it is the *second signal* gotcha #53 requires.
    A bare market 404 cannot distinguish Kalshi's retention purge (their fact) from
    a wrong ``external_id`` (our bug), and those route to completely different
    owners. The event call is skipped when the market answered, so the cost is one
    request for the common case.

    The event is asked for under the ticker we hold before its stripped parent —
    see the comment below; getting that order wrong turned every purge into a
    fabricated ingestion defect.
    """
    market_status, market_body = await _get(client, f"{KALSHI_BASE}/markets/{ticker}")
    if market_status != 404:
        return classify_kalshi(market_status, _clip(market_body))

    # ASK FOR THE TICKER WE HOLD BEFORE ASKING FOR ITS PARENT.
    #
    # ``external_id`` is not uniformly a market ticker. Measured against production
    # 2026-08-24: of the 24,739-row at-risk Kalshi cohort, ~96% carry exactly one
    # hyphen — the EVENT shape (``KXMLBEXTRAS-26JUN171400SFATL``), not the market
    # shape (``EVENT-SUFFIX``). Stripping the last segment off an event ticker
    # yields the bare SERIES (``KXMLBEXTRAS``), which 404s for every event that ever
    # existed, so the ladder in ``classify_kalshi`` reached ``NOT_FOUND`` — "suspect
    # our external_id" — for rows whose event Kalshi still serves at 200.
    #
    # That is not a cosmetic mislabel. ``NOT_FOUND`` is TERMINAL: one sweep would
    # have permanently excluded ~1,074 of the 1,096 terminal-bucket rows from every
    # future probe, recording a retention loss (their clock) as an ingestion defect
    # (our bug) — the exact conflation this module exists to prevent, written to the
    # one population that cannot be re-asked later.
    #
    # Verified against the live public API on 2026-08-24:
    #   GET /events/KXMLBEXTRAS-26JUN171400SFATL -> 200, markets: []  (PURGED)
    #   GET /events/KXMLBEXTRAS                  -> 404               (NOT_FOUND)
    #
    # So try the id as given first. The parent lookup stays as the fallback for the
    # genuine market-ticker shape, and only a 404 from BOTH is allowed to mean
    # "no such thing". Cost is unchanged for the ~96% and one extra call otherwise.
    event_status, event_body = await _get(client, f"{KALSHI_BASE}/events/{ticker}")
    if event_status == 404:
        parent = _kalshi_event_ticker(ticker)
        if parent != ticker:
            event_status, event_body = await _get(client, f"{KALSHI_BASE}/events/{parent}")

    return classify_kalshi(
        market_status, _clip(market_body), event_status, _clip(event_body)
    )


def _kalshi_event_ticker(market_ticker: str) -> str:
    """The parent event ticker of a MARKET ticker — a fallback, never the first ask.

    Kalshi market tickers are ``EVENT-SUFFIX``, so the event is everything before
    the last hyphen-delimited segment. **This is only correct when the input really
    is a market ticker.** Applied to an event ticker it returns the series, which
    always 404s; ``probe_kalshi`` therefore asks for the unmodified ticker first and
    only falls back here. Callers must not treat the result as "the event ticker".
    """
    if "-" not in market_ticker:
        return market_ticker
    head, _, tail = market_ticker.rpartition("-")
    return head or market_ticker


async def probe_polymarket(
    condition_or_event_id: str, client: httpx.AsyncClient
) -> ProbeOutcome:
    """Gamma first, then the CLOB as an INDEPENDENT corroborator.

    The CLOB is consulted whenever Gamma failed to produce a settlement — not only
    on an empty answer — because Gamma's ``200 []`` and its "present but undecided"
    are both non-answers about a market that may well have settled. ``tokens[].winner``
    survives after the Gamma record ages out (#989 / L2-32), which is what makes the
    pair genuinely two stores rather than two reads of one.

    **NOT part of the weekly sweep.** C-PM-RETENTION-1 (2026-08-21) measured **no
    Polymarket cliff at all** — 0 of 70 probed records gone, reachable from 30 days
    to 3.66 years — so Polymarket's 250,526 missing carry no retention deadline and
    are handled as one bulk re-poll job rather than a race. This function stays here
    because that bulk job needs exactly this classifier; only the *urgency* changed.

    **Channel preference, from the same measurement:** the ``/events/{id}`` probe is
    AUTHORITATIVE and the ``?condition_ids=`` lookup is UNRELIABLE — it answers
    ``200 []`` for conditions the event probe resolves fine. So a hex condition id is
    tried on Gamma, but an empty answer from it is treated as the non-fact it is
    (``AMBIGUOUS_EMPTY``) rather than as evidence, and the CLOB is what actually
    settles the question for that shape.
    """
    is_hex = condition_or_event_id.startswith("0x")
    if is_hex:
        gamma_status, gamma_body = await _get(
            client, f"{GAMMA_BASE}/markets", condition_ids=condition_or_event_id
        )
    else:
        gamma_status, gamma_body = await _get(
            client, f"{GAMMA_BASE}/events/{condition_or_event_id}"
        )

    first = classify_polymarket(gamma_status, _clip(gamma_body))
    if first.disposition is Disposition.SETTLED:
        return first

    # Only a hex condition id addresses the CLOB. A numeric Gamma event id does
    # not, so there is no second channel for it and the honest answer stays
    # whatever Gamma's shape supports — recorded as such rather than guessed.
    if not is_hex:
        return first

    clob_status, clob_body = await _get(
        client, f"{CLOB_BASE}/markets/{condition_or_event_id}"
    )
    return classify_polymarket(
        gamma_status, _clip(gamma_body), clob_status, _clip(clob_body)
    )


async def probe(source: str, external_id: str, client: httpx.AsyncClient) -> ProbeOutcome:
    """Dispatch on source. An unknown source is an error, never a silent skip."""
    if source == "kalshi":
        return await probe_kalshi(external_id, client)
    if source == "polymarket":
        return await probe_polymarket(external_id, client)
    return ProbeOutcome(
        Disposition.TRANSPORT_ERROR,
        reason=f"no settlement probe implemented for source {source!r}",
        channels=((source, None),),
    )


def make_client(timeout_s: float = 20.0) -> httpx.AsyncClient:
    """A client with a REAL timeout.

    A probe without one can hang the sweep's whole budget on a single market, which
    is the shape of gotcha #39 one layer out: the blocked call becomes the reason
    nothing else gets captured before the cliff.
    """
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=10.0),
        follow_redirects=True,
        limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
    )


async def probe_many(
    items: list[tuple[int, str, str]],
    concurrency: int = 4,
    client: httpx.AsyncClient | None = None,
) -> list[tuple[int, ProbeOutcome]]:
    """Probe ``(market_id, source, external_id)`` triples with bounded concurrency.

    Per-item isolation is mandatory (gotcha #42): one market that throws must not
    empty the sweep. A failure becomes a ``TRANSPORT_ERROR`` row — recorded, so the
    market is re-probed next sweep rather than silently dropped from the burn-down.
    """
    owns_client = client is None
    client = client or make_client()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: list[tuple[int, ProbeOutcome]] = []

    async def _one(market_id: int, source: str, external_id: str) -> None:
        async with semaphore:
            try:
                outcome = await probe(source, external_id, client)
            except Exception as exc:  # noqa: BLE001 - isolation, per gotcha #42
                logger.warning("settlement probe raised for market %s: %s", market_id, exc)
                outcome = ProbeOutcome(
                    Disposition.TRANSPORT_ERROR,
                    reason=f"probe raised {type(exc).__name__}: {exc}",
                    channels=((source, None),),
                )
            results.append((market_id, outcome))

    try:
        await asyncio.gather(*(_one(m, s, e) for m, s, e in items))
    finally:
        if owns_client:
            await client.aclose()
    return results
