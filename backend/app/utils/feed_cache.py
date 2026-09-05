"""Shared helpers for Discover feed response cache management."""

from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

FEED_RESPONSE_CACHE_PREFIX = "feed_cache"
FEED_RESPONSE_STALE_TTL_SECONDS = 300

# LAT-P001: ASGI-scope marker that tells ``GET /api/feed`` to skip the response
# cache READ and genuinely rebuild. Lives in the scope (not a header/query param)
# precisely so no HTTP caller can set it — see the note at its use site.
FEED_PREWARM_SCOPE_KEY = "bainluck_feed_prewarm"

# Scope slot the route writes the RESOLVED cache key back into during a pre-warm,
# so the warmer publishes under the exact key the request path would read.
FEED_PREWARM_KEY_SCOPE_KEY = "bainluck_feed_prewarm_key"

# Response-cache TTLs by principal (see ``feed_response_cache_ttl``).
FEED_RESPONSE_TTL_ANON_SECONDS = 60
FEED_RESPONSE_TTL_IDENTIFIED_SECONDS = 5
FEED_RESPONSE_TTL_MY_TEAMS_SECONDS = 30

# --- #2216: live-awareness -----------------------------------------------------
# The principal TTLs above ask WHO is reading. They never ask WHAT the page
# contains, so a page holding an in-progress game aged exactly as long as a page
# of futures: 30-60s fresh, +300s on the stale mirror, and an UNBOUNDED
# process-local last-good behind that. Alex's push alert said 1-0 while both My
# Stuff cards said 0-0; the DB and ``GET /api/events/{id}`` both had 0-1. The
# write side was right and the page cache served an older payload as current.
#
# ``GET /api/events/{id}`` has never had this bug because it stores the event's
# status beside the payload and picks its TTL FROM that status
# (``routes/events.py:1841`` / ``:5771-5773``). These constants are that same
# rule for the card path, with the state read off the payload instead of a
# single row — a feed page is "live" when any card on it is.
#
# THE NUMBER, written down and defended: **60 seconds is the live ceiling** —
# the oldest a payload containing a live card may be and still be served.
#   * 30s fresh mirrors ``_EVENT_DETAIL_LIVE_TTL`` exactly. The detail route and
#     the card route read the SAME ORM fields; two different answers about the
#     same score is the defect, so they get one staleness rule.
#   * 60s on the stale mirror and on last-good is the actual fix. Fresh was
#     never the problem (30s); 30 + 300 = 330s, unbounded on a Redis blip, was.
#   * Past the ceiling the page is REBUILT, not served older. A five-minute-old
#     score printed as current is the app lying quietly, and the reliability bar
#     is "the app does what it's supposed to do".
# Anti-stampede is preserved by the per-key singleflight, not by the ceiling:
# waiters coalesce onto one leader, so refusing a stale live page costs one
# build per key per process, never a herd.
FEED_RESPONSE_TTL_LIVE_SECONDS = 30
FEED_RESPONSE_STALE_TTL_LIVE_SECONDS = 60
FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS = 60

# --- #2236: the republish period lives beside the ceiling it must respect ------
# The ceiling above is a bound on how OLD a served live payload may be. A warmer
# is the thing that keeps a key from ever reaching it. Those are two halves of
# one contract, and #2236 happened because they were written in two files: the
# ceiling here at 60 s, the warm rail's period in
# `tasks/__init__.py`'s beat schedule at 120 s, and nothing anywhere compared
# them. Both numbers were individually correct and their PRODUCT was that every
# live-containing feed shape paid a full cold build once a minute, forever,
# while the warm rail reported success — because it had genuinely warmed a key
# that then died a full minute before its next chance to be refreshed.
#
# So the period is declared HERE, three lines under the ceiling, and the
# arithmetic that ties them is a function rather than a comment.
#
#: How often a live-containing shape is republished. Strictly below the ceiling.
FEED_LIVE_REPUBLISH_PERIOD_S = 40
#: Wall budget for ONE republish pass. Not headroom — it is the second term of
#: the invariant: even a pass that burns its entire budget must still land
#: before the PREVIOUS publication's stale mirror expires.
FEED_LIVE_REPUBLISH_BUDGET_S = 20

