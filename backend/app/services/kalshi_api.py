"""
Kalshi API integration service.

Handles fetching prediction market data from Kalshi's trading API.
Kalshi markets provide bid/ask spreads and last traded prices.
"""

import os
from datetime import datetime
from typing import Optional

import httpx
from pydantic import BaseModel


class KalshiMarket(BaseModel):
    """Represents a single Kalshi market (binary outcome)."""
    ticker: str
    event_ticker: str
    title: str
    subtitle: Optional[str] = None
    yes_sub_title: Optional[str] = None
    no_sub_title: Optional[str] = None
    status: str  # 'active', 'closed', 'settled'

    # Timing
    open_time: Optional[datetime] = None
    close_time: Optional[datetime] = None
    expiration_time: Optional[datetime] = None

    # Pricing (as decimals 0-1)
    yes_bid: Optional[float] = None
    yes_ask: Optional[float] = None
    no_bid: Optional[float] = None
    no_ask: Optional[float] = None
    last_price: Optional[float] = None

    # Volume
    volume: Optional[int] = None
    volume_24h: Optional[int] = None
    open_interest: Optional[int] = None

    # Result (if settled)
    result: Optional[str] = None  # 'yes', 'no', None


class KalshiEvent(BaseModel):
    """Represents a Kalshi event containing one or more markets."""
    event_ticker: str
    title: str
    subtitle: Optional[str] = None
    category: Optional[str] = None
    mutually_exclusive: bool = True

    # Nested markets
    markets: list[KalshiMarket] = []


