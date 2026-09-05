"""#3315 — the market ids page one actually rendered, so the price net can reach them.

THE DEFECT THIS EXISTS FOR
--------------------------
``futures_price_refresh`` is the safety net for prices the discovery polls
structurally cannot reach. It selected on **value** (tier 1 above a volume
floor) and on **identity** (a committed tournament register). Neither of those
is the question a reader asks. The question a reader asks is *is the number on
the card I am looking at right*, and nothing in the selector knew which cards
those were.

Measured on production 2026-09-05 (latency lane, #3315; reproduced by this lane
against Polymarket Gamma directly before any code was written):

* "Brazil Presidential Election" rendered Flávio Bolsonaro at **26.2%** while
  Gamma quoted **39.9%** — 13.7 points, on Discover page one.
* Its ``futures_outcomes`` rows had last been written **1,109 hours** (46 days)
  earlier. The market carries **$114,137,967** of volume, four orders of
  magnitude over the sweep's own floor.
* It is ``market_tier = 2``. Every one of the seven Polymarket cards on page one
  was. The tier fence meant the safety net could not see a single one of them,
  however stale they got, and no instrument anywhere went red: the sweep ran on
  time, wrote what it selected, and reported success over a set that excluded
  the whole front page.

A value floor is a proxy for "someone is looking at this". This module is the
thing itself.

WHERE THE IDS COME FROM, AND WHY THAT SOURCE AND NOT A QUERY
-------------------------------------------------------------
Page one is the *ranker's* output. It is not derivable in SQL — it is the result
of scoring, demotion, diversity caps, story caps and dedup over a candidate base
that changes every two minutes. Any predicate that tried to re-derive it would
be a second ranker, drifting from the first, which is the LAT-P001
two-writers-one-key trap in a new costume.

So the ids are read off the payload the pre-warmer **just published**, in
``_prewarm_feed_shape``, by the writer that built it. That is the same move
``FEED_PREWARM_SHAPE_KEYS_KEY`` makes with the resolved cache key and it is safe
for the same reason: it is the route's own answer, carried forward, so it cannot
disagree with what the reader is served.

Every shape in ``FEED_PREWARM_SHAPES`` is ``offset = 0`` — Discover and Sports,
web and native, first paint. "Page one" is therefore exactly the set this
warmer covers, and :func:`record_served_market_ids` refuses anything else so a
later deeper shape cannot quietly enrol page two.

AN EMPTY LIST IS FOUR DIFFERENT FACTS, AND CONFLATING THEM WAS A REAL DEFECT
-----------------------------------------------------------------------------
🔴 CERT-1970 blocked the first version of this module for exactly the bug the
paragraph below now prevents, and it is worth stating as a finding rather than
as a design note, because the first version *acknowledged the distinction in a
comment and then returned the same value anyway*.

``served_market_ids()`` returned ``[]`` for all of:

* the hash is missing or expired — the warm rail has been dead for hours;
* every entry in it is corrupt;
* the Redis read failed;
* page one genuinely holds no futures cards.

The first three mean **this arm is not working**. The fourth means **this arm
is working and has nothing to do**. They are opposite, the task recorded only
``served_known = 0`` for all four, and ``_terminal()`` never consulted it — so a
low-value page-one card outside :data:`HIGH_VALUE_SQL` could stay stale
indefinitely while successful class work kept the enforced verdict at
``complete``. Gotcha #53, in the plumbing of a change whose own commit message
cited gotcha #53.

So :func:`served_signal` returns a STATE, not a list, and the four facts get
four names. ``fresh`` and ``empty`` are the arm working. ``never_seen`` is the
arm not yet bootstrapped — no consumer has ever observed it healthy, which is
what a first deploy looks like, and it may not be treated as a regression.
``unavailable`` is the arm having worked before and not working now, and the
sweep refuses a green verdict on it.

THE GRACE, AND WHY IT IS A CONSUMER-WRITTEN MARKER
---------------------------------------------------
"Unavailable" must not fire on a cold start or a single bad minute, and the
obvious place to remember "this was healthy recently" is the very store that is
unavailable. So the memory is a SEPARATE key, :data:`SERVED_SIGNAL_LAST_OK_KEY`,
written by the CONSUMER each time it observes a healthy signal and held for
thirty days — far longer than any outage this is meant to describe.

Its absence and its age answer different questions, and the failure directions
are opposite, so they are resolved separately:

* absent  -> ``never_seen``. Nothing has regressed; nothing has started.
* present, younger than :data:`SERVED_SIGNAL_GRACE_S` -> still inside the grace.
* present, older -> ``unavailable``. The arm worked, and has now been dark for
  longer than three of the consumer's own periods.

**A Redis failure resolves to ``unavailable``, not to ``never_seen``.** If the
read raised we cannot rule out that the arm was healthy, and the conservative
direction is the one that refuses to claim page-one coverage it cannot
demonstrate. Reading a failure as a cold start would restore the exact
false-green this module was blocked for.

FAILURE DIRECTIONS, ALL CHOSEN
-------------------------------
* **Over-inclusion is free.** A market that has rotated off page one but is
  still in the hash costs one re-price of a live market we already hold.
* **A retired shape cannot persist forever.** Redis expiry is key-wide, so a
  shape that stops warming keeps its ids alive for as long as its siblings keep
  refreshing the key. Each entry therefore carries its own write time and the
  reader prunes past :data:`SERVED_SHAPE_MAX_AGE_S`
  (``L1B-051-PER-SHAPE-SERVED-SIGNAL-EXPIRY``).
* Every function here swallows its own Redis failures. A Redis outage must cost
  the sweep its page-one arm and its green verdict — never the run.
"""

