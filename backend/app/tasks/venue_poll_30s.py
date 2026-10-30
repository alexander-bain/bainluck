"""#10090 — price every shown Kalshi/Polymarket market the venue sockets do not
carry, every 30 seconds, and write only what moved.

WHY (Alex, Fri 2026-10-30 7:00 AM PT: "Build the 30-second poller for kalshi and
polymarket"). Outside the two sockets a price moved only when one of three REST
writers came round: the 2-minute live poll (live + 3 h games, all of which the
sockets already carry), the hourly Polymarket discovery poll, the 2-hourly
Kalshi one, and the hourly ``futures_price_refresh``. A Discover card or a
game's props more than 6 h before kickoff could therefore be an hour old, and a
futures chart gained one point an hour. Speed's end state is the sockets
carrying only live games; this poll is what has to exist first.

SHIPPED DARK. ``VENUE_POLL_30S_ENABLED`` unset (or ``0``) makes the task body
return before it touches Redis or the database (Celery's own broker publish and
task-counter signals still run each tick). ``1``/``all`` runs both
venues; ``kalshi`` or ``polymarket`` runs one. Speed asks Alex before setting it.

WHAT IS POLLED: shown, minus socket
----------------------------------
*Shown* is the union of:

* an unlinked market in the refresh's high-value class (``HIGH_VALUE_SQL``:
  volume >= 10k, tier 1, or posted liquidity >= 1k), or one Discover page one,
  a category page or a tournament register is serving right now (the same three
  signals ``futures_price_refresh`` reads);
* a market linked to an event that is ``scheduled`` and has not kicked off, up to
  ``GAME_HORIZON_HOURS`` ahead. A linked market further out is not polled here,
  high-value or served or not: it stays on the hourly refresh.

All under ``LIVE_MARKET_SQL`` (open, unresolved, not venue-settled), and only
legs ``_write_prices`` itself would accept (not crowned, not ``api_settlement``).

*Socket* is each socket's own shipped predicate, rendered against this module's
aliases rather than restated (:func:`_render`), so the two cannot drift:

* Kalshi game arm: ``kalshi_ws._kalshi_slate_event_window()``; Kalshi open arm
  (when ``ws_open_contracts.open_contract_prices_enabled()``): the WHERE clause
  of ``kalshi_open_contract_stmt()``, at the leg.
* Polymarket game arm: ``polymarket_ws._slate_event_window()``; open arm (when
  ``polymarket_open_contracts.open_contract_prices_enabled()``): a market with a
  persisted token key. The socket's exact pairing (``open_contract_asset_map``)
  is Python over the whole catalog; a tokened market it cannot pair
  (``markets_unpaired`` on the socket's own counter) is NOT polled here — that
  is the one known gap, and it is the socket's counter that measures it.

HAND-OFF AT KICKOFF, without a gap or a race
--------------------------------------------
The sockets re-read their scope every ``SUBSCRIPTION_REFRESH_SECONDS`` (600 s),
so an event entering the 6 h window is not subscribed the instant the predicate
says so. The poll therefore keeps an event for a band of that interval plus
``HANDOFF_SLACK_S`` inside the window (:func:`_handoff_band_sql`): overlap, never
a gap. Overlap is safe because every poll write carries ``last_updated <
fetched_at`` and ``price_changed_at < fetched_at`` — ``fetched_at`` is the
database clock just before the venue read was sent — so a socket write that
landed after the read always wins (a #9934 withdrawal moves only
``price_changed_at``), and the poll writes no snapshot for a row it did not
update. It never waits on a row a socket holds: the leg UPDATE and the rerank
take ``FOR NO KEY UPDATE SKIP LOCKED``, a held leg is counted ``legs_held`` and
left to the next pass. When a socket arm is turned
off the poll takes its markets at the next population read; the socket keeps
them until its own recycle, which is overlap again.

PRICING: the existing rules, by reuse
-------------------------------------
* Kalshi: one ``GET /markets?tickers=…`` per ``KALSHI_TICKERS_PER_REQUEST``
  tickers, parsed by ``KalshiAPIService.parse_markets`` and priced by the
  2-hour poll's ``_kalshi_yes_probability`` (#3569). The ticker is the YES leg,
  so a threshold leg is its OVER (gotcha 17). An answered leg (``result``) or a
  withdrawn one is refused, never graded here; a leg the venue does not return
  is counted, never cleared (gotcha 53).
* Polymarket: ``futures_price_refresh._fetch_polymarket_prices`` unchanged —
  Gamma events by id, the resolver (gotcha 19), field coherence (#1527), the
  parent-book refusal (#10298), the complementary book for a ``_no`` leg, and a
  closed event as settled. Under ``VENUE_POLL_30S_PM_SOURCE=clob`` the pass
  reads CLOB token prices first under the socket's own book rule
  (:mod:`app.tasks.venue_poll_pm_clob`), and this Gamma rotation prices only
  the legs that read gave no usable book.
* Both write through ``futures_price_refresh._write_prices`` with a
  :class:`PollWrite`: its out-of-range, empty-book (#6676/#9083), unknown-leg and
  settled-leg refusals all hold, plus write-only-if-changed, the newer-writer
  guard and the history bound. ``rank`` is re-derived for a market whose prices
  moved (#6598), as every price writer does.

THE HISTORY BOUND
-----------------
A chart point (``futures_odds_snapshots``, the table and writer every futures
chart reads) is written when the price differs from the outcome's last point
AND either ``HISTORY_MIN_INTERVAL_S`` has passed since it or the move is at
least ``HISTORY_BIG_MOVE``. A move inside the interval updates the row now and
gains its point on the first pass after the interval (:class:`DeferredPoints`),
so the chart's tail never disagrees with the row for longer than the interval.
The decision is taken after the write, on the last points of only the legs that
moved or hold a deferred point: that lateral read measured 3.0 s per 1,000 legs
on production (2026-10-30, cold), the stored-price read 4.5 ms.
Points are only ever written on a change, so ``collapse_snapshots``' equal-run
pass finds nothing extra to delete, and #10955's retention and settlement rules
are untouched.

COST CONTROL
------------
Each venue has a request budget per pass and a rotating cursor
(``bainluck:venue_poll_30s:<venue>:cursor``), so a population larger than one
pass's budget is covered in order and wraps; the stats say how far a pass got.
A pass stops starting requests ``_MIN_REQUEST_S`` before ``PASS_BUDGET_S``. A 429
(gotcha 36: the clients re-raise it) stops that venue for the pass and backs it
off exponentially (``…:backoff``); it never becomes "no price", and the cursor
stays before the group so it is read first once the back-off ends. Any other
failed read (an error, or a timeout on the full ``REQUEST_TIMEOUT_S``) stops the
pass with the cursor PAST the failed group (``groups_failed``), so one group
that keeps failing costs one read per rotation instead of stopping the rotation
there. A timeout the pass's own clock cut short keeps the group's place only
when an earlier group in the same pass used up the time; the pass's FIRST group
had all the time there was, so its timeout counts as a failure and moves on. A
Kalshi market with more legs than a whole pass's budget can read is skipped and
counted (``units_oversize``), never left at the head. The population
is read at most once per ``POPULATION_TTL_S`` for the whole fleet: the read is
published to Redis (``…:<venue>:population``, zlib JSON, kept
``POPULATION_SHARED_TTL_S``) and every worker process takes it while it is
fresh, because worker-realtime replaces a child after about every pass and a
per-process cache re-ran the statement on all 19 passes of the first switch-on.
A population read that fails (its 20 s statement timeout, a lost connection) is
not retried by the next tick: it starts a backoff shared by every worker process
(``…:<venue>_population:backoff``, 30 s doubling to ``BACKOFF_MAX_S``), during
which the newest population this process or the fleet read stands in
(``population_stale``) or, with none, the venue sits the pass out
(``population_backoff``); both read ``partial``. Single-flight in the task wrapper means a slow pass declines
the next tick rather than overlapping it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

ENABLED_ENV = "VENUE_POLL_30S_ENABLED"
VENUES = ("kalshi", "polymarket")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


#: Wall budget of one pass, inside the 30 s beat.
PASS_BUDGET_S = _env_float("VENUE_POLL_30S_BUDGET_S", 24.0)
#: A request is not started with less than this left in the pass.
_MIN_REQUEST_S = 3.0
#: One venue read's own wall.
REQUEST_TIMEOUT_S = 10.0

#: Kalshi publishes a token-bucket read budget: Basic 200 tokens/s at the default
#: 10 tokens per request, i.e. 20 reads/s, with a 3 s burst (docs.kalshi.com
#: "Rate Limits and Tiers", read 2026-10-30). 60 reads per 30 s pass is 2/s, 10%
#: of Basic, spaced so the peak is 10/s.
KALSHI_TICKERS_PER_REQUEST = 100
KALSHI_REQUESTS_PER_PASS = _env_int("VENUE_POLL_30S_KALSHI_REQUESTS", 60)
KALSHI_REQUEST_SPACING_S = 0.1

#: Polymarket publishes Cloudflare throttles: Gamma ``/events`` 500 requests per
#: 10 s (docs.polymarket.com "Rate Limits", read 2026-10-30). 12 per pass is 4 per
#: 10 s, under 1%. The binding cost is bytes, not the limit: 20 nested events
#: measured 1.6 MB (non-game) to 3.3 MB (game) on 2026-10-30.
PM_EVENTS_PER_REQUEST = 20
PM_REQUESTS_PER_PASS = _env_int("VENUE_POLL_30S_PM_REQUESTS", 12)
PM_REQUEST_SPACING_S = 0.2

#: How far before kickoff a linked game market counts as shown.
GAME_HORIZON_HOURS = _env_int("VENUE_POLL_30S_GAME_HORIZON_HOURS", 168)

HISTORY_MIN_INTERVAL_S = _env_float("VENUE_POLL_30S_HISTORY_MIN_INTERVAL_S", 120.0)
HISTORY_BIG_MOVE = _env_float("VENUE_POLL_30S_HISTORY_BIG_MOVE", 0.03)

POPULATION_TTL_S = 300.0
#: How long a population read stays in Redis for every worker process. Fresh is
#: still ``POPULATION_TTL_S``; past that it is only the stand-in a failed read's
#: backoff reuses (``population_stale``).
POPULATION_SHARED_TTL_S = 3600
HANDOFF_SLACK_S = 60
BACKOFF_BASE_S = 30
BACKOFF_MAX_S = 600
LEASE_TTL_S = 60

_KEY_PREFIX = "bainluck:venue_poll_30s"

#: Prices compare at the columns' own precision (probability 6 dp, book 4 dp).
_PROB_EPS = 5e-7
_BOOK_EPS = 5e-5


def enabled_venues(environ=None) -> frozenset[str]:
    """The venues ``VENUE_POLL_30S_ENABLED`` turns on; empty is OFF."""
    raw = (environ if environ is not None else os.environ).get(ENABLED_ENV, "")
    raw = raw.strip().lower()
    if raw in ("", "0", "off", "false", "no"):
        return frozenset()
    if raw in ("1", "on", "true", "yes", "all"):
        return frozenset(VENUES)
    return frozenset(p.strip() for p in raw.split(",") if p.strip() in VENUES)


# ── socket scope, rendered from the sockets' own predicates ───────────────────


def _render(expr) -> str:
    """A shipped Core predicate as SQL over this module's ``fm``/``e``/``fo``."""
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.sql.util import ClauseAdapter

    from app.models.models import Event, FuturesMarket, FuturesOutcome

    adapter = (
        ClauseAdapter(FuturesMarket.__table__.alias("fm"))
        .chain(ClauseAdapter(Event.__table__.alias("e")))
        .chain(ClauseAdapter(FuturesOutcome.__table__.alias("fo")))
    )
    compiled = adapter.traverse(expr).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return f"({compiled})"


