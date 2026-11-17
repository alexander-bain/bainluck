"""ESPN's matchup predictor as the chance for scheduled games nobody prices yet (#12824).

Alex, on Bills at Patriots three weeks out (TestFlight 5757, Mon Nov 16): "we
should have a win probability from some source." No venue listed the game, and
the two sportsbooks that had are under ruling 051's three-book floor, so the
blend had nothing to stand on. ESPN publishes a predictor for every NFL,
college football, NBA and college basketball game on its schedule. It is
already an input to our blend (``espn``, weight 1.5) once a game is live. This
task reads it BEFORE kickoff, for the games that would otherwise show nothing.

Fable's (b), 6:01 PM and 6:36 PM Mon Nov 16:

* every scheduled game we hold in the next :data:`HORIZON`, in a league where
  ESPN publishes a predictor, with no market price, shows a chance;
* as fresh as our other pregame numbers: this runs every 15 minutes, which is
  ESPN's own ``max-age=900`` on the predictor;
* ESPN is named only in the "Where this number comes from" sheet: the reading
  is the existing ``espn`` source, which that sheet already labels;
* when books or a venue price the game, they join through the existing weights
  and nothing is held at an old value: a game that holds an ESPN reading keeps
  being read until kickoff, so the reading never freezes beside them;
* a predictor ESPN has not updated in :data:`MAX_PREDICTOR_AGE` is treated as
  absent, as ruling 051 treats a source below its floor.

What this does NOT do: show a one- or two-book sportsbook number. That would
change ruling 051 and is Alex's decision 225.

A game is matched to ESPN's board by the same authorized selector every
``espn_id`` writer uses (names AND clock, with our own ``espn_id`` as an
anchor when we hold one), and only when ESPN's home team is our home team.
Nothing here stamps an ``espn_id`` or touches any other column: the one write
is the ``espn`` source, through ``write_nonvenue_probability``.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

#: Leagues where ESPN publishes a pregame predictor (probed 2026-11-17 04:00Z:
#: NFL, college football, NBA, men's and women's college basketball all
#: answer; NHL, EPL and MLS have none). Every key is also in
#: ``WIN_PROB_SOURCES["espn"]``.
PREDICTOR_LEAGUES: tuple[str, ...] = (
    "americanfootball_nfl",
    "americanfootball_ncaaf",
    "basketball_nba",
    "basketball_ncaab",
    "basketball_wncaab",
)

#: ESPN's default college boards are the ranked games only (4 men's games on
#: 2026-11-21 against 57 with ``groups=50``), so a college row would never find
#: its game. These are the full-slate groups: FBS, and Division I basketball.
BOARD_GROUPS: dict[str, str] = {
    "americanfootball_ncaaf": "80",
    "basketball_ncaab": "50",
    "basketball_wncaab": "50",
}

#: How far ahead a game is worth a reading (Fable: "the next 4 weeks").
HORIZON = timedelta(days=28)

#: A predictor ESPN has not updated within this long is absent (Fable 6:36 PM).
MAX_PREDICTOR_AGE = timedelta(days=7)

#: A stored ESPN reading we could not refresh (ESPN dark, the game not found on
#: its board) is withdrawn once it is this old: eight missed 15-minute runs.
#: Before kickoff the blend has no relative decay (`_relative_decay_applies`),
#: so without this a reading would stand at its last value indefinitely.
UNREFRESHED_READING_LIMIT = timedelta(hours=2)

#: Sources that make a game "priced". ``espn`` is ours; ``stat_model`` and
#: ``mlb`` are models, not prices. A ``betting`` entry under the 051 floor has
#: no value and so does not count.
PRICE_SOURCES: tuple[str, ...] = ("betting", "kalshi", "polymarket")

#: The off switch. ``withdraw`` makes a run REMOVE the ESPN reading from every
#: scheduled game in scope instead of reading ESPN, which is the clean rollback:
#: a plain revert would leave the last readings standing, and before kickoff the
#: blend never ages them. Run once in ``withdraw``, then revert. Set as the
#: ``ESPN_PREDICTOR_MODE`` config var (Alex) or by changing this default.
DEFAULT_MODE = "on"


def predictor_mode() -> str:
    import os

    mode = (os.environ.get("ESPN_PREDICTOR_MODE") or DEFAULT_MODE).strip().lower()
    return "withdraw" if mode == "withdraw" else "on"


@dataclass(frozen=True)
class PredictorRow:
    event_id: int
    sport_key: str
    espn_id: Optional[str]
    commence_time: datetime
    home_team_name: Optional[str]
    away_team_name: Optional[str]
    sources: dict
    # The naming surface `get_event_name_variations` and the orientation check read.
    home_team_normalized: Optional[str] = None
    away_team_normalized: Optional[str] = None
    home_team_alt_names: Optional[list] = None
    away_team_alt_names: Optional[list] = None


def _stat(side: dict, name: str) -> Optional[float]:
    for item in (side or {}).get("statistics") or ():
        if isinstance(item, dict) and item.get("name") == name:
            value = item.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _parse_modified(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def predictor_home_probability(
    payload: Any, now: datetime
) -> tuple[Optional[float], str]:
    """ESPN's home-team chance from a predictor body, ties excluded, or why not.

    ``(value, "ok")`` or ``(None, reason)``. Two shapes are live: NFL and
    college put ``gameProjection`` on both sides (Patriots 14.135, Bills
    85.752, tie 0.113); NBA puts statistics on the AWAY side only, where
    ``teamChanceLoss`` is the home team's chance. The tie share is dropped by
    normalising over the two win chances, so Bills at Patriots reads 0.1415 for
    the home side (Patriots 14%, Bills 86%).
    """
    if not isinstance(payload, dict):
        return None, "no-predictor"
    modified = _parse_modified(payload.get("lastModified"))
    if modified is None:
        return None, "no-last-modified"
    if now - modified > MAX_PREDICTOR_AGE:
        return None, "predictor-stale"
    home, away = payload.get("homeTeam") or {}, payload.get("awayTeam") or {}
    home_win = _stat(home, "gameProjection")
    if home_win is None:
        home_win = _stat(away, "teamChanceLoss")
    away_win = _stat(away, "gameProjection")
    if away_win is None:
        away_win = _stat(home, "teamChanceLoss")
    if home_win is None or away_win is None:
        return None, "no-projection"
    if home_win < 0 or away_win < 0 or home_win + away_win <= 0:
        return None, "no-projection"
    value = home_win / (home_win + away_win)
    if not 0.0 < value < 1.0:
        # A 0 or 100 is a model at its rail, not a chance we would print.
        return None, "projection-at-rail"
    return round(value, 6), "ok"


def is_priced(sources: Any) -> bool:
    """Whether a market price is in this game's blend (a `PRICE_SOURCES` value)."""
    from app.utils.aggregation import parse_source_entry
    from app.utils.probability_eligibility import is_refused

    if not isinstance(sources, dict):
        return False
    for key in PRICE_SOURCES:
        raw = sources.get(key)
        if raw is None or is_refused(raw):
            continue
        value, _ = parse_source_entry(raw)
        if value is not None:
            return True
    return False


