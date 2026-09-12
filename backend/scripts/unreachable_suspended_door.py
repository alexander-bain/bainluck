#!/usr/bin/env python3
"""Attended control for the unreachable-suspended door (#5532 / #5130, D-live176).

The door itself is an arm in ``espn_sync._transition_event_statuses_impl``. It is
OFF unless two things are true, and both of them are this script's doing:

    1. the backup table exists  — the D51 restore rail, and the arm's hard gate;
    2. a per-pass budget is set in Redis — the rate the backlog drains at.

Nothing here runs on a schedule and nothing here is imported by ``app/``. The
invocation IS the attended step (standing notice 47(c)): the ``CREATE TABLE IF
NOT EXISTS`` below executes only when a person types it, on a named app, behind
its own flag — it is not migration-class and no deploy runs it.

WHY THE BACKUP IS AN ID LIST AND NOT THE PREDICATE. Measured on production
2026-09-12 (fingerprint ``295937d629781eeb``): 4,320 rows are already ``voided``
for unrelated reasons and **2,544 of them match the retirement predicate
exactly**. A predicate-shaped restore would resurrect all 2,544 as ``suspended``
while looking like a clean rollback.

  # 0. see what it would touch, change nothing
  python3 scripts/unreachable_suspended_door.py --dry-run

  # 1. create the restore rail (attended DDL; the arm stays off without it)
  python3 scripts/unreachable_suspended_door.py --create-backup

  # 2. open the door at N rows per 60s pass
  python3 scripts/unreachable_suspended_door.py --open 200

  # -- one command to stop it (leaves everything already written in place) --
  python3 scripts/unreachable_suspended_door.py --close

  # -- one command to put every retired row back exactly as it was --
  # It shuts the door, waits out any pass that already latched a budget, and
  # only then writes. It can therefore BLOCK for up to the marker expiry, and it
  # exits 2 without touching a row rather than restore into a live writer.
  python3 scripts/unreachable_suspended_door.py --restore
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

#: The one app this may be pointed at. A repair script that will run anywhere is
#: a repair script that will eventually run somewhere else (notice 47(c)).
#:
#: FOLLOW-UP `5532-REQUIRE-THE-MAIN-APP-NOT-EITHER-APP` (CERT-2757). This read
#: `("bainluck", "bainluck-heavy")`, which is not "a named app" — it is two, and
#: notice 47(c) asks for the one where the thing being controlled actually runs.
#: The arm lives in `transition_event_statuses` on the **realtime** queue, which
#: is the main app; `bainluck-heavy` runs a different worker off the same
#: database, so a `--close` typed there would be correct about Redis and yet
#: leave the operator watching the wrong dyno for the effect. Narrowed to the
#: app whose logs answer "did it stop?".
ALLOWED_APPS = ("bainluck",)


def _constants():
    from app.tasks.espn_sync import (
        SUSPENDED_RESUME_WINDOW,
        UNREACHABLE_SUSPENDED_BACKUP_TABLE,
        UNREACHABLE_SUSPENDED_BUDGET_KEY,
        UNREACHABLE_SUSPENDED_INFLIGHT_KEY,
        UNREACHABLE_SUSPENDED_INFLIGHT_TTL,
        UNREACHABLE_SUSPENDED_MAX_BUDGET,
    )
    from app.utils.event_completion import (
        UNREACHABLE_SUSPENDED_MARGIN,
        UNREACHABLE_SUSPENDED_TERMINAL,
    )

    return {
        "table": UNREACHABLE_SUSPENDED_BACKUP_TABLE,
        "key": UNREACHABLE_SUSPENDED_BUDGET_KEY,
        "inflight_key": UNREACHABLE_SUSPENDED_INFLIGHT_KEY,
        "inflight_ttl": UNREACHABLE_SUSPENDED_INFLIGHT_TTL,
        "max_budget": UNREACHABLE_SUSPENDED_MAX_BUDGET,
        "terminal": UNREACHABLE_SUSPENDED_TERMINAL,
        # Derived from the arm's own constants, never restated here — a runbook
        # that hand-types 72 is a runbook that disagrees with the code the day
        # either number moves.
        "floor_hours": (
            SUSPENDED_RESUME_WINDOW + UNREACHABLE_SUSPENDED_MARGIN
        ).total_seconds() / 3600.0,
    }


#: The population, spelled exactly as the arm's SELECT spells it. Kept here as
#: one string so ``--dry-run`` reports the same rows the arm would act on.
_SCOPE_SQL = """
    FROM events e
    JOIN sports s ON s.id = e.sport_id
   WHERE e.status = 'suspended'
     AND e.external_id IS NULL
     AND e.espn_id IS NULL
     AND e.statpal_fixture_id IS NULL
     AND e.home_score IS NULL
     AND e.away_score IS NULL
     AND e.completed_at IS NULL
     AND s.key <> ALL(:espn_keys)
     AND e.commence_time < NOW() - make_interval(hours => :floor_hours)
