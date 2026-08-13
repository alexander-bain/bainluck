"""Queue 340 — ``events.statpal_fixture_id = ''`` → NULL (data-repair lane).

THE DEFECT. ``''`` and NULL both mean "we have no StatPal id for this event", but
they are not interchangeable to the database:

* only NULL is exempt from a unique index, so 8,272 rows sharing the literal value
  ``''`` make ``statpal_fixture_id`` structurally un-uniqueable;
* only NULL compares correctly — ``COUNT(statpal_fixture_id)`` and every
  ``statpal_fixture_id IS NOT NULL`` predicate counts a blank as a real linkage.
  Three live surfaces read exactly that way and are therefore over-reporting
  StatPal coverage today: ``app/tasks/data_quality_watchdog.py`` (the Tier-1
  coverage query), ``app/routes/admin_source_health.py`` (``"statpal"``), and the
  ``COUNT(e.statpal_fixture_id)`` linkage tiles in ``app/utils/admin_dashboard.py``
  / ``app/routes/admin_matching.py``.

So "do we have a StatPal id?" currently depends on which of two spellings of
absence a given row happens to carry. That is the bug.

WHY THE WRITE IS SAFE. Every code path that CONSUMES the column tests it for
truthiness, not for NULL-ness, so ``''`` and NULL are already indistinguishable to
them and this repair changes no behaviour there:

    event_registry._attach_claim   ``if not event.statpal_fixture_id:``  (overwrites)
    statpal_sync._get_statpal_id   ``if ... and event.statpal_fixture_id:`` (falls
                                   back to the ``win_probability_sources`` JSONB
                                   mirror, which this repair does not touch)

Only the ``IS NOT NULL`` / ``COUNT()`` readers change — and they change from wrong
to right.

NO LIVE PRODUCER (verified two ways, 2026-08-12):

  1. Measured on production — all 8,272 blank rows were created
     ``2026-02-22 03:04:59Z`` → ``2026-03-04 05:06:12Z``. A bounded historical
     cohort that stopped five months ago.
  2. Read in the tree — both ``_set_statpal_id`` call sites (``statpal_sync.py``
     :194 and :769) are guarded by ``if fixture.fixture_id and ...``, and
     ``_attach_claim`` only assigns ``claim.source_id``. No path can emit ``''``
     today, so this repair is a one-shot, not a recurring sweep.

THE EXACT-MATCH GATE (queue 339S's discipline). ``apply`` is refused unless the
LIVE before-census blank count equals ``expected_blank`` — measured on production
five minutes before this was written, hence the 8,272 default. A drifted census
means the population you measured is not the population you are about to write, and
the correct response is to re-measure, not to write anyway. The refusal is a
verdict in the result dict, never an exception: an operator must be able to read
the observed count and re-invoke with it.

    A DEADLINE-STOPPED RUN THEREFORE NEEDS AN EXPLICIT RESUME. Once a partial run
    commits, the live blank count is below 8,272 and the gate will (correctly)
    refuse the next call. Re-invoke with ``expected_blank=<the ``before.blank``
    the last response reported>``. That friction is the point.

OUT OF SCOPE — THE 8 DUPLICATE REAL IDS. Eight real ``statpal_fixture_id`` values
are carried by two events each (16 rows): ``1027790``, ``1027792``, ``1329190539``,
``1329190569``, ``1329200227``, ``627215``, ``637968``, ``637987``. This repair
REPORTS them (with their event ids, so the follow-up is a lookup and not a
re-investigation) and touches none of them. Clearing a duplicate pair means
deciding which of two events is the real fixture and what happens to the other's
data — attended, by-name work, and NOT this repair's job. Until it is done,
``statpal_fixture_id`` still cannot carry a unique index even after every blank is
NULLed.

    POST /api/admin/repairs/statpal-blank-ids?apply=false   # dry-run census
    POST /api/admin/repairs/statpal-blank-ids?apply=true    # commit
    POST /api/admin/repairs/statpal-blank-ids?apply=true&expected_blank=3272  # resume

    python3 scripts/repair_statpal_fixture_id_blanks.py            # dry-run
    python3 scripts/repair_statpal_fixture_id_blanks.py --apply

Heroku one-off (gotcha #48 — a non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO ``cd backend``). Prefer the
endpoint: it is self-verifying and this script's census is not visible from a
detached dyno's (empty) stdout.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The measured production blank count (2026-08-12). The gate's default, and the
# only value that lets an unqualified ``apply=true`` write.
EXPECTED_BLANK_COUNT = 8272

# Rows per committed batch. ``events`` is a hot table and a single 8,272-row
# UPDATE holds row locks against the live pollers for its whole duration
# (memory: heroku one-off events-table lock contention). Bounded id-RANGE
# batches with a commit each keep every lock window short and leave partial
# progress durable. A module constant, not a param, so it cannot be dialled
# off mid-run.
BATCH_SIZE = 1000

# One uninterrupted op here is a single ~1,000-row indexed UPDATE (measured
# census cost on the same table: 172ms), so the reserve bounds the longest
# single op, not just the loop boundary (memory: budget guard inner-op).
_DEADLINE_SECONDS = 22.0
_BATCH_RESERVE_SECONDS = 5.0

# ONE census definition, used for both the before- and after- reading, so the
# gate and the proof can never be computed over different populations.
_CENSUS_SQL = """
    SELECT COUNT(*) FILTER (WHERE statpal_fixture_id = '')        AS blank,
           COUNT(*) FILTER (WHERE statpal_fixture_id IS NULL)     AS nulls,
           COUNT(*) FILTER (WHERE statpal_fixture_id IS NOT NULL
                              AND statpal_fixture_id <> '')       AS real,
           COUNT(*)                                               AS total
    FROM events