def wants_reading(row: PredictorRow) -> bool:
    """Unpriced, or already holding an ESPN reading this task must keep current."""
    return not is_priced(row.sources) or "espn" in (row.sources or {})


def stored_reading_age(row: PredictorRow, now: datetime) -> Optional[timedelta]:
    """Age of the ESPN reading the row holds, ``None`` if it holds none.

    An entry with no stamp is treated as too old: nothing can say it is recent.
    """
    from app.utils.aggregation import parse_source_entry

    raw = (row.sources or {}).get("espn")
    if raw is None:
        return None
    _, stamp = parse_source_entry(raw)
    if stamp is None:
        return UNREFRESHED_READING_LIMIT + timedelta(seconds=1)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return now - stamp


def board_days(commence_time: datetime) -> list[str]:
    """The ESPN boards a game can sit on, as ``YYYYMMDD``, in reading order.

    ESPN dates boards in US Eastern. Under EDT a 11:30 PM Eastern start is
    03:30Z, under EST 04:30Z; reading UTC-5 and UTC-4 both covers either.
    """
    if commence_time.tzinfo is None:
        commence_time = commence_time.replace(tzinfo=timezone.utc)
    days: list[str] = []
    for offset in (5, 4):
        day = (commence_time - timedelta(hours=offset)).strftime("%Y%m%d")
        if day not in days:
            days.append(day)
    return days


