"""#1201 — MLB schedule-coverage check: the sentinel side of the schedule-diff.

Fetches the official MLB schedule for a date and reconciles it against our
events using the pure classifier in ``app/utils/schedule_diff.py``. The invariant
it asserts is **every official MLB game that day ↔ exactly one of our events**;
it also surfaces ``premature_settle`` (the #1193/#1201 rot) and ``postponed``
state divergences.

Read-only (it never mutates events — applying the transitions is a separate,
gated path). Fails soft: if statsapi is unreachable it returns ``skipped=True``,
never a false alarm. Exposed on-demand via the admin route so ops/Fable can prove
"today's slate clean" without waiting for a beat.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def run_mlb_schedule_coverage(date: Optional[str] = None) -> dict:
    """Reconcile the official MLB schedule for ``date`` (YYYY-MM-DD, default
    today UTC) against our events. Returns a verdict dict:

        {checked, passed, skipped, transitions: [...], counts: {...}, date}
    """
    from sqlalchemy import select, text  # noqa: F401

    from app.models.models import Event, Sport, Team
    from app.services.mlb_api import MLBAPIService
    from app.tasks.base import get_task_session
    from app.utils.schedule_diff import diff_schedule, normalize_official_game

    now = datetime.now(timezone.utc)
    day = date or now.strftime("%Y-%m-%d")

    service = MLBAPIService()
    try:
        raw_games = await service.get_todays_games(date=day)
    except Exception as exc:
        logger.warning("MLB schedule fetch failed for %s: %s", day, exc)
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": f"statsapi unreachable: {str(exc)[:120]}"}}
    finally:
        await service.close()

    if not raw_games:
        # An empty official slate (off-day) is not a failure.
        return {"flow": "mlb_schedule_coverage", "date": day, "checked": 0,
                "passed": True, "skipped": True,
                "evidence": {"reason": "no official MLB games on this date"}}

    official = [normalize_official_game(g) for g in raw_games]

    # Our MLB events for the same UTC day (±18h to cover boundary crossings), the
    # same window audit_event_counts uses.
    day_noon = datetime.strptime(day, "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
    our_events: list[dict] = []
    async with get_task_session() as s:
        rows = (await s.execute(
            select(Event.id, Event.status, Team.name.label("home"),
                   Sport.key.label("sport"))
            .join(Sport, Sport.id == Event.sport_id)
            .outerjoin(Team, Team.id == Event.home_team_id)
            .where(
                Sport.key.in_(["baseball_mlb", "baseball_mlb_preseason"]),
                Event.commence_time.between(day_noon - timedelta(hours=18),
                                            day_noon + timedelta(hours=18)),
            )
        )).all()
        # Second pass for away names (kept separate to avoid a double outerjoin alias).
        ev_map = {r.id: {"id": r.id, "status": r.status, "home_team": r.home or "",
                         "away_team": ""} for r in rows}
        if ev_map:
            away_rows = (await s.execute(
                select(Event.id, Team.name.label("away"))
                .outerjoin(Team, Team.id == Event.away_team_id)
                .where(Event.id.in_(list(ev_map.keys())))
            )).all()
            for ar in away_rows:
                if ar.id in ev_map:
                    ev_map[ar.id]["away_team"] = ar.away or ""
        our_events = list(ev_map.values())

    transitions = diff_schedule(official, our_events, now=now)
    counts: dict[str, int] = {}
    for t in transitions:
        counts[t.kind] = counts.get(t.kind, 0) + 1

    failures = [
        {"kind": t.kind, "detail": t.detail, "game_pk": t.game_pk,
         "event_ids": t.event_ids}
        for t in transitions
    ]
    return {
        "flow": "mlb_schedule_coverage",
        "date": day,
        "checked": len(official),
        "our_events": len(our_events),
        "passed": len(failures) == 0,
        "skipped": False,
        "counts": counts,
        "failures": failures,
    }
