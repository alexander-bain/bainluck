"""Redis pub/sub channel + frame shape for the live SSE push (live/034 S1).

The one place the publisher (`tasks/live_blend_refresh.py`, on the `worker-ws`
dyno) and the subscriber (`routes/event_stream.py`, on the web dyno) agree on a
channel name and a payload. They run in different processes on different dynos,
so a drifted channel string would not fail a test — it would simply deliver
nothing, forever, quietly. Keeping both halves on these two functions is what
makes that drift impossible rather than merely unlikely.

Redis pub/sub carries updates. A short-lived last committed frame per event
also lets a newly opened stream catch up immediately instead of waiting for the
next trade. Revision ordering and the existing age limit keep replay bounded.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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


def latest_frame_key(event_id: int) -> str:
    return f"live:last-event:{int(event_id)}"


def _frame_revision(frame: dict) -> Optional[int]:
    event_id = frame.get("event_id")
    rev = frame.get("rev")
    if type(event_id) is not int or not isinstance(rev, dict):
        return None
    if set(rev) != {str(event_id)}:
        return None
    value = rev[str(event_id)]
    return value if type(value) is int and value >= 0 else None


# Keep publication and last-frame storage in one Redis command. Concurrent
# source publishers may finish out of order; only a newer revision replaces it.
# PUBLISH's integer reply is retained for the packed sender's accounting.
# A full replay cache must not suppress delivery to existing subscribers.
RETAIN_AND_PUBLISH = """
local prior = redis.call('GET', KEYS[1])
local keep = true
if prior then
    local ok, frame = pcall(cjson.decode, prior)
    if ok and type(frame) == 'table' and type(frame.rev) == 'table' then
        local revision = frame.rev[ARGV[2]]
        if type(revision) == 'number' and revision >= tonumber(ARGV[3]) then
            keep = false
        end
    end
end
if keep then
    redis.pcall('SET', KEYS[1], ARGV[1], 'EX', ARGV[4])
end
return redis.call('PUBLISH', KEYS[2], ARGV[1])
"""


def frame_publish_command(frame: dict) -> tuple:
    payload = json.dumps(frame)
    channel = event_channel(frame["event_id"])
    rev = _frame_revision(frame)
    if rev is None:
        return ("PUBLISH", channel, payload)
    return (
        "EVAL", RETAIN_AND_PUBLISH, 2, latest_frame_key(frame["event_id"]),
        channel, payload, str(frame["event_id"]), rev, int(MAX_FRAME_AGE_S),
    )


async def latest_frames(event_ids: list[int]) -> list[tuple[int, str]]:
    """One bounded read after subscribing; failure leaves ordinary push live."""
    from app.utils.request_cache import bounded_redis_call, get_shared_async_redis

    ids = list(dict.fromkeys(event_ids))
    try:
        client = await get_shared_async_redis()
        result = await bounded_redis_call(
            lambda: client.mget([latest_frame_key(i) for i in ids]),
            deadline_ms=250,
        )
        if not result.is_ok or not isinstance(result.value, (list, tuple)):
            return []
        accepted = []
        now = datetime.now(timezone.utc)
        for event_id, raw in zip(ids, result.value):
            frame = parse_frame(raw)
            if (frame is None or frame.get("event_id") != event_id
                    or _frame_revision(frame) is None):
                continue
            try:
                stamp = datetime.fromisoformat(frame["updated_at"])
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                age = (now - stamp).total_seconds()
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= age <= MAX_FRAME_AGE_S:
                accepted.append((event_id, json.dumps(frame)))
        return accepted
    except Exception:
        logger.debug("live_push: latest-frame read unavailable", exc_info=True)
        return []


def build_frame(
    *,
    event_id: int,
    probability: Optional[float],
    source: str,
    source_value: float,
    updated_at: str,
    status: Optional[str] = None,
    rev: Optional[int] = None,
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

    ``rev`` (#9051) is the row's ``win_probability_sources_rev`` as the SAME
    UPDATE that wrote the bag returned it, served as ``{"<event_id>": rev}``.
    ``p`` is this ROW's aggregate, not a folded one: a client adopts it only
    when its held detail vector has exactly this one key; on a folded event the
    frame is an invalidation that makes it refetch detail. ``None`` when the
    writer had no revision to report, which the client reads as no claim.
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
        "rev": (
            None
            if rev is None or isinstance(rev, bool) or not isinstance(rev, int)
            else {str(int(event_id)): rev}
        ),
    }


async def publish_frame(redis_client, frame: dict[str, Any]) -> bool:
    """Publish one frame. Never raises — returns whether it went out.

    The push is downstream of the number: a stamp that already committed must
    not be reported as failed because a fanout that nobody may be listening to
    did not go out. Callers count the False and surface it, so a publisher that
    is failing every time is visible rather than quiet (gotcha #53).
    """
    try:
        command = frame_publish_command(frame)
        if command[0] == "PUBLISH":
            await redis_client.publish(*command[1:])
        else:
            await redis_client.execute_command(*command)
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
