"""Cache policy for the `/api/events/{id}/related-futures` tier (LAT-P136, P127-2).

Extracted out of `routes/events.py` under ruling 005 (extract-on-touch): this
queue changes the tier's serve decision, its fallback and its write path, so the
policy comes out of the route into a module that can be tested without a web
request, and the tier converts to the cache envelope
(`docs/contracts/cache-envelope.md`) on its way through.

WHAT WAS MEASURED, and it is not the build cost.

`GET /api/events/{id}/related-futures` is the section of the event detail page
that answers "what does this game mean for the season" — the Bigger Picture /
Playoff Path block. LAT-P127 parked it as **P127-2** at 19.85 s cold, LAT-P128
found and removed the largest single cause (the tier called `get_playoff_grid`,
the RAW builder, instead of `get_playoff_grid_cached` — a full grid rebuild
inline behind a key that was warm on both sides of it), and parked the rest.

This is the rest. Ten DISTINCT events taken off the live Discover feed on
2026-08-29, first touch each, production `fe5ec72c`, `x-timing-split` server
time:

    1,441  2,924  4,255  5,488  5,572  6,210  7,426  8,619  8,736  8,807  ms
    p50 5,891 ms · max 8,807 ms · `db` is 96-99 % of every one of them

Those are not tail samples. Every one of them is the FIRST request for a game
that was on the feed at that moment, which is exactly the request a person makes
by tapping a card. The reason they are all cold is the cache, not the build:

    _related_futures_cache: dict[int, tuple[float, str, dict]] = {}
    _RELATED_FUTURES_LIVE_TTL = 60
    _RELATED_FUTURES_MAX_SIZE = 30

A process-global dict of thirty entries — the same shape, one door down the same
file, that LAT-P121 replaced for `/game-markets` (#1587). The three properties
are the same and each is independently a reason almost nobody gets a hit:

  * It is per PROCESS. `WEB_CONCURRENCY=2` puts two Uvicorn workers on every
    dyno and there is more than one dyno, so a warm entry is visible to a
    fraction of requests even for a game everyone is watching.
  * It holds THIRTY events, evicted oldest-first, for a site whose feed shows
    dozens of games at once.
  * It dies with the process — every deploy, every dyno cycle.

So the tier had no shared cache at all, and — the part that costs the wait — no
mirror: a miss had never had anything to serve except a full rebuild.

WHAT THIS MODULE CHANGES.

  1. A SHARED slot in Redis, so the second person to open a game anywhere on the
     fleet gets what the first one built. The in-memory dict is kept as an L1 in
     front of it — it is faster than a Redis round trip and it is not the defect.
  2. A 24 h mirror that is a first-class SERVE path, not an error handler. On a
     primary miss the reader gets the mirror immediately and exactly one
     background rebuild is scheduled behind it.
  3. The envelope fields on the stored artifact, so a served payload discloses
     when its content was computed and whether it is live or stale.

🔴 THE MIRROR'S AGE CEILING IS IMPORTED FROM `game_markets_cache`, NOT CHOSEN.
This payload embeds live game state — `box_score`, `game_period`, `game_clock`,
`event_status` — so an over-old mirror of a LIVE game is a formatting lie of
exactly the kind the FORMATTING pillar exists to stop, arriving through a
latency fix. The sibling tier on the SAME PAGE already settled how old a mirror
of a live game may be (150 s) and of a finished one (5 h), and its own docstring
says why two disagreeing ceilings in one route would be a coin flip about which
one a reader gets. So this tier does not pick a third number: it calls
`game_markets_cache.stale_serve_ceiling_seconds`. **The event detail page has
ONE mirror-age law and both of its tiers obey it.**

That is deliberately NOT the same thing as sharing the fresh TTL. The ceiling
answers a page-level question — how stale may a reader's copy be — and the fresh
TTL answers a tier-level one — how often does this tier rebuild. This tier's
fresh TTL is carried across verbatim from the dict it replaces (60 s live), so
this ship changes who can see a cached copy and what a miss costs, never how
fresh the content is.

WHAT IS NOT DONE HERE, NAMED SO IT IS A DECISION.
  * The build is not made faster. The p50 5,891 ms above is untouched; what
    changes is how many people pay it. Which of the 14-16 queries dominates is a
    separate question — `maxq` ranged 639-7,641 ms across the ten samples, so it
    is not one query on every event — and it needs a production plan per event
    shape, not a guess. Parked as P136-1.
  * EMPTY answers are still not cached, because they are not cached today. The
    four `return empty` exits of the build are carried across with a `cacheable`
    flag rather than silently acquiring a 60 s memory: an event with no futures
    yet would start serving "no futures" for a TTL after they appear, which is a
    content change smuggled inside a latency change.
  * No negative caching, for the sibling's reason: a 404 here means the event id
    does not exist, which is not a load-bearing cost.
  * No warmer. Serve-stale needs no schedule to fail (LAT-P116's note): the
    rebuild is triggered BY the request that would otherwise have paid for it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.utils import game_markets_cache as _gmc
from app.utils.db_session_identity import UNKNOWN_BUILD
from app.utils.event_concept_cache import (
    AVAILABILITY_LIVE,
    AVAILABILITY_STALE_OK,
    ENVELOPE_FIELD,
    STALE_TTL as _SHARED_STALE_TTL,
    ConceptCacheKeys,
    cache_keys,
    get_client,
    payload_age_seconds,
    read_slot,
    stamp_envelope,
    with_availability,
    write_payload,
)

logger = logging.getLogger(__name__)

#: This tier's own Redis namespace. `cache_keys` takes a prefix precisely so a
#: third customer does not have to move its keys or re-derive the four-key
#: layout (#1651 was the first, `game_markets_cache` the second).
CACHE_PREFIX = "bainluck:related_futures:"

#: Fresh TTL for a game that has not finished. **Unchanged at 60 s** — it is
#: `_RELATED_FUTURES_LIVE_TTL`, the number the in-memory dict already used.
FRESH_TTL_LIVE = 60

#: Fresh TTL for a finished game. The in-memory dict cached these **for the life
#: of the process**, which was never a decision — it was what a dict with no
#: expiry does. A finished game's related futures move on winner backfill (6 h)
#: and on the next futures poll, so an hour bounds how long a payload can go on
#: claiming a season market is ungraded after it was graded. Strictly tighter
#: than what this replaces, not looser. Same number as the sibling tier's, which
#: is where the reasoning was first written down.
FRESH_TTL_FINAL = _gmc.FRESH_TTL_FINAL

#: The mirror. **Imported, not re-declared** — `write_payload` does not
#: parameterize the stale TTL, so a literal here would be a second constant the
#: writer never reads. This name exists so a reader of this tier can see the
#: number; it IS the shared one.
STALE_TTL = _SHARED_STALE_TTL

#: The statuses that mean the game is over. **Imported from the sibling**, so
#: finality does not acquire a second definition on the event detail page.
FINAL_STATUSES = _gmc.FINAL_STATUSES

#: Additive envelope field, outside the contract's five: the RAW `Event.status`
#: the payload was built from. The serve decision needs it (the ceiling is
#: per-status) and it is not recoverable from the body in general — the build's
#: four `empty` exits do not carry `event_status` at all.
SOURCE_STATUS_FIELD = _gmc.SOURCE_STATUS_FIELD

#: The build that produced the payload (#6355), **imported from the sibling** so
#: the two tiers that serve one page cannot disagree about what a deploy
#: invalidates. #6883: this tier shipped without it, and `FRESH_TTL_FINAL` above
#: is why that mattered — age alone cannot express "built by code that no longer
#: exists", because the payload a release invalidates is YOUNG, not old.
BUILD_FIELD = _gmc.BUILD_FIELD
SCHEDULED_STATUS = _gmc.SCHEDULED_STATUS
STALE_SERVE_CEILING_SCHEDULED = _gmc.STALE_SERVE_CEILING_SCHEDULED
SOURCE_COMMENCE_TIME_FIELD = _gmc.SOURCE_COMMENCE_TIME_FIELD

#: Explicit content/contract version stamped into `/related-futures` cache
#: entries (#13573). Bump whenever `_build_related_futures` changes what a
#: reader sees (shape, filtering, withholding, scoring); unrelated deploys leave
#: existing copies valid across releases while pre-versioned deploy stamps
#: (`"v6636"`, etc.) are refused once on first rollout.
RELATED_FUTURES_CACHE_VERSION: int = 1


def current_cache_version() -> str:
    """Content/contract version stamped into `/related-futures` cache entries (#13573)."""
    return f"rf-v{RELATED_FUTURES_CACHE_VERSION}"


def is_final(status: Any) -> bool:
    """True when `status` is a finished game, by the page's own definition."""
    return _gmc.is_final(status)


def is_scheduled(status: Any) -> bool:
    """True when `status` is a scheduled (pre-kickoff) game."""
    return _gmc.is_scheduled(status)


def fresh_ttl(status: Any) -> int:
    """The fresh TTL this payload's status earns."""
    return FRESH_TTL_FINAL if is_final(status) else FRESH_TTL_LIVE


def stale_serve_ceiling_seconds(status: Any) -> int:
    """How old a mirror of a payload with `status` may be and still be served.

    Delegated, not duplicated — see the module docstring. If the sibling tier
    ever re-tunes the event page's mirror-age law, this tier moves with it
    instead of quietly disagreeing with it.
    """
    return _gmc.stale_serve_ceiling_seconds(status)


def keys_for(event_id: int) -> ConceptCacheKeys:
    """Every Redis key one event's related-futures payload owns."""
    return cache_keys(str(event_id), prefix=CACHE_PREFIX)


def stamp(
    response: dict[str, Any],
    *,
    source_status: Any,
    created_at: datetime | None = None,
    lifecycle_watermark: datetime | None = None,
    source_commence_time: datetime | str | None = None,
) -> dict[str, Any]:
    """Attach the producer half of the envelope, plus this tier's raw status.

    Pure. `availability` stays None here on purpose — it is the SERVE decision,
    and the same stored bytes are `live` from the primary and `stale_ok` from
    the mirror, so it is stamped on the way out by `with_availability`.
    """
    enveloped = stamp_envelope(
        response,
        created_at=created_at or datetime.now(timezone.utc),
        lifecycle_watermark=lifecycle_watermark,
    )
    envelope = dict(enveloped.get(ENVELOPE_FIELD) or {})
    envelope[SOURCE_STATUS_FIELD] = str(source_status or "")
    envelope[BUILD_FIELD] = current_cache_version()
    commence_dt = _gmc._normalize_utc(source_commence_time)
    if commence_dt is not None:
        envelope[SOURCE_COMMENCE_TIME_FIELD] = commence_dt.isoformat()
    enveloped[ENVELOPE_FIELD] = envelope
    return enveloped


def build_id_of(payload: Any) -> str:
    """The stamp that produced a stored payload, or `""` when it does not say."""
    return _gmc.build_id_of(payload)


def payload_is_current_version(payload: Any) -> bool:
    """Was this payload built under `RELATED_FUTURES_CACHE_VERSION`? (#13573)

    Old deploy-build stamps (e.g. `"v6636"`) differ from `"rf-v1"`, so the
    first release after this ships throws old-style copies away once.
    Absent/`UNKNOWN_BUILD` stored or running values fail open as in #6883.
    """
    stored = build_id_of(payload)
    if not stored or stored == UNKNOWN_BUILD:
        return True
    running = current_cache_version()
    if not running or running == UNKNOWN_BUILD:
        return True
    return stored == running


payload_is_current_build = payload_is_current_version


def source_status_of(payload: Any) -> str:
    """The raw status a stored payload was built from, or `""` when absent.

    An absent field reads as not-final, which picks the SHORTER ceiling. That
    direction is deliberate: an unknown-status mirror is treated as if it were
    live, so the failure mode of a missing field is a rebuild, never a stale
    live payload.
    """
    return _gmc.source_status_of(payload)


def source_commence_time_of(payload: Any) -> datetime | None:
    """UTC kickoff stamped on a stored payload, or `None` when absent/invalid."""
    return _gmc.source_commence_time_of(payload)


def with_source_commence_time(
    payload: dict[str, Any], commence_time: datetime | str | None
) -> dict[str, Any]:
    """Attach normalized UTC `source_commence_time` to a stamped payload."""
    return _gmc.with_source_commence_time(payload, commence_time)


async def lookup_commence_time(db, event_id: int) -> datetime | None:
    """Best-effort `Event.commence_time` lookup on a build (#13573)."""
    try:
        from sqlalchemy import select

        from app.models.models import Event

        commence_time = await db.scalar(
            select(Event.commence_time).where(Event.id == event_id)
        )
    except Exception:
        logger.warning("related-futures: commence_time query failed", exc_info=True)
        return None
    if not isinstance(commence_time, datetime):
        return None
    return _gmc._normalize_utc(commence_time)


async def attach_scheduled_commence_time(
    db, event_id: int, response: Any, source_status: Any, enveloped: dict[str, Any]
) -> dict[str, Any]:
    """Resolve and stamp `source_commence_time` onto `scheduled` cache payloads."""
    return await _gmc.attach_scheduled_commence_time(
        db,
        event_id,
        response,
        source_status,
        enveloped,
        lookup_fn=lookup_commence_time,
    )


def mirror_is_servable(
    payload: Any, now: datetime | None = None
) -> tuple[bool, str]:
    """Is this mirror young enough to serve? Returns `(servable, reason)`.

    The reason is returned rather than logged so a test can assert WHICH branch
    fired — "too old" and "no timestamp" are different facts about the tier and
    a bool collapses them.
    """
    if not isinstance(payload, dict):
        return False, "absent"
    age = payload_age_seconds(payload, now)
    if age is None:
        # No `created_at` we can parse. The contract's whole point is that a
        # payload which cannot say when it was computed must not be served as
        # though it could — and here it would additionally be served under an
        # age bound we are unable to evaluate.
        return False, "no_created_at"
    if _gmc.scheduled_kickoff_passed(payload, now):
        return False, "kickoff_passed"
    status = source_status_of(payload)
    ceiling = (
        _gmc.stale_serve_ceiling_seconds(status, payload)
        if is_scheduled(status)
        else stale_serve_ceiling_seconds(status)
    )
    if age > ceiling:
        return False, "too_old"
    return True, "fresh_enough"


def read(event_id: int, rc=None) -> tuple[dict[str, Any] | None, str]:
    """Read the tier for `event_id`. Returns `(body, state)`.

    `state` is one of `live`, `stale_ok`, `stale_too_old`, `stale_build`, `miss`
    — the serve decision, made here and published in the body's envelope, never
    re-derived by a consumer (contract rule 1).

    `stale_build` (#6355, brought to this tier by #6883) is its own state and is
    not folded into `miss`: "there was nothing cached" and "there was something
    cached and a deploy made it a lie" are different facts about the tier, and
    only the second one is supposed to be rare.

    Never raises: every Redis helper below is best-effort by construction, and a
    cache that cannot be read must cost a rebuild, not a 500.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return None, "miss"
    keys = keys_for(event_id)

    primary = read_slot(client, keys.primary)
    if primary is not None:
        if payload_is_current_build(primary):
            return with_availability(primary, AVAILABILITY_LIVE), "live"
        # Young, and built by code that is no longer running. NOT demoted to the
        # mirror path — the mirror is the same bytes from the same dead build,
        # so serving it stale would launder the pre-ship payload through a
        # second door and call it a policy. A rebuild is the only honest exit.
        #
        # ⚠️ NEITHER `event_id` NOR THE STORED BUILD IS INTERPOLATED: CodeQL
        # grades a path parameter reaching a log line `py/log-injection` at
        # MEDIUM — a notice-32 refuse — and grades a string read back out of
        # Redis the same way. `current_build_id()` comes from the environment
        # and is not a taint source. The signal worth having here is the COUNT
        # of these lines just after a release, not which event; the refused
        # payload names its own build in the envelope this module publishes.
        logger.info(
            "related-futures: a slot built by an older cache version was refused "
            "(running version %s) — rebuilding",
            current_cache_version(),
        )
        return None, "stale_build"

    mirror = read_slot(client, keys.stale)
    if mirror is None:
        return None, "miss"
    if not payload_is_current_build(mirror):
        # `event_id` deliberately absent, per the primary branch above. The
        # sibling line below it DOES carry the id and is pre-existing debt a new
        # line must not add to.
        logger.info(
            "related-futures: a mirror built by an older cache version was refused "
            "(running version %s) — reader will rebuild",
            current_cache_version(),
        )
        return None, "stale_build"
    servable, reason = mirror_is_servable(mirror)
    if not servable:
        logger.info(
            "related-futures mirror for %s refused (%s) — reader will rebuild",
            event_id,
            reason,
        )
        return None, "stale_too_old"
    return with_availability(mirror, AVAILABILITY_STALE_OK), "stale_ok"


def write(event_id: int, enveloped: dict[str, Any], rc=None) -> bool:
    """Publish a stamped payload to both slots. Returns whether it was ATTEMPTED.

    `write_payload` swallows its own Redis failures and returns None, so the
    honest thing this can report is "there was a client and we handed it the
    bytes", not "Redis has them". A caller must not read the return value as
    durability — the next read is the only thing that can establish that.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return False
    write_payload(
        client,
        keys_for(event_id),
        enveloped,
        primary_ttl=fresh_ttl(source_status_of(enveloped)),
    )
    return True


async def compute_watermark(db, market_ids: list[int]) -> datetime | None:
    """The newest upstream fact this payload reflects (contract field 5).

    `max(FuturesMarket.updated_at)` over exactly the markets the payload was
    assembled from — the season markets, the game props and the series markets.
    One indexed aggregate over a handful of primary keys, run only on a BUILD
    (which already costs seconds) and never on a serve.

    A watermark we could not compute reads as null. Per the contract that is a
    published answer, and it is the honest one.

    Not delegated to the sibling even though the query is identical: its failure
    path logs `game-markets: watermark query failed`, and a warning that names
    the wrong tier is worse than a duplicated four-line query.
    """
    if not market_ids:
        return None
    try:
        from sqlalchemy import func, select

        from app.models.models import FuturesMarket

        newest = await db.scalar(
            select(func.max(FuturesMarket.updated_at)).where(
                FuturesMarket.id.in_(market_ids)
            )
        )
    except Exception:
        logger.warning("related-futures: watermark query failed", exc_info=True)
        return None
    if not isinstance(newest, datetime):
        return None
    return newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
