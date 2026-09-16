"""#2486 — refetch the ESPN win-prob series that were stored at 1/100 scale.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15305465/models` and 988
other pages: the ESPN line lies flat along the floor of the Win Probability
chart while the other sources run across the middle of it, and the green Bain
Luck aggregate hops ~45pp every time the blend's weighted median steps across
that gap. **118,824 rows across 989 events, 118,821 of them (99.998%) under 2%.**

THE PRODUCER IS FIXED AND THIS IS THE RESIDUE. `_normalize_win_percentage`
(#2486 writer half) stopped `get_win_probability` dividing a fraction by 100. A
gate governs WRITES; it does not retract rows already in the table, and the
chart draws the table.

── WHY THIS IS A REFETCH AND NOT AN ARITHMETIC REPAIR ──────────────────────────

The obvious repair is `UPDATE … SET home_win_probability = home_win_probability
* 100`, and it is WRONG. The stored value is `round(espn_value / 100, 4)` in a
`Numeric(5,4)` column, so the rounding already threw the precision away:

    0.5853  ->  0.0059  ->  x100  ->  0.59      (true 0.5853, a 0.5pp error)
    0.0066  ->  0.0001  ->  x100  ->  0.01      (true 0.0066)
    0.0040  ->  0.0000  ->  x100  ->  0.00      UNRECOVERABLE

Every point below 0.005 rounded to zero and cannot be reconstructed from the
row. ESPN still serves the original array — re-probed 2026-09-16, a ~5-month-old
game still returns its full `winprobability` — so the truth is available and
arithmetic on a rounded lie is not the way to reach it.

── WHY IT IS NOT A DELETE EITHER ───────────────────────────────────────────────

#2486's own text proposes `DELETE … WHERE backfilled` and letting the beat
refill, because `_backfill_espn_win_probability` selects events with fewer than
10 ESPN snapshots. That is delete-now-hope-to-refill: the refill is a different
process on a different schedule, it is bounded at 200 events a run, and if ESPN
declines an event — a stale `espn_id`, a 404, a league that never had the array
— nothing ever puts the rows back and the chart loses a rail it used to have,
wrong but present. So the order here is inverted: **fetch first, and only what
was successfully fetched is ever replaced.** An event ESPN will not answer for
today keeps its bad rows and is reported, which is a visible defect rather than
a silent hole.

── THE TWO PRECONDITIONS, BOTH CHECKED AT RUN TIME ─────────────────────────────

1. **The corrected writer is the one running.** Not "the PR merged" and not "the
   release shows a sha" — this script imports `_normalize_win_percentage` from
   the image it is executing in and probes it with ESPN's own published values.
   A pre-fix dyno cannot satisfy that import, so the script cannot run on one.
   (Merged is not live, and live is not running: notices 48 / #5505.)

2. **The upstream data is trustworthy, per event.** Every candidate's series is
   refetched and validated BEFORE anything is written — non-empty, every value a
   real number inside [0, 1], no fewer points than ~90% of what is stored, and
   NOT itself flat on the floor. That last check is the writer precondition
   re-proved on live data: if a freshly fetched series still maxes below 2%, the
   path this script depends on is still broken and the event is declined.

── THE SCREEN, AND WHAT IT DELIBERATELY DOES NOT TOUCH ─────────────────────────

The unit of repair is the EVENT's backfilled ESPN series, because the fix
replaces a series wholesale. An event qualifies when the MAX of its backfilled
ESPN rows is under `CORRUPT_MAX` (0.02) — the defect's signature is a whole
series on the floor, and the daily census max has been pinned at exactly 0.0100.

  * An event whose backfilled rows already max ABOVE the threshold is post-fix
    data and is never planned.
  * An event that carries BOTH — some corrupt rows and some healthy ones — is
    counted and REPORTED as `mixed`, never repaired. A whole-series replacement
    is the wrong instrument for it and guessing which rows are which from their
    value is exactly the arithmetic mistake above (gotcha #53: the residue is
    counted out loud, not dropped).
  * Live ESPN rows (`game_state->>'backfilled'` absent or false) are NOT in
    scope. They came from the scoreboard path, whose conditional divide has
    always been right.
  * No other source, no `Event.win_probability_sources`, no `odds_snapshots`.

── THE UNDO (D51(b)) ───────────────────────────────────────────────────────────

Every row this script removes is copied into `bak_2486_win_prob_snapshots`
first, and the delete is a compare-and-swap on the WHOLE backed-up row (#5595):
a row that moved between the reconciliation and the write is DECLINED, not
deleted. So every removed row has a byte-identical backup, or it was not
removed. `bak_2486_repair_manifest` records what the repair DID — which rows it
deleted and which ids it inserted — because a full-row backup cannot record that
this script is what removed them (CERT-2439).

One command, and it is a mode of this same script so it cannot drift:

    python3 scripts/repair_2486_espn_win_prob_scale.py --restore

  It deletes the rows this script inserted (by manifest id) and reinserts the
  backup rows with their original ids, in one transaction. `--restore
  --event <id>` narrows it to a single event.

── RUNNING IT ──────────────────────────────────────────────────────────────────

ATTENDED ONLY. This writes production data; no lane executes it (D51). It
refuses to run anywhere but `bainluck-heavy`, which is the attended step itself
(notice 47(c)): the DDL here is `CREATE TABLE IF NOT EXISTS bak_2486_*`, created
by a person invoking this script on a named app, never by a release.

    heroku run:detached -a bainluck-heavy -- \\
        python3 backend/scripts/repair_2486_espn_win_prob_scale.py --plan
    …                                       --apply --limit 25    # first batch
    …                                       --apply               # the rest
    …                                       --restore             # the undo

`--plan` is the default and writes nothing at all. Non-detached `heroku run`
fails silently in the sandbox (gotcha #48) — use `run:detached` and read the
output back from the logs.
"""

