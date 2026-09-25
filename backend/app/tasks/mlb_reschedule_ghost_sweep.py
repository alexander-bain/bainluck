"""#8547 half 2 — label the MLB row left behind when a game moves to another day.

**SHIP: search for "orioles" stops listing a Saturday Orioles @ Yankees game
that will not be played (row 15316409), and Kalshi's market for it reaches
Friday's game 1 page.** (Pillar: MATCHING.)

The judgement is :mod:`app.utils.mlb_reschedule_ghosts`; this is the half that
reads our MLB rows and ESPN's daily boards and writes the label.

WHAT IT WRITES
══════════════

One element on the ghost's ``event_tags``: ``provenance:duplicate-of:<canonical>``
— the same label, written by the same helpers, as
:mod:`app.tasks.soccer_ghost_twin_sweep`. Its read side already ships: the rails
and search hide the ghost, and ``_build_game_markets`` folds its markets onto the
canonical page (``folded_event_ids``). No ``futures_markets`` row moves, nothing
is merged or deleted; the prior array is banked first (D51) and
``scripts/restore_8547_mlb_reschedule_ghost_tags.py --apply`` removes exactly the
one element.

THE WINDOW LOOKS BACK
═════════════════════

A ghost whose day has passed is worse than one still ahead: it sits as an
unplayed game with no result forever. So the window covers past days as well as
the next few, and a board is read for every ET day in it (ESPN's MLB scoreboard
refuses a date range — measured 2026-09-25, HTTP 400 — so one call per day).

VERDICT CONTRACT
════════════════

``complete``  every board in the window was read, the band held, and every ghost
              the rule can decide carries its label (usually none: reschedules
              are episodic).
``partial``   a planned tag did not land (read back from disk), or a board in the
              window was dark so the window was not fully read.
``failed``    the population read raised (``measured: false``), the anchor join
              collapsed, the plan exceeded its ceiling, or the fold is unwired.
``no_work``   no MLB rows and no board games in the window (the off-season), or a
              dry run with tags withheld.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.services.anchor_channel import DUPLICATE_TAG_PREFIX
from app.tasks.soccer_ghost_twin_sweep import fold_is_live, tagged_now, write_tags
from app.utils.mlb_reschedule_ghosts import (
    MlbRow,
    board_game_from_espn,
    local_date,
    plan_reschedule_ghosts,
)
from app.utils.soccer_ghost_twins import row_has_final_score

SPORT_KEY = "baseball_mlb"

#: D51 backup, its own table so this undo never touches another sweep's ghosts.
BAK_TABLE = "bak_8547_mlb_reschedule_ghost_tags"

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_LOOKAHEAD_DAYS = 3

#: Non-vacuity floor on the canonical side's join: board games whose ESPN id one
#: of our rows carries. Measured 2026-09-25: 116 of 151 MLB rows in -8d/+4d carry
#: an espn_id against ~15 board games a day, so a healthy in-season window joins
#: well over a hundred. The floor applies only once the boards themselves are
#: busy (:data:`BUSY_BOARD_GAMES`), so the season's edges and the off-season are
#: not read as a broken join.
MIN_ANCHORED_BOARD_GAMES = 20
BUSY_BOARD_GAMES = 60

#: Ceiling on the plan. Reschedules come a handful a week; a pairing regression
#: labelling real games shows up here first.
MAX_EXPECTED_TAGS = 10

_POPULATION_SQL = """
SELECT e.id,
       e.home_team_name,
       e.away_team_name,
       e.commence_time,
       e.home_score,
       e.away_score,
       e.espn_id,
       CAST(COALESCE(e.event_tags, '[]'::jsonb) AS text) AS tags_text
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.commence_time >= now() - make_interval(days => :lookback)
   AND e.commence_time <= now() + make_interval(days => :lookahead)
   AND e.status NOT IN ('voided', 'merged')
 ORDER BY e.id
"""


async def load_rows(session, *, lookback: int, lookahead: int):
    """Every MLB row in the window, one day wider each side than the boards so a
    row near midnight ET is never outside the read while its day is inside it."""
    from sqlalchemy import text

    return (
        await session.execute(
            text(_POPULATION_SQL),
            {
                "sport_key": SPORT_KEY,
                "lookback": lookback + 1,
                "lookahead": lookahead + 1,
            },
        )
    ).all()


def window_days(now: datetime, *, lookback: int, lookahead: int) -> list[date]:
    today = local_date(now)
    return [
        today + timedelta(days=offset) for offset in range(-lookback, lookahead + 1)
    ]


async def fetch_boards(days: list[date]) -> dict:
    """ESPN's MLB board for each day: a tuple of games, or ``None`` when dark.

    ``get_combat_card_board`` is the client's raw-scoreboard read; nothing in it
    is combat-specific, and the raw body is what carries ``notes``, which the
    parsed ``get_scoreboard`` drops.
    """
    from app.services.espn_api import get_espn_service

    service = get_espn_service()
    boards: dict = {}
    for day in days:
        body = await service.get_combat_card_board(
            SPORT_KEY, dates=day.strftime("%Y%m%d")
        )
        if body is None:
            boards[day] = None
            continue
        games = (board_game_from_espn(e) for e in body.get("events") or [])
        boards[day] = tuple(g for g in games if g is not None)
    return boards


def build_rows(rows) -> list[MlbRow]:
    return [
        MlbRow(
            event_id=r.id,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            commence_time=r.commence_time,
            espn_id=str(r.espn_id) if r.espn_id else None,
            has_final_score=row_has_final_score(
                home_score=r.home_score, away_score=r.away_score
            ),
            is_duplicate_tagged=DUPLICATE_TAG_PREFIX in (r.tags_text or ""),
        )
        for r in rows
    ]


def band_refusal_reason(plan) -> str | None:
    """Why this plan must NOT be applied, or ``None``. Pure; asked every run."""
    if (
        plan.board_games_read >= BUSY_BOARD_GAMES
        and plan.anchored_board_games < MIN_ANCHORED_BOARD_GAMES
    ):
        return (
            f"only {plan.anchored_board_games} of {plan.board_games_read} ESPN board "
            f"games join a row by espn_id, below the floor {MIN_ANCHORED_BOARD_GAMES} — "
            f"the canonical side has lost its anchor (a renamed sport key, a stopped "
            f"espn_id writer). Re-measure before writing."
        )
    if len(plan.tags) > MAX_EXPECTED_TAGS:
        return (
            f"the plan labels {len(plan.tags)} row(s), above the ceiling "
            f"{MAX_EXPECTED_TAGS} — what a pairing regression looks like. "
            f"Re-measure before writing."
        )
    return None


async def ensure_backup(session, tags, current_tags: dict[int, str]) -> int:
    """Bank each ghost's current ``event_tags``; the first banked value wins."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  canonical_id bigint NOT NULL,"
            "  old_tags text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()
    banked = 0
    for tag in tags:
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, canonical_id, old_tags) "
                "VALUES (:eid, :cid, :old) ON CONFLICT (event_id) DO NOTHING"
            ),
            {
                "eid": tag.ghost_id,
                "cid": tag.canonical_id,
                "old": current_tags.get(tag.ghost_id, "[]"),
            },
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


