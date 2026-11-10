"""Validate one native Kalshi event and retain either documented market list."""

from collections.abc import Mapping
from typing import Any


class KalshiEventEnvelopeError(ValueError):
    """The response cannot establish the requested event's markets."""

    def __init__(self, event_ticker: str, reason: str):
        self.reason = reason
        super().__init__(f"{event_ticker}: {reason}")


def kalshi_event_envelope(
    payload: Any, event_ticker: str, *, require_markets: bool = True
) -> dict[str, Any]:
    event = payload.get("event") if isinstance(payload, Mapping) else None
    if not isinstance(event, Mapping) or event.get("event_ticker") != event_ticker:
        raise KalshiEventEnvelopeError(event_ticker, "event_identity_mismatch")
    nested = event.get("markets")
    separate = payload.get("markets")
    if any(
        value is not None and not isinstance(value, list)
        for value in (nested, separate)
    ):
        raise KalshiEventEnvelopeError(event_ticker, "missing_market_envelope")
    if nested and separate and nested != separate:
        raise KalshiEventEnvelopeError(event_ticker, "conflicting_market_envelopes")
    markets = separate or nested
    if markets is None and (separate == [] or nested == []):
        markets = []
    if markets is None and not require_markets:
        return dict(event)
    if not isinstance(markets, list):
        raise KalshiEventEnvelopeError(event_ticker, "missing_market_envelope")
    if any(
        not isinstance(market, Mapping) or market.get("event_ticker") != event_ticker
        for market in markets
    ):
        raise KalshiEventEnvelopeError(event_ticker, "market_identity_mismatch")
    return {**event, "markets": markets}