import argparse
import asyncio
import os
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: The only app this may run on. The invocation IS the attended step (notice
#: 47(c)); a script that can be run anywhere is a script a beat can run.
REQUIRED_APP = "bainluck-heavy"

BAK_TABLE = "bak_2486_win_prob_snapshots"
MANIFEST_TABLE = "bak_2486_repair_manifest"

#: A whole backfilled ESPN series maxing under this is the 1/100 signature. The
#: production census has read a max of exactly 0.0100 every day for ten days,
#: and 118,821 of 118,824 rows under 0.02 — the two numbers agree because
#: dividing a [0,1] fraction by 100 cannot produce anything above 0.01.
CORRUPT_MAX = 0.02

#: An event that is off the floor, but spends less than this share of its
#: length off it, is REPORTED for a person rather than repaired. It is the only
#: computable hint of a series that was partly written before the fix and topped
#: up after it; a genuine blowout can trip it too, which costs a line of output
#: and nothing else, because this bucket is never acted on.
SUSPECT_RATIO = 0.5

#: A refetched series must keep at least this share of the stored points. ESPN
#: occasionally trims a series when it re-publishes; losing a tenth of a curve is
#: tolerable, losing half of it means the refetch is not the same game.
MIN_POINT_RATIO = 0.9

#: The plan measured on production 2026-09-16 15:5xZ, with ~20% headroom:
#:
#:     plan       1,253 events / 149,357 rows   (whole series on the floor)
#:     no_anchor     30 events /   2,596 rows   (no espn_id — unrefetchable)
#:     suspect        3 events /     278 rows   (off the floor, mostly on it)
#:     healthy        0 events /       0 rows
#:
#: THE ZERO IS THE LOAD-BEARING ROW. Not one backfilled ESPN series in the table
#: is off the floor, which is what a writer that has been wrong for the whole
#: life of the task looks like — and it is also the proof that this screen is
#: not quietly excluding good data, because there is no good data to exclude.
#:
#: This population GROWS until the writer fix is deployed and then only shrinks,
#: and only by this script, so a plan below the floor is either a broken screen
#: or a drained backlog. `explain_small_plan` says which, rather than an
#: `--allow-small` flag that would let the first pass wearing the second's
#: clothes (the #5246 lesson).
SANITY_FLOOR_EVENTS = 1_100

#: ESPN's published values, used to probe the running image. Both are fractions
#: on the `/summary` `winprobability` array (MLB 0.499 / NFL 0.5853, probed
#: 2026-08-31 and 2026-09-16); a pre-fix writer turns them into 0.00499 / 0.005853.
WRITER_PROBES = (0.499, 0.5853, 0.137, 1.0, 0.0)

SQL = {
    # The population, by event. `max` is the screen; the row count sizes the
    # refetch check. Only backfilled ESPN rows are ever considered.
    "population": """
        SELECT e.id            AS event_id,
               e.espn_id       AS espn_id,
               e.commence_time AS commence_time,
               s.key           AS sport_key,
               count(*)                          AS rows_stored,
               max(w.home_win_probability)       AS max_stored,
               count(*) FILTER (WHERE w.home_win_probability >= :corrupt_max)
                                                 AS rows_above_floor
          FROM win_prob_snapshots w
          JOIN events e ON e.id = w.event_id
          JOIN sports s ON s.id = e.sport_id
         WHERE w.source = 'espn'
           AND w.game_state->>'backfilled' = 'true'
         GROUP BY 1, 2, 3, 4
         ORDER BY count(*) DESC
    """,
    "rows_for_event": """
        SELECT id FROM win_prob_snapshots
         WHERE event_id = :event_id
           AND source = 'espn'
           AND game_state->>'backfilled' = 'true'
         ORDER BY id
    """,
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE win_prob_snapshots INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_evict_stale": f"DELETE FROM {BAK_TABLE} b USING win_prob_snapshots s "
                       f"WHERE b.id = s.id AND s.id = ANY(CAST(:ids AS int[])) "
                       f"AND (b.*) IS DISTINCT FROM (s.*)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM win_prob_snapshots s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM win_prob_snapshots s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_stale": f"SELECT count(*) FROM win_prob_snapshots s "
                 f"JOIN {BAK_TABLE} b ON b.id = s.id "
                 f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                 f"AND (b.*) IS DISTINCT FROM (s.*)",
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  event_id     integer NOT NULL,"
                  f"  deleted_ids  integer[] NOT NULL,"
                  f"  inserted_ids integer[] NOT NULL,"
                  f"  points_fetched integer NOT NULL,"
                  f"  applied_at   timestamptz NOT NULL DEFAULT NOW())",
    "man_record": f"INSERT INTO {MANIFEST_TABLE} "
                  f"(event_id, deleted_ids, inserted_ids, points_fetched) "
                  f"VALUES (:event_id, CAST(:deleted AS int[]), "
                  f"        CAST(:inserted AS int[]), :points)",
    "man_events": f"SELECT event_id, deleted_ids, inserted_ids, applied_at "
                  f"FROM {MANIFEST_TABLE} ORDER BY applied_at",
    # THE FORWARD WRITE. A compare-and-swap on the whole backed-up row: this row
    # is removed only if the undo that exists for it is still a faithful copy of
    # it. A row that moved under us is declined and counted.
    "delete": f"DELETE FROM win_prob_snapshots s "
              f"WHERE s.id = ANY(CAST(:ids AS int[])) "
              f"  AND s.source = 'espn' "
              f"  AND s.game_state->>'backfilled' = 'true' "
              f"  AND EXISTS (SELECT 1 FROM {BAK_TABLE} b "
              f"               WHERE b.id = s.id "
              f"                 AND (b.*) IS NOT DISTINCT FROM (s.*)) "
              f"RETURNING s.id",
    # THE UNDO, both halves, by manifest row.
    "restore_drop_inserted": "DELETE FROM win_prob_snapshots "
                             "WHERE id = ANY(CAST(:ids AS int[]))",
    "restore_put_back": f"INSERT INTO win_prob_snapshots "
                        f"SELECT b.* FROM {BAK_TABLE} b "
                        f"WHERE b.id = ANY(CAST(:ids AS int[])) "
                        f"  AND NOT EXISTS (SELECT 1 FROM win_prob_snapshots s "
                        f"                   WHERE s.id = b.id) "
                        f"RETURNING id",
    "man_delete": f"DELETE FROM {MANIFEST_TABLE} WHERE event_id = :event_id",
}


# ── Pure decisions, so they can be tested without a database ───────────


class Candidate(NamedTuple):
    """One event's backfilled ESPN series, as the population query sees it."""

    event_id: int
    espn_id: Optional[str]
    commence_time: object
    sport_key: str
    rows_stored: int
    max_stored: float
    rows_above_floor: int


class Screen(NamedTuple):
    """The four buckets, kept apart because they need different actions."""

    plan: list           # whole series on the floor, and refetchable
    suspect: list        # off the floor, but mostly on it — reported for a human
    no_anchor: list      # corrupt, but no espn_id, so unrefetchable — reported
    healthy: list        # post-fix data — never touched


def screen_population(rows) -> Screen:
    """Split the population into repair / report / leave-alone.

    THE SCREEN IS THE SERIES MAXIMUM, and it has to be, because a corrupt value
    and a genuine low value are INDISTINGUISHABLE row by row. Dividing a [0,1]
    fraction by 100 yields at most 0.01, and ESPN genuinely reports 0.0066 at
    the wrong end of a blowout — the same number, two causes. What separates
    them is the company they keep: a real series comes off the floor somewhere,
    and a corrupt one cannot.

    So an event whose max is above the floor is HEALTHY even though some of its
    rows sit under it. That is deliberate and it leaves one residue: an event
    that was partly backfilled before the fix and topped up after it. The
    backfill only selects events with fewer than 10 ESPN snapshots, so a
    fully-corrupt event (70–200 rows) can never be re-selected and the residue
    is small — but "small" is not "none", so events that are off the floor while
    spending MOST of their length on it are reported as `suspect` for a person
    to look at. They are never repaired: a whole-series replacement is the wrong
    instrument, and picking rows out by value is the mistake above.
    """
    plan, suspect, no_anchor, healthy = [], [], [], []
    for row in rows:
        entry = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        cand = Candidate(
            event_id=int(entry["event_id"]),
            espn_id=entry.get("espn_id"),
            commence_time=entry.get("commence_time"),
            sport_key=entry.get("sport_key") or "",
            rows_stored=int(entry["rows_stored"]),
            max_stored=float(entry["max_stored"] or 0.0),
            rows_above_floor=int(entry.get("rows_above_floor") or 0),
        )
        if cand.rows_above_floor == 0 and cand.max_stored < CORRUPT_MAX:
            # An event with no `espn_id` cannot be refetched at all. It is not a
            # plan and it is not a failure of this run — it is a residue with a
            # different owner (the anchor), reported rather than absorbed.
            (plan if cand.espn_id else no_anchor).append(cand)
        elif cand.rows_above_floor < cand.rows_stored * SUSPECT_RATIO:
            suspect.append(cand)
        else:
            healthy.append(cand)
    return Screen(plan=plan, suspect=suspect, no_anchor=no_anchor,
                  healthy=healthy)


class Validation(NamedTuple):
    ok: bool
    reason: str
    points: int


def validate_refetch(series, rows_stored: int) -> Validation:
    """Is what ESPN just handed back safe to write over what we have?

    Four questions, and the order matters only in that each one's failure
    message has to be readable on its own in a run log.

    The flat-series check is the writer precondition re-proved on live data: a
    refetched series that STILL maxes below the floor means the corrected
    `_normalize_win_percentage` is not in the path, and replacing corrupt rows
    with equally corrupt rows would consume the undo for nothing.
    """
    if not series:
        return Validation(False, "espn returned no series", 0)

    values = []
    for point in series:
        value = point.get("home_win_probability")
        if value is None:
            continue  # a point ESPN published without a probability; skipped
        values.append(float(value))

    if not values:
        return Validation(False, "espn series carries no probabilities", 0)
    if any(not (0.0 <= v <= 1.0) for v in values):
        return Validation(False, "espn series has a value outside [0,1]", len(values))
    if rows_stored and len(values) < rows_stored * MIN_POINT_RATIO:
        return Validation(
            False,
            f"espn series is short: {len(values)} points against "
            f"{rows_stored} stored",
            len(values),
        )
    if max(values) < CORRUPT_MAX:
        return Validation(
            False,
            f"refetched series is STILL flat (max {max(values):.4f}) — the "
            f"corrected writer is not in this path",
            len(values),
        )
    return Validation(True, "", len(values))


class SmallPlanVerdict(NamedTuple):
    """A small plan's diagnosis AND what it means for `--apply`.

    Two facts, deliberately not collapsed into one string: #5246 shipped this
    discriminator as a bare message while the caller tested `if small:`, so both
    causes refused identically and the discriminator only changed the wording.
    """

    blocks_apply: bool
    message: str


def explain_small_plan(plan_events: int, repaired_events: int) -> SmallPlanVerdict:
    """Below the floor because the backlog drained, or because the screen broke?

    The manifest is the discriminator: only a successful forward write puts a
    row in it. Fail-closed is the default — an unrecognised shape blocks.
    """
    if plan_events >= SANITY_FLOOR_EVENTS:
        return SmallPlanVerdict(False, "")
    if plan_events + repaired_events >= SANITY_FLOOR_EVENTS:
        return SmallPlanVerdict(False, (
            f"ALREADY DRAINING — {repaired_events} events are in "
            f"{MANIFEST_TABLE} and {plan_events} remain; together they clear the "
            f"floor of {SANITY_FLOOR_EVENTS}. --apply proceeds."
        ))
    return SmallPlanVerdict(True, (
        f"SCREEN BROKE — only {plan_events} events are planned and "
        f"{repaired_events} were ever repaired, so {plan_events + repaired_events} "
        f"of an expected {SANITY_FLOOR_EVENTS}+ are accounted for. Do NOT lower "
        f"the floor; find the events."
    ))


def writer_is_corrected() -> tuple[bool, str]:
    """Is the image this script is running in the one with the #2486 fix?

    Imported and CALLED, never re-implemented: a second copy of the rule cannot
    prove anything about the first one. A pre-fix image has no
    `_normalize_win_percentage` at all, so the ImportError is itself the answer.
    """
    try:
        from app.services.espn_api import _normalize_win_percentage
    except ImportError:
        return False, (
            "app.services.espn_api has no _normalize_win_percentage — this dyno "
            "is running a pre-#2486 image. Deploy the writer fix first."
        )
    for probe in WRITER_PROBES:
        got = _normalize_win_percentage(probe)
        if got != probe:
            return False, (
                f"_normalize_win_percentage({probe}) returned {got} — the "
                f"helper is present but not behaving; refusing to write."
            )
    return True, ""


def app_is_permitted(app_name: Optional[str]) -> tuple[bool, str]:
    """Only the named app, so no scheduler can ever reach this (notice 47(c))."""
    if app_name == REQUIRED_APP:
        return True, ""
    return False, (
        f"HEROKU_APP_NAME is {app_name!r}, not {REQUIRED_APP!r}. This script "
        f"writes production data and runs only where a person put it."
    )


def backup_is_exact(recon: dict) -> bool:
    """Every planned row has a byte-identical backup, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is the whole
    point: a reconciliation that inspected nothing must not read as a pass.
    """
    return bool(recon) and all(n == 0 for n in recon.values())


# ── The run ────────────────────────────────────────────────────────────


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def reconcile_backup(session, ids) -> dict:
    """Coverage by CONTENT, not by id (#5595). Two counts, never summed."""
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = stale = 0
    for chunk in _chunks(ids, 5000):
        missing += int((await session.execute(
            text(SQL["bak_missing"]), {"ids": chunk})).scalar_one())
        stale += int((await session.execute(
            text(SQL["bak_stale"]), {"ids": chunk})).scalar_one())
    return {"missing_backup_rows": missing, "stale_backup_rows": stale}


async def repair_one_event(session, service, cand: Candidate) -> dict:
    """Fetch, validate, back up, swap — one event, one transaction.

    Nothing is deleted before the replacement series is in hand and has passed
    `validate_refetch`. Any exception leaves the event exactly as it was,
    because the backup copy and the swap share this transaction.
    """
    from datetime import datetime, timezone

    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.models.models import WinProbSnapshot
    from app.tasks.espn_sync import _wp_backfill_snap_time

    outcome = {"event_id": cand.event_id, "deleted": 0, "inserted": 0,
               "declined": 0, "skipped": ""}

    try:
        series = await service.get_win_probability(cand.sport_key, cand.espn_id)
    except Exception as exc:  # one event's failure never costs the pass
        outcome["skipped"] = f"espn fetch raised: {str(exc)[:80]}"
        return outcome

    verdict = validate_refetch(series or [], cand.rows_stored)
    if not verdict.ok:
        outcome["skipped"] = verdict.reason
        return outcome

    ids = [int(r[0]) for r in (await session.execute(
        text(SQL["rows_for_event"]), {"event_id": cand.event_id})).fetchall()]
    if not ids:
        outcome["skipped"] = "no backfilled rows left (already repaired?)"
        return outcome

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["bak_evict_stale"]), {"ids": ids})
    await session.execute(text(SQL["bak_copy"]), {"ids": ids})

    recon = await reconcile_backup(session, ids)
    if not backup_is_exact(recon):
        await session.rollback()
        outcome["skipped"] = f"backup incomplete {recon} — nothing touched"
        return outcome

    gone = [int(r[0]) for r in (await session.execute(
        text(SQL["delete"]), {"ids": ids})).fetchall()]
    outcome["deleted"] = len(gone)
    outcome["declined"] = len(ids) - len(gone)
    if not gone:
        await session.rollback()
        outcome["skipped"] = "every row declined the swap — they moved under us"
        return outcome

    now = datetime.now(timezone.utc)
    total = len(series)
    inserted = []
    for i, point in enumerate(series):
        home = point.get("home_win_probability")
        if home is None:
            continue
        stmt = pg_insert(WinProbSnapshot).values(
            event_id=cand.event_id,
            source="espn",
            home_win_probability=round(float(home), 4),
            away_win_probability=round(1.0 - float(home), 4),
            captured_at=_wp_backfill_snap_time(
                cand.commence_time, i, total, cand.sport_key, now
            ),
            game_state={
                "seconds_left": point.get("seconds_left"),
                "backfilled": True,
                # Provenance, so a later reader can tell a repaired series from
                # one the beat wrote — and so the undo can be audited by content
                # rather than by trusting the manifest alone.
                "repair": "2486",
            },
        ).on_conflict_do_nothing().returning(WinProbSnapshot.id)
        new_id = (await session.execute(stmt)).scalar()
        if new_id is not None:
            inserted.append(int(new_id))

    await session.execute(text(SQL["man_create"]))
    await session.execute(text(SQL["man_record"]), {
        "event_id": cand.event_id,
        "deleted": gone,
        "inserted": inserted,
        "points": len(inserted),
    })
    await session.commit()
    outcome["inserted"] = len(inserted)
    return outcome


