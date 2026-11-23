"""Process-local projection of trusted venue aliases for onboarding search."""

import asyncio
import logging
import re
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter
from weakref import WeakKeyDictionary

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.models import Sport, TeamIdentityMapping
from app.services.database import build_connect_args

logger = logging.getLogger(__name__)

_REFRESH_INTERVAL_SECONDS = 15 * 60
_REFRESH_BUDGET_SECONDS = 5
_DATABASE_TIMEOUT_MS = 2_000
_ALIAS_QUERY = (
    select(TeamIdentityMapping.team_id, Sport.id, TeamIdentityMapping.source_name)
    .join(Sport, TeamIdentityMapping.sport_key == Sport.key)
    .where(
        TeamIdentityMapping.source == "odds_api",
        TeamIdentityMapping.source_name.is_not(None),
    )
)
_WORDS = re.compile(r"[^\W_]+")
TeamLeague = tuple[int, int]
AliasRow = tuple[int, int, str]


@dataclass(frozen=True)
class VenueAliases:
    by_phrase: dict[tuple[str, ...], set[TeamLeague]]
    by_word: dict[str, set[TeamLeague]]
    words: list[str]

    def exact(self, words: list[str]) -> set[TeamLeague]:
        return self.by_phrase.get(tuple(word.casefold() for word in words), set())

    def prefix(self, word: str) -> set[TeamLeague]:
        folded = word.casefold()
        start = bisect_left(self.words, folded)
        stop = bisect_left(self.words, folded + chr(0x10FFFF))
        return set().union(*(self.by_word[word] for word in self.words[start:stop]))


_EMPTY_ALIASES = VenueAliases({}, {}, [])
_by_bind: WeakKeyDictionary[Engine, VenueAliases] = WeakKeyDictionary()


def onboarding_venue_aliases(db: AsyncSession) -> VenueAliases:
    """Return the last complete copy without starting or awaiting a refresh."""
    return _by_bind.get(db.get_bind(), _EMPTY_ALIASES)


def _build_aliases(rows: list[AliasRow]) -> VenueAliases:
    by_phrase: dict[tuple[str, ...], set[TeamLeague]] = defaultdict(set)
    by_word: dict[str, set[TeamLeague]] = defaultdict(set)
    for team_id, league_id, source_name in rows:
        words = tuple(_WORDS.findall(source_name.casefold()))
        if words:
            by_phrase[words].add((team_id, league_id))
            for word in words:
                by_word[word].add((team_id, league_id))
    return VenueAliases(by_phrase, by_word, sorted(by_word))


def _alias_refresh_engine(search_engine: AsyncEngine) -> AsyncEngine:
    # A refresh uses one short-lived connection of its own. It cannot check
    # out a connection from the pool used by reader requests.
    args = build_connect_args(
        str(search_engine.url),
        statement_timeout_ms=_DATABASE_TIMEOUT_MS,
        lock_timeout_ms=250,
    )
    args["server_settings"]["default_transaction_read_only"] = "on"
    args["timeout"] = args["command_timeout"] = _DATABASE_TIMEOUT_MS / 1_000
    return create_async_engine(
        search_engine.url,
        connect_args=args,
        poolclass=NullPool,
        hide_parameters=True,
        execution_options=search_engine.get_execution_options(),
    )


async def _refresh_aliases(source: AsyncEngine, search_bind: Engine) -> None:
    started = perf_counter()
    rows: list[AliasRow] = []
    try:
        async with asyncio.timeout(_REFRESH_BUDGET_SECONDS):
            async with source.connect() as db, db.stream(_ALIAS_QUERY) as result:
                async for batch in result.tuples().partitions(512):
                    rows.extend(batch)
                    await asyncio.sleep(0)
            read_ms = (perf_counter() - started) * 1_000
            aliases = await asyncio.to_thread(_build_aliases, rows)
    except Exception as exc:
        logger.warning(
            "Onboarding venue alias refresh skipped reason=%s", type(exc).__name__
        )
        return

    if not aliases.words:
        logger.warning("Onboarding venue alias refresh skipped reason=empty")
        return

    _by_bind[search_bind] = aliases
    logger.info(
        "Onboarding venue aliases refreshed read_ms=%.1f total_ms=%.1f rows=%d",
        read_ms,
        (perf_counter() - started) * 1_000,
        len(rows),
    )


async def refresh_onboarding_venue_aliases(search_engine: AsyncEngine) -> None:
    """Own one refresh at a time for this web process."""
    source = _alias_refresh_engine(search_engine)
    try:
        while True:
            await _refresh_aliases(source, search_engine.sync_engine)
            await asyncio.sleep(_REFRESH_INTERVAL_SECONDS)
    finally:
        await source.dispose()
