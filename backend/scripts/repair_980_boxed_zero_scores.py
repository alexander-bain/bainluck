"""#980 — a finished game whose box score we already hold stops reading 0 - 0.

THE SHIP. A settled card ("FINAL") that prints `0 - 0` for a baseball or
basketball game a reader can look up and see was 4 - 9. #980 fixed the forward
path; this is the unchecked follow-up on its own acceptance list:

    [ ] re-feed the box_score'd 0-total events (one-time backfill w/ a
        checked-marker to avoid postponed re-poll)

------------------------------------------------------------------------------
WHY THE FORWARD PATH NEVER REACHES THEM
------------------------------------------------------------------------------

`espn_sync._backfill_box_scores` already re-feeds a boxed 0-total row (#982,
`b06bdcc9`) — ONCE. Every processed row is stamped
`box_score_data.scores_checked_at` whether or not the score was corrected, and
`_corrected_final_score` declines to write unless ESPN's `is_final` is set
(#981). A row whose single check met a missing/false `is_final` is stamped
checked and is never selected again. The 2026-08-14 recount on this issue
measured the result: 290 impossible-sport 0-total boxed finals, 98.6% from
March–May, 0 accrued in August — a frozen backlog no forward-only fix can see.

So this pass deliberately IGNORES `scores_checked_at` (the stamp that froze
the cohort) and carries its OWN checked marker, keyed by the anchor it asked.

------------------------------------------------------------------------------
THE AUTHORITY DECIDES EVERY WRITE — REUSED, NEVER RESTATED
------------------------------------------------------------------------------

A row is written only when ESPN's own summary for the row's own `espn_id`:

  * IS that id (`anchor_is_a_different_id` — provider identity),
  * is the same game: start within 12h, both clubs in the same home/away
    orientation, no scored twin row — #5841's
    :func:`anchor_refusal_reason` / :func:`scored_twin`, IMPORTED. That rule
    refused a real borrowed anchor (a June summary stamped on an August card);
    two copies of it are how one of them rots,
  * says FINISHED (`post`, not `stopped_without_result` — postponements refused),
  * carries a score that is not 0 - 0 (ESPN 0 - 0 is the row being RIGHT),

and then the write itself is decided by #980's shipped
:func:`app.tasks.espn_sync._corrected_final_score` — "our total is 0 AND ESPN's
is positive", so a real non-zero score is never overwritten (gotcha #21).

Writes `home_score` and `away_score`. Nothing else: not `status`, not
`completed_at`, not `box_score_data`, and never `is_winner` — grading stays the
resolver's, off the corrected score, on its own cadence. No winner is inferred
from a price or a curve.

------------------------------------------------------------------------------
THE CHECKED MARKER, AND THE D51 RESTORE POINT, ARE ONE TABLE
------------------------------------------------------------------------------

:data:`BAK_TABLE`, created only by `--apply` (runtime DDL, attended invocation —
notice 47(c); the same shape as #5841's `bak_5841_zero_zero_scores`). One row per
`(event_id, espn_id)` adjudicated:

  * `WRITE`     pre-image AND post-image banked BEFORE the write; `written_at`
                set in the SAME transaction as the CAS write.
  * `REFUSED`   the authority's answer was terminal (postponed, real 0 - 0,
                different game/date/id, scored twin) — marked so it is never
                asked again.
  * `NO_ANSWER` ESPN returned nothing for the anchor — marked; `--ignore-marker`
                re-asks.

A row is re-selected only if its marker is for a DIFFERENT `espn_id` (the anchor
was since corrected — a new question), or it is a `WRITE` whose CAS declined
(`written_at IS NULL`: the row moved, so nothing was decided). A transient ESPN
exception is NOT marked; it is counted and exits 1.

Why not a `box_score_data` key like `scores_checked_at`: the forward path
rewrites that dict wholesale, so a merged key can be clobbered, and a JSONB
merge is a second statement shape per dialect. The bank table already has to
exist for the undo; making it the marker adds no storage and no schema.

------------------------------------------------------------------------------
RUNNING IT — NOT AUTHORIZED BY THE PACKET THAT BUILT IT
------------------------------------------------------------------------------

Every mode is a bounded preview unless `--apply` is given. Preview writes
nothing and creates nothing.

    python3 scripts/repair_980_boxed_zero_scores.py --selftest
    python3 scripts/repair_980_boxed_zero_scores.py                 # preview, 25 oldest
    python3 scripts/repair_980_boxed_zero_scores.py --limit 100 --apply
    python3 scripts/repair_980_boxed_zero_scores.py --restore         # undo preview
    python3 scripts/repair_980_boxed_zero_scores.py --restore --apply # undo

Heroku (gotcha #48; PROJECT_PATH=backend so scripts are at /app):

    heroku run:detached "python3 scripts/repair_980_boxed_zero_scores.py" -a bainluck
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import DateTime, Integer, String, bindparam, text  # noqa: E402

from app.tasks.espn_sync import _corrected_final_score  # noqa: E402
from app.utils.event_completion import SETTLED_STATUSES  # noqa: E402
from scripts.repair_5841_zero_zero_finals_from_the_authority import (  # noqa: E402
    DRAW_CAPABLE_PREFIXES,
    anchor_refusal_reason,
    as_aware,
    scored_twin,
)

BAK_TABLE = "bak_980_boxed_zero_scores"

#: A settled row this young may still be receiving its final from the live
#: pass; the forward path owns it.
SETTLED_FOR_HOURS = 12

#: Rows per run. Preview default is small so a look is cheap; `--apply` honours
#: the same bound so a sweep is a sequence of reviewed slices.
DEFAULT_LIMIT = 25
MAX_LIMIT = 200

#: Ceiling on the WHOLE eligible population (not the slice). The 2026-08-14
#: recount measured 290 impossible-sport rows and a frozen cohort; an order of
#: magnitude past that means a writer is producing them again — find it first.
MAX_EXPECTED_POPULATION = 600

#: ESPN rate limit between summary fetches, as the forward path sleeps.
FETCH_PAUSE_SECONDS = 0.5

VERDICT_WRITE = "WRITE"
VERDICT_REFUSED = "REFUSED"
VERDICT_NO_ANSWER = "NO_ANSWER"
VERDICT_ERROR = "ERROR"  # transient: never marked

assert SETTLED_STATUSES, "SETTLED_STATUSES is empty — this script has no subject"

_DRAW_CAPABLE_SQL = " ".join(
    f"AND COALESCE(s.key, '') NOT LIKE '{prefix}%'" for prefix in DRAW_CAPABLE_PREFIXES
)

#: The population. `box_score_data IS NOT NULL` is the #980 follow-up's whole
#: subject (the unboxed arm is the forward path's); `scores_checked_at` is NOT
#: consulted, on purpose — see the module docstring.
_TARGET_WHERE = f"""
       e.status IN :settled
   AND e.espn_id IS NOT NULL
   AND e.box_score_data IS NOT NULL
   AND COALESCE(e.home_score, 0) = 0
   AND COALESCE(e.away_score, 0) = 0
   AND e.commence_time IS NOT NULL
   AND e.commence_time < :settled_before
   {_DRAW_CAPABLE_SQL}
