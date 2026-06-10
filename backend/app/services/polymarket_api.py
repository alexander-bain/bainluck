"""
Polymarket API integration service.

Handles fetching prediction market data from Polymarket's public APIs.
No API key required for read-only access.

Two APIs used:
- Gamma API (gamma-api.polymarket.com): Market discovery, metadata, tags, sports
- CLOB API (clob.polymarket.com): Prices, order book, price history
"""

import json
import logging
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PolymarketMarket(BaseModel):
    """A single Polymarket market (binary outcome within an event)."""

    condition_id: str
    question: str
    slug: Optional[str] = None

    # Outcome data (parsed from stringified JSON arrays)
    outcomes: list[str] = []  # ["Yes", "No"]
    outcome_prices: list[float] = []  # [0.65, 0.35]
    clob_token_ids: list[str] = []  # token IDs for CLOB API price queries

    # Status
    active: bool = True
    closed: bool = False
    accepting_orders: bool = True

    # Pricing
    last_trade_price: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None

    # Volume / liquidity
    volume: Optional[float] = None
    volume_24h: Optional[float] = None
    liquidity: Optional[float] = None

    # NegRisk (multi-outcome event markets)
    neg_risk: bool = False

    # Group item title (e.g., "33°F or below" for weather markets)
    group_item_title: Optional[str] = None


class PolymarketEvent(BaseModel):
    """A Polymarket event containing one or more markets."""

    id: str
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None

    # Status
    active: bool = True
    closed: bool = False
    archived: bool = False

    # Tags for categorization (e.g., ["Sports", "NBA", "Basketball"])
    tags: list[str] = []

    # Timing
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    creation_date: Optional[datetime] = None

    # Multi-outcome flag
    neg_risk: bool = False

    # Nested markets
    markets: list[PolymarketMarket] = []

    # Volume (event-level)
    volume: Optional[float] = None
    liquidity: Optional[float] = None


class PolymarketSport(BaseModel):
    """A sport/league from Polymarket's /sports endpoint."""

    label: str
    slug: str
    tag_id: Optional[str] = None
    series_id: Optional[str] = None
    image: Optional[str] = None


