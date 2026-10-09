"""Shared slot for the feed's championship-odds map (#10772, parent #1475).

WHAT WAS MEASURED.

Every Discover feed build that scores game events awaits
`routes/feed.py::_get_championship_probabilities` inline, before a single card
is scored. Production `pg_stat_statements`, 2026-10-08 18:58Z:

    SELECT fo.team_id, MAX(fo.current_probability) ... WHERE fm.market_tier = 1
      AND fm.status = 'open' ... GROUP BY fo.team_id
    147,014 calls · mean 1,125 ms · max 25,324 ms · 165,389 s total

— the most expensive read statement on the futures tables. The plan walks
`ix_futures_markets_status` over every open market and filters `market_tier = 1`
because there is no tier index; an index is DDL and attended, so it is not this
module.

The answer is ONE global `{team_id: max championship probability}` map. It does
not depend on the reader, the feed shape or the event. Its cache was a 300 s
dict per process, so every web worker and every prewarm worker paid for the same
map independently. This slot lets the first process to compute it answer for the
rest.

🔴 THE SLOT CARRIES ITS OWN `computed_at`, AND THAT IS THE FRESHNESS BOUND.
A reader that fills its per-process dict from this slot stamps the dict with the
slot's `computed_at`, not with "now". Stamping "now" would stack the two TTLs:
a map 299 s old in Redis would earn another 300 s in-process, and a reader could
be handed a 599 s-old map where today's bound is 300 s. That would be a content
change hidden inside a latency change. With the inherited stamp, no reader ever
sees a map older than `TTL_SECONDS`, whichever level served it. `is_fresh` is
the one place that rule is written.

An EMPTY map is a real answer ("no open tier-1 market has a linked team"), and
the per-process dict has always cached it. It round-trips as an empty list, and
a malformed slot reads as a MISS rather than as empty. Those are different
facts (gotcha #53), and only the real empty may suppress a query.
"""

from __future__ import annotations

import json
import logging
import math
import time

logger = logging.getLogger(__name__)

CACHE_KEY = "bainluck:feed:champ_probs:v1"

#: The feed's own `_CHAMP_PROB_CACHE_TTL`, not a new number. Sharing the map
#: changes who computes it, never how old it may be.
TTL_SECONDS = 300


def _client():
    """The bounded shared client, or None. Never raises (gotcha #39)."""
    try:
        from app.utils.event_concept_cache import get_client

        return get_client()
    except Exception:
        return None


def is_fresh(computed_at: float, now: float | None = None) -> bool:
    """Whether a map computed at `computed_at` may still be served."""
    now = time.time() if now is None else now
    return 0 <= now - computed_at < TTL_SECONDS


def encode(probs: dict[int, float], computed_at: float) -> str:
    """The stored form. Pairs, because JSON object keys are always strings."""
    return json.dumps(
        {
            "computed_at": computed_at,
            "probs": [[int(k), float(v)] for k, v in probs.items()],
        }
    )


def decode(raw) -> tuple[dict[int, float], float] | None:
    """Turn a stored slot back into `(probs, computed_at)`, or None on any doubt.

    Pure, so it can be tested without a Redis. Anything that is not exactly the
    shape `encode` writes is a MISS.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return None
    if not isinstance(raw, str):
        return None
    try:
        value = json.loads(raw)
    except Exception:
        return None
    if not isinstance(value, dict):
        return None
    computed_at = value.get("computed_at")
    pairs = value.get("probs")
    if isinstance(computed_at, bool) or not isinstance(computed_at, (int, float)):
        return None
    if not math.isfinite(computed_at) or not isinstance(pairs, list):
        return None
    probs: dict[int, float] = {}
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            return None
        team_id, prob = pair
        # `True` is an int in Python and would silently become team 1.
        if isinstance(team_id, bool) or not isinstance(team_id, int):
            return None
        if isinstance(prob, bool) or not isinstance(prob, (int, float)):
            return None
        probs[team_id] = float(prob)
    return probs, float(computed_at)


def read(rc=None, now: float | None = None) -> tuple[dict[int, float], float] | None:
    """The shared map and its `computed_at`, or None on a miss or a stale slot.

    Never raises: a cache that cannot be read must cost a query, not a 500.
    """
    client = rc if rc is not None else _client()
    if client is None:
        return None
    try:
        raw = client.get(CACHE_KEY)
    except Exception:
        logger.warning("championship-probs cache: read failed — reader will query")
        return None
    decoded = decode(raw)
    if decoded is None or not is_fresh(decoded[1], now):
        return None
    return decoded


def write(probs: dict[int, float], computed_at: float, rc=None) -> bool:
    """Publish a map. Returns whether the write was ATTEMPTED, not whether it landed."""
    client = rc if rc is not None else _client()
    if client is None:
        return False
    try:
        client.setex(CACHE_KEY, TTL_SECONDS, encode(probs, computed_at))
    except Exception:
        logger.warning("championship-probs cache: write failed")
        return False
    return True
