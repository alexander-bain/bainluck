"""Venue inputs for the ceremony kind's worker-side finder (#11935).

DISCOVER / TRUTH. A venue-listed ceremony supplies its own card and container.
The stored open entertainment pool supplies candidate event identifiers. Primary
rules from the venue establish identity. This reader returns proposals only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select

from app.utils.awards_occasion_finder import (
    OccasionDiscovery,
    _identity,
    find_awards_occasions,
)

MAX_AWARDS_EVENT_CANDIDATES = 100
AWARDS_SOURCE_BUDGET_SECONDS = 90.0


class AwardsOccasionSourceError(ValueError):
    """An incomplete source read cannot establish a ceremony proposal set."""


def kalshi_occasion_event(payload: Any, event_ticker: str) -> dict[str, Any]:
    """Normalize Kalshi's separate or nested market envelope without losing rules."""
    event = payload.get("event") if isinstance(payload, Mapping) else None
    if not isinstance(event, Mapping) or event.get("event_ticker") != event_ticker:
        raise AwardsOccasionSourceError(f"{event_ticker}: event_identity_mismatch")

    nested = event.get("markets")
    separate = payload.get("markets")
    if nested is not None and separate is not None and nested != separate:
        raise AwardsOccasionSourceError(f"{event_ticker}: conflicting_market_envelopes")
    markets = separate if separate is not None else nested
    if not isinstance(markets, list):
        raise AwardsOccasionSourceError(f"{event_ticker}: missing_market_envelope")
    if any(
        not isinstance(market, Mapping) or market.get("event_ticker") != event_ticker
        for market in markets
    ):
        raise AwardsOccasionSourceError(f"{event_ticker}: market_identity_mismatch")
    return {**event, "provider": "kalshi", "markets": markets}


async def read_kalshi_awards_occasions(db: Any, service: Any) -> OccasionDiscovery:
    """Read bounded, current venue evidence for stored entertainment candidates.

    No ceremony names or ticker stems are declared. A candidate ceiling, bad
    response, rate limit, transport failure or deadline aborts the read. A venue
    404 is retained as an explicit refusal. The caller owns both clients.
    """
    from app.models.models import FuturesMarket

    ticker = func.coalesce(
        FuturesMarket.market_metadata["kalshi_event_ticker"].astext,
        FuturesMarket.external_id,
    ).label("event_ticker")
    statement = (
        select(ticker)
        .where(
            FuturesMarket.source == "kalshi",
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.category == "entertainment",
                FuturesMarket.llm_sport_category == "entertainment",
            ),
        )
        .distinct()
        .order_by(ticker)
        .limit(MAX_AWARDS_EVENT_CANDIDATES + 1)
    )
    events = []
    refused = []
    async with asyncio.timeout(AWARDS_SOURCE_BUDGET_SECONDS):
        tickers = (await db.execute(statement)).scalars().all()
        if len(tickers) > MAX_AWARDS_EVENT_CANDIDATES:
            raise AwardsOccasionSourceError("candidate_limit_exceeded")
        for event_ticker in tickers:
            if _identity({"provider": "kalshi", "event_ticker": event_ticker}) is None:
                refused.append(("kalshi", str(event_ticker or ""), "invalid_identity"))
                continue
            # Read the native envelope. get_event() returns only its "event"
            # object, but the venue also returns markets beside that object.
            response = await service.client.get(
                f"{service.BASE_URL}/events/{event_ticker}",
                params={"with_nested_markets": "true"},
            )
            if response.status_code == 404:
                refused.append(("kalshi", event_ticker, "provider_event_missing"))
                continue
            response.raise_for_status()
            events.append(kalshi_occasion_event(response.json(), event_ticker))

    discovery = find_awards_occasions(events)
    return OccasionDiscovery(
        occasions=discovery.occasions,
        refused=tuple(sorted(set(discovery.refused).union(refused))),
    )