_UPCOMING_RE = re.compile(r"e\.commence_time <= NOW\(\) \+ INTERVAL '(\d+) hours'")


def _upcoming_hours(window_sql: str) -> Optional[int]:
    """The socket window's upcoming hours, read off its own rendered SQL."""
    found = _UPCOMING_RE.findall(window_sql)
    return int(found[0]) if len(found) == 1 else None


def _handoff_band_sql(window_sql: str) -> str:
    """Events the window holds that the socket may not have subscribed yet.

    The last ``SUBSCRIPTION_REFRESH_SECONDS + HANDOFF_SLACK_S`` of the upcoming
    window. If the window's hours cannot be read the band is empty — the
    exclusion is then exactly the socket's predicate, and a re-scope can leave a
    gap of up to one refresh, which the stats cannot see; a guard test pins the
    reading so that state is a red test, not a quiet one.
    """
    from app.tasks.kalshi_ws import SUBSCRIPTION_REFRESH_SECONDS

    hours = _upcoming_hours(window_sql)
    if hours is None:
        return "FALSE"
    band_start_s = max(0, hours * 3600 - SUBSCRIPTION_REFRESH_SECONDS - HANDOFF_SLACK_S)
    return (
        "(e.status = 'scheduled' AND e.commence_time > "
        f"NOW() + make_interval(secs => {int(band_start_s)}))"
    )


