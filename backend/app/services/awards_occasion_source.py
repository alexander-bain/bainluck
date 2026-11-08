"""Venue inputs for the ceremony kind's worker-side finder (#11935).

DISCOVER / TRUTH. A venue-listed ceremony supplies its own card and container.
The stored open entertainment pool supplies candidate event identifiers. Primary
rules from the venue establish identity. This reader returns proposals only.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from time import monotonic
from typing import Any

from sqlalchemy import func, or_, select

from app.utils.awards_occasion_finder import (
    AwardsOccasion,
    OccasionDiscovery,
    _identity,
    find_awards_occasions,
)

MAX_AWARDS_EVENT_CANDIDATES = 1024
AWARDS_SOURCE_BUDGET_SECONDS = 90.0
AWARDS_KALSHI_CONCURRENCY = 4
AWARDS_KALSHI_REQUESTS_PER_SECOND = 12
AWARDS_POLYMARKET_BATCH_SIZE = 20


class AwardsOccasionSourceError(ValueError):
    """An incomplete source read cannot establish a ceremony proposal set."""


def _merge_discoveries(
    discoveries: Iterable[OccasionDiscovery],
    refused: Iterable[tuple[str, str, str]] = (),
) -> OccasionDiscovery:
    events_by_label = defaultdict(set)
    all_refused = set(refused)
    for discovery in discoveries:
        all_refused.update(discovery.refused)
        for occasion in discovery.occasions:
            events_by_label[occasion.label].update(occasion.events)
    return OccasionDiscovery(
        occasions=tuple(
            AwardsOccasion(label, tuple(sorted(events)))
            for label, events in sorted(events_by_label.items())
        ),
        refused=tuple(sorted(all_refused)),
    )


def kalshi_occasion_event(payload: Any, event_ticker: str) -> dict[str, Any]:
    """Normalize Kalshi's separate or nested market envelope without losing rules."""
    event = payload.get("event") if isinstance(payload, Mapping) else None
    if not isinstance(event, Mapping) or event.get("event_ticker") != event_ticker:
        raise AwardsOccasionSourceError(f"{event_ticker}: event_identity_mismatch")

    nested = event.get("markets")
    separate = payload.get("markets")
    if any(
        value is not None and not isinstance(value, list)
        for value in (nested, separate)
    ):
        raise AwardsOccasionSourceError(f"{event_ticker}: missing_market_envelope")
    if nested and separate and nested != separate:
        raise AwardsOccasionSourceError(f"{event_ticker}: conflicting_market_envelopes")
    # With nested markets requested the venue can put the complete list in
    # event.markets and leave the sibling markets list empty, or vice versa.
    markets = separate or nested
    if markets is None and (separate == [] or nested == []):
        markets = []
    if not isinstance(markets, list):
        raise AwardsOccasionSourceError(f"{event_ticker}: missing_market_envelope")
    if any(
        not isinstance(market, Mapping) or market.get("event_ticker") != event_ticker
        for market in markets
    ):
        raise AwardsOccasionSourceError(f"{event_ticker}: market_identity_mismatch")
    return {**event, "provider": "kalshi", "markets": markets}


def polymarket_occasion_event(payload: Any, event_id: str) -> dict[str, Any]:
    """Keep Gamma's enclosing event identity and each market's primary description."""
    if not isinstance(payload, Mapping) or str(payload.get("id")) != event_id:
        raise AwardsOccasionSourceError(f"{event_id}: event_identity_mismatch")
    markets = payload.get("markets")
    if not isinstance(markets, list):
        raise AwardsOccasionSourceError(f"{event_id}: missing_market_envelope")
    normalized = []
    for market in markets:
        if not isinstance(market, Mapping) or not str(market.get("id") or "").isdigit():
            raise AwardsOccasionSourceError(f"{event_id}: market_identity_mismatch")
        parents = market.get("events")
        if parents is not None and (
            not isinstance(parents, list)
            or not parents
            or any(
                not isinstance(parent, Mapping) or str(parent.get("id")) != event_id
                for parent in parents
            )
        ):
            raise AwardsOccasionSourceError(f"{event_id}: market_identity_mismatch")
        normalized.append({**market, "rules_primary": market.get("description")})
    return {**payload, "provider": "polymarket", "markets": normalized}


