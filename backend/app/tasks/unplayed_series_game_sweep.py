"""#11152 — retire the playoff game left on the schedule after its series ended.

**SHIP: Sports stops offering Brewers–Dodgers Game 5 after the series ended.**
(Pillar: TRUTH.)

The judgement is :mod:`app.utils.unplayed_series_games`; this is the half that
reads our rows and ESPN's daily boards and writes the retirement.

WHAT IT WRITES
══════════════

``status = 'voided'`` plus one ``event_tags`` element,
``provenance:unplayed-series-game:espn:<clinching espn id>``. ``voided`` is the
existing "a game that will not be played" state: every list surface reaches
events through a status allowlist that excludes it, and ``GET /api/events/{id}``
answers 410 "a game that will not be played". No ``futures_markets`` row is read
or written — a venue closes its own conditional-game markets (15330460's two
Polymarket markets were closed without a winner before this ran).

D51: the prior status and tags are banked in :data:`BAK_TABLE` first, and
``scripts/restore_11152_unplayed_series_games.py --apply`` puts each banked row
back while it is still the row this sweep voided.

THE SWEEP RUNS NO DDL. :data:`BAK_TABLE` is created only by the attended packet
(``artifacts/live-11152/apply_15330460.sql``) — notice 47(c): DDL is admitted
when a person runs it, never by an hourly task after a release. While the table
is absent the sweep writes nothing and returns ``failed`` with
``refused: "no_backup_table"``, so the missing setup stays loud.

THE WRITE IS A COMPARE-AND-SET
══════════════════════════════

The plan reads a row, then ESPN's boards, then writes — seconds apart, on a
write-hot table. The UPDATE re-asserts everything the plan judged: the status
it read, still no ESPN id, the scores it read (``IS NOT DISTINCT FROM``), the
start it read. A row that moved in the gap is left for the next pass.

VERDICT CONTRACT
════════════════

``complete``  every board in the window was read and every retirement the rule
              can decide landed (usually none: clinches are episodic).
``partial``   a planned retirement did not land (read back), or a board in the
              window was dark.
``failed``    the population read raised, every board was dark, the plan
              exceeded its ceiling, or the backup table does not exist.
``no_work``   no candidate rows in the window (no board is read), or a dry run.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone

from app.tasks.mlb_reschedule_ghost_sweep import load_rows, window_days
from app.utils.unplayed_series_games import (
    RETIRABLE_STATUSES,
    TAG_PREFIX,
    SeriesRow,
    plan_unplayed_series_games,
    retirement_tag,
    series_board_game_from_espn,
)

SPORT_KEY = "baseball_mlb"

#: D51 backup. Created by the attended packet for 15330460 and never by this
#: task; the sweep, that packet and the restore share one undo.
BAK_TABLE = "bak_11152_unplayed_series_games"

_BAK_EXISTS = f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL"

#: Wide enough back to reach a clinch several days before a stale row, and ahead
#: to a "Game 7" a few days out. The rows are read one day wider each side.
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_LOOKAHEAD_DAYS = 3

#: A clinch can leave at most three "if necessary" rows (games 5–7 of a
#: best-of-seven), and a few series clinch in one window. More than this is a
#: pairing regression, and the plan is refused, never trimmed.
MAX_EXPECTED_RETIREMENTS = 8


def build_rows(rows) -> list[SeriesRow]:
    return [
        SeriesRow(
            event_id=r.id,
            home_team_name=r.home_team_name,
            away_team_name=r.away_team_name,
            commence_time=r.commence_time,
            espn_id=str(r.espn_id) if r.espn_id else None,
            status=str(r.status or ""),
            home_score=r.home_score,
            away_score=r.away_score,
            is_retirement_tagged=TAG_PREFIX in (r.tags_text or ""),
        )
        for r in rows
    ]


def has_candidates(rows: list[SeriesRow]) -> bool:
    """Is there any row the rule could retire? If not, no board is read."""
    return any(
        not r.espn_id
        and not r.is_scored
        and not r.is_retirement_tagged
        and r.status in RETIRABLE_STATUSES
        for r in rows
    )


async def fetch_boards(days: list[date], sport_key: str = SPORT_KEY) -> dict:
    """ESPN's board for each day: a tuple of games, or ``None`` when dark.

    The raw body (``get_combat_card_board``), because the parsed scoreboard
    drops ``series`` and ``season``.
    """
    from app.services.espn_api import get_espn_service

    service = get_espn_service()
    boards: dict = {}
    for day in days:
        body = await service.get_combat_card_board(
            sport_key, dates=day.strftime("%Y%m%d")
        )
        if body is None:
            boards[day] = None
            continue
        games = (series_board_game_from_espn(e) for e in body.get("events") or [])
        boards[day] = tuple(g for g in games if g is not None)
    return boards


async def backup_table_exists(session) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(_BAK_EXISTS))).scalar_one())


async def bank_rows(session, retirements, current: dict[int, tuple]) -> int:
    """Bank each row's status and tags; the first banked value wins."""
    from sqlalchemy import text

    banked = 0
    for r in retirements:
        status, tags = current[r.event_id]
        result = await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} "
                "(event_id, clinching_espn_id, old_status, old_tags) "
                "VALUES (:eid, :cid, :status, :tags) ON CONFLICT (event_id) DO NOTHING"
            ),
            {"eid": r.event_id, "cid": r.clinching_espn_id, "status": status, "tags": tags},
        )
        banked += result.rowcount or 0
    await session.commit()
    return banked


