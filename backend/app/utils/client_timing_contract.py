"""The contract a client-timing packet must satisfy before it is stored.

LAT-P232 (#2751), Stage 1 of the un-gated path designed in
``ARTIFACT-LAT-P231-the-ungated-path-design.md``.

WHY THIS MODULE EXISTS AT ALL — AND WHY IT DUPLICATES THE FRONTEND
------------------------------------------------------------------
The browser already sanitizes these packets: ``lib/analytics/sanitize.ts`` holds
a per-event key allowlist (``PERF_EVENT_KEYS``) and strips anything outside it
before gtag sees the event. This module deliberately re-implements that same
allowlist server-side.

That duplication is the point. The frontend sanitizer is a *correctness* boundary
for our own code; it is not a *security* boundary, because the ingest endpoint is
public and unauthenticated. Anyone can POST anything to it. If the only allowlist
lived in the browser, the privacy claim below would rest on the honesty of the
caller — which is not a claim at all.

So: the browser decides what OUR readers send, and this module decides what the
TABLE is allowed to hold. A malicious poster cannot get an identifier into the
store, because there is no key here that could carry one.

THE PRIVACY CLAIM, EXACTLY — DO NOT WIDEN IT
--------------------------------------------
Every field stored is a field that, for that same reader, in that same moment,
under that same consent grant, through that same sanitizer, is ALREADY being sent
to Google Analytics.

The allowlist below is a strict subset of the frontend's ``PERF_EVENT_KEYS`` for
the same three event names. It carries durations, counts, and bounded enums.
It carries no user id, no session id, no cookie, no token, no query string, no
entity id, no free text, and no IP address.

Two fields are stored MORE COARSELY here than they are sent to Google:
``page_path`` and ``endpoint`` are shape-masked (see ``mask_path``) the way
``maskSurface`` in ``lib/screenTiming.ts`` already masks ``surface``. GA receives
the unmasked route path today; this table does not. Narrower is always allowed;
wider never is.

IF YOU ARE ABOUT TO ADD A KEY: it must already be in the frontend's
``PERF_EVENT_KEYS`` for that same event, or the claim above becomes false and
this is no longer Stage 1. Adding a key that GA does not already receive is new
collection and is Alex's ruling, not a code change.

STAGE 2 IS NOT THIS. Un-gating the beacon so it also describes readers who
declined consent is new collection from new people, touches ``/privacy``, and is
explicitly Alex's call. Nothing in this module un-gates anything; the client-side
mirror sits behind the identical consent check it always did.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------

#: Maximum events accepted in one POST. A screen arrival emits a handful of
#: packets, so this is generous for an honest client and cheap for a hostile one.
MAX_EVENTS_PER_REQUEST = 20

#: Maximum characters for any string value AFTER masking. Enum-shaped fields are
#: far shorter than this; the cap exists so a hostile caller cannot smuggle a
#: payload into a legitimately-named key.
MAX_STRING_LEN = 64

#: Upper bound for a duration in ms. One hour. A larger number is not a slow
#: page, it is a broken clock or a hostile caller, and either way it would only
#: poison the aggregate.
MAX_DURATION_MS = 3_600_000

#: Upper bound for a count.
MAX_COUNT = 10_000

#: `-1` is the taxonomy's "not measurable / did not happen" marker (see
#: `NOT_MEASURED` in `lib/screenTiming.ts`). It is a meaningful value, NOT a
#: bad one, and must survive validation — a filter that dropped it would delete
#: exactly the surfaces that never reached a first card, which is the population
#: the needle exists to find.
NOT_MEASURED = -1


# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------

# Key kinds:
#   "ms"    — a duration in milliseconds; int; NOT_MEASURED or 0..MAX_DURATION_MS
#   "count" — a cardinal; int; 0..MAX_COUNT
#   "score" — a unitless float kept to 3 decimals (CLS); 0..1000
#   "enum"  — a short bounded string, stored verbatim after length capping
#   "path"  — a route-shaped string, SHAPE-MASKED before storage

_SCREEN_TIMING: Dict[str, str] = {
    "surface": "path",
    "entry": "enum",
    "shell_ms": "ms",
    "first_card_ms": "ms",  # 🔴 THE NEEDLE
    "fold_ms": "ms",
    "interactive_ms": "ms",
    "card_count": "count",
    "device_class": "enum",
    "network_class": "enum",
    "app_build": "enum",
    "outcome_class": "enum",
}

_FEED_TELEMETRY: Dict[str, str] = {
    "endpoint": "path",
    "cohort": "enum",
    "cache_status": "enum",
    "backend_elapsed_ms": "ms",
    "duration_ms": "ms",
}

_WEB_VITAL: Dict[str, str] = {
    "metric_name": "enum",
    "metric_value": "score",
    "rating": "enum",
    "navigation_type": "enum",
    "page_path": "path",
}

#: The three event names this sink accepts. Anything else is dropped whole.
#:
#: These are exactly the three performance events whose frontend contract already
#: says "durations, counts and bounded enums, nothing else" — the three that
#: strip even the enrichment keys (`session_id`, `platform`, `event_timestamp`)
#: in `PERF_EVENT_KEYS`. Events that KEEP enrichment (`feed_exit`) are excluded
#: on purpose: `feed_exit` carries a client session marker, and a session marker
#: in a durable first-party table is a different privacy question than the one
#: this module answers.
EVENT_KEY_SPECS: Dict[str, Dict[str, str]] = {
    "screen_timing": _SCREEN_TIMING,
    "feed_telemetry": _FEED_TELEMETRY,
    "web_vital": _WEB_VITAL,
}

ACCEPTED_EVENT_NAMES = frozenset(EVENT_KEY_SPECS)

#: Columns promoted out of the JSONB blob so the read endpoint can GROUP BY them
#: without a functional index. Every one is an "enum"/"path" key above.
PROMOTED_DIMENSIONS = (
    "surface",
    "app_build",
    "device_class",
    "network_class",
    "entry",
    "outcome_class",
)


# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

_NUMERIC_SEG = re.compile(r"^\d+$")
_UUID_SEG = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}", re.IGNORECASE)


def mask_path(raw: str) -> str:
    """Collapse a route-shaped string into a bounded, id-free slug.

    A deliberate port of ``maskSurface`` in ``lib/screenTiming.ts``: mask by
    SHAPE, not by a list of known routes, so a route added next month is masked
    correctly without anyone remembering to update this. The failure direction of
    an unknown route is an OVER-masked slug, never a leaked id.

    Applied server-side to ``surface`` (already masked by the client — masking it
    twice is idempotent and costs nothing) and to ``page_path``/``endpoint``
    (which the client does NOT mask, and which therefore could otherwise carry an
    event id into the table).
    """
    clean = (raw or "/").split("?")[0].split("#")[0]
    parts = [p for p in clean.split("/") if p]
    if not parts:
        return "discover"

    masked = []
    for i, seg in enumerate(parts):
        if i == 0:
            masked.append(seg.lower()[:32])
            continue
        if _NUMERIC_SEG.match(seg):
            masked.append(":id")
        elif _UUID_SEG.match(seg):
            masked.append(":id")
        elif len(seg) > 40:
            masked.append(":slug")
        else:
            masked.append(seg.lower()[:32])

    return "/".join(masked[:3])[:MAX_STRING_LEN]


# ---------------------------------------------------------------------------
# Per-value coercion
# ---------------------------------------------------------------------------


def _coerce(kind: str, value: Any) -> Optional[Any]:
    """Coerce one value to its declared kind, or return None to DROP the key.

    Dropping rather than raising is deliberate. A single malformed key in an
    otherwise-good packet should cost that key, not the whole screen arrival —
    the same failure posture as the frontend sanitizer, and the same rule as
    gotcha #42 ("one bad item must never wipe a scoring pass").
    """
    if value is None:
        return None

    # `bool` is a subclass of `int` in Python, so an unguarded numeric branch
    # would silently store `True` as `1` and invent a duration out of a flag.
    if isinstance(value, bool):
        return None

    if kind in ("ms", "count"):
        if not isinstance(value, (int, float)):
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        ivalue = int(value)
        if kind == "ms":
            if ivalue == NOT_MEASURED:
                return NOT_MEASURED
            if ivalue < 0 or ivalue > MAX_DURATION_MS:
                return None
            return ivalue
        if ivalue < 0 or ivalue > MAX_COUNT:
            return None
        return ivalue

    if kind == "score":
        if not isinstance(value, (int, float)):
            return None
        if not math.isfinite(float(value)):
            return None
        fvalue = float(value)
        if fvalue < 0 or fvalue > 1000:
            return None
        return round(fvalue, 3)

    if kind == "path":
        if not isinstance(value, str):
            return None
        return mask_path(value)

    if kind == "enum":
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        return trimmed[:MAX_STRING_LEN]

    return None


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------


def validate_packet(
    event_name: Any, params: Any
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Return ``(accepted_name, clean_params)`` for a submitted packet.

    ``accepted_name`` is None when the event is refused outright — an unknown
    name, or params that are not an object. Otherwise every surviving key is in
    that event's allowlist and every value has been coerced to its declared kind.

    Unknown keys are dropped silently. That is the whole guarantee: the returned
    dict cannot contain a key this module does not name, so it cannot contain an
    identifier.
    """
    if not isinstance(event_name, str):
        return None, {}

    spec = EVENT_KEY_SPECS.get(event_name)
    if spec is None:
        return None, {}

    if not isinstance(params, dict):
        return None, {}

    clean: Dict[str, Any] = {}
    for key, kind in spec.items():
        if key not in params:
            continue
        coerced = _coerce(kind, params[key])
        if coerced is not None:
            clean[key] = coerced

    return event_name, clean