def _socket_game_sql(window_sql: str) -> str:
    """True when the venue's game socket carries this market (NULL-safe)."""
    return (
        f"COALESCE({window_sql} AND NOT COALESCE({_handoff_band_sql(window_sql)}, FALSE), "
        "FALSE)"
    )


def _pool_sql(venue: str, window_sql: str) -> str:
    """The shown markets of one venue the game socket does not carry.

    Two arms, each planned on its own driving index, because one predicate over
    ``futures_markets`` planned a heap scan of the venue's ~490k rows and ran
    past 10 s on production (2026-10-30):

    * unlinked: the partial index ``ix_fm_feed_open_volume``
      (``status = 'open' AND event_id IS NULL``), then the high-value class or a
      served id;
    * linked: events ``scheduled`` and not yet started, within
      ``GAME_HORIZON_HOURS`` (a range on ``ix_events_commence_time``), minus the
      game socket's window and plus its hand-off band.
    """
    from app.tasks.futures_price_refresh import HIGH_VALUE_SQL

    valued = f"({HIGH_VALUE_SQL} OR fm.id = ANY(CAST(:shown_ids AS integer[])))"
    return f"""
        unlinked AS MATERIALIZED (
            SELECT fm.id
              FROM futures_markets fm
             WHERE fm.status = 'open'
               AND fm.event_id IS NULL
               AND fm.source = '{venue}'
               AND {valued}
        ),
        linked AS MATERIALIZED (
            SELECT fm.id
              FROM events e
              JOIN futures_markets fm ON fm.event_id = e.id
             WHERE e.status = 'scheduled'
               AND e.commence_time > NOW()
               AND fm.status = 'open'
               AND fm.source = '{venue}'
               AND e.commence_time <= NOW() + make_interval(hours => :game_horizon_hours)
               AND NOT {_socket_game_sql(window_sql)}
        ),
        pool AS (
            SELECT id FROM unlinked
            UNION
            SELECT id FROM linked
        )
    """


_ELIGIBLE_LEG_SQL = (
    "fo.is_winner IS NOT TRUE "
    "AND fo.resolution_source IS DISTINCT FROM 'api_settlement'"
)

_PM_TOKEN_KEYS_SQL = (
    "(COALESCE(fm.market_metadata->>'clob_token_ids', '') NOT IN ('', '[]', 'null') "
    "OR COALESCE(fm.market_metadata->>'clobTokenIds', '') NOT IN ('', '[]', 'null') "
    "OR COALESCE(fm.market_metadata->>'{key}', '') NOT IN ('', '{{}}', 'null'))"
)


def kalshi_population_sql(open_arm: bool) -> str:
    from app.tasks.kalshi_ws import _kalshi_slate_event_window
    from app.tasks.ws_open_contracts import kalshi_open_contract_stmt
    from app.utils.futures_liveness import LIVE_MARKET_SQL

    window = _render(_kalshi_slate_event_window())
    open_leg = (
        f"AND NOT COALESCE({_render(kalshi_open_contract_stmt().whereclause)}, FALSE)"
        if open_arm
        else ""
    )
    return f"""
        WITH {_pool_sql("kalshi", window)}
        SELECT fm.id, fo.id, fo.external_id
          FROM pool
          JOIN futures_markets fm ON fm.id = pool.id
          JOIN futures_outcomes fo ON fo.market_id = fm.id
         WHERE {LIVE_MARKET_SQL}
           AND fo.external_id IS NOT NULL
           AND {_ELIGIBLE_LEG_SQL}
           {open_leg}
         ORDER BY fm.id, fo.id
    """


def polymarket_population_sql(open_arm: bool) -> str:
    from app.tasks.polymarket_open_contracts import OUTCOME_TOKEN_METADATA_KEY
    from app.tasks.polymarket_ws import _slate_event_window
    from app.utils.futures_liveness import LIVE_MARKET_SQL
    from app.utils.polymarket_settlement_scan import GAMMA_EVENT_ID_EXPR

    window = _render(_slate_event_window())
    open_market = (
        "AND NOT " + _PM_TOKEN_KEYS_SQL.format(key=OUTCOME_TOKEN_METADATA_KEY)
        if open_arm
        else ""
    )
    return f"""
        WITH {_pool_sql("polymarket", window)}
        SELECT fm.id, {GAMMA_EVENT_ID_EXPR} AS gamma_event_id, fo.id, fo.external_id
          FROM pool
          JOIN futures_markets fm ON fm.id = pool.id
          JOIN futures_outcomes fo ON fo.market_id = fm.id
         WHERE {LIVE_MARKET_SQL}
           {open_market}
           AND fo.external_id IS NOT NULL
           AND {_ELIGIBLE_LEG_SQL}
         ORDER BY fm.id, fo.id
    """


def _kalshi_open_arm() -> bool:
    from app.tasks.ws_open_contracts import open_contract_prices_enabled

    return open_contract_prices_enabled()


def _polymarket_open_arm() -> bool:
    from app.tasks.polymarket_open_contracts import open_contract_prices_enabled

    return open_contract_prices_enabled()


