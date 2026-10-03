"""#10320 — the market ids the category pages actually rendered, so the price net can reach them.

THE DEFECT THIS EXISTS FOR
--------------------------
``/politics``, ``/economics``, ``/entertainment`` and ``/weather`` are built
hourly by ``precompute_category_pages`` and served from its cache. Their cards
are mostly low-volume, ``market_tier = 2`` Kalshi boards, and on 2026-10-03 not
one of the three Kalshi price paths for an EXISTING row reached them:

* ``poll_kalshi_markets`` — scan verdict ``starved`` 24 runs of 24, about 15K
  existing events unreached per beat. #9543's rotation orders only what was
  fetched; a row the cursor does not fetch is not in the rotation at all.
* ``refresh_stale_futures_prices``' value arm — tier 1 only.
* its served arm (#3315) — reads :mod:`app.utils.feed_served_markets`, which
  only Discover and Sports PAGE ONE write.

Measured that morning (open rows, newest leg write per market): /politics 9 of
58 Kalshi cards older than 72h, /entertainment 17 of 71, /economics 10 of 57.
The sharpest one: "Will the U.S. and China announce an AI safety agreement?"
read **25%** on /politics while Kalshi had finalized all four legs YES on
2026-09-26. Polymarket cards on the same pages were fresh, because #3879's
condition refresh covers that venue's long tail.

WHY A SEPARATE KEY AND NOT A LABEL IN THE PAGE-ONE HASH
-------------------------------------------------------
``served_signal()`` turns the page-one hash into a STATE (fresh / empty /
warming up / unavailable), and the sweep refuses a green verdict on the state
that means page one is dark (CERT-1970). A category entry in that hash would
keep the state ``fresh`` while every Discover shape had stopped warming. That
would bring back the false green the state machine was built to stop, with a
new cause. These ids answer a different question ("which cards are the category
pages showing"), so they get their own key and their own reader, and the
page-one signal does not change.

It is also what makes the change safe to land in either order. The producer
runs on the main app and the consumer on ``bainluck-heavy`` (notice 48). Before
the consumer is released, the new key is just ignored.

Same rules as the page-one module otherwise: the producer REPLACES its own
page's list, every entry carries its own write time and the reader drops it past
:data:`CATEGORY_SERVED_MAX_AGE_S`, and nothing here raises into the caller.
"""

from __future__ import annotations

import json
import logging
import time
from typing import NamedTuple

logger = logging.getLogger(__name__)

#: Redis hash: category page (``politics``, ``economics``…) -> JSON
#: ``{"at": <epoch>, "ids": [...]}`` for the payload that page last published.
CATEGORY_SERVED_MARKET_IDS_KEY = "bainluck:precompute:category_pages:served_market_ids"

#: TTL on that hash, refreshed on every write. Sized against the consumer, which
#: runs hourly at :50, like the page-one key: six hours means only a dead producer
#: empties it.
CATEGORY_SERVED_MARKET_IDS_TTL_S = 6 * 3600

#: How old one page's entry may be before the reader ignores it. The producer is
#: hourly (beat ``precompute-category-pages`` at :25), so three hours tolerates two
#: missed runs and no more. It must stay below the TTL, or the key would expire
#: first and this bound could never fire.
CATEGORY_SERVED_MAX_AGE_S = 3 * 3600

#: Per-page cap, so a runaway payload cannot write an unbounded value. The
#: largest page rendered 109 ids on 2026-10-03, so this is headroom. Truncation is
#: logged.
MAX_CATEGORY_SERVED_IDS_PER_PAGE = 500

#: The payload keys that carry a ``futures_markets.id``. ``market_id`` is every
#: card; the cross-source spotlight carries one id per venue; the economics
#: recession headline carries ``main_market_id``. Read by name only:
#: entertainment's ``external_id`` is a venue string and an event's ``id`` is an
#: event id, and passing either to the sweep would select the wrong row or none.
CATEGORY_MARKET_ID_KEYS = (
    "market_id",
    "kalshi_market_id",
    "poly_market_id",
    "main_market_id",
)


