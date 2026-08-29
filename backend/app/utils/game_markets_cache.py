"""Cache policy for the `/api/events/{id}/game-markets` tier (#1587, LAT-P121).

Extracted out of `routes/events.py` under ruling 005 (extract-on-touch): this
queue changes the tier's serve decision, its fallback and its write path, so the
policy comes out of the route into a module that can be tested without a web
request, and the tier converts to the cache envelope
(`docs/contracts/cache-envelope.md`) on its way through.

WHAT WAS WRONG, and it is not the build cost.

`GET /api/events/{id}/game-markets` is the SECOND request of the event detail
page — the page where the probability a person came for actually lives, and one
of the four north-star tasks. #1587 measured it on production at **2.25 s for
8.5 KB**: a small payload and a slow response, which points at the build.

But the reason a person pays that build is the cache, not the query. The tier's
only cache was:

    _game_markets_cache: dict[int, tuple[float, str, dict]] = {}
    _GAME_MARKETS_MAX_SIZE = 30

— a **process-global dict of thirty entries**. Three properties follow, and each
of them is a reason almost nobody ever gets a hit:

  * It is per PROCESS. `WEB_CONCURRENCY=2` means two Uvicorn workers per dyno,
    and there is more than one dyno, so a warm entry is visible to a fraction of
    requests even for a game everyone is watching. Two people opening the same
    game a second apart routinely land on different workers and both pay 2.25 s.
  * It holds THIRTY events, evicted oldest-first, for a site whose feed shows
    dozens of games at once. On any busy evening the entry for the game you are
    about to open has already been evicted by the games somebody else opened.
  * It dies with the process. Every deploy, every dyno cycle, every Heroku
    restart empties it, and the first reader of every game pays full price again.

So the tier had no shared cache at all, and — the part that actually costs the
wait — **no mirror**: a miss has never had anything to serve except a full
rebuild. This is the same shape LAT-P021 fixed for `/api/event/{key}` (#1107)
and #1651 records for `hub.py`: *while a miss costs a build, a slow enough build
has no exit via user traffic.*

WHAT THIS MODULE CHANGES.

  1. A SHARED slot in Redis, so the second person to open a game anywhere on the
     fleet gets what the first one built. The in-memory dict is kept as an L1 in
     front of it — it is faster than a Redis round trip and it is not the defect.
  2. A 24h mirror that is a first-class SERVE path, not an error handler. On a
     primary miss the reader gets the mirror immediately and exactly one
     background rebuild is scheduled behind it (`_serve_stale_and_refresh`,
     already in `routes/events.py` three lines above the dict this replaces).
  3. The five envelope fields on the stored artifact, so a served payload
     discloses when its content was computed, how far into reality the build had
     got, and whether it is live or stale.

🔴 THE MIRROR IS AGE-BOUNDED BY STATUS, AND THAT IS NOT DECORATION.
This payload is a function of the CLOCK as well as of the database: it filters
player props through `prop_window_closed` and it publishes
`served_event_status(...)`. A 24h-old mirror of a LIVE game would show prop
windows that closed hours ago — a formatting lie of exactly the kind the
FORMATTING pillar exists to stop, arriving through a latency fix. So the mirror
is only served while it is younger than `STALE_SERVE_CEILING` x the tier's own
fresh TTL for that status (150 s live, 5 h final); past that the reader blocks
and rebuilds, which is the pre-existing behaviour. A permanently-failing refresh
degrades to slow, never to wrong. The ceiling multiple is LAT-P116's, from the
same file, deliberately: two serve-stale ceilings in one route that disagree
would be a coin flip about which one a reader gets.

WHAT IS NOT DONE HERE, NAMED SO IT IS A DECISION.
  * The build is not made faster. #1587's 2.25 s is untouched; what changes is
    how many people pay it. Whether the roster/ILIKE arms can be cheapened is a
    separate question and it needs a production plan, not a guess.
  * No negative caching. `cache_keys` carries a `negative` slot and this tier
    does not use it: a 404 here means the event id does not exist, which is not
    a load-bearing cost, and a negative slot that outlives an event's creation
    would be a new bug for no measured win.
  * No warmer. Serve-stale needs no schedule to fail (LAT-P116's note): the
    rebuild is triggered BY the request that would otherwise have paid for it.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

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
#: second customer does not have to move its keys or re-derive the four-key
#: layout (its docstring names #1651 as the first such case; this is the second).
CACHE_PREFIX = "bainluck:game_markets:"

#: Fresh TTL for a game that has not finished. **Unchanged at 30 s** — it is
#: `_GAME_MARKETS_LIVE_TTL`, the number the in-memory dict already used. This
#: ship is about who can see a cached copy and what a miss costs, not about how
#: fresh the content is, so the freshness rule is carried across verbatim.
FRESH_TTL_LIVE = 30

#: Fresh TTL for a finished game. The in-memory dict cached these **for the life
#: of the process**, which was never a decision — it was what a dict with no
#: expiry does. A finished game's markets stop moving except for winner
#: backfill, which runs every 6h, so an hour bounds how long a payload can go on
#: claiming a prop is ungraded after it was graded. That is strictly tighter
#: than what this replaces, not looser.
FRESH_TTL_FINAL = 3600

#: The mirror. **Imported, not re-declared.** `write_payload` does not
#: parameterize the stale TTL — "the mirror's job is to outlive an outage, and
#: that is the same job for every tier" — so a 86400 written here would be a
#: second constant that the writer never reads and that nothing compares. This
#: name exists so a reader of this tier can see the number; it IS the shared one.
STALE_TTL = _SHARED_STALE_TTL

#: How far past its fresh TTL a mirror may still be served while a rebuild runs
#: behind it. 5x, which is `_STALE_SERVE_CEILING` in `routes/events.py` — see
#: the module docstring for why it is deliberately the same number.
STALE_SERVE_CEILING = 5

#: The statuses that mean the game is over. Same tuple the in-memory cache used
#: for its "cache indefinitely" branch, so finality does not acquire a second
#: definition on the way into Redis.
FINAL_STATUSES = frozenset({"completed", "closed"})

#: Additive envelope field, outside the contract's five: the RAW `Event.status`
#: the payload was built from. The serve decision needs it (the ceiling is
#: per-status) and it cannot be re-derived from the body, whose `status` is
#: `served_event_status`' presentation value and not the row's.
SOURCE_STATUS_FIELD = "source_status"

def is_final(status: Any) -> bool:
    """True when `status` is a finished game, by the tier's own definition."""
    return str(status or "").lower() in FINAL_STATUSES


