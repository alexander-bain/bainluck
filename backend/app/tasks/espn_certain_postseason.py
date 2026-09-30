"""A postseason game that must be played gets its row when ESPN schedules it (#9216).

**SHIP: Braves–Phillies and Astros–White Sox Wild Card Game 2 (Wed 9/30) get a
page on /sports/baseball_mlb with their Kalshi price as soon as ESPN schedules
them — and so does every later postseason game once it is certain.**
(Pillar: MATCHING.)

On 2026-09-28 04:00Z the MLB page showed Game 2 for Red Sox–Yankees and
Cubs–Padres (StatPal lists those two series) and Game 1 only for the other two.
Kalshi had listed both missing Game 2s at 02:48Z (62924881 ``PHIATL``, 62924880
``CWSHOU``), with nothing to attach to. ESPN had them as 401907972 and 401907897,
but our ESPN passes read only today's board. The Odds API lists a Game 2 only
once Game 1 is played (#8956), so the page appeared about 20 hours before first
pitch, and in the LDS (2–3 days between games) the gap is longer.

**What this pass does.** Hourly, for the postseason sports in
:data:`LOOKAHEAD_SPORTS`, it reads ESPN's dated boards for the next
:data:`LOOKAHEAD_DAYS` Eastern days. It keeps only the games
``postseason_series.certain_to_be_played`` accepts, then hands each game whose
``espn_id`` no row holds to the registry as an ESPN claim (ruling 048 arm B,
exactly the claim ``create_events_from_unmatched_espn`` makes off today's
board) with ``same_game_only`` set. The registry then does one of two things:

* **attach** to a row we already hold for that game (a StatPal or Odds row
  within 12h, bound to no other ESPN game), stamping the id; or
* **create** the row, tagged ``provenance:source:espn``.

**What it never does.** It never creates an "If Necessary" game before the
series makes it certain: a created game that is never played would sit on the
site as a scheduled game that never happens, and nothing retires a row whose
ESPN event disappears. It never lands a Game 2 claim on the Game 1 row
(``same_game_only``: the 28h window would otherwise return it, and ESPN's rank
would move Game 1's start). It writes no score, status or probability — the
live pass owns those on game day. A group-scoped board is never read.

**What it corrects (#9602).** Every certain game's row — one it just made or
attached, and one it already held — is marked ``llm_importance = 'playoff'``,
the rule the ESPN game-day pass applies from ``season.type = 3``, and like that
rule it never downgrades ``'championship'``. Without this a Game 2 that StatPal
created a day early carries the LLM classifier's ``'regular_season'`` fallback
until it reaches today's board, so its card reads as a regular-season game
("PHI 88-74 · ATL 94-68") instead of "Playoff game". It is one Core ``UPDATE``
per league, scoped by league and ESPN id, and idempotent: a row the metadata
enrichment re-labels before its first enrichment (it writes importance on any
row with no gender/level yet) is marked again on the next hourly run.

**What the later Odds row does.** The Odds API claim is a listing, not a
dereference, so it creates its own row when it arrives, and the two are one
game. ``fold_twin_events`` shows that pair as one card with both venues on
search, the feed, team, league and event pages, the same as the StatPal + Odds
pairs that Red Sox–Yankees and Cubs–Padres Game 2 already are today.

Bounded by construction: at most ``len(LOOKAHEAD_SPORTS) * LOOKAHEAD_DAYS``
board reads per run (12). A board of regular-season games stops that sport's
read, so during the regular season it is one read per sport.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, update

from app.utils.postseason_series import certain_to_be_played

logger = logging.getLogger(__name__)

#: Leagues whose playoffs are series ESPN describes with a ``series`` object.
#: A league missing here is never read, so adding one is a decision, not drift.
LOOKAHEAD_SPORTS: tuple[str, ...] = (
    "baseball_mlb",
    "basketball_nba",
    "basketball_wnba",
    "icehockey_nhl",
)

#: Eastern days ahead of today. Today's board belongs to the live pass. Three
#: covers a Wild Card (daily games) and the LDS/LCS travel days.
LOOKAHEAD_DAYS = 3

_EASTERN = ZoneInfo("America/New_York")
_POSTSEASON = 3

#: ``espn_helpers``' season-type rule: type 3 is ``'playoff'``, and a row that
#: already reads ``'championship'`` keeps it (a World Series game is both).
_PLAYOFF = "playoff"
_NOT_DOWNGRADED = ("playoff", "championship")


def board_days(now: datetime, days: int = LOOKAHEAD_DAYS) -> list[str]:
    """ESPN board days (``YYYYMMDD``, Eastern) from tomorrow, soonest first."""
    today = now.astimezone(_EASTERN).date()
    return [(today + timedelta(days=offset)).strftime("%Y%m%d") for offset in range(1, days + 1)]


def select_certain_games(board: Iterable[Any], stats: dict) -> list[Any]:
    """The games on one board this pass may claim.

    Scheduled, postseason, two named teams, an ESPN id, and certain to be
    played. Every refusal is counted by its reason, so a run says why a game it
    saw was left alone.
    """
    keep = []
    for ee in board:
        if getattr(ee, "season_type", None) != _POSTSEASON:
            continue
        if not getattr(ee, "espn_id", None):
            _count(stats, "refused_no_id")
            continue
        if getattr(ee, "status", None) != "scheduled":
            _count(stats, "refused_not_scheduled")
            continue
        if not _team_name(getattr(ee, "home_team", None)) or not _team_name(
            getattr(ee, "away_team", None)
        ):
            _count(stats, "refused_no_teams")
            continue
        if getattr(ee, "date", None) is None:
            _count(stats, "refused_no_date")
            continue
        certain, reason = certain_to_be_played(getattr(ee, "playoff_series", None))
        if not certain:
            _count(stats, f"refused_{reason}")
            continue
        keep.append(ee)
    return keep


def _team_name(team: Any) -> str:
    if team is None:
        return ""
    return (getattr(team, "display_name", None) or getattr(team, "name", None) or "").strip()


def _count(stats: dict, key: str, by: int = 1) -> None:
    stats[key] = stats.get(key, 0) + by


def claim_identity(sport_key: str, ee: Any):
    """The registry identity for one certain game — ESPN's own teams and date."""
    from app.services.event_registry import EventClaim, EventIdentity
    from app.utils.espn_start_time import espn_start_time

    return EventIdentity(
        sport_key=sport_key,
        home_team_name=_team_name(ee.home_team),
        away_team_name=_team_name(ee.away_team),
        commence_time=ee.date,
        # Ruling 048 arm B, the same claim `create_events_from_unmatched_espn`
        # makes: teams and date are read off the board entry `ee.espn_id` names.
        claim=EventClaim("espn", str(ee.espn_id), schedule_derived=True),
        commence_time_source="espn",
        status="scheduled",
        # #8841: an unannounced start mints the row (the game exists) but never
        # moves a matched row's clock onto ESPN's midnight-Eastern placeholder.
        commence_time_is_placeholder=espn_start_time(ee) is None,
        same_game_only=True,
    )


