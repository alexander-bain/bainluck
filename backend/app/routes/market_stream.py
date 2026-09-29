"""One bounded SSE connection for the markets a reader currently has visible.

This is an invalidation transport. It never supplies prices or infers sports
state: clients re-read authoritative REST, including its normalized fields and
settlement. All database work ends before the first streamed byte.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import exists, func, select

from app.models import FuturesMarket, FuturesOutcome
from app.services.database import async_session_maker
from app.utils.live_push import MAX_FRAME_AGE_S, sse_encode
from app.utils.market_quote_push import SOURCES, market_channel, parse_market_frame
from app.utils.settledness import ASSIGNED_SETTLED_STATUSES

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_MARKETS = 50
MAX_CONNECTIONS = 100
MAX_CONNECTION_S = 900.0
HEARTBEAT_INTERVAL_S = 20.0
RETRY_MS = 5000
FRAME_WAIT_S = 1.0
_open_connections = 0


def _market_ids(ids: str) -> list[int]:
    # Bound parsing before int conversion or SQL construction.
    if not isinstance(ids, str) or len(ids) > 1100:
        raise HTTPException(
            400, detail={"reason": "invalid_market_ids", "max_ids": MAX_MARKETS}
        )
    parts = ids.split(",")
    if not 1 <= len(parts) <= MAX_MARKETS or any(
        not part.isascii() or not part.isdecimal() or not 0 < int(part) <= 2147483647
        for part in parts
    ):
        raise HTTPException(
            400, detail={"reason": "invalid_market_ids", "max_ids": MAX_MARKETS}
        )
    return list(dict.fromkeys(map(int, parts)))


async def _eligible_markets(db, ids: list[int]) -> tuple[list[int], list[int]]:
    # Match market_assigned_settled without loading potentially huge outcome
    # fields. This uses only market state/grade, never the linked game's phase.
    has_winner = exists().where(
        FuturesOutcome.market_id == FuturesMarket.id,
        FuturesOutcome.is_winner.is_(True),
    )
    rows = (
        await db.execute(
            select(
                FuturesMarket.id,
                FuturesMarket.source,
                func.lower(func.coalesce(FuturesMarket.status, "")).label("status"),
                has_winner.label("has_winner"),
            ).where(FuturesMarket.id.in_(ids))
        )
    ).all()
    existing = {row[0] for row in rows}
    eligible = {
        mid
        for mid, source, status, winner in rows
        if source in SOURCES and status not in ASSIGNED_SETTLED_STATUSES and not winner
    }
    return [mid for mid in ids if mid in eligible], [
        mid for mid in ids if mid in existing
    ]


class _MarketSubscriptions:
    def __init__(self, hub):
        self.hub = hub
        self.subscriptions = {}
        self.pending = {}

    async def subscribe(self, ids):
        for mid in ids:
            self.subscriptions[mid] = await self.hub.subscribe(market_channel(mid))

    async def next(self, timeout):
        for mid, sub in self.subscriptions.items():
            if mid not in self.pending:
                self.pending[mid] = asyncio.create_task(sub.next(timeout=timeout))
        done, _ = await asyncio.wait(
            self.pending.values(), timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        for mid, task in list(self.pending.items()):
            if task in done:
                del self.pending[mid]
                return mid, task.result()
        return None, None

    def remove(self, mid):
        task = self.pending.pop(mid, None)
        if task is not None:
            task.cancel()
        sub = self.subscriptions.pop(mid, None)
        if sub is not None:
            self.hub.release(sub)

    def release(self):
        # Synchronous even during cancellation, like the event stream.
        for mid in list(self.subscriptions):
            self.remove(mid)


async def _stream(ids: list[int], unavailable: list[int], request: Request):
    global _open_connections
    from app.utils.live_fanout import CLOSED, fanout

    subscriptions = _MarketSubscriptions(fanout())
    started = asyncio.get_running_loop().time()
    _open_connections += 1
    settled = []
    try:
        await subscriptions.subscribe(ids)
        yield f"retry: {RETRY_MS}\n\n"
        yield sse_encode(
            json.dumps({"market_ids": ids, "unavailable_market_ids": unavailable}),
            event="open",
        )
        last_beat = started
        while subscriptions.subscriptions:
            if await request.is_disconnected():
                return
            now = asyncio.get_running_loop().time()
            if now - started >= MAX_CONNECTION_S:
                yield sse_encode(json.dumps({"reason": "max_age"}), event="reconnect")
                return
            mid, raw = await subscriptions.next(FRAME_WAIT_S)
            if raw is CLOSED:
                yield sse_encode(json.dumps({"reason": "upstream"}), event="reconnect")
                return
            if raw is not None:
                frame = parse_market_frame(raw)
                if frame is not None and frame["market_id"] == mid:
                    age = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(frame["published_at"])
                    ).total_seconds()
                    if -5 <= age <= MAX_FRAME_AGE_S:
                        yield sse_encode(json.dumps(frame), event="market")
                        last_beat = now
                        if frame["terminal"]:
                            settled.append(mid)
                            subscriptions.remove(mid)
                # Even malformed traffic must not starve the named heartbeat.
            if now - last_beat >= HEARTBEAT_INTERVAL_S:
                yield sse_encode(
                    json.dumps({"t": datetime.now(timezone.utc).isoformat()}),
                    event="heartbeat",
                )
                last_beat = now
        yield sse_encode(
            json.dumps({"reason": "settled", "market_ids": settled}), event="closed"
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("market stream failed for %s markets", len(ids), exc_info=True)
        yield sse_encode(json.dumps({"reason": "upstream"}), event="reconnect")
    finally:
        _open_connections -= 1
        subscriptions.release()


@router.get("/stream")
async def stream_markets(request: Request, ids: str):
    requested = _market_ids(ids)
    if _open_connections >= MAX_CONNECTIONS:
        raise HTTPException(503, detail={"reason": "stream_capacity", "poll": True})
    async with async_session_maker() as session:
        admitted, existing = await _eligible_markets(session, requested)
    if not existing:
        raise HTTPException(404, detail={"reason": "markets_not_found", "poll": True})
    if not admitted:
        raise HTTPException(409, detail={"reason": "markets_unavailable", "poll": True})
    if _open_connections >= MAX_CONNECTIONS:
        raise HTTPException(503, detail={"reason": "stream_capacity", "poll": True})
    return StreamingResponse(
        _stream(admitted, [mid for mid in requested if mid not in admitted], request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
