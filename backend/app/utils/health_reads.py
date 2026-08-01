"""Fail-honest typed boundary for reading warm health state out of Redis (Queue #294).

The C102 audit found the same defect in nine places: every admin/cockpit health
rail wrapped its Redis read in ``except Exception: return None`` (or nothing at
all), so a dead store, an evicted key, a half-written payload, and a genuine
"this has never run" all arrived at the caller as the SAME value. Downstream
that became ``no_data`` / ``no_run_cached`` / a zero / an opaque 500 — and in the
worst case (the cockpit grid tile) a dependency loss rendered as a GREEN tile
coloured from a legacy score the codebase itself documents as non-authoritative.

The fix is one small result type that keeps those cases apart:

``ok``          the key was read and decoded to the expected shape
``missing``     the store answered, and the key genuinely is not there
``malformed``   the key is there but its bytes do not decode
``wrong_shape`` it decodes, but not to the type the consumer requires
``unavailable`` we could not ask the store at all (construction or command error)

Only ``missing`` may be reported as "never ran". ``unavailable`` is UNKNOWN — it
is never a value, never a zero, and never a colour on a tile.

Nothing here logs or returns raw payloads, connection URLs, or credentials: every
error is reduced to a bounded class + message by :func:`redact`.
"""

from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# Read statuses. Import these rather than typing the strings at call sites.
OK = "ok"
MISSING = "missing"
MALFORMED = "malformed"
WRONG_SHAPE = "wrong_shape"
UNAVAILABLE = "unavailable"

#: Statuses that mean "the store could not answer" (as opposed to "it answered,
#: and the answer was nothing / garbage").
DEGRADED = (MALFORMED, WRONG_SHAPE, UNAVAILABLE)

_MAX_ERROR_CHARS = 160

# Anything shaped like a URL with userinfo (``rediss://user:password@host``) or a
# bare ``password=`` / ``auth=`` pair is stripped before an error is surfaced.
_CRED_PATTERNS = (
    re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)[^\s/@]*@"),
    re.compile(r"(?i)\b(password|passwd|auth|token|secret)\s*[=:]\s*\S+"),
)


def redact(exc: BaseException) -> str:
    """Bounded, credential-free rendering of ``exc`` for an operator payload.

    Redis connection errors routinely embed the full ``rediss://user:pass@host``
    URL in their message; an admin response is not a place to publish it.
    """
    text = str(exc).strip() or exc.__class__.__name__
    for pattern in _CRED_PATTERNS:
        text = pattern.sub(
            lambda m: (m.group(1) + "***") if m.group(1).endswith("//") else (m.group(1) + "=***"),
            text,
        )
    return text[:_MAX_ERROR_CHARS]


@dataclass(frozen=True)
class RedisRead:
    """One classified read. ``value`` is meaningful only when :attr:`ok`."""

    status: str
    key: str
    value: Any = None
    error_class: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == OK

    @property
    def missing(self) -> bool:
        return self.status == MISSING

    @property
    def unavailable(self) -> bool:
        return self.status == UNAVAILABLE

    @property
    def degraded(self) -> bool:
        """True when the read failed for a reason that is NOT 'never written'."""
        return self.status in DEGRADED

    def as_status(self, **extra: Any) -> dict:
        """A composite-safe status object: never a value, always a cause.

        Used by ops-snapshot / cockpit for a field whose source could not be
        read, so the field says WHY instead of masquerading as no-data.
        """
        out: dict = {"status": self.status, "source": self.key}
        if self.error_class:
            out["error_class"] = self.error_class
        if self.error:
            out["error"] = self.error
        out.update(extra)
        return out


def _failed(key: str, exc: BaseException, status: str = UNAVAILABLE) -> RedisRead:
    return RedisRead(
        status=status,
        key=key,
        error_class=exc.__class__.__name__,
        error=redact(exc),
    )


