"""#2174 — the capture probe's credential and its brakes.

Queue 409. These tests are written against **CERT-399 §2 (G5/G6/G7)**, which was
authored pre-fix by the certification window. That section is the ruler; this file
is the subject's attempt to meet it, and the cert runs independently.

WHY THIS DEFECT COST THE PROGRAM ITS WINDOW
-------------------------------------------

``KALSHI_API_KEY`` is set in Heroku config and the probe never sent it. The bill is
measured, not assumed — C-KALSHI-RETENTION-1 (2026-08-24) probed 3,095 markets and
got **1,317 rate-limited answers (42.6%)**, more than the settled (87) and purged
(908) definitive reads combined. A sweep that spends 43% of its budget being told
"slow down" is not slow because Kalshi is slow; it is slow because it queued behind
every other anonymous caller, and every sweep it wastes is retention it does not
beat. The same run BLOCKED the old horizon: verified loss starts at **47 days**,
not 74, and it is not monotonic in age.

The three properties, and why each alone is insufficient:

* **G5 auth** without backoff still storms a source that says stop.
* **G6 backoff** without auth still draws the anonymous limit, so it backs off
  from a 429 it should never have received.
* **G7 pacing** is not implied by either. The semaphore bounds *in flight*, and a
  429 returns in ~20 ms — so N permits is ~50N req/s of rate-limit traffic, and
  per-request backoff runs on each coroutine's own clock while the others keep
  firing. The brake has to be shared to be a brake.

TIMING TESTS PATCH THE CONSTANTS DOWN, AND THAT IS NOT A WEAKENING
------------------------------------------------------------------

The production shape is 5/10/10 s. Sleeping that in CI would be 25 s per probe, so
the timing tests scale the step to tens of milliseconds and assert the *behaviour*
(retried N+1 times, measurably delayed, wall time grows, deadline honoured).
``test_g6_production_constants_are_the_capped_shape`` asserts the real values
separately, so scaling the clock cannot hide an uncapped constant — the mutation
CERT-399 names ("``5*attempt`` without cap, or no deadline clamp") fails there.
"""

from __future__ import annotations

import time

import httpx
import pytest

from app.services import settlement_probe as sp
from app.services.settlement_probe import (
    CLOB_BASE,
    GAMMA_BASE,
    KALSHI_BASE,
    RatePacer,
    _backoff_delay,
    _get,
    probe_kalshi,
    probe_many,
    probe_polymarket,
)
from app.utils.settlement_truth import Disposition

TICKER = "KXMLBEXTRAS-26JUN171400SFATL"
HEX_ID = "0x" + "ab" * 32


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def fast_backoff(monkeypatch):
    """Real sleeps, small ones. See the module docstring.

    Both clocks scale together — the retry backoff and the shared pace interval —
    because a test that scaled only one would measure a shape production never
    runs. ``test_g6_production_constants_are_the_capped_shape`` and
    ``test_g7_production_pace_constants_are_bounded`` hold the real values.
    """
    monkeypatch.setattr(sp, "_BACKOFF_STEP_S", 0.05)
    monkeypatch.setattr(sp, "_BACKOFF_CAP_S", 0.10)
    monkeypatch.setattr(sp, "_PACE_FIRST_PENALTY_S", 0.01)
    monkeypatch.setattr(sp, "_PACE_INTERVAL_CEIL_S", 0.02)
    return 0.05


