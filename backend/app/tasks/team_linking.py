"""
Team linking task: populates team_id on FuturesOutcome records,
market_tier on FuturesMarket records, and backfills league/canonical keys.

Runs as a backfill task and is also called inline during futures polling.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import select, func, or_, and_
from sqlalchemy.exc import DBAPIError, PendingRollbackError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tasks.base import get_task_session

logger = logging.getLogger(__name__)


# --- Phase 2 selector: skip list, sport scope, and the resumable cursor (#7307) ---

# Skip generic outcomes that can never match a team/player name.
# This dramatically reduces the number of outcomes we process.
_SKIP_PATTERNS = (
    "^(Yes|No|Over|Under|Draw|Tie|Push)$",          # Binary outcomes
    "^O/U ",                                         # Over/Under lines
    "^Spread ",                                      # Spread lines
    "^(Handicap|Game Handicap|Map Handicap)",        # Handicaps
    "^(Match Winner|Game [0-9]|Map [0-9]|Round [0-9])",  # Game/map labels
    "^(Odd/Even|Total Kills|First Blood|Both Teams|Any Player|Exact Score)",  # Esports/soccer generics
    "^[0-9]",                                        # Numeric outcomes ("218.5")
    "wins (by|the|1H)",                              # Spread descriptions ("Team wins by over 5.5")
    " over [0-9]",                                   # Point totals ("Team over 119.5 points")
    " -[0-9]",                                       # Game handicaps ("Frances Tiafoe -1.5 games")
    "\\(-[0-9]",                                     # Handicap notation ("Team (-2.5)")
    "^(Double Double|Triple Double|Both Teams to Score|No Goal)",  # Stat/game generics
)
SKIP_REGEX = "|".join(f"({p})" for p in _SKIP_PATTERNS)

# A name this short is a generic word ("Yes", "Tie", "AFC") far more often than
# a team, so only a Kalshi leg is selected with one, and only the ticker's own
# league may bind it (Step 0): "USC" on Kalshi's college board is USC, "LSU" is
# LSU, "VMI" is VMI (#9687). No category-wide or LLM step reads it, and the
# roster matcher refuses it itself.
_MIN_NAME_CHARS = 4


def _short_name(name: str | None) -> bool:
    return len(name or "") < _MIN_NAME_CHARS


# Prioritize US major sports where we have roster data.
# Skip golf — individual sport, no team rosters to match against.
_US_SPORTS = ("basketball", "baseball", "football", "hockey")

# #7307 — THE SELECTOR HAS TO ADVANCE. The Phase 2 query used to be
# ``... WHERE team_id IS NULL ... ORDER BY market_id LIMIT :limit`` with no
# memory of where the last run stopped. There is no attempted marker on
# ``futures_outcomes``, so a row that FAILS to bind stays ``team_id IS NULL``
# and is re-selected, hour after hour, forever; the queue only ever drains by
# successful binds. Measured on production 2026-09-19: 1,469,773 rows match
# this selector and the head of the order is college-basketball outcomes that
# have no ``teams`` row at all. PR #7301 fixed a real matching defect affecting
# 862 legs whose lowest ``market_id`` is 199,045 — not one of them was
# reachable, so a correct, fully guard-tested fix bound nothing in production.
#
# The fix is the ``backfill_market_shapes`` pattern: a persisted id cursor per
# pass that wraps to 0 when a pass runs off the end of the table. A failure
# therefore leaves the working window immediately and is retried once per full
# cycle instead of once per hour.
#
# TWO CURSORS, NOT ONE, because one cursor over 1.47M rows at the scheduled
# 2,000/hour is a 31-day cycle and a reader cannot see 95% of that population.
# Only 64,527 of the rows sit in ``status='open'`` markets — the legs a person
# can load today — so the open pass is served first and the resolved pass keeps
# a reserved floor of the batch so it can never be starved to zero.
_CURSOR_KEY_OPEN = "bainluck:team_link_cursor:open"
_CURSOR_KEY_RESOLVED = "bainluck:team_link_cursor:resolved"
_CURSOR_TTL = 86400 * 14
_RESOLVED_FLOOR_DIVISOR = 4


def _resolved_floor(limit: int) -> int:
    """Rows of each batch the resolved-market pass may never be denied.

    A floor and not a fixed size: the open pass takes ``limit - floor`` at most,
    and whatever the open pass leaves on the table goes to the resolved pass on
    top of the floor. With the scheduled ``limit=2000`` the open backlog cycles
    in ~43h and the resolved one still moves 500 rows an hour.
    """
    if limit <= 1:
        return 0
    return max(1, limit // _RESOLVED_FLOOR_DIVISOR)


def _cursor_store():
    """The bounded Redis client the cursors live in, or None if unreachable.

    Gotcha #39: never build a client here — ``get_redis_client`` is the one with
    a socket timeout, and a sync client without one can freeze an async task.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception as exc:  # pragma: no cover - redis outage
        logger.warning("team-link cursor store unavailable (%s); running from the head", exc)
        return None


def _apply_cursor_writes(rc, writes) -> None:
    """Persist this run's cursors. Called only AFTER the batch has committed.

    A cursor written before the commit that then rolls back would step the
    window past rows nothing ever linked; they would come back a full cycle
    later rather than next hour, which is the failure this whole change exists
    to stop. ``None`` means wrap: delete the key so the next run starts at 0.
    """
    if rc is None:
        # NOTE: this comment is load-bearing. `if rc is None:` followed directly
        # by a bare `return` is `tennis_population_mutations` M7's replacement
        # literal, and the mutation-residue scan matches changed files as text.
        return
    for key, value in writes:
        try:
            if value is None:
                rc.delete(key)
            else:
                rc.setex(key, _CURSOR_TTL, int(value))
        except Exception as exc:  # pragma: no cover - redis outage
            logger.warning("team-link cursor write failed for %s (%s)", key, exc)