def client(*, key: str = "*", **kwargs: Any):
    """Construct the sync Redis client, classified.

    ``get_redis_client()`` builds lazily, so a dead store usually surfaces on the
    FIRST command rather than here — callers must guard both, which is what
    :func:`read_json` and :func:`command` do.

    Returns ``(client, None)`` on success or ``(None, RedisRead)`` on failure.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client(**kwargs), None
    except Exception as exc:  # noqa: BLE001 — classified, not swallowed
        return None, _failed(key, exc)


def command(key: str, fn: Callable[[], Any]) -> RedisRead:
    """Run one arbitrary Redis command (``llen``, ``smembers``, ``zrangebyscore``…)
    under the boundary. ``ok`` carries the raw return value verbatim."""
    try:
        return RedisRead(status=OK, key=key, value=fn())
    except Exception as exc:  # noqa: BLE001
        return _failed(key, exc)


def _decode(raw: Any) -> str:
    return raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)


def read_text(conn, key: str) -> RedisRead:
    """Read a scalar string key. Absent → ``missing``; command error → ``unavailable``."""
    try:
        raw = conn.get(key)
    except Exception as exc:  # noqa: BLE001
        return _failed(key, exc)
    if raw is None:
        return RedisRead(status=MISSING, key=key)
    return RedisRead(status=OK, key=key, value=_decode(raw))


def read_json(conn, key: str, *, expect: type | tuple[type, ...] = dict) -> RedisRead:
    """Read + decode a JSON key, classified.

    ``expect`` is the type the consumer can actually handle. A payload that
    decodes to something else (a bare list where a dict is required — the shape
    that reached an unguarded ``.get()`` and 500'd) is ``wrong_shape``, never
    passed through as if it were usable.
    """
    try:
        raw = conn.get(key)
    except Exception as exc:  # noqa: BLE001
        return _failed(key, exc)
    if raw is None:
        return RedisRead(status=MISSING, key=key)
    try:
        value = _json.loads(_decode(raw))
    except Exception as exc:  # noqa: BLE001
        return _failed(key, exc, status=MALFORMED)
    if expect is not None and not isinstance(value, expect):
        names = (
            expect.__name__
            if isinstance(expect, type)
            else "/".join(t.__name__ for t in expect)
        )
        return RedisRead(
            status=WRONG_SHAPE,
            key=key,
            error_class="TypeError",
            error=f"expected {names}, got {type(value).__name__}",
        )
    return RedisRead(status=OK, key=key, value=value)


def read_json_key(key: str, *, expect: type | tuple[type, ...] = dict, **kwargs: Any) -> RedisRead:
    """:func:`read_json` including client construction — for one-shot rails."""
    conn, failure = client(key=key, **kwargs)
    if failure is not None:
        return failure
    return read_json(conn, key, expect=expect)


# --- Freshness ---------------------------------------------------------------


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 stamp (``Z`` suffix included) to an aware datetime."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def age_seconds(value: Any, *, now: Optional[datetime] = None) -> Optional[float]:
    """Seconds since ``value`` (an ISO stamp), or None if it is unreadable.

    A NEGATIVE result is returned as-is: a payload stamped in the future is clock
    skew, and clamping it to zero (what the candidate-base rail used to do) hides
    exactly the condition an operator needs to see.
    """
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    reference = now or datetime.now(timezone.utc)
    return round((reference - parsed).total_seconds(), 1)


def payload_age_seconds(payload: Any, *, field: str = "generated_at") -> Optional[float]:
    """Age of a warm payload from its own run stamp."""
    if not isinstance(payload, dict):
        return None
    return age_seconds(payload.get(field))


def completeness(reads: dict[str, RedisRead]) -> dict:
    """Roll a set of per-field reads into an envelope-level completeness block.

    ``status`` is ``complete`` (everything readable — ``missing`` counts as a
    readable answer), ``partial`` (some field could not be read), or
    ``unavailable`` (nothing could be read).
    """
    total = len(reads)
    failed = sorted(k for k, r in reads.items() if r.degraded)
    if not total:
        status = "complete"
    elif not failed:
        status = "complete"
    elif len(failed) == total:
        status = "unavailable"
    else:
        status = "partial"
    return {
        "status": status,
        "fields_total": total,
        "fields_degraded": len(failed),
        "degraded_fields": failed,
    }
