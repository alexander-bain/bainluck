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

BOUNDS. ``PM_HOT_PROPS_MAX`` (default 200, 0 = off) caps the live set; the
props switch off makes every function here a no-op.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Iterable

logger = logging.getLogger(__name__)

HOT_WINDOW_MIN = 10
_KEY = "venue_poll_30s:pm_prop_moves"
_BUCKET_TTL_S = (HOT_WINDOW_MIN + 5) * 60


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except ValueError:
        return default
    return min(max(value, low), high)


def hot_max() -> int:
    """``PM_HOT_PROPS_MAX``: how many props the open arm may keep live (0-2000)."""
    return _env_int("PM_HOT_PROPS_MAX", 200, 0, 2000)


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
        owned = [row[0] for row in (await session.execute(props_arm_stmt(ids))).all()]
        await session.commit()
        if not owned:
            return 0
        key = _bucket(int((time.time() if now is None else now) // 60))
        pipe = _redis().pipeline()
        for mid in owned:
            pipe.zincrby(key, 1, mid)
        pipe.expire(key, _BUCKET_TTL_S)
        pipe.execute()
        return len(owned)
    except Exception as exc:  # noqa: BLE001 — heat is an optimisation
        logger.warning("pm_hot_props: moves not recorded: %s", exc)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0


def hot_market_ids(*, now: float | None = None, client=None) -> frozenset[int]:
    """The top ``hot_max()`` props by moves over the last ``HOT_WINDOW_MIN``
    minutes, each with at least ``hot_min_moves()``. Empty when off or
    unreadable (heat never blocks a refresh)."""
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
        for members in pipe.execute():
            for member, score in members or ():
                mid = int(member.decode() if isinstance(member, bytes) else member)
                totals[mid] = totals.get(mid, 0.0) + float(score)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pm_hot_props: heat unreadable: %s", exc)
        return frozenset()
    floor = hot_min_moves()
    ranked = sorted((mid for mid, n in totals.items() if n >= floor),
                    key=lambda mid: (-totals[mid], mid))
    return frozenset(ranked[: hot_max()])