from __future__ import annotations

import json
import logging
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

#: Redis hash: pre-warm shape label -> JSON ``{"at": <epoch>, "ids": [...]}``
#: describing what that shape's last published payload rendered.
#:
#: A hash keyed by label, not a flat set: a shape that stops warming must be
#: able to drop out on its own without taking its siblings' ids with it, and a
#: shape that warms again must REPLACE its own list rather than accumulate into
#: a set that only ever grows. A growing set is how a "what page one is showing"
#: signal becomes "what page one has ever shown", which is the volume floor with
#: extra steps.
#:
#: ``at`` is per ENTRY and not merely per key, because Redis expiry is key-wide:
#: a shape that is retired or stops warming keeps its ids alive for as long as
#: any sibling keeps refreshing the key's TTL. Without a per-entry stamp a dead
#: label is priority work forever (CERT-1970's follow-up,
#: ``L1B-051-PER-SHAPE-SERVED-SIGNAL-EXPIRY``).
SERVED_MARKET_IDS_KEY = "bainluck:precompute:feed_prewarm:served_market_ids"

#: TTL on that hash, refreshed on every warm.
#:
#: Sized against the CONSUMER, not the producer. The producer runs every 40-120s;
#: the consumer (``refresh_stale_futures_prices``) runs hourly at :50, and the
#: longest observed pre-warm gap on production was 2,511s. A TTL near the
#: producer's period would leave the consumer reading an expired key on any bad
#: half hour. Six hours is long enough that only a genuinely dead warm rail
#: empties it, and short enough that a deleted shape's ids do not outlive the day.
SERVED_MARKET_IDS_TTL_S = 6 * 3600

#: How old one shape's entry may be before the reader ignores it.
#:
#: Bounded by the producer's behaviour, not by the key's TTL: the warm rail's
#: longest observed gap on production is 2,511s (42 minutes), so two hours is
#: generous against a rail that is merely struggling and decisive against one
#: that has stopped. It must stay BELOW :data:`SERVED_MARKET_IDS_TTL_S` or it
#: could never fire — the key would expire first and the pruning would be
#: unreachable code.
SERVED_SHAPE_MAX_AGE_S = 2 * 3600

#: Per-shape cap. The largest warmed shape asks for 200 items and a bundle can
#: carry several markets, so this is headroom rather than a bound anyone should
#: hit — it exists so a runaway payload cannot write an unbounded value into a
#: Redis hash. Truncation is logged, never silent.
MAX_SERVED_IDS_PER_SHAPE = 500

#: The consumer's memory that this signal was once healthy. See the module
#: docstring: it has to live outside the store whose absence it explains.
SERVED_SIGNAL_LAST_OK_KEY = "bainluck:futures_price_refresh:served_signal_last_ok"

#: Thirty days. Long enough that the marker's own expiry can never be mistaken
#: for "the arm was never healthy" across any outage worth describing, and
#: bounded so a permanently-retired signal does eventually stop accusing.
SERVED_SIGNAL_LAST_OK_TTL_S = 30 * 86_400

#: How long an unavailable signal is tolerated after the last healthy sighting
#: before the sweep refuses a green verdict.
#:
#: THREE of the consumer's own hourly periods, and the unit is the consumer's
#: because the consumer is what writes the marker: whatever the producer does,
#: this marker can never be fresher than one sweep, so a grace of one period
#: would be a coin flip on scheduling jitter. Three gives the warm rail two full
#: chances to come back before anything reads not-green, and still detects a
#: genuinely dead rail well inside a working day.
SERVED_SIGNAL_GRACE_S = 3 * 3600

