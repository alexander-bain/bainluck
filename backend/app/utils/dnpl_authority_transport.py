"""Internal Redis envelope; not the public SSE authority-v3 contract.

The prefix makes old JSON-only hubs ignore v3 previews. The validated frame
reaches only opted-in subscriptions; the route owns the public stream session.
"""

from dataclasses import asdict
import json
from uuid import UUID

from app.services.dnpl_authority import Authority
from app.utils.blend_preview import is_preview_frame
from app.utils.dnpl_authority_fanout import MAX_RECORD_BYTES, PreviewReceipt
from app.utils.live_push import event_channel

PREFIX = "DNPL3 "


def is_authority_payload(payload) -> bool:
    return (isinstance(payload, str) and payload.startswith(PREFIX)) or (
        isinstance(payload, bytes) and payload.startswith(PREFIX.encode())
    )


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite JSON")


def encode_preview(authority: Authority, frame: dict) -> str:
    if authority.state != "ready" or not is_preview_frame(frame):
        raise ValueError("ready preview required")
    fields = asdict(authority)
    for name in ("namespace", "operation_id"):
        fields[name] = str(fields[name])
    raw = PREFIX + json.dumps(
        {"authority": fields, "frame": frame}, separators=(",", ":"), allow_nan=False
    )
    if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("preview envelope too large")
    return raw


def decode_preview(
    channel: str, raw: str | bytes, received_at: float
) -> PreviewReceipt:
    if not is_authority_payload(raw):
        raise ValueError("v3 prefix required")
    data = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("preview envelope too large")
    packet = json.loads(
        data[len(PREFIX) :],
        object_pairs_hook=_unique_object,
        parse_constant=_invalid_constant,
    )
    if not isinstance(packet, dict) or set(packet) != {"authority", "frame"}:
        raise ValueError("invalid internal envelope")
    fields = packet["authority"]
    if not isinstance(fields, dict):
        raise ValueError("authority object required")
    for name in ("namespace", "operation_id"):
        value = fields[name]
        if not isinstance(value, str):
            raise ValueError("UUID string required")
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError("canonical UUID required")
        fields[name] = parsed
    authority = Authority(**fields)
    frame = packet["frame"]
    if authority.state != "ready" or not is_preview_frame(frame):
        raise ValueError("ready preview required")
    event_id = frame.get("event_id")
    if (
        type(event_id) is not int
        or not 0 < event_id <= 9007199254740991
        or channel != event_channel(event_id)
    ):
        raise ValueError("preview event/channel mismatch")
    return PreviewReceipt(
        channel,
        json.dumps(frame, separators=(",", ":"), allow_nan=False),
        authority,
        received_at,
    )