class PolymarketAPIService:
    """Service for interacting with Polymarket's public APIs."""

    GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
    CLOB_BASE_URL = "https://clob.polymarket.com"

    # Note: We fetch ALL active events (no tag filtering). Categorization
    # happens in the polling task via tag-to-category mapping.

    def __init__(self):
        """Initialize with no auth (Polymarket read API is fully public)."""
        self.gamma_client = httpx.AsyncClient(
            base_url=self.GAMMA_BASE_URL,
            timeout=30.0,
            headers={
                "Accept": "application/json",
            },
        )
        self.clob_client = httpx.AsyncClient(
            base_url=self.CLOB_BASE_URL,
            timeout=30.0,
            headers={
                "Accept": "application/json",
            },
        )

    async def close(self):
        """Close HTTP clients."""
        await self.gamma_client.aclose()
        await self.clob_client.aclose()

    # =========================================================================
    # Gamma API — Market Discovery
    # =========================================================================

    async def get_events(
        self,
        active: Optional[bool] = True,
        closed: Optional[bool] = False,
        tag_id: Optional[str] = None,
        tag_slug: Optional[str] = None,
        series_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        order: Optional[str] = None,
        ascending: bool = False,
    ) -> list[dict]:
        """
        Get events from Gamma API.

        Args:
            active: Filter active events
            closed: Filter closed events
            tag_id: Filter by tag ID
            tag_slug: Filter by tag slug (e.g., "baseball", "basketball")
            series_id: Filter by series/league ID
            limit: Max results per page
            offset: Pagination offset
            order: Sort field (e.g., "volume", "liquidity", "startDate")
            ascending: Sort direction

        Returns:
            List of raw event dicts
        """
        params: dict = {"limit": min(limit, 100), "offset": offset}
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if tag_id:
            params["tag_id"] = tag_id
        if tag_slug:
            params["tag_slug"] = tag_slug
        if series_id:
            params["series_id"] = series_id
        if order:
            params["order"] = order
            params["ascending"] = str(ascending).lower()

        response = await self.gamma_client.get("/events", params=params)
        response.raise_for_status()
        return response.json()

    async def get_event_by_id(self, event_id: str) -> Optional[dict]:
        """
        Get a single event by its Polymarket event ID (includes all markets
        with clobTokenIds needed for price history).
        """
        try:
            response = await self.gamma_client.get(f"/events/{event_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.warning("Failed to get event %s: %s", event_id, e)
            return None

    async def get_sports(self) -> list[dict]:
        """
        Get supported sports/leagues from Gamma API.

        Returns metadata including tag_id and series_id for each sport,
        which can be used to filter events by league.
        """
        response = await self.gamma_client.get("/sports")
        response.raise_for_status()
        return response.json()

    async def get_markets(
        self,
        active: Optional[bool] = True,
        closed: Optional[bool] = False,
        tag_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """Get markets from Gamma API."""
        params: dict = {"limit": min(limit, 100), "offset": offset}
        if active is not None:
            params["active"] = str(active).lower()
        if closed is not None:
            params["closed"] = str(closed).lower()
        if tag_id:
            params["tag_id"] = tag_id

        response = await self.gamma_client.get("/markets", params=params)
        response.raise_for_status()
        return response.json()

    async def get_tags(self, limit: int = 100) -> list[dict]:
        """Get all available tags/categories."""
        response = await self.gamma_client.get("/tags", params={"limit": limit})
        response.raise_for_status()
        return response.json()

    async def get_market_by_condition(self, condition_id: str) -> Optional[dict]:
        """Fetch a single market by condition_id from Gamma API.

        Returns raw dict with outcome_prices reflecting settlement for
        resolved markets. Returns None on 404 or error.
        """
        try:
            response = await self.gamma_client.get(f"/markets/{condition_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug("Failed to get market %s: %s", condition_id, e)
            return None

    # =========================================================================
    # CLOB API — Prices & History
    # =========================================================================

    async def get_price(self, token_id: str, side: str = "buy") -> Optional[float]:
        """Get best bid or ask price for a token."""
        try:
            response = await self.clob_client.get(
                "/price", params={"token_id": token_id, "side": side}
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get("price", 0))
        except Exception as e:
            logger.warning("Failed to get price for token %s: %s", token_id, e)
            return None

    async def get_midpoint(self, token_id: str) -> Optional[float]:
        """Get mid-market price for a token."""
        try:
            response = await self.clob_client.get(
                "/midpoint", params={"token_id": token_id}
            )
            response.raise_for_status()
            data = response.json()
            return float(data.get("mid", 0))
        except Exception as e:
            logger.warning("Failed to get midpoint for token %s: %s", token_id, e)
            return None

    async def get_prices_history(
        self,
        token_id: str,
        interval: str = "max",
        fidelity: int = 60,
    ) -> list[dict]:
        """
        Get historical price time series for a token.

        Args:
            token_id: The clobTokenId for the outcome
            interval: Time range ('1h', '6h', '1d', '1w', 'max')
            fidelity: Granularity in minutes (e.g., 60 = hourly)

        Returns:
            List of {"t": unix_timestamp, "p": price} dicts
        """
        try:
            response = await self.clob_client.get(
                "/prices-history",
                params={
                    "market": token_id,
                    "interval": interval,
                    "fidelity": fidelity,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("history", [])
        except Exception as e:
            logger.warning("Failed to get price history for token %s: %s", token_id, e)
            return []

    # =========================================================================
    # High-level fetchers
    # =========================================================================

    async def get_all_active_events(self) -> list[PolymarketEvent]:
        """
        Fetch ALL active events by paginating through /events.

        Fetches everything Polymarket has — sports, politics, entertainment,
        crypto, weather, etc. Events are categorized using their tags array
        in the polling task.

        Rate impact: ~50-80 pages × 1 request each, well within ~1,000/hr limit.
        """
        import asyncio

        all_events: list[PolymarketEvent] = []
        seen_ids: set[str] = set()
        max_pages = 100  # safety limit (~10,000 events max)

        for page in range(max_pages):
            if page > 0:
                await asyncio.sleep(0.3)

            try:
                events_data = await self.get_events(
                    active=True,
                    closed=False,
                    limit=100,
                    offset=page * 100,
                )
            except httpx.HTTPStatusError as e:
                logger.warning("Error fetching events page %d: %s", page, e)
                break

            if not events_data:
                break

            for event_data in events_data:
                event_id = str(event_data.get("id", ""))
                if event_id and event_id not in seen_ids:
                    seen_ids.add(event_id)
                    parsed = self._parse_event(event_data)
                    if parsed and parsed.markets:
                        all_events.append(parsed)

            if len(events_data) < 100:
                break

        logger.info(
            "Polymarket: fetched %d active events (all categories) across %d pages",
            len(all_events),
            min(page + 1, max_pages),
        )
        return all_events

    async def get_events_by_tag(
        self,
        tag_id: str,
        max_pages: int = 5,
    ) -> list[PolymarketEvent]:
        """
        Fetch active events for a specific tag/category.

        Useful for non-sports categories (politics, entertainment, etc.).
        """
        import asyncio

        all_events: list[PolymarketEvent] = []
        offset = 0

        for page in range(max_pages):
            if page > 0:
                await asyncio.sleep(0.2)

            try:
                events_data = await self.get_events(
                    active=True,
                    closed=False,
                    tag_id=tag_id,
                    limit=100,
                    offset=offset,
                )
            except httpx.HTTPStatusError as e:
                logger.warning("Error fetching tag %s page %d: %s", tag_id, page, e)
                break

            if not events_data:
                break

            for event_data in events_data:
                parsed = self._parse_event(event_data)
                if parsed and parsed.markets:
                    all_events.append(parsed)

            if len(events_data) < 100:
                break
            offset += 100

        return all_events

    # =========================================================================
    # Parsing
    # =========================================================================

    def _parse_event(self, event_data: dict) -> Optional[PolymarketEvent]:
        """Parse raw event data into PolymarketEvent."""
        try:
            markets = []
            for market_data in event_data.get("markets", []):
                market = self._parse_market(market_data)
                if market:
                    markets.append(market)

            # Parse tags (can be list of dicts or list of strings)
            raw_tags = event_data.get("tags", [])
            tags = []
            for tag in raw_tags:
                if isinstance(tag, dict):
                    tags.append(tag.get("label", ""))
                elif isinstance(tag, str):
                    tags.append(tag)

            return PolymarketEvent(
                id=str(event_data.get("id", "")),
                title=event_data.get("title", ""),
                slug=event_data.get("slug"),
                description=event_data.get("description"),
                active=event_data.get("active", True),
                closed=event_data.get("closed", False),
                archived=event_data.get("archived", False),
                tags=[t for t in tags if t],
                start_date=self._parse_timestamp(event_data.get("startDate")),
                end_date=self._parse_timestamp(event_data.get("endDate")),
                creation_date=self._parse_timestamp(event_data.get("creationDate")),
                neg_risk=event_data.get("negRisk", False),
                markets=markets,
                volume=self._safe_float(event_data.get("volume")),
                liquidity=self._safe_float(event_data.get("liquidity")),
            )
        except Exception as e:
            logger.warning("Error parsing Polymarket event: %s", e)
            return None

    def _parse_market(self, market_data: dict) -> Optional[PolymarketMarket]:
        """Parse raw market data into PolymarketMarket."""
        try:
            # Critical: outcomes, outcomePrices, clobTokenIds are stringified JSON
            outcomes = self._parse_json_string_array(
                market_data.get("outcomes", "[]")
            )
            outcome_prices = [
                float(p) for p in self._parse_json_string_array(
                    market_data.get("outcomePrices", "[]")
                )
            ]
            clob_token_ids = self._parse_json_string_array(
                market_data.get("clobTokenIds", "[]")
            )

            return PolymarketMarket(
                condition_id=market_data.get("conditionId", ""),
                question=market_data.get("question", ""),
                slug=market_data.get("slug"),
                group_item_title=market_data.get("groupItemTitle"),
                outcomes=outcomes,
                outcome_prices=outcome_prices,
                clob_token_ids=clob_token_ids,
                active=market_data.get("active", True),
                closed=market_data.get("closed", False),
                accepting_orders=market_data.get("acceptingOrders", True),
                last_trade_price=self._safe_float(
                    market_data.get("lastTradePrice")
                ),
                best_bid=self._safe_float(market_data.get("bestBid")),
                best_ask=self._safe_float(market_data.get("bestAsk")),
                volume=self._safe_float(market_data.get("volume")),
                volume_24h=self._safe_float(market_data.get("volume24hr")),
                liquidity=self._safe_float(market_data.get("liquidity")),
                neg_risk=market_data.get("negRisk", False),
            )
        except Exception as e:
            logger.warning("Error parsing Polymarket market: %s", e)
            return None

    @staticmethod
    def _parse_json_string_array(value) -> list[str]:
        """
        Parse Polymarket's stringified JSON arrays.

        Polymarket returns fields like outcomes as '"[\\"Yes\\", \\"No\\"]"'
        instead of proper JSON arrays. This handles both formats.
        """
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(v) for v in parsed]
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    @staticmethod
    def _parse_timestamp(ts) -> Optional[datetime]:
        """Parse various timestamp formats to datetime."""
        if not ts:
            return None
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                if ts.endswith("Z"):
                    ts = ts[:-1] + "+00:00"
                return datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                pass
        if isinstance(ts, (int, float)):
            try:
                return datetime.fromtimestamp(ts)
            except (ValueError, OSError):
                pass
        return None

    @staticmethod
    def _safe_float(value) -> Optional[float]:
        """Safely convert a value to float."""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# Convenience function for one-off fetches
async def fetch_polymarket_events() -> list[PolymarketEvent]:
    """Fetch all active events from Polymarket."""
    service = PolymarketAPIService()
    try:
        return await service.get_all_active_events()
    finally:
        await service.close()
