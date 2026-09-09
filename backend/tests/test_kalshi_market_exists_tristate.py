"""#4253 — `market_exists` must never let "we could not tell" read as "it is gone".

`KalshiAPIService.get_market` is documented "Returns None only for 404", and that
sentence is false about its own body: the `except Exception` arm returns `None`
too, after three attempts. A DNS blip, a read timeout and a genuine 404 all
arrive as the same value (gotcha #36).

That collapse is harmless while the only question asked of it is "give me the
market, or nothing". It stops being harmless the moment a caller reads the
absence as a FACT about the venue — which is exactly what the delisted-leg
retirement does: a `False` there withdraws a price. So the retirement asks
through `market_exists`, whose contract is tri-state, and these arms pin the
distinction the caller depends on.

Pure and offline: the transport is stubbed, because the property under test is
how each HTTP outcome is *classified*, not that httpx works.
"""

from __future__ import annotations

import pytest


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {"market": {"ticker": "KXIPOTEST-27JUN01", "status": "active"}}


class _Client:
    """Replays a scripted sequence of outcomes; an `Exception` instance raises."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def get(self, url, **kwargs):
        self.calls += 1
        outcome = self.outcomes[min(self.calls - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return _Response(outcome)


def _service(*outcomes):
    from app.services.kalshi_api import KalshiAPIService

    service = KalshiAPIService.__new__(KalshiAPIService)
    service.client = _Client(*outcomes)
    return service


pytestmark = pytest.mark.asyncio


class TestMarketExistsIsTriState:
    async def test_an_observed_404_is_a_definite_absence(self):
        service = _service(404)
        assert await service.market_exists("KXIPOTEST-25SEP01") is False

    async def test_a_200_is_presence_whatever_the_market_status(self):
        """`finalized` markets answer 200 and must never be retired.

        Measured 2026-09-09: `KXIPOSTARLINK-26SEP01` is `finalized`,
        `result=no`, and still served — the row a status-blind rule would eat.
        """
        service = _service(200)
        assert await service.market_exists("KXIPOSTARLINK-26SEP01") is True

    async def test_an_unreachable_venue_is_None_and_not_False(self):
        """THE arm. If this ever returns False, a timeout withdraws real prices."""
        service = _service(OSError("connection reset"))
        result = await service.market_exists("KXIPOTEST-25SEP01")
        assert result is None, (
            "an unreachable venue was classified as a definite absence; the "
            "retirement would spend a network failure as evidence a contract "
            "was delisted"
        )
        assert result is not False

    async def test_a_server_error_is_None_and_not_False(self):
        service = _service(500)
        assert await service.market_exists("KXIPOTEST-25SEP01") is None

    async def test_a_429_is_retried_and_never_reported_as_absent(self):
        """Rate limiting is the venue's throttle, not its inventory (gotcha #36)."""
        service = _service(429, 200)
        assert await service.market_exists("KXIPOTEST-27JUN01") is True
        assert service.client.calls == 2

    async def test_a_transient_failure_that_recovers_reports_the_recovery(self):
        service = _service(OSError("reset"), 404)
        assert await service.market_exists("KXIPOTEST-25SEP01") is False
        assert service.client.calls == 2


class TestTheContractItReplaces:
    async def test_get_market_still_cannot_tell_the_two_apart(self):
        """The reason `market_exists` exists, demonstrated rather than described.

        If this arm ever fails because `get_market` learned the difference, this
        whole module is redundant and should be deleted — not "fixed".
        """
        from_404 = await _service(404).get_market("KXIPOTEST-25SEP01")
        from_error = await _service(OSError("reset"), OSError("reset"), OSError("reset")).get_market(
            "KXIPOTEST-25SEP01"
        )
        assert from_404 is None and from_error is None, (
            "get_market distinguishes 404 from failure now; market_exists is "
            "no longer needed"
        )
