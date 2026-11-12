"""Recheck a quiet Kalshi field without rewriting its prices (#12633).

The socket can keep recording chart points while no new ticker frame changes
the detail row. Those keepalive points cannot date a fresh venue read. For a
small, stale, open field, ask the existing venue client once and certify only
the exact stored probabilities. The full field must agree because the served
normalization depends on every leg. A moved, missing or settled leg refuses
the observation; the ordinary writers still own prices and settlement.

This is a response-only observation. No database statement or task dispatch.
Cache hits retain the successful upstream read time, never the page-read time.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

MAX_LEGS = 50
RECHECK_AFTER_S = 20 * 60
READ_TIMEOUT_S = 1.0
CACHE_SECONDS = 5 * 60
FAILURE_SECONDS = 30
MAX_CACHE_ENTRIES = 128
MAX_IN_FLIGHT = 4
MAX_READS_PER_MINUTE = 30


@dataclass(frozen=True)
class Observation:
    ticker: str
    prices: tuple[tuple[str, float], ...]
    observed_at: datetime


@dataclass(frozen=True)
class ReadResult:
    observation: Observation | None
    reason: str | None = None


_cache: OrderedDict[str, tuple[float, ReadResult]] = OrderedDict()
_in_flight: dict[str, asyncio.Task] = {}
_reads: deque[float] = deque()


def _price(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 6) if math.isfinite(number) and 0 < number < 1 else None


def _stamp(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _book_price(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 6) if math.isfinite(number) and 0 <= number <= 1 else None


def board_prices(market: Any, now: datetime) -> tuple[tuple[str, float], ...] | None:
    """Only complete, ungraded standalone fields with an old observation."""
    from app.utils.resolution_authority import AUTHORITATIVE_SOURCES

    if (
        getattr(market, "source", None) != "kalshi"
        or getattr(market, "status", None) != "open"
        or getattr(market, "market_type", None) != "field"
        or getattr(market, "event_id", None) is not None
        or getattr(market, "settled_at", None) is not None
    ):
        return None
    rows = getattr(market, "outcomes", ())
    if not 2 <= len(rows) <= MAX_LEGS:
        return None
    prices = {}
    stale = False
    for row in rows:
        ticker = getattr(row, "external_id", None)
        probability = _price(getattr(row, "current_probability", None))
        if (
            not isinstance(ticker, str)
            or not ticker
            or ticker in prices
            or probability is None
            or getattr(row, "is_winner", None) is True
            or getattr(row, "resolution_source", None) in AUTHORITATIVE_SOURCES
        ):
            return None
        prices[ticker] = probability
        observed = _stamp(getattr(row, "last_updated", None))
        stale |= observed is None or (now - observed).total_seconds() >= RECHECK_AFTER_S
    return tuple(sorted(prices.items())) if stale else None


def venue_prices(
    service: Any, raw: Any, ticker: str
) -> tuple[tuple[str, float], ...] | None:
    """Use the writer's parser and pricing rule; require every native leg."""
    from app.tasks.kalshi import _kalshi_yes_probability

    if not isinstance(raw, dict) or raw.get("event_ticker") != ticker:
        return None
    rows = raw.get("markets")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_LEGS:
        return None
    prices = {}
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("status") != "active"
            or row.get("result")
            or row.get("event_ticker") != ticker
        ):
            return None
        leg = service._parse_market(row)
        if leg is None or not leg.ticker or leg.ticker in prices:
            return None
        probability = _price(
            _kalshi_yes_probability(leg.yes_bid, leg.yes_ask, leg.last_price)
        )
        bid, ask = _book_price(leg.yes_bid), _book_price(leg.yes_ask)
        if probability is None or bid is None or ask is None or bid > ask:
            return None
        prices[leg.ticker] = probability
    # Date the number we just verified, not the older stored book. The live
    # book can change without changing the writer's selected probability.
    return tuple(sorted(prices.items()))


async def _read(ticker: str) -> ReadResult:
    from app.services.kalshi_api import KalshiAPIService

    # The outer deadline includes client creation, retries and close. No
    # independent retry here; a venue failure leaves the existing stale state.
    async with asyncio.timeout(READ_TIMEOUT_S):
        service = KalshiAPIService()
        try:
            raw = await service.get_event(ticker, with_nested_markets=True)
            observed = datetime.now(timezone.utc)
            prices = venue_prices(service, raw, ticker)
            if prices is None:
                return ReadResult(None, "venue_field_not_live_complete")
            return ReadResult(Observation(ticker, prices, observed))
        finally:
            await service.close()


async def _read_and_cache(ticker: str) -> ReadResult:
    result = ReadResult(None, "cancelled")
    try:
        result = await _read(ticker)
        return result
    except TimeoutError:
        result = ReadResult(None, "venue_timeout")
        return result
    except Exception as exc:
        logger.info(
            "futures observation unavailable for %s: %s", ticker, type(exc).__name__
        )
        result = ReadResult(None, "venue_read_failed")
        return result
    finally:
        _in_flight.pop(ticker, None)
        ttl = CACHE_SECONDS if result.observation else FAILURE_SECONDS
        _cache[ticker] = (time.monotonic() + ttl, result)
        _cache.move_to_end(ticker)
        while len(_cache) > MAX_CACHE_ENTRIES:
            _cache.popitem(last=False)


async def current_observation(ticker: str) -> ReadResult:
    now = time.monotonic()
    cached = _cache.get(ticker)
    if cached and cached[0] > now:
        _cache.move_to_end(ticker)
        return cached[1]
    task = _in_flight.get(ticker)
    if task is None:
        while _reads and now - _reads[0] >= 60:
            _reads.popleft()
        if len(_in_flight) >= MAX_IN_FLIGHT or len(_reads) >= MAX_READS_PER_MINUTE:
            return ReadResult(None, "read_budget_full")
        _reads.append(now)
        task = asyncio.create_task(_read_and_cache(ticker))
        _in_flight[ticker] = task
    # A disconnected reader cannot cancel the bounded read shared by another.
    return await asyncio.shield(task)


async def apply_live_observation(detail: dict, market: Any) -> None:
    """Date only an identical source field, including its normalized numbers."""
    if detail.get("representation", "source") != "source":
        return
    prices = board_prices(market, datetime.now(timezone.utc))
    ticker = getattr(market, "external_id", None)
    if prices is None or not isinstance(ticker, str) or not ticker:
        return
    result = await current_observation(ticker)
    observation = result.observation
    if observation is None:
        detail["price_observation"] = {"state": "unavailable", "reason": result.reason}
        return
    if observation.ticker != ticker or observation.prices != prices:
        detail["price_observation"] = {
            "state": "refused",
            "reason": "stored_field_changed",
        }
        return
    age = (datetime.now(timezone.utc) - observation.observed_at).total_seconds()
    if not 0 <= age <= CACHE_SECONDS:
        detail["price_observation"] = {
            "state": "refused",
            "reason": "observation_outside_window",
        }
        return
    stamp = observation.observed_at.isoformat()
    for row in detail.get("outcomes", []):
        if row.get("probability") is not None:
            row["observed_at"] = stamp
            # Installed readers use this legacy field for "Recorded ...".
            # Only the response is changed; row-touch and movement clocks in
            # storage stay intact, as does the response's price_changed_at.
            row["last_updated"] = stamp
    detail["price_observation"] = {
        "state": "verified",
        "basis": "upstream_read_verified",
        "observed_at": stamp,
    }