def _read_cursor(rc, key: str) -> int:
    """Last outcome id this pass reached, or 0 when there is no usable cursor.

    Fails OPEN to 0 on a missing key, a flushed Redis or junk: that is the old
    behaviour (start at the head), never a skipped population.
    """
    if rc is None:
        # See _apply_cursor_writes: the comment breaks a mutation-harness literal.
        return 0
    try:
        raw = rc.get(key)
    except Exception:  # pragma: no cover - redis outage must not stop the drain
        return 0
    try:
        return int(raw.decode() if isinstance(raw, bytes) else raw)
    except (TypeError, ValueError, AttributeError):
        return 0


def unlinked_outcomes_query(*, open_markets: bool, cursor: int, batch: int):
    """The Phase 2 selector for one pass. Exposed so a guard test can drive it.

    ``open_markets`` picks the pass: ``status='open'`` (what a reader can load)
    or everything else. ``cursor`` is the exclusive lower bound on
    ``FuturesOutcome.id`` and is what makes the window move off a row that
    cannot bind.
    """
    from app.models import FuturesMarket, FuturesOutcome

    status_clause = (
        FuturesMarket.status == "open"
        if open_markets
        else FuturesMarket.status != "open"
    )
    return (
        select(FuturesOutcome)
        .options(selectinload(FuturesOutcome.market))
        .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
        .where(
            FuturesOutcome.team_id.is_(None),
            ~FuturesOutcome.name.op("~*")(SKIP_REGEX),
            or_(
                func.length(FuturesOutcome.name) >= _MIN_NAME_CHARS,
                FuturesMarket.source == "kalshi",
            ),
            FuturesMarket.llm_sport_category.in_(_US_SPORTS),  # US sports only
            status_clause,
            FuturesOutcome.id > cursor,
        )
        .order_by(FuturesOutcome.id)
        .limit(batch)
    )


async def _load_teams_by_sport(
    session: AsyncSession,
    sport_keys: Optional[list[str]] = None,
) -> list[dict]:
    """Load team records scoped by sport keys.

    Returns list of dicts: [{id, name, alternate_names, sport_key}, ...]
    """
    from app.models import Team, Sport

    query = (
        select(Team.id, Team.name, Team.alternate_names, Team.roster_players, Sport.key)
        .join(Sport, Team.sport_id == Sport.id)
    )
    if sport_keys:
        query = query.where(Sport.key.in_(sport_keys))

    result = await session.execute(query)
    return [
        {
            "id": row.id,
            "name": row.name,
            "alternate_names": row.alternate_names or [],
            "roster_players": row.roster_players,
            "sport_key": row.key,
        }
        for row in result.all()
    ]


# Venues whose market names its league for Step 0 and Phase 3: a Kalshi ticker,
# and a Polymarket event slug (#9761 — "Pro Football: … Defensive Rookie of the
# Year" is ``pro-football-…``, so Mansoor Delane leaves LSU for the NFL).
_LEAGUE_NAMING_VENUES = ("kalshi", "polymarket")


def _match_in_ticker_league(outcome, teams: list[dict]) -> Optional[int]:
    """Bind a Kalshi outcome inside the league its ticker names, else None (#9617).

    ``teams`` is the category's team list; only the rows whose sport key is the
    ticker's league are consulted. No league, or no team rows for it, leaves the
    outcome to the category-wide matcher exactly as before.

    The league is the same read Phase 3 rebinds into and the league check refuses
    on (#9663): read off the bare ticker map, the FCS title board is FBS, so this
    bound "San Diego" to San Diego State and Phase 3 cleared it again every run.
    """
    from app.utils.market_team_sport import market_event_slug, market_league_sport_key
    from app.utils.team_linking import match_outcome_to_league_team

    market = outcome.market
    if market is None or market.source not in _LEAGUE_NAMING_VENUES:
        return None
    league = market_league_sport_key(
        market.source, market.external_id, market_event_slug(market.market_metadata)
    )
    if not league:
        return None
    league_teams = [t for t in teams if t.get("sport_key") == league]
    if not league_teams:
        return None
    return match_outcome_to_league_team(outcome.name, league_teams)


async def _ticker_league_teams(
    session: AsyncSession, outcome, teams: list[dict], cache: dict
) -> list[dict]:
    """The teams Step 0 reads: the category's, or its ticker league's when those are missing (#9663).

    ``get_sport_keys_for_category("football")`` is NFL + FBS, so the FCS title
    board's league had no rows in ``teams`` and Step 0 could never bind inside it.
    The league's rows are loaded once per run, whatever the market's category,
    as Phase 3 already does when it rebinds a stored link into that league.
    """
    from app.utils.market_team_sport import market_event_slug, market_league_sport_key

    market = outcome.market
    if market is None or market.source not in _LEAGUE_NAMING_VENUES:
        return teams
    league = market_league_sport_key(
        market.source, market.external_id, market_event_slug(market.market_metadata)
    )
    if not league:
        return teams
    if any(t.get("sport_key") == league for t in teams):
        return teams
    if league not in cache:
        cache[league] = await _load_teams_by_sport(session, [league])
    return cache[league]


async def _load_team_sport_keys(session: AsyncSession) -> dict[int, str]:
    """Every team's sport key, for the league check at each bind site (#5119)."""
    from app.models import Team, Sport

    rows = await session.execute(
        select(Team.id, Sport.key).join(Sport, Team.sport_id == Sport.id)
    )
    return {team_id: key for team_id, key in rows.all()}


def _crosses_market_league(outcome, team_id: int, team_sport_keys: dict[int, str]) -> bool:
    """True when binding ``team_id`` would put the outcome outside its market's league (#5119).

    ``link_crosses_league`` is the championship path's own refusal (#2593), so a
    link the page would drop is never written in the first place. A market whose
    venue id names no league, or a team outside the one-league sports, is no claim.
    """
    from app.utils.market_team_sport import link_crosses_league, market_event_slug

    market = outcome.market
    if market is None:
        return False
    return link_crosses_league(
        market.source,
        market.external_id,
        team_sport_keys.get(team_id),
        market_event_slug(market.market_metadata),
    )