"""

#: The checked marker, as a clause. Only spliced in when the bank exists.
_MARKER_WHERE = f"""
   AND NOT EXISTS (
       SELECT 1 FROM {BAK_TABLE} b
        WHERE b.event_id = e.id
          AND b.espn_id = e.espn_id
          AND (b.verdict <> '{VERDICT_WRITE}' OR b.written_at IS NOT NULL))
"""

_SELECT_COLUMNS = """
SELECT e.id, e.status, e.home_score, e.away_score, e.espn_id,
       e.home_team_name, e.away_team_name, e.commence_time, e.sport_id,
       s.key AS sport_key
  FROM events e
  JOIN sports s ON s.id = e.sport_id
"""


def candidates_sql(*, marker: bool, only_ids: bool) -> str:
    """Oldest first within the slice: the cohort is frozen and old, and a
    newest-first bounded pass never reaches the April tail (gotcha #41). The
    marker is what makes successive slices advance."""
    return (
        _SELECT_COLUMNS
        + " WHERE "
        + _TARGET_WHERE
        + (_MARKER_WHERE if marker else "")
        + (" AND e.id IN :only_ids" if only_ids else "")
        + " ORDER BY e.commence_time, e.id LIMIT :limit"
    )


def population_sql(*, marker: bool) -> str:
    return (
        "SELECT COUNT(*) FROM events e JOIN sports s ON s.id = e.sport_id WHERE "
        + _TARGET_WHERE
        + (_MARKER_WHERE if marker else "")
    )


def statement(sql: str, *, only_ids: bool = False):
    params = [
        bindparam("settled", expanding=True, type_=String),
        bindparam("settled_before", type_=DateTime(timezone=True)),
    ]
    if ":limit" in sql:
        params.append(bindparam("limit", type_=Integer))
    if only_ids:
        params.append(bindparam("only_ids", expanding=True, type_=Integer))
    return text(sql).bindparams(*params)


#: The write. Re-states everything it adjudicated: still zero-total, same
#: status, same anchor. A score arriving from any other writer between plan and
#: write, an un-settle, or a re-anchor all make this touch 0 rows.
_WRITE_SQL = """
UPDATE events
   SET home_score = :home_score, away_score = :away_score
 WHERE id = :eid
   AND COALESCE(home_score, 0) = 0
   AND COALESCE(away_score, 0) = 0
   AND status = :status
   AND espn_id = :espn_id
"""

_MARK_WRITTEN_SQL = f"""
UPDATE {BAK_TABLE}
   SET written_at = CURRENT_TIMESTAMP
 WHERE event_id = :eid AND espn_id = :espn_id AND verdict = '{VERDICT_WRITE}'
"""

_BAK_DDL = f"""
CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
  event_id bigint NOT NULL,
  espn_id text NOT NULL,
  verdict text NOT NULL,
  reason text,
  old_home_score integer,
  old_away_score integer,
  old_status text NOT NULL,
  new_home_score integer,
  new_away_score integer,
  checked_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
  written_at timestamptz,
  restored_at timestamptz,
  PRIMARY KEY (event_id, espn_id))
