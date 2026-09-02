"""Server-Sent Events stream for LIVE events (live/034 S1).

Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES): push for LIVE events only; web
and iOS subscribe; non-live keeps polling.

WHY THIS IS SMALL. The hard part shipped already. `worker-ws` streams Kalshi and
Polymarket prices, flushes every 2 s, and `LiveBlendRefresher` stamps the blend
into `Event.win_probability_sources` at most once per event per 5 s. The number
in the database is already live. What was NOT live was the number on the screen:
the client polled every 32 s, so a value 3 s old in Postgres could be 32 s old in
front of a user. This endpoint closes that gap and nothing else — it makes no
data fresher, it makes the fresh data *arrive*.

That is also why the ruling's "≤1 update/5 s" needs no throttle here. It is
already the refresher's per-event cadence, upstream. A second timer in this file
could only drift away from the first one.

WHAT THIS FILE MUST NOT DO. It shares the web dyno's two uvicorn event loops
with `/api/feed`. Every connection here is long-lived, so any per-tick database
work or blocking call would put feed latency behind stream fanout for every
other request on the same loop. After the one live-gate lookup at connect there
is no database access on this path at all: frames carry their own values, and
the client's initial state comes from the REST payload the page already fetched.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.services import get_db
from app.utils.live_push import (
    MAX_FRAME_AGE_S, event_channel, parse_frame, sse_encode,
)

logger = logging.getLogger(__name__)

router = APIRouter()

#: Heroku's router closes a connection idle for ~55 s. Two heartbeats inside
#: that window means one can be lost to a hiccup without killing the stream.
HEARTBEAT_INTERVAL_S = float(os.getenv("SSE_HEARTBEAT_INTERVAL_S", "20"))

#: Hard ceiling on one connection's life. The client reconnects, which keeps
#: reconnect a routine, continuously-exercised path instead of the path that
#: only ever runs during an incident — and bounds any per-connection leak to
#: this long rather than to the length of a match.
MAX_CONNECTION_S = float(os.getenv("SSE_MAX_CONNECTION_S", "900"))

#: Concurrent streams allowed per uvicorn worker. Over this, connect is refused
#: with 503 and the client polls. Refusing loudly is the whole point: the
#: alternative is degrading `/api/feed` for everyone, silently, under load.
MAX_CONNECTIONS = int(os.getenv("SSE_MAX_CONNECTIONS", "200"))

#: Reconnect delay handed to the client via the SSE `retry:` field.
RETRY_MS = int(os.getenv("SSE_RETRY_MS", "5000"))

#: Statuses that get a push. Everything else polls, per the ruling. This keys
#: off `Event.status` deliberately and inherits whatever that column means —
#: see the design doc §5: a match wrongly left at `scheduled` is an event-graph
#: defect, and widening the gate here would hide it behind a UI feature (D27).
LIVE_STATUSES = frozenset({"live"})

#: Per-worker connection count. A plain int on the worker process, not Redis:
#: it is a guard on THIS loop's capacity, and asking Redis how loaded we are
#: would add a network round trip to the connect path to answer a local
#: question.
_open_connections = 0


def _frame_is_fresh(frame: dict, now: datetime) -> bool:
    """Drop a frame that has aged past the useful window.

    A frame can only be this old if it sat buffered through a stall, and a
    stalled client's REST refetch has almost certainly already passed it. The
    visible symptom of forwarding one is the number animating BACKWARDS to a
    price the market has left — worse than showing nothing, because it looks
    like a real move.
    """
    stamp = frame.get("updated_at")
    if not stamp:
        return True
    try:
        parsed = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() <= MAX_FRAME_AGE_S


async def _event_status(db: AsyncSession, event_id: int) -> Optional[str]:
    return (
        await db.execute(select(Event.status).where(Event.id == event_id))
    ).scalar_one_or_none()


async def _stream(event_id: int, request: Request) -> AsyncIterator[str]:
    """Yield SSE frames for one event until the client leaves or time is up."""
    global _open_connections

    from app.tasks.redis_state import get_async_redis_client

    redis_client = get_async_redis_client()
    pubsub = redis_client.pubsub()
    started = asyncio.get_event_loop().time()
    _open_connections += 1
    try:
        await pubsub.subscribe(event_channel(event_id))
        yield f"retry: {RETRY_MS}\n\n"
        yield sse_encode(json.dumps({"event_id": event_id}), event="open")

        last_beat = started
        while True:
            # The client going away is the common exit, and it is the one that
            # actually frees the slot — check it every pass, not just on send.
            if await request.is_disconnected():
                return
            loop_now = asyncio.get_event_loop().time()
            if loop_now - started >= MAX_CONNECTION_S:
                yield sse_encode(
                    json.dumps({"reason": "max_age"}), event="reconnect"
                )
                return

            # Bounded wait: this is what keeps the heartbeat on its clock even
            # when the market is completely silent, and what keeps this
            # coroutine yielding control back to the loop that is also serving
            # `/api/feed`.
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if message and message.get("type") == "message":
                frame = parse_frame(message.get("data"))
                if frame is not None and _frame_is_fresh(
                    frame, datetime.now(timezone.utc)
                ):
                    yield sse_encode(json.dumps(frame), event="probability")
                    # A frame is as good as a heartbeat for keeping the router
                    # from reaping us; a busy market should not also pay for
                    # pings it does not need.
                    last_beat = loop_now
                    if frame.get("status") not in LIVE_STATUSES:
                        # The match ended under us. Say so and close, so the
                        # client refetches once and settles rather than holding
                        # a stream open on a decided event forever.
                        yield sse_encode(
                            json.dumps({"reason": "not_live"}), event="closed"
                        )
                        return
                continue

            if loop_now - last_beat >= HEARTBEAT_INTERVAL_S:
                # An SSE comment. Keeps the Heroku router and any intermediary
                # from treating the connection as idle, and reaches no handler
                # on the client.
                yield ": ping\n\n"
                last_beat = loop_now
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "event_stream: stream for event %s failed", event_id, exc_info=True
        )
    finally:
        _open_connections -= 1
        # Both wrapped: teardown of a connection that is already gone must not
        # raise out of the generator and turn a normal disconnect into an error.
        try:
            await pubsub.unsubscribe(event_channel(event_id))
            await pubsub.close()
        except Exception:
            pass
        try:
            await redis_client.aclose()
        except Exception:
            pass


@router.get("/{event_id}/stream")
async def stream_event(
    event_id: int, request: Request, db: AsyncSession = Depends(get_db)
):
    """SSE stream of live blend updates for one event.

    Non-live events are refused rather than served an empty stream: a client
    holding an open connection on a scheduled match would sit silent for hours
    and look identical to a live match nobody is trading. The 409 tells the
    client to poll, which is the ruling's stated behaviour for non-live.
    """
    status = await _event_status(db, event_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if status not in LIVE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={"reason": "not_live", "status": status, "poll": True},
        )
    if _open_connections >= MAX_CONNECTIONS:
        raise HTTPException(
            status_code=503,
            detail={"reason": "stream_capacity", "poll": True},
        )

    return StreamingResponse(
        _stream(event_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # nginx and friends buffer by default, which for SSE means frames
            # arrive in a clump at close instead of as they happen.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