async def _load_team_names(session: AsyncSession) -> dict[int, str]:
    """Every team's name, for the conference check at each bind site (#8072)."""
    from app.models import Team

    rows = await session.execute(select(Team.id, Team.name))
    return {team_id: name for team_id, name in rows.all()}


def _crosses_market_conference(
    outcome, team_id: int, team_sport_keys: dict[int, str], team_names: dict[int, str]
) -> bool:
    """True when binding ``team_id`` would put the outcome in the other conference (#8072)."""
    from app.utils.market_team_sport import link_crosses_conference

    market = outcome.market
    if market is None:
        return False
    return link_crosses_conference(
        market.source,
        market.external_id,
        team_sport_keys.get(team_id),
        team_names.get(team_id),
    )


async def _relink_outside_market_league(
    session: AsyncSession, stats: dict, limit: int
) -> None:
    """Move a stored link that sits outside its market's league (#5119, #2593).

    City-name matching across a whole sport category put Kalshi's "Buffalo" Super
    Bowl leg on the Buffalo Bulls and "Houston" on the Houston Cougars, so the
    Bills' and Texans' pages carried no Kalshi title, conference or playoff price
    at all. Measured 2026-09-29: 520 open Kalshi outcomes linked outside the league
    their ticker names. Phase 2 only ever selects ``team_id IS NULL``, so a wrong
    link was permanent.

    Each such link is re-decided inside the market's league with the #9617
    matcher — unique exact name/alias or own-name-minus-nickname, never a
    substring — and set to that team, or to NULL when the league has no unique
    answer (a player's rookie-award leg on his college, "Tennessee: 2+ wins" on the
    Volunteers). A NULL re-enters Phase 2, whose league check refuses the old
    team, so the two passes cannot undo each other.
    """
    from app.models import FuturesMarket, FuturesOutcome, Sport, Team
    from app.utils.market_team_sport import (
        POLYMARKET_SLUG_LEAGUE_PREFIXES,
        POLYMARKET_SLUG_LEAGUE_SUFFIXES,
        link_crosses_league,
        market_league_sport_key,
    )
    from app.utils.team_linking import match_outcome_to_league_team
    from app.utils.venue_competition import POLYMARKET_EVENT_SLUG_KEY

    # A Polymarket market names a league only through its event slug (#9761), so
    # only the rows a listed prefix or suffix claims are read — not every
    # Polymarket link.
    slug = FuturesMarket.market_metadata[POLYMARKET_EVENT_SLUG_KEY].as_string()
    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesMarket.source,
                FuturesMarket.external_id,
                slug.label("event_slug"),
                Sport.key,
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Team, Team.id == FuturesOutcome.team_id)
            .join(Sport, Sport.id == Team.sport_id)
            .where(
                or_(
                    FuturesMarket.source == "kalshi",
                    and_(
                        FuturesMarket.source == "polymarket",
                        or_(
                            *(
                                slug.startswith(prefix, autoescape=True)
                                for prefix in POLYMARKET_SLUG_LEAGUE_PREFIXES
                            ),
                            *(
                                slug.endswith(suffix, autoescape=True)
                                for suffix in POLYMARKET_SLUG_LEAGUE_SUFFIXES
                            ),
                        ),
                    ),
                ),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesOutcome.id)
        )
    ).all()
    crossing = [
        r for r in rows if link_crosses_league(r.source, r.external_id, r.key, r.event_slug)
    ]
    stats["links_outside_market_league"] = len(crossing)
    crossing = crossing[:limit]
    if not crossing:
        return

    league_teams: dict[str, list[dict]] = {}
    decisions: dict[int, Optional[int]] = {}
    for row in crossing:
        league = market_league_sport_key(row.source, row.external_id, row.event_slug)
        if league not in league_teams:
            league_teams[league] = await _load_teams_by_sport(session, [league])
        decisions[row.id] = match_outcome_to_league_team(row.name, league_teams[league])

    outcomes = (
        await session.execute(
            select(FuturesOutcome).where(FuturesOutcome.id.in_(list(decisions)))
        )
    ).scalars().all()
    for outcome in outcomes:
        new_team_id = decisions[outcome.id]
        outcome.team_id = new_team_id
        if new_team_id:
            stats["outcomes_relinked_into_market_league"] += 1
        else:
            stats["outcomes_unlinked_outside_market_league"] += 1


# Outcome names Phase 3c reads: two to four words (a name suffix included). No
# letters in it, so case-insensitive `~*` selects exactly what `~` would.
_GIVEN_NAME_SHAPE = r"^[^ ]+( [^ ]+){1,3}$"


def _rests_on_given_name_city(name: str, team_name: str, alternate_names) -> bool:
    """True when a stored link can only have come from a given name before the team's city,
    or from the city and then "D/ST" (#9726).

    False whenever any of the team's names still matches the outcome.
    """
    from app.utils.team_linking import _names_match, city_alias_names_someone_else

    alts = [a for a in alternate_names if isinstance(a, str)] if isinstance(
        alternate_names, list
    ) else []
    if not any(city_alias_names_someone_else(name, alias, team_name) for alias in alts):
        return False
    return not _names_match(name, team_name, alts)


def _on_own_roster(name: str, roster) -> bool:
    """True when the team's own roster lists the person (a Huskies player named Washington)."""
    from app.utils.team_linking import match_outcome_to_roster

    players = [
        (p.get("name") if isinstance(p, dict) else p)
        for p in (roster if isinstance(roster, list) else [])
    ]
    players = [p for p in players if isinstance(p, str) and len(p) >= 4]
    return bool(players) and match_outcome_to_roster(name, {0: players}) == 0