"""

#: A COMPLETED write's tuple is never replaced — its pre-image is the pre-repair
#: score, and a re-run must never bank this pass's own write as the thing to
#: restore. Every other prior verdict (a refusal re-asked under
#: `--ignore-marker`, a WRITE whose CAS declined and so changed nothing) is
#: replaced by the fresh one, so the post-image the undo compares against is
#: always the pair that is about to be written.
_BANK_SQL = f"""
INSERT INTO {BAK_TABLE}
       (event_id, espn_id, verdict, reason, old_home_score, old_away_score,
        old_status, new_home_score, new_away_score)
VALUES (:eid, :espn_id, :verdict, :reason, :old_home_score, :old_away_score,
        :old_status, :new_home_score, :new_away_score)
ON CONFLICT (event_id, espn_id) DO UPDATE SET
       verdict = excluded.verdict, reason = excluded.reason,
       old_home_score = excluded.old_home_score, old_away_score = excluded.old_away_score,
       old_status = excluded.old_status,
       new_home_score = excluded.new_home_score, new_away_score = excluded.new_away_score,
       checked_at = CURRENT_TIMESTAMP, written_at = NULL, restored_at = NULL
 WHERE NOT ({BAK_TABLE}.verdict = '{VERDICT_WRITE}' AND {BAK_TABLE}.written_at IS NOT NULL)
"""

_RESTORE_PLAN_SQL = f"""
SELECT event_id, espn_id, old_home_score, old_away_score, old_status,
       new_home_score, new_away_score
  FROM {BAK_TABLE}
 WHERE verdict = '{VERDICT_WRITE}'
   AND written_at IS NOT NULL
   AND restored_at IS NULL
 ORDER BY event_id
"""

#: The undo is an equality against the IMMUTABLE banked post-image, never an
#: inference from the current score: a row the authority has since corrected
#: to something else is not this repair's to put back (CERT-2947's lesson).
_RESTORE_SQL = """
UPDATE events
   SET home_score = :old_home_score, away_score = :old_away_score
 WHERE id = :eid
   AND home_score = :new_home_score
   AND away_score = :new_away_score
   AND status = :old_status
   AND espn_id = :espn_id
"""

_MARK_RESTORED_SQL = f"""
UPDATE {BAK_TABLE}
   SET restored_at = CURRENT_TIMESTAMP
 WHERE event_id = :eid AND espn_id = :espn_id
"""

_SCORE_BINDS = ("home_score", "away_score", "old_home_score", "old_away_score",
                "new_home_score", "new_away_score")


def typed(sql: str):
    """Score binds typed Integer so a NULL pre-image binds on asyncpg."""
    return text(sql).bindparams(
        *[bindparam(name, type_=Integer) for name in _SCORE_BINDS if f":{name}" in sql]
    )


async def bank_exists(session) -> bool:
    """Does the marker/bank table exist? Preview must not create it."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        sql, params = "SELECT to_regclass(:name) IS NOT NULL", {"name": BAK_TABLE}
    else:
        sql = "SELECT COUNT(*) > 0 FROM sqlite_master WHERE type = 'table' AND name = :name"
        params = {"name": BAK_TABLE}
    return bool((await session.execute(text(sql), params)).scalar())


