"""#5432 — retire the Polymarket win-prob rows a DERIVATIVE market wrote.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15296755`, Barcelona 5-1
Feyenoord, a finished Champions League tie. The Win Probability card's legend
reads `Bain Luck · Sportsbooks · Polymarket`, and the blue dashed **Polymarket**
line sits flat at ~3% from kickoff to full time — on the team that won by four
— while the card's own footer says `Barcelona 100% — Feyenoord 0%`. The green
Bain Luck aggregate is dragged into vertical spikes down to 3% and back, because
it is blending that leg. Screenshots at 390px:
`artifacts/DEFECT-5432-barca-sources-0958Z.png` (legend expanded) and
`artifacts/DEFECT-5432-barca-chart-0956Z.png`.

The 3% is not a wrong win probability. It is a CORRECT price for a different
question: `FC Barcelona vs. Feyenoord Rotterdam - Exact Score`. Polymarket mints
a dozen derivative books per fixture — Exact Score, Second Half Result, More
Markets, Both Teams to Score, First Team to Score — each wearing the match's own
title, and for months the blend's Polymarket leg resolved one of those and wrote
its price into `win_prob_snapshots` as the match winner.

THE PRODUCER IS ALREADY FIXED AND THIS IS THE RESIDUE. #5323 (`bb79264d`, v4446,
2026-09-11 23:35Z) gates new writes on the shared class recognizer. It holds.
Measured on production 2026-09-12 ~09:5xZ, over every Polymarket snapshot row
written since that release, classified by the row's OWN recorded producer:

    admissible producers      214 markets    3,308 rows
    NON-admissible producers    0 markets        0 rows

That reading is NON-VACUOUS in the way a starved rail is not: the zero and the
3,308 come out of one query over one window, so the rail is provably alive. No
new bad rows are arriving, and nothing races this repair. But a gate governs
WRITES; it does not retract rows already in the table, and the chart draws the
table.

── WHY THE SCREEN IS THE ROW, NOT THE EVENT ────────────────────────────────────

The obvious screen is "an event with no admissible Polymarket market", and it is
WRONG — it convicts rows on evidence about their event's market list when the
row itself carries the truth. Event 15309638 (Guardians-Twins) has 42 Polymarket
markets and not one is a bare matchup; every event-level screen calls it
derivative-only and plans its 109 Polymarket rows for deletion. Those rows say:

    market_id 60383004 | market_name 'Cleveland Guardians vs. Minnesota Twins'

— a genuine moneyline, correctly oriented, whose `futures_markets.event_id`
points at 15310687, this game's TWIN. The market was split off onto the duplicate
event; the snapshots stayed. An event-level repair deletes 109 good rows and
leaves the reader worse off, and the twin population is exactly where that
mistake concentrates. (This is #5432's own descope of Defect 1 reproduced from
the other side: the issue read 15309638 as *having* a `cls=moneyline` market and
concluded the fallback works. Both readings are event-level; both are answering
a question the row already answers.)

So the unit of judgement is the SNAPSHOT ROW, and the evidence is the producer
it recorded at write time:

    game_state->>'market_name'  ->  live_blend._class_says_game_winner

Write-time, not a lookup of `futures_markets` today. A market's row is mutable —
60587848 is the standing proof that a producer can be re-pointed, renamed or
re-linked long after it wrote — and re-deriving the verdict from today's market
row would judge a 2026-08-30 write by a 2026-09-12 fact.

THE RECOGNIZER IS CALLED, NEVER COPIED. `_class_says_game_winner` is imported and
invoked on a shim carrying the recorded name, so this script cannot drift from
the gate that #5323 installed — the #1951 failure is a second copy that does not
throw when it disagrees, it just quietly answers differently. `external_id` on
the shim is None, and that is not a shortcut: the recognizer consults it only to
read a Kalshi `kx…` ticker, and every row here is `source='polymarket'`, whose
external ids are opaque numerics. `test_shim_external_id_is_inert_5432` pins it.

FAIL-OPEN ON ABSENCE, the same asymmetry `outcomes_refute_game_winner` argues
for. A row whose `game_state` records no `market_name` is NO EVIDENCE, not
evidence of guilt, and is never planned — deleting it would be a guess about a
producer nobody wrote down. Measured all-time on 2026-09-12 ~10:0xZ: of
1,557,588 Polymarket snapshot rows, 583,827 carry a producer name and 973,761
do not (the older `{market_id, backfill: True}` shape, concentrated before
August). The 973,761 are REPORTED by every run and repaired by none, so the
residue this leaves is counted rather than silently dropped (gotcha #53).

── THE COHORT, measured on production 2026-09-12 10:0x-10:1xZ ──────────────────

Producers are classified by name, rows are attributed by event; the two counts
were derived independently and agree to the row (150,818), which is the
cross-check that the name screen and the row screen are the same screen.

    distinct producers carrying a name            16,499    583,827 rows
      admissible to the shared gate               10,800    433,009 rows
      REFUTED                                      5,699    150,818 rows

    refuted rows, by event                                  150,818 rows / 5,057 events
      REFUSE — the delete would leave no chart at all         9,840 rows / 1,307 events
      DELETE                                                140,978 rows / 3,750 events

The refusal is not decoration: it declines 26% of the events in the plan. Of the
1,568 events the delete would strip of every win-probability row, 1,307 have no
odds snapshot either and are refused; the other 261 keep a sportsbook line and
proceed, which is exactly the #5432 acceptance-2 shape (`15297734` is the named
specimen — ux/1205 measured it drawing a clean 827-point sportsbook curve with
no Polymarket legend entry).

── THE REFUSAL, WHICH IS THE GROUP-COST TEST ───────────────────────────────────

A rule's verdict is about a row; the cost of the verdict is borne by the page.
Deleting an event's whole Polymarket line is the INTENDED outcome here (#5432
acceptance 2: a derivative-only group draws an honest blank, never the
best-looking prop) — but only while something else still draws. So a candidate
is refused if deleting it would leave its event with no win-probability row from
ANY source AND no odds snapshot to draw a sportsbook line from, i.e. an event
whose chart this repair would empty. Those pages are a different and much larger
defect (#3612, "Tracking will begin when odds are available") and this repair
must not quietly enlarge it.

WHAT IS NOT TOUCHED, each with another owner:

  * `futures_markets` / `futures_outcomes` — no market is retired, renamed or
    re-linked here. The derivative books are real books and keep their prices.
  * `Event.win_probability_sources` — the live blend's current reading. #5323
    already governs it; a row in this table is history, not the live number.
  * any row whose recorded producer IS a game winner, on any event, including
    the twins above.
  * `odds_snapshots` / `espn_snapshots` — the other two chart rails, untouched,
    which is what makes the refusal above computable.

RESTORE, one command (D51(b)):

    INSERT INTO win_prob_snapshots
    SELECT b.* FROM bak_5432_win_prob_snapshots b
     WHERE b.id IN (SELECT snapshot_id FROM bak_5432_repair_manifest)
       AND NOT EXISTS (SELECT 1 FROM win_prob_snapshots s WHERE s.id = b.id);

  The restore is only as honest as the backup, and #5595 is why `--backup`
  now checks the backup by CONTENT rather than by id. A row staged in one
  session, re-parented to another event, then deleted by a later pass used to
  restore with its stale `event_id` — a snapshot hung on a game it never
  belonged to — because every gate on that path asked only "is this id in the
  backup table?". `--backup` now evicts and re-stages a drifted row, and
  `--apply` refuses while `stale_backup_rows` is non-zero.

USAGE:

    python3 scripts/repair_5432_derivative_polymarket_win_prob_snapshots.py
    python3 scripts/repair_5432_derivative_polymarket_win_prob_snapshots.py --backup
    python3 scripts/repair_5432_derivative_polymarket_win_prob_snapshots.py --backup --apply
"""