def match_on_board(row: PredictorRow, board: list) -> tuple[Any, str]:
    """ESPN's game for this row via the shared authorized selector, home = home only."""
    from app.tasks.espn_sync import (
        espn_team_matches,
        espn_team_matches_distinctly,
        get_event_name_variations,
    )
    from app.utils.espn_candidate_selection import select_authorized_espn_candidate
    from app.utils.espn_helpers import ESPN_ORIENTATION_ALIGNED, espn_orientation_verdict

    home_names, away_names = get_event_name_variations(row)
    matched, reason = select_authorized_espn_candidate(
        board,
        row.commence_time,
        is_name_match=lambda ee: (
            espn_team_matches(home_names, ee.home_team)
            and espn_team_matches(away_names, ee.away_team)
        ),
        is_distinct_match=lambda ee: (
            espn_team_matches_distinctly(home_names, ee.home_team)
            and espn_team_matches_distinctly(away_names, ee.away_team)
        ),
        anchor_espn_id=row.espn_id,
    )
    if matched is None:
        return None, reason
    if espn_orientation_verdict(row, matched) != ESPN_ORIENTATION_ALIGNED:
        # A predictor's "home" is ESPN's home. Writing it onto a row whose
        # sides we cannot confirm would risk the opposite team's chance.
        return None, "orientation-not-aligned"
    return matched, "ok"


def candidate_statement(now: datetime):
    from sqlalchemy import select

    from app.models.models import Event, Sport
    from app.utils.game_pairing import PREGAME_LIVE_GRACE

    return (
        select(
            Event.id,
            Sport.key,
            Event.espn_id,
            Event.commence_time,
            Event.home_team_name,
            Event.away_team_name,
            Event.win_probability_sources,
            Event.home_team_normalized,
            Event.away_team_normalized,
            Event.home_team_alt_names,
            Event.away_team_alt_names,
        )
        .join(Sport, Sport.id == Event.sport_id)
        .where(
            Event.status == "scheduled",
            # Inside the grace the live ESPN writer may own the `espn` source.
            Event.commence_time > now + PREGAME_LIVE_GRACE,
            Event.commence_time <= now + HORIZON,
            Event.home_team_name.isnot(None),
            Event.away_team_name.isnot(None),
            Sport.key.in_(PREDICTOR_LEAGUES),
        )
        .order_by(Event.commence_time, Event.id)
    )


async def _read_espn(rows: list[PredictorRow], now: datetime, stats: dict) -> dict:
    """``{event_id: ("write", value, evidence) | ("remove", reason) | ("keep", reason)}``.

    No database session is open while ESPN is read.
    """
    from app.services.espn_api import ESPNAPIService, ESPNAuthorityDark

    plans: dict[int, tuple] = {}
    by_board: dict[tuple[str, str], list[PredictorRow]] = defaultdict(list)
    for row in rows:
        for day in board_days(row.commence_time):
            by_board[(row.sport_key, day)].append(row)

    espn = ESPNAPIService(rate_limit_delay=0.2)
    boards: dict[tuple[str, str], Optional[list]] = {}
    try:
        for key in sorted(by_board, key=lambda k: (k[1], k[0])):
            sport_key, day = key
            try:
                boards[key] = await espn.get_scoreboard(
                    sport_key, date=day, groups=BOARD_GROUPS.get(sport_key)
                )
            except Exception as exc:  # noqa: BLE001 — one board must not cost the rest
                boards[key] = None
                stats["errors"].append(f"board {sport_key}/{day}: {type(exc).__name__}")
            stats["boards_read" if boards[key] is not None else "boards_dark"] += 1

        for row in rows:
            dark = False
            matched = None
            reason = "no-name-match"
            for day in board_days(row.commence_time):
                board = boards.get((row.sport_key, day))
                if board is None:
                    dark = True
                    continue
                matched, reason = match_on_board(row, board)
                if matched is not None:
                    break
            if matched is None:
                stats["not_matched" if not dark else "board_dark_rows"] += 1
                plans[row.event_id] = ("keep", "board-dark" if dark else reason)
                continue
            try:
                payload = await espn.get_predictor(row.sport_key, str(matched.espn_id))
            except ESPNAuthorityDark:
                stats["predictor_dark"] += 1
                plans[row.event_id] = ("keep", "predictor-dark")
                continue
            except Exception as exc:  # noqa: BLE001
                stats["errors"].append(f"predictor {row.event_id}: {type(exc).__name__}")
                plans[row.event_id] = ("keep", "predictor-error")
                continue
            stats["predictors_read"] += 1
            value, why = predictor_home_probability(payload, now)
            if value is None:
                stats[f"absent_{why}"] = stats.get(f"absent_{why}", 0) + 1
                plans[row.event_id] = ("remove", why)
                continue
            plans[row.event_id] = ("write", value, {
                "basis": "espn_predictor",
                "espn_id": str(matched.espn_id),
                "last_modified": payload.get("lastModified"),
            })
    finally:
        await espn.close()
    return plans