def anchor_id_refusal(row, anchor) -> str | None:
    """Provider identity: the summary ESPN returned is the one we asked for."""
    returned = getattr(anchor, "espn_id", None)
    if returned is not None and str(returned) != str(row.espn_id):
        return (
            f"anchor_is_a_different_id — asked ESPN for {row.espn_id!r}, it "
            f"answered with {returned!r}"
        )
    return None


async def adjudicate(session, espn, row) -> dict:
    """One row's verdict. The twin read is first so a refused row costs no fetch."""
    base = {"id": row.id, "espn_id": row.espn_id}
    twin = await scored_twin(session, row)
    if twin:
        return {
            **base,
            "verdict": VERDICT_REFUSED,
            "reason": (
                f"scored_twin_exists — event {twin['id']} ({twin['status']}) already "
                f"holds this fixture at {twin['score']}"
            ),
        }

    try:
        anchor = await espn.get_event(row.sport_key, row.espn_id)
    except Exception as exc:  # noqa: BLE001 — transient: report, never mark
        return {**base, "verdict": VERDICT_ERROR, "reason": f"espn_error — {exc!r}"}
    if anchor is None:
        return {
            **base,
            "verdict": VERDICT_NO_ANSWER,
            "reason": "espn_no_answer — nothing returned for this anchor (gotcha #53)",
        }

    reason = anchor_id_refusal(row, anchor) or anchor_refusal_reason(row, anchor)
    if reason:
        if "different_date" in reason and getattr(anchor, "time_valid", True) is False:
            reason += " (ESPN timeValid=false: its date is a placeholder)"
        return {**base, "verdict": VERDICT_REFUSED, "reason": reason}

    fix = _corrected_final_score(
        row.home_score, row.away_score, anchor.home_score, anchor.away_score,
        espn_is_final=True,  # anchor_refusal_reason just required `post`, not stopped
    )
    if fix is None:
        return {
            **base,
            "verdict": VERDICT_REFUSED,
            "reason": "corrected_final_score_declined — #980's helper refuses this pair",
        }
    return {
        **base,
        "verdict": VERDICT_WRITE,
        "home_score": fix[0],
        "away_score": fix[1],
        "anchor_date": as_aware(anchor.date).isoformat(),
    }


async def bank(session, verdict: dict, row) -> int:
    result = await session.execute(
        typed(_BANK_SQL),
        {
            "eid": row.id,
            "espn_id": row.espn_id,
            "verdict": verdict["verdict"],
            "reason": verdict.get("reason"),
            "old_home_score": row.home_score,
            "old_away_score": row.away_score,
            "old_status": row.status,
            "new_home_score": verdict.get("home_score"),
            "new_away_score": verdict.get("away_score"),
        },
    )
    return result.rowcount or 0


async def apply_verdicts(session, verdicts: list[dict], rows_by_id: dict) -> dict:
    """Bank every terminal verdict, then write each WRITE in its own transaction.

    Banking commits BEFORE any write: the restore point exists before the thing
    it restores. The CAS write and its `written_at` share one transaction, so
    the marker can never claim a write that rolled back.
    """
    await session.execute(text(_BAK_DDL))
    await session.commit()

    out = {"banked": 0, "written": 0, "skipped": [], "failed": [], "unbanked": []}
    banked_ids = set()
    for verdict in verdicts:
        if verdict["verdict"] == VERDICT_ERROR:
            continue
        if await bank(session, verdict, rows_by_id[verdict["id"]]):
            banked_ids.add(verdict["id"])
            out["banked"] += 1
    await session.commit()

    for verdict in verdicts:
        if verdict["verdict"] != VERDICT_WRITE:
            continue
        if verdict["id"] not in banked_ids:
            # No restore point for this exact pair — the write does not happen.
            out["unbanked"].append(verdict["id"])
            continue
        row = rows_by_id[verdict["id"]]
        params = {
            "eid": row.id,
            "home_score": verdict["home_score"],
            "away_score": verdict["away_score"],
            "status": row.status,
            "espn_id": row.espn_id,
        }
        try:
            result = await session.execute(typed(_WRITE_SQL), params)
            if result.rowcount:
                await session.execute(
                    text(_MARK_WRITTEN_SQL), {"eid": row.id, "espn_id": row.espn_id}
                )
                out["written"] += result.rowcount
            else:
                out["skipped"].append(row.id)
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — surface in the exit code
            await session.rollback()
            print(f"  FAILED event {row.id}: {exc}")
            out["failed"].append(row.id)
    return out