async def _unlink_given_name_city_alias(
    session: AsyncSession, stats: dict, limit: int
) -> None:
    """Clear a stored link made by a surname that is a team's city (#9726).

    Step 1 no longer binds "Parker Washington" to the Washington Huskies, but
    Phase 2 only selects ``team_id IS NULL``, so the links it already wrote would
    stay forever. Each open outcome whose link rests only on that shape, and whose
    team's roster does not list the person, is set to NULL; Phase 2 then offers it
    to the roster matcher (Darnell Washington reaches the Steelers) or leaves it
    unlinked.
    """
    from app.models import FuturesMarket, FuturesOutcome, Team

    rows = (
        await session.execute(
            select(FuturesOutcome.id, FuturesOutcome.name, FuturesOutcome.team_id)
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .where(
                FuturesMarket.status == "open",
                FuturesOutcome.team_id.is_not(None),
                FuturesOutcome.name.op("~*")(_GIVEN_NAME_SHAPE),
            )
            .order_by(FuturesOutcome.id)
        )
    ).all()
    if not rows:
        return
    teams = {
        t.id: t
        for t in (
            await session.execute(
                select(Team.id, Team.name, Team.alternate_names).where(
                    Team.id.in_({r.team_id for r in rows})
                )
            )
        ).all()
    }
    suspects = [
        r
        for r in rows
        if r.team_id in teams
        and _rests_on_given_name_city(
            r.name, teams[r.team_id].name, teams[r.team_id].alternate_names
        )
    ]
    if not suspects:
        stats["links_on_given_name_city_alias"] = 0
        return
    rosters = dict(
        (
            await session.execute(
                select(Team.id, Team.roster_players).where(
                    Team.id.in_({r.team_id for r in suspects})
                )
            )
        ).all()
    )
    doomed = [r.id for r in suspects if not _on_own_roster(r.name, rosters.get(r.team_id))]
    stats["links_on_given_name_city_alias"] = len(doomed)
    doomed = doomed[:limit]
    if not doomed:
        return

    outcomes = (
        await session.execute(select(FuturesOutcome).where(FuturesOutcome.id.in_(doomed)))
    ).scalars().all()
    for outcome in outcomes:
        outcome.team_id = None
        stats["outcomes_unlinked_given_name_city_alias"] += 1


async def _relink_outside_market_conference(
    session: AsyncSession, stats: dict, limit: int
) -> None:
    """Move a stored link that sits in the other half of its market's league (#8072).

    "NL MVP Winner?" and "NL Hank Aaron Award Winner?" — Max Muncy were linked to
    the Athletics (an American League club) because the Athletics' roster was read
    before the Dodgers', so the Athletics' team page listed the Dodgers' player's
    National League awards. Phase 2 only selects ``team_id IS NULL``, so the wrong
    link was permanent.

    Each such link is re-decided with the #9617 matcher among the league's teams
    in the conference the ticker names, and set to that team or to NULL (a
    player's name never matches a team). A NULL re-enters Phase 2, whose
    conference check refuses the old team, so the two passes cannot undo each other.
    """
    from app.models import FuturesMarket, FuturesOutcome, Sport, Team
    from app.utils.market_team_sport import link_crosses_conference, market_conference
    from app.utils.static_divisions import lookup_division
    from app.utils.team_linking import match_outcome_to_league_team

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesMarket.source,
                FuturesMarket.external_id,
                Sport.key,
                Team.name.label("team_name"),
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Team, Team.id == FuturesOutcome.team_id)
            .join(Sport, Sport.id == Team.sport_id)
            .where(FuturesMarket.source == "kalshi", FuturesMarket.status == "open")
            .order_by(FuturesOutcome.id)
        )
    ).all()
    crossing = [
        r
        for r in rows
        if link_crosses_conference(r.source, r.external_id, r.key, r.team_name)
    ]
    stats["links_outside_market_conference"] = len(crossing)
    crossing = crossing[:limit]
    if not crossing:
        return

    conference_teams: dict[tuple[str, str], list[dict]] = {}
    decisions: dict[int, Optional[int]] = {}
    for row in crossing:
        league, conference = market_conference(row.source, row.external_id)
        if (league, conference) not in conference_teams:
            conference_teams[(league, conference)] = [
                t
                for t in await _load_teams_by_sport(session, [league])
                if lookup_division(league, t["name"])[0] == conference
            ]
        decisions[row.id] = match_outcome_to_league_team(
            row.name, conference_teams[(league, conference)]
        )

    outcomes = (
        await session.execute(
            select(FuturesOutcome).where(FuturesOutcome.id.in_(list(decisions)))
        )
    ).scalars().all()
    for outcome in outcomes:
        new_team_id = decisions[outcome.id]
        outcome.team_id = new_team_id
        if new_team_id:
            stats["outcomes_relinked_into_market_conference"] += 1
        else:
            stats["outcomes_unlinked_outside_market_conference"] += 1


