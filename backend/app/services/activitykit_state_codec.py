"""Shared durable ActivityKit codec; no credentials, I/O or lifecycle policy."""

import base64
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from app.utils.activitykit_delivery_state import (
    Attempt,
    DeliveryCommand,
    DeliveryState,
    RetryPolicy,
)
from app.utils.activitykit_payload import (
    ActivityKitPush,
    GameActivitySnapshot,
    MAX_PAYLOAD_BYTES,
)


def _clock(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("An explicit aware clock is required")
    return value.astimezone(timezone.utc)


def encode_state(state: DeliveryState) -> dict:
    def encode(value):
        if isinstance(value, datetime):
            return _clock(value).isoformat()
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        if isinstance(value, dict):
            return {k: encode(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [encode(v) for v in value]
        return value

    return {"schema": 1, "state": encode(asdict(state))}


def decode_state(value: dict) -> DeliveryState:
    try:
        if value["schema"] != 1:
            raise ValueError()
        data = dict(value["state"])

        def date(value):
            return _clock(datetime.fromisoformat(value)) if value is not None else None

        data["retry_policy"] = RetryPolicy(
            tuple(timedelta(seconds=v) for v in data["retry_policy"]["delays"])
        )
        for name in ("score_fence", "probability_fence"):
            data[name] = date(data[name])
        if data["snapshot"] is not None:
            snapshot = dict(data["snapshot"])
            for name in ("score_observed_at", "probability_observed_at"):
                snapshot[name] = date(snapshot[name])
            data["snapshot"] = GameActivitySnapshot(**snapshot)
        if data["attempt"] is not None:
            attempt = dict(data["attempt"])
            command = dict(attempt["command"])
            body = base64.b64decode(command["push"]["body"], validate=True)
            if not 0 < len(body) <= MAX_PAYLOAD_BYTES:
                raise ValueError()
            command["push"] = ActivityKitPush(body)
            attempt["command"] = DeliveryCommand(**command)
            attempt["retry_at"] = date(attempt["retry_at"])
            data["attempt"] = Attempt(**attempt)
        return DeliveryState(**data)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError("Invalid persisted ActivityKit state") from None
