"""#10090 — the hottest Polymarket props stay live while the rest take the 30-second poll.

WHY (Alex, 2026-11-01 ~9:20 AM PT): "instead of doing a blanket 30 seconds for
all props, should we do 30 seconds for almost all props, but live for the props
with the highest very recent trading volume, to the extent that we can do that
without burdening the cpu?" Under ``PM_WS_PROPS_TO_POLL`` every venue-labelled
prop of the socket's games is priced by the poll every ~30 s. The poll sees each
of them every pass, so it knows which are moving now.

HEAT. After each Polymarket pass the poll records the props it saw MOVE (sent to
the writer) in a one-minute Redis bucket; a market's heat is the number of
passes it moved in over the last ``HOT_WINDOW_MIN`` minutes. CLOB tops carry no
traded size, so price movement is the recent-activity signal the poll has. Only
markets the props arm owns are recorded (open, on an event the socket's window
holds, venue-refused as a winner): heat never widens the socket past its games.

LIVE. The open arm (``polymarket_ws``) adds the top ``HOT_MAX`` markets with at
least ``HOT_MIN_MOVES`` to its seeds, exactly as a market a reader holds: at
each catalog refresh, and through the presence check, which can bring the
refresh forward (at most every ``OPEN_SCOPE_EARLY_REFRESH_MIN_S``). A market
that cools stays a seed for ``OPEN_SCOPE_QUIET_S`` after it was last hot, the
open arm's own demotion rule. The poll keeps pricing it meanwhile (overlap,
never a gap: a newer socket write always wins).

BOUNDS. ``PM_HOT_PROPS_MAX`` (default 1500, 0 = off) is the CEILING of the live
set; the props switch off makes every function here a no-op.

NO HARD RULE (Alex, 2026-11-01 2:40 PM PT): "show as many props as we can all
the time, roughly ranked by how dynamic they are and how much total volume
they're seeing". The live set's size follows this process's own CPU
(`LiveBudget`): every ``BUDGET_EVAL_S`` it grows by ``BUDGET_STEP`` while the
process stays below ``PM_HOT_PROPS_CPU_TARGET`` minus a margin, and shrinks by a
third once it is above it, so a quiet day carries many props and a full NFL
slate fewer. Rank = moves in the window, weighted up by the market's 24-hour
volume (recorded with each move). Props a reader holds, or a surface serves,
stay live whatever this says: they are seeded on their own.
"""

from __future__ import annotations

import logging
import math
import os
import time
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

HOT_WINDOW_MIN = 10
_KEY = "venue_poll_30s:pm_prop_moves"
_BUCKET_TTL_S = (HOT_WINDOW_MIN + 5) * 60
#: market id -> 24-hour volume, written with each recorded move.
_VOLUME_KEY = "venue_poll_30s:pm_prop_volume"
_VOLUME_TTL_S = 6 * 3600
#: The live set starts here and moves by these steps (`LiveBudget`).
BUDGET_START = 200
BUDGET_STEP = 100
BUDGET_FLOOR = 50
BUDGET_EVAL_S = 120.0
#: Grow only this far below the target: a step's cost must fit in the margin.
BUDGET_MARGIN = 0.10


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return min(max(value, low), high)


def hot_max() -> int:
    """``PM_HOT_PROPS_MAX``: the most props the open arm may keep live (0-3000)."""
    return _env_int("PM_HOT_PROPS_MAX", 1500, 0, 3000)


def cpu_target() -> float:
    """``PM_HOT_PROPS_CPU_TARGET``: this process's CPU (cores) the live set may grow to."""
    try:
        value = float(os.getenv("PM_HOT_PROPS_CPU_TARGET", "").strip())
    except ValueError:
        return 0.75  # headroom for the headline's 0.5 s: a busier loop delays receipts
    return min(max(value, 0.30), 0.95)


class LiveBudget:
    """How many hot props stay live, from this process's measured CPU.

    Every ``BUDGET_EVAL_S`` (on the next call): CPU over the interval is the
    process's CPU seconds over wall seconds. Above the target, the budget drops
    by a third (never below ``BUDGET_FLOOR``); below target minus the margin it
    grows by ``BUDGET_STEP`` (never above the ceiling); in between it holds.
    """

    def __init__(self, *, clock=time.monotonic, cpu_clock=time.process_time) -> None:
        self._clock, self._cpu_clock = clock, cpu_clock
        self.cap = BUDGET_START
        self.cpu: Optional[float] = None
        self._mark = (clock(), cpu_clock())

    def current(self, ceiling: int) -> int:
        now, cpu_now = self._clock(), self._cpu_clock()
        wall = now - self._mark[0]
        if wall >= BUDGET_EVAL_S:
            self.cpu = max(0.0, (cpu_now - self._mark[1]) / wall)
            self._mark = (now, cpu_now)
            target, before = cpu_target(), self.cap
            if self.cpu > target:
                self.cap = max(BUDGET_FLOOR, int(self.cap * 2 / 3))
            elif self.cpu < target - BUDGET_MARGIN:
                self.cap = self.cap + BUDGET_STEP
            self.cap = min(self.cap, ceiling)
            if self.cap != before:
                logger.info("pm_hot_props: live budget %d -> %d (cpu %.2f, target %.2f)",
                            before, self.cap, self.cpu, target)
        return min(self.cap, ceiling)


