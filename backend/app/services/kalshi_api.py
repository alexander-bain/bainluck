"""
Kalshi API integration service.

Handles fetching prediction market data from Kalshi's trading API.
Kalshi markets provide bid/ask spreads and last traded prices.
"""

import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from app.services.base_api import BaseAPIClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)


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


class KalshiAPIService(BaseAPIClient):
    """Service for interacting with Kalshi's Trading API."""

    BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

    SPORTS_CATEGORIES = ["Sports"]
    SPORTS_TAGS = ["Olympics", "Winter Olympics", "Football", "Basketball", "Baseball", "Hockey", "Golf", "Tennis", "Soccer"]

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("KALSHI_API_KEY")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        super().__init__(timeout=30.0, headers=headers)

    async def get_events(
        self,
        status: Optional[str] = "open",
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """
        Get events from Kalshi.

        Note: The events endpoint does NOT support category filtering.
        Use series_ticker to filter events by series instead.

        Args:
            status: Filter by status ('open', 'closed', 'settled')
            series_ticker: Filter to events in a specific series
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
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get(
            f"{self.BASE_URL}/events",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        events = data.get("events") or []
        next_cursor = data.get("cursor")

        return events, next_cursor

    async def get_series(
        self,
        category: Optional[str] = None,
        tags: Optional[str] = None,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> tuple[list[dict], Optional[str]]:
        """
        Get series from Kalshi. Series support category and tags filtering.

        Args:
            category: Filter by category (e.g., "Sports")
            tags: Comma-separated tags to filter by (e.g., "Olympics,Winter Olympics")
            limit: Max results per page
            cursor: Pagination cursor

        Returns:
            Tuple of (series list, next cursor or None)
        """
        params = {"limit": min(limit, 200)}
        if category:
            params["category"] = category
        if tags:
            params["tags"] = tags
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get(
            f"{self.BASE_URL}/series",
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        series = data.get("series") or []
        next_cursor = data.get("cursor")

        return series, next_cursor

    async def get_tags_by_categories(self) -> dict:
        """
        Get tags organized by series categories from Kalshi's search API.

        Returns a mapping of category names to their associated tags.
        This reveals subcategories like Olympics under Sports.
        """
        response = await self.client.get(
            f"{self.BASE_URL}/search/tags_by_categories",
        )
        response.raise_for_status()
        return response.json()

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

        markets = data.get("markets") or []
        next_cursor = data.get("cursor")

        return markets, next_cursor

    async def _discover_series_tickers(
        self,
        categories: list[str],
        tags: Optional[list[str]] = None,
    ) -> list[str]:
        """
        Discover all series tickers for the given categories and tags.

        Strategy:
        1. Query each category (e.g., "Sports") to get all series
        2. Also query each tag within the primary category to find
           subcategory series (e.g., Olympics under Sports)

        Args:
            categories: List of Kalshi category names
            tags: Optional list of tags to search within categories

        Returns:
            Deduplicated list of series tickers
        """
        import asyncio

        tickers: set[str] = set()
        request_count = 0

        # Phase 1: Discover series by category
        for category in categories:
            cursor = None
            page_count = 0
            max_pages = 10
            category_tickers = set()

            try:
                while page_count < max_pages:
                    if request_count > 0:
                        await asyncio.sleep(0.5)

                    series_list, cursor = await self.get_series(
                        category=category,
                        cursor=cursor,
                    )
                    request_count += 1

                    for s in series_list:
                        ticker = s.get("ticker")
                        if ticker:
                            tickers.add(ticker)
                            category_tickers.add(ticker)

                    page_count += 1
                    if not cursor:
                        break

            except Exception as e:
                logger.warning("Error fetching Kalshi series for category %s: %s", category, e)
                continue

            if category_tickers:
                logger.info(
                    "Category '%s': found %d series tickers: %s",
                    category, len(category_tickers),
                    sorted(category_tickers)[:20],
                )
            else:
                logger.info("Category '%s': no series found (empty or null response)", category)

        # Phase 2: Discover additional series by tags (subcategories)
        if tags:
            primary_category = categories[0] if categories else None
            for tag in tags:
                cursor = None
                page_count = 0
                max_pages = 5
                tag_tickers = set()

                try:
                    while page_count < max_pages:
                        if request_count > 0:
                            await asyncio.sleep(0.5)

                        series_list, cursor = await self.get_series(
                            category=primary_category,
                            tags=tag,
                            cursor=cursor,
                        )
                        request_count += 1

                        for s in series_list:
                            ticker = s.get("ticker")
                            if ticker and ticker not in tickers:
                                tag_tickers.add(ticker)
                                tickers.add(ticker)

                        page_count += 1
                        if not cursor:
                            break

                except Exception as e:
                    logger.warning("Error fetching Kalshi series for tag '%s': %s", tag, e)
                    continue

                if tag_tickers:
                    logger.info(
                        "Tag '%s': found %d NEW series tickers: %s",
                        tag, len(tag_tickers), sorted(tag_tickers)[:20],
                    )

        logger.info("Discovered %d unique series tickers total (%d API requests)", len(tickers), request_count)
        return sorted(tickers)

    async def get_all_events(
        self,
        categories: Optional[list[str]] = None,
    ) -> list[KalshiEvent]:
        """
        Fetch all open events across specified categories.

        Strategy: The events endpoint does NOT support category filtering.
        Instead, we first discover series tickers via the series endpoint
        (which does support category), then fetch events per series_ticker.

        Args:
            categories: List of Kalshi category names to fetch, or None for all

        Returns:
            List of KalshiEvent objects (deduplicated by event_ticker)
        """
        import asyncio

        # If no categories specified, fetch all events without filtering
        if not categories:
            return await self._fetch_all_events_unfiltered()

        # Step 1: Discover series tickers for these categories + tags
        # Tags find subcategory series (e.g., Olympics under Sports)
        series_tickers = await self._discover_series_tickers(
            categories, tags=self.SPORTS_TAGS
        )

        if not series_tickers:
            logger.warning("No series tickers found for categories: %s", categories)
            return []

        # Step 2: Fetch events per series_ticker
        all_events: dict[str, KalshiEvent] = {}  # Dedup by event_ticker
        request_count = 0
        max_pages_per_series = 5

        for series_ticker in series_tickers:
            cursor = None
            page_count = 0

            try:
                while page_count < max_pages_per_series:
                    if request_count > 0:
                        await asyncio.sleep(0.5)

                    events, cursor = await self.get_events(
                        status="open",
                        series_ticker=series_ticker,
                        with_nested_markets=True,
                        cursor=cursor,
                    )
                    request_count += 1

                    for event_data in events:
                        parsed_event = self._parse_event(event_data)
                        if parsed_event:
                            all_events[parsed_event.event_ticker] = parsed_event

                    page_count += 1
                    if not cursor:
                        break

            except Exception as e:
                logger.warning("Error fetching Kalshi events for series %s: %s", series_ticker, e)
                continue

        logger.info(
            "Fetched %d unique events from %d series (%d API requests)",
            len(all_events), len(series_tickers), request_count,
        )
        return list(all_events.values())

    async def _fetch_all_events_unfiltered(self) -> list[KalshiEvent]:
        """Fetch all events from Kalshi without category filtering (paginated).

        Kalshi neg-risk events (championships, conferences) can have
        status=None even when they have open markets. Omitting the status
        filter ensures we discover them.
        """
        import asyncio

        all_events: dict[str, KalshiEvent] = {}  # Dedup by event_ticker
        cursor = None
        page_count = 0
        max_pages = 50
        categories_seen: dict[str, int] = {}

        while page_count < max_pages:
            if page_count > 0:
                await asyncio.sleep(0.5)

            events, cursor = await self.get_events(
                status=None,
                with_nested_markets=True,
                cursor=cursor,
            )

            for event_data in events:
                nested = event_data.get("markets", [])
                if nested and all(m.get("status") == "finalized" for m in nested):
                    continue
                parsed_event = self._parse_event(event_data)
                if parsed_event:
                    all_events[parsed_event.event_ticker] = parsed_event
                    cat = parsed_event.category or "unknown"
                    categories_seen[cat] = categories_seen.get(cat, 0) + 1

            page_count += 1
            if not cursor:
                break

        logger.info(
            "Fetched %d unique events across %d pages. Categories: %s",
            len(all_events), page_count, dict(sorted(categories_seen.items())),
        )

        # Supplementary fetch: Kalshi neg-risk sports events can have
        # status=None and may not appear in the first N pages of the
        # unfiltered listing. Explicitly query key sports series tickers
        # to guarantee we don't miss championship/conference markets.
        _SPORTS_SERIES_TICKERS = [
            # Championship / conference
            "KXNBA", "KXNBAEAST", "KXNBAWEST",
            "KXNHL", "KXNHLEAST", "KXNHLWEST",
            "KXMLB", "KXMLBAL", "KXMLBNL",
            "KXNFL", "KXNFLNFC", "KXNFLAFC",
            # Game-level (neg-risk, status=None — missed by unfiltered pagination)
            "KXNBASPREAD", "KXNBATOTAL", "KXNBATEAMTOTAL",
            "KXNBA1HSPREAD", "KXNBA1HTOTAL", "KXNBA1HWINNER",
            "KXNBA2HSPREAD", "KXNBA2HTOTAL", "KXNBA2HWINNER",
            "KXNBASERIES",
            "KXNHLSPREAD", "KXNHLTOTAL", "KXNHLTEAMTOTAL",
            "KXNHL1HSPREAD", "KXNHL1HTOTAL", "KXNHLSERIES",
            "KXMLBSPREAD", "KXMLBTOTAL", "KXMLBTEAMTOTAL",
            "KXMLB1HSPREAD", "KXMLB1HTOTAL", "KXMLBSERIES",
            "KXNFLSPREAD", "KXNFLTOTAL", "KXNFLTEAMTOTAL",
            "KXNFL1HSPREAD", "KXNFL1HTOTAL", "KXNFL2HSPREAD", "KXNFL2HTOTAL",
            "KXNFLSERIES",
        ]
        supplemented = 0
        for st in _SPORTS_SERIES_TICKERS:
            if any(e.event_ticker.upper().startswith(st.upper()) for e in all_events.values()):
                continue
            try:
                await asyncio.sleep(0.3)
                events_page, _ = await self.get_events(
                    status=None,
                    series_ticker=st,
                    with_nested_markets=True,
                    limit=50,
                )
                for event_data in events_page:
                    nested = event_data.get("markets", [])
                    if nested and all(m.get("status") == "finalized" for m in nested):
                        continue
                    parsed_event = self._parse_event(event_data)
                    if parsed_event and parsed_event.event_ticker not in all_events:
                        all_events[parsed_event.event_ticker] = parsed_event
                        supplemented += 1
            except Exception as e:
                logger.debug("Supplementary fetch for %s failed: %s", st, e)
        if supplemented:
            logger.info("Supplementary series fetch added %d events", supplemented)

        # Backfill: for events with 0 nested markets (Kalshi sometimes omits
        # them from the listing for large multivariate events), fetch markets
        # separately via the /markets endpoint.
        import asyncio
        empty_events = [
            e for e in all_events.values()
            if not e.markets and e.category and "sport" in (e.category or "").lower()
        ]
        if empty_events:
            logger.info(
                "Backfilling markets for %d sports events with 0 nested markets",
                len(empty_events),
            )
            backfilled = 0
            for event in empty_events:
                try:
                    await asyncio.sleep(0.3)
                    raw_markets, _ = await self.get_markets(
                        status=None,
                        event_ticker=event.event_ticker,
                        limit=200,
                    )
                    if raw_markets:
                        parsed = [self._parse_market(m) for m in raw_markets]
                        event.markets = [m for m in parsed if m is not None]
                        if event.markets:
                            backfilled += 1
                except Exception as e:
                    logger.warning(
                        "Failed to backfill markets for %s: %s",
                        event.event_ticker, e,
                    )
            logger.info("Backfilled markets for %d events", backfilled)

        return list(all_events.values())

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

            # Kalshi API v2 returns prices in two possible formats:
            # - Old format: yes_bid, yes_ask, last_price as integers in cents (0-100)
            # - New format: yes_bid_dollars, yes_ask_dollars, last_price_dollars as
            #   string dollar amounts ("0.0100" = 1 cent = 1% probability)
            # We try the new dollar fields first, falling back to old cent fields.
            def to_decimal(val):
                """Convert a cents-based integer (0-100) to decimal (0-1)."""
                if val is None:
                    return None
                if isinstance(val, float) and val <= 1:
                    return val
                return val / 100.0

            def parse_dollar_str(val) -> Optional[float]:
                """Parse a dollar string ('0.0100') to decimal probability.

                Returns 0.0 for '0.0000' — a $0.00 bid is a valid data point
                (no one is bidding), not missing data. Consumers (grids, display)
                handle noise filtering at their level.
                """
                if val is None or val == "":
                    return None
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            # Prefer new *_dollars fields, fall back to old cent-based fields.
            # Use explicit None checks — 0.0 is a valid value (no bid placed).
            def _prefer_dollars(dollars_key: str, cents_key: str) -> Optional[float]:
                v = parse_dollar_str(market_data.get(dollars_key))
                if v is not None:
                    return v
                return to_decimal(market_data.get(cents_key))

            yes_bid = _prefer_dollars("yes_bid_dollars", "yes_bid")
            yes_ask = _prefer_dollars("yes_ask_dollars", "yes_ask")
            no_bid = _prefer_dollars("no_bid_dollars", "no_bid")
            no_ask = _prefer_dollars("no_ask_dollars", "no_ask")
            last_price = _prefer_dollars("last_price_dollars", "last_price")

            # Volume/open_interest also have new *_fp string fields
            def parse_int_str(val) -> Optional[int]:
                if val is None or val == "":
                    return None
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return None

            volume = parse_int_str(market_data.get("volume_fp")) or market_data.get("volume")
            volume_24h = parse_int_str(market_data.get("volume_24h_fp")) or market_data.get("volume_24h")
            open_interest = parse_int_str(market_data.get("open_interest_fp")) or market_data.get("open_interest")

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
                yes_bid=yes_bid,
                yes_ask=yes_ask,
                no_bid=no_bid,
                no_ask=no_ask,
                last_price=last_price,
                volume=volume,
                volume_24h=volume_24h,
                open_interest=open_interest,
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
