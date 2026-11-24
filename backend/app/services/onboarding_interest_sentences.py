"""Resolve first-run interests against existing Bain Luck identities."""

from __future__ import annotations

import asyncio
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Literal

from fastapi import HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.major_team_search import MAJOR_TEAM_QUERY_ALIASES
from app.config.team_aliases import CURATED_TEAM_ALIASES
from app.models import Entity, EntityAlias, Sport, Team
from app.services.entity_registry import ALIAS_CANONICAL, normalize_alias
from app.services.onboarding_team_membership import (
    club_filters,
    onboarding_team_members,
)
from app.utils.competition_identity import load_competitions
from app.utils.sport_keys import SPORT_HIERARCHY
from app.utils.static_divisions import lookup_division

_CATALOG = (
    Path(__file__).resolve().parents[2] / "data" / "onboarding" / "interest-catalog.tsv"
)
_MAX_BODY_BYTES = 8192
_MAX_WORDS = 80
_MAX_MENTIONS = 16
_MAX_SPAN_WORDS = 7
_RESOLVE_SECONDS = 4.5
_SPORT_KINDS = frozenset(("team", "school", "city", "sport", "person", "person-id"))
_SHORT_TEAM_PLACES = {
    "Kansas City ": "KC ",
    "Las Vegas ": "Vegas ",
    "Los Angeles ": "LA ",
    "New York ": "NY ",
    "Philadelphia ": "Philly ",
    "San Francisco ": "SF ",
}

