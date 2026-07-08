"""
Kalshi API integration service.

Handles fetching prediction market data from Kalshi's trading API.
Kalshi markets provide bid/ask spreads and last traded prices.
"""

import logging
import os
from datetime import datetime
from typing import Callable, Optional

import httpx

from app.services.base_api import BaseAPIClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# #995 attempt-10: decode Kalshi responses with orjson when available. stdlib
# json.loads holds the GIL for the ENTIRE parse of a giant nested-markets page
# (~67s observed on a 200-event page), which freezes the asyncio event loop so
# no wait_for/deadline timer can fire — the confirmed mechanism behind the
# month-long creation freeze. orjson parses ~5-10x faster, so the GIL is held a
# fraction of the time. Import behind a guard: a missing wheel degrades to json
# (still correct, just slower), never crashes.
try:
    import orjson as _orjson

    def _decode_json(raw: bytes):
        return _orjson.loads(raw)

    _HAS_ORJSON = True
except ImportError:  # pragma: no cover - exercised only where orjson is absent
    import json as _json

    def _decode_json(raw: bytes):
        return _json.loads(raw)

    _HAS_ORJSON = False


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
        # #995 attempt-5: EXPLICIT per-phase timeouts. The plain `timeout=30.0`
        # left the poll stuck in the FETCH phase to the 660s SIGKILL (attempt-4
        # phase marker read `fetch@0s`). A generic scalar timeout resets its read
        # window on every received byte, so a huge nested-markets response that
        # trickles never trips it. An explicit read timeout + short connect
        # timeout bounds each call hard; the wall-time cap in poll_kalshi is the
        # backstop for anything that still slips through.
        super().__init__(
            timeout=httpx.Timeout(connect=10.0, read=25.0, write=10.0, pool=10.0),
            headers=headers,
        )

    async def get_events(
        self,
        status: Optional[str] = "open",
        series_ticker: Optional[str] = None,
        with_nested_markets: bool = True,
        limit: int = 200,
        cursor: Optional[str] = None,
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
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
            deadline: Optional time.monotonic() deadline. The retry/backoff span
                is bounded by it — once reached, return ([], cursor) instead of
                sleeping/retrying. #969: a settled-backfill page must not let the
                429-backoff retry span overrun the caller's time budget (the
                nested caller-3 × internal-4 retries could burn ~165s of sleeps
                and push the task past its 900s soft wall). Returns the INPUT
                cursor so the caller resumes/re-fetches this same page next run.

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

        import asyncio as _asyncio
        import time as _time

        def _tick(sub: str) -> None:
            # #995 attempt-9: fine-grained markers INSIDE get_events. attempt-8's
            # trigger-proof showed the loop freezes on a small nested=False page
            # even after decode moved off-thread — so the residual block is one of
            # these exact ops. If the poll still freezes, the marker names WHICH
            # (client.get vs decode) for attempt-10. Safe now that the marker
            # client is socket-timeout-bounded (can't itself freeze the loop).
            if progress_cb is not None:
                try:
                    progress_cb(sub)
                except Exception:
                    pass

        for _attempt in range(4):
            # #969: never start another attempt past the deadline.
            if deadline is not None and _time.monotonic() >= deadline:
                return [], cursor
            _tick(f"get_events:req:a{_attempt}")
            response = await self.client.get(
                f"{self.BASE_URL}/events",
                params=params,
            )
            _tick(f"get_events:resp:{response.status_code}")
            if response.status_code == 429:
                # #969: cap the backoff (was 5/10/15/20 = up to 50s) and never
                # sleep past the deadline.
                _backoff = min(5 * (_attempt + 1), 10)
                if deadline is not None:
                    _backoff = min(_backoff, max(0.0, deadline - _time.monotonic()))
                    if _backoff <= 0:
                        return [], cursor
                await _asyncio.sleep(_backoff)
                continue
            response.raise_for_status()
            # #995 attempt-8→10: decode the nested-markets payload with orjson.
            # attempt-8 moved response.json() to a thread believing that freed the
            # loop, but the C json parser NEVER releases the GIL — so a 200-event
            # nested page held the GIL ~67s inside the thread, freezing the loop
            # anyway (marker pinned at `get_events:decode:done@67s`, past the
            # wait_for(45s) bound it could never fire). orjson decodes the same
            # payload ~5-10x faster (sub-second GIL hold at limit=50), so wait_for/
            # deadline timers actually run between pages. to_thread still wraps it
            # as belt-and-suspenders for the rare huge page.
            _tick("get_events:decode:start")
            data = await _asyncio.to_thread(_decode_json, response.content)
            _tick("get_events:decode:done")

            events = data.get("events") or []
            next_cursor = data.get("cursor")

            return events, next_cursor

        response.raise_for_status()
        return [], None

    async def get_event(
        self,
        event_ticker: str,
        with_nested_markets: bool = True,
    ) -> Optional[dict]:
        """Get a single event by ticker. Returns None only for 404."""
        import asyncio as _asyncio
        params = {"with_nested_markets": str(with_nested_markets).lower()}
        for _attempt in range(3):
            try:
                response = await self.client.get(
                    f"{self.BASE_URL}/events/{event_ticker}",
                    params=params,
                )
                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    await _asyncio.sleep(3 * (_attempt + 1))
                    continue
                response.raise_for_status()
                return response.json().get("event")
            except Exception:
                if _attempt < 2:
                    await _asyncio.sleep(1)
                    continue
                return None
        return None

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

    async def get_market(self, ticker: str) -> Optional[dict]:
        """Get a single market by ticker. Returns None only for 404."""
        import asyncio as _asyncio
        for _attempt in range(3):
            try:
                response = await self.client.get(
                    f"{self.BASE_URL}/markets/{ticker}",
                )
                if response.status_code == 404:
                    return None
                if response.status_code == 429:
                    await _asyncio.sleep(3 * (_attempt + 1))
                    continue
                response.raise_for_status()
                return response.json().get("market")
            except Exception:
                if _attempt < 2:
                    await _asyncio.sleep(1)
                    continue
                return None
        return None

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

    async def get_market_candlesticks(
        self,
        ticker: str,
        period_interval: int = 60,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict]:
        """Get historical candlestick data for a market.

        Uses the batch endpoint GET /markets/candlesticks (the old per-market
        endpoint /markets/{ticker}/candlesticks was deprecated).

        Args:
            ticker: Market ticker
            period_interval: Candle width in minutes (1, 5, 15, 60, 1440)
            start_ts: Unix timestamp for start of range (default: 90 days ago)
            end_ts: Unix timestamp for end of range (default: now)

        Returns:
            List of normalized dicts with "t" (unix_ts) and "yes_price" (0-1 float)
        """
        import time as _time
        if start_ts is None:
            start_ts = int(_time.time()) - 90 * 86400
        if end_ts is None:
            end_ts = int(_time.time())

        try:
            response = await self.client.get(
                f"{self.BASE_URL}/markets/candlesticks",
                params={
                    "market_tickers": ticker,
                    "period_interval": period_interval,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                },
            )
            response.raise_for_status()
            data = response.json()

            raw_markets = data.get("markets", [])
            if not raw_markets:
                return []

            raw_candles = raw_markets[0].get("candlesticks", [])
            normalized = []
            for c in raw_candles:
                ts = c.get("end_period_ts")
                if ts is None:
                    continue
                yes_bid = c.get("yes_bid", {})
                yes_ask = c.get("yes_ask", {})
                try:
                    bid = float(yes_bid.get("close_dollars") or 0)
                    ask = float(yes_ask.get("close_dollars") or 0)
                except (ValueError, TypeError):
                    continue
                if bid > 0 and ask > 0:
                    price = (bid + ask) / 2
                elif ask > 0:
                    price = ask
                elif bid > 0:
                    price = bid
                else:
                    continue
                normalized.append({"t": ts, "yes_price": price})
            return normalized
        except Exception as e:
            logger.warning("Failed to get candlesticks for %s: %s", ticker, e)
            return []

    async def get_market_trades(
        self,
        ticker: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[dict], str | None]:
        """Get trade history for a market.

        Returns list of trades with created_time, yes_price_dollars, count_fp.
        Works for settled markets (unlike candlesticks) but Kalshi purges
        older trade data — returns empty for old markets.
        """
        params: dict = {"ticker": ticker, "limit": min(limit, 100)}
        if cursor:
            params["cursor"] = cursor

        response = await self.client.get(
            f"{self.BASE_URL}/markets/trades",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("trades", []), data.get("cursor") or None

    async def get_market_candlesticks_batch(
        self,
        tickers: list[str],
        period_interval: int = 60,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> dict[str, list[dict]]:
        """Get candlestick data for multiple markets in one API call.

        Returns dict of ticker → normalized candle list.
        """
        import time as _time
        if start_ts is None:
            start_ts = int(_time.time()) - 90 * 86400
        if end_ts is None:
            end_ts = int(_time.time())

        try:
            ticker_str = ",".join(tickers)
            url = (
                f"{self.BASE_URL}/markets/candlesticks"
                f"?market_tickers={ticker_str}"
                f"&period_interval={period_interval}"
                f"&start_ts={start_ts}"
                f"&end_ts={end_ts}"
            )
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()

            results: dict[str, list[dict]] = {}
            for market in data.get("markets", []):
                ticker = market.get("market_ticker", "")
                normalized = []
                for c in market.get("candlesticks", []):
                    ts = c.get("end_period_ts")
                    if ts is None:
                        continue
                    yes_bid = c.get("yes_bid", {})
                    yes_ask = c.get("yes_ask", {})
                    try:
                        bid = float(yes_bid.get("close_dollars") or 0)
                        ask = float(yes_ask.get("close_dollars") or 0)
                    except (ValueError, TypeError):
                        continue
                    if bid > 0 and ask > 0:
                        price = (bid + ask) / 2
                    elif ask > 0:
                        price = ask
                    elif bid > 0:
                        price = bid
                    else:
                        continue
                    normalized.append({"t": ts, "yes_price": price})
                results[ticker] = normalized
            return results
        except Exception as e:
            logger.warning("Failed to get batch candlesticks: %s", e)
            return {}

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
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
        start_cursor: Optional[str] = None,
        save_cursor: Optional[Callable[[Optional[str]], None]] = None,
    ) -> list[KalshiEvent]:
        """
        Fetch all open events across specified categories.

        Strategy: The events endpoint does NOT support category filtering.
        Instead, we first discover series tickers via the series endpoint
        (which does support category), then fetch events per series_ticker.

        Args:
            categories: List of Kalshi category names to fetch, or None for all
            deadline: Optional time.monotonic() budget. When set, fetching stops
                and returns whatever has been collected so far once reached, so
                the caller (poll_kalshi) never SIGKILLs mid-fetch and always has
                time left to process+commit (#995). Checked before each page —
                the LONGEST single uninterrupted op is one page fetch.

        Returns:
            List of KalshiEvent objects (deduplicated by event_ticker)
        """
        import asyncio

        # If no categories specified, fetch all events without filtering
        if not categories:
            return await self._fetch_all_events_unfiltered(
                deadline=deadline, progress_cb=progress_cb,
                start_cursor=start_cursor, save_cursor=save_cursor,
            )

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

    # #995 attempt-10: smaller nested pages. A 200-event nested-markets page
    # decoded in ~67s (GIL-held) and froze the loop. 50 events/page keeps each
    # decode sub-second (with orjson) so wait_for/deadline timers stay live.
    _MAIN_SCAN_PAGE_LIMIT = 50

    async def _fetch_all_events_unfiltered(
        self,
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
        start_cursor: Optional[str] = None,
        save_cursor: Optional[Callable[[Optional[str]], None]] = None,
    ) -> list[KalshiEvent]:
        """Fetch all events from Kalshi without category filtering (paginated).

        Kalshi neg-risk events (championships, conferences) can have
        status=None even when they have open markets. Omitting the status
        filter ensures we discover them.

        ``deadline`` (time.monotonic()) bounds total fetch time (#995): this
        method is otherwise uncapped (main scan + a supplementary series
        loop) and blew poll_kalshi's 660s hard limit → SIGKILL mid-fetch → a
        month of zero market creation. The deadline is checked BEFORE every page
        (a page is the longest single uninterrupted op — budget-guard-inner-op),
        so we always return what we have with time left for the caller to
        process+commit.

        ``start_cursor`` / ``save_cursor`` (#995 attempt-10): a RESUMABLE main-scan
        cursor. With smaller pages the deadline truncates the scan mid-listing;
        without resume the next run would re-scan the same head pages forever and
        never reach the long tail. The caller persists ``save_cursor(cursor)`` in
        Redis and feeds it back as ``start_cursor`` next run, so successive beats
        page THROUGH the full listing (draining the backlog) and a SIGKILL/wall
        loses nothing — the next beat continues where this one stopped. When the
        listing is exhausted the saved cursor is None, so the scan wraps to the
        head next run.
        """
        import asyncio
        import time as _time

        def _past_deadline() -> bool:
            return deadline is not None and _time.monotonic() >= deadline

        def _progress(sub: str) -> None:
            # #995 attempt-5 sub-phase marker: names the exact fetch call in
            # flight, so if the poll still SIGKILLs the next run pinpoints the
            # hanging page/endpoint (not just "fetch").
            if progress_cb is not None:
                try:
                    progress_cb(sub)
                except Exception:
                    pass

        all_events: dict[str, KalshiEvent] = {}  # Dedup by event_ticker
        cursor = start_cursor or None
        page_count = 0
        max_pages = 100
        categories_seen: dict[str, int] = {}

        while page_count < max_pages:
            _progress(f"fetch:unfiltered:p{page_count}")
            if _past_deadline():
                logger.warning(
                    "Kalshi fetch deadline hit during main scan at page %d "
                    "(%d events so far) — returning partial", page_count, len(all_events),
                )
                break
            if page_count > 0:
                await asyncio.sleep(0.5)

            # #995 attempt-6: the poll consistently froze at `fetch:unfiltered:p26`
            # — 26 pages fine, then this call never returns. #128's httpx read
            # timeout (25s) bounds a network stall, but NOT a huge-response
            # download/parse. Wrap each page in a hard per-page wait_for so ONE
            # bad page can't hang the whole scan; on timeout/error, mark it and
            # STOP the scan, returning the pages we DID get so the caller reaches
            # the create step (process-new-first) instead of SIGKILLing. Bounds
            # the fetch op the finer marker fingered — does not touch create/dedup.
            try:
                events, cursor = await asyncio.wait_for(
                    self.get_events(
                        status=None,
                        with_nested_markets=True,
                        limit=self._MAIN_SCAN_PAGE_LIMIT,
                        cursor=cursor,
                        deadline=deadline,
                        progress_cb=_progress,
                    ),
                    timeout=45.0,
                )
            except Exception as e:  # asyncio.TimeoutError is an Exception subclass
                _progress(f"fetch:unfiltered:p{page_count}:err")
                logger.error(
                    "Kalshi main-scan page %d failed/timed out (%s) — stopping "
                    "scan with %d events collected so the poll reaches create.",
                    page_count, type(e).__name__, len(all_events),
                )
                break
            _progress(f"fetch:unfiltered:p{page_count}:recv{len(events)}")

            # #995 attempt-9b (live-proof pinpoint): the marker froze EXACTLY at
            # `fetch:unfiltered:pN:recv200` — get_events returned (decode fine,
            # attempt-8 holds) but the PARSE never finished. The per-page
            # wait_for(45s) bounds the fetch/decode but NOT this parse, so a
            # monster nested-markets page (200 events × thousands of markets,
            # minutes of pure-Python object construction) had no time bound and
            # ran the task into the 300s Celery SIGKILL before the create step —
            # the actual cause of the month-long creation freeze. Bound the parse
            # too (off-loop + wait_for); on timeout skip THIS page's events but
            # keep paginating so creation is never starved by one fat page.
            try:
                parsed_events = await asyncio.wait_for(
                    self._parse_events_offloaded(events), timeout=60.0
                )
            except Exception as e:
                _progress(f"fetch:unfiltered:p{page_count}:parse_timeout")
                logger.error(
                    "Kalshi main-scan page %d parse exceeded 60s (%s) — likely a "
                    "monster nested-markets page; skipping its events and "
                    "continuing so the poll still reaches create.",
                    page_count, type(e).__name__,
                )
                parsed_events = []
            for parsed_event in parsed_events:
                if parsed_event:
                    all_events[parsed_event.event_ticker] = parsed_event
                    cat = parsed_event.category or "unknown"
                    categories_seen[cat] = categories_seen.get(cat, 0) + 1

            page_count += 1
            if not cursor:
                break

        # #995 attempt-10: persist the resume point. If the loop ended because the
        # listing was exhausted (`not cursor`), save None so the next run wraps to
        # the head. Otherwise (deadline / max_pages / a page error left `cursor`
        # set) save it so the next beat continues the tail — draining the full
        # listing across runs instead of re-scanning the same head every time.
        if save_cursor is not None:
            try:
                save_cursor(cursor or None)
            except Exception:
                pass

        _progress(f"fetch:unfiltered:done:{page_count}pages")
        logger.info(
            "Fetched %d unique events across %d pages (start_cursor=%s → next=%s). "
            "Categories: %s",
            len(all_events), page_count, bool(start_cursor), bool(cursor),
            dict(sorted(categories_seen.items())),
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
            # Game winner (moneyline) — Kalshi retains settled events forever
            "KXNBAGAME", "KXNHLGAME", "KXMLBGAME", "KXNFLGAME",
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
            # Announcer/broadcast mention props
            "KXNBAMENTION", "KXNHLMENTION", "KXMLBMENTION", "KXNFLMENTION",
        ]
        supplemented = 0
        _GAME_SERIES = {"KXNBAGAME", "KXNHLGAME", "KXMLBGAME", "KXNFLGAME"}
        # #995 attempt-8 (targeted): game-level series (GAME/SPREAD/TOTAL/1H/2H/
        # WINNER/SERIES) explode into monster nested-markets payloads — the exact
        # blobs whose sync parse froze the loop (KXMLBGAME, KXNBA1HSPREAD). Fetch
        # them WITHOUT nested markets (tiny response); the empty-events backfill
        # below fetches their markets per-event, lazily + bounded. Small
        # championship series (KXNBA, KXNBAEAST, KXMLBAL…) keep nested.
        _HEAVY_TOKENS = ("GAME", "SPREAD", "TOTAL", "1H", "2H", "WINNER", "SERIES")
        for st in _SPORTS_SERIES_TICKERS:
            _supp_nested = not any(tok in st.upper() for tok in _HEAVY_TOKENS)
            _progress(f"fetch:supp:{st}")
            if _past_deadline():
                logger.warning(
                    "Kalshi fetch deadline hit before supplementary series %s "
                    "(%d events so far) — returning partial", st, len(all_events),
                )
                break
            # Game series always need the supplementary fetch — the main scan
            # finds open events but misses some open game events.
            if st not in _GAME_SERIES and any(
                e.event_ticker.upper().startswith(st.upper()) for e in all_events.values()
            ):
                continue
            try:
                # #995: OPEN events only. The settled-game-series fetch
                # ([None,"settled"] x 25 pages for 4 game series ~= 200 nested
                # pages) is what blew the 660s budget → SIGKILL before the create
                # loop, freezing creation. Settled capture is `kalshi_settled`'s
                # job, not the create/update poll's. Uniform 5-page open scan.
                series_cursor = None
                for _sp in range(5):
                    if _past_deadline():
                        break
                    await asyncio.sleep(0.3)
                    _progress(f"fetch:supp:{st}:p{_sp}")
                    # #995 attempt-7: same per-page hard bound as the main scan.
                    # attempt-6 got the poll PAST the unfiltered scan, and the
                    # marker then fingered the supplementary loop (fetch:supp:
                    # KXMLBGAME) as the next stall — a hung get_events here isn't
                    # caught by the series try/except (that only catches raises,
                    # not hangs). wait_for turns a hang into a TimeoutError the
                    # except below swallows → skip to the next series.
                    events_page, series_cursor = await asyncio.wait_for(
                        self.get_events(
                            status=None,
                            series_ticker=st,
                            with_nested_markets=_supp_nested,
                            limit=200,
                            cursor=series_cursor,
                            deadline=deadline,
                            progress_cb=_progress,
                        ),
                        timeout=45.0,
                    )
                    # #995 attempt-9b: bound the parse here too (see main scan).
                    try:
                        parsed_page = await asyncio.wait_for(
                            self._parse_events_offloaded(events_page), timeout=60.0
                        )
                    except Exception:
                        _progress(f"fetch:supp:{st}:p{_sp}:parse_timeout")
                        parsed_page = []
                    for parsed_event in parsed_page:
                        if parsed_event and parsed_event.event_ticker not in all_events:
                            all_events[parsed_event.event_ticker] = parsed_event
                            supplemented += 1
                    if not series_cursor:
                        break
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
        if empty_events and not _past_deadline():
            logger.info(
                "Backfilling markets for %d sports events with 0 nested markets",
                len(empty_events),
            )
            backfilled = 0
            for _bi, event in enumerate(empty_events):
                _progress(f"fetch:markets_backfill:{_bi}")
                if _past_deadline():
                    logger.warning(
                        "Kalshi fetch deadline hit during empty-event backfill "
                        "(%d/%d done)", backfilled, len(empty_events),
                    )
                    break
                try:
                    await asyncio.sleep(0.3)
                    # #995 attempt-7: bound this fetch too (same hang class).
                    raw_markets, _ = await asyncio.wait_for(
                        self.get_markets(
                            status=None,
                            event_ticker=event.event_ticker,
                            limit=200,
                        ),
                        timeout=45.0,
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

    async def _parse_events_offloaded(
        self, events: list[dict]
    ) -> list[Optional["KalshiEvent"]]:
        """Parse a page of raw event dicts into KalshiEvent objects.

        #995 attempt-9: ``_parse_event`` (and its nested ``_parse_market`` loop)
        is pure CPU but can be heavy for large nested-markets pages. Run inline it
        blocks the event loop, so a page that arrives fine still starves the
        wait_for/deadline timers during parse. For a large page we offload the
        whole page to a worker thread (the functions touch no shared mutable
        state, so this is safe); tiny pages parse inline to avoid thread-pool
        overhead.
        """
        import asyncio as _asyncio

        if not events:
            return []
        if len(events) < 10:
            return [self._parse_event(ed) for ed in events]
        return await _asyncio.to_thread(
            lambda evs=events: [self._parse_event(ed) for ed in evs]
        )

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
            logger.warning("Error parsing Kalshi event: %s", e)
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
            logger.warning("Error parsing Kalshi market: %s", e)
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