async def run_repair(args) -> None:
    from sqlalchemy import text

    from app.services.espn_api import ESPNAPIService
    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        rows = (await session.execute(
            text(SQL["population"]), {"corrupt_max": CORRUPT_MAX})).fetchall()
        screen = screen_population(rows)

        def _rows(bucket):
            return sum(c.rows_stored for c in bucket)

        print(f"population    : {len(rows)} events / "
              f"{sum(_rows(b) for b in screen)} backfilled ESPN rows")
        print(f"  PLAN        : {len(screen.plan)} events / "
              f"{_rows(screen.plan)} rows (whole series under {CORRUPT_MAX})")
        print(f"  suspect     : {len(screen.suspect)} events / "
              f"{_rows(screen.suspect)} rows (off the floor but mostly on it — "
              f"reported, never repaired)")
        print(f"  no espn_id  : {len(screen.no_anchor)} events / "
              f"{_rows(screen.no_anchor)} rows (corrupt but unrefetchable)")
        print(f"  healthy     : {len(screen.healthy)} events / "
              f"{_rows(screen.healthy)} rows (post-fix, untouched)")

        repaired_before = 0
        if await _table_exists(session, "man_exists"):
            repaired_before = int((await session.execute(
                text(f"SELECT count(DISTINCT event_id) FROM {MANIFEST_TABLE}")
            )).scalar_one())
        small = explain_small_plan(len(screen.plan), repaired_before)
        if small.message:
            print(f"\n⚠️  plan is below the sanity floor of "
                  f"{SANITY_FLOOR_EVENTS} events.\n   {small.message}")

        plan = screen.plan
        if args.event:
            plan = [c for c in plan if c.event_id == args.event]
            print(f"  --event {args.event}: {len(plan)} of the plan")
        if args.limit:
            plan = plan[:args.limit]
            print(f"  --limit {args.limit}: repairing {len(plan)} this run")

        if not args.apply:
            print("\nplan only — nothing written. Re-run with --apply.")
            for cand in plan[:10]:
                print(f"    event {cand.event_id:>9} {cand.sport_key:<20} "
                      f"{cand.rows_stored:>4} rows  max {cand.max_stored:.4f}")
            if len(plan) > 10:
                print(f"    … and {len(plan) - 10} more")
            return

        if small.blocks_apply:
            print("REFUSING --apply: the plan is below the sanity floor (above).")
            return

        service = ESPNAPIService()
        totals = {"repaired": 0, "deleted": 0, "inserted": 0, "skipped": 0}
        try:
            for cand in plan:
                outcome = await repair_one_event(session, service, cand)
                if outcome["skipped"]:
                    totals["skipped"] += 1
                    print(f"  SKIP  event {outcome['event_id']}: {outcome['skipped']}")
                    continue
                totals["repaired"] += 1
                totals["deleted"] += outcome["deleted"]
                totals["inserted"] += outcome["inserted"]
                print(f"  OK    event {outcome['event_id']}: "
                      f"-{outcome['deleted']} +{outcome['inserted']}")
                await asyncio.sleep(0.5)
        finally:
            await service.close()

        print(f"\nrepaired {totals['repaired']} events "
              f"(-{totals['deleted']} corrupt rows, +{totals['inserted']} refetched), "
              f"skipped {totals['skipped']}")
        print(f"undo: python3 {os.path.basename(__file__)} --restore")


