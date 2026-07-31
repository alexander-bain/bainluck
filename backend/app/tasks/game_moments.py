"""THE MOMENTS ENGINE — offline per-event join task (#1168, MLB v1).

Runs the pure join (`app.utils.game_moments`) over recently-completed MLB events
and persists confident moments to `game_moments`. Offline + storage-cheap: the
history endpoint reads rows, never computes them at render.

It also carries the MLB ground-truth validation gate — comparing our confident
moments against MLB's OWN per-at-bat win probability — and reports the aggregate
agreement rate. Poor agreement is the signal to keep the table but hold the
surfacing (a Redis kill switch, `moments:surface_enabled`, gates the payload).
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models import Event, GameMoment, Sport, WinProbSnapshot
from app.tasks.base import get_task_session
from app.utils.game_moments import (
    agreement_rate,
    canonicalize_moments,
    compute_moments,
    synth_scoring_plays_from_snapshots,
)

logger = logging.getLogger(__name__)

MLB_SPORT_KEY = "baseball_mlb"
LOOKBACK_HOURS = 72  # recently-completed games still have live snapshot streams
# Prefer the WP source with the most score-carrying snapshots for the join.
_SCORE_SOURCES = ("mlb", "espn", "stat_model")

# Transaction-scoped advisory-lock namespace (#1168) — serializes replacement of
# ONE event's moment set across overlapping invocations (manual dispatch, a
# duplicate beat, or a broker redelivery). Released automatically at COMMIT or
# ROLLBACK, so a crashed run can never hold it.
_LOCK_NAMESPACE = 1168

# Every selected event reaches exactly one of these; a run that cannot name an
# event's outcome is a bug, not a quiet skip (C56/C59).
TERMINAL_WRITTEN = "written"
TERMINAL_EMPTY = "empty"
TERMINAL_SKIPPED = "skipped"  # no evidence to judge on → prior rows preserved
TERMINAL_FAILED = "failed"
TERMINAL_CANCELLED = "cancelled"

# Columns the upsert refreshes when a key already exists (everything but the
# identity pair and the server-defaulted created_at).
_UPSERT_COLUMNS = (
    "ts",
    "moment_type",
    "description",
    "actor_team",
    "actor_player",
    "period",
    "home_score",
    "away_score",
    "source",
    "prob_delta",
    "confidence",
    "label",
)


class GameMomentsRunFailure(Exception):
    """At least one selected event failed to reach a written/empty outcome.

    Raised only AFTER every event has been attempted, so a poison event can never
    starve its siblings — but the run is still reported red. A failed event that
    returned a green task result is exactly the false-green #1445 hid behind.
    """


async def _replace_event_moments(session, event_id: int, moments: list[dict]) -> None:
    """Make ``game_moments`` for ONE event equal ``moments``, atomically.

    Ordering matters: upsert first, delete-what's-missing second, one commit. A
    delete-then-insert (the v1 shape) exposes a window where the event has NO
    annotations, and races another invocation into `uq_game_moment_event_key`.
    The advisory lock serializes concurrent replacements of the same event; the
    upsert makes a lost race a no-op update instead of a crash.
    """
    await session.execute(
        select(func.pg_advisory_xact_lock(_LOCK_NAMESPACE, event_id))
    )

    # Defence in depth: a producer must never hand us one key twice — PostgreSQL
    # rejects an ON CONFLICT that touches the same row a second time.
    rows = canonicalize_moments(moments)
    keys = [m["dedupe_key"] for m in rows]

    if rows:
        stmt = pg_insert(GameMoment).values(
            [{"event_id": event_id, **m} for m in rows]
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_game_moment_event_key",
            set_={c: getattr(stmt.excluded, c) for c in _UPSERT_COLUMNS},
        )
        await session.execute(stmt)

    stale = delete(GameMoment).where(GameMoment.event_id == event_id)
    if keys:
        stale = stale.where(GameMoment.dedupe_key.notin_(keys))
    await session.execute(stale)

    await session.commit()


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
                "period": gs.get("period"),
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


async def _select_events(session, cutoff, limit: int) -> list[dict]:
    """Select the pass's events as SCALARS.

    Gotcha #6: the loop below commits and rolls back per event, and a rollback
    expires every ORM object attached to the session — `expire_on_commit=False`
    does not save you. Copying what the loop needs up front keeps a poison event
    from turning its siblings into `MissingGreenlet` lazy-load crashes.
    """
    rows = (
        await session.execute(
            select(
                Event.id,
                Event.home_team_name,
                Event.away_team_name,
                Event.box_score_data,
            )
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
    ).all()
    return [
        {
            "id": r.id,
            "home": r.home_team_name,
            "away": r.away_team_name,
            "box": r.box_score_data or {},
        }
        for r in rows
    ]


async def _process_event(session, ev: dict, stats: dict) -> str:
    """Compute + persist ONE event. Returns its terminal state.

    The three outcomes are deliberately distinct:
      * computed rows      → authoritative replacement (`written`)
      * computed nothing   → authoritative removal of stale rows (`empty`)
      * no evidence to judge on → prior rows PRESERVED (`skipped`)
    Only a real error is `failed`; thin evidence must never delete truth we
    cannot currently re-derive.
    """
    event_id = ev["id"]
    snaps = (
        await session.execute(
            select(WinProbSnapshot).where(WinProbSnapshot.event_id == event_id)
        )
    ).scalars().all()
    snap_dicts = _snapshot_dicts(snaps)
    if len(snap_dicts) < 2:
        return TERMINAL_SKIPPED

    # Prefer real ESPN scoring plays (NBA/NFL); MLB's are empty, so fall
    # back to synthesizing plays from snapshot score-transitions.
    plays = ev["box"].get("scoring_plays") or []
    src = "espn"
    if not plays:
        plays = synth_scoring_plays_from_snapshots(snap_dicts, ev["home"], ev["away"])
        src = "mlb"
    if not plays:
        return TERMINAL_SKIPPED

    moments = compute_moments(
        plays, snap_dicts, ev["home"], ev["away"], source=src
    )

    await _replace_event_moments(session, event_id, moments)
    if not moments:
        return TERMINAL_EMPTY

    stats["events_with_moments"] += 1
    stats["moments_written"] += len(moments)
    stats["confident_written"] += sum(
        1
        for m in moments
        if m.get("confidence") is not None and float(m["confidence"]) >= 0.5
    )

    # MLB ground-truth validation (advisory) — runs after the event is already
    # durable, and can never change its terminal state.
    try:
        game_pk = next(
            (s.get("mlb_game_pk") for s in snap_dicts if s.get("mlb_game_pk")),
            None,
        )
        report = await _validate_against_mlb(game_pk, moments)
        if report and report.get("checked"):
            stats["agreement_checked"] += report["checked"]
            stats["agreement_agreed"] += report["agreed"]
    except Exception as exc:  # noqa: BLE001
        logger.info("moments: validation skipped for event %s: %s", event_id, exc)

    return TERMINAL_WRITTEN


async def _compute_game_moments(limit: int = 60):
    """Compute + persist moments for recently-completed MLB events.

    Each event is its own error boundary (gotcha #42): one event's failure
    rolls back only that event, is counted truthfully, and the loop continues so
    healthy siblings still commit. The run is still reported RED at the end —
    starvation and false-green are two different bugs and this fixes both.
    """
    stats = {
        "events_scanned": 0,
        "events_with_moments": 0,
        "moments_written": 0,
        "confident_written": 0,
        "agreement_checked": 0,
        "agreement_agreed": 0,
        "events_written": 0,
        "events_empty": 0,
        "events_skipped": 0,
        "events_failed": 0,
        "events_cancelled": 0,
        "failures": [],
    }
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    async with get_task_session() as session:
        events = await _select_events(session, cutoff, limit)

        for ev in events:
            stats["events_scanned"] += 1
            try:
                state = await _process_event(session, ev, stats)
            except (asyncio.CancelledError, SoftTimeLimitExceeded):
                # Never swallow a stop signal: roll this event back so its prior
                # rows survive, name the outcome, then let it propagate.
                await session.rollback()
                stats["events_cancelled"] += 1
                logger.warning(
                    "game_moments: cancelled during event %s: %s", ev["id"], stats
                )
                raise
            except Exception as exc:  # noqa: BLE001
                await session.rollback()
                stats["events_failed"] += 1
                if len(stats["failures"]) < 10:
                    stats["failures"].append(
                        {"event_id": ev["id"], "error": f"{type(exc).__name__}: {exc}"[:300]}
                    )
                logger.exception("game_moments: event %s failed", ev["id"])
                continue
            stats[f"events_{state}"] += 1

    if stats["agreement_checked"]:
        stats["agreement_rate"] = round(
            stats["agreement_agreed"] / stats["agreement_checked"], 3
        )
    else:
        stats["agreement_rate"] = None
    logger.info("game_moments: %s", stats)

    if stats["events_failed"]:
        failure = GameMomentsRunFailure(
            f"{stats['events_failed']}/{stats['events_scanned']} events failed: "
            f"{stats['failures']}"
        )
        failure.stats = stats
        raise failure
    return stats