def shown_market_ids() -> list[int]:
    """Markets a page is serving now: Discover page one, category pages, registers.

    Best-effort: each signal that cannot be read contributes nothing, and the
    high-value class still stands.
    """
    ids: set[int] = set()
    try:
        from app.utils.feed_served_markets import served_signal

        ids.update(int(i) for i in served_signal().ids)
    except Exception as exc:  # noqa: BLE001 — a missing signal narrows, never fails
        logger.warning("venue_poll_30s: served signal unreadable: %s", exc)
    try:
        from app.utils.category_served_markets import category_served_market_ids

        ids.update(int(i) for i in category_served_market_ids().ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("venue_poll_30s: category signal unreadable: %s", exc)
    try:
        from app.utils.tournament_register import registered_market_ids

        ids.update(int(i) for i in registered_market_ids())
    except Exception as exc:  # noqa: BLE001
        logger.warning("venue_poll_30s: register signal unreadable: %s", exc)
    return sorted(ids)


# ── population and rotation ───────────────────────────────────────────────────


@dataclass
class Unit:
    """One rotation step: a Kalshi market, or a Polymarket Gamma event."""

    key: str
    #: market_id → [(outcome_id, external_id)]
    legs: dict[int, list[tuple[int, str]]] = field(default_factory=dict)

    def leg_count(self) -> int:
        return sum(len(v) for v in self.legs.values())


def _sort_key(key: str):
    return (0, int(key), "") if key.isdigit() else (1, 0, key)


def build_units(venue: str, rows) -> list[Unit]:
    """Rows from the population SQL → units in rotation order."""
    units: dict[str, Unit] = {}
    for row in rows:
        if venue == "kalshi":
            market_id, outcome_id, ext = row[0], row[1], row[2]
            key = str(market_id)
        else:
            market_id, gamma_id, outcome_id, ext = row[0], row[1], row[2], row[3]
            if not gamma_id:
                continue
            key = str(gamma_id)
        unit = units.setdefault(key, Unit(key))
        unit.legs.setdefault(int(market_id), []).append((int(outcome_id), str(ext)))
    return sorted(units.values(), key=lambda u: _sort_key(u.key))


def rotate(units: list[Unit], cursor: Optional[str]) -> list[Unit]:
    """Units after ``cursor`` first, then from the start (wrap)."""
    if not cursor:
        return list(units)
    at = _sort_key(cursor)
    after = [u for u in units if _sort_key(u.key) > at]
    before = [u for u in units if _sort_key(u.key) <= at]
    return after + before


_POPULATION: dict[str, tuple[float, list[Unit]]] = {}
#: Process-local floor under the shared population backoff: a process does not
#: retry a failed read before this monotonic time even when Redis is unreadable.
_POPULATION_RETRY_AT: dict[str, float] = {}
#: Consecutive failed reads in this process, so the floor doubles like the
#: shared backoff (``start_backoff`` reads a flat 30 s when Redis is down).
_POPULATION_FAILS: dict[str, int] = {}


class PopulationBackoff(Exception):
    """A recent population read failed and this process has no population to reuse."""


def _population_backoff_name(venue: str) -> str:
    return f"{venue}_population"


def _population_tag(sql: str) -> str:
    """Which statement a shared population answers: a copy read under another
    socket scope (open arm, window hours) is never taken for this one."""
    return hashlib.sha1(sql.encode("utf-8")).hexdigest()[:16]


def _population_key(venue: str) -> str:
    return f"{_KEY_PREFIX}:{venue}:population"


def _dumps(payload) -> bytes:
    """orjson when available (gotcha 38: a big ``json.loads`` holds the GIL)."""
    try:
        import orjson

        return orjson.dumps(payload)
    except Exception:  # noqa: BLE001 — the stdlib encodes the same document
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _loads(raw: bytes):
    try:
        import orjson

        return orjson.loads(raw)
    except Exception:  # noqa: BLE001
        return json.loads(raw)


def read_shared_population(venue: str, tag: str) -> Optional[tuple[float, list]]:
    """``(read_at, rows)`` of the fleet's last population read, or ``None``.

    Fails open: an unreadable or malformed copy reads as no copy, and the
    caller reads the database (or, inside a backoff, falls back further).
    """
    try:
        raw = _redis().get(_population_key(venue))
    except Exception as exc:  # noqa: BLE001
        logger.warning("venue_poll_30s: shared population unreadable for %s: %s", venue, exc)
        return None
    if not isinstance(raw, (bytes, bytearray)):
        return None
    try:
        doc = _loads(zlib.decompress(bytes(raw)))
        if doc.get("tag") != tag:
            return None
        return float(doc["read_at"]), list(doc["rows"])
    except Exception:  # noqa: BLE001 — a malformed copy is no copy
        return None


def write_shared_population(venue: str, tag: str, read_at: float, rows) -> None:
    """Publish a population read for every worker process (best-effort)."""
    try:
        doc = {"tag": tag, "read_at": read_at, "rows": [list(r) for r in rows]}
        _redis().set(
            _population_key(venue), zlib.compress(_dumps(doc), 1), ex=POPULATION_SHARED_TTL_S
        )
    except Exception as exc:  # noqa: BLE001 — this process still has its own copy
        logger.warning("venue_poll_30s: shared population unwritable for %s: %s", venue, exc)


async def load_population(
    session, venue: str, *, now_mono: float, stats: Optional[dict] = None
) -> list[Unit]:
    """The venue's population: one read per ``POPULATION_TTL_S`` for the fleet.

    A read is published to Redis, and any worker process takes it while it is
    fresh (``population_shared``, ``population_age_s``). A per-process cache
    alone re-ran the statement on every pass: on 2026-10-30 21:29–21:41Z the
    19 passes ran on 19 different worker-realtime children (``--max-memory-per-
    child`` replaces them), and pg_stat_statements counted 19 reads, mean
    4.2 s, max 19.9 s against the 20 s statement timeout.

    A failed read never makes the next tick re-run the statement: it starts the
    shared population backoff; until it lapses the newest population this
    process or the fleet holds is reused (``population_stale``), or
    :class:`PopulationBackoff` is raised when there is none.
    """
    stats = stats if stats is not None else {}
    cached = _POPULATION.get(venue)
    if cached is not None and now_mono - cached[0] < POPULATION_TTL_S:
        stats["population_cached"] = True
        return cached[1]
    if venue == "kalshi":
        sql = kalshi_population_sql(_kalshi_open_arm())
    else:
        sql = polymarket_population_sql(_polymarket_open_arm())
    tag = _population_tag(sql)
    shared = read_shared_population(venue, tag)
    shared_age = max(0.0, time.time() - shared[0]) if shared is not None else None
    if shared is not None and shared_age < POPULATION_TTL_S:
        units = build_units(venue, shared[1])
        # Expires with the shared copy, never later.
        _POPULATION[venue] = (now_mono - shared_age, units)
        stats["population_shared"] = True
        stats["population_age_s"] = round(shared_age, 1)
        return units
    name = _population_backoff_name(venue)
    wait = max(backoff_remaining(name), _POPULATION_RETRY_AT.get(venue, 0.0) - now_mono)
    if wait > 0:
        stats["population_backoff_s"] = round(wait, 1)
        if cached is not None and (shared is None or now_mono - cached[0] <= shared_age):
            stale = cached[1]
        elif shared is not None:
            stale = build_units(venue, shared[1])
        else:
            raise PopulationBackoff(venue)
        stats["population_stale"] = True
        return stale
    started = time.monotonic()
    read_at = time.time()
    try:
        rows = (
            await session.execute(
                text(sql),
                population_binds(shown_market_ids()),
            )
        ).fetchall()
    except Exception:
        stats["population_read_s"] = round(time.monotonic() - started, 2)
        fails = _POPULATION_FAILS[venue] = _POPULATION_FAILS.get(venue, 0) + 1
        local = min(BACKOFF_BASE_S * 2 ** (fails - 1), BACKOFF_MAX_S)
        seconds = max(start_backoff(name), local)
        _POPULATION_RETRY_AT[venue] = now_mono + seconds
        stats["population_backoff_started_s"] = seconds
        raise  # the pass records it as `stopped: error`; later passes go stale
    stats["population_read_s"] = round(time.monotonic() - started, 2)
    stats["population_cached"] = False
    clear_backoff(name)
    _POPULATION_RETRY_AT.pop(venue, None)
    _POPULATION_FAILS.pop(venue, None)
    write_shared_population(venue, tag, read_at, rows)
    units = build_units(venue, rows)
    _POPULATION[venue] = (now_mono, units)
    return units


def population_binds(shown_ids: list[int]) -> dict:
    """Every bind the population SQL needs. ``HIGH_VALUE_SQL``'s come from
    ``pool_bind_params()`` taken whole (#5781: a site that picks keys out of it
    is how a new arm's bind goes missing in production only)."""
    from app.tasks.futures_price_refresh import pool_bind_params

    return {
        **pool_bind_params(),
        "shown_ids": shown_ids,
        "game_horizon_hours": GAME_HORIZON_HOURS,
    }


def _redis():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)