# --- #3233: the term the budget never counted — how much ONE build costs ------
# The two numbers above bound the pass. Neither says anything about the work
# inside it, and that gap is what #3233 measured: the pass ran its targets
# SEQUENTIALLY, each given `BUDGET / N`, and once N reached 5 that slice (4 s)
# fell below the cost of a single feed build. Every target was then started and
# killed — 1,322 passes a day, 290 timeouts in 24 h, nothing published, every
# counter green — and a reader opening the Sports tab paid a 4–6 s cold build
# once a minute.
#
# The generalisation, because this file has now hosted it twice (#2236 was a
# period and a ceiling nobody compared; LAT-P099 was a per-item deadline that
# tightened on every addition):
#
#     A per-item deadline obtained by dividing a wall by an item count drops
#     below the cost of one item as items are added, and at that moment the pass
#     stops doing anything at all rather than doing less.
#
# So the cost of one item is declared here, next to the wall it has to fit in,
# and `live_republish_target_headroom_s()` compares them.

#: What ONE feed build is assumed to cost, as a floor for "is it worth starting".
#: Measured on production 2026-09-05 (#3233): the 40 s rail's targets timed out
#: at slices of 3.5–5.0 s, so a build costs MORE than 5 s; the 120 s host pass
#: times out on `discover` at its own 11.4 s slice, so the tail runs past 11 s.
#: 6 s is deliberately the FLOOR of the observed range and not the tail — it is
#: used to decide whether starting a build can possibly pay, and a floor is the
#: honest bound for that question. A target with less than this left is skipped
#: rather than started, because a build that will be killed costs the same
#: database work as one that completes and publishes nothing.
FEED_PREWARM_MIN_VIABLE_BUILD_S = 6.0

#: How many republish targets may build AT ONCE.
#:
#: Concurrency is the only lever #2236 leaves. `PERIOD + BUDGET == 60` exactly,
#: with zero headroom against the live ceiling, so the wall cannot grow; and
#: five sequential 6 s builds need 30 s, which no ordering fits into 20 s.
#:
#: 3 is bounded by the task database pool, not chosen: `tasks/base.py` declares
#: `pool_size=3, max_overflow=2`. Three concurrent builds take the pooled slots
#: and leave the overflow entirely to co-resident tasks, so this is the largest
#: value that never reaches for overflow. `test_live_prewarm_concurrency.py`
#: reads that pool out of the source rather than restating it.
FEED_LIVE_REPUBLISH_CONCURRENCY = 3


def live_republish_target_headroom_s(target_count: int) -> float:
    """Spare wall seconds after serving ``target_count`` targets. Negative = cannot.

    The second invariant of the republish pass, stated once (#3233):

        ceil(N / CONCURRENCY) * MIN_VIABLE_BUILD_S <= BUDGET

    Read it as waves. With ``CONCURRENCY`` builds in flight at a time, N targets
    take ``ceil(N / CONCURRENCY)`` waves, and a wave cannot be assumed cheaper
    than one build. If the waves do not fit the wall, the pass is structurally
    unable to serve its targets no matter how the budget is divided — which is
    the state #3233 found, where the division itself was the mechanism.

    A function and not an import-time ``assert`` for the same reason as
    `live_republish_headroom_s()`: a guard test should fail loudly by name rather
    than take a dyno down. It is what makes a shape added past the pass's real
    capacity fail at the moment of the addition instead of a day later in
    production.

    At the numbers declared above that capacity is
    ``CONCURRENCY * floor(BUDGET / MIN_VIABLE_BUILD_S)`` = 9 shapes, and today's
    five sit at 8 s of headroom. The capacity is stated because it was NOT
    obvious: the first draft of #3233 asserted a sixth shape would trip this, and
    the arithmetic says the tenth does. A bound nobody has evaluated is a bound
    nobody knows the value of.
    """
    if target_count <= 0:
        return float(FEED_LIVE_REPUBLISH_BUDGET_S)
    waves = math.ceil(target_count / FEED_LIVE_REPUBLISH_CONCURRENCY)
    return FEED_LIVE_REPUBLISH_BUDGET_S - waves * FEED_PREWARM_MIN_VIABLE_BUILD_S