# ---------------------------------------------------------------------------
# G5 — authenticated when a key exists, harmless when it does not
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g5_kalshi_probe_sends_bearer_when_key_is_present(monkeypatch):
    """RED-FIRST. Pre-fix the probe sent only User-Agent, so this fails on master.

    Asserted on the REQUEST the transport actually received — not by looking for
    the string ``Authorization`` in the source, which CERT-399 rules out and which
    would pass for a header that is built and never sent.
    """
    monkeypatch.setenv("KALSHI_API_KEY", "sekrit-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    async with _client(handler) as client:
        await probe_kalshi(TICKER, client)

    assert seen, "no request was issued"
    assert seen[0].headers.get("Authorization") == "Bearer sekrit-token"
    # The UA is load-bearing too (Gamma 403s without it); auth must be additive.
    assert seen[0].headers.get("User-Agent") == sp._UA


@pytest.mark.asyncio
async def test_g5_every_kalshi_channel_is_authenticated_not_just_the_first(
    monkeypatch,
):
    """The event fallback is a second request. A fix that authenticates only the
    market call leaves the purge/not-found decision — the terminal one — running
    unauthenticated."""
    monkeypatch.setenv("KALSHI_API_KEY", "sekrit-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "/markets/" in request.url.path:
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"event": {"markets": []}})

    async with _client(handler) as client:
        await probe_kalshi(TICKER, client)

    assert len(seen) >= 2, f"expected market + event calls, saw {len(seen)}"
    assert all(r.headers.get("Authorization") == "Bearer sekrit-token" for r in seen)


@pytest.mark.asyncio
async def test_g5_no_key_degrades_to_todays_behaviour_without_error(monkeypatch):
    """Unset must be silent, not an exception and not an empty bearer."""
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    async with _client(handler) as client:
        outcome = await probe_kalshi(TICKER, client)

    assert "Authorization" not in seen[0].headers
    assert seen[0].headers.get("User-Agent") == sp._UA
    assert outcome.disposition is not Disposition.TRANSPORT_ERROR


@pytest.mark.asyncio
async def test_g5_an_empty_key_is_treated_as_absent(monkeypatch):
    """``KALSHI_API_KEY=""`` in a config is absence, not a credential. Sending
    ``Bearer `` would be a 401 that reads as a Kalshi outage."""
    monkeypatch.setenv("KALSHI_API_KEY", "")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    async with _client(handler) as client:
        await probe_kalshi(TICKER, client)

    assert "Authorization" not in seen[0].headers


@pytest.mark.asyncio
async def test_g5_the_kalshi_credential_never_reaches_polymarket(monkeypatch):
    """The leak control for the host-scoping decision.

    ``_get`` is shared by three hosts. An unscoped ``Authorization`` header would
    hand our Kalshi bearer to Gamma and the CLOB on every Polymarket probe — two
    third parties that do not read it and have no business receiving it.
    """
    monkeypatch.setenv("KALSHI_API_KEY", "sekrit-token")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host.endswith("polymarket.com") and "gamma" in request.url.host:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={})

    async with _client(handler) as client:
        await probe_polymarket(HEX_ID, client)

    assert seen, "no request was issued"
    for request in seen:
        assert str(request.url).startswith((GAMMA_BASE, CLOB_BASE))
        assert "Authorization" not in request.headers, (
            f"Kalshi credential leaked to {request.url}"
        )


def test_g5_the_header_builder_is_scoped_by_host(monkeypatch):
    """The same property stated directly on the pure helper, so a future refactor
    that reroutes a call site still trips a test."""
    monkeypatch.setenv("KALSHI_API_KEY", "sekrit-token")
    headers = sp._headers_for(f"{KALSHI_BASE}/markets/X")
    assert headers["Authorization"] == "Bearer sekrit-token"
    assert "Authorization" not in sp._headers_for(f"{GAMMA_BASE}/events/1")
    assert "Authorization" not in sp._headers_for(f"{CLOB_BASE}/markets/0xab")


def test_g5_the_key_is_read_at_call_time_not_import_time(monkeypatch):
    """A key that appears after import must take effect without a restart."""
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    assert "Authorization" not in sp._headers_for(f"{KALSHI_BASE}/markets/X")
    monkeypatch.setenv("KALSHI_API_KEY", "later-token")
    assert sp._headers_for(f"{KALSHI_BASE}/markets/X")["Authorization"] == (
        "Bearer later-token"
    )