def read_cursor(venue: str) -> Optional[str]:
    try:
        raw = _redis().get(f"{_KEY_PREFIX}:{venue}:cursor")
    except Exception as exc:  # noqa: BLE001 — fail open: start from the top
        logger.warning("venue_poll_30s: cursor unreadable for %s: %s", venue, exc)
        return None
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else str(raw)


def write_cursor(venue: str, key: Optional[str]) -> None:
    if key is None:
        return
    try:
        _redis().set(f"{_KEY_PREFIX}:{venue}:cursor", key, ex=3600)
    except Exception as exc:  # noqa: BLE001
        logger.warning("venue_poll_30s: cursor not saved for %s: %s", venue, exc)


def backoff_remaining(venue: str) -> float:
    try:
        ttl = _redis().ttl(f"{_KEY_PREFIX}:{venue}:backoff")
    except Exception:  # noqa: BLE001 — unreadable backoff reads as none
        return 0.0
    return float(ttl) if ttl and ttl > 0 else 0.0


def start_backoff(venue: str) -> int:
    """Back the venue off after a 429: 30 s, doubling to ``BACKOFF_MAX_S``."""
    try:
        rc = _redis()
        level = int(rc.incr(f"{_KEY_PREFIX}:{venue}:backoff_level"))
        rc.expire(f"{_KEY_PREFIX}:{venue}:backoff_level", BACKOFF_MAX_S * 2)
        seconds = min(BACKOFF_BASE_S * (2 ** (level - 1)), BACKOFF_MAX_S)
        rc.set(f"{_KEY_PREFIX}:{venue}:backoff", str(level), ex=seconds)
        return seconds
    except Exception as exc:  # noqa: BLE001 — the pass still stops this venue
        logger.warning("venue_poll_30s: backoff not recorded for %s: %s", venue, exc)
        return BACKOFF_BASE_S


def clear_backoff(venue: str) -> None:
    try:
        _redis().delete(f"{_KEY_PREFIX}:{venue}:backoff_level")
    except Exception:  # noqa: BLE001
        pass


def is_rate_limited(exc: BaseException) -> bool:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) == 429


# ── the write ─────────────────────────────────────────────────────────────────


def _same(a, b, eps: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) < eps


class DeferredPoints:
    """Outcomes whose chart point the history bound deferred, shared by passes.

    A Redis set, because the pass that deferred a point and the pass that is due
    to write it can run in different worker processes. Fail-open both ways: an
    unreadable set reads as empty (the deferred point then waits for the leg's
    next move), and an unsaved change is logged, never raised.
    """

    KEY = f"{_KEY_PREFIX}:deferred_points"
    TTL_S = 3600

    def __init__(self, members: frozenset = frozenset()):
        self.members = set(members)
        self.add: set[int] = set()
        self.remove: set[int] = set()

    @classmethod
    def read(cls, outcome_ids) -> "DeferredPoints":
        ids = list(outcome_ids)
        if not ids:
            return cls()
        try:
            flags = _redis().smismember(cls.KEY, ids)
        except Exception as exc:  # noqa: BLE001
            logger.warning("venue_poll_30s: deferred points unreadable: %s", exc)
            return cls()
        return cls(frozenset(i for i, flag in zip(ids, flags) if flag))

    def save(self) -> None:
        add, remove = self.add - self.remove, self.remove - self.add
        if not add and not remove:
            return
        try:
            rc = _redis()
            if add:
                rc.sadd(self.KEY, *add)
            if remove:
                rc.srem(self.KEY, *remove)
            rc.expire(self.KEY, self.TTL_S)
        except Exception as exc:  # noqa: BLE001
            logger.warning("venue_poll_30s: deferred points not saved: %s", exc)
        self.members = (self.members | add) - remove
        self.add, self.remove = set(), set()


@dataclass
class PollWrite:
    """What ``_write_prices`` consults for one market when the poll writes.

    ``stored``: outcome_id → (probability, yes_bid, yes_ask) as the row holds
    them. ``allowed``: the legs this pass polls — a leg outside it (a socket's,
    or one the population did not admit) is never written. ``moved``: the legs
    ``_write_prices`` updated, ``(outcome_id, side)``, for the history bound to
    judge after the write (:func:`write_market`).
    """

    fetched_at: datetime
    now: datetime
    stored: dict[int, tuple]
    allowed: frozenset[int]
    moved: list[tuple[int, dict]] = field(default_factory=list)
    #: outcome_id → (probability, yes_bid, yes_ask) read unchanged.
    unchanged: dict[int, tuple] = field(default_factory=dict)

    def admit(self, outcome_id, prob, bid, ask, stats) -> bool:
        if outcome_id not in self.allowed:
            stats["legs_not_polled"] = stats.get("legs_not_polled", 0) + 1
            return False
        held = self.stored.get(outcome_id)
        if (
            held is not None
            and _same(prob, held[0], _PROB_EPS)
            and _same(bid, held[1], _BOOK_EPS)
            and _same(ask, held[2], _BOOK_EPS)
        ):
            self.unchanged[outcome_id] = (prob, bid, ask)
            stats["legs_unchanged"] = stats.get("legs_unchanged", 0) + 1
            return False
        return True

    def point_due(self, last, prob) -> Optional[str]:
        """The history bound for one leg against its newest chart point.

        ``last`` is ``(captured_at, probability)`` or None. ``first`` (no
        point yet), ``big_move``, ``interval`` → write a point; ``deferred`` →
        moved inside the interval; None → the point already says this price.
        """
        if last is None or last[1] is None:
            return "first"
        moved = abs(float(prob) - float(last[1]))
        if moved < _PROB_EPS:
            return None
        if moved >= HISTORY_BIG_MOVE:
            return "big_move"
        captured_at = last[0]
        if captured_at is not None and captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        if captured_at is None or (self.now - captured_at).total_seconds() >= HISTORY_MIN_INTERVAL_S:
            return "interval"
        return "deferred"


_STORED_SQL = text(
    """
    SELECT fo.id, fo.current_probability, fo.current_yes_bid, fo.current_yes_ask
      FROM futures_outcomes fo
     WHERE fo.id = ANY(CAST(:ids AS integer[]))
    """
)

