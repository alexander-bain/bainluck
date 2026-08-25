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
import contextvars
import logging
import os
import time as _time
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

#: 429 retry shape, modelled on ``kalshi_api.py``'s ``get_events`` (#969): capped,
#: never unbounded, and never allowed to sleep past a caller's deadline. Four
#: attempts at 5/10/10 s is at most 25 s of sleeping per request, and that only
#: when nothing clamps it.
_MAX_429_ATTEMPTS = 4
_BACKOFF_STEP_S = 5.0
_BACKOFF_CAP_S = 10.0

#: Pacing bounds. The pacer costs NOTHING while the source is healthy — the
#: interval sits at zero and ``wait_turn`` returns without sleeping — and only
#: opens up once a 429 has actually been seen.
#:
#: The ceiling is deliberately modest. The brake exists to stop the sweep
#: *storming* a source that said no; it must not become the reason the sweep
#: misses its own budget. At 0.5 s the paced floor is 2 req/s — slow enough that
#: Kalshi stops seeing a flood, fast enough that a 2,000-row budget is still
#: reachable inside a sweep window. A 2 s ceiling was tried first and is wrong in
#: both directions: it stalls the burn-down, and the deadline clamp then converts
#: the stall into a batch of RATE_LIMITED rows — a brake that manufactures the
#: outcome it was added to prevent.
_PACE_FIRST_PENALTY_S = 0.1
_PACE_WIDEN_FACTOR = 2.0
_PACE_RELAX_FACTOR = 0.5
_PACE_INTERVAL_CEIL_S = 0.5
#: Below this the interval is snapped to zero rather than decaying forever.
_PACE_FLOOR_S = 0.01


def _kalshi_api_key() -> str | None:
    """Read at CALL time, never at import.

    An import-time read bakes the key's presence into the module the first time
    anything imports it, which makes the credential untestable and makes a
    Heroku config change require a dyno restart to take effect.
    """
    key = os.getenv("KALSHI_API_KEY")
    return key or None


def _headers_for(url: str) -> dict[str, str]:
    """Request headers for ``url`` — and the credential goes to Kalshi ONLY.

    #2174: the sweep probed Kalshi unauthenticated while ``KALSHI_API_KEY`` sat in
    Heroku config, so it drew the anonymous rate limit and spent its window
    collecting 429s. C-KALSHI-RETENTION-1 measured the cost directly: of 3,095
    probes, **1,317 (42.6%) came back rate-limited** — more than were settled and
    purged combined. The window is not short because the source is slow; it is
    short because we were queueing behind every other anonymous caller.

    **Scoped by host on purpose.** ``_get`` is shared by the Kalshi, Gamma and CLOB
    channels, so an unscoped header would send a Kalshi bearer token to two
    unrelated third parties on every Polymarket probe. That is a credential leak
    with no upside — neither host reads it — and it is the kind of thing that is
    obvious here and invisible at the call site. G5 asks that the probe use the
    credential when present; it does not ask that everyone else receive it.
    """
    headers = {"User-Agent": _UA}
    if url.startswith(KALSHI_BASE):
        key = _kalshi_api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    return headers


def _backoff_delay(
    attempt: int, deadline: float | None = None, now: float | None = None
) -> float:
    """Seconds to sleep after ``attempt`` (0-based) has drawn a 429.

    Pure, so the two properties that matter are testable without a clock:

    * **capped** — ``min(5*(attempt+1), 10)``, so no burst can grow without bound;
    * **deadline-clamped** — never returns more than the time actually remaining,
      and returns ``0.0`` once the deadline has passed, which the caller reads as
      "stop retrying" rather than "sleep zero and hammer".
    """
    delay = min(_BACKOFF_STEP_S * (attempt + 1), _BACKOFF_CAP_S)
    if deadline is None:
        return delay
    remaining = deadline - (_time.monotonic() if now is None else now)
    return max(0.0, min(delay, remaining))


