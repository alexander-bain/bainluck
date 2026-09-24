"""Take an anchor-less match off the live board when Polymarket says it ended (#3017).

Mechanism and every refusal: ``app/utils/venue_event_ended.py``. This module is
the I/O around it — one indexed read, batched Gamma ``/events?id=`` reads, one
compare-and-set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.tasks.base import get_task_session
from app.utils.polymarket_settlement_scan import GAMMA_MAX_IDS_PER_REQUEST
from app.utils.venue_event_ended import (
    GROUP_ID_PREFIX,
    SUSPEND_ON_VENUE_EVENT_ENDED_SQL,
    VENUE_EVENT_ENDED_CANDIDATES_SQL,
    gamma_event_id_from_group,
    row_carries_no_authority_id,
    row_verdict,
)

logger = logging.getLogger(__name__)


async def _suspend_venue_ended_events(service=None, now=None) -> dict:
    """One pass. Returns counts, every key present at zero (gotcha #53).

    ``service`` and ``now`` are injectable for the band; production passes
    neither.
    """
    stats = {
        "candidates": 0,
        "gamma_ids": 0,
        "batches_read": 0,
        "batches_unreadable": 0,
        "held_not_ended": 0,
        "held_unreadable": 0,
        "ruled": 0,
        "suspended": 0,
        "errors": [],
    }
    now = now or datetime.now(timezone.utc)

    # The read and the write are two sessions, so no connection is held across
    # the Gamma wait; the write's compare-and-set is what makes the gap safe.
    async with get_task_session() as session:
        rows = (
            await session.execute(
                text(VENUE_EVENT_ENDED_CANDIDATES_SQL),
                {"now": now, "group_prefix": GROUP_ID_PREFIX},
            )
        ).all()

    # Plain scalars, never live rows (gotcha #6).
    work = []
    for r in rows:
        if not row_carries_no_authority_id(r.espn_id, r.statpal_fixture_id):
            continue
        gamma_ids = sorted(
            {gid for gid in map(gamma_event_id_from_group, r.group_ids or []) if gid}
        )
        if gamma_ids:
            work.append(
                {
                    "event_id": r.event_id,
                    "home": r.home_team_name,
                    "away": r.away_team_name,
                    "commence_time": r.commence_time,
                    "gamma_ids": gamma_ids,
                }
            )
    stats["candidates"] = len(work)
    if not work:
        stats["terminal"] = "no_anchorless_polymarket_rows_live"
        return stats

    all_ids = sorted({gid for w in work for gid in w["gamma_ids"]}, key=int)
    stats["gamma_ids"] = len(all_ids)

    owns_service = service is None
    if owns_service:
        from app.services.polymarket_api import PolymarketAPIService

        service = PolymarketAPIService()
    payloads: dict[str, dict] = {}
    unreadable: set[str] = set()
    try:
        for start in range(0, len(all_ids), GAMMA_MAX_IDS_PER_REQUEST):
            chunk = all_ids[start : start + GAMMA_MAX_IDS_PER_REQUEST]
            try:
                raw = await service.get_events_by_ids(chunk)
            except Exception as exc:  # noqa: BLE001 — one batch may not end the pass
                stats["batches_unreadable"] += 1
                stats["errors"].append(f"batch {chunk[0]}…: {str(exc)[:120]}")
                unreadable.update(chunk)
                continue
            stats["batches_read"] += 1
            # Keyed by the record's OWN id: Gamma omits ids it does not know.
            for p in raw or []:
                if isinstance(p, dict) and p.get("id") is not None:
                    payloads[str(p["id"])] = p
    finally:
        if owns_service:
            await service.close()

    ruling: dict[int, str] = {}
    for w in work:
        # A row is ruled on EVERY record its markets point at, or not at
        # all. A record we could not read, or one Gamma did not return, may
        # be the one still saying `live` — so its absence holds the row.
        if any(gid in unreadable or gid not in payloads for gid in w["gamma_ids"]):
            stats["held_unreadable"] += 1
            continue
        try:
            period = row_verdict(
                [payloads[gid] for gid in w["gamma_ids"]],
                commence_time=w["commence_time"],
                now=now,
            )
        except Exception as exc:  # noqa: BLE001 — one bad record never wipes the pass (gotcha #42)
            stats["held_unreadable"] += 1
            stats["errors"].append(f"event {w['event_id']}: {str(exc)[:120]}")
            continue
        if period is None:
            stats["held_not_ended"] += 1
            continue
        ruling[w["event_id"]] = period

    stats["ruled"] = len(ruling)
    if ruling:
        async with get_task_session() as session:
            result = await session.execute(
                text(SUSPEND_ON_VENUE_EVENT_ENDED_SQL),
                {"event_ids": sorted(ruling)},
            )
            # The CAS's own rowcount: the difference from `ruled` is rows an
            # authority reached between the read and the write.
            stats["suspended"] = result.rowcount or 0
            await session.commit()
        by_id = {w["event_id"]: w for w in work}
        for event_id, period in sorted(ruling.items()):
            w = by_id[event_id]
            # A RULING, not a receipt — the CAS may have written fewer.
            logger.info(
                "#3017 ruled event %s (%s vs %s) off the live board: "
                "Polymarket's event record says ended (period %s) on "
                "every sports record %s. Suspended, no score and no "
                "completed_at written.",
                event_id,
                w["home"],
                w["away"],
                period,
                w["gamma_ids"],
            )
        if stats["suspended"] != len(ruling):
            logger.info(
                "#3017 ruled %d events and the compare-and-set wrote %d; "
                "the difference is rows an authority reached first.",
                len(ruling),
                stats["suspended"],
            )
    return stats