#: Only for legs that moved or carry a deferred point — never for every polled
#: leg: this lateral read measured 3.0 s per 1,000 legs on production
#: (2026-10-30, cold buffers), the primary-key read above 4.5 ms.
_LAST_POINT_SQL = text(
    """
    SELECT fo.id, s.captured_at, s.probability
      FROM futures_outcomes fo
      JOIN LATERAL (
            SELECT captured_at, probability
              FROM futures_odds_snapshots
             WHERE outcome_id = fo.id
             ORDER BY captured_at DESC
             LIMIT 1
      ) s ON TRUE
     WHERE fo.id = ANY(CAST(:ids AS integer[]))
    """
)


async def load_state(session, outcome_ids: list[int]) -> dict:
    """outcome_id → (probability, yes_bid, yes_ask) as stored."""
    stored: dict[int, tuple] = {}
    if not outcome_ids:
        return stored
    for row in (await session.execute(_STORED_SQL, {"ids": outcome_ids})).fetchall():
        stored[row[0]] = (row[1], row[2], row[3])
    return stored


async def load_last_points(session, outcome_ids) -> dict:
    """outcome_id → (captured_at, probability) of its newest chart point."""
    ids = sorted(set(outcome_ids))
    if not ids:
        return {}
    rows = (await session.execute(_LAST_POINT_SQL, {"ids": ids})).fetchall()
    return {row[0]: (row[1], row[2]) for row in rows}


async def db_clock(session) -> datetime:
    return (await session.execute(text("SELECT clock_timestamp()"))).scalar_one()


async def write_market(
    session,
    *,
    venue: str,
    market_id: int,
    priced: list[dict],
    poll: PollWrite,
    deferred: DeferredPoints,
    stats: dict,
) -> None:
    """One market: changed legs, its rank, then its due chart points; one commit.

    The history bound runs after the write, on the last points of only the legs
    that moved plus the unchanged legs holding a deferred point.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import FuturesOddsSnapshot
    from app.tasks.futures_price_refresh import _write_prices
    from app.utils.futures_rank import rerank_market_field_skip_locked_stmt
    from app.utils.odds_math import probability_to_american

    await _write_prices(session, market_id, venue, priced, stats, poll=poll)
    if poll.moved:
        stats["rows_updated"] = stats.get("rows_updated", 0) + len(poll.moved)
        await session.execute(rerank_market_field_skip_locked_stmt(market_id))
        stats["markets_moved"] = stats.get("markets_moved", 0) + 1
    carrying = [oid for oid in poll.unchanged if oid in deferred.members]
    #: merged into `deferred` only once this market's commit has landed
    defer: set[int] = set()
    undefer: set[int] = set()
    last = await load_last_points(session, [oid for oid, _s in poll.moved] + carrying)

    async def point(outcome_id, side, counter):
        prob = side["probability"]
        await session.execute(
            pg_insert(FuturesOddsSnapshot).values(
                outcome_id=outcome_id,
                bookmaker=venue,
                probability=prob,
                american_odds=probability_to_american(prob),
                yes_bid=side.get("yes_bid"),
                yes_ask=side.get("yes_ask"),
                last_price=side.get("last_price"),
                captured_at=poll.now,
            )
        )
        stats[counter] = stats.get(counter, 0) + 1

    for outcome_id, side in poll.moved:
        due = poll.point_due(last.get(outcome_id), side["probability"])
        if due == "deferred":
            stats["history_deferred"] = stats.get("history_deferred", 0) + 1
            defer.add(outcome_id)
            continue
        undefer.add(outcome_id)
        if due is not None:
            await point(outcome_id, side, "history_points")
    for outcome_id in carrying:
        prob, bid, ask = poll.unchanged[outcome_id]
        due = poll.point_due(last.get(outcome_id), prob)
        if due == "deferred":
            continue
        undefer.add(outcome_id)
        # A leg with no chart history gains its first point when its price
        # next moves, not because a pass read it.
        if due in ("big_move", "interval"):
            await point(
                outcome_id,
                {"probability": prob, "yes_bid": bid, "yes_ask": ask},
                "history_trailing_points",
            )
    await session.commit()
    deferred.add |= defer
    deferred.remove |= undefer


# ── venue reads ───────────────────────────────────────────────────────────────


def kalshi_items(service, raw_markets: list[dict], stats: dict) -> dict[str, dict]:
    """TICKER → priced item, under the 2-hour poll's own Kalshi rules."""
    from app.services.kalshi_api import venue_volume_24h
    from app.tasks.kalshi import _is_withdrawn_leg, _kalshi_yes_probability
    from app.utils.futures_liveness import venue_answered

    volume = {
        str(m.get("ticker") or "").upper(): venue_volume_24h(m)
        for m in raw_markets
        if m.get("ticker")
    }
    items: dict[str, dict] = {}
    for km in service.parse_markets(raw_markets):
        ticker = (km.ticker or "").upper()
        if not ticker:
            continue
        if venue_answered(km.result):
            stats["refused_settled"] = stats.get("refused_settled", 0) + 1
            continue
        if _is_withdrawn_leg(km.status):
            stats["refused_withdrawn"] = stats.get("refused_withdrawn", 0) + 1
            continue
        prob = _kalshi_yes_probability(km.yes_bid, km.yes_ask, km.last_price)
        if prob is None:
            stats["no_price"] = stats.get("no_price", 0) + 1
            continue
        items[ticker] = {
            "probability": prob,
            "yes_bid": km.yes_bid,
            "yes_ask": km.yes_ask,
            "last_price": km.last_price,
            "volume_24h": volume.get(ticker),
        }
    return items


def pack_requests(
    units: list[Unit],
    keys_of,
    per_request: int,
    budget: int,
    stats: Optional[dict] = None,
    oversize_key: str = "units_oversize",
) -> list[tuple[list[Unit], list[list[str]]]]:
    """Pack units into request groups: (units, key chunks), within ``budget``.

    ``keys_of(unit)`` is the list of keys one read names for that unit (Kalshi
    tickers, CLOB tokens). A unit is never split across groups, so its legs are
    written after every one of its reads; a unit with more keys than one
    request is its own group. A unit with no keys is skipped. A unit needing
    more reads than the whole ``budget`` can never be read, so it is skipped and
    counted (``stats[oversize_key]``) rather than stopping the pack — at the
    head of the rotation it would otherwise stop every pass there.
    """
    groups: list[tuple[list[Unit], list[list[str]]]] = []
    used = 0
    current: list[Unit] = []
    keys: list[str] = []

    def flush():
        nonlocal current, keys, used
        if current:
            groups.append((current, [keys]))
            used += 1
        current, keys = [], []

    for unit in units:
        legs = keys_of(unit)
        if not legs:
            continue
        if len(legs) > per_request:
            flush()
            chunks = [legs[i : i + per_request] for i in range(0, len(legs), per_request)]
            if len(chunks) > budget:
                if stats is not None:
                    stats[oversize_key] = stats.get(oversize_key, 0) + 1
                continue
            if used + len(chunks) > budget:
                break
            groups.append(([unit], chunks))
            used += len(chunks)
            continue
        if len(keys) + len(legs) > per_request:
            flush()
        if used >= budget:
            break
        current.append(unit)
        keys.extend(legs)
    if used < budget:
        flush()
    return groups