def live_republish_headroom_s() -> int:
    """Seconds of slack in the #2236 invariant. Negative means it is violated.

    The invariant, stated once so it cannot be re-derived differently by the
    next reader:

        PERIOD + BUDGET <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    Read it as a worst case, not an average. A pass fires at t=0 and publishes a
    payload whose stale mirror dies at t=60. The next pass fires at t=PERIOD and
    may take up to BUDGET before it publishes. If PERIOD + BUDGET exceeds the
    ceiling there is a window in which the key is simply gone and a user eats a
    cold build — which is exactly the state #2236 measured, with PERIOD=120 and
    no budget term at all.

    It is a function and not a bare `assert` at import time because a guard test
    should FAIL, loudly and by name, rather than take the web dyno down.
    """
    return (
        FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        - FEED_LIVE_REPUBLISH_PERIOD_S
        - FEED_LIVE_REPUBLISH_BUDGET_S
    )


# --- LAT-P230 (#3144): the OTHER term the ceiling never counted ---------------
def live_total_age_headroom_s(oldest_artifact_age_s: float) -> int:
    """Seconds a live payload may still be CACHED for, given its inputs' age.

    The ceiling above bounds how old a served live payload may be. It was written
    when a payload's age started at zero — the build read the database, and the
    only clock that then ran was the response cache's. Once a build can be
    assembled from a SHARED ARTIFACT that was already N seconds old
    (`principal_independent_cache`), the two ages ADD:

        artifact_age + response_age <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

    Nothing anywhere compared them, which is #2236's shape exactly — two
    individually-correct numbers whose PRODUCT nobody computed. So the sum is a
    function beside the ceiling it protects rather than an assumption at a call
    site, on the same reasoning that put `live_republish_headroom_s()` here.

    This became load-bearing when LAT-P230 raised `market_load`'s TTL to 120s. It
    is deliberately NOT scoped to that artifact: `market_load` cannot itself make
    a payload live (see the guard in `test_shared_artifact_total_age_lat_p230.py`),
    so the term this function adds is today usually zero. It exists for the NEXT
    namespace given a long TTL — the one whose exemption nobody will re-derive.

    Returns 0 once the inputs alone have spent the ceiling. The payload is then
    not cached at all, so the next reader REBUILDS rather than being served
    something older — which is what #2216 requires ("past the ceiling the page is
    REBUILT, not served older").

    The age is rounded UP, not truncated. TTLs are whole seconds and artifact ages
    are not, so the fractional part has to go somewhere; `int()` would round the
    INPUT'S age down and hand the difference to the response, which is the
    generous direction on a correctness bound. A 59.9s-old artifact has spent 60
    seconds of the ceiling, not 59.
    """
    spent = math.ceil(max(0.0, oldest_artifact_age_s))
    return max(0, FEED_RESPONSE_STALE_TTL_LIVE_SECONDS - spent)

# LAT-P089 operator kill switch for the inert-principal share.
FEED_INERT_PRINCIPAL_SHARE_ENV = "FEED_INERT_PRINCIPAL_SHARE"
_INERT_SHARE_OFF_VALUES = frozenset({"0", "false", "no", "off"})