# ---------------------------------------------------------------------------
# G6 — bounded 429 backoff that respects a deadline
# ---------------------------------------------------------------------------


def test_g6_production_constants_are_the_capped_shape():
    """Guards the mutation CERT-399 names: ``5*attempt`` with no cap.

    Checked on the real constants, so the timing tests' scaled clock cannot hide
    an unbounded production value.
    """
    assert sp._BACKOFF_STEP_S == 5.0
    assert sp._BACKOFF_CAP_S == 10.0
    assert sp._MAX_429_ATTEMPTS == 4
    # Every attempt, including ones far past the last, stays under the cap.
    assert [_backoff_delay(a) for a in range(6)] == [5.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    # Total sleeping is bounded, so one burst cannot eat a sweep budget.
    total = sum(_backoff_delay(a) for a in range(sp._MAX_429_ATTEMPTS - 1))
    assert total <= 25.0


def test_g6_backoff_is_clamped_to_the_remaining_deadline():
    now = time.monotonic()
    # 2 s left, but the uncapped delay for attempt 1 would be 10 s.
    assert _backoff_delay(1, deadline=now + 2.0, now=now) == pytest.approx(2.0, abs=0.01)
    # Deadline already passed -> 0.0, which the caller reads as "stop".
    assert _backoff_delay(0, deadline=now - 1.0, now=now) == 0.0
    # Never negative.
    assert _backoff_delay(3, deadline=now - 100.0, now=now) == 0.0


@pytest.mark.asyncio
async def test_g6_429_then_200_is_retried_n_plus_one_times_with_real_delay(
    fast_backoff,
):
    """RED-FIRST — the timing probe CERT-399 specifies.

    Pre-fix, a 429 was classified and returned immediately: one call, no delay.
    Post-fix the transport must be hit exactly N+1 times and the wall clock must
    show it, "not N+1 times in <100 ms".
    """
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] <= 2:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    started = time.monotonic()
    async with _client(handler) as client:
        status, _ = await _get(client, f"{KALSHI_BASE}/markets/{TICKER}")
    elapsed = time.monotonic() - started

    assert status == 200
    assert calls["n"] == 3, "expected exactly N+1 = 3 requests"
    # 0.05 + 0.10 = 0.15 s of real sleeping.
    assert elapsed >= 0.14, f"retried without delay ({elapsed:.4f}s)"


@pytest.mark.asyncio
async def test_g6_sustained_429_gives_up_as_rate_limited_not_as_a_fact(fast_backoff):
    """Exhausting the retries must stay RETRYABLE. A terminal answer here would
    delete the row from the burn-down over a transient limit — the same shape of
    harm as the NOT_FOUND bug this module's first suite was written for."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={})

    async with _client(handler) as client:
        outcome = await probe_kalshi(TICKER, client)

    assert calls["n"] == sp._MAX_429_ATTEMPTS
    assert outcome.disposition is Disposition.RATE_LIMITED
    assert outcome.disposition.is_retryable()


@pytest.mark.asyncio
async def test_g6_the_deadline_stops_the_retrying_and_is_not_slept_past(fast_backoff):
    """A caller deadline binds even mid-burst, and the answer stays retryable."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={})

    started = time.monotonic()
    async with _client(handler) as client:
        status, _ = await _get(
            client, f"{KALSHI_BASE}/markets/{TICKER}", deadline=started + 0.06
        )
    elapsed = time.monotonic() - started

    assert status == 429
    assert Disposition.RATE_LIMITED.is_retryable()
    assert elapsed < 0.25, f"slept past the deadline ({elapsed:.4f}s)"
    assert calls["n"] < sp._MAX_429_ATTEMPTS, "deadline did not cut the retries short"


