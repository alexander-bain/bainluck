"""Redis pub/sub channel + frame shape for the live SSE push (live/034 S1).

The one place the publisher (`tasks/live_blend_refresh.py`, on the `worker-ws`
dyno) and the subscriber (`routes/event_stream.py`, on the web dyno) agree on a
channel name and a payload. They run in different processes on different dynos,
so a drifted channel string would not fail a test — it would simply deliver
nothing, forever, quietly. Keeping both halves on these two functions is what
makes that drift impossible rather than merely unlikely.

Transport is Redis **pub/sub**, deliberately not a list or a stream: pub/sub
stores nothing, so the live push adds zero bytes to the 100 MB LRU that Celery
shares. The cost of that choice is honest and stated in the design doc — a frame
published while nobody is subscribed is simply gone. The stream is a latency
optimisation over a database that remains the source of truth, never a delivery
guarantee; a dropped frame self-heals on the next tick, and the refresher's 45 s
unchanged-re-stamp puts a floor under how long "the next tick" can be.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Frames older than this are dropped by the subscriber rather than forwarded.
#: A frame can only be this stale if it sat in a Redis buffer through a stall,
#: in which case it is behind the REST payload the client already has and
#: forwarding it would animate the number BACKWARDS.
MAX_FRAME_AGE_S = 30.0


def event_channel(event_id: int) -> str:
    """The pub/sub channel carrying one event's live blend updates."""
    return f"live:event:{int(event_id)}"


def build_frame(
    *,
    event_id: int,
    probability: Optional[float],
    source: str,
    source_value: float,
    updated_at: str,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """One live update, in the shape the web + iOS clients parse.

    ``probability`` is the AGGREGATE home probability — the number the hero
    actually renders — not the single source that happened to move. Publishing
    the moved source's own price would put a second, disagreeing number on
    screen, which is precisely what the standing "the blend is the product"
    ruling forbids. ``source``/``source_value`` ride along so the sources rail
    can show which feed moved and what it said, and ``updated_at`` is the
    STAMPED write time so the client's "live · Ns ago" counts from when the data
    was true rather than from when the packet arrived.
    """
    # Coerce through float BEFORE the frame is built, not at json.dumps time.
    # `compute_aggregate_probability` can fall back to `opening_home_probability`,
    # which is a SQLAlchemy Numeric and therefore arrives as a `Decimal` —
    # unserialisable by the stdlib encoder. Left to `json.dumps` that raises
    # inside the publisher, where it would be swallowed as a generic publish
    # error and the stream would simply go dark on exactly the events that have
    # no live source yet.
    return {
        "event_id": int(event_id),
        "p": None if probability is None else float(probability),
        "source": source,
        "source_value": None if source_value is None else float(source_value),
        "updated_at": updated_at,
        "status": status,
    }


async def publish_frame(redis_client, frame: dict[str, Any]) -> bool:
    """Publish one frame. Never raises — returns whether it went out.

    The push is downstream of the number: a stamp that already committed must
    not be reported as failed because a fanout that nobody may be listening to
    did not go out. Callers count the False and surface it, so a publisher that
    is failing every time is visible rather than quiet (gotcha #53).
    """
    try:
        await redis_client.publish(
            event_channel(frame["event_id"]), json.dumps(frame)
        )
        return True
    except Exception:
        logger.warning(
            "live_push: publish failed for event %s", frame.get("event_id"),
            exc_info=True,
        )
        return False


def parse_frame(raw: Any) -> Optional[dict[str, Any]]:
    """Decode a pub/sub payload, or None if it is not a frame we can use.

    Returns None rather than raising on anything malformed: the subscriber is a
    long-lived loop on the web dyno's shared event loop, and one bad message
    must never be able to take down a connection — let alone the loop that is
    also serving `/api/feed`.
    """
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            return None
        frame = json.loads(raw)
    except Exception:
        return None
    if not isinstance(frame, dict) or "event_id" not in frame:
        return None
    return frame


def sse_encode(data: str, *, event: Optional[str] = None) -> str:
    """Frame one SSE message.

    ``data`` is emitted as a single `data:` line, so it must not contain a
    newline — every caller here passes compact JSON, which cannot. The trailing
    blank line is what actually dispatches the event to the client; omitting it
    is the classic SSE bug where everything looks right on the wire and no
    handler ever fires.
    """
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {data}\n\n"