"""

# The blank ids, ordered, so the batches are contiguous id ranges. Served from
# ix_events_statpal_fixture_id — it never scans the table.
_BLANK_IDS_SQL = """
    SELECT id FROM events WHERE statpal_fixture_id = '' ORDER BY id
"""

# Bounded by an id RANGE rather than ``id = ANY(:ids)``: an array-bound UPDATE on
# this table has rolled back silently before (memory: events-table lock
# contention). The predicate is repeated so the write can only ever touch blanks,
# even if a row inside the range changed between the SELECT and the UPDATE.
_NULL_BATCH_SQL = """
    UPDATE events
       SET statpal_fixture_id = NULL
     WHERE id >= :lo AND id <= :hi
       AND statpal_fixture_id = ''
"""

# Reported, never touched. Real (non-blank) values carried by more than one event.
_DUPLICATES_SQL = """
    SELECT statpal_fixture_id AS value,
           ARRAY_AGG(id ORDER BY id) AS event_ids,
           COUNT(*) AS rows
    FROM events
    WHERE statpal_fixture_id IS NOT NULL AND statpal_fixture_id <> ''
    GROUP BY 1
    HAVING COUNT(*) > 1
    ORDER BY 1
"""


def _census(row) -> dict:
    return {
        "blank": int(row.blank),
        "nulls": int(row.nulls),
        "real": int(row.real),
        "total": int(row.total),
    }


def batch_ranges(ids: list[int], batch_size: int = BATCH_SIZE) -> list[tuple[int, int]]:
    """Contiguous ``(lo, hi)`` id ranges covering ``ids``, ``batch_size`` ids each.

    Pure, so the batching contract is testable without a database. Inclusive on
    both ends — ``_NULL_BATCH_SQL`` uses ``>= lo AND <= hi``. Ranges may span ids
    that are NOT blank; the UPDATE's repeated ``= ''`` predicate is what keeps the
    write exact, which is why the ranges may be coarse but the rowcounts cannot be.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    return [
        (chunk[0], chunk[-1])
        for chunk in (ids[i : i + batch_size] for i in range(0, len(ids), batch_size))
    ]


