"""THE MOMENTS ENGINE — offline per-event join task (#1168, MLB v1).

Runs the pure join (`app.utils.game_moments`) over recently-completed MLB events
and persists confident moments to `game_moments`. Offline + storage-cheap: the
history endpoint reads rows, never computes them at render.

It also carries the MLB ground-truth validation gate — comparing our confident
moments against MLB's OWN per-at-bat win probability — and reports the aggregate
agreement rate. Poor agreement is the signal to keep the table but hold the
surfacing (a Redis kill switch, `moments:surface_enabled`, gates the payload).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.models import Event, GameMoment, Sport, WinProbSnapshot
from app.tasks.base import get_task_session
from app.utils.game_moments import agreement_rate, compute_moments

logger = logging.getLogger(__name__)

MLB_SPORT_KEY = "baseball_mlb"
LOOKBACK_HOURS = 72  # recently-completed games still have live snapshot streams
# Prefer the WP source with the most score-carrying snapshots for the join.
_SCORE_SOURCES = ("mlb", "espn", "stat_model")


def _snapshot_dicts(snaps: list[WinProbSnapshot]) -> list[dict]:
    """Build the join's snapshot input from the best-covered source: rows whose
    game_state carries a score, so scoring plays can be score-matched."""
    by_source: dict[str, list[dict]] = {}
    for s in snaps:
        gs = s.game_state or {}
        if gs.get("home_score") is None or gs.get("away_score") is None:
            continue
        if s.home_win_probability is None:
            continue
        by_source.setdefault(s.source, []).append(
            {
                "ts": s.captured_at,
                "home_prob": float(s.home_win_probability),
                "home_score": gs.get("home_score"),
                "away_score": gs.get("away_score"),
                "mlb_game_pk": gs.get("mlb_game_pk"),
            }
        )
    if not by_source:
        return []
    # richest source (ties broken by the _SCORE_SOURCES preference order)
    best = max(
        by_source.items(),
        key=lambda kv: (
            len(kv[1]),
            -(_SCORE_SOURCES.index(kv[0]) if kv[0] in _SCORE_SOURCES else 99),
        ),
    )
    return best[1]


async def _validate_against_mlb(game_pk, our_moments) -> dict | None:
    """Fetch MLB's own per-at-bat WP and report agreement. Advisory — never blocks
    persistence; a network hiccup just skips this event's validation."""
    if not game_pk:
        return None
    try:
        from app.services.mlb_api import MLBAPIService

        entries = await MLBAPIService().get_win_probability_history(int(game_pk))
    except Exception as exc:  # noqa: BLE001
        logger.info("moments: MLB validation fetch failed for %s: %s", game_pk, exc)
        return None
    mlb = [
        {"description": e.description, "home_win_probability": e.home_win_probability}
        for e in entries
    ]
    return agreement_rate(our_moments, mlb)


async def _compute_game_moments(limit: int = 60):
    """Compute + persist moments for recently-completed MLB events."""
    stats = {
        "events_scanned": 0,
        "events_with_moments": 0,
        "moments_written": 0,
        "confident_written": 0,
        "agreement_checked": 0,
        "agreement_agreed": 0,
    }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    async with get_task_session() as session:
        rows = (
            await session.execute(
                select(Event)
                .join(Sport, Event.sport_id == Sport.id)
                .where(
                    Sport.key == MLB_SPORT_KEY,
                    Event.status.in_(("completed", "closed")),
                    Event.commence_time >= cutoff,
                    Event.box_score_data.isnot(None),
                )
                .order_by(Event.commence_time.desc())
                .limit(limit)
            )
        ).scalars().all()

        for event in rows:
            stats["events_scanned"] += 1
            box = event.box_score_data or {}
            plays = box.get("scoring_plays") or []
            if not plays:
                continue
            snaps = (
                await session.execute(
                    select(WinProbSnapshot).where(
                        WinProbSnapshot.event_id == event.id
                    )
                )
            ).scalars().all()
            snap_dicts = _snapshot_dicts(snaps)
            if len(snap_dicts) < 2:
                continue

            moments = compute_moments(
                plays,
                snap_dicts,
                event.home_team_name,
                event.away_team_name,
                source="espn",
            )
            if not moments:
                continue

            # Idempotent recompute: replace this event's rows.
            await session.execute(
                delete(GameMoment).where(GameMoment.event_id == event.id)
            )
            confident = 0
            for m in moments:
                if m.get("confidence") is not None and float(m["confidence"]) >= 0.5:
                    confident += 1
                session.add(GameMoment(event_id=event.id, **m))
            await session.commit()

            stats["events_with_moments"] += 1
            stats["moments_written"] += len(moments)
            stats["confident_written"] += confident

            # MLB ground-truth validation (advisory).
            game_pk = next(
                (s.get("mlb_game_pk") for s in snap_dicts if s.get("mlb_game_pk")),
                None,
            )
            report = await _validate_against_mlb(game_pk, moments)
            if report and report.get("checked"):
                stats["agreement_checked"] += report["checked"]
                stats["agreement_agreed"] += report["agreed"]

    if stats["agreement_checked"]:
        stats["agreement_rate"] = round(
            stats["agreement_agreed"] / stats["agreement_checked"], 3
        )
    else:
        stats["agreement_rate"] = None
    logger.info("game_moments: %s", stats)
    return stats