def kalshi_requests(
    units: list[Unit], budget: int, stats: Optional[dict] = None
) -> list[tuple[list[Unit], list[list[str]]]]:
    """Kalshi request groups: a unit's tickers, ``KALSHI_TICKERS_PER_REQUEST`` a read."""
    return pack_requests(
        units,
        lambda unit: [ext for legs in unit.legs.values() for _oid, ext in legs],
        KALSHI_TICKERS_PER_REQUEST,
        budget,
        stats,
    )


def polymarket_requests(
    units: list[Unit], budget: int, stats: Optional[dict] = None
) -> list[tuple[list[Unit], list[list[str]]]]:
    """Gamma events in reads of ``PM_EVENTS_PER_REQUEST``; one read per group,
    so no unit can exceed the budget (``stats`` is for the shared signature)."""
    groups = []
    for i in range(0, len(units), PM_EVENTS_PER_REQUEST):
        if len(groups) >= budget:
            break
        chunk = units[i : i + PM_EVENTS_PER_REQUEST]
        groups.append((chunk, [[u.key for u in chunk]]))
    return groups


_LEG_SUFFIX = re.compile(r"_(yes|no|side1)$")


def _items_for_market(venue: str, legs: list[tuple[int, str]], found) -> list[dict]:
    """The priced items this market's own legs name, keyed to its external ids."""
    if venue == "kalshi":
        out = []
        for _oid, ext in legs:
            item = found.get(ext.upper())
            if item is not None:
                out.append({**item, "external_id": ext})
        return out
    wanted = {_LEG_SUFFIX.sub("", ext) for _oid, ext in legs}
    return [item for item in found if item.get("external_id") in wanted]


# ── one venue, one pass ───────────────────────────────────────────────────────


async def _fetch_group(venue: str, service, chunks: list[list[str]], stats: dict, timeout: float):
    """One group's venue reads → {unit key: found}, or raises."""
    from app.tasks.futures_price_refresh import VENUE_SETTLED, _fetch_polymarket_prices

    if venue == "kalshi":
        found: dict[str, dict] = {}
        for i, chunk in enumerate(chunks):
            if i:
                await asyncio.sleep(KALSHI_REQUEST_SPACING_S)
            raw, _cursor = await asyncio.wait_for(
                service.get_markets(status=None, tickers=chunk, limit=len(chunk)),
                timeout=timeout,
            )
            stats["requests"] = stats.get("requests", 0) + 1
            stats["absent"] = stats.get("absent", 0) + max(0, len(chunk) - len(raw))
            found.update(kalshi_items(service, raw, stats))
        return found
    (event_ids,) = chunks
    priced, _unpriced = await asyncio.wait_for(
        _fetch_polymarket_prices(service, event_ids, stats=stats), timeout=timeout
    )
    stats["requests"] = stats.get("requests", 0) + 1
    out = {}
    for event_id in event_ids:
        value = priced.get(str(event_id))
        if value is VENUE_SETTLED:
            stats["refused_settled_events"] = stats.get("refused_settled_events", 0) + 1
            continue
        if value is None:
            stats["events_unpriced_or_absent"] = stats.get("events_unpriced_or_absent", 0) + 1
            continue
        out[str(event_id)] = value
    return out


def _new_service(venue: str):
    if venue == "kalshi":
        from app.services.kalshi_api import KalshiAPIService

        return KalshiAPIService()
    from app.services.polymarket_api import PolymarketAPIService

    return PolymarketAPIService()


async def poll_venue(venue: str, *, deadline: float) -> dict:
    """One venue's pass. Never raises: a failure is a counted stop.

    Polymarket under ``VENUE_POLL_30S_PM_SOURCE=clob`` reads CLOB token prices
    first (:mod:`app.tasks.venue_poll_pm_clob`); the Gamma rotation below then
    runs over only the legs that read gave no usable book, on its own cursor.
    """
    from app.tasks.base import get_task_session

    #: `unknown_outcomes` is incremented bare by `_write_prices`.
    stats: dict = {"errors": [], "unknown_outcomes": 0}
    remaining = backoff_remaining(venue)
    if remaining > 0:
        stats["backoff_s"] = remaining
        stats["stopped"] = "backoff"
        return stats

    spacing = KALSHI_REQUEST_SPACING_S if venue == "kalshi" else PM_REQUEST_SPACING_S
    budget = KALSHI_REQUESTS_PER_PASS if venue == "kalshi" else PM_REQUESTS_PER_PASS
    service = _new_service(venue)
    try:
        async with get_task_session(
            statement_timeout_ms=20_000, lock_timeout_ms=2_000
        ) as session:
            try:
                units = await load_population(
                    session, venue, now_mono=time.monotonic(), stats=stats
                )
            except PopulationBackoff:
                stats["stopped"] = "population_backoff"
                return stats
            stats["population_units"] = len(units)
            stats["population_legs"] = sum(u.leg_count() for u in units)
            if not units:
                stats["stopped"] = "empty"
                return stats
            # Local clock read AFTER the database answers: `fetched_at` then
            # errs early by the reply's latency, so the newer-writer guard yields.
            db_now = await db_clock(session)
            offset = time.time() - db_now.timestamp()
            await session.commit()
            cursor_name = venue
            if venue == "polymarket":
                from app.tasks.venue_poll_pm_clob import GAMMA_RESERVE_S, clob_pass, pm_source

                # Which instrument ran is on every pass: the first switch-on set
                # only VENUE_POLL_30S_ENABLED, so the CLOB arm stayed dark and no
                # field said why (2026-10-30, 19 passes with no `clob_*` key).
                stats["pm_source"] = pm_source()
                if stats["pm_source"] == "clob":
                    units = await clob_pass(
                        session, service, units, deadline=deadline - GAMMA_RESERVE_S,
                        offset=offset, stats=stats,
                    )
                    cursor_name = "polymarket_gamma"
                    stats["gamma_fallback_units"] = len(units)
                    if not units:
                        stats.setdefault("stopped", "done")
                        stats["covered_share"] = 1.0
                        return stats
            cursor = read_cursor(cursor_name)
            ordered = rotate(units, cursor)
            pack = kalshi_requests if venue == "kalshi" else polymarket_requests
            groups = pack(ordered, budget, stats)
            last_key = None
            for gi, (group_units, chunks) in enumerate(groups):
                left = deadline - time.monotonic()
                if left < _MIN_REQUEST_S:
                    stats["stopped"] = "budget"
                    break
                if gi:
                    await asyncio.sleep(spacing)
                fetched_at = datetime.fromtimestamp(time.time() - offset, timezone.utc)
                wall = min(REQUEST_TIMEOUT_S, left)
                try:
                    found = await _fetch_group(venue, service, chunks, stats, wall)
                except asyncio.TimeoutError:
                    if wall < REQUEST_TIMEOUT_S and gi > 0:
                        # An earlier group used up the pass's clock: this one
                        # never had its full wall, so it is first next pass.
                        # The FIRST group had all the time the pass could give
                        # it, so it fails and moves on like a full-wall timeout.
                        stats["stopped"] = "budget"
                        break
                    stats["groups_failed"] = stats.get("groups_failed", 0) + 1
                    stats["stopped"] = "timeout"
                    last_key = group_units[-1].key
                    break
                except Exception as exc:  # noqa: BLE001 — classified below
                    if is_rate_limited(exc):
                        # The venue said slow down: no cursor move past it.
                        stats["backoff_started_s"] = start_backoff(venue)
                        stats["stopped"] = "rate_limited"
                    else:
                        stats["errors"].append(f"fetch: {str(exc)[:200]}")
                        stats["groups_failed"] = stats.get("groups_failed", 0) + 1
                        stats["stopped"] = "fetch_error"
                        last_key = group_units[-1].key
                    break
                await _write_group(session, venue, group_units, found, fetched_at, stats)
                last_key = group_units[-1].key
                stats["units_done"] = stats.get("units_done", 0) + len(group_units)
            else:
                stats.setdefault("stopped", "done")
            write_cursor(cursor_name, last_key)
            if stats.get("stopped") != "rate_limited":
                clear_backoff(venue)
            done = stats.get("units_done", 0)
            stats["covered_share"] = round(done / len(units), 4) if units else 0.0
    except Exception as exc:  # noqa: BLE001 — one venue never takes the other down
        logger.exception("venue_poll_30s: %s pass failed", venue)
        stats["errors"].append(f"pass: {str(exc)[:200]}")
        stats["stopped"] = "error"
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass
    return stats


