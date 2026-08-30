"""The tennis concept tier's market population — fetched once, not once per page.

WHY THIS MODULE EXISTS, measured on production `944c466e`, 2026-08-30.

`TennisEventAdapter.build_event` answered "what is the US Open" by loading EVERY
tennis market in a 30-day window, with every one of their outcomes, as ORM
objects — and then used about six percent of them:

    GET /api/event/event:tennis:us-open-men-s-singles-winner
        wall 21,018 ms   db 17,984 ms   app 3,034 ms   q 52   maxq 15,563 ms
    GET /api/event/event:tennis:2026-men-s-us-open-winner-tennis
        wall 30,260 ms -> **H12, the reader got Heroku's error page**

    population        23,101 markets / 50,842 outcomes
    actually used      1,307 children + 1 winner field

The 52 queries are one population scan plus ~46 `selectinload` batches of 500
market ids each. The 15.5s query is the scan, and `EXPLAIN (ANALYZE, BUFFERS)`
says why it cannot be indexed away from here:

    Seq Scan on futures_markets   23,101 rows emitted, 891,784 removed by filter
    126,137 blocks (81,933 read)  8,399 ms, of which 7,275 ms is disk I/O wait

`futures_markets` is 1,664 MB and carries no index that covers the RESOLVED half
of the predicate. `ix_fm_open_category` covers the open half — the open arm alone
measures **568 ms** against the combined 8.4-15.5 s. The resolved half was tried
against the two other plausible indexes and both are worse, not better: routing
it through the `name` trigram (`ILIKE '%winner%' OR ILIKE '%champion%'`) measured
**21,124 ms**, because a common trigram's GIN scan produces 63,325 candidate rows
whose heap fetches cost more than the sequential scan it replaced.

So the resolved arm is a sequential scan of a 1.6 GB table, and the lane holds no
migration slot (nine index requests are parked in
`MIGRATION-SLOT-REQUEST-LATENCY-2026-08-29.md`; gotcha #31 and ruling 080 make a
`CREATE INDEX CONCURRENTLY` on this table an Alex action, not a lane action).

**What is therefore fixed here is not the scan's cost but its FREQUENCY.** The
resolved arm is identical for every tennis key — the same rows answer the US
Open, the women's draw, and every alias slug search emits — and it is the
slowest-changing half of the population, because a row only enters it when a
market resolves. So it is fetched once per `RESOLVED_TTL_SECONDS` and shared,
while the OPEN arm — the live half, where a new match appears and a price moves —
is read fresh on every build off its own index for half a second.

TWO PROPERTIES THAT MAKE THE SHARED HALF SAFE, and they are the design:

* **The cache is a strict SUPERSET, never a substitute for the predicate.** The
  cached query widens the window by `CUTOFF_SLACK_SECONDS`, and the caller's
  exact `resolution_date >= cutoff` is re-applied in Python on every read. A
  stale cache can therefore only ever be MISSING a row that resolved in the last
  few minutes; it can never serve a row that has aged out of the window. The two
  failure directions are not symmetric and only one of them is admitted.
* **No price and no grade is ever read from it.** The cached rows carry market
  identity only (id, name, status, group_id, source, volume, resolution_date).
  Every outcome — every probability, every `is_winner` — is loaded fresh from the
  database in the same request that renders it (`load_outcomes`).

Gotcha #53 applies to the miss: an empty cached population and an absent cache
are different facts, and a fetch that returns nothing is never stored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

#: How long the RESOLVED arm is shared across tennis builds. Five minutes is
#: chosen against the two costs it sits between, not tuned: the scan it avoids is
#: 8.4-15.5 s of a 1.6 GB table, and the freshness it spends is the delay before
#: a just-resolved match reappears on the page as a settled child. The envelope
#: this feeds is itself cached for 60 s and mirrored for 24 h
#: (`event_concept_cache`), so this TTL is not the page's staleness bound — it is
#: strictly inside one that already exists.
RESOLVED_TTL_SECONDS = 300

#: The mirror. Serve-stale for the same reason the envelope tier does it
#: (LAT-P021): a reader arriving one second past the TTL must not pay a 15 s scan
#: that the next background touch would have paid anyway.
RESOLVED_MIRROR_TTL_SECONDS = 86400

#: How much WIDER than the caller's window the cached query reaches. It has to
#: exceed the mirror's life, or a payload served from the mirror could be missing
#: rows the caller's own (narrower, more recent) cutoff still admits — which is
#: the one direction the superset property forbids. One hour of headroom past the
#: 24 h mirror.
CUTOFF_SLACK_SECONDS = RESOLVED_MIRROR_TTL_SECONDS + 3600

#: Cache generation. Bump when `_encode_row` changes shape — a payload from an
#: older generation reads as a miss rather than as a row with shifted columns.
CACHE_GENERATION = "v1"

#: The keys this slot owns, laid out by the policy home rather than re-derived
#: here (ruling 005 — `event_concept_cache.cache_keys` exists because a second
#: tier adopting the policy must not have to re-invent the layout). There is no
#: negative slot: "no tennis markets" is a population, not a 404.
def _slot_keys():
    from app.utils.event_concept_cache import cache_keys

    return cache_keys(CACHE_GENERATION, prefix="bainluck:tennis_pop:resolved:")


SLOT_KEYS = _slot_keys()

#: 🔴 ONE COPY OF THE PAYLOAD, NOT TWO, AND THE REASON IS MEASURED.
#:
#: The envelope tier stores its value twice — a short-TTL primary and a 24 h
#: mirror — and copying that layout here was the first draft. Then the store was
#: measured: Heroku Redis **premium-1, 100 MB maxmemory, policy `allkeys-lru`**,
#: and it is the SAME instance the Celery broker runs on. The encoded population
#: is 3.06 MB, so two copies is **6.1% of the whole store**, evicted against
#: everything else in it — including queue keys.
#:
#: So the two slots are split by ROLE instead of by copy: the payload lives once
#: under a 24 h TTL, and freshness is a separate marker holding no data at all.
#: Marker present -> serve; marker gone, payload present -> serve the payload and
#: refresh behind it. Exactly the same three states as primary/mirror, at half
#: the memory and with one state fewer to go wrong — the two copies can no longer
#: disagree, because there are not two copies.
PAYLOAD_KEY = SLOT_KEYS.stale
FRESH_KEY = SLOT_KEYS.primary

#: The value under `FRESH_KEY`. Never read; only its existence means anything.
FRESH_MARKER = b"1"

#: The statuses the resolved arm admits — the adapter's own list, kept here so the
#: cached query and the caller's re-filter cannot drift apart.
RESOLVED_STATUSES: tuple[str, ...] = ("resolved", "closed", "settled")

#: Refuse a cached payload larger than this rather than decoding it. A runaway
#: population is a bug worth seeing as a miss (and a log line), not one worth
#: spending seconds of JSON decode on inside a page build.
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024


class MarketRow:
    """One market, carrying exactly what the tennis adapter reads off a market.

    Deliberately duck-type-identical to the ORM object it replaces: the adapter's
    helpers (`select_winner_field`, `market_assigned_settled`, the children loop)
    are passed these unchanged and are not aware of the substitution. `outcomes`
    starts EMPTY and is filled only for the markets that reach the page — that is
    the second half of the fix, and it is why this is a class and not a
    NamedTuple.
    """

    __slots__ = (
        "id",
        "name",
        "status",
        "resolution_date",
        "group_id",
        "source",
        "volume_24h",
        "outcomes",
    )

    def __init__(
        self,
        id: int,
        name: str | None,
        status: str | None,
        resolution_date: datetime | None,
        group_id: str | None,
        source: str | None,
        volume_24h: float | None,
    ) -> None:
        self.id = id
        self.name = name
        self.status = status
        self.resolution_date = resolution_date
        self.group_id = group_id
        self.source = source
        self.volume_24h = volume_24h
        self.outcomes: list[OutcomeRow] = []

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"MarketRow(id={self.id!r}, name={self.name!r}, status={self.status!r})"


class OutcomeRow:
    """One outcome, carrying exactly what the tennis adapter reads off an outcome.

    `is_winner` is the graded truth (gotcha #21) and `current_probability` is the
    price; both are loaded in the request that renders them and are never cached
    by this module.
    """

    __slots__ = ("name", "current_probability", "is_winner")

    def __init__(
        self, name: str | None, current_probability: Any, is_winner: Any = False
    ) -> None:
        self.name = name
        self.current_probability = current_probability
        self.is_winner = bool(is_winner)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"OutcomeRow(name={self.name!r}, p={self.current_probability!r})"


# ---------------------------------------------------------------------------
# Encoding. A list of lists, not a list of dicts — 21,378 rows of key names is
# a megabyte of nothing.
# ---------------------------------------------------------------------------


def _encode_row(row: MarketRow) -> list:
    return [
        row.id,
        row.name,
        row.status,
        row.resolution_date.isoformat() if row.resolution_date is not None else None,
        row.group_id,
        row.source,
        float(row.volume_24h) if row.volume_24h is not None else None,
    ]


def _decode_row(raw: Sequence) -> MarketRow | None:
    """One cached row back into a `MarketRow`, or None if it is not one.

    A malformed row is dropped rather than raising: the population is a cache of a
    query, and one bad element must not empty a page (gotcha #42).
    """
    try:
        rid, name, status, resolution, group_id, source, volume = raw
    except (TypeError, ValueError):
        return None
    if not isinstance(rid, int):
        return None
    when: datetime | None = None
    if resolution:
        try:
            when = datetime.fromisoformat(resolution)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    return MarketRow(rid, name, status, when, group_id, source, volume)


def _dumps(payload: Any) -> bytes:
    """orjson when available (gotcha #38 — a big `json.loads` holds the GIL)."""
    try:
        import orjson

        return orjson.dumps(payload)
    except Exception:
        import json

        return json.dumps(payload).encode("utf-8")


def _loads(raw: bytes | str) -> Any:
    try:
        import orjson

        return orjson.loads(raw)
    except Exception:
        import json

        return json.loads(raw)


#: zlib level 1, measured rather than picked: on a 21,378-row payload of the real
#: shape it takes 3.06 MB to 1.13 MB in 14 ms and back in 2.2 ms. Level 6 buys
#: another 3 percentage points for 3x the compress time, which is the wrong trade
#: for a value written by a background refresh and read on a page build. Real
#: market names repeat far more than that fixture's did (the same players appear
#: across hundreds of match markets), so 36.8% is the pessimistic figure.
COMPRESSION_LEVEL = 1

#: Two bytes that say "this value is deflated". A payload without them is read as
#: plain JSON, so a slot written by an older build is still readable rather than
#: being a hard miss on the deploy that changes the encoding.
_ZLIB_MAGIC = b"\x78"


def _pack(payload: Any) -> bytes:
    import zlib

    return zlib.compress(_dumps(payload), COMPRESSION_LEVEL)


def _unpack(raw: bytes | str) -> Any:
    import zlib

    if isinstance(raw, bytes) and raw[:1] == _ZLIB_MAGIC:
        return _loads(zlib.decompress(raw))
    return _loads(raw)


# ---------------------------------------------------------------------------
# The two arms
# ---------------------------------------------------------------------------


def _select_columns():
    from app.models import FuturesMarket

    return (
        FuturesMarket.id,
        FuturesMarket.name,
        FuturesMarket.status,
        FuturesMarket.resolution_date,
        FuturesMarket.group_id,
        FuturesMarket.source,
        FuturesMarket.volume_24h,
    )


def _row_to_market(row: Any) -> MarketRow:
    """One selected row into a `MarketRow`, read BY COLUMN NAME.

    Named access, not positional unpacking, and that is deliberate:
    `event_concept_population` carries the lesson in its own docstring — "a
    projection that disagrees with the row loop it feeds silently mis-assigns
    columns, which is a data bug wearing a latency fix's clothes". A SQLAlchemy
    `Row` exposes every selected column as an attribute, so reading them by name
    makes the projection and the reader impossible to desynchronise.

    Outcomes are CARRIED OVER when the row already has them, and left empty
    otherwise. The production projection never selects them — that is the entire
    point of the two-phase load — but a reader is not the right place to destroy
    data its caller already holds, and a row arriving with its outcomes attached
    must not silently become a market with no prices. Same rule as
    `attach_outcomes`: fill what is missing, never empty what is there.
    """
    market = MarketRow(
        row.id,
        row.name,
        row.status,
        row.resolution_date,
        row.group_id,
        row.source,
        getattr(row, "volume_24h", None),
    )
    carried = getattr(row, "outcomes", None)
    if carried:
        market.outcomes = list(carried)
    return market


def _rows_from(result) -> list[MarketRow]:
    return [_row_to_market(r) for r in result]


async def fetch_open_arm(db) -> list[MarketRow]:
    """Every OPEN tennis market. Read fresh on every build, and cheap because it
    is the half the database can index.

    `ix_fm_open_category` is `btree (llm_sport_category) WHERE status = 'open'`;
    measured on production 2026-08-30 this arm is a bitmap index scan returning
    1,653 rows in **568 ms**, against 8,399 ms for the combined predicate's
    sequential scan. Keeping it out of the cache is what lets a new match and a
    changed status appear immediately.
    """
    from sqlalchemy import select

    from app.models import FuturesMarket

    result = await db.execute(
        select(*_select_columns()).where(
            FuturesMarket.llm_sport_category == "tennis",
            FuturesMarket.status == "open",
        )
    )
    return _rows_from(result.all())


async def fetch_resolved_arm(db, cutoff: datetime) -> list[MarketRow]:
    """Tennis markets resolved since `cutoff`. THE SEQUENTIAL SCAN.

    Called with a cutoff already widened by `CUTOFF_SLACK_SECONDS` when it is
    filling the cache, and with the caller's exact cutoff when it is not.
    """
    from sqlalchemy import select

    from app.models import FuturesMarket

    result = await db.execute(
        select(*_select_columns()).where(
            FuturesMarket.llm_sport_category == "tennis",
            FuturesMarket.status.in_(RESOLVED_STATUSES),
            FuturesMarket.resolution_date.isnot(None),
            FuturesMarket.resolution_date >= cutoff,
        )
    )
    return _rows_from(result.all())


# ---------------------------------------------------------------------------
# The shared resolved arm
# ---------------------------------------------------------------------------


def _get_client():
    """The bounded shared Redis client, or None (gotcha #39). Never raises."""
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _read_cached(rc, key: str) -> list[MarketRow] | None:
    """Decode one cache slot into rows, or None for a miss.

    None and `[]` are different answers and stay different (gotcha #53): an empty
    LIST is a population that was measured and was empty, and it is served as
    such; None is "nothing usable is cached".
    """
    if rc is None:
        return None
    try:
        raw = rc.get(key)
    except Exception:
        logger.warning("tennis population: cache read failed for %s", key)
        return None
    if not raw:
        return None
    if len(raw) > MAX_PAYLOAD_BYTES:
        logger.warning(
            "tennis population: refusing %d-byte payload at %s", len(raw), key
        )
        return None
    try:
        decoded = _unpack(raw)
    except Exception:
        logger.warning("tennis population: undecodable payload at %s", key)
        return None
    if not isinstance(decoded, list):
        logger.warning("tennis population: payload at %s is not a list", key)
        return None
    rows = [r for r in (_decode_row(item) for item in decoded) if r is not None]
    dropped = len(decoded) - len(rows)
    if dropped:
        logger.warning("tennis population: dropped %d malformed cached rows", dropped)
    return rows


def _is_fresh(rc) -> bool:
    """Whether the stored payload is inside its short TTL. Never raises.

    A Redis that cannot answer reads as NOT fresh, which routes the caller into
    serve-stale — the conservative side, since serve-stale still refuses to serve
    without a rebuild behind it.
    """
    if rc is None:
        return False
    try:
        return bool(rc.get(FRESH_KEY))
    except Exception:
        logger.warning("tennis population: freshness read failed")
        return False


def _write_cached(rc, rows: list[MarketRow]) -> None:
    """Store the resolved arm and stamp it fresh. Best-effort; never raises.

    An EMPTY fetch is not stored. "It returned" is not "it worked" (gotcha #53) —
    a zero-row population is either a genuinely empty month of tennis or a broken
    read, and freezing the second one into a 24 h payload is how a page goes
    blank for a day.

    The payload is written BEFORE the marker. Stamping first would open a window
    in which the marker says fresh and the payload is the old one, and a crash
    inside that window leaves it saying so for the whole TTL.
    """
    if rc is None or not rows:
        return
    try:
        rc.setex(PAYLOAD_KEY, RESOLVED_MIRROR_TTL_SECONDS, _pack([_encode_row(r) for r in rows]))
        rc.setex(FRESH_KEY, RESOLVED_TTL_SECONDS, FRESH_MARKER)
    except Exception:
        logger.warning("tennis population: cache write failed", exc_info=True)


def _within(rows: Iterable[MarketRow], cutoff: datetime) -> list[MarketRow]:
    """Re-apply the caller's EXACT window to a superset. This is the property.

    The cached query reaches further back than any caller's cutoff, so this can
    only ever remove rows. A cached population is therefore never able to put a
    market on the page that the live predicate would have excluded.
    """
    return [
        r
        for r in rows
        if r.resolution_date is not None and r.resolution_date >= cutoff
    ]


async def _refresh_shared_arm(widened: datetime) -> None:
    """Re-scan and re-store the shared arm, on its OWN session.

    Never the request's session — `serve_stale_and_refresh`'s docstring names
    that as how a background task ends up writing into a closed one. `widened` is
    the cutoff the reader that kicked this refresh would itself have used, passed
    in rather than re-derived, so the window has exactly one definition
    (`_RESOLVED_WINDOW_DAYS`, in the adapter) and cannot drift into a second.
    """
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        rows = await fetch_resolved_arm(session, widened)
    _write_cached(_get_client(), rows)


async def resolved_arm(db, cutoff: datetime, *, rc: Any = None) -> list[MarketRow]:
    """The resolved arm for `cutoff`, shared across tennis builds.

    Order of attempts, and each one is a deliberate answer to a measured failure:

    1. the stored payload, while the freshness marker is still alive;
    2. the same payload past that marker, with exactly ONE rebuild behind it —
       LAT-P021's lesson applied one layer down. That fix exists because a plain
       TTL expiry, the overwhelmingly common cache event, was walking a reader
       into an 18.5 s rebuild; here it would be an 8.4-15.5 s sequential scan,
       and the reader who arrives one second past the TTL must not pay what the
       refresh is about to pay anyway. Single-flight across the FLEET, not per
       worker: `serve_stale_and_refresh` takes the shared Redis lock;
    3. a live fetch, when there is no payload at all or nothing could run behind
       one — a cold miss must still SERVE, so this stays synchronous;
    4. the stored payload again, if that live fetch raised. A scan that failed
       must not take the page down when a day-old identity list would have
       rendered it.
    """
    from app.utils.event_concept_cache import serve_stale_and_refresh

    rc = _get_client() if rc is None else rc

    stored = _read_cached(rc, PAYLOAD_KEY)
    if stored is not None and _is_fresh(rc):
        return _within(stored, cutoff)

    widened = cutoff - timedelta(seconds=CUTOFF_SLACK_SECONDS)

    if stored is not None and serve_stale_and_refresh(
        SLOT_KEYS, lambda: _refresh_shared_arm(widened), rc=rc
    ):
        return _within(stored, cutoff)

    try:
        fresh = await fetch_resolved_arm(db, widened)
    except Exception:
        if stored is not None:
            logger.warning("tennis population: scan failed — serving what is stored")
            return _within(stored, cutoff)
        raise

    _write_cached(rc, fresh)
    return _within(fresh, cutoff)


async def load_population(
    db, *, now: datetime | None = None, window_days: int, rc: Any = None
) -> list[MarketRow]:
    """The adapter's whole market population: open (fresh) + resolved (shared).

    Returned sorted by id. The query this replaces had no `ORDER BY`, so the
    children rendered in whatever order the sequential scan happened to emit;
    ordering them makes the page's `children` and `market_ids` reproducible
    between two builds of the same data, which is also what makes the cached and
    uncached paths comparable at all.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    open_rows = await fetch_open_arm(db)
    resolved_rows = await resolved_arm(db, cutoff, rc=rc)

    # Deduplicate by id, which is what the ORM query's `.unique()` did. The two
    # arms are disjoint by status in production, but a row that changed status
    # between the two reads — the exact race the arms create — must appear once,
    # not twice, or it renders as two identical children.
    seen: set[int] = set()
    combined: list[MarketRow] = []
    for row in open_rows + resolved_rows:
        if row.id in seen:
            continue
        seen.add(row.id)
        combined.append(row)
    combined.sort(key=lambda r: r.id)
    return combined


# ---------------------------------------------------------------------------
# Outcomes, for the markets that actually reach the page
# ---------------------------------------------------------------------------


def winner_candidate_ids(markets: Iterable[MarketRow], slug: str) -> list[int]:
    """Every market `select_winner_field` can ask a real-outcome count about.

    This is a SUPERSET BY CONSTRUCTION, and the construction is the whole reason
    the two-phase load is safe. `select_winner_field` calls its
    `real_outcome_count` callable in exactly two places, and both sit behind the
    same pair of name-only tests:

        if not is_winner_market(m.name):        continue
        exact  = clean_slug(m.name) == slug
        subset = slug_tokens and slug_tokens <= canonical_tokens(m.name)
        if not (exact or subset):               continue
        if not exact and not is_winner_field(m.name, real_outcome_count(m)):  # <- here
        ...
        def _rank(m): ... real_outcome_count(m) ...   # <- and here, over candidates

    Both tests read the NAME and nothing else, so the set of ids the resolver can
    reach is knowable before a single outcome is loaded. `select_winner_field`
    itself is not touched — it is #1793's identity function and rewriting it to
    fit a latency fix is exactly the trade that issue's docstring forbids.

    `tests/test_tennis_population_lat_p146.py` proves the superset directly, by
    driving the real `select_winner_field` with a callable that records every id
    it is asked about and asserting the recorded set is contained in this one.
    """
    from app.utils.event_tennis import (
        canonical_slug_tokens,
        canonical_tokens,
        is_winner_market,
    )
    from app.utils.name_normalization import clean_slug

    slug_tokens = canonical_slug_tokens(slug)
    ids: list[int] = []
    for m in markets:
        if not is_winner_market(m.name):
            continue
        exact = clean_slug(m.name or "") == slug
        subset = bool(slug_tokens) and slug_tokens <= canonical_tokens(m.name)
        if exact or subset:
            ids.append(m.id)
    return ids


async def load_outcomes(db, market_ids: Iterable[int]) -> dict[int, list[OutcomeRow]]:
    """Outcomes for exactly `market_ids`, in one query, as plain rows.

    This is the other half of the fix. `selectinload` over the whole population
    issued ~46 batched queries for 50,842 outcomes so that the adapter could read
    about 6% of them; the sets that matter are the winner-field candidates and
    the associated children, and both are known from names and group ids before
    a single outcome is needed.

    Plain data, not ORM rows: nothing here may expire under a later commit or
    rollback (gotcha #6).
    """
    ids = sorted({int(i) for i in market_ids if i is not None})
    if not ids:
        return {}

    from sqlalchemy import select

    from app.models import FuturesOutcome

    result = await db.execute(
        select(
            FuturesOutcome.market_id,
            FuturesOutcome.name,
            FuturesOutcome.current_probability,
            FuturesOutcome.is_winner,
        ).where(FuturesOutcome.market_id.in_(ids))
    )

    out: dict[int, list[OutcomeRow]] = {i: [] for i in ids}
    unattributable = 0
    for row in result.all():
        market_id = getattr(row, "market_id", None)
        bucket = out.get(market_id) if market_id is not None else None
        if bucket is None:
            unattributable += 1
            continue
        bucket.append(
            OutcomeRow(
                getattr(row, "name", None),
                getattr(row, "current_probability", None),
                getattr(row, "is_winner", False),
            )
        )
    if unattributable:
        # Loud rather than silent: a row this query returned that cannot be
        # attributed to a market it asked for is a projection bug, and the
        # symptom would otherwise be a page quietly missing prices.
        logger.warning(
            "tennis population: %d outcome rows carried no requested market_id",
            unattributable,
        )
    return out


def attach_outcomes(
    markets: Iterable[MarketRow], loaded: dict[int, list[OutcomeRow]]
) -> None:
    """Hang the loaded outcomes on their markets.

    A market with nothing loaded is left ALONE, never emptied. "Loaded nothing"
    and "was not asked for" are different facts (gotcha #53) and only the caller
    knows which one it meant — clearing on absence is how a two-phase load turns
    a market that was fetched in the other phase into a child with no prices.
    """
    for market in markets:
        rows = loaded.get(market.id)
        if rows:
            market.outcomes = rows
