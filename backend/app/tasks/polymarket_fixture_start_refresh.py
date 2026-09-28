"""Keep a near-kickoff Polymarket match on the venue's current start (#9418).

Mechanism, specimen and every refusal: ``app/utils/polymarket_fixture_start.py``.
This module is the I/O around it — one indexed read, batched Gamma
``/events?id=`` reads, a one-key stamp merge per moved group, and the #6073
re-date through Phase 1.5's own decision functions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.tasks.base import get_task_session
from app.utils.polymarket_fixture_start import (
    GROUP_ID_PREFIX,
    LOOKAHEAD,
    LOOKBACK,
    POLYMARKET_OWNED_SOURCES,
    STAMP_VENUE_GAME_START_SQL,
    gamma_event_id_from_group,
    row_fixture_start,
    stamp_for,
)
from app.utils.polymarket_settlement_scan import GAMMA_MAX_IDS_PER_REQUEST

logger = logging.getLogger(__name__)


def candidates_query(now: datetime):
    """``(event_id, group_id)`` for every open Polymarket group linked to an
    unfinished row inside the window whose start Polymarket owns.

    The authority door is still asked per row before any write; the source
    filter only keeps rows it would refuse out of the Gamma read. Core rather
    than ``text()`` so the band runs it on the same rail as production, and so
    the prefix test cannot parse as a bind parameter (gotcha #45).
    """
    from app.models.models import Event, FuturesMarket

    return (
        select(Event.id, FuturesMarket.group_id)
        .join(FuturesMarket, FuturesMarket.event_id == Event.id)
        .where(
            Event.status.in_(["scheduled", "live", "suspended"]),
            Event.completed_at.is_(None),
            Event.commence_time_source.in_(list(POLYMARKET_OWNED_SOURCES)),
            Event.commence_time >= now - LOOKBACK,
            Event.commence_time <= now + LOOKAHEAD,
            FuturesMarket.source == "polymarket",
            FuturesMarket.status == "open",
            FuturesMarket.group_id.startswith(GROUP_ID_PREFIX, autoescape=True),
        )
        .distinct()
    )


async def _refresh_polymarket_fixture_starts(service=None, now=None) -> dict:
    """One pass. Returns counts, every key present at zero (gotcha #53).

    ``service`` and ``now`` are injectable for the band; production passes
    neither.
    """
    from app.models.models import Event, FuturesMarket
    from app.services.event_registry import authorized_commence_time_write
    from app.tasks.prediction_market_matching import (
        POLYMARKET_VENUE_COMMENCE_SOURCE,
        _phase15_redate_write_or_shout,
        phase15_event_row_is_unmoved,
        phase15_link_is_valid_for_redate,
        polymarket_venue_redate,
    )

    stats = {
        "candidates": 0,
        "gamma_ids": 0,
        "batches_read": 0,
        "batches_unreadable": 0,
        "groups_with_instant": 0,
        "groups_stamped": 0,
        "rows_stamped": 0,
        "held_unreadable": 0,
        "held_disagreeing": 0,
        "redated": 0,
        "redated_and_unstarted": 0,
        "refused_link": 0,
        "refused_row_moved": 0,
        "refused_inversion": 0,
        "lost_race": 0,
        "funnel": {},
        "errors": [],
    }
    now = now or datetime.now(timezone.utc)

    async with get_task_session() as session:
        rows = (await session.execute(candidates_query(now))).all()

    # Plain scalars, never live rows (gotcha #6).
    groups_by_event: dict[int, list[str]] = {}
    for event_id, group_id in rows:
        if gamma_event_id_from_group(group_id):
            groups_by_event.setdefault(event_id, [])
            if group_id not in groups_by_event[event_id]:
                groups_by_event[event_id].append(group_id)
    for gids in groups_by_event.values():
        gids.sort()
    stats["candidates"] = len(groups_by_event)
    if not groups_by_event:
        stats["terminal"] = "no_polymarket_dated_rows_in_window"
        return stats

    all_gamma_ids = sorted(
        {gamma_event_id_from_group(g) for gs in groups_by_event.values() for g in gs},
        key=int,
    )
    stats["gamma_ids"] = len(all_gamma_ids)

    owns_service = service is None
    if owns_service:
        from app.services.polymarket_api import PolymarketAPIService

        service = PolymarketAPIService()
    instant_by_group: dict[str, object] = {}
    unreadable: set[str] = set()
    try:
        for start in range(0, len(all_gamma_ids), GAMMA_MAX_IDS_PER_REQUEST):
            chunk = all_gamma_ids[start:start + GAMMA_MAX_IDS_PER_REQUEST]
            try:
                raw = await service.get_events_by_ids(chunk)
            except Exception as exc:  # noqa: BLE001 — one batch may not end the pass
                stats["batches_unreadable"] += 1
                stats["errors"].append(f"batch {chunk[0]}…: {str(exc)[:120]}")
                unreadable.update(chunk)
                continue
            stats["batches_read"] += 1
            for payload in raw or []:
                if not isinstance(payload, dict) or payload.get("id") is None:
                    continue
                # The poll's own parser, so the stamp is byte-for-byte what the
                # poll would have written had it reached this event.
                parsed = service._parse_event(payload)
                instant = getattr(parsed, "game_start_time", None)
                if instant is not None:
                    instant_by_group[f"{GROUP_ID_PREFIX}{payload['id']}"] = instant
    finally:
        if owns_service:
            await service.close()
    stats["groups_with_instant"] = len(instant_by_group)

    # Decide per event before writing anything: a group whose record we could
    # not read, or that published no instant, holds every event it serves.
    target_by_event: dict[int, object] = {}
    for event_id, gids in groups_by_event.items():
        if any(gamma_event_id_from_group(g) in unreadable for g in gids):
            stats["held_unreadable"] += 1
            continue
        target = row_fixture_start(instant_by_group.get(g) for g in gids)
        if target is None:
            stats["held_disagreeing"] += 1
            continue
        target_by_event[event_id] = target
    if not target_by_event:
        return stats

    async with get_task_session() as session:
        # 1. The stamp. Only groups that serve a decided event, so a group
        #    this pass holds is left exactly as the poll last wrote it.
        stamped_groups = sorted(
            {g for eid in target_by_event for g in groups_by_event[eid]}
        )
        for gid in stamped_groups:
            result = await session.execute(
                text(STAMP_VENUE_GAME_START_SQL),
                {"group_id": gid, "stamp": stamp_for(instant_by_group[gid])},
            )
            if result.rowcount:
                stats["groups_stamped"] += 1
                stats["rows_stamped"] += result.rowcount

        # 2. The re-date, through Phase 1.5's decision functions verbatim.
        pairs = (
            await session.execute(
                select(FuturesMarket, Event)
                .join(Event, FuturesMarket.event_id == Event.id)
                .where(
                    FuturesMarket.event_id.in_(sorted(target_by_event)),
                    FuturesMarket.group_id.in_(stamped_groups),
                    FuturesMarket.source == "polymarket",
                    FuturesMarket.status == "open",
                )
                .order_by(Event.id, FuturesMarket.id)
            )
        ).all()
        markets_by_event: dict[int, list] = {}
        event_by_id: dict[int, object] = {}
        for market, event in pairs:
            markets_by_event.setdefault(event.id, []).append(market)
            event_by_id[event.id] = event

        for event_id, event in event_by_id.items():
            try:
                target = target_by_event[event_id]
                markets = markets_by_event[event_id]
                redated = polymarket_venue_redate(markets[0], event, fixture=target)
                if redated is None:
                    continue  # no drift, or a start this door may not move
                link_ok = False
                for market in markets:
                    ok, _why = await phase15_link_is_valid_for_redate(
                        session, market, event,
                    )
                    if ok:
                        link_ok = True
                        break
                if not link_ok:
                    stats["refused_link"] += 1
                    continue
                unmoved, observed = await phase15_event_row_is_unmoved(session, event)
                if not unmoved:
                    stats["refused_row_moved"] += 1
                    continue
                was = event.commence_time
                outcome, writes = authorized_commence_time_write(
                    event, redated, POLYMARKET_VENUE_COMMENCE_SOURCE,
                    unstart_when_future=True, now=now,
                )
                if outcome == "refused_inversion":
                    stats["refused_inversion"] += 1
                    continue
                wrote = await _phase15_redate_write_or_shout(
                    session, event, writes, observed, stats,
                )
                if wrote:
                    stats["redated"] += 1
                    if outcome == "corrected_and_unstarted":
                        stats["redated_and_unstarted"] += 1
                    logger.info(
                        "#9418 re-dated event %s (%s vs %s): %s -> %s from "
                        "Polymarket's current record (%s)",
                        event_id, event.home_team_name, event.away_team_name,
                        was, redated, outcome,
                    )
                elif wrote is False:
                    stats["lost_race"] += 1
            except Exception as exc:  # noqa: BLE001 — one bad row never wipes the pass (gotcha #42)
                stats["errors"].append(f"event {event_id}: {str(exc)[:120]}")
                logger.warning("#9418 re-date of event %s failed: %s", event_id, exc)
        await session.commit()
    return stats
