"""#10090 — the Polymarket long tail, priced off CLOB token books every 3 minutes.

WHY. Thin and rarely viewed Polymarket markets get ~3 chart points a day
(measured 2026-10-30 19:39Z: 106 thin legs the socket carries, median 3 points
in 24 h, 24 with none; of 82 whose price moved, 15 had a point within 15 min of
the move). The socket writes no chart points at all — only REST writers insert
``futures_odds_snapshots`` — so those charts are as sparse as the hourly rails
that happen to reach them. And ``POLYMARKET_WS_OPEN_SCOPE=slate`` (#11801, "A")
takes these markets off the socket, which would freeze their rows too. This
rotation is what gives them a current price and a chart point whenever the
price moves (at most 4 an hour), and it is the coverage A needs before it can
switch on.

SHIPPED DARK. ``VENUE_POLL_TAIL_ENABLED``:

* unset, ``0``, ``off`` — the task body returns before it touches Redis or the
  database (Celery's broker publish and task-counter signals still run);
* ``shadow`` — reads the slate tail (below) whatever the socket's scope, writes
  nothing, and counts what it would have done, including the agreement counters
  for P4. This is how the rotation is measured while the socket is still ``all``;
* ``1`` / ``on`` / ``true`` — writes what the socket does not carry under the
  scope this process reads (``write``).

THE SETTINGS ARE READ ON THE APP THAT RUNS THIS TASK. The task is on the
``heavy`` queue, so it runs on ``bainluck-heavy`` and reads that app's config:
``VENUE_POLL_TAIL_ENABLED``, the socket scope it follows
(``POLYMARKET_WS_OPEN_SCOPE`` and the open-arm undo flags) and
``VENUE_POLL_30S_ENABLED`` (whose markets it leaves to the 30-second poll). The
socket and the 30-second poll read the main app's. A scope set on one app only
is a mismatch: ``slate`` on the main app with ``all`` here leaves the descoped
markets to nobody, so the two are set together. Every pass reports the scope it
read (``scope``).

WHAT IS PRICED
--------------
Open Polymarket markets (``LIVE_MARKET_SQL``, the poll writer's own liveness)
with a persisted token key that the socket does not carry:

* scope ``all`` (and the socket's open arm on): the socket streams every
  tokened market it can pair, so a ``write`` pass has nothing to price and
  returns without a read (``stopped=socket_carries_all``). A market whose tokens
  the socket cannot pair is unpairable here too: the pairing is the socket's;
* scope ``slate``, or the open arm off: every tokened market whose OWN event is
  not in the game socket's window (``polymarket_ws._slate_event_window``, minus
  the hand-off band, rendered from the shipped predicate exactly as the
  30-second poll renders it). An unlinked market has no event and is always in.
  Slate also keeps a window market's dependencies (an event-less binary behind a
  live board, a held page) streaming; those are priced here AND streamed, and
  the ``fetched_at`` guard below makes that overlap safe — overlap, never a gap.

Minus what the 30-second poll takes: when ``VENUE_POLL_30S_ENABLED`` runs its
Polymarket venue, every market in its shown pool (``venue_poll_30s._pool_sql``)
is left to it. That assumes the 30-second poll takes the shown tokened markets
slate drops (live's follow-up to #11801, ``3dcd1ae0``), so the two ship
together.

The population is read at most every ``POPULATION_TTL_S`` per worker process,
in pieces. Measured on production 2026-10-30, EXPLAIN plus timed reads:

* the candidate ids (~46,900 markets, or ~19,200 with the shown pool left out):
  0.7 s warm, but 16.6 s once with its heap pages cold (19,800 blocks read);
  2.3 s with the pool. A re-read that fails keeps the last population;
* a 2,000-id metadata chunk: 0.8-1.4 s, mostly reading cold pages;
* a 1,000-market leg chunk: 0.06 s warm, 1.9 s cold.

One statement for the whole population measured 10.7 s cold / 6.3 s warm —
36,000 index probes for ``LIVE_MARKET_SQL``'s single-winner clause — so the
metadata and legs are read in ``OUTCOME_READ_MARKETS`` chunks, as the socket
reads its legs.

TOKENS: PERSISTED, PAIRED BY THE SOCKET'S OWN RULE
--------------------------------------------------
Never a Gamma read. The market's ``clob_token_ids`` / ``clobTokenIds`` /
``clob_yes_token_by_outcome`` go through
``polymarket_open_contracts.open_contract_asset_map`` — the socket's pairing,
verbatim: positional only when the token count equals the leg count, else per
outcome, else counted unpaired. A leg is priced when that pairing admits it
(owner or mirror, never graded) and token 0 of its condition
(``contract_key``) is known; its book is read once per condition, as the
30-second poll reads it.

PRICING: #11793's socket book rule, unchanged
---------------------------------------------
``venue_poll_pm_clob.socket_book_price`` on token 0's top of book (both sides
quoted, not crossed, not ``_poly_book_is_untradeable``, midpoint in (0, 1)),
and ``clob_item`` for the item, with the ``_no`` / ``_side1`` leg as its
complement. The write is ``venue_poll_30s._write_group`` → ``write_market`` →
``futures_price_refresh._write_prices`` with a ``PollWrite``, so the tail
inherits every guard the 30-second poll ships with:

* write-on-change — a leg whose price and book equal the row is not written;
* the newer-writer guard — the UPDATE requires ``last_updated`` and
  ``price_changed_at`` older than ``fetched_at`` (the database clock just
  before the book read was sent), so a socket write that landed after the read
  wins and the tail writes no point for that leg (``legs_newer_writer``);
* ``FOR NO KEY UPDATE SKIP LOCKED`` — a row another transaction holds is
  counted (``legs_held``) and left to the next pass, never waited on.

D1. A REFUSED BOOK IS COUNTED, NEVER REPLACED. A token-0 book the rule refuses
is ``tail_book_refused`` (with ``tail_book_refused_<reason>``), and the row is
left as it is. There is no per-sweep Gamma reading of the tail: that matches
what the socket gives such a leg today, no price from the book. One known
difference: the socket withdraws on an untradeable book (#1578/#9934); this
rotation does not.

D2. THE HISTORY BOUND is ``HISTORY_MIN_INTERVAL_S`` (900 s) with a big move of
``HISTORY_BIG_MOVE`` (0.03): a chart point when the price differs from the
outcome's last point and 15 min have passed since it, or the move is at least
3 points. A move inside the interval moves the row now and gains its point on
the first pass after the interval (the shared ``DeferredPoints`` set).

P4. THE AGREEMENT COUNTERS. For a leg whose row was written within
``REFERENCE_FRESH_S`` (60 s) of the book read — on this population, almost
always by the socket — ``tail_agree`` when ``|sweep - row| <= AGREE_TOLERANCE``
(0.01), else ``tail_disagree``; a leg with no fresh write is
``tail_unreferenced``. Counted in both modes, before any write.

COST AND ROTATION
-----------------
``POST /prices`` takes 250 tokens a read (a BUY and a SELL item each). ~36,000
tokens are ~144 reads, ~72,000 ~288, inside ``REQUESTS_PER_PASS``; at
``CONCURRENCY`` reads in flight and 0.29 s a read, about 5-10 s. Every 180 s
that is 0.8-1.6 reads/s against the CLOB's published 500 per 10 s. The rotation
has its own cursor (``polymarket_tail``): a population larger than one pass's
budget is covered in order and wraps, and the stats say how far a pass got
(``covered_share``). The cursor rules are the 30-second poll's: a 429 keeps its
place and backs off THIS rotation (``polymarket_tail_clob``); a group that failed
with its full wall, or the pass's first group, is passed and counted
(``tail_groups_failed``); a later group the pass clock clipped keeps its place.
The rotation also stands down while the 30-second poll's CLOB back-off
(``polymarket_clob``) is running, so it never adds load to a throttled CLOB, but
its own 429 never backs that poll off.

Its own task (``poll_venue_prices_tail``, every 180 s, own ``single_flight``
lease), on the ``heavy`` queue: the 30-second task is single-flight on
``realtime`` with a 24 s pass, and a tail pass inside it would steal shown
passes and put tail work on the live queue. Nothing in ``venue_poll_30s`` calls
this module.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from app.tasks.venue_poll_30s import (
    _BOOK_EPS,
    _MIN_REQUEST_S,
    _PM_TOKEN_KEYS_SQL,
    _PROB_EPS,
    REQUEST_TIMEOUT_S,
    Unit,
    _env_float,
    _env_int,
    _pool_sql,
    _render,
    _same,
    _socket_game_sql,
    _write_group,
    backoff_remaining,
    clear_backoff,
    db_clock,
    enabled_venues,
    is_rate_limited,
    pack_requests,
    population_binds,
    read_cursor,
    rotate,
    shown_market_ids,
    start_backoff,
    write_cursor,
)
from app.tasks.venue_poll_pm_clob import (
    CLOB_BACKOFF_VENUE,
    CLOB_TOKENS_PER_REQUEST,
    _OutOfTime,
    clob_item,
    socket_book_price,
)

logger = logging.getLogger(__name__)

ENABLED_ENV = "VENUE_POLL_TAIL_ENABLED"
MODE_OFF, MODE_SHADOW, MODE_WRITE = "off", "shadow", "write"

#: The beat's period, and the wall a pass may use inside it.
CADENCE_S = 180
PASS_BUDGET_S = _env_float("VENUE_POLL_TAIL_BUDGET_S", 150.0)
#: ~72,000 tokens are ~288 reads; a population past the budget rotates.
REQUESTS_PER_PASS = _env_int("VENUE_POLL_TAIL_REQUESTS", 400)
CONCURRENCY = max(1, _env_int("VENUE_POLL_TAIL_CONCURRENCY", 8))
#: Longer than the 30-second poll's 300 s: the tail's membership moves slowly,
#: and a re-read is several statements.
POPULATION_TTL_S = 900.0
#: Above the task's hard time limit, so a running pass is never overlapped and
#: a killed one frees the lease by TTL.
LEASE_TTL_S = 240

#: D2 (speed, 2026-10-30): at most 4 points an hour per moving leg.
HISTORY_MIN_INTERVAL_S = _env_float("VENUE_POLL_TAIL_HISTORY_MIN_INTERVAL_S", 900.0)
HISTORY_BIG_MOVE = _env_float("VENUE_POLL_TAIL_HISTORY_BIG_MOVE", 0.03)

#: P4: a row written this recently is the reference the sweep is graded against.
REFERENCE_FRESH_S = 60
AGREE_TOLERANCE = 0.01

CURSOR = "polymarket_tail"
#: This rotation's own 429 back-off. It also stands down on the 30-second
#: poll's (``CLOB_BACKOFF_VENUE``), but never sets it.
BACKOFF_VENUE = "polymarket_tail_clob"


def tail_mode(environ=None) -> str:
    """``off`` unless ``VENUE_POLL_TAIL_ENABLED`` says ``shadow`` or on."""
    raw = (environ if environ is not None else os.environ).get(ENABLED_ENV, "")
    raw = raw.strip().lower()
    if raw == MODE_SHADOW:
        return MODE_SHADOW
    if raw in ("1", "on", "true", "yes"):
        return MODE_WRITE
    return MODE_OFF


def socket_open_scope() -> str:
    """What the Polymarket socket's open arm streams, as this process reads it.

    ``off`` (the arm's undo flags), ``all`` or ``slate``. ``open_contract_scope``
    arrives with #11801; before it the arm streams every pairable market, which
    is ``all``.
    """
    from app.tasks import polymarket_open_contracts as poc

    if not poc.open_contract_prices_enabled():
        return "off"
    read = getattr(poc, "open_contract_scope", None)
    return str(read()) if read is not None else "all"


def thirty_second_poll_takes_shown() -> bool:
    """True when the 30-second poll runs its Polymarket venue (this app's env)."""
    return "polymarket" in enabled_venues()


# ── population ────────────────────────────────────────────────────────────────


def candidate_sql(exclude_shown: bool) -> str:
    """Open Polymarket markets whose own event the game socket does not hold.

    Ids only, so no metadata is detoasted here; the token and liveness
    predicates run on the chunks (:func:`markets_stmt`). ``exclude_shown``
    leaves the 30-second poll's shown pool to it.
    """
    from app.tasks.polymarket_ws import _slate_event_window

    window = _render(_slate_event_window())
    pool = f"WITH {_pool_sql('polymarket', window)}" if exclude_shown else ""
    shown = "AND fm.id NOT IN (SELECT id FROM pool)" if exclude_shown else ""
    return f"""
        {pool}
        SELECT fm.id
          FROM futures_markets fm
          LEFT JOIN events e ON e.id = fm.event_id
         WHERE fm.status = 'open'
           AND fm.source = 'polymarket'
           AND NOT {_socket_game_sql(window)}
           {shown}
         ORDER BY fm.id
    """


def markets_stmt(market_ids):
    """``(market_id, clob_token_ids, clobTokenIds, clob_yes_token_by_outcome)``
    of the live, tokened markets among ``market_ids`` — the first four columns
    of the socket's own catalog read, which its pairing takes."""
    from sqlalchemy import Integer, any_, bindparam, select
    from sqlalchemy.dialects.postgresql import ARRAY

    from app.models.models import FuturesMarket
    from app.tasks.polymarket_open_contracts import OUTCOME_TOKEN_METADATA_KEY
    from app.utils.futures_liveness import LIVE_MARKET_SQL

    fm = FuturesMarket.__table__.alias("fm")
    meta = fm.c.market_metadata
    ids = bindparam("market_ids", value=list(market_ids), type_=ARRAY(Integer))
    return (
        select(
            fm.c.id,
            meta["clob_token_ids"],
            meta["clobTokenIds"],
            meta[OUTCOME_TOKEN_METADATA_KEY],
        )
        .where(
            fm.c.id == any_(ids),
            text(LIVE_MARKET_SQL),
            text(_PM_TOKEN_KEYS_SQL.format(key=OUTCOME_TOKEN_METADATA_KEY)),
        )
        .order_by(fm.c.id)
    )


def build_tail(market_rows, legs) -> tuple[list[Unit], dict[str, str], dict]:
    """The socket's pairing over the population → units and condition → token 0.

    ``legs`` is a ``polymarket_open_contracts.OpenContractLegs``. A unit is one
    market and the legs to price: admitted by the pairing (owner or mirror,
    never graded) and naming a condition whose token 0 is known.
    """
    from app.tasks.polymarket_open_contracts import (
        contract_key,
        open_contract_asset_map,
        tokens_by_contract,
    )

    admission = open_contract_asset_map(market_rows, legs)
    by_contract = tokens_by_contract(admission.asset_to_outcome, legs.ext_by_outcome)
    admitted = set(admission.asset_to_outcome.values()) | set(admission.mirrored_outcomes())
    token_of: dict[str, str] = {}
    units: list[Unit] = []
    untokened = 0
    for market_id, market_legs in legs.by_market.items():
        priced = []
        for outcome_id, ext in market_legs:
            if outcome_id not in admitted:
                continue
            key = contract_key(ext)
            token = by_contract.get(f"{key[0]}:0") if key is not None else None
            if token is None:
                untokened += 1
                continue
            token_of[key[0]] = token
            priced.append((outcome_id, ext))
        if priced:
            units.append(Unit(str(market_id), {market_id: priced}))
    units.sort(key=lambda u: int(u.key))
    counts = {
        "markets_unpaired": admission.counts.get("markets_unpaired", 0),
        "markets_without_tokens": admission.counts.get("markets_without_tokens", 0),
        "legs_graded": admission.counts.get("legs_graded", 0),
        "legs_untokened": untokened,
    }
    return units, token_of, counts


_POPULATION: dict[bool, tuple[float, list[Unit], dict[str, str], dict]] = {}


async def load_tail_population(session, *, exclude_shown: bool, now_mono: float):
    """``(units, condition → token 0, pairing counts)``, cached per process."""
    cached = _POPULATION.get(exclude_shown)
    if cached is not None and now_mono - cached[0] < POPULATION_TTL_S:
        return cached[1], cached[2], {**cached[3], "cached": 1}
    started = time.monotonic()
    try:
        units, token_of, counts = await _read_tail_population(session, exclude_shown)
    except Exception as exc:  # noqa: BLE001 — a cold re-read must not stop the rotation
        if cached is None:
            raise
        # The candidate read measured 0.7 s warm and 16.6 s cold on production
        # (2026-10-30, 20 s statement timeout): a re-read that fails keeps the
        # last population, whose membership moves slowly, for another TTL — so
        # a read that timed out cold is not re-run on every 3-minute pass.
        await session.rollback()
        _POPULATION[exclude_shown] = (now_mono, *cached[1:])
        logger.warning("venue_poll_pm_tail: population re-read failed, keeping the last: %s", exc)
        return cached[1], cached[2], {
            **cached[3], "cached": 1, "reread_failed": 1,
            "read_s": round(time.monotonic() - started, 2),
        }
    _POPULATION[exclude_shown] = (now_mono, units, token_of, counts)
    return units, token_of, {**counts, "cached": 0, "read_s": round(time.monotonic() - started, 2)}


async def _read_tail_population(session, exclude_shown: bool):
    from app.tasks.polymarket_open_contracts import (
        OUTCOME_READ_MARKETS,
        OpenContractLegs,
        open_contract_outcome_stmts,
    )

    binds = population_binds(shown_market_ids()) if exclude_shown else {}
    candidates = [
        row[0]
        for row in (await session.execute(text(candidate_sql(exclude_shown)), binds)).fetchall()
    ]
    await session.commit()
    market_rows: list[tuple] = []
    size = max(1, int(OUTCOME_READ_MARKETS))
    for i in range(0, len(candidates), size):
        chunk = candidates[i : i + size]
        market_rows.extend(tuple(r) for r in (await session.execute(markets_stmt(chunk))).fetchall())
        await session.commit()
    legs = OpenContractLegs()
    for stmt in open_contract_outcome_stmts([r[0] for r in market_rows]):
        for outcome_id, market_id, ext, graded in (await session.execute(stmt)).fetchall():
            legs.add(outcome_id, market_id, ext, graded)
        await session.commit()
    units, token_of, counts = build_tail(market_rows, legs)
    counts["candidate_markets"] = len(candidates)
    counts["tokened_markets"] = len(market_rows)
    return units, token_of, counts


# ── pricing and the agreement counters ────────────────────────────────────────

_REFERENCE_SQL = text(
    """
    SELECT fo.id, fo.current_probability, fo.current_yes_bid, fo.current_yes_ask,
           fo.last_updated
      FROM futures_outcomes fo
     WHERE fo.id = ANY(CAST(:ids AS integer[]))
    """
)


def _count(stats: dict, key: str, n: int = 1) -> None:
    stats[key] = stats.get(key, 0) + n


def price_group(group_units, token_of, tops, stats: dict) -> dict[str, list[dict]]:
    """``{unit key: [items]}`` for the conditions whose token-0 book is usable.

    D1: a refused book is counted and gives no item; nothing else reads it.
    """
    from app.tasks.venue_poll_pm_clob import leg_condition

    found: dict[str, list[dict]] = {}
    for unit in group_units:
        items = []
        seen: set[str] = set()
        for legs in unit.legs.values():
            for _oid, ext in legs:
                cond = leg_condition(ext)
                if cond is None or cond in seen:
                    continue
                seen.add(cond)
                top = tops.get(token_of.get(cond))
                if top is None:
                    _count(stats, "tail_tokens_absent")
                    continue
                verdict, prob = socket_book_price(*top)
                if verdict != "price":
                    _count(stats, "tail_book_refused")
                    _count(stats, f"tail_book_refused_{verdict}")
                    continue
                items.append(clob_item(cond, top[0], top[1], prob))
        if items:
            found[unit.key] = items
    return found


def _leg_side(ext: str, item: dict) -> Optional[dict]:
    from app.tasks.venue_poll_30s import _SECOND_LEG

    return item.get("no") if _SECOND_LEG.search(ext) else item


def grade_against_rows(group_units, found, rows, fetched_at: datetime, stats: dict) -> int:
    """The P4 counters for one group, against the rows as read after the book read.

    Returns how many priced legs differ from their row (what a write pass would
    try to write before its guards).
    """
    from app.tasks.venue_poll_30s import _LEG_SUFFIX

    fresh_after = fetched_at - timedelta(seconds=REFERENCE_FRESH_S)
    differ = 0
    for unit in group_units:
        by_condition = {i["external_id"]: i for i in found.get(unit.key, ())}
        for legs in unit.legs.values():
            for oid, ext in legs:
                item = by_condition.get(_LEG_SUFFIX.sub("", ext))
                side = _leg_side(ext, item) if item is not None else None
                row = rows.get(oid)
                if side is None or row is None:
                    continue
                prob, bid, ask, row_last_updated = row
                if not (
                    _same(side["probability"], prob, _PROB_EPS)
                    and _same(side.get("yes_bid"), bid, _BOOK_EPS)
                    and _same(side.get("yes_ask"), ask, _BOOK_EPS)
                ):
                    differ += 1
                if prob is None or row_last_updated is None:
                    _count(stats, "tail_unreferenced")
                    continue
                if row_last_updated.tzinfo is None:
                    row_last_updated = row_last_updated.replace(tzinfo=timezone.utc)
                if row_last_updated < fresh_after:
                    _count(stats, "tail_unreferenced")
                elif abs(float(side["probability"]) - float(prob)) <= AGREE_TOLERANCE + 1e-9:
                    _count(stats, "tail_agree")
                else:
                    _count(stats, "tail_disagree")
    return differ


async def read_reference(session, group_units) -> dict:
    ids = [oid for u in group_units for legs in u.legs.values() for oid, _ext in legs]
    if not ids:
        return {}
    rows = (await session.execute(_REFERENCE_SQL, {"ids": ids})).fetchall()
    await session.commit()
    return {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}


# ── one pass ──────────────────────────────────────────────────────────────────


def _stop_reason(exc: BaseException, stats: dict, *, first: bool) -> str:
    """The 30-second CLOB rotation's classification, backing off THIS rotation."""
    if isinstance(exc, _OutOfTime):
        return "timeout" if first and exc.started else "budget"
    if isinstance(exc, asyncio.TimeoutError):
        return "timeout"
    if is_rate_limited(exc):
        stats["backoff_started_s"] = start_backoff(BACKOFF_VENUE)
        return "rate_limited"
    stats["errors"].append(f"clob: {str(exc)[:200]}")
    return "fetch_error"


async def rotate_tail(
    session, service, units, token_of, *, mode: str, deadline: float, offset: float, stats: dict
) -> None:
    """Read, price, grade and (``write``) write the units after the cursor."""

    def tokens_of(unit: Unit) -> list[str]:
        from app.tasks.venue_poll_pm_clob import leg_condition

        return list(dict.fromkeys(
            token_of[c]
            for legs in unit.legs.values()
            for _oid, ext in legs
            if (c := leg_condition(ext)) in token_of
        ))

    ordered = rotate(units, read_cursor(CURSOR))
    groups = pack_requests(
        ordered, tokens_of, CLOB_TOKENS_PER_REQUEST, REQUESTS_PER_PASS,
        stats, oversize_key="tail_units_oversize",
    )
    gate = asyncio.Semaphore(CONCURRENCY)

    async def read(chunks):
        """One group's reads → (tops, fetched_at); fetched_at is the first send."""
        tops: dict = {}
        fetched_at = None
        for chunk in chunks:
            async with gate:
                left = deadline - time.monotonic()
                if left < _MIN_REQUEST_S:
                    raise _OutOfTime(started=fetched_at is not None)
                sent = datetime.fromtimestamp(time.time() - offset, timezone.utc)
                fetched_at = fetched_at or sent
                wall = min(REQUEST_TIMEOUT_S, left)
                try:
                    tops.update(
                        await asyncio.wait_for(service.get_book_tops(chunk), timeout=wall)
                    )
                except asyncio.TimeoutError:
                    if wall < REQUEST_TIMEOUT_S:
                        raise _OutOfTime(started=True) from None
                    raise
                _count(stats, "requests")
        return tops, fetched_at

    last_key = None
    stop = None
    for start in range(0, len(groups), CONCURRENCY):
        window = groups[start : start + CONCURRENCY]
        if deadline - time.monotonic() < _MIN_REQUEST_S:
            stop = "budget"
            break
        results = await asyncio.gather(*(read(c) for _u, c in window), return_exceptions=True)
        for gi, ((group_units, _chunks), result) in enumerate(zip(window, results), start):
            if isinstance(result, BaseException):
                if stop is None:
                    stop = _stop_reason(result, stats, first=gi == 0)
                    if stop in ("timeout", "fetch_error"):
                        # Passed, so a group that keeps failing costs one read
                        # per rotation and never stops the rotation there.
                        _count(stats, "tail_groups_failed")
                        last_key = group_units[-1].key
                continue
            if stop:
                # Written in order, so the cursor names a contiguous prefix.
                continue
            tops, fetched_at = result
            found = price_group(group_units, token_of, tops, stats)
            rows = await read_reference(session, group_units)
            differ = grade_against_rows(group_units, found, rows, fetched_at, stats)
            if mode == MODE_WRITE:
                await _write_group(
                    session, "polymarket", group_units, found, fetched_at, stats,
                    history=(HISTORY_MIN_INTERVAL_S, HISTORY_BIG_MOVE),
                )
            else:
                _count(stats, "tail_would_write", differ)
            last_key = group_units[-1].key
            _count(stats, "units_done", len(group_units))
        if stop:
            break
    stats["stopped"] = stop or "done"
    write_cursor(CURSOR, last_key)
    if stop != "rate_limited":
        clear_backoff(BACKOFF_VENUE)


async def poll_tail(mode: str) -> dict:
    """One pass. Never raises: a failure is a counted stop."""
    from app.services.polymarket_api import PolymarketAPIService
    from app.tasks.base import get_task_session

    started = time.monotonic()
    deadline = started + PASS_BUDGET_S
    #: `unknown_outcomes` is incremented bare by `_write_prices`.
    stats: dict = {"mode": mode, "errors": [], "unknown_outcomes": 0}
    stats["scope"] = scope = socket_open_scope()
    if mode == MODE_WRITE and scope == "all":
        stats["stopped"] = "socket_carries_all"
        stats["terminal"] = "complete"
        return stats
    for venue in (BACKOFF_VENUE, CLOB_BACKOFF_VENUE):
        remaining = backoff_remaining(venue)
        if remaining > 0:
            stats["backoff_s"] = remaining
            stats["backoff_venue"] = venue
            stats["stopped"] = "backoff"
            stats["terminal"] = "complete"
            return stats

    exclude_shown = thirty_second_poll_takes_shown()
    stats["shown_left_to_30s_poll"] = exclude_shown
    service = PolymarketAPIService()
    try:
        async with get_task_session(
            statement_timeout_ms=20_000, lock_timeout_ms=2_000
        ) as session:
            units, token_of, counts = await load_tail_population(
                session, exclude_shown=exclude_shown, now_mono=time.monotonic()
            )
            stats.update({f"population_{k}": v for k, v in counts.items()})
            stats["population_units"] = len(units)
            stats["population_legs"] = sum(u.leg_count() for u in units)
            stats["population_tokens"] = len(set(token_of.values()))
            if not units:
                stats["stopped"] = "empty"
            else:
                # Local clock read AFTER the database answers: `fetched_at` then
                # errs early by the reply's latency, so the newer-writer guard yields.
                db_now = await db_clock(session)
                offset = time.time() - db_now.timestamp()
                await session.commit()
                await rotate_tail(
                    session, service, units, token_of, mode=mode,
                    deadline=deadline, offset=offset, stats=stats,
                )
            done = stats.get("units_done", 0)
            stats["covered_share"] = round(done / len(units), 4) if units else 0.0
    except Exception as exc:  # noqa: BLE001 — a failed pass is a counted stop
        logger.exception("venue_poll_pm_tail: pass failed")
        stats["errors"].append(f"pass: {str(exc)[:200]}")
        stats["stopped"] = "error"
    finally:
        try:
            await service.close()
        except Exception:  # noqa: BLE001
            pass
    stop = stats.get("stopped")
    if stop == "error":
        stats["terminal"] = "failed"
    elif stop in ("fetch_error", "rate_limited", "timeout") or stats["errors"] or stats.get(
        "tail_units_oversize"
    ):
        stats["terminal"] = "partial"
    else:
        stats["terminal"] = "complete"
    stats["elapsed_s"] = round(time.monotonic() - started, 2)
    return stats
