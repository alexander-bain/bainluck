"""Verified game clubs shared by new outcome links and the fixture repair.

An event link is a restriction, including when its identity cannot be resolved.
It never grants permission to search the market's whole guessed category.
"""

from dataclasses import dataclass

from sqlalchemy import or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Sport, Team
from app.utils.sport_keys import same_sport_same_gender, sport_family_key
from app.utils.team_linking import (
    _normalize_name, _normalized_names, match_outcome_to_roster, match_outcome_to_team,
)


@dataclass(frozen=True)
class FixtureClubs:
    event_id: int
    teams: tuple[dict, ...] = ()
    event_identity: tuple = ()
    refusal: str | None = None

    @property
    def ids(self) -> frozenset[int]:
        return frozenset(team["id"] for team in self.teams)

    @property
    def rosters(self) -> dict[int, list[str]]:
        result = {}
        for team in self.teams:
            roster = team["roster_players"]
            if not isinstance(roster, list):
                continue
            players = [item.get("name") if isinstance(item, dict) else item for item in roster]
            players = [name for name in players if isinstance(name, str) and len(name) >= 4]
            if players:
                result[team["id"]] = players
        return result

    def match(self, name: str) -> tuple[int | None, str | None]:
        if self.refusal:
            return None, self.refusal
        by_name = match_outcome_to_team(name, list(self.teams))
        if by_name is not None:
            return by_name, "name"
        by_roster = match_outcome_to_roster(name, self.rosters)
        return by_roster, "roster" if by_roster is not None else None


async def load_fixture_clubs(
    session: AsyncSession, event_ids: set[int]
) -> dict[int, FixtureClubs]:
    """Resolve both clubs in two bounded reads, returning only plain values.

    An explicit club FK may name a domestic club playing a cup fixture. It must
    have a known, compatible sport and gender, with a matching name or alias.
    A missing FK needs a unique exact
    name in the fixture's competition; missing/ambiguous sides refuse the whole
    set. No category, nickname or LLM inference establishes fixture identity.
    """
    if not event_ids:
        return {}
    events = (await session.execute(
        select(
            Event.id, Event.sport_id, Event.home_team_id, Event.away_team_id,
            Event.home_team_name, Event.away_team_name, Sport.key.label("sport_key"),
        ).outerjoin(Sport, Sport.id == Event.sport_id).where(Event.id.in_(event_ids))
    )).all()
    explicit_ids = set()
    named_sides = set()
    for event in events:
        for side in ("home", "away"):
            team_id = getattr(event, f"{side}_team_id")
            name = getattr(event, f"{side}_team_name")
            if team_id is not None:
                explicit_ids.add(team_id)
            elif name and event.sport_id is not None:
                named_sides.add((event.sport_id, name))
    filters = []
    if explicit_ids:
        filters.append(Team.id.in_(explicit_ids))
    if named_sides:
        filters.append(tuple_(Team.sport_id, Team.name).in_(named_sides))
    team_rows = (await session.execute(
        select(
            Team.id, Team.sport_id, Team.name, Team.alternate_names,
            Team.roster_players, Sport.key.label("sport_key"),
        ).outerjoin(Sport, Sport.id == Team.sport_id).where(or_(*filters))
    )).all() if filters else []
    teams = {row.id: dict(row._mapping) for row in team_rows}
    by_name: dict[tuple, list[dict]] = {}
    for team in teams.values():
        by_name.setdefault((team["sport_id"], team["name"]), []).append(team)

    result = {event_id: FixtureClubs(event_id, refusal="missing_event") for event_id in event_ids}
    for event in events:
        identity = tuple(event)
        refusal = None
        chosen = []
        if not sport_family_key(event.sport_key):
            refusal = "unknown_fixture_sport"
        else:
            for side in ("home", "away"):
                team_id = getattr(event, f"{side}_team_id")
                name = getattr(event, f"{side}_team_name")
                candidates = (
                    [teams[team_id]] if team_id in teams else []
                ) if team_id is not None else by_name.get((event.sport_id, name), [])
                if len(candidates) != 1:
                    refusal = f"{side}_club_ambiguous" if candidates else f"{side}_club_unknown"
                    break
                team = candidates[0]
                if not sport_family_key(team["sport_key"]):
                    refusal = f"{side}_club_sport_unknown"
                    break
                if not same_sport_same_gender(team["sport_key"], event.sport_key):
                    refusal = f"{side}_club_sport_or_gender_mismatch"
                    break
                if not name or _normalize_name(name) not in _normalized_names(team):
                    refusal = f"{side}_club_name_mismatch"
                    break
                chosen.append(team)
            if not refusal and len({team["id"] for team in chosen}) != 2:
                refusal = "same_club_on_both_sides"
        result[event.id] = FixtureClubs(
            event.id, tuple(chosen) if not refusal else (), identity, refusal,
        )
    return result
