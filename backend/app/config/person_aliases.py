"""Reviewed person-only search aliases for #11617.

These identify people, never an award, season, market, or probability. A caller
may use the returned full name at search's existing identity boundary, while
retaining the original query. No database writes or request-time provider call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ReviewedPersonAlias:
    alias: str
    canonical_name: str
    sport_key: str
    provider: str
    provider_id: str
    evidence_url: str


# NBA's player 1628983 page identifies DISPLAY_FIRST_LAST as this full name and
# uses "Follow SGA on Twitter (@shaiglalex) and Instagram (@shai)" in its bio.
# https://www.nba.com/player/1628983/shai-gilgeous-alexander
# Read 2026-10-25T06:09:20Z, body SHA256:
# d1e0bc0d29cc41b05d432315275b4a663168fd024a372d52560222b5374c605e
# Existing teams.roster_players independently anchors this full name to ESPN
# 4278073. The NBA page ID is NOT an ESPN ID; neither is a database entity ID.
# Team membership is deliberately absent: a trade must not rename the person.
REVIEWED_PERSON_ALIASES: tuple[ReviewedPersonAlias, ...] = (
    ReviewedPersonAlias(
        alias="sga",
        canonical_name="Shai Gilgeous-Alexander",
        sport_key="basketball_nba",
        provider="espn",
        provider_id="4278073",
        evidence_url="https://www.nba.com/player/1628983/shai-gilgeous-alexander",
    ),
)


def resolve_reviewed_person_alias(
    query: str,
    *,
    kind: str | None = None,
    sport_key: str | None = None,
    aliases: Sequence[ReviewedPersonAlias] | None = None,
) -> ReviewedPersonAlias | None:
    """Resolve a whole person-only alias, refusing known scope or identity conflicts.

    An unspecified scope permits only an unambiguous reviewed alias. An explicit
    non-person kind or different sport never inherits a person alias. Multiple
    matching records must agree on identity AND canonical spelling; their order,
    confidence, and IDs never choose a winner. Missing provenance refuses the
    candidate set, rather than silently discarding a possible competing claim.

    Case and outer whitespace are immaterial. Prefixes, substrings, punctuation
    variants and compound queries are not aliases: "SGA MVP" stays under the
    separate explicit-award intent contract. No generic acronym inference.
    """
    if kind not in (None, "person"):
        return None
    key = query.strip().casefold()
    if not key:
        return None
    records = REVIEWED_PERSON_ALIASES if aliases is None else aliases
    candidates = [
        record
        for record in records
        if record.alias.strip().casefold() == key
        and (sport_key is None or record.sport_key in ("", sport_key))
    ]
    if not candidates or any(
        not all(
            value.strip()
            for value in (
                record.canonical_name,
                record.sport_key,
                record.provider,
                record.provider_id,
                record.evidence_url,
            )
        )
        for record in candidates
    ):
        return None
    identities = {
        (record.sport_key, record.provider, record.provider_id, record.canonical_name)
        for record in candidates
    }
    return candidates[0] if len(identities) == 1 else None