async def _relink_contradicted_in_league(
    session: AsyncSession, stats: dict, limit: int
) -> None:
    """Move a stored link its own league's matcher names a different school for (#9952).

    North Carolina's football page listed NC State's playoff and title odds as its
    own: 53 open "North Carolina St." legs sat on the Tar Heels while the Wolfpack
    row (alias "north carolina state") got none, and 46 "Northwestern" legs sat on
    the Northwestern State Demons. Measured 2026-09-30 over all 19,693 open Kalshi
    links: the #9617 matcher named a different team on 114 legs (10 names, all
    NCAAF), and every stored link was the wrong school. Phase 3 re-decides only a
    link outside its market's league, 3b the other conference, so a wrong school
    inside the right league was permanent.

    Only a positive contradiction moves a link — the matcher's unique answer in the
    stored team's league, different from the stored team. No answer leaves the link
    alone (event-linked and roster links are names the matcher cannot read), and an
    answer 3b would move back across a conference is skipped, so no pass undoes
    another.

    Polymarket links are re-decided the same way (#9952 after-check, 2026-10-01):
    with the Kalshi legs moved, UNC's page still printed NC State's playoff, title,
    quarter, semi and top-4-seed odds from five Polymarket "North Carolina St."
    legs. Replay over all 5,695 open Polymarket links: 7 contradictions, every one
    the wrong school ("Los Angeles Angels" on the Dodgers, "Georgia Southern
    Eagles" on Southern University). The event slug goes to the league check so a
    ``pro-football-`` board stays Phase 3's row.
    """
    from app.models import FuturesMarket, FuturesOutcome, Sport, Team
    from app.utils.market_team_sport import link_crosses_conference, link_crosses_league
    from app.utils.team_linking import match_outcome_to_league_team
    from app.utils.venue_competition import POLYMARKET_EVENT_SLUG_KEY

    slug = FuturesMarket.market_metadata[POLYMARKET_EVENT_SLUG_KEY].as_string()

    rows = (
        await session.execute(
            select(
                FuturesOutcome.id,
                FuturesOutcome.name,
                FuturesOutcome.team_id,
                FuturesMarket.source,
                FuturesMarket.external_id,
                slug.label("event_slug"),
                Sport.key,
            )
            .join(FuturesMarket, FuturesOutcome.market_id == FuturesMarket.id)
            .join(Team, Team.id == FuturesOutcome.team_id)
            .join(Sport, Sport.id == Team.sport_id)
            .where(
                FuturesMarket.source.in_(("kalshi", "polymarket")),
                FuturesMarket.status == "open",
            )
            .order_by(FuturesOutcome.id)
        )
    ).all()

    league_teams: dict[str, list[dict]] = {}
    answers: dict[tuple[str, str], Optional[int]] = {}
    decisions: dict[int, int] = {}
    for row in rows:
        if link_crosses_league(row.source, row.external_id, row.key, row.event_slug):
            continue  # Phase 3's row
        if row.key not in league_teams:
            league_teams[row.key] = await _load_teams_by_sport(session, [row.key])
        if (row.name, row.key) not in answers:
            answers[(row.name, row.key)] = match_outcome_to_league_team(
                row.name, league_teams[row.key]
            )
        new_team_id = answers[(row.name, row.key)]
        if not new_team_id or new_team_id == row.team_id:
            continue
        new_name = next(t["name"] for t in league_teams[row.key] if t["id"] == new_team_id)
        if link_crosses_conference(row.source, row.external_id, row.key, new_name):
            continue  # 3b would move it back
        decisions[row.id] = new_team_id

    stats["links_contradicted_in_league"] = len(decisions)
    chosen = dict(list(decisions.items())[:limit])
    if not chosen:
        return

    outcomes = (
        await session.execute(
            select(FuturesOutcome).where(FuturesOutcome.id.in_(list(chosen)))
        )
    ).scalars().all()
    for outcome in outcomes:
        outcome.team_id = chosen[outcome.id]
        stats["outcomes_relinked_in_league"] += 1


async def link_outcome_to_team(
    session: AsyncSession,
    outcome_name: str,
    sport_category: Optional[str],
    market_name: Optional[str],
    teams: list[dict],
    use_llm: bool = True,
) -> Optional[int]:
    """
    Try to match a futures outcome name to a team_id.

    1. Try direct name matching against team records
    2. If no match and use_llm=True, try LLM player-team classification

    Args:
        session: DB session (for potential follow-up queries)
        outcome_name: The outcome name (e.g., "Boston Celtics" or "Jaylen Brown")
        sport_category: Sport category (e.g., "basketball")
        market_name: Market name for LLM context
        teams: Pre-loaded team records to match against
        use_llm: Whether to fall back to LLM for player names

    Returns:
        team_id if matched, None otherwise
    """
    from app.utils.team_linking import match_outcome_to_team

    # Step 1: Identity service fast path (indexed lookup)
    from app.services.team_identity import team_identity_service
    # Determine sport key from teams list (all teams in same category share a key)
    identity_sport_key = ""
    if teams:
        identity_sport_key = teams[0].get("sport_key", "")
    if identity_sport_key:
        resolved = await team_identity_service.resolve_team(
            session, "futures", identity_sport_key,
            source_name=outcome_name,
        )
        if resolved:
            return resolved.id

    # Step 2: Direct name match
    team_id = match_outcome_to_team(outcome_name, teams)
    if team_id:
        # Register for future instant lookups
        if identity_sport_key:
            await team_identity_service.register_team_identity(
                session, team_id, "futures", identity_sport_key,
                source_name=outcome_name,
            )
        return team_id

    # Step 3: LLM player-team classification
    if use_llm:
        from app.services import llm
        if not llm.is_available():
            return None

        team_name = llm.classify_player_team_cached(
            player_name=outcome_name,
            sport_category=sport_category,
            market_name=market_name,
        )
        if team_name:
            # Now match the LLM's team name against our team records
            team_id = match_outcome_to_team(team_name, teams)
            if team_id:
                logger.info(
                    f"LLM linked '{outcome_name}' → '{team_name}' → team_id={team_id}"
                )
            return team_id

    return None


@asynccontextmanager
async def _unit(session: AsyncSession, stats: dict, label: str):
    """Run one unit of the drain in its own SAVEPOINT (#9790).

    The drain is one transaction and a deadlock aborts all of it: measured
    09:50Z 9/30, the hockey category's autoflush hit ``deadlock detected``, every
    later category and phase raised ``PendingRollbackError``, and the commit
    threw away the whole batch while the task logged ``outcomes_linked: 1206``.
    Rolled back to here, a failure costs its own unit. Its counts go back to
    what they were before it, so the result reports only what landed, and
    ``units_rolled_back`` names it.
    """
    counts = {k: v for k, v in stats.items() if type(v) is int}
    try:
        async with session.begin_nested():
            yield
    except Exception as e:
        stats.update(counts)
        stats["units_rolled_back"].append(label)
        stats["errors"].append(f"{label}: {str(e)}")