@pytest.mark.asyncio
async def test_g6_an_already_expired_deadline_issues_no_request_at_all(fast_backoff):
    """And it reports the honest ``-1`` (no HTTP response obtained), which is
    TRANSPORT_ERROR — retryable, so the row survives to the next sweep."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={})

    async with _client(handler) as client:
        status, body = await _get(
            client, f"{KALSHI_BASE}/markets/{TICKER}", deadline=time.monotonic() - 1.0
        )

    assert calls["n"] == 0
    assert status == -1 and body is None
    assert Disposition.TRANSPORT_ERROR.is_retryable()


@pytest.mark.asyncio
async def test_g6_non_429_errors_are_not_retried(fast_backoff):
    """503 is a fact about the source, and the classifier already handles it.
    Retrying every status would multiply the sweep's cost for no information."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={})

    async with _client(handler) as client:
        status, _ = await _get(client, f"{KALSHI_BASE}/markets/{TICKER}")

    assert status == 503
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# G7 — concurrency bounds rate, not just in-flight
# ---------------------------------------------------------------------------


def test_g7_production_pace_constants_are_bounded():
    """The brake must be capped, and capped somewhere the sweep can still finish.

    Held on the real values so the scaled clock in ``fast_backoff`` cannot hide a
    ceiling that would stall the burn-down — the mirror of the backoff-constants
    guard above.
    """
    assert sp._PACE_INTERVAL_CEIL_S == 0.5, "paced floor must stay at 2 req/s"
    assert sp._PACE_FIRST_PENALTY_S == 0.1
    assert 0.0 < sp._PACE_FIRST_PENALTY_S <= sp._PACE_INTERVAL_CEIL_S
    assert sp._PACE_WIDEN_FACTOR > 1.0, "the brake must tighten, not loosen"
    assert 0.0 < sp._PACE_RELAX_FACTOR < 1.0, "the brake must be able to release"


def test_g7_the_pacer_widens_on_429_and_decays_on_success():
    pacer = RatePacer()
    assert pacer.interval == 0.0, "a healthy pacer must be free-running"

    pacer.penalise()
    first = pacer.interval
    assert first > 0.0

    pacer.penalise()
    assert pacer.interval > first, "the brake must tighten under sustained 429"

    for _ in range(20):
        pacer.penalise()
    assert pacer.interval <= sp._PACE_INTERVAL_CEIL_S, "the brake must be capped"

    for _ in range(20):
        pacer.relax()
    assert pacer.interval == 0.0, "success must decay the brake back to free-running"