_CAS_WRITE_SQL = """
UPDATE events
   SET status = 'voided',
       event_tags = COALESCE(event_tags, '[]'::jsonb) || CAST(:tag_array AS jsonb)
 WHERE id = :eid
   AND status = :status
   AND NULLIF(espn_id, '') IS NULL
   AND home_score IS NOT DISTINCT FROM :home_score
   AND away_score IS NOT DISTINCT FROM :away_score
   AND commence_time = :commence_time
"""


def observed_state(rows) -> dict[int, tuple]:
    """What the planner read: ``(status, espn_id, home, away, commence_time)``."""
    return {
        r.id: (r.status, r.espn_id, r.home_score, r.away_score, r.commence_time)
        for r in rows
    }


async def write_retirements(session, retirements, observed: dict[int, tuple]):
    """Void each row, ONE ROW PER TRANSACTION, only while it is as the plan saw it.

    Returns ``(written, failed_ids)``. A guarded write that touched no row is
    read back by the caller (gotcha #53).
    """
    from sqlalchemy import text

    written, failed = 0, []
    for r in retirements:
        seen = observed.get(r.event_id)
        if seen is None or seen[1]:
            failed.append(r.event_id)
            continue
        status, _espn, home, away, commence = seen
        params = {
            "tag_array": json.dumps([retirement_tag(r.clinching_espn_id)]),
            "eid": r.event_id,
            "status": status,
            "home_score": home,
            "away_score": away,
            "commence_time": commence,
        }
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(text(_CAS_WRITE_SQL), params)
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {r.event_id} after 3 attempts: {exc}")
                    failed.append(r.event_id)
                else:
                    await asyncio.sleep(attempt)
    return written, failed


_READBACK_SQL = """
SELECT id, status, espn_id, home_score, away_score, commence_time
  FROM events
 WHERE id = ANY(:ids)
"""


async def read_back(session, ids, observed: dict[int, tuple]):
    """``(voided, changed)``: rows now voided, and rows that moved under us."""
    from sqlalchemy import text

    if not ids:
        return [], []
    rows = (await session.execute(text(_READBACK_SQL), {"ids": list(ids)})).all()
    now = {r.id: r for r in rows}
    voided, changed = [], []
    for eid in ids:
        r = now.get(eid)
        if r is not None and r.status == "voided":
            voided.append(eid)
            continue
        state = (
            None
            if r is None
            else (r.status, r.espn_id or None, r.home_score, r.away_score, r.commence_time)
        )
        seen = observed[eid]
        if state != (seen[0], seen[1] or None, seen[2], seen[3], seen[4]):
            changed.append(eid)
    return voided, changed


