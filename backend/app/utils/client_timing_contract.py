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

**KEYS ARE NOT ENOUGH — VALUES ARE CLOSED TOO (CERT-1869).** The first version of
this module allowlisted key NAMES and accepted any string as a VALUE. That is not
a privacy boundary: it says where a value may go, never what it may be, so
``outcome_class: "alice@example.com"`` was stored. Every enum-shaped field now
declares its complete legal value set (``_ENUM_DOMAINS``), ``app_build`` declares
a closed grammar, and path-shaped fields keep only KNOWN route segments
(``mask_path``, fail-closed). A value outside its domain is dropped.

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
#   "path"  — a route-shaped string, FAIL-CLOSED segment-masked before storage

# ---------------------------------------------------------------------------
# CLOSED VALUE DOMAINS (CERT-1869's repair)
# ---------------------------------------------------------------------------
#
# THE DEFECT THIS FIXES. The first version allowlisted KEYS and let any string
# through as a VALUE, capped only at 64 characters. So a hostile POST could put
# `alice@example.com`, `user-12345` or `Bearer <token>` into `outcome_class` — a
# perfectly allowlisted key — and it would be stored. A key allowlist is not a
# privacy boundary; it only says WHERE a value may go, never WHAT it may be.
#
# My own tests could not see this: every hostile case attacked a hostile KEY
# NAME (`user_id`, `email`) and none attacked a hostile VALUE inside a legitimate
# key, so the suite discriminated against one defect while being structurally
# blind to the other.
#
# So every enum-shaped field now names its complete set of legal values, taken
# from the field's real producer rather than invented here. A value outside the
# set is DROPPED (the key, not the packet).

_ENUM_DOMAINS: Dict[str, frozenset] = {
    # `ScreenTimingParams` in `lib/analytics/types.ts` — literal unions.
    "entry": frozenset({"cold", "warm"}),
    "device_class": frozenset({"phone", "tablet", "desktop", "watch", "unknown"}),
    "outcome_class": frozenset({"ok", "empty", "no_card", "error"}),
    # `networkClass()` in `lib/screenTiming.ts` returns the Network Information
    # API's `effectiveType`, whose domain is fixed by the spec, or "unknown".
    "network_class": frozenset({"slow-2g", "2g", "3g", "4g", "unknown"}),
    # `FeedTelemetryParams.cohort` — a literal union.
    "cohort": frozenset({"authenticated", "session_anon", "shared_anon"}),
    # Every value `app/routes/feed.py` actually writes to `X-Feed-Cache`, plus
    # `other`/`none` from `app/middleware/latency.py` and `unknown` from
    # `normalizeCacheStatus` in `lib/feedTelemetry.ts`.
    #
    # CERT-1873 FOLLOW-UP. This was first taken from `_CACHE_BUCKETS` in
    # `middleware/latency.py` alone, which is a BUCKETING of the header, not the
    # header's domain — so `last_good`, `coalesced` and `unavailable` were real
    # values being silently dropped. That is precisely the "an over-tight domain
    # ships a permanently-empty column that reads as no-data rather than as a
    # bug" failure this module's own tests warn about, shipped anyway. The
    # authority is the WRITER (`_set_feed_cache_status`'s call sites), and
    # `test_cache_status_domain_matches_its_producer` now parses them.
    "cache_status": frozenset(
        {
            "miss",
            "hit",
            "stale_hit",
            "error",
            "coalesced",
            "last_good",
            "unavailable",
            "disabled",
            "disabled_debug",
            "disabled_reviewed_filter",
            "other",
            "none",
            "unknown",
        }
    ),
    # web-vitals' own metric ids.
    "metric_name": frozenset({"LCP", "INP", "CLS", "TTFB", "FCP", "FID"}),
    # `RATINGS` in `lib/webVitals.ts`.
    "rating": frozenset({"good", "needs-improvement", "poor"}),
    # The Navigation Timing `type` domain, both spellings seen in the wild.
    "navigation_type": frozenset(
        {"navigate", "reload", "back-forward", "back_forward", "prerender", "restore"}
    ),
}

#: WHY THERE IS NO `app_build` FIELD (CERT-1880, after three BLOCKs on it alone).
#:
#: `app_build` was the ONLY free-form value in this contract, and it is the only
#: field that ever leaked. Three repairs failed in the same way — each closed the
#: shapes the last cert named and left a neighbouring one open:
#:
#:   CERT-1869  any string accepted             -> `alice@example.com`
#:   CERT-1873  bounded the dotted-component count -> `127.0.1` (abbreviated IPv4)
#:   CERT-1880  allowed the real iOS wrapper     -> `127.0.1 (317)`, `1.4.2 (alice-123)`
#:
#: The third failure proves it is not fixable by a better pattern. The real
#: producer format IS an IP address: `socket.inet_aton` accepts `1.4.2` and
#: `1.0` — genuine `CFBundleShortVersionString` values — as valid IPv4
#: encodings. There is no rule that admits the producer and rejects the address,
#: because they are the same strings. Every further attempt would be another
#: round of enumerating against an attacker, which is what lost the last three.
#:
#: So the field is GONE, and the contract now has a structural guarantee instead
#: of an enumerated one:
#:
#:     EVERY stored string is either a member of a declared finite domain, or a
#:     path composed only of known route segments and fixed placeholders.
#:
#: There is no free-form value anywhere, so there is nothing left for a hostile
#: caller to put an identifier into. `test_no_field_accepts_free_form_text`
#: asserts exactly that over the whole contract, so re-adding a free-form field
#: reds the suite rather than reopening this.
#:
#: WHAT IS LOST, AND HOW IT COMES BACK. Per-release attribution — "is 1.4.2
#: slower than 1.4.1". That is worth having and it should never have been asked
#: of the CLIENT: a build tag from a public, unauthenticated endpoint is
#: untrustworthy by construction. The server already knows its own deploy
#: (`HEROKU_SLUG_COMMIT`), so the honest version of this dimension is stamped
#: server-side at ingest. Deliberately not done here: it is a new field with its
#: own argument to make, and this change is a removal.

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