#: The four facts an empty id list used to mean. See the module docstring.
SERVED_FRESH = "fresh"            #: read, healthy, and page one holds futures cards
SERVED_EMPTY = "empty"            #: read, healthy, and page one holds none
SERVED_NEVER_SEEN = "never_seen"  #: no consumer has ever observed it healthy
SERVED_WARMING_UP = "warming_up"  #: healthy recently enough not to be a regression
SERVED_UNAVAILABLE = "unavailable"  #: it worked before; it is not working now

#: The states a green verdict is allowed on.
#:
#: ``never_seen`` is here because a cold start is not a regression: nothing can
#: have been lost by an arm that has never run, and a first deploy would
#: otherwise alarm on its own bootstrap. ``warming_up`` is here because a signal
#: that was healthy within the grace has not yet demonstrated anything is wrong —
#: it is its own state rather than a reuse of ``never_seen``, because a reader
#: asking "has this ever worked" must not be answered "no" about a signal that
#: worked twenty minutes ago.
#:
#: ``unavailable`` is deliberately absent, and that omission IS CERT-1970's
#: repair. Adding it back makes the enforced verdict green while the page-one arm
#: is dark, which is the whole defect.
SERVED_GREEN_STATES = frozenset(
    {SERVED_FRESH, SERVED_EMPTY, SERVED_NEVER_SEEN, SERVED_WARMING_UP}
)


class ServedSignal(NamedTuple):
    """What page one is showing, AND whether we can currently tell.

    ``ids`` is meaningful only when ``state`` is :data:`SERVED_FRESH`; it is
    empty for every other state, and a caller that reads it without reading
    ``state`` is making the mistake this type exists to prevent.
    """

    state: str
    ids: list[int]
    shapes: int = 0            #: entries read, parsed and inside the age bound
    stale_shapes: int = 0      #: entries pruned for age (a retired warm target)
    unreadable_shapes: int = 0  #: entries present and not parseable

    @property
    def green_allowed(self) -> bool:
        return self.state in SERVED_GREEN_STATES


def market_ids_in_feed_payload(payload) -> list[int]:
    """Every futures market id a feed payload renders, deduped, order preserved.

    THREE PLACES AN ID HIDES, and missing any one of them re-opens the hole for
    a whole card type:

    * a top-level ``{"type": "futures", "data": {"id": N}}`` card;
    * a ``bundle``'s ``data.member_ids`` — the ids the bundle was built from;
    * a ``bundle``'s ``data.items``, which are themselves feed items and carry
      their own ``data.id``. Six of the twenty cards on Discover page one were
      bundles on 2026-09-05, so walking only the top level would miss most of
      the page.

    ``event`` / ``concept`` / ``tournament`` cards carry event ids, not futures
    market ids, and are deliberately not collected: an event id passed to the
    price sweep would select the wrong row or none, and "none" is the failure
    that looks like success.

    Pure and total: any shape it does not understand yields nothing rather than
    raising into the pre-warm path, which must never fail because of this.
    """
    seen: dict[int, None] = {}

    def _collect(items) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            data = item.get("data")
            if not isinstance(data, dict):
                continue
            if item.get("type") == "futures":
                _add(data.get("id"))
            # A bundle is a container, so both of its id-bearing fields are read.
            # They overlap in practice and the dict dedupes them; relying on the
            # overlap would make whichever one is dropped look harmless.
            for member in data.get("member_ids") or []:
                _add(member)
            _collect(data.get("items"))

    def _add(value) -> None:
        # `bool` is an `int` subclass and `True` would collect as market 1 — the
        # same trap `tournament_register` documents. Rejected by type, not by
        # value, so a `True` cannot arrive as a plausible id.
        if isinstance(value, bool) or not isinstance(value, int):
            return
        if value > 0:
            seen.setdefault(value, None)

    if isinstance(payload, dict):
        _collect(payload.get("items"))
    return list(seen)


def record_served_market_ids(rc, label: str, market_ids) -> None:
    """Publish one shape's served ids, stamped with the time it rendered them.

    REPLACES the shape's list rather than merging into it — see the note on
    :data:`SERVED_MARKET_IDS_KEY`. An empty list is written as an empty list, not
    skipped: a shape that legitimately renders no futures cards must be able to
    say so, or its last non-empty answer stands until the age bound retires it.

    The stamp is what makes a per-shape age bound possible at all, and the key's
    TTL is refreshed on every write including the empty one, so the key's expiry
    tracks the rail's liveness while each entry's stamp tracks its own shape's.
    """
    if not rc or not label:
        return
    ids = list(market_ids or [])
    if len(ids) > MAX_SERVED_IDS_PER_SHAPE:
        logger.warning(
            "served-market-ids: %s rendered %d markets, capping at %d",
            label,
            len(ids),
            MAX_SERVED_IDS_PER_SHAPE,
        )
        ids = ids[:MAX_SERVED_IDS_PER_SHAPE]
    try:
        pipe = rc.pipeline(transaction=True)
        pipe.hset(
            SERVED_MARKET_IDS_KEY,
            label,
            json.dumps({"at": int(time.time()), "ids": ids}),
        )
        pipe.expire(SERVED_MARKET_IDS_KEY, SERVED_MARKET_IDS_TTL_S)
        pipe.execute()
    except Exception:
        logger.debug("served-market-ids write failed for %s", label, exc_info=True)