class RatePacer:
    """A shared brake on the ISSUE RATE, not just on the in-flight count.

    G7's point, and it is a real gap rather than a belt-and-braces ask: a 429 comes
    back in ~20 ms, so a semaphore of N permits does not bound requests per second
    once the source is refusing — it bounds them to N *concurrent*, which at 20 ms
    a piece is ~50N req/s of pure rate-limit traffic. Per-request backoff alone
    does not close it either, because each coroutine backs off on its OWN clock and
    the other N-1 keep firing into a source that has already said stop.

    So the interval is shared: one 429 anywhere widens the gap for everyone, and
    successes decay it back toward zero. While the source is healthy the interval
    IS zero and this class does nothing measurable.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._interval = 0.0
        self._next_at = 0.0

    @property
    def interval(self) -> float:
        """Current spacing between request starts, in seconds. Read-only, for tests."""
        return self._interval

    async def wait_turn(self, deadline: float | None = None) -> bool:
        """Reserve this request's slot. ``False`` means the deadline landed first.

        The slot is reserved under the lock and slept for OUTSIDE it — holding the
        lock across the sleep would serialise every worker onto one queue and turn
        a pacer into a mutex.
        """
        async with self._lock:
            now = _time.monotonic()
            start_at = max(now, self._next_at)
            self._next_at = start_at + self._interval
        delay = start_at - _time.monotonic()
        if delay <= 0:
            return True
        if deadline is not None and start_at > deadline:
            return False
        await asyncio.sleep(delay)
        return True

    def penalise(self) -> None:
        """A 429 was seen. Widen the shared gap, capped."""
        widened = max(_PACE_FIRST_PENALTY_S, self._interval * _PACE_WIDEN_FACTOR)
        self._interval = min(_PACE_INTERVAL_CEIL_S, widened)

    def relax(self) -> None:
        """A non-429 answer. Decay back toward free-running."""
        relaxed = self._interval * _PACE_RELAX_FACTOR
        self._interval = 0.0 if relaxed < _PACE_FLOOR_S else relaxed


#: Installed by ``probe_many`` so ``_get`` can find the pacer and the deadline
#: without threading two parameters through ``probe`` and ``probe_kalshi``.
#: ContextVars are copied into each task at creation, so the tasks ``gather``
#: spawns below inherit whatever ``probe_many`` set before spawning them — and a
#: caller that never sets them gets today's behaviour exactly.
_pacer_var: contextvars.ContextVar[RatePacer | None] = contextvars.ContextVar(
    "settlement_probe_pacer", default=None
)
_deadline_var: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "settlement_probe_deadline", default=None
)


def install_pacer(pacer: RatePacer) -> contextvars.Token:
    """Share ``pacer`` with every ``_get`` in this task and its children.

    Exported because ``settlement_sweep_runner`` does NOT call ``probe_many`` — it
    has its own concurrency loop — and a brake wired only into ``probe_many``
    would miss the one path production takes. Set BEFORE spawning the tasks:
    each task copies the context at creation.
    """
    return _pacer_var.set(pacer)


def install_deadline(deadline: float | None) -> contextvars.Token:
    """Bound all retrying in this task at a ``time.monotonic()`` value."""
    return _deadline_var.set(deadline)


def reset_pacer(token: contextvars.Token) -> None:
    _pacer_var.reset(token)


def reset_deadline(token: contextvars.Token) -> None:
    _deadline_var.reset(token)


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
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any] | None = None,
    *,
    deadline: float | None = None,
) -> tuple[int, Any]:
    """One logical request, including its 429 retries. NEVER raises.

    Returns ``(status, parsed_body)``. ``-1`` means no HTTP response was obtained
    at all. The distinction between ``-1`` and ``503`` matters to nobody today —
    both are ``TRANSPORT_ERROR`` — but collapsing them at the source is how the
    next reader loses the ability to tell "the service answered badly" from "we
    never reached it".

    **On 429 this retries with a capped, deadline-clamped backoff** (#2174). What
    it must never do is give up in a way that looks like a fact: every exit here
    returns either ``429`` (``RATE_LIMITED``) or ``-1`` (``TRANSPORT_ERROR``), and
    both are ``is_retryable()``. A deadline that fires mid-retry therefore costs a
    row one sweep, never its place in the cohort — the row comes back next pass.
    Returning something terminal here would delete it from the burn-down instead,
    which is the same shape of harm as the ``NOT_FOUND`` bug this module's tests
    were written for.

    ``deadline`` is a ``time.monotonic()`` value and falls back to the one
    ``probe_many`` installed, so the sweep's budget binds even though ``probe`` and
    ``probe_kalshi`` never mention it.
    """
    if deadline is None:
        deadline = _deadline_var.get()
    pacer = _pacer_var.get()

    status, body = -1, None
    for attempt in range(_MAX_429_ATTEMPTS):
        if deadline is not None and _time.monotonic() >= deadline:
            break
        if pacer is not None and not await pacer.wait_turn(deadline):
            break

        try:
            response = await client.get(
                url, params=params or None, headers=_headers_for(url)
            )
        except Exception as exc:  # noqa: BLE001 - deliberately broad; recorded, not swallowed
            logger.debug("settlement probe transport failure for %s: %s", url, exc)
            return -1, None

        status = response.status_code
        try:
            body = response.json()
        except Exception:  # noqa: BLE001 - a 200 that is not JSON is still a status
            body = None

        if status != 429:
            if pacer is not None:
                pacer.relax()
            return status, body

        if pacer is not None:
            pacer.penalise()
        if attempt == _MAX_429_ATTEMPTS - 1:
            break
        delay = _backoff_delay(attempt, deadline)
        if delay <= 0:
            break
        await asyncio.sleep(delay)

    return status, body


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
            client,
            f"{GAMMA_BASE}/markets",
            {"condition_ids": condition_or_event_id},
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
    deadline: float | None = None,
    pacer: RatePacer | None = None,
) -> list[tuple[int, ProbeOutcome]]:
    """Probe ``(market_id, source, external_id)`` triples with bounded concurrency.

    Per-item isolation is mandatory (gotcha #42): one market that throws must not
    empty the sweep. A failure becomes a ``TRANSPORT_ERROR`` row — recorded, so the
    market is re-probed next sweep rather than silently dropped from the burn-down.

    **The semaphore is not the rate limit** (#2174 / G7). It bounds how many
    requests are in flight; under sustained 429 — which answers in ~20 ms — that
    is not a bound on requests per second at all. So a single :class:`RatePacer`
    is shared by every worker here: the first 429 anywhere widens the gap for all
    of them, and successes decay it back to zero. Pass ``pacer`` to observe it.

    ``deadline`` is a ``time.monotonic()`` value bounding the whole batch's
    retrying, so one rate-limited stretch cannot eat the sweep's budget.
    """
    owns_client = client is None
    client = client or make_client()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    results: list[tuple[int, ProbeOutcome]] = []
    # Set BEFORE the tasks are created: each task copies the context at creation,
    # so setting it after ``gather`` starts would reach none of them.
    pacer_token = _pacer_var.set(pacer if pacer is not None else RatePacer())
    deadline_token = _deadline_var.set(deadline)

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
        # Reset so a second batch in the same task does not inherit the first
        # batch's brake or, worse, its expired deadline.
        _pacer_var.reset(pacer_token)
        _deadline_var.reset(deadline_token)
        if owns_client:
            await client.aclose()
    return results