def inert_principal_share_enabled() -> bool:
    """Whether an inert principal may read the anonymous cache entry.

    ``FEED_INERT_PRINCIPAL_SHARE=0`` turns the LAT-P089 share off process-wide
    without a code change, mirroring ``FEED_SHARED_BUILD_TTL_S=0`` for #2143's
    module.

    It exists because the correctness argument, though sound, is an EQUALITY
    ARGUMENT — if some future field makes a personalized context compare equal
    to the default one, identified users start receiving anonymous content, and
    the only other remedy is a full deploy cycle. An operator lever must be
    faster than a release when the failure mode is "the wrong person's feed".

    Unset (the normal state) means ENABLED. Anything unrecognised also means
    enabled, deliberately: a typo'd config value must not silently switch off a
    latency fix and leave everyone wondering why the cold builds came back.
    """
    raw = os.environ.get(FEED_INERT_PRINCIPAL_SHARE_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _INERT_SHARE_OFF_VALUES


# --- LAT-P141: the page base ---------------------------------------------------
# ``GET /api/feed`` builds the WHOLE ranked list on every request and then does
# ``feed_items[offset : offset + limit]``. ``offset`` reaches the build at
# exactly one place — that slice. Every other stage (pools, scoring, the display
# chain) depends on ``limit`` and the shape, never on the offset.
#
# The response cache, however, keys on ``offset``. So page 2 is a different key
# holding the same build, nobody warms it, and it is a guaranteed cold build.
# Measured on production 2026-08-30, one fresh ``x-session-id`` per sample,
# native Discover shape (``limit=50&event_pct=0.15``):
#
#     offset=0    46 ms   shared_hit
#     offset=50   1,329 ms   miss
#     offset=100  1,232 ms   miss
#     web offset=20  1,033 ms   miss     offset=40  1,164 ms   miss
#
# ``total`` was 105, i.e. the entire feed is three native pages, and the second
# and third cost 28x the first for a list the server had already built and
# thrown away.
#
# The page base is that list, stored once. One entry per shape-minus-offset
# serves every page of it.
#
# 🔴 IT IS ALWAYS THE ANONYMOUS BUILD, AND THAT IS STRUCTURAL, NOT A CONVENTION.
# This key takes no ``user_id`` and no ``session_id`` — not "defaulted to None",
# ABSENT — so no caller can key a personalized list into it by passing the wrong
# argument. The route publishes and reads it only under LAT-P089's own equality
# predicate (``ctx == PersonalizationContext()``), which is the already-ratified
# proof that such a build is byte-identical to the anonymous one. This inherits
# that argument rather than inventing a second one.
FEED_PAGE_BASE_CACHE_PREFIX = f"{FEED_RESPONSE_CACHE_PREFIX}:pagebase"

# The prefix is deliberately UNDER ``feed_cache:`` so
# ``invalidate_feed_response_cache``'s ``feed_cache:*`` scan already deletes
# bases and their stale mirrors. An invalidation that cleared the pages but left
# the base behind would re-serve the pre-invalidation list on the next scroll.
FEED_PAGE_BASE_ENV = "FEED_PAGE_BASE"
_PAGE_BASE_OFF_VALUES = frozenset({"0", "false", "no", "off"})

#: Where a stored base keeps its CERT-409 build time. Not ``cache.built_at``,
#: because ``cache`` describes a serve and the base is never served as-is.
FEED_PAGE_BASE_BUILT_AT_FIELD = "_page_base_built_at"


def feed_page_base_enabled() -> bool:
    """Whether the offset-independent page base may be read or published.

    Its own lever, not ``FEED_INERT_PRINCIPAL_SHARE``'s. The two share a
    soundness argument but not a failure mode: turning the inert share off is
    "stop letting sessions read the anonymous entry", turning this off is "stop
    serving pages from a stored list". An operator narrowing one should not have
    to accept the other.

    Unset means ENABLED, and an unrecognised value also means enabled — same
    reasoning as ``inert_principal_share_enabled``.
    """
    raw = os.environ.get(FEED_PAGE_BASE_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _PAGE_BASE_OFF_VALUES


def feed_page_base_cache_key(
    *,
    sport: Optional[str] = None,
    limit: int,
    include_events: bool = True,
    include_futures: bool = True,
    tags: Optional[str] = None,
    event_pct: Optional[float] = None,
    my_teams_only: bool = False,
    mode: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Key for one stored, offset-independent Discover build.

    Every parameter here is a build input. ``offset`` is absent because it is
    not one, and no principal appears because the base is only ever the
    anonymous build (see the block comment above).

    ``limit`` IS a build input and stays in the key —
    ``apply_discover_display_chain``'s own docstring says so ("Several stages
    size their windows from it, so it is part of the build, not just the
    slice"). Native (50) and web (20) therefore get one base each, which is
    honest: they are two different lists, not two windows onto one.

    ``tests/test_feed_page_base_p141.py`` pins this signature against
    ``get_feed``'s ``_cache_shape`` so a build input added to the response key
    cannot be silently omitted here — omitting one would serve page 2 of the
    wrong list, which no latency test would catch.
    """
    parts = (
        f"pagebase:{sport or 'all'}:{limit}:"
        f"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:"
        f"{my_teams_only}:{mode or 'discover'}"
    )
    if category:
        # Same prepended, length-delimited form as ``feed_response_cache_key``,
        # for the same two reasons. Here the docstring's warning is literal:
        # omitting `category` would serve page 2 of another category's list.
        parts = f"cat={len(category)}:{category}|{parts}"
    return f"{FEED_PAGE_BASE_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}"


def render_feed_page_from_base(
    base: Any, *, limit: int, offset: int
) -> Optional[dict]:
    """Slice a stored page base into the payload ``get_feed`` would have built.

    Pure: no clock, no I/O, no Redis. That is the point — the serve-time half of
    this fix is testable without a cache, and gotcha #44's "a test anchor must
    not branch on the clock" cannot bite a function that has no clock to branch
    on.

    Returns ``None`` — meaning "fail closed, build it" — for anything it cannot
    vouch for:

    * a non-dict base, or one whose ``items`` is not a list;
    * ``len(items) != total``. The base is the WHOLE list by construction, so a
      disagreement means a truncated, legacy or half-written blob. Serving one
      would silently under-report ``has_more`` and end a user's scroll early —
      a wrong answer, not a slow one, and the reliability bar puts that first.

    ``has_more`` is recomputed as ``(offset + limit) < total`` because that is
    the exact expression the build uses and the native client mirrors
    (``DiscoverViewModel.swift`` advances by the server page boundary, not by
    the decoded count).

    The base's own ``built_at`` (CERT-409) is stripped from the rendered page
    rather than passed through: it is the BASE's provenance, it belongs in the
    served page's ``cache`` metadata and nowhere else, and a stray top-level
    key would change the public response shape. The caller reads it off the
    base — ``feed_page_base_built_at`` — and stamps it there.
    """
    if not isinstance(base, dict):
        return None
    items = base.get("items")
    if not isinstance(items, list):
        return None
    total = base.get("total")
    if not isinstance(total, int) or total != len(items):
        return None
    out = dict(base)
    out["items"] = items[offset : offset + limit]
    out["total"] = total
    out["limit"] = limit
    out["offset"] = offset
    out["has_more"] = (offset + limit) < total
    # Both describe THIS serve or the BASE, never the page. Cache metadata is
    # stamped by the caller; provenance travels via `feed_page_base_built_at`.
    out.pop("cache", None)
    out.pop(FEED_PAGE_BASE_BUILT_AT_FIELD, None)
    return out


def feed_page_base_built_at(base: Any) -> Optional[float]:
    """The epoch at which a stored page base's CONTENT was computed.

    CERT-409's rule is that every tier CARRIES the build time rather than
    minting its own — otherwise each hop silently restarts the clock the live
    ceiling is measured against. The base cannot keep it in ``cache`` (that
    field is per-serve and is dropped on store), so it keeps it here, and this
    is the only reader.

    ``None`` for a base written before this field existed, which is the same
    legitimate-unknown ``_payload_built_at`` returns and degrades the same way:
    ``remember_last_good`` falls back to read-time, no weaker than the
    pre-LAT-P141 behaviour, exact again on the next rebuild.
    """
    if not isinstance(base, dict):
        return None
    built_at = base.get(FEED_PAGE_BASE_BUILT_AT_FIELD)
    return float(built_at) if isinstance(built_at, (int, float)) else None


def feed_response_cache_key(
    *,
    user_id: Any = None,
    session_id: Optional[str] = None,
    sport: Optional[str] = None,
    limit: int,
    offset: int,
    include_events: bool = True,
    include_futures: bool = True,
    tags: Optional[str] = None,
    event_pct: Optional[float] = None,
    my_teams_only: bool = False,
    mode: Optional[str] = None,
    category: Optional[str] = None,
) -> str:
    """Build the Redis response-cache key for one ``GET /api/feed`` shape.

    LAT-P001: this is the SINGLE source of truth for the key. It used to be an
    inline f-string in ``routes/feed.py``, which was fine while the request path
    was the only writer. The pre-warm beat is a second writer, and a warmer that
    computes the key even slightly differently warms a key nobody reads — it
    fails silently and looks exactly like a warmer that is working. Both callers
    now go through this function, and ``test_feed_prewarm.py`` pins that the
    warmed shapes equal the keys the route derives from the real request params.

    The principal segment mirrors the L2-242 shared-anon contract: an
    authenticated user and a session both get their own key; only a request with
    neither shares the ``anon`` key.
    """
    if user_id is not None:
        user_part = f"u:{user_id}"
    elif session_id:
        user_part = f"s:{session_id}"
    else:
        user_part = "anon"
    parts = (
        f"feed:{user_part}:{sport or 'all'}:{limit}:{offset}:"
        f"{include_events}:{include_futures}:{tags or ''}:{event_pct or ''}:"
        f"{my_teams_only}:{mode or 'discover'}"
    )
    if category:
        # PREPENDED and length-delimited, deliberately, on both counts.
        #
        # Prepended: every existing key begins ``feed:``, so a category-browse
        # key can never collide with a Discover / sports key — and a request
        # with no category hashes the byte-identical string it always did, so
        # shipping this does not cold-start the whole response cache.
        #
        # Length-delimited: `sport`, `tags` and `mode` are all free-form strings
        # in `parts`, so a bare separator is forgeable. `cat=<len>:<value>` is
        # not: two different categories cannot produce the same prefix.
        parts = f"cat={len(category)}:{category}|{parts}"
    return f"{FEED_RESPONSE_CACHE_PREFIX}:{hashlib.md5(parts.encode()).hexdigest()}"


def feed_response_cache_ttl(
    *, my_teams_only: bool = False, identified: bool = False
) -> int:
    """Fresh-TTL for a feed response cache entry.

    Session/user feeds change as impressions are recorded, so they stay short.
    The anonymous key is deliberately the longest-lived: it is the one key a
    first-time visitor can hit, and it is the key the pre-warm beat keeps warm.
    """
    if my_teams_only:
        return FEED_RESPONSE_TTL_MY_TEAMS_SECONDS
    return (
        FEED_RESPONSE_TTL_IDENTIFIED_SECONDS
        if identified
        else FEED_RESPONSE_TTL_ANON_SECONDS
    )


def payload_contains_live_event(payload: Any) -> bool:
    """Whether a built feed payload carries at least one live card (#2216).

    This is the feed's equivalent of the single ``event.status`` the detail
    route stores beside its cached response. A page is only as fresh as its
    fastest-moving card, so ONE live card makes the whole page live.

    Deliberately permissive in two ways, both toward freshness:

    * It does not filter on ``item["type"]``. Any card that declares itself
      ``status == "live"`` counts. A new card type that carries a live score
      should shorten the page's life on the day it ships, not on the day
      somebody remembers to add it to an allowlist here.
    * Anything it cannot parse — a non-dict payload, a missing or non-list
      ``items`` — returns ``False``, i.e. "not live", i.e. the ordinary TTL.
      That is the correct direction: this function only ever SHORTENS a TTL,
      so failing closed would mean a malformed payload silently gets the long
      one, while failing open would expire every unparseable page in 30s.

    Pure — no I/O, no clock. It is called on both the write and the read side
    precisely so the two cannot drift; the read path re-derives liveness from
    the payload rather than trusting a flag stamped into it, because a stamped
    flag can be dropped by any future serializer change without a test noticing.
    """
    if not isinstance(payload, dict):
        return False
    items = payload.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        data = item.get("data")
        if isinstance(data, dict) and data.get("status") == "live":
            return True
    return False


def feed_response_cache_ttls(
    *,
    my_teams_only: bool = False,
    identified: bool = False,
    live: bool = False,
    oldest_artifact_age_s: float = 0.0,
) -> tuple[int, int]:
    """``(fresh_ttl, stale_ttl)`` for one feed response cache entry (#2216).

    The principal rule (``feed_response_cache_ttl``) is unchanged and still
    decides the baseline. ``live=True`` then applies the live ceiling as a
    ``min``, never a replacement: the 5s identified TTL must stay 5s, because a
    live-aware ceiling that LENGTHENED anybody's cache would be a latency fix
    wearing a correctness fix's clothes.

    ``oldest_artifact_age_s`` (LAT-P230) is how old the oldest SHARED ARTIFACT
    this payload was built from already was — the term the ceiling never counted.
    It applies on the same discipline: a ``min``, only when ``live``, and it can
    only ever SHORTEN. Defaulting to ``0.0`` keeps every existing caller's answer
    byte-identical, so an un-updated call site is conservative rather than wrong.
    """
    fresh = feed_response_cache_ttl(
        my_teams_only=my_teams_only, identified=identified
    )
    stale = FEED_RESPONSE_STALE_TTL_SECONDS
    if live:
        fresh = min(fresh, FEED_RESPONSE_TTL_LIVE_SECONDS)
        stale = min(stale, FEED_RESPONSE_STALE_TTL_LIVE_SECONDS)
        # The inputs have already spent part of the ceiling.
        headroom = live_total_age_headroom_s(oldest_artifact_age_s)
        fresh = min(fresh, headroom)
        stale = min(stale, headroom)
    return fresh, stale


def build_feed_cache_metadata(
    status: str,
    *,
    ttl_seconds: int | None = None,
    stale_ttl_seconds: int | None = FEED_RESPONSE_STALE_TTL_SECONDS,
    reason: str | None = None,
    live: bool | None = None,
    built_at: float | None = None,
) -> dict[str, Any]:
    """Return stable cache metadata safe to expose in feed responses.

    ``live`` (#2216) is emitted only when known, so an untouched caller's
    payload shape is byte-identical to before. It is the field that makes the
    ceiling verifiable from outside the process: ``.cache.live == true`` with
    ``.cache.ttl_seconds`` still at 60 would mean the live rule did not fire,
    and that is a distinction no amount of reading ``status`` can make.

    ``built_at`` (CERT-409 [P1]) is the wall-clock epoch at which the payload's
    CONTENT was computed — not the moment some tier copied it. It travels with
    the payload through Redis and through every republication, because the live
    ceiling is a bound on how old a SCORE may be, and every tier that re-stamped
    its own read time was silently restarting that clock. Emitted only when
    known, on the same discipline as ``live``.
    """
    metadata: dict[str, Any] = {
        "status": status,
    }
    if built_at is not None:
        metadata["built_at"] = float(built_at)
    if ttl_seconds is not None:
        metadata["ttl_seconds"] = ttl_seconds
    if stale_ttl_seconds is not None:
        metadata["stale_ttl_seconds"] = stale_ttl_seconds
    if reason:
        metadata["reason"] = reason
    if live is not None:
        metadata["live"] = bool(live)
    return metadata


async def invalidate_feed_response_cache(reason: str) -> dict[str, Any]:
    """Delete cached Discover feed responses and stale fallbacks."""
    deleted = 0
    try:
        from app.tasks.redis_state import get_async_redis_client

        redis = get_async_redis_client()
        keys: list[Any] = []
        async for key in redis.scan_iter(
            match=f"{FEED_RESPONSE_CACHE_PREFIX}:*",
            count=100,
        ):
            keys.append(key)
            if len(keys) >= 100:
                deleted += await redis.delete(*keys) or 0
                keys = []
        if keys:
            deleted += await redis.delete(*keys) or 0
        await redis.aclose()
        return {"status": "ok", "deleted": deleted, "reason": reason}
    except Exception as exc:
        logger.warning("Failed to invalidate feed cache after %s: %s", reason, exc)
        return {"status": "error", "deleted": deleted, "reason": reason}
