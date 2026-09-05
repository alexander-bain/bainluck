"""
Kalshi API integration service.

Handles fetching prediction market data from Kalshi's trading API.
Kalshi markets provide bid/ask spreads and last traded prices.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Sequence

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


def event_series_ticker(event_ticker: str) -> str:
    """The series prefix of a Kalshi event ticker.

    ``KXMLBGAME-26AUG26BOSMIA`` → ``KXMLBGAME``. Split on the first ``-`` rather
    than testing ``startswith`` against the series list: ``KXMLBGAME-…`` also
    starts with ``KXMLB`` (a DIFFERENT series, the AL/NL championship futures,
    which keeps its nested markets), so a prefix test silently conflates the two.
    """
    return (event_ticker or "").split("-", 1)[0].upper()


def order_market_backfill_candidates(
    events,
    stripped_series: set,
    now: Optional[datetime] = None,
) -> list:
    """Order the empty-event market backfill so a bounded budget spends it well.

    The backfill can only ever reach a few dozen events per beat, so its ORDER
    is the whole of its behaviour — gotcha #41: ask what the ordering starts on.
    Left in fetch order it starts on whatever the main scan paged first, and the
    game-level series it exists to serve sit at the very end (the supplementary
    loop appends them, and golf is deliberately fetched before them).

    Two keys, in order:

    1. **Events whose series was deliberately stripped of nested markets first.**
       Those are the ones the ``_HEAVY_TOKENS`` decision emptied on an explicit
       promise that this backfill would fill them; everything else in the list
       is empty by accident of the upstream listing. Serving the accident before
       the promise is how the promise stayed unkept.
    2. **Within those, the soonest game that has not already happened.** These
       tickers embed their own game date, and the supplementary fetch is
       unfiltered by status, so the candidate list is mostly SETTLED games going
       back months. A settled game's markets cannot light up a live card. Games
       from yesterday onward sort ascending (tonight before next week); anything
       older sorts last, newest-first, so the ordering has BOTH bounds rather
       than starting on the dead tail.

    Pure and total: unparseable tickers sort last within their group rather than
    raising, because a fetch must never fail on a telemetry-shaped concern.
    """
    from app.utils.prediction_market_matching import extract_game_date_from_ticker

    _now = now or datetime.now(timezone.utc)
    # A game that started yesterday can still be settling, so the floor is -1d
    # rather than "now" — a hard `now` floor drops in-progress late games.
    _floor = _now - timedelta(days=1)

    def _key(event):
        stripped = event_series_ticker(event.event_ticker) in stripped_series
        try:
            game_date = extract_game_date_from_ticker(event.event_ticker)
        except Exception:
            game_date = None
        if game_date is None:
            # Undated: after every dated sibling in the same group, but still
            # ahead of the other group.
            return (0 if stripped else 1, 2, 0.0)
        delta = (game_date - _now).total_seconds()
        if game_date >= _floor:
            return (0 if stripped else 1, 0, delta)      # soonest first
        return (0 if stripped else 1, 1, -delta)         # most recent past first

    return sorted(events, key=_key)


# ---------------------------------------------------------------------------
# The guaranteed supplementary rescue net.
#
# Module level, not method local (Q426): these four constants ARE the policy
# for what this service can and cannot see, and every incident recorded in the
# comments below was a series being absent from them. A policy a guard test can
# only reach by scraping `inspect.getsource` is one that stays green when
# somebody comments the list out.
# ---------------------------------------------------------------------------
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
    # Golf tournaments + props (Queue #163): the main unfiltered scan's
    # resumable cursor was not reaching the KXPGA* series pages, so
    # OPEN tournaments — incl. marquee majors like The Open Championship
    # (KXPGATOUR-THOC26, listed but 0 markets ingested) AND the current
    # week's Scottish Open / ISCO — surfaced with no cross-source
    # markets. Golf had no supplementary safety net (this list was
    # NBA/NHL/MLB/NFL only). None of these carry a _HEAVY_TOKEN, so they
    # fetch WITH nested markets; per-series open-event counts are tiny
    # (~4 events/series), well under the #995 monster-payload threshold.
    # NB: the highest-volume matchup series (KXPGAH2H ~724, KXPGA3BALL
    # ~677) are intentionally EXCLUDED — they open only during play and
    # their nested payloads are the largest, so we keep them off the
    # guaranteed rescue to avoid re-introducing #995 monster-page risk;
    # the pre-tournament futures below are what marquee readiness needs.
    "KXPGATOUR", "KXPGATOP5", "KXPGATOP10", "KXPGATOP20",
    "KXPGAMAKECUT", "KXPGAR1LEAD", "KXPGAR2LEAD", "KXPGAR3LEAD",
    "KXPGAHOLEINONE",
    # #171: KXPGAPLAYOFF was the single golf series missing from the
    # rescue net — the main scan carried its playoff market for 19
    # prior events but The Open (KXPGAPLAYOFF-THOC26, active on Kalshi
    # with 1 market) was never ingested. It carries no _HEAVY_TOKEN and
    # each event holds a single market (tiny nested payload), so it fits
    # the guaranteed rescue exactly like the other KXPGA* golf futures.
    "KXPGAPLAYOFF",
    "KXLPGATOUR", "KXLIVTOUR", "KXDPWORLDTOUR",
    # Combat sports (#173/#1024): KXUFCFIGHT / KXBOXING had NO
    # supplementary safety net — the golf-class gap applied to combat.
    # The fight-WINNER series depend entirely on the deadline-bounded
    # main unfiltered scan reaching their expiry-DESC tail page inside
    # the ~180s fetch budget; during the #995 create-freeze window (and
    # any slow beat) they never surfaced. Confirmed live: UFC 329
    # (KXUFCFIGHT-26JUL11*) had 15 fights on Kalshi but only 1 in our DB
    # (the McGregor headliner, ingested months early) — SAIPIM
    # (Saint-Denis vs Pimblett) and 13 siblings were never created, so
    # A5's combat cross-source blend had no fight to feed. These are the
    # win-prob-blend-critical markets. Each card is one event with
    # ~15 single-market fights (2 outcomes each) → tiny nested payload,
    # no _HEAVY_TOKEN, so they fetch WITH nested markets like the golf
    # futures — well under the #995 monster-page threshold. Fight-prop
    # series (KXUFCMOV/DISTANCE/VICROUND/MOF/ROUNDS, KXBOXING* props)
    # share the same events and already reach via the main scan; the
    # guaranteed rescue on the winner series is what fixes the class.
    "KXUFCFIGHT", "KXBOXING",
    # Tennis (Q426). The golf-class gap, third occurrence — and this
    # time it cost a whole Grand Slam. Measured 2026-08-28: Kalshi
    # carried 47 KXATPMATCH + 49 KXWTAMATCH events for the US Open main
    # draw (`KXATPMATCH-26AUG30YIBWAL`, Wu vs Walton, among them) and
    # our database held ZERO of them; the 15 tennis match rows we did
    # have were all created 2026-08-19 and long settled. Tennis had no
    # supplementary safety net, so — exactly like golf before #163 and
    # combat before #173 — it depended entirely on the deadline-bounded
    # main scan reaching its pages. That scan's own report says it never
    # does: 24 of 24 beats in the ring read `verdict: frozen`,
    # `wrapped: false`, `stop_reason: max_pages`, with ~21K events
    # fetched and a few hundred processed per beat. A series that is
    # only reachable by a walk that has never once completed is not
    # "low priority"; it is unreachable, and the register recorded the
    # consequence as 96 R128 matchups pinned to nothing.
    #
    # KXATPNATSTAGE / KXWTANATSTAGE are the nationality props ("US Open
    # Men's/Women's Singles: Americans to Reach Quarterfinals") — 5 open
    # events total, both draws. They are here for the same reason and
    # cost almost nothing: the whole series is one page of three rows.
    #
    # None of the four carries a _HEAVY_TOKEN, so they fetch WITH nested
    # markets; a match event holds a single two-outcome market, which is
    # the smallest nested payload on the exchange and nowhere near the
    # #995 monster-page threshold. Ordering measured before adding them
    # (gotcha #41 — ask what the ordering starts on): `status=None`
    # paginates expiry-DESC, so page 0 of KXATPMATCH opens on
    # `26AUG30ZVESON` and covers the entire main draw before it reaches
    # anything settled. The 5-page uniform cap is not in the way.
    "KXATPMATCH", "KXWTAMATCH",
    "KXATPNATSTAGE", "KXWTANATSTAGE",
]

# Series whose supplementary fetch runs even when the main scan already
# produced an event with the same prefix.
#
# Q426: this set used to be the four game series, and the `any(...)`
# short-circuit below silently made partial coverage self-sealing for
# everything else. Tennis match series turn over DAILY — one stale
# KXATPMATCH event surviving in the listing is enough to satisfy
# `startswith` and skip the rescue for all 60 of today's, which is the
# shape our own data was already in (8 open KXATPMATCH rows, every one
# of them created 2026-08-19). "We have one of these" is not "we have
# these"; for a daily series it is the reverse.
_ALWAYS_FETCH_SERIES = {
    "KXNBAGAME", "KXNHLGAME", "KXMLBGAME", "KXNFLGAME",
    "KXATPMATCH", "KXWTAMATCH",
    "KXATPNATSTAGE", "KXWTANATSTAGE",
}
# #995 attempt-8 (targeted): game-level series (GAME/SPREAD/TOTAL/1H/2H/
# WINNER/SERIES) explode into monster nested-markets payloads — the exact
# blobs whose sync parse froze the loop (KXMLBGAME, KXNBA1HSPREAD). Fetch
# them WITHOUT nested markets (tiny response); the empty-events backfill
# below fetches their markets per-event, lazily + bounded. Small
# championship series (KXNBA, KXNBAEAST, KXMLBAL…) keep nested.
_HEAVY_TOKENS = ("GAME", "SPREAD", "TOTAL", "1H", "2H", "WINNER", "SERIES")
# #999 / Queue #166: fetch the priority (golf) rescue tickers FIRST so
# they get first claim on the reserved supplementary window. Even with
# the main-scan cap, the earlier championship/game series could otherwise
# eat the whole reserve before the loop ever reached the golf entries at
# the tail of the list. `str.startswith` accepts a tuple; `sorted` is
# stable, so within each group the original order is preserved.
_PRIORITY_RESCUE_PREFIXES = ("KXPGA", "KXLPGA", "KXLIV", "KXDPWORLD")

# ---------------------------------------------------------------------------
# Series DISCOVERY (#2927 container principle, applied to series).
#
# The four constants above are a hand list, and `app/utils/kalshi_series_
# selection.py` carries the measurement that says why that is now the binding
# constraint rather than a safety net: Kalshi lists 140 tennis series, 39 of
# them carry open events, the hand list names 4 — and those 4 were the only
# tennis series in `futures_markets` whose newest row was from today. The US
# Open doubles draw (32 KXATPDOUBLES + 22 KXWTADOUBLES open events at the
# venue) was 0 open rows on our side, newest row five days cold.
#
# So membership becomes discovered. These constants are the BOUNDS on that
# discovery, not the membership itself.
# ---------------------------------------------------------------------------
#: Tags whose series are discovered. Deliberately one tag: this is the widening
#: knob, and a tag goes in only once its open-event population has been
#: measured against the fetch budget. `Sports` in full is 3,648 series and
#: 1,263 with open events — discovery scoped to the whole category would need
#: ~380s of paging against a 240s budget, so "discover everything" is not a
#: braver version of this, it is a beat that finishes nothing.
_DISCOVERY_TAGS = ("Tennis",)
#: Hard cap on series one beat may ADD. Today's tennis selection is ~30.
_DISCOVERY_MAX_SERIES = 40
#: Refuse a series holding more open events than one beat could drain.
_DISCOVERY_MAX_OPEN_EVENTS = 100
#: Events per page for a discovered series. `_MAIN_SCAN_PAGE_LIMIT`'s value and
#: for its reason (#995 attempt-10): a 200-event nested page decoded in ~67s
#: holding the GIL. Discovered series are fetched WITH nested markets, so they
#: take the page size that was measured safe for nested pages, not the 200 the
#: guaranteed floor uses for its mostly-stripped fetches.
_DISCOVERY_PAGE_LIMIT = 50
#: Per-series page ceiling, on top of the census-derived page count.
_DISCOVERY_MAX_PAGES = 3
#: Page ceiling for the census walk. Measured 2026-09-04: the whole open
#: listing is 72 pages of 200 at `with_nested_markets=false` and exhausts in
#: 17s. The ceiling is headroom over that, not a target.
_DISCOVERY_CENSUS_MAX_PAGES = 120


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

    async def get_markets_candlesticks_raw(
        self,
        tickers: list[str],
        period_interval: int = 60,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> dict[str, list[dict]]:
        """Raw candlesticks for MANY tickers in one request, keyed by ticker.

        Added for live/059. `GET /markets/candlesticks` has always taken a
        `market_tickers` LIST; :meth:`get_market_candlesticks_raw` throws that
        away by reading `markets[0]`, which is correct for its one caller and
        wasteful for a caller that wants a whole winner field. Drawing the top
        twelve outcomes of the US Open men's title at three granularities is 36
        requests one at a time and 3 batched.

        🔴 **THE RESPONSE IS NOT IN REQUEST ORDER AND IS NOT THE SAME LENGTH.**
        Measured against the live endpoint 2026-09-04: asking for
        `ALC,NOSUCHXYZ,SHE` returns TWO entries, ordered `SHE, ALC`. A caller
        that zips the response against its own ticker list therefore mislabels
        every series after the first gap — Shelton's 9% curve drawn as Alcaraz's
        43% one, silently, with no error anywhere. The only safe key is each
        entry's own `market_ticker` field, which is what this returns, and a
        ticker the venue omitted is simply absent from the dict rather than
        present and empty (an omission and an empty series are different facts —
        gotcha #53).

        Raises on transport/HTTP failure rather than swallowing, so a chunked
        caller can count the window it lost instead of recording it as "no data".
        """
        import time as _time

        if not tickers:
            return {}
        if start_ts is None:
            start_ts = int(_time.time()) - 90 * 86400
        if end_ts is None:
            end_ts = int(_time.time())

        response = await self.client.get(
            f"{self.BASE_URL}/markets/candlesticks",
            params={
                "market_tickers": ",".join(tickers),
                "period_interval": period_interval,
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
        )
        response.raise_for_status()
        data = response.json()
        out: dict[str, list[dict]] = {}
        for entry in data.get("markets") or []:
            ticker = entry.get("market_ticker")
            if not ticker:
                continue
            out[ticker] = entry.get("candlesticks") or []
        return out

    async def get_market_candlesticks_raw(
        self,
        ticker: str,
        period_interval: int = 60,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict]:
        """The UNNORMALIZED candlesticks for one market ticker.

        Added for live/035. :meth:`get_market_candlesticks` reduces each candle
        to one number before the caller sees it, and its reduction is wrong at
        settlement (see the note on that method). A caller that needs to make
        its own price decision — because it is drawing a chart a person reads,
        not filling a calibration bucket — needs the whole candle: both sides of
        the book AND the last traded price.

        Raises on transport/HTTP failure rather than swallowing, so a chunked
        caller can count the window it lost instead of recording it as "no data"
        (gotcha #53).
        """
        import time as _time
        if start_ts is None:
            start_ts = int(_time.time()) - 90 * 86400
        if end_ts is None:
            end_ts = int(_time.time())

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
        return raw_markets[0].get("candlesticks", []) or []

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

        KNOWN FLAW, DELIBERATELY NOT FIXED HERE (live/035). The reduction below
        falls back to the ASK when there is no bid, and at settlement a losing
        market's book is bid 0.00 / ask 1.00 — so the LOSER's final candle
        normalizes to **1.0**. Measured 2026-09-02 on
        ``KXATPMATCH-26AUG30VALMON-VAL`` (Vallejo lost; last real trade 0.01;
        this returns 1.0). It is left alone because its two consumers
        (``kalshi_cliff``, ``_backfill_kalshi_price_history``) fill calibration
        buckets whose behaviour is not this queue's to change. Anything drawing a
        USER-FACING curve must use :meth:`get_market_candlesticks_raw` and decide
        for itself — see ``app/tasks/event_chart_backfill.normalize_candle``.

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

    async def census_open_series(
        self,
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> tuple[dict[str, int], dict]:
        """Count OPEN events per series across the entire exchange listing.

        This is the measurement that makes series discovery affordable. The
        catalog says what EXISTS (3,648 sports series); this says what is
        actually live right now (1,263 of them), which is the only population a
        rescue loop can be sized against.

        It is cheap for one reason: ``with_nested_markets=false``. The main scan
        pages the same listing at 50/page WITH nested markets and has never once
        walked it to the end — 24 of 24 beats in the ring read ``stop_reason:
        max_pages``. Stripped of markets the same listing is 200/page and
        exhausts in **72 pages / 17s measured 2026-09-04**, because the cost was
        never the pagination, it was decoding nested markets we then throw away.
        We are counting tickers here, so we ask for none.

        Returns ``(counts, receipt)`` where ``counts`` maps a series prefix (the
        ticker up to the first ``-``) to its open-event count. ``receipt``
        carries ``exhausted`` — **the caller must not cache a census that is
        False**. A truncated walk under-counts, and every series it never
        reached looks dormant rather than missed; caching that would freeze the
        exact gap this exists to find for the whole TTL.

        Never raises: a census is a bounded improvement to the rescue, and a
        rescue must not fail because an optimisation did.
        """
        import asyncio
        import time as _time

        counts: dict[str, int] = {}
        cursor: Optional[str] = None
        pages = 0
        events_seen = 0
        exhausted = False
        error: Optional[str] = None
        _t0 = _time.monotonic()

        def _tick(sub: str) -> None:
            if progress_cb is not None:
                try:
                    progress_cb(sub)
                except Exception:
                    # A dropped phase marker is acceptable; a census that fails
                    # because its own telemetry failed is not (#995 attempt-9).
                    pass

        try:
            while pages < _DISCOVERY_CENSUS_MAX_PAGES:
                if deadline is not None and _time.monotonic() >= deadline:
                    break
                if pages:
                    await asyncio.sleep(0.1)
                _tick(f"fetch:census:p{pages}")
                # A hung page is caught here rather than by the try below: the
                # except only catches raises, not hangs (#995 attempt-7).
                raw_events, cursor = await asyncio.wait_for(
                    self.get_events(
                        status="open",
                        with_nested_markets=False,
                        limit=200,
                        cursor=cursor,
                        deadline=deadline,
                        progress_cb=progress_cb,
                    ),
                    timeout=30.0,
                )
                for ed in raw_events:
                    prefix = event_series_ticker(ed.get("event_ticker") or "")
                    if prefix:
                        counts[prefix] = counts.get(prefix, 0) + 1
                        events_seen += 1
                pages += 1
                if not cursor or not raw_events:
                    exhausted = True
                    break
        except Exception as e:  # noqa: BLE001 — see docstring
            error = f"{type(e).__name__}: {e}"
            logger.warning("Kalshi open-series census stopped early: %s", error)

        receipt = {
            "pages": pages,
            "events": events_seen,
            "series": len(counts),
            "exhausted": exhausted,
            "elapsed_s": round(_time.monotonic() - _t0, 1),
        }
        if error:
            receipt["error"] = error
        logger.info("Kalshi open-series census: %s", receipt)
        return counts, receipt

    async def discover_series_for_tags(
        self,
        tags: Sequence[str],
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> tuple[list[str], dict]:
        """Every series ticker the venue lists for these tags.

        Asks the venue what exists rather than reading it off our own ingest
        tables — notice 26's rule, and the reason yesterday's "0 US Open doubles
        markets on Kalshi" census was wrong: it measured our mirror. The answer
        here is the venue's own catalog, so a series we have never held is
        exactly as visible as one we have.

        Never raises, for the same reason as the census.
        """
        import asyncio
        import time as _time

        tickers: list[str] = []
        seen: set[str] = set()
        per_tag: dict[str, int] = {}
        requests = 0
        error: Optional[str] = None

        for tag in tags:
            cursor: Optional[str] = None
            page = 0
            try:
                while page < 5:
                    if deadline is not None and _time.monotonic() >= deadline:
                        break
                    if requests:
                        await asyncio.sleep(0.2)
                    if progress_cb is not None:
                        try:
                            progress_cb(f"fetch:discover:{tag}:p{page}")
                        except Exception:
                            # Telemetry must never fail the fetch it observes.
                            pass
                    series_list, cursor = await asyncio.wait_for(
                        self.get_series(
                            category=self.SPORTS_CATEGORIES[0],
                            tags=tag,
                            limit=200,
                            cursor=cursor,
                        ),
                        timeout=30.0,
                    )
                    requests += 1
                    for s in series_list:
                        t = (s.get("ticker") or "").strip().upper()
                        if t and t not in seen:
                            seen.add(t)
                            tickers.append(t)
                            per_tag[tag] = per_tag.get(tag, 0) + 1
                    page += 1
                    if not cursor:
                        break
            except Exception as e:  # noqa: BLE001 — see docstring
                error = f"{tag}: {type(e).__name__}: {e}"
                logger.warning("Kalshi series discovery failed for tag %s: %s", tag, e)
                continue

        receipt = {"tags": list(tags), "per_tag": per_tag, "requests": requests}
        if error:
            receipt["error"] = error
        return tickers, receipt

    async def resolve_discovered_series(
        self,
        cached: Optional[dict] = None,
        save: Optional[Callable[[dict], None]] = None,
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
    ) -> tuple[list[tuple[str, int]], dict]:
        """The discovered half of the rescue list, cached across beats.

        On a cache hit this costs one Redis read and the beat spends its whole
        budget fetching. On a miss it pays ~20s for a catalog read plus the
        census walk, out of a reserve carved for exactly that (the #999/#2214
        trade, made a third time): the main scan gives up the seconds, and its
        cursor is resumable, so they are deferred rather than lost.

        A partial census is used but never saved — see ``census_open_series``.

        Returns ``(selected, receipt)`` with ``selected`` a list of
        ``(series_ticker, pages)``.
        """
        from app.utils.kalshi_series_selection import select_discovered_series

        if cached:
            try:
                sel = [
                    (str(t).upper(), int(p))
                    for t, p in (cached.get("selected") or [])
                    if t
                ]
                if sel:
                    receipt = dict(cached.get("receipt") or {})
                    receipt["source"] = "cache"
                    return sel, receipt
            except Exception:
                # A malformed cache entry is a reason to re-measure, never a
                # reason to fail the fetch.
                logger.warning("Kalshi discovery cache unreadable; re-measuring")

        discovered, disc_receipt = await self.discover_series_for_tags(
            _DISCOVERY_TAGS, deadline=deadline, progress_cb=progress_cb,
        )
        if not discovered:
            return [], {"source": "live", "discovered": 0, "catalog": disc_receipt}

        counts, census_receipt = await self.census_open_series(
            deadline=deadline, progress_cb=progress_cb,
        )

        selected, receipt = select_discovered_series(
            discovered=discovered,
            open_counts=counts,
            guaranteed=_SPORTS_SERIES_TICKERS,
            heavy_tokens=_HEAVY_TOKENS,
            max_series=_DISCOVERY_MAX_SERIES,
            max_open_events=_DISCOVERY_MAX_OPEN_EVENTS,
            page_limit=_DISCOVERY_PAGE_LIMIT,
            max_pages=_DISCOVERY_MAX_PAGES,
        )
        receipt["source"] = "live"
        receipt["catalog"] = disc_receipt
        receipt["census"] = census_receipt

        if save is not None and census_receipt.get("exhausted") and selected:
            try:
                save({"selected": [list(s) for s in selected], "receipt": receipt})
            except Exception:
                # A cache write is an optimisation. Failing to persist the
                # measurement costs the next beat ~20s to re-measure; raising
                # here would cost it the whole fetch.
                pass
        elif not census_receipt.get("exhausted"):
            receipt["not_cached"] = "census_partial"

        return selected, receipt

    async def get_all_events(
        self,
        categories: Optional[list[str]] = None,
        deadline: Optional[float] = None,
        progress_cb: Optional[Callable[[str], None]] = None,
        start_cursor: Optional[str] = None,
        save_cursor: Optional[Callable[[Optional[str]], None]] = None,
        telemetry: Optional[dict] = None,
        discovery_cache: Optional[dict] = None,
        save_discovery: Optional[Callable[[dict], None]] = None,
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
                telemetry=telemetry,
                discovery_cache=discovery_cache, save_discovery=save_discovery,
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
        telemetry: Optional[dict] = None,
        discovery_cache: Optional[dict] = None,
        save_discovery: Optional[Callable[[dict], None]] = None,
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

        ``discovery_cache`` / ``save_discovery`` (#2927): the same
        caller-owns-Redis pattern for the DISCOVERED half of the rescue list.
        The service stays network-pure and the caller decides the TTL, exactly
        as it already does for the main-scan cursor. On a cache hit the whole
        discovery stage costs one Redis read; on a miss it pays a catalog read
        plus the census walk out of a reserve carved for it. See
        ``app/utils/kalshi_series_selection.py`` for what discovery is FOR — in
        one line, the hand list below names 4 tennis series and the venue
        carries 39 live ones, so the US Open doubles draw was never fetchable.
        """
        import asyncio
        import time as _time

        # #999 / Queue #166: reserve a floor of the total fetch budget for the
        # guaranteed supplementary rescue (golf majors, championship series).
        # The main unfiltered scan will happily drain the ENTIRE deadline paging
        # the backlog; the supplementary loop's first `_past_deadline()` check
        # then fires immediately and breaks with ZERO series fetched — a
        # deterministic 0-golf poll on the exact weeks a marquee tournament
        # (e.g. The Open, KXPGATOUR-THOC26) opens with only a handful of markets.
        # Capping the main scan at `deadline - reserve` guarantees the rescue
        # always gets its floor. The main scan's resumable cursor means the 60s
        # it gives up is not lost — the next beat continues the tail from where
        # this one stopped, so the backlog still drains, just one page slower.
        _RESCUE_RESERVE_S = 60.0
        # #2214: the SAME failure as #999, one stage further down the function.
        # The empty-event market backfill at the bottom of this method is the
        # promise `_HEAVY_TOKENS` makes: the game-level series (KXMLBGAME and
        # friends) are deliberately fetched WITHOUT nested markets, on the
        # stated undertaking that the backfill picks their markets up per-event.
        # That undertaking was never kept, for the identical structural reason
        # #999 fixed here: the step is LAST and had no reserve of its own, so
        # `_past_deadline()` is already true when control reaches it and the
        # step does ZERO work, every beat, deterministically.
        #
        # Measured on production 2026-08-26 before this change: 1,940
        # `KXMLBGAME` rows in `futures_markets`, ALL `resolved`, newest created
        # 2026-08-19 — no game market created for a week. The scan report agrees
        # and is not ambiguous: `events_fetched 16,340`, `events_processed 389`,
        # `loop_deadline_hit false` on all 12 beats in the ring, `verdict frozen`
        # on all 12. The upsert loop did not run out of time; it reached every
        # event and dropped 15,951 of them on `if not event.markets: continue`
        # (`tasks/kalshi.py:645`), because the backfill that was supposed to put
        # markets IN them never ran.
        #
        # Carving this out of the main scan is the same trade #999 already made
        # and justified: the main scan's cursor is RESUMABLE, so the seconds it
        # gives up are deferred, not lost — the next beat continues the tail.
        # The backfill's seconds are not deferrable in the same way, because a
        # market-less event is dropped outright rather than resumed.
        _BACKFILL_RESERVE_S = 45.0
        # Series discovery, the same carve for the third time. Discovery is a
        # strictly LATER stage than the guaranteed floor, so without a reserve
        # of its own it inherits #999's and #2214's failure exactly: the floor
        # expands to fill the rescue window, discovery's first deadline check
        # fires immediately, and every beat adds zero discovered series —
        # deterministically, while reporting a healthy fetch. Two carves:
        #
        #   _DISCOVERY_MEASURE_CAP_S  the catalog read + census walk. Paid only
        #                             on a cache miss (~20s measured); on a hit
        #                             it is handed straight back to the main
        #                             scan, which is why the deadlines below are
        #                             computed AFTER discovery has run.
        #   _DISCOVERY_RESERVE_S      fetching the selected series. Collapses to
        #                             zero when nothing was selected, so a tag
        #                             with no live series costs the floor nothing.
        _DISCOVERY_MEASURE_CAP_S = 35.0
        _DISCOVERY_RESERVE_S = 25.0

        def _progress(sub: str) -> None:
            # #995 attempt-5 sub-phase marker: names the exact fetch call in
            # flight, so if the poll still SIGKILLs the next run pinpoints the
            # hanging page/endpoint (not just "fetch").
            if progress_cb is not None:
                try:
                    progress_cb(sub)
                except Exception:
                    pass

        # Resolve the discovered half of the rescue list BEFORE the main scan,
        # so the seconds it does not spend are seconds the main scan gets.
        _discovered_series: list[tuple[str, int]] = []
        _discovery_receipt: dict = {"source": "disabled"}
        # Opt-in at the call site, on the caller's cache handles. Discovery
        # costs venue calls (a catalog read plus the census walk), and a caller
        # with nowhere to persist the result would pay them every single beat
        # and throw the answer away — so "no cache handles" means "this caller
        # did not ask for discovery", not "measure it anyway". It also keeps the
        # change additive for every existing caller and test: without the
        # handles the fetch issues exactly the calls it always did.
        _discovery_wired = discovery_cache is not None or save_discovery is not None
        if _DISCOVERY_TAGS and not _discovery_wired:
            _discovery_receipt = {"source": "not_wired"}
        elif _DISCOVERY_TAGS:
            _measure_deadline = None
            if deadline is not None:
                _measure_deadline = min(
                    _time.monotonic() + _DISCOVERY_MEASURE_CAP_S,
                    deadline
                    - _RESCUE_RESERVE_S
                    - _DISCOVERY_RESERVE_S
                    - _BACKFILL_RESERVE_S,
                )
            try:
                _discovered_series, _discovery_receipt = await asyncio.wait_for(
                    self.resolve_discovered_series(
                        cached=discovery_cache,
                        save=save_discovery,
                        deadline=_measure_deadline,
                        progress_cb=_progress,
                    ),
                    # Belt to the deadline's braces: the deadline is checked
                    # between pages and cannot interrupt one hung call.
                    timeout=_DISCOVERY_MEASURE_CAP_S + 15.0,
                )
            except Exception as e:  # noqa: BLE001
                _discovery_receipt = {
                    "source": "failed", "error": f"{type(e).__name__}: {e}",
                }
                logger.warning("Kalshi series discovery failed: %s", e)

        # CERT-953: the census count per selected series, used below to say what
        # each one was SUPPOSED to bring. A cached receipt carries it too, so a
        # cache-served beat alarms on the same evidence as a live one.
        _disc_expected: dict = {}
        try:
            _disc_expected = dict(_discovery_receipt.get("selected_expected") or {})
        except Exception:  # noqa: BLE001 — telemetry never breaks the fetch
            _disc_expected = {}

        # main scan → guaranteed floor → discovered → market backfill, each
        # stopping where the next one's floor begins. The arithmetic is a pure
        # function because #999 and #2214 were both the same off-by-one-stage
        # mistake and neither was visible in a test.
        from app.utils.kalshi_series_selection import fetch_stage_deadlines

        (
            _main_scan_deadline,
            _supp_deadline,
            _disc_fetch_deadline,
        ) = fetch_stage_deadlines(
            deadline,
            has_discovered=bool(_discovered_series),
            rescue_reserve_s=_RESCUE_RESERVE_S,
            discovery_reserve_s=_DISCOVERY_RESERVE_S,
            backfill_reserve_s=_BACKFILL_RESERVE_S,
        )

        def _past_deadline() -> bool:
            return deadline is not None and _time.monotonic() >= deadline

        def _past_main_scan_deadline() -> bool:
            # The main scan stops early so the guaranteed rescue keeps its floor.
            return (
                _main_scan_deadline is not None
                and _time.monotonic() >= _main_scan_deadline
            )

        def _past_supp_deadline() -> bool:
            # The supplementary rescue stops early so the empty-event market
            # backfill keeps ITS floor. Without this the rescue simply expands
            # to fill the whole remaining budget and the backfill inherits none.
            return (
                _supp_deadline is not None
                and _time.monotonic() >= _supp_deadline
            )

        def _past_disc_fetch_deadline() -> bool:
            return (
                _disc_fetch_deadline is not None
                and _time.monotonic() >= _disc_fetch_deadline
            )

        all_events: dict[str, KalshiEvent] = {}  # Dedup by event_ticker
        cursor = start_cursor or None
        page_count = 0
        max_pages = 100
        categories_seen: dict[str, int] = {}

        # #1586/#1845 instrumentation. Read-only: records where the walk starts,
        # where it ends, what it drops, and why it stops, so the freeze's
        # mechanism is a measurement rather than a hypothesis. `stop_reason`
        # starts as the ceiling case and is overwritten by whichever branch
        # actually breaks the loop.
        from app.utils.kalshi_scan_report import cursor_fingerprint

        _tel = telemetry if telemetry is not None else {}
        _tel["resumed"] = bool(start_cursor)
        _tel["start_cursor_fp"] = cursor_fingerprint(start_cursor)
        _tel["stop_reason"] = "max_pages"
        _tel["pages_skipped"] = 0
        _tel.setdefault("skip_reasons", {})

        def _skip(reason: str) -> None:
            _tel["pages_skipped"] = int(_tel.get("pages_skipped") or 0) + 1
            reasons = _tel.setdefault("skip_reasons", {})
            reasons[reason] = reasons.get(reason, 0) + 1

        while page_count < max_pages:
            _progress(f"fetch:unfiltered:p{page_count}")
            if _past_main_scan_deadline():
                logger.warning(
                    "Kalshi main scan hit its capped deadline at page %d "
                    "(%d events so far) — stopping early to reserve %.0fs for the "
                    "guaranteed supplementary rescue; cursor resumes next beat.",
                    page_count, len(all_events), _RESCUE_RESERVE_S,
                )
                _tel["stop_reason"] = "main_scan_deadline"
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
                        deadline=_main_scan_deadline,
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
                _tel["stop_reason"] = "page_error"
                _skip(f"page_error:{type(e).__name__}")
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
                # A dropped page is invisible in a coverage curve; count it.
                _skip(f"parse_timeout:{type(e).__name__}")
                parsed_events = []
            for parsed_event in parsed_events:
                if parsed_event:
                    all_events[parsed_event.event_ticker] = parsed_event
                    cat = parsed_event.category or "unknown"
                    categories_seen[cat] = categories_seen.get(cat, 0) + 1

            page_count += 1
            if not cursor:
                # Listing walked to the end. This is the ONLY stop reason under
                # which the tail is actually revisited next beat.
                _tel["stop_reason"] = "exhausted"
                break

        _tel["pages_fetched"] = page_count
        # Queue 355 / #1845: this is the MAIN SCAN's population, and only that.
        # It used to be written to `events_fetched`, which the report then
        # compared against `events_new + events_existing` — counters derived
        # from the list this method RETURNS, i.e. main scan PLUS the
        # supplementary rescue below. The two are different populations, so the
        # pair could never be a partition of the whole, and beat 1 duly read
        # `5,335 + 5,075 = 10,410` against `events_fetched 5,000`. A mechanism
        # named by a counter that cannot add up is not named. `events_fetched`
        # is now written ONCE, at the return, over the population it claims.
        _tel["main_scan_events"] = len(all_events)
        _tel["end_cursor_fp"] = cursor_fingerprint(cursor)
        _tel["wrapped"] = not cursor

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

        supplemented = 0
        _ordered_series = sorted(
            _SPORTS_SERIES_TICKERS,
            key=lambda s: 0 if s.upper().startswith(_PRIORITY_RESCUE_PREFIXES) else 1,
        )
        for st in _ordered_series:
            _supp_nested = not any(tok in st.upper() for tok in _HEAVY_TOKENS)
            _progress(f"fetch:supp:{st}")
            if _past_supp_deadline():
                logger.warning(
                    "Kalshi fetch deadline hit before supplementary series %s "
                    "(%d events so far) — returning partial", st, len(all_events),
                )
                break
            # Daily-turnover series always need the supplementary fetch — the
            # main scan finds SOME of their open events and misses the rest, and
            # for these the difference between "some" and "all" is the whole
            # slate. Everything else may short-circuit on presence.
            if st not in _ALWAYS_FETCH_SERIES and any(
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
                    if _past_supp_deadline():
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
                            # #2214: bound the PAGE by the supplementary
                            # deadline, not the full one. `get_events` uses this
                            # to cap its own 429 retry/backoff span, so a page
                            # handed the full deadline can sleep straight
                            # through the backfill's reserve. A floor that is
                            # only checked BETWEEN pages is not a floor.
                            deadline=_supp_deadline,
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
        # ---- The DISCOVERED half of the rescue --------------------------
        # Runs after the guaranteed floor and on a reserve the floor cannot
        # touch, so a full floor never means zero discovered series.
        #
        # `status="open"` rather than the floor's `status=None`, and the two are
        # not interchangeable here (gotcha #41 — ask what the ordering starts
        # on). These series were SELECTED on a census of open events, and their
        # page counts derive from that census: `KXATPDOUBLES` is 32 open events,
        # one page. Unfiltered it is 255 events paginating expiry-DESC, so a
        # one-page `status=None` fetch would spend its page on settled rows from
        # August and return none of today's draw — a series that reads as
        # covered and is empty.
        _disc_added = 0
        _disc_series_fetched = 0
        # CERT-953: per-SERIES results, because the aggregate cannot carry the
        # ship. `events_added` sums every selected series AND counts only events
        # the main/supplementary scan had not already mapped, so it fails in
        # both directions: a dead KXATPDOUBLES hides behind a live sibling that
        # added events, and a perfectly healthy doubles fetch whose events the
        # main scan already held reports zero unique additions and would alarm.
        # `returned` is the number the VENUE handed back for this series — the
        # only one of the three that answers "did this draw arrive".
        _disc_series: dict[str, dict] = {}
        for _dst, _dpages in _discovered_series:
            if _past_disc_fetch_deadline():
                _discovery_receipt["fetch_truncated_after"] = _disc_series_fetched
                # Series never attempted are NOT zero-return series; recording
                # them as such would alarm on the reserve running out, which
                # `fetch_truncated_after` already says precisely.
                logger.warning(
                    "Kalshi discovery reserve spent after %d/%d series",
                    _disc_series_fetched, len(_discovered_series),
                )
                break
            _progress(f"fetch:disc:{_dst}")
            _dsr = _disc_series.setdefault(
                _dst,
                {"expected": int(_disc_expected.get(_dst) or 0),
                 "returned": 0, "unique_added": 0, "truncated": False},
            )
            try:
                _dcursor = None
                for _dp in range(_dpages):
                    if _past_disc_fetch_deadline():
                        _dsr["truncated"] = True
                        break
                    await asyncio.sleep(0.2)
                    _progress(f"fetch:disc:{_dst}:p{_dp}")
                    _dpage, _dcursor = await asyncio.wait_for(
                        self.get_events(
                            status="open",
                            series_ticker=_dst,
                            with_nested_markets=True,
                            limit=_DISCOVERY_PAGE_LIMIT,
                            cursor=_dcursor,
                            deadline=_disc_fetch_deadline,
                            progress_cb=_progress,
                        ),
                        timeout=45.0,
                    )
                    try:
                        _dparsed = await asyncio.wait_for(
                            self._parse_events_offloaded(_dpage), timeout=60.0
                        )
                    except Exception:
                        _progress(f"fetch:disc:{_dst}:p{_dp}:parse_timeout")
                        _dsr["parse_failed"] = True
                        _dparsed = []
                    for parsed_event in _dparsed:
                        if not parsed_event:
                            continue
                        # Counted BEFORE the dedup check: this is what the venue
                        # listed for this series, which is the question the
                        # alarm asks. Whether we already had the event is our
                        # bookkeeping, not the draw's existence.
                        _dsr["returned"] += 1
                        if parsed_event.event_ticker not in all_events:
                            all_events[parsed_event.event_ticker] = parsed_event
                            _dsr["unique_added"] += 1
                            _disc_added += 1
                            # Queue 355 / #1845: `supplementary_events` is one
                            # half of an identity the report CHECKS every beat
                            # (main_scan + supplementary == events_fetched). A
                            # third source of additions that did not roll into
                            # it would break that identity on every beat that
                            # discovered anything — the fetch would look wrong
                            # precisely when it worked.
                            supplemented += 1
                    if not _dcursor:
                        break
                _disc_series_fetched += 1
            except Exception as e:
                _dsr["error"] = f"{type(e).__name__}: {e}"
                logger.debug("Discovered-series fetch for %s failed: %s", _dst, e)

        _discovery_receipt["series_fetched"] = _disc_series_fetched
        _discovery_receipt["events_added"] = _disc_added
        _discovery_receipt["series_results"] = _disc_series
        _tel["series_discovery"] = _discovery_receipt
        if _disc_added:
            logger.info(
                "Kalshi series discovery added %d events from %d discovered "
                "series (%s)", _disc_added, _disc_series_fetched,
                ", ".join(t for t, _ in _discovered_series[:10]),
            )

        if supplemented:
            logger.info("Supplementary series fetch added %d events", supplemented)

        # Backfill: for events with 0 nested markets (Kalshi sometimes omits
        # them from the listing for large multivariate events), fetch markets
        # separately via the /markets endpoint.
        import asyncio

        # #2214: the series this method deliberately fetched WITHOUT nested
        # markets. Derived from the same two constants the fetch branched on, so
        # the two decisions cannot drift — the population the backfill owes is
        # by definition the population `_HEAVY_TOKENS` emptied.
        _stripped_series = {
            st.upper()
            for st in _SPORTS_SERIES_TICKERS
            if any(tok in st.upper() for tok in _HEAVY_TOKENS)
        }
        empty_events = [
            e for e in all_events.values()
            if not e.markets
            and (
                (e.category and "sport" in (e.category or "").lower())
                # #2214: a stripped game series qualifies on its ticker alone.
                # The `sport` category test was the second way the promise could
                # be broken: these events are fetched with `with_nested_markets=
                # False`, and an event that arrives with a missing or unexpected
                # `category` was silently not a candidate at all — for exactly
                # the rows this step exists to serve. The ticker is ours to
                # reason about; the category is Kalshi's to change.
                or event_series_ticker(e.event_ticker) in _stripped_series
            )
        ]
        empty_events = order_market_backfill_candidates(
            empty_events, _stripped_series
        )
        # Queue 359 (#1586): how many of the events this method is about to
        # hand back cannot possibly be ingested. The upsert loop's very first
        # statement is `if not event.markets: continue`, so a market-less event
        # is fetched, parsed, deduped, returned, counted — and dropped.
        #
        # This is the number that explains the capture gap, and nothing was
        # recording it. Measured on the 2026-08-17 14:45 beat: 13,513 events
        # fetched, **356 processed**. The scan report's `unreached_existing`
        # (6,315 that beat, and always exactly `events_existing`) reads as if
        # the loop ran out of time before the tail; `loop_deadline_hit` is
        # False on all 24 beats in the ring and the loop in fact reached every
        # event. It did not run out of budget. 97.4% of what it was handed had
        # nothing in it to upsert.
        #
        # `_HEAVY_TOKENS` above is the deliberate half of that: those series are
        # fetched WITHOUT nested markets on the stated promise that the backfill
        # below picks their markets up per-event.
        #
        # #2214 (2026-08-26): the promise is now KEPT, and the two ways it was
        # broken are both closed above — `_BACKFILL_RESERVE_S` gives this step a
        # floor of the fetch budget instead of leaving it structurally last with
        # nothing left, and the candidate rule no longer lets a missing Kalshi
        # `category` exclude a stripped game series. `market_backfill_*` below is
        # the proof: it reaches the scan report now, so "the backfill ran" is a
        # reading rather than an assumption, and a future regression shows up as
        # `market_backfill_filled: 0` instead of as a silent week of no games.
        _tel["events_without_markets"] = sum(
            1 for e in all_events.values() if not e.markets
        )
        _tel["market_backfill_candidates"] = len(empty_events)
        # #2214: the sub-count that says whether the reserve is being spent on
        # the population it was reserved FOR. `candidates` alone cannot: a beat
        # that fills 45 accidental non-game events reads identically to one that
        # fills tonight's slate, and only the second one lights up a card.
        _tel["market_backfill_stripped_candidates"] = sum(
            1
            for e in empty_events
            if event_series_ticker(e.event_ticker) in _stripped_series
        )
        _tel["market_backfill_skipped_past_deadline"] = bool(
            empty_events and _past_deadline()
        )
        _tel["market_backfill_filled"] = 0
        if empty_events and _past_deadline():
            logger.warning(
                "Kalshi fetch: the empty-event market backfill was SKIPPED "
                "entirely — %d of %d fetched events carry zero markets and the "
                "fetch deadline was already spent before this step. Every one "
                "of them will be dropped by `if not event.markets: continue`. "
                "Its %.0fs reserve was consumed by an earlier phase, which is a "
                "budget bug, not the structural starvation #2214 fixed.",
                _tel["events_without_markets"], len(all_events),
                _BACKFILL_RESERVE_S,
            )
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
            _tel["market_backfill_filled"] = backfilled
            # Re-count: the backfill's whole job is to move events OUT of this
            # bucket, so reporting the pre-backfill number would credit it with
            # work it did not do.
            _tel["events_without_markets"] = sum(
                1 for e in all_events.values() if not e.markets
            )

        # Queue 355 / #1845: close the arithmetic. `supplemented` counts only
        # dedup-guarded ADDITIONS, so main_scan_events + supplementary_events ==
        # len(all_events) exactly, and len(all_events) is the list the caller
        # partitions into new/existing. The report's reconciliation invariant
        # checks that identity every beat rather than trusting this comment.
        _tel["supplementary_events"] = supplemented
        _tel["events_fetched"] = len(all_events)

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
