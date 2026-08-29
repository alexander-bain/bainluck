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


def is_final(status: Any) -> bool:
    """True when `status` is a finished game, by the page's own definition."""
    return _gmc.is_final(status)


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
    enveloped[ENVELOPE_FIELD] = envelope
    return enveloped


def source_status_of(payload: Any) -> str:
    """The raw status a stored payload was built from, or `""` when absent.

    An absent field reads as not-final, which picks the SHORTER ceiling. That
    direction is deliberate: an unknown-status mirror is treated as if it were
    live, so the failure mode of a missing field is a rebuild, never a stale
    live payload.
    """
    return _gmc.source_status_of(payload)


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
    ceiling = stale_serve_ceiling_seconds(source_status_of(payload))
    if age > ceiling:
        return False, "too_old"
    return True, "fresh_enough"


def read(event_id: int, rc=None) -> tuple[dict[str, Any] | None, str]:
    """Read the tier for `event_id`. Returns `(body, state)`.

    `state` is one of `live`, `stale_ok`, `stale_too_old`, `miss` — the serve
    decision, made here and published in the body's envelope, never re-derived
    by a consumer (contract rule 1).

    Never raises: every Redis helper below is best-effort by construction, and a
    cache that cannot be read must cost a rebuild, not a 500.
    """
    client = rc if rc is not None else get_client()
    if client is None:
        return None, "miss"
    keys = keys_for(event_id)

    primary = read_slot(client, keys.primary)
    if primary is not None:
        return with_availability(primary, AVAILABILITY_LIVE), "live"

    mirror = read_slot(client, keys.stale)
    if mirror is None:
        return None, "miss"
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