async def run_unplayed_series_game_sweep(
    *,
    apply: bool = True,
    lookback: int = DEFAULT_LOOKBACK_DAYS,
    lookahead: int = DEFAULT_LOOKAHEAD_DAYS,
    sport_key: str = SPORT_KEY,
) -> dict:
    """One pass: read rows and boards, plan, bank, void."""
    from app.tasks.base import get_task_session

    now = datetime.now(timezone.utc)
    summary: dict = {
        "task": "unplayed_series_game_sweep",
        "issue": "#11152",
        "sport_key": sport_key,
        "apply": apply,
        "measured": True,
        "lookback_days": lookback,
        "lookahead_days": lookahead,
    }

    async with get_task_session() as session:
        try:
            raw_rows = await load_rows(
                session, lookback=lookback, lookahead=lookahead, sport_key=sport_key
            )
        except Exception as exc:  # noqa: BLE001 — "I could not look" is not "nothing to do"
            await session.rollback()
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "reason": f"population read raised: {type(exc).__name__}: {exc}"[:300],
            }

        rows = build_rows(raw_rows)
        summary["rows_read"] = len(rows)
        if not has_candidates(rows):
            return {
                **summary,
                "terminal": "no_work",
                "written": 0,
                "reason": "no unanchored, unscored row on the schedule shelf in the window",
            }

        boards = await fetch_boards(
            window_days(now, lookback=lookback, lookahead=lookahead), sport_key
        )
        plan = plan_unplayed_series_games(rows, boards)
        retirements = plan.retirements
        summary.update(
            {
                "board_days": len(boards),
                "dark_days": [d.isoformat() for d in plan.dark_days],
                "board_games_read": plan.board_games_read,
                "clinched_series_seen": plan.clinched_series_seen,
                "already_retired": plan.already_retired,
                "to_write": len(retirements),
                "retirement_sample": [
                    {
                        "event_id": r.event_id,
                        "clinching_espn_id": r.clinching_espn_id,
                        "clinching_event_id": r.clinching_event_id,
                        "reason": r.reason,
                    }
                    for r in retirements[:10]
                ],
                "refusals": len(plan.refusals),
                "refusal_sample": plan.refusals[:20],
            }
        )

        if boards and len(plan.dark_days) == len(boards):
            return {
                **summary,
                "measured": False,
                "terminal": "failed",
                "written": 0,
                "reason": "every ESPN board in the window was dark — nothing could be judged",
            }

        if len(retirements) > MAX_EXPECTED_RETIREMENTS:
            return {
                **summary,
                "terminal": "failed",
                "written": 0,
                "reason": (
                    f"the plan retires {len(retirements)} row(s), above the "
                    f"ceiling {MAX_EXPECTED_RETIREMENTS} — what a pairing regression "
                    f"looks like. Re-measure before writing."
                ),
            }

        dark_note = (
            f"; ESPN's board was dark for {len(plan.dark_days)} day(s): "
            f"{[d.isoformat() for d in plan.dark_days]}"
            if plan.dark_days
            else ""
        )

        if not retirements:
            return {
                **summary,
                "terminal": "partial" if plan.dark_days else "complete",
                "written": 0,
                "banked": 0,
                "reason": (
                    f"no unplayed series game left to retire "
                    f"({plan.clinched_series_seen} finished series seen, "
                    f"{plan.already_retired} already retired)" + dark_note
                ),
            }

        if not apply:
            return {
                **summary,
                "terminal": "no_work",
                "written": 0,
                "reason": f"dry run — {len(retirements)} retirement(s) withheld",
            }

        if not await backup_table_exists(session):
            return {
                **summary,
                "terminal": "failed",
                "refused": "no_backup_table",
                "written": 0,
                "banked": 0,
                "reason": (
                    f"{len(retirements)} retirement(s) withheld: the backup table "
                    f"{BAK_TABLE} does not exist. This task runs no DDL; the attended "
                    f"packet (artifacts/live-11152/apply_15330460.sql) creates it."
                ),
            }

        current = {r.id: (str(r.status), r.tags_text or "[]") for r in raw_rows}
        banked = await bank_rows(session, retirements, current)
        observed = observed_state(raw_rows)
        written, failed = await write_retirements(session, retirements, observed)
        ids = [r.event_id for r in retirements]
        voided, changed = await read_back(session, ids, observed)
        missing = [
            eid for eid in ids if eid not in voided and eid not in changed and eid not in failed
        ]

        problems = []
        if failed:
            problems.append(f"{len(failed)} row(s) exhausted their retries: {failed[:20]}")
        if missing:
            problems.append(f"{len(missing)} planned row(s) are not voided: {missing[:20]}")

        return {
            **summary,
            "terminal": "partial" if (problems or plan.dark_days) else "complete",
            "written": written,
            "banked": banked,
            "voided": voided[:20],
            "failed_ids": failed[:20],
            "not_voided": missing[:20],
            "changed_under_us": changed[:20],
            "reason": (
                "; ".join(problems)
                if problems
                else f"{len(voided)} game(s) that will not be played left the schedule"
            )
            + (
                f"; {len(changed)} row(s) changed between read and write and were "
                f"left alone: {changed[:20]}"
                if changed
                else ""
            )
            + dark_note,
            "undo": "python3 scripts/restore_11152_unplayed_series_games.py --apply",
        }