import argparse
import asyncio
import collections
import os
import sys
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_5432_win_prob_snapshots"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited via #5221/#5246). A full-row backup records where a row came from
#: and cannot record that this script is what removed it.
MANIFEST_TABLE = "bak_5432_repair_manifest"

#: The rows this repair can even see. A row without a recorded producer is not
#: judged — see the module docstring on fail-open.
PRODUCER_KEY = "market_name"

#: The sanity floor, ~80% of the 140,978-row plan measured on production
#: 2026-09-12 10:1xZ (see the module docstring's cohort table).
#:
#: Two causes present as a small plan — a broken filter and an already-drained
#: backlog — so the floor is paired with a DISCRIMINATOR rather than an
#: `--allow-small` override, which would let the first through wearing the
#: second's clothes (the #5246 lesson, where the discriminator existed and did
#: not reach the decision).
#:
#: This population only SHRINKS: the producer gate (#5323) has been holding
#: since 2026-09-11 23:35Z, so no new refuted row can join it. A plan that has
#: grown is therefore itself a finding.
SANITY_FLOOR = 112_000

SQL = {
    # Stage 1. The DISTINCT producer names, which is a few thousand rows rather
    # than the ~1.5M-row candidate set — the recognizer runs in Python, so the
    # scan must hand it names, not rows.
    "producers": f"""
        SELECT game_state->>'{PRODUCER_KEY}' AS market_name,
               count(*)                      AS n_rows
          FROM win_prob_snapshots
         WHERE source = 'polymarket'
           AND game_state ? '{PRODUCER_KEY}'
         GROUP BY 1
         ORDER BY 1
    """,
    # How much of the population carries no producer at all, so the fail-open
    # residue is REPORTED rather than silently dropped (gotcha #53).
    "unjudgeable": f"""
        SELECT count(*) AS n_rows, count(DISTINCT event_id) AS n_events
          FROM win_prob_snapshots
         WHERE source = 'polymarket'
           AND NOT (game_state ? '{PRODUCER_KEY}')
    """,
    # Stage 2. Every row a refuted producer wrote.
    "rows_for_producers": f"""
        SELECT id, event_id
          FROM win_prob_snapshots
         WHERE source = 'polymarket'
           AND game_state->>'{PRODUCER_KEY}' = ANY(CAST(:names AS text[]))
         ORDER BY event_id, id
    """,
    # Stage 3, the group-cost test. For every event in the plan: what would
    # still draw after the delete? `win_prob_snapshots` rows that are NOT in the
    # plan (any source, including Polymarket rows a winner market wrote), and
    # odds snapshots, which this repair never touches.
    "survivors": """
        SELECT e.id AS event_id,
               (SELECT count(*) FROM win_prob_snapshots w
                 WHERE w.event_id = e.id
                   AND NOT (w.id = ANY(CAST(:doomed AS int[])))) AS wp_left,
               (SELECT count(*) FROM odds_snapshots o
                 WHERE o.event_id = e.id)                        AS odds_left
          FROM events e
         WHERE e.id = ANY(CAST(:events AS int[]))
    """,
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE win_prob_snapshots INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM win_prob_snapshots s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM win_prob_snapshots s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # #5595 — PRESENCE BY ID IS NOT COVERAGE, AND THE GAP RESTORES ONTO THE
    # WRONG EVENT. `bak_copy` skips any id already in the backup and
    # `bak_missing` asks only whether the id is there, so a row backed up in an
    # earlier session and then RE-PARENTED to another `event_id` reconciles
    # clean. The delete's CAS covers source and producer name, not parentage,
    # so the row is still removed — and the documented undo then reinserts the
    # backup's stale `event_id`, hanging a snapshot on a game it never belonged
    # to. A whole-row `IS DISTINCT FROM` is the test, not an `event_id`
    # comparison: any column that drifted makes the backup a false record of
    # what was deleted, and enumerating the columns here would silently stop
    # covering a column added to `win_prob_snapshots` later.
    "bak_stale": f"SELECT count(*) FROM win_prob_snapshots s "
                 f"JOIN {BAK_TABLE} b ON b.id = s.id "
                 f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                 f"AND (b.*) IS DISTINCT FROM (s.*)",
    # The repair, not merely the alarm: drop the divergent backup rows so the
    # ordinary `bak_copy` re-stages them from live. A row still present in
    # `win_prob_snapshots` has not been deleted by any pass, so live is the
    # truth the undo must be able to restore — refreshing loses nothing.
    "bak_evict_stale": f"DELETE FROM {BAK_TABLE} b "
                       f"USING win_prob_snapshots s "
                       f"WHERE b.id = s.id AND s.id = ANY(CAST(:ids AS int[])) "
                       f"AND (b.*) IS DISTINCT FROM (s.*)",
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run. A missing table yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  snapshot_id integer PRIMARY KEY,"
                  f"  event_id    integer NOT NULL,"
                  f"  applied_at  timestamptz NOT NULL DEFAULT NOW())",
    "man_record": f"INSERT INTO {MANIFEST_TABLE} (snapshot_id, event_id, applied_at) "
                  f"SELECT unnest(CAST(:ids AS int[])), "
                  f"       unnest(CAST(:events AS int[])), :now "
                  f"ON CONFLICT (snapshot_id) DO UPDATE SET "
                  f"  event_id = EXCLUDED.event_id,"
                  f"  applied_at = EXCLUDED.applied_at",
    # THE FORWARD WRITE, and it is a compare-and-swap on the premise. If a row's
    # recorded producer changed between the plan and the write, the delete
    # no-ops rather than removing a row this plan never judged.
    "delete": f"DELETE FROM win_prob_snapshots "
              f"WHERE id = ANY(CAST(:ids AS int[])) "
              f"  AND source = 'polymarket' "
              f"  AND game_state->>'{PRODUCER_KEY}' = ANY(CAST(:names AS text[])) "
              f"RETURNING id, event_id",
}