#: Placeholders this function and `maskSurface` emit. Carry no information, and
#: must survive a second pass so masking stays idempotent.
_MASK_PLACEHOLDERS = frozenset({":id", ":seg", ":slug"})

#: Every STATIC segment the app's own route table contains, plus the API path
#: segments `feed_telemetry.endpoint` can name. Derived from `npm run build`'s
#: route listing and `app/routes/*.py`'s router prefixes — not invented here.
#:
#: TO ADD A ROUTE: put its static segments in this set. A segment that is not
#: here is reported as `:seg`, so the cost of forgetting is a surface that reads
#: as `:seg` in the p50 table — a loss of resolution, never a leaked id.
SAFE_ROUTE_SEGMENTS = frozenset(
    {
        # frontend pages
        "about",
        "admin",
        "admin-proxy",
        "analytics",
        "bug-reports",
        "calibration",
        "categories",
        "challenge",
        "cohort-views",
        "daily",
        "discover",
        "discover-quality",
        "economics",
        "entertainment",
        "eval",
        "event",
        "events",
        "feed-review",
        "frontend-build",
        "futures",
        "golf",
        "hub",
        "kernels-preview",
        "label-pass",
        "labeling",
        "labeling-coverage",
        "matching",
        "models",
        "my-odds",
        "my-stuff",
        "og",
        "onboarding",
        "opengraph-image",
        "play",
        "playoffs",
        "politics",
        "preferences",
        "privacy",
        "robots",
        "scorecard",
        "search",
        "share",
        "sitemap",
        "source-intelligence",
        "sport",
        "sports",
        "stats",
        "story",
        "taxonomy",
        "team",
        "team-clusters",
        "tournaments",
        "weather",
        "props",
        "results",
        "leaderboard",
        # API prefixes (`endpoint`)
        "api",
        "feed",
        "leagues",
        "teams",
        "telemetry",
        "client-timing",
        "summary",
        "interactions",
        "predictions",
        "notifications",
        "feedback",
        "auth",
        "user",
        "challenges",
        "oscars",
        "market-moves",
        "prop-families",
        "unsubscribe",
        "health",
        "docs",
        "march-madness",
        "league-futures",
        "event-stream",
    }
)


def mask_path(raw: str) -> str:
    """Collapse a route-shaped string into a bounded, id-free slug — FAIL CLOSED.

    CERT-1869's repair. The first version masked by SHAPE, keeping any segment
    that was not numeric, uuid-shaped or very long. That is safe for OUR client
    (which masks before sending) and unsafe for the public endpoint, because a
    hostile POST is not our client: ``/user/alice@example.com`` and
    ``/profile/alex-bain`` both survived shape-masking with the identifier intact.

    A grammar cannot fix this — ``alex-bain`` and ``probability-trend`` are the
    same shape. So the rule is inverted: **a segment is kept only if it is a
    known static route segment**; everything else becomes ``:seg``. Unknown now
    fails CLOSED rather than open.

    The honest client pays nothing for this: ``surface`` arrives already masked
    by ``maskSurface``, and its output is drawn from the same route table. What
    changes is only what a hostile caller can achieve, which is nothing.

    Applied to ``surface``, ``page_path`` and ``endpoint``. The latter two are
    NOT masked by the client at all, so this is their only defence.
    """
    clean = (raw or "/").split("?")[0].split("#")[0]
    parts = [p for p in clean.split("/") if p]
    if not parts:
        return "discover"

    masked = []
    for seg in parts[:3]:
        low = seg.lower()
        if low in _MASK_PLACEHOLDERS:
            # Already masked — by this function, or by `maskSurface` on the
            # client, which is where `surface` ALWAYS comes from. Re-masking a
            # placeholder into `:seg` would silently downgrade every real
            # client-masked surface (`event/:id` -> `event/:seg`) and blind the
            # p50 table to the entity pages. Masking must be idempotent.
            masked.append(low)
        elif _NUMERIC_SEG.match(seg) or _UUID_SEG.match(seg):
            masked.append(":id")
        elif low in SAFE_ROUTE_SEGMENTS:
            masked.append(low)
        else:
            # Unknown segment. It may be a legitimate new route, an entity slug,
            # an email address or a token — and from here they are
            # indistinguishable, so it is refused by name.
            masked.append(":seg")

    return "/".join(masked)[:MAX_STRING_LEN]


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

    return None


def _coerce_enum(key: str, value: Any) -> Optional[str]:
    """Admit a value only if it is in that FIELD's closed domain.

    Keyed by field name, not by kind, because "is this a legal value" is a
    question about `outcome_class` specifically — the previous version asked only
    "is this a string", which every identifier also answers yes to.

    A field with no declared domain is refused outright rather than waved
    through: forgetting to add a domain must cost the column its data, never
    cost the table its guarantee.
    """
    domain = _ENUM_DOMAINS.get(key)
    if domain is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed in domain else None


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
        if kind == "enum":
            coerced = _coerce_enum(key, params[key])
        else:
            coerced = _coerce(kind, params[key])
        if coerced is not None:
            clean[key] = coerced

    return event_name, clean