async def run_mlb_reschedule_ghost_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
) -> dict:
    """One scheduled pass: read rows and boards, plan, bank, tag."""
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    summary: dict = {
        "task": "mlb_reschedule_ghost_sweep",
        "issue": "#8547",
        "apply": apply,
        "measured": True,
        "lookback_days": lookback,
        "lookahead_days": lookahead,
    }

    async with get_task_session() as session:
        try:
            raw_rows = await load_rows(session, lookback=lookback, lookahead=lookahead)
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        boards = await fetch_boards(
            window_days(now, lookback=lookback, lookahead=lookahead)
        )
        plan = plan_reschedule_ghosts(build_rows(raw_rows), boards)
        folding = fold_is_live()
        summary.update(
            {
                "rows_read": plan.rows_considered,
                "board_days": len(boards),
                "dark_days": [d.isoformat() for d in plan.dark_days],
                "board_games_read": plan.board_games_read,
                "anchored_board_games": plan.anchored_board_games,
                "rescheduled_games_seen": plan.rescheduled_games_seen,
                "already_tagged": plan.already_tagged,
                "tags_to_write": len(plan.tags),
                "tag_sample": [
                    {
                        "ghost": t.ghost_id,
                        "canonical": t.canonical_id,
                        "reason": t.reason,
                    }
                    for t in plan.tags[:10]
                ],
                "refusals": len(plan.refusals),
                "refusal_sample": plan.refusals[:20],
                "fold_live": folding,
            }
        )

        if len(plan.dark_days) == len(boards):
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "written": 0,
                "reason": "every ESPN board in the window was dark — nothing could be judged",
            }

        if plan.rows_considered == 0 and plan.board_games_read == 0:
            return {
                **summary,
                "terminal": "no_work",
                "written": 0,
                "reason": "no MLB rows and no ESPN games in the window (off-season)",
            }

        blocked = band_refusal_reason(plan)
        if blocked:
            return {**summary, "terminal": "failed", "reason": blocked, "written": 0}

        if plan.tags and not folding:
            return {
                **summary,
                "terminal": "failed",
                "written": 0,
                "reason": (
                    f"_build_game_markets no longer calls folded_event_ids, so "
                    f"{len(plan.tags)} ghost(s) were NOT tagged — tagging without the "
                    f"fold moves their markets out of reach"
                ),
            }

        dark_note = (
            f"; ESPN's board was dark for {len(plan.dark_days)} day(s): "
            f"{[d.isoformat() for d in plan.dark_days]}"
            if plan.dark_days
            else ""
        )

        if not plan.tags:
            return {
                **summary,
                "terminal": "partial" if plan.dark_days else "complete",
                "written": 0,
                "banked": 0,
                "reason": (
                    f"no reschedule ghost left to label ({plan.rescheduled_games_seen} "
                    f"rescheduled game(s) seen, {plan.already_tagged} already labelled)"
                    + dark_note
                ),
            }

        if not apply:
            return {
                **summary,
                "terminal": "no_work",
                "written": 0,
                "reason": f"dry run — {len(plan.tags)} tag(s) withheld",
            }

        current = {r.id: (r.tags_text or "[]") for r in raw_rows}
        banked = await ensure_backup(session, plan.tags, current)
        written, failed = await write_tags(session, plan.tags)
        after = await tagged_now(session, [t.ghost_id for t in plan.tags])
        still_untagged = [t.ghost_id for t in plan.tags if t.ghost_id not in after]

        problems = []
        if failed:
            problems.append(
                f"{len(failed)} row(s) exhausted their retries: {failed[:20]}"
            )
        if still_untagged:
            problems.append(
                f"{len(still_untagged)} planned ghost(s) carry no tag: {still_untagged[:20]}"
            )

        return {
            **summary,
            "terminal": "partial" if (problems or plan.dark_days) else "complete",
            "written": written,
            "banked": banked,
            "failed_ids": failed[:20],
            "still_untagged": still_untagged[:20],
            "reason": (
                "; ".join(problems)
                if problems
                else f"{written} moved game(s) stopped being listed on the day they left"
            )
            + dark_note,
            "undo": "python3 scripts/restore_8547_mlb_reschedule_ghost_tags.py --apply",
        }