"""


async def _dry_run():
    from app.tasks.base import get_task_session
    from app.tasks.config import ESPN_SPORT_MAPPING

    c = _constants()
    async with get_task_session() as session:
        present = (await session.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"),
            {"t": f"public.{c['table']}"},
        )).scalar()
        rows = (await session.execute(
            text(
                "SELECT s.key, COUNT(*) AS n, MIN(e.commence_time) AS oldest"
                + _SCOPE_SQL
                + " GROUP BY 1 ORDER BY 2 DESC"
            ),
            {
                "espn_keys": list(ESPN_SPORT_MAPPING.keys()),
                "floor_hours": c["floor_hours"],
            },
        )).all()

    total = sum(r.n for r in rows)
    print(f"backup table {c['table']}: {'PRESENT' if present else 'ABSENT — arm is gated off'}")
    print(f"budget key   {c['key']}  (max {c['max_budget']}/pass)")
    print(f"floor        {c['floor_hours']:.0f}h past commence, terminal {c['terminal']!r}")
    print(f"eligible     {total} rows across {len(rows)} sports")
    for r in rows[:12]:
        print(f"  {r.key:34} {r.n:6}  oldest {str(r.oldest)[:10]}")
    if len(rows) > 12:
        print(f"  ... and {len(rows) - 12} more sports")
    return 0


async def _create_backup():
    from app.tasks.base import get_task_session

    c = _constants()
    async with get_task_session() as session:
        await session.execute(text(
            f"CREATE TABLE IF NOT EXISTS {c['table']} ("
            "  event_id BIGINT PRIMARY KEY,"
            "  previous_status TEXT NOT NULL,"
            "  commence_time TIMESTAMPTZ,"
            "  retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            ")"
        ))
        await session.commit()
    print(f"{c['table']} ready — the arm's restore rail is in place.")
    return 0


async def _restore():
    from app.tasks.base import get_task_session

    c = _constants()
    # 🔴 CLOSE THE DOOR FIRST, AND REFUSE TO RESTORE IF IT WILL NOT CLOSE
    # (CERT-2753, repair `5532-RESTORE-CLOSES-THE-DOOR-FIRST`).
    #
    # The first version restored the rows and then printed "run --close if you
    # also want it shut". That is not a rollback. The arm runs every 60s off the
    # same budget key, and every row this UPDATE hands back is still eligible by
    # construction — the predicate that selected it has not changed — so the next
    # pass re-retires the rows just restored. The claimed one-command undo was
    # two commands with a live race between them, and the race runs in the
    # direction that silently reverses the operator.
    #
    # It also has to FAIL CLOSED. A restore that cannot reach Redis cannot know
    # the door is shut, and restoring into an armed arm is worse than not
    # restoring: the operator is told the rollback succeeded.
    if not _close_door():
        print("REFUSING to restore: the door could not be closed, so the next "
              "pass would re-retire every row this restores. Nothing written.")
        return 2

    # 🔴 THEN WAIT OUT THE PASS THAT IS ALREADY RUNNING
    # (CERT-2757, repair `5532-RESTORE-FENCES-IN-FLIGHT-RETIREMENT`).
    #
    # Closing the door stops every FUTURE pass and says nothing about the
    # current one. A pass that read the budget key a moment ago holds that
    # number in memory, is inside an uncommitted transaction, and will write
    # `voided` AFTER this UPDATE has handed the row back — so the rollback
    # reports success and the row ends retired anyway. That is the same failure
    # CERT-2753 caught, one layer down: not "the next pass undoes it" but "the
    # pass already in flight undoes it".
    #
    # Ordering is the fix, and it only works in this sequence: close first so no
    # new pass can latch a budget, THEN drain, so the set being waited on can
    # only shrink. Draining first would race forever against new passes.
    if not _wait_out_inflight_passes():
        return 2

    async with get_task_session() as session:
        r = await session.execute(
            text(
                "UPDATE events e SET status = b.previous_status "
                f"FROM {c['table']} b "
                "WHERE e.id = b.event_id AND e.status = :terminal"
            ),
            {"terminal": c["terminal"]},
        )
        await session.commit()
    print(f"restored {r.rowcount} rows from {c['table']} to their previous status.")
    print("The door was closed first, so the next pass will retire none of them.")
    return 0


def _close_door() -> bool:
    """Delete the budget key and PROVE the next pass will read zero.

    Returns False on any failure, and on a delete that did not take. The
    read-back is not ceremony: `delete` returning without raising says the
    command was accepted, not that the key is gone — and the whole value of this
    function to `_restore` is the guarantee that the arm is off.
    """
    from app.tasks.redis_state import get_redis_client

    c = _constants()
    try:
        r = get_redis_client()
        r.delete(c["key"])
        still_there = r.get(c["key"])
    except Exception as exc:  # noqa: BLE001 — a close that raised is a close that failed
        print(f"could not close the door: {exc}")
        return False
    if still_there is not None:
        print(f"could not close the door: {c['key']} still reads "
              f"{still_there!r} after delete.")
        return False
    print(f"{c['key']} deleted — the arm is off from its next pass.")
    return True


def _live_inflight_markers(client, now):
    """Markers of passes that may still write; expired ones are pruned.

    Each field's value is a deadline. A field past it belongs to a pass that was
    hard-killed before it could clear up, and it is deleted HERE rather than
    left to the registry's own expiry — every fresh registration pushes that
    expiry out, so on a task that registers every 60 seconds a dead field would
    otherwise be immortal and no restore would ever run again.

    A value that will not parse counts as LIVE. That is one unreadable byte
    weighed against writing a terminal status onto rows somebody just asked to
    have back; the registry's expiry bounds how long it can hold restore up.
    """
    live, expired = [], []
    for field, value in (client.hgetall(_constants()["inflight_key"]) or {}).items():
        raw = value.decode() if isinstance(value, bytes) else value
        try:
            deadline = float(raw)
        except (TypeError, ValueError):
            live.append(field)
            continue
        (live if deadline > now else expired).append(field)
    if expired:
        client.hdel(_constants()["inflight_key"], *expired)
    return live


def _wait_out_inflight_passes(poll_seconds: float = 1.0) -> bool:
    """Block until no pass holds a latched budget. False ⇒ do not restore.

    Bounded by the marker expiry plus a margin, so this terminates even if the
    registry is wedged. It can only terminate EARLY on a positive answer — the
    door is already shut when we get here, so the set of in-flight passes can
    only shrink, and "empty once" cannot become "non-empty again".

    Every failure returns False. A restore that cannot see the fence is a
    restore that cannot promise the rows stay restored, and saying so is worth
    more than performing the UPDATE.
    """
    import time

    c = _constants()
    try:
        from app.tasks.redis_state import get_redis_client

        client = get_redis_client()
    except Exception as exc:  # noqa: BLE001
        print(f"REFUSING to restore: no Redis to read the in-flight fence: {exc}")
        return False

    give_up_at = time.monotonic() + c["inflight_ttl"] + 5
    announced = False
    while True:
        try:
            live = _live_inflight_markers(client, time.time())
        except Exception as exc:  # noqa: BLE001
            print(f"REFUSING to restore: in-flight fence unreadable: {exc}")
            return False
        if not live:
            if announced:
                print("in-flight pass finished; restoring.")
            return True
        if time.monotonic() >= give_up_at:
            print(f"REFUSING to restore: {len(live)} pass(es) still hold a "
                  f"latched budget after {c['inflight_ttl'] + 5}s. They would "
                  f"re-void the rows this restores. Nothing written.")
            return False
        if not announced:
            print(f"door shut; waiting out {len(live)} pass(es) that already "
                  f"latched a budget (up to {c['inflight_ttl'] + 5}s)...")
            announced = True
        time.sleep(poll_seconds)


def _set_budget(value):
    from app.tasks.redis_state import get_redis_client

    c = _constants()
    if value is None:
        return 0 if _close_door() else 2
    get_redis_client().set(c["key"], int(value))
    print(f"{c['key']} = {int(value)} rows/pass (arm caps at {c['max_budget']}).")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="report the eligible population and the gates; change nothing")
    g.add_argument("--create-backup", action="store_true",
                   help="create the restore table (attended DDL)")
    g.add_argument("--open", type=int, metavar="N",
                   help="set the per-pass budget to N rows")
    g.add_argument("--close", action="store_true",
                   help="delete the budget key; the arm stops next pass")
    g.add_argument("--restore", action="store_true",
                   help="put every backed-up row back to its previous status")
    args = p.parse_args()

    # FOLLOW-UP `5532-REQUIRE-NAMED-HEROKU-APP` (CERT-2753, nonblocking) — taken
    # in the same sha. The first version only refused a WRONG app name and let an
    # ABSENT one through, which is the larger hole: every laptop and every lane
    # worktree has no `HEROKU_APP_NAME`, so the unset case was the one path that
    # could point a mutating run at whatever `DATABASE_URL` happened to be
    # exported. Notice 47(c) asks the script to refuse to run anywhere but the
    # named app; an absent name is not the named app. `--dry-run` is exempt
    # because it writes nothing and is how the population is read locally.
    app_name = os.environ.get("HEROKU_APP_NAME")
    if not args.dry_run and app_name not in ALLOWED_APPS:
        p.error(f"refusing to act with HEROKU_APP_NAME={app_name!r}; "
                f"this script mutates state only on {ALLOWED_APPS} "
                f"(use --dry-run locally)")

    if args.dry_run:
        return asyncio.run(_dry_run())
    if args.create_backup:
        return asyncio.run(_create_backup())
    if args.restore:
        return asyncio.run(_restore())
    if args.close:
        return _set_budget(None)
    return _set_budget(args.open)


if __name__ == "__main__":
    sys.exit(main())