async def _read_kalshi_event(service: Any, event_ticker: str) -> dict[str, Any] | None:
    response = await service.client.get(
        f"{service.BASE_URL}/events/{event_ticker}",
        params={"with_nested_markets": "true"},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return kalshi_occasion_event(response.json(), event_ticker)


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
    discoveries = []
    refused = []
    async with asyncio.timeout(AWARDS_SOURCE_BUDGET_SECONDS):
        tickers = (await db.execute(statement)).scalars().all()
        if len(tickers) > MAX_AWARDS_EVENT_CANDIDATES:
            raise AwardsOccasionSourceError("candidate_limit_exceeded")
        valid_tickers = []
        for event_ticker in tickers:
            if _identity({"provider": "kalshi", "event_ticker": event_ticker}) is None:
                refused.append(("kalshi", str(event_ticker or ""), "invalid_identity"))
            else:
                valid_tickers.append(event_ticker)
        for offset in range(0, len(valid_tickers), AWARDS_KALSHI_CONCURRENCY):
            batch = valid_tickers[offset : offset + AWARDS_KALSHI_CONCURRENCY]
            started = monotonic()
            # Waiting for every sibling also joins failures and cancellations
            # before the caller closes the HTTP client.
            results = await asyncio.gather(
                *(_read_kalshi_event(service, ticker) for ticker in batch),
                return_exceptions=True,
            )
            for event_ticker, event in zip(batch, results):
                if isinstance(event, BaseException):
                    raise event
                if event is None:
                    refused.append(("kalshi", event_ticker, "provider_event_missing"))
                else:
                    # Keep the evidence, rather than retaining the whole venue
                    # response for every unrelated entertainment event.
                    discoveries.append(find_awards_occasions([event]))
            await asyncio.sleep(
                max(
                    0,
                    len(batch) / AWARDS_KALSHI_REQUESTS_PER_SECOND
                    - (monotonic() - started),
                )
            )

    return _merge_discoveries(discoveries, refused)


async def read_polymarket_awards_occasions(db: Any, service: Any) -> OccasionDiscovery:
    """Read stored open entertainment event IDs with the same bounds as Kalshi."""
    from app.models.models import FuturesMarket

    event_id = FuturesMarket.market_metadata["polymarket_event_id"].astext.label(
        "provider_event_id"
    )
    statement = (
        select(event_id)
        .where(
            FuturesMarket.source == "polymarket",
            FuturesMarket.status == "open",
            or_(
                FuturesMarket.category == "entertainment",
                FuturesMarket.llm_sport_category == "entertainment",
            ),
        )
        .distinct()
        .order_by(event_id)
        .limit(MAX_AWARDS_EVENT_CANDIDATES + 1)
    )
    discoveries = []
    refused = []
    async with asyncio.timeout(AWARDS_SOURCE_BUDGET_SECONDS):
        event_ids = (await db.execute(statement)).scalars().all()
        if len(event_ids) > MAX_AWARDS_EVENT_CANDIDATES:
            raise AwardsOccasionSourceError("candidate_limit_exceeded")
        valid_ids = []
        for stored_id in event_ids:
            identity = _identity({"provider": "polymarket", "id": stored_id})
            if identity is None:
                refused.append(("polymarket", str(stored_id or ""), "invalid_identity"))
                continue
            valid_ids.append(identity[1])
        for offset in range(0, len(valid_ids), AWARDS_POLYMARKET_BATCH_SIZE):
            batch = valid_ids[offset : offset + AWARDS_POLYMARKET_BATCH_SIZE]
            payloads = await service.get_events_by_ids(batch)
            if not isinstance(payloads, list):
                raise AwardsOccasionSourceError("polymarket: malformed_event_batch")
            seen = set()
            for payload in payloads:
                provider_id = (
                    str(payload.get("id") or "") if isinstance(payload, Mapping) else ""
                )
                if provider_id not in batch or provider_id in seen:
                    raise AwardsOccasionSourceError(
                        "polymarket: batch_identity_mismatch"
                    )
                seen.add(provider_id)
                discoveries.append(
                    find_awards_occasions(
                        [polymarket_occasion_event(payload, provider_id)]
                    )
                )
            for provider_id in batch:
                if provider_id in seen:
                    continue
                # Gamma can truncate an id batch or omit unknown IDs. Only
                # the single-event endpoint's 404 proves absence (#53).
                payload = await service.get_event_by_id(provider_id)
                if payload is None:
                    refused.append(
                        ("polymarket", provider_id, "provider_event_missing")
                    )
                else:
                    discoveries.append(
                        find_awards_occasions(
                            [polymarket_occasion_event(payload, provider_id)]
                        )
                    )

    return _merge_discoveries(discoveries, refused)


async def read_awards_occasions(
    db: Any, kalshi_service: Any, polymarket_service: Any
) -> OccasionDiscovery:
    """One bounded discovery combines event membership, preserving each venue's rules."""
    async with asyncio.timeout(AWARDS_SOURCE_BUDGET_SECONDS):
        kalshi = await read_kalshi_awards_occasions(db, kalshi_service)
        polymarket = await read_polymarket_awards_occasions(db, polymarket_service)
    return _merge_discoveries((kalshi, polymarket))


@asynccontextmanager
async def read_only_session():
    """Connection-level limits survive every rollback in the proposal and worker paths."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.services.database import DATABASE_URL, build_connect_args

    connect_args = build_connect_args(
        DATABASE_URL, statement_timeout_ms=2000, lock_timeout_ms=250
    )
    connect_args["server_settings"]["default_transaction_read_only"] = "on"
    engine = create_async_engine(
        DATABASE_URL,
        connect_args=connect_args,
        poolclass=NullPool,
        hide_parameters=True,
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as db:
            yield db
    finally:
        await engine.dispose()


async def read_live(provider: str = "kalshi") -> OccasionDiscovery:
    """The CLI and worker share client cleanup and the read-only source boundary."""
    from app.services.kalshi_api import KalshiAPIService
    from app.services.polymarket_api import PolymarketAPIService

    if provider not in {"kalshi", "polymarket", "all"}:
        raise ValueError("Unsupported awards provider")
    async with AsyncExitStack() as clients:
        kalshi = polymarket = None
        if provider in {"kalshi", "all"}:
            kalshi = KalshiAPIService()
            clients.push_async_callback(kalshi.close)
        if provider in {"polymarket", "all"}:
            polymarket = PolymarketAPIService()
            clients.push_async_callback(polymarket.close)
        async with read_only_session() as db:
            if provider == "all":
                return await read_awards_occasions(db, kalshi, polymarket)
            if provider == "polymarket":
                return await read_polymarket_awards_occasions(db, polymarket)
            return await read_kalshi_awards_occasions(db, kalshi)