async def _write_group(session, venue, group_units, found, fetched_at, stats) -> None:
    outcome_ids = [
        oid for u in group_units for legs in u.legs.values() for oid, _ext in legs
    ]
    try:
        stored = await load_state(session, outcome_ids)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        stats["errors"].append(f"state: {str(exc)[:200]}")
        return
    deferred = DeferredPoints.read(outcome_ids)
    now = datetime.now(timezone.utc)
    for unit in group_units:
        unit_found = found if venue == "kalshi" else found.get(unit.key)
        if not unit_found:
            continue
        for market_id, legs in unit.legs.items():
            priced = _items_for_market(venue, legs, unit_found)
            if not priced:
                continue
            if venue == "polymarket" and _pm_market_unchanged(legs, priced, stored, deferred):
                # Nothing to write and no deferred point to carry: skip the
                # writer's per-market read and commit (~6,600 markets a pass
                # on the CLOB path, ~0.8% of whose legs move per minute).
                stats["markets_unchanged"] = stats.get("markets_unchanged", 0) + 1
                continue
            poll = PollWrite(
                fetched_at=fetched_at,
                now=now,
                stored=stored,
                allowed=frozenset(oid for oid, _ext in legs),
            )
            try:
                await write_market(
                    session, venue=venue, market_id=market_id, priced=priced,
                    poll=poll, deferred=deferred, stats=stats,
                )
            except Exception as exc:  # noqa: BLE001 — gotcha 42: one market, not the pass
                await session.rollback()
                stats["market_errors"] = stats.get("market_errors", 0) + 1
                stats["errors"].append(f"market {market_id}: {str(exc)[:160]}")
    deferred.save()


_SECOND_LEG = re.compile(r"_(no|side1)$")


def _pm_market_unchanged(legs, priced, stored, deferred: DeferredPoints) -> bool:
    """True when every leg the items price equals its stored row, none deferred.

    The side each leg takes is ``_write_prices``' own convention (``_legs``): a
    bare or ``_yes`` leg the item, a ``_no`` or ``_side1`` leg ``item["no"]``.
    Conservative by construction: any leg it cannot judge as equal (a missing
    row, a missing side, a changed value) sends the market to the writer, which
    decides exactly.
    """
    by_condition = {item.get("external_id"): item for item in priced}
    for oid, ext in legs:
        item = by_condition.get(_LEG_SUFFIX.sub("", ext))
        if item is None:
            continue
        if oid in deferred.members:
            return False
        side = item.get("no") if _SECOND_LEG.search(ext) else item
        held = stored.get(oid)
        if side is None or held is None:
            return False
        if not (
            _same(side.get("probability"), held[0], _PROB_EPS)
            and _same(side.get("yes_bid"), held[1], _BOOK_EPS)
            and _same(side.get("yes_ask"), held[2], _BOOK_EPS)
        ):
            return False
    return True


async def poll_venue_prices(venues) -> dict:
    """Both venues concurrently, each on its own session and budget."""
    started = time.monotonic()
    deadline = started + PASS_BUDGET_S
    names = [v for v in VENUES if v in set(venues)]
    results = await asyncio.gather(*(poll_venue(v, deadline=deadline) for v in names))
    summary: dict = {v: r for v, r in zip(names, results)}
    stops = [r.get("stopped") for r in results]
    if all(s == "error" for s in stops):
        summary["terminal"] = "failed"
    elif (
        any(s in ("error", "fetch_error", "rate_limited", "timeout") for s in stops)
        or any(r.get("errors") for r in results)
        or any(r.get("units_oversize") for r in results)
        # lane1 R3 on #11793: a CLOB rotation stopped by a timeout or a 429
        # leaves the rest of the book to Gamma's ~14-minute rotation, which is
        # the staleness this poll removes; `backoff` stays not-partial, like
        # the venue-level backoff.
        or any(r.get("clob_stopped") in ("timeout", "rate_limited") for r in results)
        # A failed population read: the venue sat out, or ran on its last one.
        or any(
            r.get("stopped") == "population_backoff" or r.get("population_stale")
            for r in results
        )
    ):
        summary["terminal"] = "partial"
    else:
        summary["terminal"] = "complete"
    summary["elapsed_s"] = round(time.monotonic() - started, 2)
    return summary
