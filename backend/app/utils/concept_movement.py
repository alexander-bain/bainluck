"""#12091 (Decide 32-A): movement orders the concept cards in Discover's opening.

The opening's grouped concept cards — the theme bundles (AI, Awards Season,
Middle East, Fed & Rates, IPOs, …) — outrank nearly everything and their order
never changes, so the top of Discover is the same on every visit (Alex, Nov 5:
"basically always the same grouped cards"). With the switch on, the theme
bundles trade seats by movement: the bundle whose printed legs moved most since
the previous day takes the earliest bundle seat; a bundle that did not move
yields its seat to one that did and stays on the page, lower.

A PERMUTATION OF THE BUNDLE SEATS, nothing more: the same cards, and every seat
that held a bundle still holds one, so no single-event card is promoted into the
opening (Alex's constraint on 32-A). Nothing is dropped, rescored or edited, and
every later stage — collections, round-ups, the opening seating (#5105 as
amended by 23-A), the edition pin — runs exactly as before. Seating partitions
without reordering, so the bundles' relative order survives it.

WHAT "MOVED" MEANS. Per printed leg (a futures member's ``top_outcomes``): the
latest stored reading minus the reading in force 24 hours ago from the SAME
venue — the latest ``futures_odds_snapshots`` row captured at or before
``now - 24h`` for that bookmaker (rows are deduplicated, so that row is the
price in force then). Raw to raw on one venue, never a blend against a book
(#1844). It is a RANKING signal and is never printed: the card's movement badge
keeps its own dated rule (#4079). A concept's movement is its biggest leg move;
under :data:`MIN_CONCEPT_MOVE` (the card floor, 2 points) it has not moved.

Why not the card's ``movement`` field: on the live deck of Nov 5 it was set on
4 of 80 futures cards and on none of the 25 bundle members, because the dated
bank (``dated_movement_basis``) covered 1 of the 25 — ordering on it would never
move anything.

SETTLED MARKETS DO NOT MOVE. A settled market's last reading jumps to 0 or 100,
which is settlement, not movement, so its legs are skipped: a resolved status,
or any leg already graded (``is_winner`` set) — Kalshi's settled markets stay
``status='open'`` in our table (gotcha #33), so the status alone is not enough.

COST. One Redis read per build. The SQL — two index seeks per leg on
``(outcome_id, captured_at)`` and ``(outcome_id, bookmaker, captured_at DESC)`` —
measured 229 ms for all 419 legs of the 25 bundle members on production (Nov 5);
the printed legs are fewer. One answer serves every dyno for
:data:`CACHE_TTL_S` (refreshed sooner when the cached legs stop covering the
deck's), and one builder at a time refreshes it (a Redis ``SET NX`` lock); a
builder that misses the lock uses the stale answer or the current order.

THE READ NEVER TOUCHES THE REQUEST'S SESSION. It runs on its own short-lived
session with a database statement timeout, as a task the stage stops waiting
for at :data:`READ_BUDGET_S` — it is never awaited after that, so a slow
cancel or close cannot hold the build (a cancelled asyncpg query leaves its
connection waiting for the query to land; #10530). Every failure keeps the
cached or current order.

Dark: with ``DISCOVER_CONCEPT_MOVEMENT`` off the stage is never entered.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CONCEPT_MOVEMENT_ENV = "DISCOVER_CONCEPT_MOVEMENT"
#: The card floor (``futures_highlights.MODERATE_MOVEMENT_THRESHOLD``): a smaller
#: move is not one a card would draw, so it does not earn a seat either.
MIN_CONCEPT_MOVE = 0.02
#: Legs read per build at most (the theme bundles hold ~30 members × 3 legs).
MAX_LEGS = 600
CACHE_KEY = "discover:concept_moves:v1"
#: How long one SQL answer serves every dyno's builds.
CACHE_TTL_S = 600
#: A stale answer still beats none while a refresh fails; past this, none.
CACHE_KEEP_S = 3600
#: Below this share of the deck's legs covered, the cached answer is refreshed.
MIN_COVERAGE = 0.9
READ_BUDGET_S = 1.0
#: The database's own bound on the read, past the stage's budget.
STATEMENT_TIMEOUT_MS = 3000
LOCK_KEY = "discover:concept_moves:refresh_lock"
LOCK_TTL_S = 30

MOVE_SQL = """
SELECT o.id AS outcome_id, cur.probability - old.probability AS move
FROM futures_outcomes o
JOIN futures_markets m ON m.id = o.market_id
JOIN LATERAL (
  SELECT s.bookmaker, s.probability FROM futures_odds_snapshots s
  WHERE s.outcome_id = o.id
  ORDER BY s.captured_at DESC LIMIT 1
) cur ON true
JOIN LATERAL (
  SELECT s.probability FROM futures_odds_snapshots s
  WHERE s.outcome_id = o.id AND s.bookmaker = cur.bookmaker
    AND s.captured_at <= CAST(:now AS timestamptz) - INTERVAL '24 hours'
  ORDER BY s.captured_at DESC LIMIT 1
) old ON true
WHERE o.id IN :ids
  AND lower(coalesce(m.status, '')) NOT IN ('resolved', 'closed', 'settled', 'finalized')
  AND NOT EXISTS (
    SELECT 1 FROM futures_outcomes w
    WHERE w.market_id = o.market_id AND w.is_winner IS NOT NULL
  )