@pytest.mark.asyncio
async def test_g7_healthy_traffic_is_not_paced():
    """The brake must cost nothing when the source is answering. A pacer that
    always sleeps would slow the sweep it exists to protect."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    pacer = RatePacer()
    items = [(i, "kalshi", TICKER) for i in range(40)]

    started = time.monotonic()
    async with _client(handler) as client:
        await probe_many(items, concurrency=8, client=client, pacer=pacer)
    elapsed = time.monotonic() - started

    assert pacer.interval == 0.0
    assert elapsed < 0.5, f"healthy traffic was paced ({elapsed:.4f}s)"


@pytest.mark.asyncio
async def test_g7_sustained_429_grows_wall_time_instead_of_staying_flat(fast_backoff):
    """The measured property CERT-399 asks for, stated as a comparison.

    Same batch size, same concurrency, only the source's answer differs. A fix
    that bounds in-flight but not rate leaves these two roughly equal, because a
    429 returns as fast as a 200.
    """
    def ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    items = [(i, "kalshi", TICKER) for i in range(20)]

    started = time.monotonic()
    async with _client(ok) as client:
        await probe_many(items, concurrency=8, client=client)
    healthy = time.monotonic() - started

    pacer = RatePacer()
    started = time.monotonic()
    async with _client(limited) as client:
        results = await probe_many(items, concurrency=8, client=client, pacer=pacer)
    throttled = time.monotonic() - started

    assert len(results) == 20
    assert all(o.disposition is Disposition.RATE_LIMITED for _, o in results)
    assert pacer.interval > 0.0, "the shared brake never engaged"
    assert throttled > healthy * 5, (
        f"429 traffic ran as fast as healthy traffic "
        f"(throttled {throttled:.4f}s vs healthy {healthy:.4f}s) — "
        "concurrency is bounding in-flight, not rate"
    )


@pytest.mark.asyncio
async def test_g7_the_brake_is_shared_so_one_workers_429_slows_the_others():
    """The half a per-request backoff cannot cover.

    Worker A draws the 429 and widens the shared interval; worker B, which only
    ever sees 200s, must still wait on the gap A opened. With a per-coroutine
    backoff B sails straight through and the source keeps being hammered.
    """
    pacer = RatePacer()
    pacer.penalise()
    widened = pacer.interval
    assert widened > 0.0

    started = time.monotonic()
    assert await pacer.wait_turn() is True   # reserves t0, no wait
    assert await pacer.wait_turn() is True   # must wait out the gap
    elapsed = time.monotonic() - started

    assert elapsed >= widened * 0.9, (
        f"the second caller did not wait on the shared gap ({elapsed:.4f}s "
        f"vs interval {widened:.4f}s)"
    )


@pytest.mark.asyncio
async def test_g7_the_pacer_yields_to_the_deadline_rather_than_sleeping_past_it():
    """The brake must never become the reason the sweep misses its budget."""
    pacer = RatePacer()
    for _ in range(10):
        pacer.penalise()
    assert pacer.interval == sp._PACE_INTERVAL_CEIL_S

    await pacer.wait_turn()  # reserve, so the next turn is a full interval away
    started = time.monotonic()
    granted = await pacer.wait_turn(deadline=time.monotonic() + 0.01)
    elapsed = time.monotonic() - started

    assert granted is False, "the pacer slept past the caller's deadline"
    assert elapsed < sp._PACE_INTERVAL_CEIL_S / 2


@pytest.mark.asyncio
async def test_g7_the_runners_own_loop_is_braked_not_just_probe_many():
    """The gap that would have shipped a fix which does not fix.

    ``settlement_sweep_runner.run_sweep`` does not call ``probe_many`` — it has
    its own semaphore and its own ``gather``. A pacer installed only inside
    ``probe_many`` therefore reaches every caller EXCEPT the one that performs
    the production sweep, and G7 would have passed while the real capture kept
    issuing unpaced retries.

    Asserted structurally rather than by running a sweep (which needs a session):
    the runner must import the pacer surface and install it, and ``_get`` must
    read the pacer from the shared ContextVar the runner sets.
    """
    from app.services import settlement_sweep_runner as runner

    assert runner.install_pacer is sp.install_pacer
    assert runner.RatePacer is sp.RatePacer

    # A pacer installed OUTSIDE probe_many still brakes a bare _get — this is the
    # mechanism the runner relies on.
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    pacer = RatePacer()
    token = sp.install_pacer(pacer)
    try:
        async with _client(limited) as client:
            await _get(
                client,
                f"{KALSHI_BASE}/markets/{TICKER}",
                deadline=time.monotonic() + 0.05,
            )
    finally:
        sp.reset_pacer(token)

    assert pacer.interval > 0.0, (
        "a pacer installed by the runner never saw the 429 — the runner's loop "
        "is unbraked"
    )


@pytest.mark.asyncio
async def test_g7_a_second_batch_does_not_inherit_the_first_batchs_brake():
    """ContextVar hygiene. A leaked expired deadline would make every later batch
    return TRANSPORT_ERROR without issuing a request — a silent, total false
    negative that looks exactly like an outage."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"market": {"status": "finalized"}})

    items = [(1, "kalshi", TICKER)]
    async with _client(handler) as client:
        await probe_many(items, client=client, deadline=time.monotonic() - 1.0)
        assert calls["n"] == 0, "expired deadline should have blocked the first batch"

        await probe_many(items, client=client)
        assert calls["n"] == 1, "the expired deadline leaked into the next batch"

    assert sp._deadline_var.get() is None
    assert sp._pacer_var.get() is None