def _needs_playoff(sport_key: str, espn_ids: list[str]):
    """The rows of these ESPN games, in this league, not yet marked postseason."""
    from app.models.models import Event, Sport

    return (
        Event.espn_id.in_(espn_ids),
        Event.sport_id.in_(select(Sport.id).where(Sport.key == sport_key)),
        or_(Event.llm_importance.is_(None), Event.llm_importance.notin_(_NOT_DOWNGRADED)),
    )


def mark_playoff_statement(sport_key: str, espn_ids: list[str]):
    """``UPDATE events SET llm_importance = 'playoff'`` for those rows (#9602).

    Core, not ORM assignment (gotcha #5): the registry's rows are not loaded here.
    """
    from app.models.models import Event

    return (
        update(Event)
        .where(*_needs_playoff(sport_key, espn_ids))
        .values(llm_importance=_PLAYOFF)
        .returning(Event.id)
        .execution_options(synchronize_session=False)
    )


async def _mark_playoff(session, candidates, held: set[str], apply: bool, stats: dict) -> None:
    """Mark every certain game's row we hold as a playoff game (#9602).

    ``held`` is every candidate id a row carries after the claims — the ones
    already held and the ones just made or attached. On a dry run it names only
    the rows held before the run, and the rows it would mark are counted, not
    written.
    """
    from app.models.models import Event

    by_sport: dict[str, set[str]] = {}
    for sport_key, ee in candidates:
        if str(ee.espn_id) in held:
            by_sport.setdefault(sport_key, set()).add(str(ee.espn_id))
    for sport_key, ids in sorted(by_sport.items()):
        wanted = sorted(ids)
        try:
            if apply:
                rows = (await session.execute(mark_playoff_statement(sport_key, wanted))).all()
                await session.commit()
            else:
                rows = (
                    await session.execute(
                        select(Event.id).where(*_needs_playoff(sport_key, wanted))
                    )
                ).all()
        except Exception as e:  # noqa: BLE001 — gotcha #42: one league, not the run
            await session.rollback()
            stats["errors"].append(f"{sport_key}/importance: {e}")
            continue
        marked = sorted(int(r[0]) for r in rows)
        stats["marked_playoff"] += len(marked)
        stats["marked_playoff_ids"].extend(marked)
        if marked:
            logger.info(
                "Certain postseason games (#9602): %s %d row(s) %s playoff: %s",
                sport_key, len(marked), "marked" if apply else "would be marked", marked,
            )


