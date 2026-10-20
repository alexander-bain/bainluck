"""#847 — the bounded, saved-only read behind the Correctness Console's readers.

The console's Matching and Source Intelligence tabs must open without starting a
database computation. Their producers already save what the views need in
Redis; this module is the one way those readers touch it:

* ``read_first_saved`` GETs a FIXED, ordered tuple of keys and stops at the
  first one that exists. Every GET, plus building the client, runs in ONE
  executor job under ONE total deadline. ``asyncio.wait`` rather than
  ``wait_for``: the deadline bounds the request's wait. An executor thread
  cannot be cancelled — it finishes under the client's own socket bounds and its
  late result is discarded.
* The client is the existing request-path signature
  (``socket_timeout=0.5, fast_fail=True``, #1197) — a lookup in the per-process
  client cache, so no new pool and no change to the shared Redis policy.
* A value larger than the caller's byte bound is reported as OVERSIZED and
  never decoded. The deadline bounds the transfer; the byte bound bounds the
  decode, the validation and the response. Nothing is truncated to fit.
* ``strict_loads`` refuses NaN/Infinity and exponent overflow (``1e400``)
  wherever they sit, because the response encoder would refuse them later with
  a 500.

Nothing here computes, opens a session, enqueues, writes, expires or deletes a
key. The key tuple comes from the caller's constants, never from a request.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Sequence


class SavedReadError(Exception):
    """The saved evidence could not be read. ``code`` is a fixed safe word."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SavedPayloadInvalid(ValueError):
    """The saved bytes do not satisfy the reader's contract."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SavedRead:
    """What the read found. ``key is None`` means every key was missing."""

    key: Optional[str]
    raw: Any = None
    size: Optional[int] = None


def _request_path_client():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=0.5, fast_fail=True)


def _blocking_read_first(keys: tuple[str, ...]) -> SavedRead:
    try:
        client = _request_path_client()
        for key in keys:
            raw = client.get(key)
            if raw is not None:
                size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
                return SavedRead(key=key, raw=raw, size=size)
    except Exception:
        # Never the exception text: it can carry the URL and its password.
        raise SavedReadError("redis_unavailable") from None
    return SavedRead(key=None)


def _discard_late_read(future) -> None:
    # The read outlived its deadline; its result (or error) has no reader.
    if not future.cancelled():
        future.exception()


async def read_first_saved(keys: Sequence[str], *, deadline_s: float) -> SavedRead:
    """GET ``keys`` in order and return the first present value, all within ONE
    total deadline. A missing key is ``None`` from Redis; an empty string is a
    present (and malformed) value, never a miss."""
    ordered = tuple(keys)
    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, _blocking_read_first, ordered)
    done, _ = await asyncio.wait({future}, timeout=deadline_s)
    if not done:
        future.add_done_callback(_discard_late_read)
        raise SavedReadError("read_deadline_exceeded")
    try:
        return future.result()
    except SavedReadError:
        raise
    except Exception:
        raise SavedReadError("redis_unavailable") from None


def _reject_non_finite(token: str):
    raise SavedPayloadInvalid("non_finite_number")


def _parse_finite_float(token: str) -> float:
    # ``parse_constant`` sees only the NaN/Infinity literals. An exponent that
    # overflows is an ordinary number token that ``float`` makes infinite.
    value = float(token)
    if not math.isfinite(value):
        raise SavedPayloadInvalid("non_finite_number")
    return value


def strict_loads(raw: Any) -> Any:
    """Decode saved bytes (or a decoded str) into JSON, refusing non-finite numbers."""
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return json.loads(raw, parse_constant=_reject_non_finite, parse_float=_parse_finite_float)
    except SavedPayloadInvalid:
        raise
    except (UnicodeDecodeError, ValueError, TypeError, RecursionError):
        # RecursionError: the C decoder's answer to valid but absurdly nested JSON.
        raise SavedPayloadInvalid("not_json") from None


# ---------------------------------------------------------------------------
# Type checks. Every saved value is checked before it is used; a JSON integer
# is unbounded, so it is compared as an int and never pushed through a float.
# ---------------------------------------------------------------------------


def is_count(value: Any) -> bool:
    return type(value) is int and value >= 0


def is_number(value: Any) -> bool:
    if type(value) is int:
        return True
    return type(value) is float and math.isfinite(value)


def in_range(value: Any, low: float, high: float) -> bool:
    return is_number(value) and low <= value <= high


def is_name(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def parse_aware_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise SavedPayloadInvalid("invalid_generated_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise SavedPayloadInvalid("invalid_generated_at") from None
    if parsed.tzinfo is None:
        raise SavedPayloadInvalid("invalid_generated_at")
    return parsed


SAVED_READER_SCHEMA_VERSION = 1


def saved_reader_response(
    status: int,
    cache_state: str,
    reason: str,
    *,
    freshness_basis: str,
    max_bytes: int,
    served_key: Optional[str] = None,
    served_from: Optional[str] = None,
    saved_bytes: Optional[int] = None,
    payload: Optional[dict] = None,
    age_seconds: Optional[float] = None,
    freshness: str = "unknown",
) -> tuple[int, dict]:
    """The one envelope every saved reader answers with: ``(http_status, body)``.

    ``served_key``/``served_from`` name the saved record that answered (absent on
    a miss or a read error). ``payload`` and its clock are present only on a
    hit; every other state carries no numbers.
    """
    return status, {
        "schema_version": SAVED_READER_SCHEMA_VERSION,
        "cache_state": cache_state,
        "reason": reason,
        "freshness": freshness,
        "freshness_basis": freshness_basis,
        "served_key": served_key,
        "served_from": served_from,
        "saved_bytes": saved_bytes,
        "max_saved_bytes": max_bytes,
        "generated_at": payload["generated_at"] if payload is not None else None,
        "age_seconds": age_seconds,
        "payload": payload,
    }