async def _run_refresh_espn_predictor() -> dict:
    from types import SimpleNamespace

    from app.tasks.base import get_task_session
    from app.utils.nonvenue_live_push import (
        publish_committed_nonvenue_frames,
        write_nonvenue_probability,
    )

    now = datetime.now(timezone.utc)
    stats: dict[str, Any] = {
        "candidates": 0, "wanted": 0, "boards_read": 0, "boards_dark": 0,
        "not_matched": 0, "board_dark_rows": 0, "predictor_dark": 0,
        "predictors_read": 0, "written": 0, "removed": 0, "kept": 0,
        "write_errors": 0, "written_ids": [], "removed_ids": [], "errors": [],
    }

    async with get_task_session() as session:
        result = await session.execute(candidate_statement(now))
        rows = [
            PredictorRow(
                event_id=r[0], sport_key=r[1],
                espn_id=str(r[2]) if r[2] is not None else None,
                commence_time=r[3], home_team_name=r[4], away_team_name=r[5],
                sources=r[6] if isinstance(r[6], dict) else {},
                home_team_normalized=r[7], away_team_normalized=r[8],
                home_team_alt_names=r[9], away_team_alt_names=r[10],
            )
            for r in result.all()
        ]
    stats["candidates"] = len(rows)
    stats["mode"] = predictor_mode()
    if stats["mode"] == "withdraw":
        rows = [row for row in rows if "espn" in (row.sources or {})]
    else:
        rows = [row for row in rows if wants_reading(row)]
    stats["wanted"] = len(rows)
    if not rows:
        stats["status"] = "no_candidates"
        return stats

    if stats["mode"] == "withdraw":
        plans = {row.event_id: ("remove", "switched-off") for row in rows}
    else:
        plans = await _read_espn(rows, now, stats)

    async with get_task_session(reuse_publication_client=True) as session:
        for row in rows:
            plan = plans.get(row.event_id, ("keep", "unplanned"))
            age = stored_reading_age(row, now)
            if plan[0] == "keep":
                if age is None or age <= UNREFRESHED_READING_LIMIT:
                    stats["kept"] += 1
                    continue
                plan = ("remove", f"unrefreshed-{plan[1]}")
            if plan[0] == "remove" and age is None:
                continue  # nothing stored, nothing to withdraw
            # Scalars only (gotcha #6): a rollback below must not expire a row
            # the next iteration reads.
            target = SimpleNamespace(id=row.event_id)
            try:
                if plan[0] == "write":
                    await write_nonvenue_probability(
                        session, target, "espn", plan[1], evidence=plan[2],
                    )
                    stats["written"] += 1
                    if len(stats["written_ids"]) < 40:
                        stats["written_ids"].append(row.event_id)
                else:
                    await write_nonvenue_probability(
                        session, target, "espn", None,
                        evidence={"basis": "espn_predictor", "withdrawn": plan[1]},
                    )
                    stats["removed"] += 1
                    if len(stats["removed_ids"]) < 40:
                        stats["removed_ids"].append(row.event_id)
                await session.commit()
                await publish_committed_nonvenue_frames(session)
            except Exception as exc:  # noqa: BLE001 — one game must not cost the rest (gotcha #42)
                await session.rollback()
                stats["write_errors"] += 1
                stats["errors"].append(f"write {row.event_id}: {type(exc).__name__}")
                logger.warning("espn predictor write failed for %s", row.event_id, exc_info=True)

    stats["errors"] = stats["errors"][:20]
    stats["status"] = "ok"
    logger.info(
        "espn predictor: %d candidates, %d wanted, %d written, %d removed, %d kept, "
        "%d unmatched, %d boards dark",
        stats["candidates"], stats["wanted"], stats["written"], stats["removed"],
        stats["kept"], stats["not_matched"], stats["boards_dark"],
    )
    return stats