class KalshiAPIService:
    """Service for interacting with Kalshi's Trading API."""

    # Production API (despite "elections" in URL, serves all markets)
    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

    # Categories we're interested in
    SPORTS_CATEGORIES = ["Sports", "Golf", "Football", "Basketball", "Baseball", "Hockey", "Soccer", "Tennis", "Olympics"]

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with API key from env or parameter.

        Kalshi API key should be set as KALSHI_API_KEY environment variable.
        """
        self.api_key = api_key or os.getenv("KALSHI_API_KEY")

        # Build headers
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers=headers,
        )

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_events(
        self,
        status: Optional[str] = "open",
        category: Optional[str] = None,
        with_nested_markets: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """
        Get events from Kalshi.

        Args:
            status: Filter by status ('open', 'closed', 'settled')
            category: Filter by category
            with_nested_markets: Include nested market data
            limit: Max results per page (1-200)
            cursor: Pagination cursor

        Returns:
            Tuple of (events list, next cursor or None)
        """
        params = {
            "limit": min(limit, 200),
            "with_nested_markets": str(with_nested_markets).lower(),
        }
        if status:
            params["status"] = status
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get(
            f"{self.BASE_URL}/events",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        events = data.get("events", [])
        next_cursor = data.get("cursor")

        return events, next_cursor

    async def get_markets(
        self,
        status: Optional[str] = "open",
        event_ticker: Optional[str] = None,
        limit: int = 1000,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """
        Get markets from Kalshi.

        Args:
            status: Filter by status ('open', 'closed', 'settled')
            event_ticker: Filter to specific event
            limit: Max results per page (1-1000)
            cursor: Pagination cursor

        Returns:
            Tuple of (markets list, next cursor or None)
        """
        params = {
            "limit": min(limit, 1000),
        }
        if status:
            params["status"] = status
        if event_ticker:
            params["event_ticker"] = event_ticker
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get(
            f"{self.BASE_URL}/markets",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        markets = data.get("markets", [])
        next_cursor = data.get("cursor")

        return markets, next_cursor

    async def get_all_sports_events(self) -> list[KalshiEvent]:
        """
        Fetch all open sports-related events with their markets.

        Returns:
            List of KalshiEvent objects with nested markets
        """
        all_events = []

        for category in self.SPORTS_CATEGORIES:
            try:
                cursor = None
                while True:
                    events, cursor = await self.get_events(
                        status="open",
                        category=category,
                        with_nested_markets=True,
                        cursor=cursor,
                    )

                    for event_data in events:
                        parsed_event = self._parse_event(event_data)
                        if parsed_event and parsed_event.markets:
                            all_events.append(parsed_event)

                    if not cursor:
                        break

            except httpx.HTTPStatusError as e:
                print(f"Error fetching Kalshi category {category}: {e}")
                continue

        return all_events

    async def get_all_events(
        self,
        categories: Optional[list[str]] = None,
    ) -> list[KalshiEvent]:
        """
        Fetch all open events across specified categories.

        Args:
            categories: List of categories to fetch, or None for all

        Returns:
            List of KalshiEvent objects
        """
        import asyncio

        all_events = []
        cursor = None
        page_count = 0
        max_pages = 10  # Limit to avoid rate limits

        while page_count < max_pages:
            # Add delay between requests to avoid rate limiting
            if page_count > 0:
                await asyncio.sleep(0.5)

            events, cursor = await self.get_events(
                status="open",
                with_nested_markets=True,
                cursor=cursor,
            )

            for event_data in events:
                # Filter by category if specified
                if categories:
                    event_category = event_data.get("category", "")
                    if not any(cat.lower() in event_category.lower() for cat in categories):
                        continue

                parsed_event = self._parse_event(event_data)
                if parsed_event:
                    all_events.append(parsed_event)

            page_count += 1

            if not cursor:
                break

        return all_events

    def _parse_event(self, event_data: dict) -> Optional[KalshiEvent]:
        """Parse raw event data into KalshiEvent object."""
        try:
            markets = []
            for market_data in event_data.get("markets", []):
                market = self._parse_market(market_data)
                if market:
                    markets.append(market)

            return KalshiEvent(
                event_ticker=event_data.get("event_ticker", ""),
                title=event_data.get("title", ""),
                subtitle=event_data.get("sub_title"),
                category=event_data.get("category"),
                mutually_exclusive=event_data.get("mutually_exclusive", True),
                markets=markets,
            )
        except Exception as e:
            print(f"Error parsing Kalshi event: {e}")
            return None

    def _parse_market(self, market_data: dict) -> Optional[KalshiMarket]:
        """Parse raw market data into KalshiMarket object."""
        try:
            # Parse timestamps
            open_time = self._parse_timestamp(market_data.get("open_time"))
            close_time = self._parse_timestamp(market_data.get("close_time"))
            expiration_time = self._parse_timestamp(market_data.get("expiration_time"))

            # Kalshi prices are in cents (0-100), convert to decimal (0-1)
            def to_decimal(val):
                if val is None:
                    return None
                # If it's already a decimal < 1, return as-is
                if isinstance(val, float) and val <= 1:
                    return val
                # Otherwise assume it's cents (0-100)
                return val / 100.0

            return KalshiMarket(
                ticker=market_data.get("ticker", ""),
                event_ticker=market_data.get("event_ticker", ""),
                title=market_data.get("title", ""),
                subtitle=market_data.get("subtitle"),
                yes_sub_title=market_data.get("yes_sub_title"),
                no_sub_title=market_data.get("no_sub_title"),
                status=market_data.get("status", ""),
                open_time=open_time,
                close_time=close_time,
                expiration_time=expiration_time,
                yes_bid=to_decimal(market_data.get("yes_bid")),
                yes_ask=to_decimal(market_data.get("yes_ask")),
                no_bid=to_decimal(market_data.get("no_bid")),
                no_ask=to_decimal(market_data.get("no_ask")),
                last_price=to_decimal(market_data.get("last_price")),
                volume=market_data.get("volume"),
                volume_24h=market_data.get("volume_24h"),
                open_interest=market_data.get("open_interest"),
                result=market_data.get("result"),
            )
        except Exception as e:
            print(f"Error parsing Kalshi market: {e}")
            return None

    def _parse_timestamp(self, ts: Optional[str]) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime."""
        if not ts:
            return None
        try:
            # Handle both formats: with and without Z suffix
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.fromisoformat(ts)
        except Exception:
            return None


# Convenience function for one-off fetches
async def fetch_kalshi_events(categories: Optional[list[str]] = None) -> list[KalshiEvent]:
    """Fetch Kalshi events for specified categories."""
    service = KalshiAPIService()
    try:
        return await service.get_all_events(categories=categories)
    finally:
        await service.close()