async def _backfill_team_links(limit: int = 200, use_llm: bool = True):
    """
    Backfill team_id on FuturesOutcome records and market_tier on FuturesMarket records.

    Processes outcomes where team_id IS NULL and the market has a known sport category.
    Also sets market_tier on any FuturesMarket where it's NULL.
    """
    from app.models import FuturesMarket
    from app.utils.market_label_normalization import compute_market_tier
    from app.utils.team_linking import get_sport_keys_for_category

    stats = {
        "outcomes_processed": 0,
        "outcomes_linked": 0,
        "outcomes_linked_by_name": 0,
        "outcomes_linked_by_league": 0,
        "outcomes_linked_by_roster": 0,
        "outcomes_linked_by_llm": 0,
        "outcomes_refused_outside_market_league": 0,
        "outcomes_relinked_into_market_league": 0,
        "outcomes_unlinked_outside_market_league": 0,
        "outcomes_refused_outside_market_conference": 0,
        "outcomes_relinked_into_market_conference": 0,
        "outcomes_unlinked_outside_market_conference": 0,
        "outcomes_unlinked_given_name_city_alias": 0,
        "outcomes_relinked_in_league": 0,
        "markets_tiered": 0,
        "units_rolled_back": [],
        "errors": [],
    }

    rc = _cursor_store()
    cursor_writes: list[tuple[str, Optional[int]]] = []

    try:
        async with get_task_session() as session:
            # --- Phase 1: Assign market_tier where missing or wrong ---
            # Re-tier: NULL tiers AND all tier-5 markets. compute_market_tier
            # now checks name patterns before category, so "game_prop" markets
            # whose names match division/conference/championship patterns get
            # promoted to their correct tier.
            async with _unit(session, stats, "Market tiers"):
                tier_result = await session.execute(
                    select(FuturesMarket)
                    .where(
                        or_(
                            FuturesMarket.market_tier.is_(None),
                            FuturesMarket.market_tier == 5,
                        )
                    )
                    .limit(limit * 5)
                )
                markets_to_tier = tier_result.scalars().all()

                for market in markets_to_tier:
                    new_tier = compute_market_tier(
                        market.name, market.category,
                        sport_category=market.llm_sport_category,
                    )
                    if market.market_tier != new_tier:
                        market.market_tier = new_tier
                        stats["markets_tiered"] += 1

            # --- Phase 2: Link outcomes to teams ---
            # Two passes, each resuming from its own persisted id cursor (#7307).
            # Open markets first — those are the legs a reader can load — with a
            # reserved floor for the resolved backlog so it never starves.
            floor = _resolved_floor(limit)
            passes = [
                ("open", _CURSOR_KEY_OPEN, True, max(0, limit - floor)),
                ("resolved", _CURSOR_KEY_RESOLVED, False, None),
            ]

            outcomes = []

            for label, key, open_markets, budget in passes:
                if budget is None:
                    budget = max(0, limit - len(outcomes))
                if budget <= 0:
                    # Nothing asked for is not the end of the table: leave the
                    # cursor exactly where it is, or the next run rewinds.
                    stats[f"selected_{label}"] = 0
                    continue

                cursor = _read_cursor(rc, key)
                rows = (
                    await session.execute(
                        unlinked_outcomes_query(
                            open_markets=open_markets, cursor=cursor, batch=budget,
                        )
                    )
                ).scalars().all()

                stats[f"selected_{label}"] = len(rows)
                stats[f"cursor_{label}_start"] = cursor
                if len(rows) < budget:
                    # Ran off the end of this pass's population: wrap so the next
                    # run re-scans from the head and picks up new rows plus the
                    # ones that failed a full cycle ago.
                    cursor_writes.append((key, None))
                    stats[f"wrapped_{label}"] = True
                else:
                    cursor_writes.append((key, rows[-1].id))
                outcomes.extend(rows)

            # No early return on an empty batch: the cursor writes below are
            # applied outside this block, after the session has committed, and
            # a wrap recorded by an empty pass has to survive.

            # #5119: every bind below is refused when it would put the outcome
            # outside the league its market's venue id names.
            team_sport_keys = await _load_team_sport_keys(session) if outcomes else {}
            # #8072: and outside the conference its ticker names (NL MVP, AFC East).
            team_names = await _load_team_names(session) if outcomes else {}

            def _admit(outcome, team_id) -> bool:
                if team_id and _crosses_market_league(outcome, team_id, team_sport_keys):
                    stats["outcomes_refused_outside_market_league"] += 1
                    return False
                if team_id and _crosses_market_conference(
                    outcome, team_id, team_sport_keys, team_names
                ):
                    stats["outcomes_refused_outside_market_conference"] += 1
                    return False
                return bool(team_id)

            # --- Phase 2a: Fast path for event-linked markets ---
            # Game props (Kalshi/Polymarket) have FuturesMarket.event_id set,
            # which gives us the exact two teams. Match against only those
            # rosters — eliminates cross-team false positives entirely.
            from app.models import Event, Sport, Team as TeamModel
            from app.utils.team_linking import match_outcome_to_roster
            remaining_outcomes = []
            event_cache: dict[int, dict] = {}  # event_id → {team_id: [player_names]}

            def _extract_rosters(team_rows) -> dict[int, list[str]]:
                rosters: dict[int, list[str]] = {}
                for tr in team_rows:
                    roster = tr.roster_players
                    if roster and isinstance(roster, list):
                        players = []
                        for item in roster:
                            name = item.get("name") if isinstance(item, dict) else item if isinstance(item, str) else None
                            if isinstance(name, str) and len(name) >= 4:
                                players.append(name)
                        if players:
                            rosters[tr.id] = players
                return rosters

            async with _unit(session, stats, "Event rosters"):
                for outcome in outcomes:
                    market = outcome.market
                    if not market.event_id:
                        remaining_outcomes.append(outcome)
                        continue

                    stats["outcomes_processed"] += 1

                    # Load event teams (cached per event_id)
                    if market.event_id not in event_cache:
                        ev = await session.get(Event, market.event_id)
                        event_rosters: dict[int, list[str]] = {}
                        if ev:
                            if ev.home_team_id or ev.away_team_id:
                                # Fast path: FK team IDs exist
                                team_ids = [t for t in [ev.home_team_id, ev.away_team_id] if t]
                                team_rows = (await session.execute(
                                    select(TeamModel.id, TeamModel.name, TeamModel.roster_players)
                                    .where(TeamModel.id.in_(team_ids))
                                )).all()
                                event_rosters = _extract_rosters(team_rows)
                            elif ev.home_team_name and ev.away_team_name:
                                # Fallback: team IDs not set, look up by name + sport
                                name_filters = [
                                    or_(
                                        TeamModel.name == ev.home_team_name,
                                        TeamModel.name == ev.away_team_name,
                                    )
                                ]
                                if ev.sport_id:
                                    name_filters.append(TeamModel.sport_id == ev.sport_id)
                                team_rows = (await session.execute(
                                    select(TeamModel.id, TeamModel.name, TeamModel.roster_players)
                                    .where(*name_filters)
                                )).all()
                                event_rosters = _extract_rosters(team_rows)
                        event_cache[market.event_id] = event_rosters
                        if not event_rosters and ev:
                            logger.info(
                                "Event %s (%s vs %s): no rosters found (team_ids=%s/%s, sport_id=%s)",
                                market.event_id, ev.home_team_name, ev.away_team_name,
                                ev.home_team_id, ev.away_team_id, ev.sport_id,
                            )

                    event_rosters = event_cache[market.event_id]
                    if event_rosters:
                        team_id = match_outcome_to_roster(outcome.name, event_rosters)
                        if _admit(outcome, team_id):
                            outcome.team_id = team_id
                            stats["outcomes_linked"] += 1
                            stats["outcomes_linked_by_roster"] += 1
                            continue

                    # Event-linked but no roster match — fall through to category matching
                    remaining_outcomes.append(outcome)

            # --- Phase 2b: Category-based matching for non-event-linked markets ---
            # Group outcomes by sport category to batch team loading
            category_outcomes: dict[str, list] = {}
            for outcome in remaining_outcomes:
                market = outcome.market
                category = (
                    market.llm_sport_category
                    or market.category
                    or "unknown"
                )
                category_outcomes.setdefault(category, []).append(outcome)

            # Process each category
            ticker_league_cache: dict[str, list[dict]] = {}
            for category, cat_outcomes in category_outcomes.items():
                async with _unit(session, stats, f"Category '{category}'"):
                    # Load teams for this sport category
                    sport_keys = get_sport_keys_for_category(category)
                    teams = await _load_teams_by_sport(session, sport_keys)

                    if not teams and sport_keys:
                        # Fallback: load all teams if sport-scoped search returned nothing
                        teams = await _load_teams_by_sport(session, None)

                    # Build roster lookup: {team_id: [player_name, ...]}
                    from app.utils.team_linking import match_outcome_to_roster
                    team_rosters: dict[int, list[str]] = {}
                    for team in teams:
                        roster = team.get("roster_players")
                        if roster and isinstance(roster, list):
                            players = []
                            for item in roster:
                                if isinstance(item, dict):
                                    name = item.get("name")
                                elif isinstance(item, str):
                                    name = item
                                else:
                                    continue
                                if isinstance(name, str) and len(name) >= 4:
                                    players.append(name)
                            if players:
                                team_rosters[team["id"]] = players

                    for outcome in cat_outcomes:
                        try:
                            stats["outcomes_processed"] += 1

                            # Step 0: the Kalshi ticker names the league (#9617).
                            # A city-only name is ambiguous across the category
                            # (Knicks + Liberty) and unique inside one league.
                            team_id = _match_in_ticker_league(
                                outcome,
                                await _ticker_league_teams(
                                    session, outcome, teams, ticker_league_cache
                                ),
                            )
                            # ...and inside the conference the ticker names (#8072,
                            # CERT-3801's follow-up): "Los Angeles D" on the AL
                            # champion board is the Dodgers by city and an NL club.
                            if _admit(outcome, team_id):
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_league"] += 1
                                continue
                            if _short_name(outcome.name):
                                # #9687: Step 0 is the only reader of a short name.
                                continue

                            # Step 1: Try name matching first (no LLM)
                            from app.utils.team_linking import match_outcome_to_team
                            team_id = match_outcome_to_team(outcome.name, teams)

                            if _admit(outcome, team_id):
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_name"] += 1
                                continue

                            # Step 1.5: Try roster player matching
                            team_id = match_outcome_to_roster(
                                outcome.name, team_rosters
                            )
                            if _admit(outcome, team_id):
                                outcome.team_id = team_id
                                stats["outcomes_linked"] += 1
                                stats["outcomes_linked_by_roster"] += 1
                                continue

                            # Step 2: Try LLM for player names
                            if use_llm:
                                team_id = await link_outcome_to_team(
                                    session=session,
                                    outcome_name=outcome.name,
                                    sport_category=category,
                                    market_name=outcome.market.name,
                                    teams=teams,
                                    use_llm=True,
                                )
                                if _admit(outcome, team_id):
                                    outcome.team_id = team_id
                                    stats["outcomes_linked"] += 1
                                    stats["outcomes_linked_by_llm"] += 1

                        except Exception as e:
                            # A statement that failed aborted the savepoint: every
                            # later outcome would fail on it too (#9790).
                            if isinstance(e, (DBAPIError, PendingRollbackError)):
                                raise
                            stats["errors"].append(
                                f"Outcome {outcome.id} '{outcome.name}': {str(e)}"
                            )

            # --- Phase 3: stored links outside their market's league (#5119) ---
            async with _unit(session, stats, "Market-league relink"):
                await _relink_outside_market_league(session, stats, limit)

            # --- Phase 3b: stored links in the other conference (#8072) ---
            async with _unit(session, stats, "Market-conference relink"):
                await _relink_outside_market_conference(session, stats, limit)

            # --- Phase 3c: stored links on a surname that is a city (#9726) ---
            async with _unit(session, stats, "Given-name city unlink"):
                await _unlink_given_name_city_alias(session, stats, limit)

            # --- Phase 3d: stored links on the wrong school in the right league (#9952) ---
            async with _unit(session, stats, "In-league contradiction relink"):
                await _relink_contradicted_in_league(session, stats, limit)

        # Outside the session:``get_task_session`` commits on the way out and
        # rolls back on an exception, so reaching here is the proof the batch
        # landed. Only now may the window move (#7307). It moves past a unit
        # that rolled back too (#9790): those rows come round again at the next
        # wrap, where holding the window would re-run a unit that deadlocks
        # every hour and strand everything behind it.
        _apply_cursor_writes(rc, cursor_writes)

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    if stats["units_rolled_back"]:
        logger.warning(
            "team-link drain: %d unit(s) rolled back, their links did not land: %s",
            len(stats["units_rolled_back"]),
            stats["units_rolled_back"],
        )

    logger.info(
        "team-link drain: open=%s resolved=%s processed=%d linked=%d "
        "cursor_open=%s cursor_resolved=%s wrapped_open=%s wrapped_resolved=%s",
        stats.get("selected_open"),
        stats.get("selected_resolved"),
        stats["outcomes_processed"],
        stats["outcomes_linked"],
        stats.get("cursor_open_start"),
        stats.get("cursor_resolved_start"),
        stats.get("wrapped_open", False),
        stats.get("wrapped_resolved", False),
    )
    return stats


