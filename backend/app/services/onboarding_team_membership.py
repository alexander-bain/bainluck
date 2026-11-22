"""Optional league membership for onboarding team search."""

import logging
from collections.abc import Sequence
from struct import Struct
from time import perf_counter, time

from redis import Redis
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Event, Sport, Team
from app.utils.request_cache import bounded_redis_call, get_shared_async_redis
from app.utils.search_fixture_dedup import INDIVIDUAL_SPORT_PREFIXES

logger = logging.getLogger(__name__)

_KEY = "bainluck:onboarding:team-league-members:2"
_SNAPSHOT_TTL_S = 7 * 24 * 60 * 60
_REBUILD_TASK = "app.tasks.refresh_onboarding_team_membership"
# One Redis string lets readers fetch metadata and up to 60 team entries
# atomically, without downloading the entire snapshot on each keystroke.
_HEADER = Struct(">qII")  # built_at in seconds, indexed teams, bytes
_MEMBER = Struct(">II")  # league ID, canonical team ID, indexed by team ID
_MAX_SNAPSHOT_BYTES = 1024 * 1024

MARKET_TEAM_SUFFIX = (
    r"(?i)\s*[-–—:]\s*(?:exact score|more markets|player props|total corners|"
    r"alternate (?:spread|total)s?|both teams to score)\s*$"
)
INDIVIDUAL_SPORT_KEY = (
    r"^(?:"
    + "|".join(prefix.rstrip("_") for prefix in INDIVIDUAL_SPORT_PREFIXES)
    + r")(?:_|$)"
)
EXCLUDED_LEAGUES = (
    "baseball_mlb_preseason",
    "soccer_copa_sudamericana",
    "soccer_copa_libertadores",
    "soccer_brazil_campeonato",
    "soccer_brazil_serie_b",
    "soccer_argentina_primera_division",
    "soccer_chile_primera_division",
    "soccer_colombia_primera_a",
)


def club_filters():
    return (
        ~Team.name.regexp_match(MARKET_TEAM_SUFFIX),
        ~Sport.key.regexp_match(INDIVIDUAL_SPORT_KEY),
        Sport.key.notin_(EXCLUDED_LEAGUES),
    )


_game_sides = select(
    Event.sport_id,
    func.unnest(
        array(
            [
                Event.home_team_id,
                case(
                    (
                        Event.away_team_id.is_distinct_from(Event.home_team_id),
                        Event.away_team_id,
                    )
                ),  # Count a game at most once for a team.
            ]
        )
    ).label("team_id"),
).subquery()
_game_counts = (
    select(_game_sides.c.sport_id, _game_sides.c.team_id, func.count().label("games"))
    .where(_game_sides.c.team_id.is_not(None))
    .group_by(_game_sides.c.sport_id, _game_sides.c.team_id)
    .subquery()
)
_TEAM_GAME_COUNTS = (
    select(Team.sport_id, Team.id, Team.espn_id, func.coalesce(_game_counts.c.games, 0))
    .join(Sport, Sport.id == Team.sport_id)
    .outerjoin(
        _game_counts,
        and_(
            _game_counts.c.sport_id == Team.sport_id, _game_counts.c.team_id == Team.id
        ),
    )
    .where(*club_filters())
)


def _member_offset(team_id: int) -> int:
    return _HEADER.size + (team_id - 1) * _MEMBER.size


async def onboarding_team_members(
    candidates: Sequence[tuple[int, int]],
) -> dict[tuple[int, int], int] | None:
    """Return canonical IDs for verified candidates, or None for a cache miss."""
    reads = ["GET", "i64", "0", "GET", "u32", "#2", "GET", "u32", "#3"]
    looked_up = []
    for league_id, team_id in candidates:
        offset = _member_offset(team_id)
        if team_id > 0 and offset < _MAX_SNAPSHOT_BYTES:
            pos = offset // 4
            reads.extend(("GET", "u32", f"#{pos}", "GET", "u32", f"#{pos + 1}"))
            looked_up.append((league_id, team_id))

    async def read():
        cache = await get_shared_async_redis()
        return await cache.execute_command("BITFIELD_RO", _KEY, *reads)

    result = await bounded_redis_call(read)
    # Redis returns zeros from BITFIELD_RO when the key is missing. The header
    # and every requested entry are from the very same read.
    values = result.value if result.is_ok else None
    built_at, count, size = (
        values[:3] if values and len(values) == 3 + 2 * len(looked_up) else (0, 0, 0)
    )
    present = built_at > 0 and _HEADER.size <= size <= _MAX_SNAPSHOT_BYTES
    logger.info(
        "Onboarding team membership snapshot present=%s age_s=%s members=%d bytes=%d redis=%s",
        present,
        max(0, int(time()) - built_at) if present else None,
        count if present else 0,
        size if present else 0,
        result.status,
    )
    if not present:
        return None
    return {
        pair: canonical_id
        for pair, stored_league, canonical_id in zip(
            looked_up, values[3::2], values[4::2]
        )
        if stored_league == pair[0] and canonical_id
    }


async def rebuild_onboarding_team_membership(db: AsyncSession, cache: Redis) -> dict:
    """Read league membership and publish it whole, under one rebuild lock."""
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

    rows = (await db.execute(_TEAM_GAME_COUNTS)).all()
    # The same ESPN ID in one league is one club. Pick the ID with more
    # games, even when only a different spelling of the club matched.
    preferred = {}
    for league_id, team_id, espn_id, games in rows:
        if espn_id and games:
            key = (league_id, espn_id)
            rank = (games, -team_id)
            preferred[key] = max(rank, preferred.get(key, rank))
    members = {}
    for league_id, team_id, espn_id, games in rows:
        winner = preferred.get((league_id, espn_id))
        if winner:
            members[team_id] = (league_id, -winner[1])
        elif games:
            members[team_id] = (league_id, team_id)

    if not members:
        logger.warning("Onboarding team membership rebuild found no eligible teams")
        return {"terminal": "skipped", "reason": "no_eligible_teams"}

    size = _HEADER.size + max(members) * _MEMBER.size
    if size > _MAX_SNAPSHOT_BYTES:
        logger.warning(
            "Onboarding team membership snapshot exceeds cap bytes=%d cap_bytes=%d",
            size,
            _MAX_SNAPSHOT_BYTES,
        )
        return {"terminal": "skipped", "reason": "snapshot_too_large", "bytes": size}

    payload = bytearray(size)
    _HEADER.pack_into(payload, 0, int(time()), len(members), size)
    for team_id, pair in members.items():
        _MEMBER.pack_into(payload, _member_offset(team_id), *pair)
    # SET replaces the old snapshot and its TTL in one operation.
    cache.set(_KEY, bytes(payload), ex=_SNAPSHOT_TTL_S)

    elapsed_ms = round((perf_counter() - started) * 1000, 1)
    logger.info(
        "Onboarding team membership rebuilt in %.1f ms (%d indexed teams, %d bytes)",
        elapsed_ms,
        len(members),
        size,
    )
    return {
        "terminal": "complete",
        "members": len(members),
        "bytes": size,
        "elapsed_ms": elapsed_ms,
    }