"""


def concept_movement_enabled() -> bool:
    return os.environ.get(CONCEPT_MOVEMENT_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def is_concept_bundle(item: Any) -> bool:
    if not isinstance(item, dict) or item.get("type") != "bundle":
        return False
    data = item.get("data")
    return isinstance(data, dict) and data.get("kind") == "theme"


def _int_id(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def concept_leg_ids(bundle: dict) -> list[int]:
    """The printed legs of a theme bundle's futures members."""
    out: list[int] = []
    for member in (bundle.get("data") or {}).get("items") or ():
        if not isinstance(member, dict) or member.get("type") != "futures":
            continue
        for leg in (member.get("data") or {}).get("top_outcomes") or ():
            oid = _int_id(leg.get("id")) if isinstance(leg, dict) else None
            if oid is not None:
                out.append(oid)
    return out


def wanted_leg_ids(items: list) -> list[int]:
    seen: dict[int, None] = {}
    for item in items:
        if is_concept_bundle(item):
            for oid in concept_leg_ids(item):
                seen.setdefault(oid, None)
    return sorted(seen)[:MAX_LEGS]


def concept_move(bundle: dict, moves: dict[int, float]) -> Optional[float]:
    """The bundle's biggest leg move (absolute), or ``None`` with no reading."""
    found = [abs(moves[oid]) for oid in concept_leg_ids(bundle) if oid in moves]
    return max(found) if found else None


def order_concepts_by_movement(items: list, moves: dict[int, float]) -> list:
    """Re-seat the theme bundles by movement; returns ``items`` itself when
    nothing moves seat.

    Moved bundles (≥ :data:`MIN_CONCEPT_MOVE`) first, biggest move first; then
    the unmoved, in their current order. They fill the seats bundles already
    held, so the deck's shape is unchanged. Ties keep the current order.
    """
    seats = [i for i, item in enumerate(items) if is_concept_bundle(item)]
    if len(seats) < 2:
        return items

    def rank(pair: tuple[int, dict]) -> tuple:
        position, bundle = pair
        move = concept_move(bundle, moves)
        if move is not None and move >= MIN_CONCEPT_MOVE:
            return (0, -move, position)
        return (1, 0.0, position)

    bundles = [items[i] for i in seats]
    ordered = [b for _, b in sorted(enumerate(bundles), key=rank)]
    if all(a is b for a, b in zip(ordered, bundles)):
        return items
    out = list(items)
    for seat, bundle in zip(seats, ordered):
        out[seat] = bundle
    return out


def _parse_cache(raw: Any) -> Optional[dict]:
    if isinstance(raw, bytes):
        raw = raw.decode()
    if not raw:
        return None
    try:
        doc = json.loads(raw)
        at = float(doc["at"])
        moves = {int(k): float(v) for k, v in (doc.get("moves") or {}).items()}
        legs = {int(k) for k in doc.get("legs") or ()}
    except (TypeError, ValueError, KeyError, AttributeError):
        return None
    return {"at": at, "moves": moves, "legs": legs}


def cache_serves(cached: Optional[dict], wanted: list[int], now_s: float) -> bool:
    """A fresh answer that read (nearly) every leg the deck now prints."""
    if not cached or not wanted or now_s - cached["at"] > CACHE_TTL_S:
        return False
    covered = sum(1 for oid in wanted if oid in cached["legs"])
    return covered / len(wanted) >= MIN_COVERAGE