_BUDGET: Optional[LiveBudget] = None


def live_budget() -> LiveBudget:
    global _BUDGET
    if _BUDGET is None:
        _BUDGET = LiveBudget()
    return _BUDGET


def rank_score(moves: float, volume: Optional[float]) -> float:
    """Moves in the window, weighted up to about 2x by 24-hour volume ($100k)."""
    vol = volume if isinstance(volume, (int, float)) and volume > 0 else 0.0
    return moves * (1.0 + math.log10(1.0 + vol) / 5.0)


def hot_min_moves() -> int:
    """``PM_HOT_PROPS_MIN_MOVES``: passes moved in the window to count as hot."""
    return _env_int("PM_HOT_PROPS_MIN_MOVES", 3, 1, 1000)


def enabled() -> bool:
    from app.tasks.polymarket_open_contracts import props_to_poll_enabled

    return props_to_poll_enabled() and hot_max() > 0


def _redis():
    from app.tasks.redis_state import get_redis_client

    return get_redis_client(socket_timeout=2.0, socket_connect_timeout=2.0)


def _bucket(minute: int) -> str:
    return f"{_KEY}:{minute}"


def props_arm_stmt(market_ids: Iterable[int]):
    """The given ids the props arm owns: open Polymarket markets on an event
    the socket's window holds, refused as a winner by their venue label."""
    from sqlalchemy import select

    from app.models.models import Event, FuturesMarket
    from app.tasks.polymarket_open_contracts import venue_label_refusal_clause
    from app.tasks.polymarket_ws import _slate_event_window

    return (
        select(FuturesMarket.id)
        .join(Event, FuturesMarket.event_id == Event.id)
        .where(
            FuturesMarket.id.in_(sorted(set(market_ids))),
            FuturesMarket.source == "polymarket",
            FuturesMarket.status == "open",
            _slate_event_window(),
            venue_label_refusal_clause(),
        )
    )


async def record_moved(session, market_ids: Iterable[int], *, now: float | None = None) -> int:
    """Count one move for each of these markets the props arm owns. Never raises."""
    ids = set(market_ids)
    if not ids or not enabled():
        return 0
    try:
        from app.models.models import FuturesMarket

        rows = (await session.execute(
            props_arm_stmt(ids).add_columns(FuturesMarket.volume_24h))).all()
        await session.commit()
        owned = [row[0] for row in rows]
        if not owned:
            return 0
        key = _bucket(int((time.time() if now is None else now) // 60))
        pipe = _redis().pipeline()
        for mid in owned:
            pipe.zincrby(key, 1, mid)
        pipe.expire(key, _BUCKET_TTL_S)
        volumes = {row[0]: int(row[1]) for row in rows if len(row) > 1 and row[1] is not None}
        if volumes:
            pipe.hset(_VOLUME_KEY, mapping=volumes)
            pipe.expire(_VOLUME_KEY, _VOLUME_TTL_S)
        pipe.execute()
        return len(owned)
    except Exception as exc:  # noqa: BLE001 — heat is an optimisation
        logger.warning("pm_hot_props: moves not recorded: %s", exc)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def hot_market_ids(*, now: float | None = None, client=None,
                   budget: Optional[LiveBudget] = None) -> frozenset[int]:
    """The top props by `rank_score` over the last ``HOT_WINDOW_MIN`` minutes,
    each with at least ``hot_min_moves()`` moves, as many as the CPU budget
    allows (`LiveBudget`, at most ``hot_max()``). Empty when off or unreadable
    (heat never blocks a refresh)."""
    if not enabled():
        return frozenset()
    minute = int((time.time() if now is None else now) // 60)
    keys = [_bucket(m) for m in range(minute - HOT_WINDOW_MIN + 1, minute + 1)]
    try:
        rc = client if client is not None else _redis()
        totals: dict[int, float] = {}
        pipe = rc.pipeline()
        for key in keys:
            pipe.zrange(key, 0, -1, withscores=True)
        pipe.hgetall(_VOLUME_KEY)
        *buckets, raw_volumes = pipe.execute()
        for members in buckets:
            for member, score in members or ():
                mid = int(member.decode() if isinstance(member, bytes) else member)
                totals[mid] = totals.get(mid, 0.0) + float(score)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pm_hot_props: heat unreadable: %s", exc)
        return frozenset()
    volumes: dict[int, float] = {}
    for key, value in (raw_volumes or {}).items():
        try:
            volumes[int(key.decode() if isinstance(key, bytes) else key)] = float(
                value.decode() if isinstance(value, bytes) else value)
        except (TypeError, ValueError):
            continue
    floor = hot_min_moves()
    ranked = sorted((mid for mid, n in totals.items() if n >= floor),
                    key=lambda mid: (-rank_score(totals[mid], volumes.get(mid)), mid))
    cap = (budget if budget is not None else live_budget()).current(hot_max())
    return frozenset(ranked[:cap])