class _RecordedMarket:
    """The producer a snapshot row RECORDED, shaped for the shared recognizer.

    `external_id` is None on purpose and it is inert here: the recognizer reads
    it only to spot a Kalshi `kx…` ticker (a `KXNBA2HSPREAD` title that looks
    like a bare matchup is really a spread), and every row this script can see
    is `source='polymarket'`, whose external ids are opaque numerics that match
    no branch. Pinned by `test_shim_external_id_is_inert_5432` so a future
    recognizer that DOES read a Polymarket id fails the guard instead of
    silently re-classifying the population.
    """

    __slots__ = ("name", "external_id")

    def __init__(self, name: Optional[str]) -> None:
        self.name = name
        self.external_id = None


def producer_is_game_winner(market_name: Optional[str]) -> bool:
    """Call the ONE shared admission rule on a recorded producer name.

    Imported inside the function so the module stays importable — and its pure
    helpers testable — without dragging the app's model layer into the process.
    """
    from app.utils.live_blend import _class_says_game_winner

    return _class_says_game_winner(_RecordedMarket(market_name))


def refuted_producers(producer_rows) -> list[str]:
    """The producer names whose rows are candidates: every one the gate refuses.

    Takes the aggregate rows rather than the raw snapshots because the
    recognizer's answer is a property of the NAME, and there are three orders of
    magnitude more rows than names.

    A NULL, empty or WHITESPACE-ONLY name is skipped rather than classified. It
    reaches here only if `game_state ? 'market_name'` is true with a blank
    value, which is a producer that wrote no name — the fail-open case, not a
    refutation.

    🔴 THE STRIP IS LOAD-BEARING AND THE FIRST DRAFT DID NOT HAVE IT. `"   "` is
    truthy in Python, so a bare `if not name` let a whitespace name through to
    the recognizer, which answers "not a game winner" for it — and the rows
    would have been DELETED on no evidence at all, the one direction this
    function is built to refuse. Caught by
    `test_a_producer_with_no_name_is_never_planned_5432`.
    """
    names = []
    for row in producer_rows:
        entry = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        name = entry.get("market_name")
        if not name or not name.strip():
            continue
        if not producer_is_game_winner(name):
            names.append(name)
    return names