async def _read_candidates(espn, now: datetime, stats: dict) -> list[tuple[str, Any]]:
    """``[(sport_key, espn_event)]`` across the lookahead, soonest day first."""
    from app.services.espn_api import ESPN_FULL_SLATE_GROUPS
    from app.utils.sport_keys import ESPN_GROUP_SCOPED_BOARDS

    found: list[tuple[str, Any]] = []
    for sport_key in LOOKAHEAD_SPORTS:
        if sport_key in ESPN_GROUP_SCOPED_BOARDS:
            continue
        for day in board_days(now):
            try:
                board = await espn.get_scoreboard(
                    sport_key, date=day, groups=ESPN_FULL_SLATE_GROUPS.get(sport_key)
                )
            except Exception as e:  # noqa: BLE001 — one board must not cost the rest
                stats["errors"].append(f"{sport_key}/{day}: {e}")
                continue
            if board is None:
                # ESPN did not answer: absence proves nothing, so nothing is made.
                _count(stats, "boards_dark")
                continue
            _count(stats, "boards_read")
            # A board of games none of which is postseason means the regular
            # season: nothing later in the window is either. An EMPTY board is
            # not that — it is a playoff travel day, or the off-season — so the
            # next day is still read.
            if board and not any(
                getattr(ee, "season_type", None) == _POSTSEASON for ee in board
            ):
                _count(stats, "sports_not_in_postseason")
                break
            for ee in select_certain_games(board, stats):
                found.append((sport_key, ee))
    return found


async def _run_create_certain_postseason_games(apply: bool = True) -> dict:
    from app.models.models import Event
    from app.services.espn_api import ESPNAPIService
    from app.services.event_registry import find_or_create_event
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "apply": apply,
        "boards_read": 0,
        "boards_dark": 0,
        "certain": 0,
        "already_held": 0,
        "created": 0,
        "attached": 0,
        "marked_playoff": 0,
        "planned": [],
        "created_ids": [],
        "attached_ids": [],
        "marked_playoff_ids": [],
        "errors": [],
    }

    espn = ESPNAPIService()
    try:
        candidates = await _read_candidates(espn, now, stats)
    finally:
        await espn.close()
    stats["certain"] = len(candidates)
    if not candidates:
        stats["status"] = "no_candidates"
        return stats

    async with get_task_session() as session:
        wanted = sorted({str(ee.espn_id) for _k, ee in candidates})
        held = {
            str(r[0])
            for r in (
                await session.execute(select(Event.espn_id).where(Event.espn_id.in_(wanted)))
            ).all()
        }
        for sport_key, ee in candidates:
            espn_id = str(ee.espn_id)
            if espn_id in held:
                stats["already_held"] += 1
                continue
            plan = {
                "sport_key": sport_key,
                "espn_id": espn_id,
                "game": f"{_team_name(ee.away_team)} @ {_team_name(ee.home_team)}",
                "commence_time": ee.date.isoformat(),
                "game_number": getattr(ee.playoff_series, "game_number", None),
            }
            stats["planned"].append(plan)
            if not apply:
                continue
            try:
                event, created = await find_or_create_event(session, claim_identity(sport_key, ee))
                event_id = event.id
                await session.commit()
            except Exception as e:  # noqa: BLE001 — gotcha #42: one game, not the run
                await session.rollback()
                stats["errors"].append(f"{sport_key}/{espn_id}: {e}")
                continue
            held.add(espn_id)
            if created:
                stats["created"] += 1
                stats["created_ids"].append(event_id)
            else:
                stats["attached"] += 1
                stats["attached_ids"].append(event_id)
            logger.info(
                "Certain postseason game (#9216): %s espn_id=%s %s -> event %s (%s)",
                sport_key, espn_id, plan["game"], event_id,
                "created" if created else "attached",
            )

        await _mark_playoff(session, candidates, held, apply, stats)

    stats["status"] = "complete" if not stats["errors"] else "partial"
    logger.info(
        "Certain postseason games (#9216): %d boards (%d dark), %d certain, %d held, "
        "%d created, %d attached, %d marked playoff, apply=%s",
        stats["boards_read"], stats["boards_dark"], stats["certain"],
        stats["already_held"], stats["created"], stats["attached"],
        stats["marked_playoff"], apply,
    )
    return stats

