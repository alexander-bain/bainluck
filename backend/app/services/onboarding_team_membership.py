"""Shared league membership for the bounded onboarding search."""

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter

from redis import Redis
from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, Team
from app.utils.request_cache import (
    bounded_redis_call,
    get_shared_async_redis,
    schedule_background,
)

logger = logging.getLogger(__name__)

_KEY = "bainluck:onboarding:team-league-members:1"
_READY = "ready"
_SNAPSHOT_TTL_S = 7 * 24 * 60 * 60
_BOOTSTRAP_CLAIM_TTL_S = 60 * 60
_REBUILD_TASK = "app.tasks.refresh_onboarding_team_membership"

_game_sides = (
    select(
        Event.sport_id,
        func.unnest(array([Event.home_team_id, Event.away_team_id])).label("team_id"),
    )
    .distinct()
    .subquery()
)
_CONTRIBUTING_TEAMS = select(_game_sides.c.sport_id, _game_sides.c.team_id).join(
    Team,
    and_(Team.id == _game_sides.c.team_id, Team.sport_id == _game_sides.c.sport_id),
)


def _dispatch_bootstrap_rebuild() -> None:
    from app.tasks import refresh_onboarding_team_membership

    try:
        refresh_onboarding_team_membership.apply_async(
            queue="background", expires=300, retry=False
        )
    except Exception as exc:
        logger.warning(
            "Could not request onboarding membership rebuild (%s)", type(exc).__name__
        )


async def onboarding_team_members(
    candidates: Sequence[tuple[int, int]],
) -> set[tuple[int, int]] | None:
    """Check only shortlisted (league ID, team ID) pairs against one snapshot."""
    cache = await get_shared_async_redis()
    keys = [_READY, *(f"{league_id}:{team_id}" for league_id, team_id in candidates)]
    result = await bounded_redis_call(lambda: cache.smismember(_KEY, keys))
    # The marker and all memberships come from the same Redis operation.
    if not result.is_ok or len(result.value) != len(keys):
        return None
    if not result.value[0]:
        claim = await bounded_redis_call(
            lambda: cache.set(
                f"{_KEY}:bootstrap", 1, nx=True, ex=_BOOTSTRAP_CLAIM_TTL_S
            )
        )
        if claim.is_ok and claim.value:
            schedule_background(asyncio.to_thread(_dispatch_bootstrap_rebuild))
        return None
    return {pair for pair, is_member in zip(candidates, result.value[1:]) if is_member}


async def rebuild_onboarding_team_membership(db: AsyncSession, cache: Redis) -> dict:
    """Build once on the worker and publish a whole snapshot on success."""
    from app.tasks.task_checkpoint import advisory_lock_key

    started = perf_counter()
    await db.execute(text("SET TRANSACTION READ ONLY"))
    await db.execute(text("SET LOCAL statement_timeout = '120s'"))
    await db.execute(text("SET LOCAL lock_timeout = '250ms'"))
    acquired = await db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"),
        {"key": advisory_lock_key(_REBUILD_TASK)},
    )
    if not acquired:
        return {"terminal": "skipped", "reason": "rebuild_already_running"}

    rows = (await db.execute(_CONTRIBUTING_TEAMS)).all()
    members = [f"{league_id}:{team_id}" for league_id, team_id in rows]
    pending_key = f"{_KEY}:pending"
    # The worker reuses the bounded sync Redis pool across its per-task event
    # loops. Hold the transaction lock until the new snapshot is published.
    with cache.pipeline() as pipe:
        (
            pipe.delete(pending_key)
            .sadd(pending_key, _READY, *members)
            .expire(pending_key, _SNAPSHOT_TTL_S)
            .execute()
        )
    cache.rename(pending_key, _KEY)

    elapsed_ms = round((perf_counter() - started) * 1000, 1)
    logger.info(
        "Onboarding team membership rebuilt in %.1f ms (%d eligible teams)",
        elapsed_ms,
        len(members),
    )
    return {
        "terminal": "complete",
        "eligible_teams": len(members),
        "elapsed_ms": elapsed_ms,
    }
