"""Fast ESPN score refresh for games with an active Live Activity (#10542 step 5).

``sync_espn_live_events`` runs on a 60 s beat (measured p95 ~81 s), which leaves
served scores 21-40 s (worst ~60 s) behind ESPN (#12999). When at least one phone
is actively following a game via Live Activity, this helper refreshes ONLY those
pinned live (or tipping-off-within-15-min) games from ESPN right before
``ActivityKitObservationAdapter.capture`` runs, then the worker pushes immediately
if the screen changed.

Design invariants:
* **Zero cost when nobody has a Live Activity.** Never called unless
  ``run_activitykit_page`` enumerated active registrations.
* **No DB connection held across HTTP.** Phase 1 reads ``(event.id, event.espn_id,
  sport.key)`` and releases the session; Phase 2 fetches ESPN with a hard timeout
  (one ``get_scoreboard`` call per distinct active sport, plus a single-event
  ``get_event`` fallback only if a live game fell across midnight UTC); Phase 3
  re-loads matched ``Event`` rows and writes through the canonical
  ``update_event_fields_from_espn`` (keeping all #6056 reversion guards, #7338
  orientation checks, #4571 ``score_observed_at`` stamps, and ``ScoreSnapshot``
  writes intact).
* **Fails open.** A slow, dark, or errored ESPN call never blocks APNs delivery
  of already-stored readings.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Callable, Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.models.models import Event, Sport
from app.services.espn_api import ESPNAPIService
from app.utils.espn_helpers import update_event_fields_from_espn

logger = logging.getLogger(__name__)

#: Total wall-clock budget for all ESPN fetches in one Live Activity tick.
FAST_REFRESH_TIMEOUT_SECONDS = 4.0

#: Catch tipoff within 15 s for games pinned just before start, while making zero
#: ESPN calls for games scheduled hours or days away.
PREGAME_LEAD_WINDOW = timedelta(minutes=15)

#: Hard cap on single-event fallbacks per tick (e.g. midnight-UTC rollover).
MAX_EVENT_FALLBACKS = 5

_ACTIVE_STATUSES = ("live", "suspended")
_PREGAME_STATUS = "scheduled"


async def refresh_active_live_activity_scores(
    sessions,
    event_ids: Iterable[int],
    *,
    espn_factory: Callable[[], ESPNAPIService] = ESPNAPIService,
    updater=update_event_fields_from_espn,
    timeout_seconds: float = FAST_REFRESH_TIMEOUT_SECONDS,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, int]:
    """Refresh ESPN scores for active-Live-Activity games before observation capture."""
    summary = {
        "checked": 0,
        "sports_fetched": 0,
        "matched": 0,
        "refreshed": 0,
        "errors": 0,
    }
    distinct_ids = list(
        dict.fromkeys(eid for eid in event_ids if type(eid) is int and eid > 0)
    )
    if not distinct_ids:
        return summary

    now = clock()
    if now.utcoffset() is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    # Phase 1: short read-only lookup of eligible ESPN-anchored games; release
    # the connection before touching the network.
    try:
        async with sessions() as session:
            rows = (
                await session.execute(
                    select(Event.id, Event.espn_id, Sport.key)
                    .join(Sport, Event.sport_id == Sport.id)
                    .where(
                        Event.id.in_(distinct_ids),
                        Event.espn_id.is_not(None),
                        or_(
                            Event.status.in_(_ACTIVE_STATUSES),
                            and_(
                                Event.status == _PREGAME_STATUS,
                                Event.commence_time.is_not(None),
                                Event.commence_time <= now + PREGAME_LEAD_WINDOW,
                            ),
                        ),
                    )
                )
            ).all()
    except Exception:
        summary["errors"] += 1
        return summary

    if not rows:
        return summary

    targets_by_sport: dict[str, list[tuple[int, str]]] = {}
    for event_id, espn_id, sport_key in rows:
        if not espn_id or not sport_key:
            continue
        targets_by_sport.setdefault(str(sport_key), []).append(
            (int(event_id), str(espn_id))
        )
    if not targets_by_sport:
        return summary

    # Phase 2: fetch ESPN with NO database connection held.
    espn = espn_factory()
    matched: dict[int, tuple[object, datetime]] = {}
    try:
        supported_sports = [
            sport_key
            for sport_key in targets_by_sport
            if espn._get_espn_path(sport_key)
        ]
        summary["checked"] = sum(
            len(targets_by_sport[sport_key]) for sport_key in supported_sports
        )
        if not supported_sports:
            return summary

        async def _fetch_sport(sport_key: str):
            events = await espn.get_scoreboard(sport_key)
            fetched_at = clock()
            if fetched_at.utcoffset() is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            else:
                fetched_at = fetched_at.astimezone(timezone.utc)
            return sport_key, events, fetched_at

        missing_targets: list[tuple[int, str, str]] = []
        try:
            async with asyncio.timeout(timeout_seconds):
                board_results = await asyncio.gather(
                    *(_fetch_sport(sk) for sk in supported_sports),
                    return_exceptions=True,
                )
                for item in board_results:
                    if isinstance(item, Exception):
                        summary["errors"] += 1
                        continue
                    sport_key, board_events, fetched_at = item
                    summary["sports_fetched"] += 1
                    if not board_events:
                        for event_id, espn_id in targets_by_sport[sport_key]:
                            missing_targets.append((event_id, sport_key, espn_id))
                        continue
                    by_espn_id = {
                        str(ee.espn_id): ee
                        for ee in board_events
                        if getattr(ee, "espn_id", None) is not None
                    }
                    for event_id, espn_id in targets_by_sport[sport_key]:
                        ee = by_espn_id.get(espn_id)
                        if ee is not None:
                            matched[event_id] = (ee, fetched_at)
                        else:
                            missing_targets.append((event_id, sport_key, espn_id))

                # Midnight-UTC rollover fallback: if an anchored live game is not
                # on today's scoreboard, fetch it directly by ESPN event id.
                if missing_targets:
                    fallback_batch = missing_targets[:MAX_EVENT_FALLBACKS]

                    async def _fetch_single(event_id: int, sport_key: str, espn_id: str):
                        ee = await espn.get_event(sport_key, espn_id)
                        fetched_at = clock()
                        if fetched_at.utcoffset() is None:
                            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
                        else:
                            fetched_at = fetched_at.astimezone(timezone.utc)
                        return event_id, ee, fetched_at

                    single_results = await asyncio.gather(
                        *(
                            _fetch_single(eid, sk, espn_id)
                            for eid, sk, espn_id in fallback_batch
                        ),
                        return_exceptions=True,
                    )
                    for item in single_results:
                        if isinstance(item, Exception):
                            summary["errors"] += 1
                            continue
                        event_id, ee, fetched_at = item
                        if ee is not None:
                            matched[event_id] = (ee, fetched_at)
        except TimeoutError:
            summary["errors"] += 1
    finally:
        close_fn = getattr(espn, "close", None)
        if callable(close_fn):
            try:
                async with asyncio.timeout(2):
                    await close_fn()
            except Exception:
                # Best-effort client cleanup; never block APNs delivery on close failure.
                logger.debug("ActivityKit fast score refresh client close failed")

    summary["matched"] = len(matched)
    if not matched:
        return summary

    # Phase 3: write matched live scores through canonical update_event_fields_from_espn.
    try:
        async with sessions() as session:
            events = (
                await session.execute(
                    select(Event)
                    .options(selectinload(Event.sport))
                    .where(Event.id.in_(list(matched.keys())))
                )
            ).scalars().all()
            stats: dict[str, int] = {}
            claimed_espn_ids: set[str] = set()
            for event in events:
                pair = matched.get(event.id)
                if pair is None:
                    continue
                ee, observed_at = pair
                try:
                    async with session.begin_nested():
                        changed = await updater(
                            session,
                            event,
                            ee,
                            claimed_espn_ids,
                            stats,
                            observed_at=observed_at,
                        )
                    if changed:
                        summary["refreshed"] += 1
                except Exception:
                    summary["errors"] += 1
            await session.commit()
    except Exception:
        summary["errors"] += 1

    return summary