async def read_leg_moves(db: Any, leg_ids: list[int], now: datetime) -> dict[int, float]:
    from sqlalchemy import bindparam, text

    await db.execute(text(f"SET LOCAL statement_timeout = {int(STATEMENT_TIMEOUT_MS)}"))
    stmt = text(MOVE_SQL).bindparams(bindparam("ids", expanding=True))
    rows = (await db.execute(stmt, {"ids": list(leg_ids), "now": now})).all()
    return {int(r[0]): float(r[1]) for r in rows if r[1] is not None}


async def _read_on_own_session(session_factory: Any, leg_ids: list[int], now: datetime) -> dict[int, float]:
    async with session_factory() as session:
        return await read_leg_moves(session, leg_ids, now)


def _forget(task: "asyncio.Task") -> None:
    """Let an abandoned read finish (or fail) on its own, quietly."""

    def _done(t: "asyncio.Task") -> None:
        if not t.cancelled() and t.exception() is not None:
            logger.warning("concept movement: abandoned leg read ended: %s", str(t.exception())[:200])

    task.add_done_callback(_done)
    task.cancel()


async def _bounded_read(session_factory: Any, leg_ids: list[int], now: datetime, budget_s: float):
    """The leg moves, or ``None`` past ``budget_s`` or on any failure. Returns
    within ``budget_s``: a slow read is cancelled and NOT awaited."""
    task = asyncio.ensure_future(_read_on_own_session(session_factory, leg_ids, now))
    done, _ = await asyncio.wait({task}, timeout=max(budget_s, 0.05))
    if task not in done:
        _forget(task)
        logger.warning("concept movement: leg read over its %.2f s budget; keeping the cached or current order", budget_s)
        return None
    if task.exception() is not None:
        logger.warning("concept movement: leg read failed: %s", str(task.exception())[:200])
        return None
    return task.result()


async def _redis_call(redis: Any, factory) -> Any:
    from app.utils.request_cache import bounded_redis_call

    res = await bounded_redis_call(factory)
    return res.value if res.is_ok else None


def _default_session_factory() -> Any:
    from app.services.database import async_session_maker

    return async_session_maker


async def load_leg_moves(
    wanted: list[int],
    *,
    now: datetime,
    redis: Any = None,
    session_factory: Any = None,
    budget_s: float = READ_BUDGET_S,
) -> dict[int, float]:
    """Leg moves for ``wanted``: the shared cached answer while it serves, else
    one bounded read by the builder holding the refresh lock (then cached). A
    failed read, or a missed lock, falls back to a stale answer, then to ``{}``
    — which orders nothing."""
    if redis is None:
        try:
            from app.utils.request_cache import get_shared_async_redis

            redis = await get_shared_async_redis()
        except Exception:  # noqa: BLE001 — no cache is a slower read, not a failure
            redis = None
    cached = None
    if redis is not None:
        cached = _parse_cache(await _redis_call(redis, lambda: redis.get(CACHE_KEY)))
    now_s = now.timestamp()
    if cache_serves(cached, wanted, now_s):
        return cached["moves"]
    stale = cached["moves"] if cached and now_s - cached["at"] <= CACHE_KEEP_S else {}
    if redis is not None:
        locked = await _redis_call(redis, lambda: redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_S))
        if not locked:
            return stale
    moves = await _bounded_read(session_factory or _default_session_factory(), wanted, now, budget_s)
    if moves is None:
        return stale
    if redis is not None:
        blob = json.dumps({"at": now_s, "moves": {str(k): v for k, v in moves.items()}, "legs": wanted})
        await _redis_call(redis, lambda: redis.set(CACHE_KEY, blob, ex=CACHE_KEEP_S))
    return moves


async def apply_concept_movement(
    items: list,
    *,
    now: Optional[datetime] = None,
    redis: Any = None,
    session_factory: Any = None,
    budget_s: float = READ_BUDGET_S,
) -> list:
    """The get_feed stage: ``items`` itself unless a bundle changes seat. It
    takes no request session — the read opens its own."""
    if not concept_movement_enabled():
        return items
    wanted = wanted_leg_ids(items)
    if not wanted:
        return items
    started = time.monotonic()
    moves = await load_leg_moves(
        wanted,
        now=now or datetime.now(timezone.utc),
        redis=redis,
        session_factory=session_factory,
        budget_s=budget_s,
    )
    out = order_concepts_by_movement(items, moves)
    if out is not items:
        logger.info(
            "concept movement: re-seated %d theme bundles from %d legs in %.0f ms",
            sum(1 for i in items if is_concept_bundle(i)),
            len(wanted),
            (time.monotonic() - started) * 1000,
        )
    return out