_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\w)(?:\+|\()?\d(?:[\s().-]*\d){6,14}(?!\w)")
_SECRET = re.compile(
    r"\b(?:password|passcode|secret|ssn|api[ _-]?key|access[ _-]?token)\s*[:=]\s*"
    r"""(?:"[^"]*"|'[^']*'|[^\s,;]+)"""
    r"|\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{15,}|"
    r"\d{3}-\d{2}-\d{4})\b",
    re.IGNORECASE,
)
# Accept attributes and whitespace on closing tags when discarding opaque text.
_SCRIPT = re.compile(
    r"<(?P<tag>script|style)\b[^>]*>.*?</(?P=tag)(?=[\s/>])[^>]*>", re.I | re.S
)
_MARKUP = re.compile(r"<[^>]*>")
_ABBREVIATION = re.compile(r"\b(st|mt|jr)\.(?=\s)|\bd\.c\.", re.I)
_CLAUSE = re.compile(r"[!?;\n]+|\.(?=\s|$)|\b(?:but|however|instead|just)\b", re.I)
_DIRECTIVE = re.compile(
    r"^(?:(?:please|also|now)\s+)*(?:ignore (?:your|all|the) (?:prior |previous )?instructions"
    r"|return every (?:team|item|chip)|(?:add|make|create) a (?:new )?chip|"
    r"(?:drop|delete|select|update)\s+(?:table|from|database))\b"
)
_NO_SPORTS = re.compile(
    r"\b(?:no sports|not a sports fan|(?:dont|don t|do not) care about sports)\b"
)
_NO_POLITICS = re.compile(
    r"\b(?:no politics|not interested in politics|not a politics fan)\b"
)
_NEGATE = (
    ("not",),
    ("no",),
    ("never",),
    ("except",),
    ("without",),
    ("hate",),
    ("dislike",),
    ("f", "the"),
    ("fuck",),
    ("screw",),
    ("neither",),
    ("nor",),
    ("don", "t"),
    ("dont",),
    ("do", "not"),
    ("doesn", "t"),
    ("does", "not"),
    ("skip",),
    ("exclude",),
    ("avoid",),
    ("whoever", "is", "playing"),
    ("against",),
)
_POST_NEGATE = (("is", "not", "for", "me"), ("is", "not", "my", "thing"))
_NO_EDGE = frozenset(
    "a an and are at about but for from i in is of on or that the to was will with".split()
)


class InterestChip(BaseModel):
    id: int | str
    kind: Literal["team", "school", "city", "sport", "person", "topic"]
    name: str
    selected: bool = True
    ambiguity_group: str | None = None
    team_ids: list[int] | None = None
    sport_key: str | None = None


@dataclass(frozen=True)
class Target:
    kind: str
    name: str
    selector: str


@dataclass(frozen=True)
class Mention:
    options: tuple[Target, ...]
    excluded: bool


def _add_alias(
    aliases: dict[str, list[Target]], target: Target, names: Iterable[str]
) -> None:
    for name in names:
        key = normalize_alias(name)
        if key and target not in aliases[key]:
            aliases[key].append(target)


def _read_aliases() -> dict[str, list[Target]]:
    aliases: dict[str, list[Target]] = defaultdict(list)
    for (sport, name), versions in MAJOR_TEAM_QUERY_ALIASES.items():
        short_names = [
            short + name[len(place) :]
            for place, short in _SHORT_TEAM_PLACES.items()
            if name.startswith(place)
        ]
        _add_alias(
            aliases, Target("team", name, sport), (name, *versions, *short_names)
        )
        if sport == "americanfootball_nfl":
            _, division = lookup_division(sport, name)
            if division:
                _add_alias(aliases, Target("division-team", name, sport), (division,))
    for (sport, name), nicknames in CURATED_TEAM_ALIASES.items():
        _add_alias(aliases, Target("team", name, sport), nicknames)
    with _CATALOG.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            target = Target(row["kind"], row["name"], row["selector"])
            _add_alias(
                aliases, target, (target.name, *(row["aliases"] or "").split("|"))
            )
    return aliases


def _clean_text(sentence: str) -> str:
    sentence = _SCRIPT.sub(" ", sentence)
    sentence = _MARKUP.sub(" ", sentence)
    sentence = _EMAIL.sub(" ", sentence)
    sentence = _PHONE.sub(" ", sentence)
    sentence = _SECRET.sub(" ", sentence)
    return _ABBREVIATION.sub(lambda match: match.group(1) or "dc", sentence)


def _parts(sentence: str) -> list[tuple[str, ...]]:
    parts = []
    for clause in _CLAUSE.split(sentence):
        text = normalize_alias(clause)
        if text and not _DIRECTIVE.match(text):
            parts.append(tuple(text.split()))
    return parts


def _candidate_spans(
    parts: list[tuple[str, ...]], known: dict[str, list[Target]]
) -> set[str]:
    phrases = set()
    for words in parts:
        for start, word in enumerate(words):
            if word in _NO_EDGE:
                continue
            for end in range(start + 2, min(len(words), start + _MAX_SPAN_WORDS) + 1):
                if words[end - 1] not in _NO_EDGE:
                    phrase = " ".join(words[start:end])
                    if phrase not in known:
                        phrases.add(phrase)
    return phrases


async def _registry_matches(
    db: AsyncSession, phrases: set[str], person_names: set[str]
) -> dict[str, list[Target]]:
    wanted = phrases | person_names
    if not wanted:
        return {}
    rows = await db.execute(
        select(
            EntityAlias.alias_norm,
            Entity.id,
            Entity.kind,
            Entity.canonical_name,
            Entity.sport_key,
        )
        .join(Entity, EntityAlias.entity_id == Entity.id)
        .where(
            EntityAlias.alias_norm.in_(sorted(wanted)),
            EntityAlias.alias_type == ALIAS_CANONICAL,
            Entity.kind.in_(("team", "person")),
            Entity.confidence >= 0.95,
        )
    )
    grouped: dict[str, set[Target]] = defaultdict(set)
    for phrase, entity_id, kind, name, league in rows:
        if kind == "person":
            grouped[phrase].add(Target("person-id", name, str(entity_id)))
        elif league:
            grouped[phrase].add(Target("team", name, league))
    return {
        phrase: sorted(
            targets, key=lambda target: (target.kind, target.name, target.selector)
        )
        for phrase, targets in grouped.items()
    }


def _scan(words: tuple[str, ...], aliases: dict[str, list[Target]]) -> list[Mention]:
    mentions = []
    excluded = False
    start = 0
    while start < len(words):
        negation = next(
            (cue for cue in _NEGATE if words[start : start + len(cue)] == cue), None
        )
        if negation is not None:
            start += len(negation)
            excluded = True
            continue
        last = min(len(words), start + _MAX_SPAN_WORDS)
        for end in range(last, start, -1):
            targets = aliases.get(" ".join(words[start:end]))
            if targets:
                after = any(words[end : end + len(cue)] == cue for cue in _POST_NEGATE)
                if all(target.kind == "division-team" for target in targets):
                    mentions.extend(
                        Mention(
                            (Target("team", target.name, target.selector),),
                            excluded or after,
                        )
                        for target in targets
                    )
                else:
                    mentions.append(Mention(tuple(targets), excluded or after))
                start = end
                break
        else:
            start += 1
    return mentions


def _places(target: Target) -> set[str]:
    if target.kind not in {"team", "school", "city"}:
        return set()
    words = normalize_alias(target.name).split()
    prefixes = {" ".join(words[:size]) for size in (1, 2) if size < len(words)}
    if target.kind != "team":
        prefixes.add(" ".join(words))
    return prefixes


def _narrow(
    mentions: list[Mention], *, sports_excluded: bool, politics_excluded: bool
) -> dict[Target, str | None]:
    exclusions = {
        target for mention in mentions if mention.excluded for target in mention.options
    }
    certain_places = set().union(
        *(
            _places(mention.options[0])
            for mention in mentions
            if not mention.excluded and len(mention.options) == 1
        )
    )
    selected: dict[Target, str | None] = {}
    for index, mention in enumerate(mentions, 1):
        if mention.excluded:
            continue
        options = [
            target
            for target in mention.options
            if target.kind != "unsupported"
            and target not in exclusions
            and not (sports_excluded and target.kind in _SPORT_KINDS)
            and not (
                politics_excluded
                and target.kind == "topic"
                and target.selector.startswith("politics")
            )
        ]
        school_teams = {
            option.selector.casefold() for option in options if option.kind == "school"
        }
        options = [
            option
            for option in options
            if option.kind != "team" or option.name.casefold() not in school_teams
        ]
        # Prefer the already identified metro when an alias has several clubs.
        if len(options) > 1:
            local = [target for target in options if _places(target) & certain_places]
            if local:
                options = local
        if len(options) > 1 and len(mentions) > 1:
            continue
        group = str(index) if len(options) > 1 else None
        for target in options:
            if target not in selected or group is None:
                selected[target] = group
    return selected


async def _teams(
    db: AsyncSession, targets: Iterable[Target]
) -> dict[tuple[str, str], int]:
    names = {
        (target.name if target.kind == "team" else target.selector).lower()
        for target in targets
        if target.kind in {"team", "school"}
    }
    if not names:
        return {}
    rows = (
        await db.execute(
            select(Team.id, Team.sport_id, Team.name, Sport.key)
            .join(Sport, Sport.id == Team.sport_id)
            .where(func.lower(Team.name).in_(sorted(names)), *club_filters())
            .order_by(Team.id)
        )
    ).all()
    membership = await onboarding_team_members(
        [(sport_id, team_id) for team_id, sport_id, _, _ in rows]
    )
    result = {}
    for team_id, sport_id, name, league in rows:
        if membership is not None and membership.get((sport_id, team_id)) != team_id:
            continue
        result.setdefault((name.lower(), league), team_id)
    return result


async def _sports(db: AsyncSession, targets: Iterable[Target]) -> dict[str, int | str]:
    keys = sorted({target.selector for target in targets if target.kind == "sport"})
    if not keys:
        return {}
    # A league or tournament can have its own route without an Odds API Sport row.
    registered = set(SPORT_HIERARCHY)
    for sport in SPORT_HIERARCHY.values():
        for league in sport["leagues"]:
            registered.update(league["sport_keys"])
    if any(key.startswith("event:") for key in keys):
        competitions = await asyncio.to_thread(load_competitions)
        registered.update(
            key for row in competitions if (key := row.get("standing_concept_key"))
        )
    resolved: dict[str, int | str] = {key: key for key in keys if key in registered}
    resolved.update(
        (
            await db.execute(
                select(Sport.key, Sport.id).where(Sport.key.in_(keys), Sport.active)
            )
        ).all()
    )
    return resolved


async def resolve_interests(
    sentence: str,
    db: AsyncSession,
    read_city: Callable[[str], Awaitable[list[int]]],
) -> list[InterestChip]:
    cleaned = _clean_text(sentence)
    parts = _parts(cleaned)
    if not parts:
        return []
    if sum(map(len, parts)) > _MAX_WORDS:
        raise HTTPException(
            422, detail={"code": "sentence_too_long", "fallback": "search"}
        )

    async with asyncio.timeout(_RESOLVE_SECONDS):
        aliases = await asyncio.to_thread(_read_aliases)
        normalized = normalize_alias(cleaned)
        if normalized != "la" and not re.search(r"\bLA\b", cleaned):
            # A lowercase article in "de la Formule 1" names no US city.
            aliases.pop("la", None)
        # Topic use of a word such as "hurricanes" takes precedence over a
        # bare club nickname. A full name still identifies the club.
        for name, options in tuple(aliases.items()):
            topics = [target for target in options if target.kind == "topic"]
            if topics:
                aliases[name] = topics
        initial_mentions = [
            mention for part in parts for mention in _scan(part, aliases)
        ]
        person_names = {
            normalize_alias(target.selector)
            for mention in initial_mentions
            for target in mention.options
            if target.kind == "person"
        }
        registry = await _registry_matches(
            db, _candidate_spans(parts, aliases), person_names
        )
        for name, matches in registry.items():
            aliases.setdefault(name, matches)
        mentions = [mention for part in parts for mention in _scan(part, aliases)]
        targets = _narrow(
            mentions,
            sports_excluded=bool(_NO_SPORTS.search(normalized)),
            politics_excluded=bool(_NO_POLITICS.search(normalized)),
        )
        if len(targets) > _MAX_MENTIONS:
            raise HTTPException(
                422, detail={"code": "too_many_interests", "fallback": "search"}
            )

        excluded_teams = {
            target
            for mention in mentions
            if mention.excluded
            for target in mention.options
            if target.kind == "team"
        }
        teams = await _teams(db, set(targets) | excluded_teams)
        excluded_ids = {
            team_id
            for target in excluded_teams
            if (team_id := teams.get((target.name.lower(), target.selector)))
            is not None
        }
        sports = await _sports(db, targets)
        chips: dict[tuple[str, int | str], InterestChip] = {}
        for target, ambiguity_group in targets.items():
            chip = await _resolve(
                target,
                ambiguity_group,
                teams,
                sports,
                registry,
                read_city,
                excluded_ids,
            )
            if chip is not None:
                chips.setdefault((chip.kind, chip.id), chip)
        return list(chips.values())


async def _resolve(
    target: Target,
    ambiguity_group: str | None,
    teams: dict[tuple[str, str], int],
    sports: dict[str, int | str],
    registry: dict[str, list[Target]],
    read_city: Callable[[str], Awaitable[list[int]]],
    excluded_ids: set[int],
) -> InterestChip | None:
    team_ids = None
    kind = target.kind
    name = target.name
    identifier: int | str | None = target.selector
    if kind == "team":
        identifier = teams.get((name.lower(), target.selector))
    elif kind == "school":
        team_ids = sorted(
            {
                team_id
                for (stored, league), team_id in teams.items()
                if stored == target.selector.lower()
                and "_ncaa" in league
                and team_id not in excluded_ids
            }
        )
        identifier = team_ids[0] if team_ids else None
    elif kind == "city":
        team_ids = [
            team_id
            for team_id in dict.fromkeys(await read_city(target.selector))
            if team_id not in excluded_ids
        ]
        identifier = target.selector.replace(" ", "-") if team_ids else None
    elif kind == "sport":
        identifier = sports.get(target.selector)
    elif kind == "person":
        hits = [
            item
            for item in registry.get(normalize_alias(target.selector), ())
            if item.kind == "person-id"
        ]
        if len(hits) != 1:
            return None
        identifier, name = int(hits[0].selector), hits[0].name
    elif kind == "person-id":
        identifier, kind = int(target.selector), "person"

    if identifier is None:
        return None
    return InterestChip(
        id=identifier,
        kind=kind,
        name=name,
        selected=ambiguity_group is None,
        ambiguity_group=ambiguity_group,
        team_ids=team_ids,
        sport_key=target.selector if kind == "team" else None,
    )


async def read_sentence(request: Request) -> str:
    """Bound request size and keep raw input out of validation error bodies."""
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise HTTPException(
                413, detail={"code": "sentence_too_long", "fallback": "search"}
            )
        body.extend(chunk)
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        data = None
    sentence = data.get("text") if isinstance(data, dict) else None
    if not isinstance(sentence, str):
        raise HTTPException(
            422, detail={"code": "invalid_sentence", "fallback": "search"}
        )
    return sentence
