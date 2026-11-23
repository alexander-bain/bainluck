"""Process-local projection of trusted venue aliases for onboarding search."""

import asyncio
import re
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from time import monotonic
from weakref import WeakKeyDictionary

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Sport, TeamIdentityMapping

_MAX_AGE_SECONDS = 60
_WORDS = re.compile(r"[^\W_]+")
TeamLeague = tuple[int, int]


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


@dataclass
class _CachedVenueAliases:
    expires_at: float = 0
    aliases: VenueAliases | None = None
    refresh_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_by_bind: WeakKeyDictionary = WeakKeyDictionary()


async def onboarding_venue_aliases(db: AsyncSession) -> VenueAliases:
    """Read venue names once per minute rather than scanning them per keystroke."""
    bind = db.get_bind()
    entry = _by_bind.get(bind)
    if entry is None:
        entry = _CachedVenueAliases()
        _by_bind[bind] = entry
    if entry.aliases is not None and monotonic() < entry.expires_at:
        return entry.aliases

    async with entry.refresh_lock:
        if entry.aliases is not None and monotonic() < entry.expires_at:
            return entry.aliases
        rows = await db.execute(
            select(
                TeamIdentityMapping.team_id, Sport.id, TeamIdentityMapping.source_name
            )
            .join(Sport, TeamIdentityMapping.sport_key == Sport.key)
            .where(
                TeamIdentityMapping.source == "odds_api",
                TeamIdentityMapping.source_name.is_not(None),
            )
        )
        by_phrase: dict[tuple[str, ...], set[TeamLeague]] = defaultdict(set)
        by_word: dict[str, set[TeamLeague]] = defaultdict(set)
        for team_id, league_id, source_name in rows:
            words = tuple(_WORDS.findall(source_name.casefold()))
            if words:
                by_phrase[words].add((team_id, league_id))
                for word in words:
                    by_word[word].add((team_id, league_id))
        entry.aliases = VenueAliases(by_phrase, by_word, sorted(by_word))
        entry.expires_at = monotonic() + _MAX_AGE_SECONDS
        return entry.aliases