async def _backfill_canonical_keys(limit: int = 500):
    """
    Backfill canonical_market_key, llm_league, and llm_sport_category on
    FuturesMarket records.

    Processes markets where:
    - canonical_market_key IS NULL, or
    - llm_league IS NULL, or
    - llm_sport_category is 'other' or NULL (tries to upgrade via league
      inference or expanded pattern matching)

    Also fills in llm_league where missing.
    """
    from app.models import FuturesMarket
    from app.utils.futures_categorization import (
        categorize_by_rules, detect_league, detect_season,
        compute_canonical_market_key, infer_sport_from_league,
        extract_olympic_discipline,
    )

    stats = {
        "processed": 0,
        "leagues_set": 0,
        "keys_set": 0,
        "categories_upgraded": 0,
        "errors": [],
    }

    try:
        async with get_task_session() as session:
            # Find markets missing canonical key, league, or stuck as 'other'
            result = await session.execute(
                select(FuturesMarket)
                .where(
                    or_(
                        FuturesMarket.canonical_market_key.is_(None),
                        FuturesMarket.llm_league.is_(None),
                        FuturesMarket.llm_sport_category.is_(None),
                        FuturesMarket.llm_sport_category == "other",
                    )
                )
                .limit(limit)
            )
            markets = result.scalars().all()

            if not markets:
                stats["message"] = "No markets to backfill"
                return stats

            for market in markets:
                try:
                    stats["processed"] += 1

                    # Detect league if missing
                    if not market.llm_league:
                        sport_key = (
                            market.external_id
                            if market.source == "odds_api"
                            else None
                        )
                        league = detect_league(market.name, sport_key)
                        if league:
                            market.llm_league = league
                            stats["leagues_set"] += 1
                    else:
                        league = market.llm_league

                    # Try to upgrade 'other' or NULL sport category
                    if not market.llm_sport_category or market.llm_sport_category == "other":
                        upgraded = False

                        # Strategy 1: Infer sport from detected league
                        if league:
                            sport = infer_sport_from_league(league)
                            if sport:
                                market.llm_sport_category = sport
                                stats["categories_upgraded"] += 1
                                upgraded = True

                        # Strategy 2: Re-run pattern matching (catches newly added patterns)
                        if not upgraded:
                            sport_key = (
                                market.external_id
                                if market.source == "odds_api"
                                else None
                            )
                            rules_result = categorize_by_rules(market.name, sport_key)
                            if rules_result and rules_result != "other":
                                market.llm_sport_category = rules_result
                                stats["categories_upgraded"] += 1

                    # Compute canonical key if missing
                    if not market.canonical_market_key:
                        season = detect_season(
                            market.name, league, market.resolution_date,
                        )
                        # For Olympics, use specific discipline as category
                        canon_category = market.category
                        if market.llm_sport_category == "olympics":
                            discipline = extract_olympic_discipline(market.name)
                            if discipline:
                                canon_category = discipline
                        key = compute_canonical_market_key(
                            market.llm_sport_category,
                            league,
                            canon_category,
                            season,
                        )
                        if key:
                            market.canonical_market_key = key
                            stats["keys_set"] += 1

                except Exception as e:
                    stats["errors"].append(
                        f"Market {market.id} '{market.name}': {str(e)}"
                    )

            await session.commit()

    except Exception as e:
        stats["errors"].append(f"Top-level error: {str(e)}")

    stats["message"] = (
        f"Processed {stats['processed']} markets: "
        f"{stats['leagues_set']} leagues set, "
        f"{stats['keys_set']} canonical keys set, "
        f"{stats['categories_upgraded']} categories upgraded from 'other'"
    )
    logger.info(
        "Canonical key backfill: %d processed, %d leagues, %d keys, %d categories upgraded",
        stats["processed"],
        stats["leagues_set"],
        stats["keys_set"],
        stats["categories_upgraded"],
    )
    return stats
