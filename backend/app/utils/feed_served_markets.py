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

FAILURE DIRECTIONS, BOTH CHOSEN
--------------------------------
* **Over-inclusion is free.** A market that has rotated off page one but is
  still in the hash costs one re-price of a live market we already hold. The
  TTL is generous for exactly that reason.
* **Under-inclusion is the bug this closes**, so the reader never invents a
  bound of its own: it takes what is there and reports how many, and the task
  reports that count in its stats. An empty set is a *number in the run
  summary*, not a silent no-op (gotcha #53).
* Every function here swallows its own Redis failures. A Redis outage must cost
  the sweep its page-one arm, never the run.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

#: Redis hash: pre-warm shape label -> JSON list of the futures market ids that
#: shape's last published payload rendered.
#:
#: A hash keyed by label, not a flat set: a shape that stops warming must be
#: able to drop out on its own without taking its siblings' ids with it, and a
#: shape that warms again must REPLACE its own list rather than accumulate into
#: a set that only ever grows. A growing set is how a "what is on page one"
#: signal becomes "what was ever on page one", which is the volume floor again.
SERVED_MARKET_IDS_KEY = "bainluck:precompute:feed_prewarm:served_market_ids"

#: TTL on that hash, refreshed on every warm.
#:
#: Sized against the CONSUMER, not the producer. The producer runs every 40-120s;
#: the consumer (``refresh_stale_futures_prices``) runs hourly at :50, and the
#: longest observed pre-warm gap on production was 2,511s. A TTL near the
#: producer's period would leave the consumer reading an expired key on any bad
#: half hour and silently reverting to the pre-#3315 coverage. Six hours is long
#: enough that only a genuinely dead warm rail empties it, and short enough that
#: a deleted shape's ids do not outlive the day.
SERVED_MARKET_IDS_TTL_S = 6 * 3600

#: Per-shape cap. The largest warmed shape asks for 200 items and a bundle can
#: carry several markets, so this is headroom rather than a bound anyone should
#: hit — it exists so a runaway payload cannot write an unbounded value into a
#: Redis hash. Truncation is logged, never silent.
MAX_SERVED_IDS_PER_SHAPE = 500


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
    """Publish one shape's served ids. Never raises.

    REPLACES the shape's list rather than merging into it — see the note on
    :data:`SERVED_MARKET_IDS_KEY`. An empty list is written as an empty list, not
    skipped: a shape that legitimately renders no futures cards must be able to
    say so, or its last non-empty answer stands for six hours.

    The TTL is refreshed on every write, including the empty one, so the hash's
    expiry tracks the rail's liveness rather than the last interesting payload.
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
        pipe.hset(SERVED_MARKET_IDS_KEY, label, json.dumps(ids))
        pipe.expire(SERVED_MARKET_IDS_KEY, SERVED_MARKET_IDS_TTL_S)
        pipe.execute()
    except Exception:
        logger.debug("served-market-ids write failed for %s", label, exc_info=True)


def served_market_ids() -> list[int]:
    """Every futures market id any warmed page-one shape last rendered.

    Sorted, so the sweep's selection is deterministic across runs and two
    identical Redis states cannot produce two different orderings.

    Empty on any failure — and the caller REPORTS the count rather than treating
    empty as "nothing to do", because "no shape has warmed" and "page one holds
    no futures cards" are opposite states that arrive as the same value.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        raw = rc.hgetall(SERVED_MARKET_IDS_KEY) or {}
    except Exception:
        logger.debug("served-market-ids read failed", exc_info=True)
        return []

    ids: set[int] = set()
    for value in raw.values():
        if isinstance(value, (bytes, bytearray)):
            value = value.decode()
        try:
            parsed = json.loads(value)
        except Exception:
            continue
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            if isinstance(item, bool) or not isinstance(item, int):
                continue
            if item > 0:
                ids.add(item)
    return sorted(ids)