def refuse_events_that_would_go_dark(survivor_rows) -> set:
    """Events where the delete would leave NO chart at all.

    The verdict is about a row and the cost is borne by the page, so the test
    population is not the row — it is whatever has to survive the row being
    refused. An event keeps its chart if ANY win-prob row outlives the plan
    (from any source, including a Polymarket row a genuine winner market wrote)
    or if it has an odds snapshot to draw a sportsbook line from.

    Both, and not either alone: `win_prob_history` and the sportsbook `history`
    array are separate rails in `/api/events/{id}/history`, and an event page
    draws its empty state only when both are bare.
    """
    dark = set()
    for row in survivor_rows:
        entry = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        if not int(entry["wp_left"] or 0) and not int(entry["odds_left"] or 0):
            dark.add(entry["event_id"])
    return dark


def backup_is_exact(recon) -> bool:
    """The D51 gate: every planned row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


class SmallPlanVerdict(NamedTuple):
    """A small plan's diagnosis AND what it means for `--apply`.

    Two facts, deliberately not collapsed into one string: #5246 shipped this
    discriminator as a bare message while the caller tested `if small:`, so both
    causes refused `--apply` identically and the discriminator only ever changed
    the wording of the refusal. It cost that repair a session.
    """

    blocks_apply: bool
    message: str


def explain_small_plan(plan_count: int, manifest_rows: int) -> SmallPlanVerdict:
    """Why is the plan below the floor — a broken filter, or a drained backlog?

    The manifest is the discriminator, because only a successful forward write
    puts a row in it. Fail-closed stays the default: an unrecognised shape would
    have to be added here deliberately, as a blocking one.
    """
    if plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(blocks_apply=False, message="")
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(
            blocks_apply=False,
            message=(
                f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} "
                f"and {plan_count} remain deletable; together they clear the "
                f"floor of {SANITY_FLOOR}. This is a drained backlog, not a "
                f"broken filter, so --apply proceeds."
            ),
        )
    return SmallPlanVerdict(
        blocks_apply=True,
        message=(
            f"FILTER BROKE — only {plan_count} rows are deletable and "
            f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} "
            f"of an expected {SANITY_FLOOR}+ are accounted for. Either the "
            f"producer scan stopped matching or the recognizer moved. Do NOT "
            f"lower the floor; find the rows."
        ),
    )


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def backup(session, ids) -> int:
    """Stage the undo, refreshing any row that drifted since an earlier pass.

    Returns the number of stale backup rows evicted and re-staged (#5595), so
    the caller can say so out loud rather than silently repairing.
    """
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    refreshed = 0
    for chunk in _chunks(ids, 5000):
        # Evict BEFORE copying: `bak_copy` skips ids already present, so a
        # divergent row would otherwise never be re-staged. Ordering is the
        # whole fix.
        refreshed += int(
            (
                await session.execute(text(SQL["bak_evict_stale"]), {"ids": chunk})
            ).rowcount
            or 0
        )
        await session.execute(text(SQL["bak_copy"]), {"ids": chunk})
    await session.commit()
    return refreshed


async def reconcile_backup(session, ids) -> dict:
    """Does the backup cover every planned row, by CONTENT and not just by id?

    Two keys, deliberately not summed: `missing` means no backup row exists,
    `stale` means one exists and disagrees with the live row. They have
    different causes and the second is the #5595 defect, so collapsing them
    into one count would hide which one fired.
    """
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = 0
    stale = 0
    for chunk in _chunks(ids, 5000):
        missing += int(
            (await session.execute(text(SQL["bak_missing"]), {"ids": chunk})).scalar_one()
        )
        stale += int(
            (await session.execute(text(SQL["bak_stale"]), {"ids": chunk})).scalar_one()
        )
    return {"win_prob_snapshots": missing, "stale_backup_rows": stale}


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        producers = (await s.execute(text(SQL["producers"]))).fetchall()
        names = refuted_producers(producers)
        total_named = sum(int(dict(p._mapping)["n_rows"]) for p in producers)
        unjudged = dict(
            (await s.execute(text(SQL["unjudgeable"]))).fetchone()._mapping
        )

        print(f"producers with a recorded name : {len(producers)} "
              f"({total_named} rows)")
        print(f"  refuted by the shared gate   : {len(names)}")
        print(f"rows with NO recorded producer : {unjudged['n_rows']} "
              f"across {unjudged['n_events']} events (never judged, fail-open)")

        if not names:
            print("\nno refuted producer — nothing to plan.")
            return

        rows = []
        for chunk in _chunks(names, 500):
            rows += (
                await s.execute(text(SQL["rows_for_producers"]), {"names": chunk})
            ).fetchall()
        doomed = [int(dict(r._mapping)["id"]) for r in rows]
        by_event = collections.OrderedDict()
        for r in rows:
            e = dict(r._mapping)
            by_event.setdefault(int(e["event_id"]), []).append(int(e["id"]))

        survivors = (
            await s.execute(
                text(SQL["survivors"]),
                {"doomed": doomed, "events": list(by_event)},
            )
        ).fetchall()
        dark = refuse_events_that_would_go_dark(survivors)

        plan_ids, plan_events, refused_rows = [], [], 0
        for event_id, ids in by_event.items():
            if event_id in dark:
                refused_rows += len(ids)
                continue
            plan_ids.extend(ids)
            plan_events.extend([event_id] * len(ids))

        if args.limit:
            plan_ids, plan_events = plan_ids[: args.limit], plan_events[: args.limit]

        print(f"\nDELETE : {len(plan_ids)} rows / "
              f"{len(set(plan_events))} events")
        print(f"REFUSE : {refused_rows} rows / {len(dark)} events "
              f"(the delete would leave no chart at all)")

        manifest_rows = await manifest_count(s)
        small = explain_small_plan(len(plan_ids), manifest_rows)
        if small.message:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"   {small.message}")

        if not args.backup and not args.apply:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return

        if not plan_ids:
            print("\nnothing to do.")
            return

        if args.backup:
            refreshed = await backup(s, plan_ids)
            print(f"\nbacked up {len(plan_ids)} rows into {BAK_TABLE}")
            if refreshed:
                print(
                    f"  refreshed {refreshed} stale backup rows that had drifted "
                    f"since an earlier pass (#5595) — restoring them would have "
                    f"written a stale event_id"
                )

        recon = await reconcile_backup(s, plan_ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned row.")
            return

        if not args.apply:
            print("\nbackup staged — re-run with --apply to write.")
            return

        if small.blocks_apply:
            print("REFUSING --apply: plan is below the sanity floor (see above).")
            return

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = 0
        for chunk in _chunks(plan_ids, 2000):
            gone = (
                await s.execute(text(SQL["delete"]), {"ids": chunk, "names": names})
            ).fetchall()
            if gone:
                await s.execute(
                    text(SQL["man_record"]),
                    {
                        "ids": [int(dict(g._mapping)["id"]) for g in gone],
                        "events": [int(dict(g._mapping)["event_id"]) for g in gone],
                        "now": now,
                    },
                )
            applied += len(gone)
        await s.commit()
        declined = len(plan_ids) - applied
        print(f"\napplied {applied}, declined {declined} "
              f"(a decline means the row moved under us — the good case)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="copy every planned row into the backup table first")
    p.add_argument("--apply", action="store_true",
                   help="delete the rows (requires an exact backup)")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