def _decode(value):
    """One hash value -> ``(at, ids)``, or ``None`` if it cannot be read."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode()
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    at = parsed.get("at")
    raw_ids = parsed.get("ids")
    # `at` is REQUIRED. An entry without one cannot be aged out, and silently
    # treating it as fresh would reinstate the immortal retired shape this stamp
    # was added to kill.
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    if not isinstance(raw_ids, list):
        return None
    ids = [
        i for i in raw_ids if not isinstance(i, bool) and isinstance(i, int) and i > 0
    ]
    return float(at), ids


def served_signal(now: float | None = None) -> ServedSignal:
    """What page one is showing, and whether we can currently tell.

    Read the module docstring before changing any branch here: every one of them
    is a different fact that used to arrive as an empty list, and CERT-1970
    blocked this change for exactly that conflation.

    ``now`` is injectable so the age bound and the grace can be tested at a fixed
    clock rather than by sleeping — and, per gotcha #44, the tests offset from a
    supplied anchor instead of branching on the wall clock.
    """
    now = time.time() if now is None else now
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        raw = rc.hgetall(SERVED_MARKET_IDS_KEY) or {}
    except Exception:
        # THE READ FAILED, so we cannot rule out that this arm was healthy. That
        # is `unavailable`, never `never_seen`: reading a Redis outage as a cold
        # start is the false-green this module was blocked for.
        logger.debug("served-market-ids read failed", exc_info=True)
        return ServedSignal(state=SERVED_UNAVAILABLE, ids=[])

    ids: set[int] = set()
    shapes = stale = unreadable = 0
    for value in raw.values():
        decoded = _decode(value)
        if decoded is None:
            unreadable += 1
            continue
        at, shape_ids = decoded
        if now - at > SERVED_SHAPE_MAX_AGE_S:
            # A warm target that has stopped warming. Its ids are not what page
            # one is showing; they are what it was showing.
            stale += 1
            continue
        shapes += 1
        ids.update(shape_ids)

    if shapes == 0:
        # No usable entry: the key is missing or expired, or every entry in it is
        # stale or corrupt. All of those mean the arm is not working — the only
        # question left is whether it ever did.
        return ServedSignal(
            state=_unavailable_or_never_seen(now),
            ids=[],
            stale_shapes=stale,
            unreadable_shapes=unreadable,
        )

    return ServedSignal(
        state=SERVED_FRESH if ids else SERVED_EMPTY,
        ids=sorted(ids),
        shapes=shapes,
        stale_shapes=stale,
        unreadable_shapes=unreadable,
    )


def _unavailable_or_never_seen(now: float) -> str:
    """Has this signal EVER been observed healthy, and how long ago?

    Same conservative direction as the caller: a marker we cannot read leaves the
    state ``unavailable``, because "I could not check whether this used to work"
    is not evidence that it never did.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        raw = rc.get(SERVED_SIGNAL_LAST_OK_KEY)
    except Exception:
        logger.debug("served-signal last-ok read failed", exc_info=True)
        return SERVED_UNAVAILABLE

    if raw is None:
        return SERVED_NEVER_SEEN
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    try:
        last_ok = float(raw)
    except (TypeError, ValueError):
        # A marker we cannot parse is still a marker: something wrote it, so the
        # arm has been healthy at least once. Fail toward not-green.
        return SERVED_UNAVAILABLE
    if now - last_ok > SERVED_SIGNAL_GRACE_S:
        return SERVED_UNAVAILABLE
    return SERVED_WARMING_UP


def note_served_signal_healthy(now: float | None = None) -> None:
    """Remember that a consumer saw this signal working. Never raises.

    Written by the SWEEP and not by the warmer, deliberately: the question the
    marker answers is "has the thing that depends on this ever had it", and only
    the depender can answer that. A warmer-written marker would say the producer
    ran, which is the fact already in the hash.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        rc.setex(
            SERVED_SIGNAL_LAST_OK_KEY,
            SERVED_SIGNAL_LAST_OK_TTL_S,
            str(int(time.time() if now is None else now)),
        )
    except Exception:
        logger.debug("served-signal last-ok write failed", exc_info=True)