def fresh_ttl(status: Any) -> int:
    """The fresh TTL this payload's status earns."""
    return FRESH_TTL_FINAL if is_final(status) else FRESH_TTL_LIVE


def stale_serve_ceiling_seconds(status: Any) -> int:
    """How old a mirror of a payload with `status` may be and still be served."""
    return STALE_SERVE_CEILING * fresh_ttl(status)


def keys_for(event_id: int) -> ConceptCacheKeys:
    """Every Redis key one event's game-markets payload owns."""
    return cache_keys(str(event_id), prefix=CACHE_PREFIX)


def stamp(
    response: dict[str, Any],
    *,
    source_status: Any,
    created_at: datetime | None = None,
    lifecycle_watermark: datetime | None = None,
) -> dict[str, Any]:
    """Attach the producer half of the envelope, plus this tier's raw status.

    Pure. `availability` stays None here on purpose — it is the SERVE decision
    and the same stored bytes are `live` from the primary and `stale_ok` from the
    mirror, so it is stamped on the way out by `with_availability`.
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
    if not isinstance(payload, dict):
        return ""
    envelope = payload.get(ENVELOPE_FIELD)
    if not isinstance(envelope, dict):
        return ""
    return str(envelope.get(SOURCE_STATUS_FIELD) or "")


def mirror_is_servable(
    payload: Any, now: datetime | None = None
) -> tuple[bool, str]:
    """Is this mirror young enough to serve? Returns `(servable, reason)`.

    The reason is returned rather than logged so a test can assert WHICH branch
    fired — "too old" and "no timestamp" are different facts about the tier and a
    bool collapses them.
    """
    if not isinstance(payload, dict):
        return False, "absent"
    age = payload_age_seconds(payload, now)
    if age is None:
        # No `created_at` we can parse. The contract's whole point is that a
        # payload which cannot say when it was computed must not be served as
        # though it could — and here it would additionally be served under an
        # age bound that we are unable to evaluate.
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
            "game-markets mirror for %s refused (%s) — reader will rebuild",
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
    assembled from. One indexed aggregate over a handful of primary keys, run
    only on a BUILD — which already costs seconds — and never on a serve.

    A watermark we could not compute reads as null. Per the contract that is a
    published answer, and it is the honest one: coercing something else would put
    a fabricated freshness claim on the payload.
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
        logger.warning("game-markets: watermark query failed", exc_info=True)
        return None
    if not isinstance(newest, datetime):
        return None
    return newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