async def repair(
    session,
    apply: bool,
    expected_blank: int = EXPECTED_BLANK_COUNT,
    deadline_seconds: float = _DEADLINE_SECONDS,
) -> dict:
    """Session-taking core, shared by the CLI and
    ``POST /api/admin/repairs/statpal-blank-ids``.

    Returns the before census unconditionally, the duplicate-pair report
    unconditionally, and — when it wrote — the after census, so the response body
    is its own proof (gotcha #48/#53: "it returned" is not "it worked", and a
    zero-yield run must be loud rather than indistinguishable from a clean one).

    Writes nothing when ``apply`` is False, and nothing when the exact-match gate
    refuses. The refusal is returned, not raised.
    """
    import time

    from sqlalchemy import text

    s = session
    started = time.monotonic()

    before = _census((await s.execute(text(_CENSUS_SQL))).one())
    duplicates = [
        {"value": r.value, "event_ids": list(r.event_ids), "rows": int(r.rows)}
        for r in (await s.execute(text(_DUPLICATES_SQL))).all()
    ]
    dup_ids = {i for d in duplicates for i in d["event_ids"]}

    result = {
        "repair": "statpal-blank-ids",
        "applied": False,
        "before": before,
        "expected_blank": int(expected_blank),
        "batch_size": BATCH_SIZE,
        # Out of scope, reported so the follow-up is a lookup (see module docstring).
        "duplicate_real_values": duplicates,
        "duplicate_value_count": len(duplicates),
        "duplicate_row_count": sum(d["rows"] for d in duplicates),
        "duplicates_note": (
            "REPORTED, NOT TOUCHED. Clearing a duplicate pair is attended, by-name "
            "work. statpal_fixture_id cannot carry a unique index until both the "
            "blanks are NULLed AND these pairs are resolved."
        ),
    }

    if before["blank"] == 0:
        # Idempotent no-op, said out loud rather than reported as a clean apply.
        result["terminal"] = "noop"
        result["verdict"] = "already_clean"
        result["rows_nulled"] = 0
        result["after"] = before
        return result

    if not apply:
        result["terminal"] = "noop"
        result["verdict"] = "dry_run"
        result["would_null"] = before["blank"]
        result["would_batch_count"] = -(-before["blank"] // BATCH_SIZE)
        return result

    # --- THE EXACT-MATCH GATE ------------------------------------------------
    # Apply only on an exact census match. A drifted census means the population
    # measured is not the population about to be written.
    if before["blank"] != int(expected_blank):
        result["terminal"] = "failed"
        result["verdict"] = "refused_census_drift"
        result["refused"] = True
        result["reason"] = (
            f"exact-match gate: live blank count is {before['blank']}, expected "
            f"{int(expected_blank)}. NOTHING WAS WRITTEN. Re-measure, then re-invoke "
            f"with expected_blank={before['blank']} if that count is the population "
            f"you intend to NULL."
        )
        return result

    ids = [int(r.id) for r in (await s.execute(text(_BLANK_IDS_SQL))).all()]
    # Read the module global at CALL time, not at def time, so the constant is
    # the single knob (and a test can shrink it without redefining the default).
    ranges = batch_ranges(ids, BATCH_SIZE)

    batches: list[dict] = []
    rows_nulled = 0
    stopped_on_deadline = False
    for lo, hi in ranges:
        if time.monotonic() - started > deadline_seconds - _BATCH_RESERVE_SECONDS:
            # Stop cleanly. Committed batches stand; the operator resumes with the
            # NEW blank count as expected_blank.
            stopped_on_deadline = True
            break
        n = (await s.execute(text(_NULL_BATCH_SQL), {"lo": lo, "hi": hi})).rowcount or 0
        await s.commit()
        rows_nulled += n
        batches.append({"lo": lo, "hi": hi, "rows": n})

    after = _census((await s.execute(text(_CENSUS_SQL))).one())

    complete = not stopped_on_deadline and after["blank"] == 0
    result.update({
        "applied": True,
        "terminal": "complete" if complete else "partial",
        "verdict": "cleared" if complete else "partial_resume_required",
        "batches": batches,
        "batches_planned": len(ranges),
        "batches_committed": len(batches),
        "commits": len(batches),
        "rows_nulled": rows_nulled,
        "after": after,
        "stopped_on_deadline": stopped_on_deadline,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        # The self-verification: the ONLY column that may move is blank -> nulls.
        "census_consistent": (
            after["blank"] == before["blank"] - rows_nulled
            and after["nulls"] == before["nulls"] + rows_nulled
            and after["real"] == before["real"]
            and after["total"] == before["total"]
        ),
        # The duplicate pairs carry REAL ids, so they can never be in the blank
        # id set — assert it rather than assume it, and confirm the real-id
        # population is numerically untouched.
        "duplicates_untouched": (
            dup_ids.isdisjoint(ids) and after["real"] == before["real"]
        ),
    })
    if not complete:
        result["resume_with_expected_blank"] = after["blank"]
    return result


async def run(apply: bool, expected_blank: int) -> None:
    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        res = await repair(s, apply, expected_blank=expected_blank)

    b = res["before"]
    print(f"=== statpal-blank-ids ({'APPLY' if apply else 'DRY-RUN'}) ===")
    print(f"BEFORE  blank={b['blank']}  nulls={b['nulls']}  real={b['real']}  "
          f"total={b['total']}")
    print(f"duplicate real values (OUT OF SCOPE, untouched): "
          f"{res['duplicate_value_count']} values / {res['duplicate_row_count']} rows")
    for d in res["duplicate_real_values"]:
        print(f"    {d['value']}: events {d['event_ids']}")

    if res.get("refused"):
        print(f"\nREFUSED — {res['reason']}")
        return
    if not apply:
        print(f"\nDRY-RUN — would NULL {res.get('would_null', 0)} row(s) in "
              f"{res.get('would_batch_count', 0)} batch(es) of {BATCH_SIZE}. "
              f"No writes made. Pass --apply to commit.")
        return

    a = res.get("after", b)
    print(f"\nCOMMITTED {res['rows_nulled']} row(s) in {res['batches_committed']} "
          f"batch(es) ({res['elapsed_seconds']}s)")
    print(f"AFTER   blank={a['blank']}  nulls={a['nulls']}  real={a['real']}  "
          f"total={a['total']}")
    if not res["census_consistent"]:
        print("⚠️  CENSUS INCONSISTENT — blank/nulls did not move by exactly "
              "rows_nulled, or real/total changed. Investigate before re-running.")
    elif res["terminal"] == "complete":
        print("✅ every blank statpal_fixture_id is now NULL.")
    else:
        print(f"⏸  stopped early — re-run with "
              f"--expected-blank {res['resume_with_expected_blank']}")


if __name__ == "__main__":
    _expected = EXPECTED_BLANK_COUNT
    for i, a in enumerate(sys.argv):
        if a == "--expected-blank" and i + 1 < len(sys.argv):
            _expected = int(sys.argv[i + 1])
    asyncio.run(run("--apply" in sys.argv, _expected))