class CategoryServed(NamedTuple):
    """What the category pages are showing, and how much of it could be read."""

    ids: list[int]
    pages: int = 0
    stale_pages: int = 0
    unreadable_pages: int = 0
    read_ok: bool = True


def market_ids_in_category_payload(*payloads) -> list[int]:
    """Every futures market id one or more category payloads render, deduped, order kept.

    The category routes nest cards at different depths (themes -> markets,
    cross-source pairs, related markets, the weather sub-endpoints), so this
    walks the whole structure and collects the named keys wherever they sit,
    instead of encoding five layouts that drift on their own.

    Pure and total: anything it does not understand yields nothing. ``bool`` is
    rejected by type because ``True`` would otherwise collect as market 1.
    """
    seen: dict[int, None] = {}

    def _walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in CATEGORY_MARKET_ID_KEYS:
                    if (
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value > 0
                    ):
                        seen.setdefault(value, None)
                elif isinstance(value, (dict, list)):
                    _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    for payload in payloads:
        _walk(payload)
    return list(seen)


def record_category_served_market_ids(rc, page: str, market_ids) -> None:
    """Publish one category page's rendered ids, stamped with the time. Never raises.

    REPLACES the page's list. An empty list is written as an empty list, so a page
    that renders no futures cards says so instead of leaving its last answer up.
    """
    if not rc or not page:
        return
    ids = list(market_ids or [])
    if len(ids) > MAX_CATEGORY_SERVED_IDS_PER_PAGE:
        logger.warning(
            "category-served-market-ids: %s rendered %d markets, capping at %d",
            page,
            len(ids),
            MAX_CATEGORY_SERVED_IDS_PER_PAGE,
        )
        ids = ids[:MAX_CATEGORY_SERVED_IDS_PER_PAGE]
    try:
        pipe = rc.pipeline(transaction=True)
        pipe.hset(
            CATEGORY_SERVED_MARKET_IDS_KEY,
            page,
            json.dumps({"at": int(time.time()), "ids": ids}),
        )
        pipe.expire(CATEGORY_SERVED_MARKET_IDS_KEY, CATEGORY_SERVED_MARKET_IDS_TTL_S)
        pipe.execute()
    except Exception:
        logger.debug(
            "category-served-market-ids write failed for %s", page, exc_info=True
        )


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
    # `at` is REQUIRED: an entry that cannot be aged out would be priority work
    # forever once its page stopped publishing.
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    if not isinstance(raw_ids, list):
        return None
    ids = [
        i for i in raw_ids if not isinstance(i, bool) and isinstance(i, int) and i > 0
    ]
    return float(at), ids


def category_served_market_ids(now: float | None = None) -> CategoryServed:
    """The ids the category pages last published, minus any page past the age bound.

    A failed read returns ``read_ok=False`` with no ids, so the sweep can report
    it rather than show an empty arm as a quiet one (gotcha #53). It never
    raises: a Redis outage costs the sweep this arm, never the run.
    """
    now = time.time() if now is None else now
    try:
        from app.tasks.redis_state import get_redis_client

        rc = get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)
        raw = rc.hgetall(CATEGORY_SERVED_MARKET_IDS_KEY) or {}
    except Exception:
        logger.debug("category-served-market-ids read failed", exc_info=True)
        return CategoryServed(ids=[], read_ok=False)

    ids: set[int] = set()
    pages = stale = unreadable = 0
    for value in raw.values():
        decoded = _decode(value)
        if decoded is None:
            unreadable += 1
            continue
        at, page_ids = decoded
        if now - at > CATEGORY_SERVED_MAX_AGE_S:
            stale += 1
            continue
        pages += 1
        ids.update(page_ids)
    return CategoryServed(
        ids=sorted(ids),
        pages=pages,
        stale_pages=stale,
        unreadable_pages=unreadable,
    )