async def _run_inner(*, espn, session, apply: bool, limit: int, only_ids,
                     ignore_marker: bool, now: datetime, pause: float = 0.0) -> int:
    has_bank = await bank_exists(session)
    marker = has_bank and not ignore_marker
    params = {
        "settled": sorted(SETTLED_STATUSES),
        "settled_before": now - timedelta(hours=SETTLED_FOR_HOURS),
    }

    population = (await session.execute(statement(population_sql(marker=marker)), params)).scalar()
    print(f"eligible population (marker {'on' if marker else 'off'}): {population}")
    if population > MAX_EXPECTED_POPULATION:
        msg = (f"population {population} exceeds the ceiling {MAX_EXPECTED_POPULATION} "
               "— this cohort is supposed to be frozen; a writer is producing them again")
        if apply:
            print(f"\nREFUSING TO APPLY: {msg}")
            return 2
        print(f"\nband: {msg}")
    if population == 0:
        print("nothing eligible — drained, or the premise moved; re-measure before claiming either")

    sql = candidates_sql(marker=marker, only_ids=bool(only_ids))
    slice_params = {**params, "limit": limit}
    if only_ids:
        slice_params["only_ids"] = list(only_ids)
    rows = (await session.execute(statement(sql, only_ids=bool(only_ids)), slice_params)).all()
    rows_by_id = {r.id: r for r in rows}
    print(f"slice: {len(rows)} (limit {limit}, oldest first)")

    verdicts = []
    for row in rows:
        verdict = await adjudicate(session, espn, row)
        verdicts.append(verdict)
        fixture = f"{row.home_team_name} v {row.away_team_name}"
        when = as_aware(row.commence_time).isoformat()
        was = f"{row.home_score}-{row.away_score}"
        if verdict["verdict"] == VERDICT_WRITE:
            print(f"  WRITE     {row.id} [{row.sport_key}] {fixture} {when} {was} → "
                  f"{verdict['home_score']}-{verdict['away_score']} "
                  f"(espn {row.espn_id} @ {verdict['anchor_date']})")
        else:
            print(f"  {verdict['verdict']:<9} {row.id} [{row.sport_key}] {fixture} {when} — {verdict['reason']}")
        if pause:
            await asyncio.sleep(pause)

    counts = {}
    for v in verdicts:
        counts[v["verdict"]] = counts.get(v["verdict"], 0) + 1
    print(f"\nverdicts: {counts or 'none'}")
    errors = counts.get(VERDICT_ERROR, 0)

    if not apply:
        print("\nPREVIEW — nothing written, nothing created. Add --apply to bank and write.")
        return 1 if errors else 0
    if not verdicts:
        return 0

    out = await apply_verdicts(session, verdicts, rows_by_id)
    print(f"\nbanked {out['banked']} into {BAK_TABLE} · written {out['written']} · "
          f"skipped (row moved) {len(out['skipped'])} · failed {len(out['failed'])}")
    if out["skipped"]:
        print(f"  skipped ids: {out['skipped']}")
    if out["failed"]:
        print(f"  FAILED ids: {out['failed']}")
    if out["unbanked"]:
        print(f"  NOT WRITTEN, no restore point banked: {out['unbanked']}")
    return 1 if (out["failed"] or out["unbanked"] or errors) else 0