async def run_restore(args) -> None:
    """Put every repaired event back exactly as it was."""
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as session:
        if not await _table_exists(session, "man_exists"):
            print(f"no {MANIFEST_TABLE} — this repair has never been applied.")
            return
        manifest = (await session.execute(text(SQL["man_events"]))).fetchall()
        rows = [dict(r._mapping) for r in manifest]
        if args.event:
            rows = [r for r in rows if int(r["event_id"]) == args.event]

        print(f"restoring {len(rows)} events")
        for entry in rows:
            dropped = (await session.execute(
                text(SQL["restore_drop_inserted"]),
                {"ids": list(entry["inserted_ids"])})).rowcount or 0
            back = (await session.execute(
                text(SQL["restore_put_back"]),
                {"ids": list(entry["deleted_ids"])})).fetchall()
            await session.execute(
                text(SQL["man_delete"]), {"event_id": entry["event_id"]})
            await session.commit()
            print(f"  event {entry['event_id']}: -{dropped} repaired rows, "
                  f"+{len(back)} original rows restored "
                  f"(of {len(entry['deleted_ids'])} backed up)")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--plan", action="store_true",
                        help="the default: count and list, write nothing")
    parser.add_argument("--apply", action="store_true",
                        help="refetch and replace (production write, attended)")
    parser.add_argument("--restore", action="store_true",
                        help="the undo: put every repaired event back")
    parser.add_argument("--limit", type=int, default=0,
                        help="cap the events repaired this run")
    parser.add_argument("--event", type=int, default=0,
                        help="one event id, for a first attended batch of one")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the gate decisions and exit; touches nothing")
    args = parser.parse_args()

    ok_app, app_why = app_is_permitted(os.environ.get("HEROKU_APP_NAME"))
    ok_writer, writer_why = writer_is_corrected()

    if args.dry_run:
        print(f"#2486 repair — dry run, no database connection opened")
        print(f"  app gate        : {'PASS' if ok_app else 'REFUSE'} "
              f"({app_why or REQUIRED_APP})")
        print(f"  writer gate     : {'PASS' if ok_writer else 'REFUSE'} "
              f"({writer_why or 'the running image normalizes ESPN fractions'})")
        print(f"  mode            : "
              f"{'restore' if args.restore else 'apply' if args.apply else 'plan'}")
        print(f"  corrupt screen  : max(home_win_probability) < {CORRUPT_MAX} "
              f"over an event's backfilled ESPN rows")
        print(f"  backup table    : {BAK_TABLE}")
        print(f"  manifest table  : {MANIFEST_TABLE}")
        return 0

    if (args.apply or args.restore) and not ok_app:
        print(f"REFUSING: {app_why}")
        return 2
    if args.apply and not ok_writer:
        print(f"REFUSING: {writer_why}")
        return 2

    asyncio.run(run_restore(args) if args.restore else run_repair(args))
    return 0


if __name__ == "__main__":
    sys.exit(main())