async def _restore_inner(*, session, apply: bool) -> int:
    if not await bank_exists(session):
        print(f"{BAK_TABLE} does not exist — nothing was ever applied, nothing to restore")
        return 0
    rows = (await session.execute(text(_RESTORE_PLAN_SQL))).all()
    print(f"restorable bank rows: {len(rows)}")
    for r in rows:
        print(f"  {r.event_id} espn {r.espn_id}: {r.new_home_score}-{r.new_away_score} → "
              f"{r.old_home_score}-{r.old_away_score}")
    if not apply:
        print("\nRESTORE PREVIEW — nothing written. Add --apply to restore.")
        return 0
    restored, declined, failed = 0, [], []
    for r in rows:
        params = {
            "eid": r.event_id, "espn_id": r.espn_id, "old_status": r.old_status,
            "old_home_score": r.old_home_score, "old_away_score": r.old_away_score,
            "new_home_score": r.new_home_score, "new_away_score": r.new_away_score,
        }
        try:
            result = await session.execute(typed(_RESTORE_SQL), params)
            if result.rowcount:
                await session.execute(text(_MARK_RESTORED_SQL), {"eid": r.event_id, "espn_id": r.espn_id})
                restored += result.rowcount
            else:
                declined.append(r.event_id)
            await session.commit()
        except Exception as exc:  # noqa: BLE001
            await session.rollback()
            print(f"  FAILED event {r.event_id}: {exc}")
            failed.append(r.event_id)
    print(f"\nrestored {restored} · declined (score moved since the repair — newer truth kept) "
          f"{len(declined)} · failed {len(failed)}")
    if declined:
        print(f"  declined ids: {declined}")
    return 1 if failed else 0


async def run(args) -> int:
    from app.tasks.base import get_task_session

    if args.restore:
        async with get_task_session() as session:
            return await _restore_inner(session=session, apply=args.apply)

    from app.services.espn_api import get_espn_service

    espn = get_espn_service()
    try:
        async with get_task_session() as session:
            return await _run_inner(
                espn=espn, session=session, apply=args.apply, limit=args.limit,
                only_ids=args.only_ids, ignore_marker=args.ignore_marker,
                now=datetime.now(timezone.utc), pause=FETCH_PAUSE_SECONDS,
            )
    finally:
        await espn.close()


def _selftest() -> int:
    """Offline: the reused rules answer #980's own specimens. No database."""
    from types import SimpleNamespace as NS

    def row(**kw):
        base = dict(id=1, status="completed", home_score=0, away_score=0,
                    espn_id="401815890", home_team_name="Arizona Diamondbacks",
                    away_team_name="St. Louis Cardinals",
                    commence_time=datetime(2026, 6, 24, 21, 40, tzinfo=timezone.utc))
        base.update(kw)
        return NS(**base)

    def anchor(**kw):
        base = dict(espn_id="401815890", date=datetime(2026, 6, 24, 21, 40, tzinfo=timezone.utc),
                    status="post", stopped_without_result=False, time_valid=True,
                    home_team=NS(display_name="Arizona Diamondbacks", name="Diamondbacks"),
                    away_team=NS(display_name="St. Louis Cardinals", name="Cardinals"),
                    home_score=9, away_score=4)
        base.update(kw)
        return NS(**base)

    checks = [
        ("401815890 STL 4 - ARI 9 is cashable",
         anchor_id_refusal(row(), anchor()) is None and anchor_refusal_reason(row(), anchor()) is None),
        ("#980's helper writes it", _corrected_final_score(0, 0, 9, 4) == (9, 4)),
        ("#980's helper never overwrites a real score", _corrected_final_score(3, 2, 9, 4) is None),
        ("401815854 POSTPONED is refused",
         "not_final" in (anchor_refusal_reason(row(), anchor(stopped_without_result=True,
                                                              home_score=0, away_score=0)) or "")),
        ("ESPN 0 - 0 leaves the row alone",
         "confirms_0_0" in (anchor_refusal_reason(row(), anchor(home_score=0, away_score=0)) or "")),
        ("a different returned id is refused",
         "different_id" in (anchor_id_refusal(row(), anchor(espn_id="401815887")) or "")),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
    print(f"\nselftest: {len(checks) - len(failed)}/{len(checks)}")
    return 1 if failed else 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true",
                        help="bank and write (default: preview, nothing written or created)")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"rows per run, oldest first (max {MAX_LIMIT})")
    parser.add_argument("--ids", type=str, default=None, help="comma-separated event ids")
    parser.add_argument("--ignore-marker", action="store_true",
                        help="re-ask rows this pass already checked (a deliberate re-sweep)")
    parser.add_argument("--restore", action="store_true",
                        help="undo applied writes (preview unless --apply)")
    parser.add_argument("--selftest", action="store_true", help="offline rule check, no database")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= MAX_LIMIT:
        parser.error(f"--limit must be between 1 and {MAX_LIMIT}")
    args.only_ids = [int(x) for x in args.ids.split(",")] if args.ids else None
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return _selftest()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
