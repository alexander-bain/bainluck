"""#9348 / #9417 — retire the Polymarket chart rows a not-the-match market wrote.

WHAT A READER SEES TODAY. ``/events/15319905`` (Rajecki): between 4:00 and
6:30 AM PT the Win Probability chart steps to 98% and back, and on
``/events/15320043`` (Hunter v Zhang) the line spikes 06:10–06:16Z. Those
points are the price of Polymarket's tennis novelty ``China Open,
Qualification: Completed Match: Ruien Zhang vs Storm Hunter`` ("will the match
be completed?", Yes 0.98) drawn as a win probability. Same class, bigger:
``/events/15317139`` (SC Braga v Sporting CP) interleaves 0.225 — the
``Halftime Result`` book — with the match price 0.27 (#9417).

THE PRODUCERS ARE FIXED AND THIS IS THE RESIDUE. #9348 (``5134409fb3``) made
``admissible_as_blend_speaker`` refuse a market whose venue label says it is
not a full-contest winner; the live poll and the matcher stopped writing the
novelty once main (11:48Z) and heavy v112 (15:47Z, 2026-09-28) carried it.
The matcher's Phase 3 history backfill asked no admission rule at all and kept
writing ``{"market_id": N, "backfill": true}`` rows for Halftime Result, First
to Score and Exact Score books; #9417 gates it in the same change as this
script. Neither gate retracts a row already in ``win_prob_snapshots``, and the
chart draws that table.

── THE UNIT IS THE ROW, THE EVIDENCE IS ITS ``market_id`` ──────────────────────

Every row here recorded the market that produced it in
``game_state->>'market_id'`` — the live shape and the backfill shape alike (the
backfill shape carries no ``market_name``, which is why #5432's name-keyed
repair could never see it). The verdict is the venue's own label on that
market, read by the SAME predicate the admission gate reads:
``content_understanding.venue_label_refutes_full_contest_winner``, imported and
called, never copied (#1951).

The label is the venue's (Gamma ``sportsMarketType``), not our classifier's, so
it cannot go stale the way a title verdict can: a market labelled
``soccer_halftime_result`` today was a halftime-result market when it wrote.

FAIL-OPEN ON ABSENCE, twice. A row with no ``market_id`` is never judged. A
market with no label (about a fifth of Polymarket, and every market stamped
before the label existed in mid-September) refutes nothing and its rows are
never planned. Both are the predicate's own answer, not a filter added here.

── THE COHORT, measured on production 2026-09-28 16:3xZ ────────────────────────

``win_prob_snapshots`` source=polymarket whose market carries a venue label
other than ``moneyline`` — every month before September reads 0 (no labels):

    soccer_halftime_result           31,588 rows / 325 events   (backfill)
    soccer_first_to_score            20,798 rows /  46 events   (backfill)
    soccer_second_half_result         4,073 rows /  26 events   (backfill)
    soccer_exact_score                3,261 rows / ~150 events  (2,297 backfill)
    tennis_completed_match            1,265 rows /  40 events   (live poll, #9348)
    smaller families                    696 rows

── THE REFUSAL (the group-cost test, inherited from #5432) ─────────────────────

A candidate is refused if deleting it would leave its event with no
win-probability row from ANY source AND no odds snapshot — i.e. a page this
repair would empty. Those pages belong to #3612, not to this script.

WHAT IS NOT TOUCHED: ``futures_markets`` / ``futures_outcomes`` (the books are
real and keep their prices); ``Event.win_probability_sources`` (the live number,
governed by the gate); any row whose market is unlabelled or labelled
``moneyline``; ``odds_snapshots`` / ``espn_snapshots``.

RESTORE, one command (D51(b)):

    heroku run:detached -a bainluck-heavy -- \\
        python3 scripts/repair_9348_refuted_venue_label_win_prob_snapshots.py --restore

  which runs:

    INSERT INTO win_prob_snapshots
    SELECT b.* FROM bak_9348_win_prob_snapshots b
     WHERE b.id IN (SELECT snapshot_id FROM bak_9348_repair_manifest)
       AND NOT EXISTS (SELECT 1 FROM win_prob_snapshots s WHERE s.id = b.id);

  The delete swaps on the WHOLE backed-up row (#5595), so every row this script
  removed has a byte-identical backup, or it was not removed.

USAGE (plan-only runs anywhere; every write refuses off ``bainluck-heavy``):

    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_9348_refuted_venue_label_win_prob_snapshots.py
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_9348_refuted_venue_label_win_prob_snapshots.py --backup
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_9348_refuted_venue_label_win_prob_snapshots.py --backup --apply

Runtime DDL (``CREATE TABLE IF NOT EXISTS bak_9348_*``), attended invocation
only — notice 47(c), not migration class. Nothing here runs on merge or release.
Gotcha #48: ``heroku run`` without ``:detached`` fails silently in the sandbox.
"""

import argparse
import asyncio
import collections
import os
import sys
from datetime import date
from typing import NamedTuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

#: Only this app may write — notice 47(c).
PRODUCER_APP = "bainluck-heavy"

BAK_TABLE = "bak_9348_win_prob_snapshots"
MANIFEST_TABLE = "bak_9348_repair_manifest"

#: The first month holding a Polymarket snapshot (2026-01-22). The scan walks
#: month by month from here because one all-time pass over the ~1.5M-row source
#: times out; months before the label existed simply return nothing.
FIRST_MONTH = date(2026, 1, 1)

#: ~75% of the 61,681 candidate rows measured 2026-09-28 16:3xZ. Paired with the
#: manifest discriminator exactly as #5432's floor is (a drained backlog and a
#: broken filter both present as a small plan).
SANITY_FLOOR = 46_000

SQL = {
    # Stage 1, one month at a time. The DISTINCT producers whose market carries
    # SOME venue label — a superset the predicate then decides in Python. The
    # SQL narrows; it never judges (a `<> 'moneyline'` here would be a second
    # copy of the rule).
    "candidate_markets": """
        SELECT DISTINCT fm.id AS market_id,
               fm.market_metadata->'content_understanding_v1' AS understanding
          FROM win_prob_snapshots s
          JOIN futures_markets fm
            ON fm.id = (s.game_state->>'market_id')::int
         WHERE s.source = 'polymarket'
           AND s.captured_at >= :lo AND s.captured_at < :hi
           AND s.game_state ? 'market_id'
           AND fm.market_metadata->'content_understanding_v1'->>'venue_type'
               IS NOT NULL
    """,
    # Stage 2, same month: every row a refuted producer wrote.
    "rows_for_markets": """
        SELECT id, event_id
          FROM win_prob_snapshots
         WHERE source = 'polymarket'
           AND captured_at >= :lo AND captured_at < :hi
           AND game_state->>'market_id' = ANY(CAST(:mids AS text[]))
         ORDER BY event_id, id
    """,
    # Stage 3, the group-cost test: what each planned event holds in total.
    # Survivors are computed in Python as total minus planned, which avoids
    # handing Postgres a 60k-element NOT IN per event.
    "event_totals": """
        SELECT e.id AS event_id,
               (SELECT count(*) FROM win_prob_snapshots w
                 WHERE w.event_id = e.id)                   AS wp_total,
               (SELECT count(*) FROM odds_snapshots o
                 WHERE o.event_id = e.id)                   AS odds_total
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
    # #5595: presence by id is not coverage — a whole-row comparison is.
    "bak_stale": f"SELECT count(*) FROM win_prob_snapshots s "
                 f"JOIN {BAK_TABLE} b ON b.id = s.id "
                 f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                 f"AND (b.*) IS DISTINCT FROM (s.*)",
    "bak_evict_stale": f"DELETE FROM {BAK_TABLE} b "
                       f"USING win_prob_snapshots s "
                       f"WHERE b.id = s.id AND s.id = ANY(CAST(:ids AS int[])) "
                       f"AND (b.*) IS DISTINCT FROM (s.*)",
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
    # The forward write: a compare-and-swap on the premise (source + producer)
    # AND on the whole backed-up row, so a row that moved after reconciliation
    # is declined rather than removed without a faithful undo.
    "delete": f"DELETE FROM win_prob_snapshots s "
              f"WHERE s.id = ANY(CAST(:ids AS int[])) "
              f"  AND s.source = 'polymarket' "
              f"  AND s.game_state->>'market_id' = ANY(CAST(:mids AS text[])) "
              f"  AND EXISTS (SELECT 1 FROM {BAK_TABLE} b "
              f"               WHERE b.id = s.id "
              f"                 AND (b.*) IS NOT DISTINCT FROM (s.*)) "
              f"RETURNING s.id, s.event_id",
    "restore": f"INSERT INTO win_prob_snapshots "
               f"SELECT b.* FROM {BAK_TABLE} b "
               f"WHERE b.id IN (SELECT snapshot_id FROM {MANIFEST_TABLE}) "
               f"AND NOT EXISTS (SELECT 1 FROM win_prob_snapshots s "
               f"                WHERE s.id = b.id)",
}


def wrong_app_refusal() -> Optional[str]:
    """A refusal string unless this process runs on :data:`PRODUCER_APP`."""
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to write on HEROKU_APP_NAME={app!r}: this repair changes "
        f"production rows and writes only on {PRODUCER_APP!r}"
    )


class _RecordedMarket:
    """A producer market shaped for the shared predicate: its metadata only."""

    __slots__ = ("market_metadata",)

    def __init__(self, understanding) -> None:
        self.market_metadata = (
            {"content_understanding_v1": understanding}
            if understanding is not None else None
        )


def producer_is_refuted(understanding) -> bool:
    """Ask the ONE venue-label predicate the admission gate asks (#9348)."""
    from app.utils.content_understanding import (
        venue_label_refutes_full_contest_winner,
    )

    return venue_label_refutes_full_contest_winner(_RecordedMarket(understanding))


def _as_dict(row) -> dict:
    return dict(row._mapping) if hasattr(row, "_mapping") else dict(row)


def refuted_market_ids(candidate_rows) -> list[str]:
    """The producer ids whose rows are candidates, as the text ``game_state`` holds.

    A db driver may hand the JSONB subobject back as a dict or, through some
    paths, as its JSON text; both are read. Anything else is no evidence.
    """
    import json

    out = []
    for row in candidate_rows:
        entry = _as_dict(row)
        understanding = entry.get("understanding")
        if isinstance(understanding, str):
            try:
                understanding = json.loads(understanding)
            except ValueError:
                continue
        if entry.get("market_id") is None:
            continue
        if producer_is_refuted(understanding):
            out.append(str(int(entry["market_id"])))
    return out


def refuse_events_that_would_go_dark(total_rows, planned_by_event) -> set:
    """Events where the delete would leave NO chart at all (#5432's group-cost test)."""
    dark = set()
    for row in total_rows:
        entry = _as_dict(row)
        event_id = int(entry["event_id"])
        wp_left = int(entry["wp_total"] or 0) - len(planned_by_event.get(event_id, ()))
        if wp_left <= 0 and not int(entry["odds_total"] or 0):
            dark.add(event_id)
    return dark


def backup_is_exact(recon) -> bool:
    """Every planned row has a faithful backup, and something was checked."""
    return bool(recon) and all(n == 0 for n in recon.values())


class SmallPlanVerdict(NamedTuple):
    blocks_apply: bool
    message: str


def explain_small_plan(plan_count: int, manifest_rows: int) -> SmallPlanVerdict:
    """Below the floor: a drained backlog (manifest covers it) or a broken filter."""
    if plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(False, "")
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return SmallPlanVerdict(
            False,
            f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} and "
            f"{plan_count} remain; together they clear {SANITY_FLOOR}.",
        )
    return SmallPlanVerdict(
        True,
        f"FILTER BROKE — {plan_count} planned + {manifest_rows} applied of an "
        f"expected {SANITY_FLOOR}+. Do NOT lower the floor; find the rows.",
    )


def months(first: date, last: date):
    """Half-open ``[lo, hi)`` month windows from ``first`` through ``last``'s month."""
    lo = date(first.year, first.month, 1)
    while lo <= last:
        hi = date(lo.year + (lo.month == 12), lo.month % 12 + 1, 1)
        yield lo, hi
        lo = hi


def _chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def backup(session, ids) -> int:
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    refreshed = 0
    for chunk in _chunks(ids, 5000):
        refreshed += int(
            (await session.execute(text(SQL["bak_evict_stale"]), {"ids": chunk})).rowcount
            or 0
        )
        await session.execute(text(SQL["bak_copy"]), {"ids": chunk})
    await session.commit()
    return refreshed


async def reconcile_backup(session, ids) -> dict:
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = stale = 0
    for chunk in _chunks(ids, 5000):
        missing += int(
            (await session.execute(text(SQL["bak_missing"]), {"ids": chunk})).scalar_one()
        )
        stale += int(
            (await session.execute(text(SQL["bak_stale"]), {"ids": chunk})).scalar_one()
        )
    return {"win_prob_snapshots": missing, "stale_backup_rows": stale}


async def plan(session, today: date):
    """Walk the months; return ``(refuted_mids, by_event)``."""
    from sqlalchemy import text

    mids: set[str] = set()
    by_event: dict[int, list[int]] = collections.OrderedDict()
    for lo, hi in months(FIRST_MONTH, today):
        window = {"lo": lo, "hi": hi}
        candidates = (
            await session.execute(text(SQL["candidate_markets"]), window)
        ).fetchall()
        month_mids = refuted_market_ids(candidates)
        n_rows = 0
        for chunk in _chunks(month_mids, 2000):
            rows = (
                await session.execute(
                    text(SQL["rows_for_markets"]), {**window, "mids": chunk}
                )
            ).fetchall()
            for r in rows:
                e = _as_dict(r)
                by_event.setdefault(int(e["event_id"]), []).append(int(e["id"]))
            n_rows += len(rows)
        mids.update(month_mids)
        print(f"  {lo:%Y-%m}: {len(candidates)} labelled producers, "
              f"{len(month_mids)} refuted, {n_rows} rows")
    return sorted(mids), by_event


async def run(args) -> int:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    writes = args.backup or args.apply or args.restore
    if writes:
        refusal = wrong_app_refusal()
        if refusal:
            print(f"REFUSED: {refusal}")
            return 2

    async with get_task_session() as s:
        if args.restore:
            if not await _table_exists(s, "man_exists"):
                print("nothing to restore: no manifest table.")
                return 0
            restored = (await s.execute(text(SQL["restore"]))).rowcount or 0
            await s.commit()
            print(f"restored {restored} rows from {BAK_TABLE}")
            return 0

        print("#9348 — Polymarket rows whose producer's venue label refutes "
              "a full-contest winner")
        mids, by_event = await plan(s, datetime.now(timezone.utc).date())
        if not mids:
            print("\nno refuted producer — nothing to plan.")
            return 0

        totals = []
        events = list(by_event)
        for chunk in _chunks(events, 500):
            totals += (
                await s.execute(text(SQL["event_totals"]), {"events": chunk})
            ).fetchall()
        dark = refuse_events_that_would_go_dark(totals, by_event)

        plan_ids, plan_events, refused_rows = [], [], 0
        for event_id, ids in by_event.items():
            if event_id in dark:
                refused_rows += len(ids)
                continue
            plan_ids.extend(ids)
            plan_events.extend([event_id] * len(ids))
        # The floor judges the FILTER, so it reads the whole plan; `--limit`
        # only sizes the batch written after it.
        small = explain_small_plan(len(plan_ids), await manifest_count(s))
        if args.limit:
            plan_ids, plan_events = plan_ids[: args.limit], plan_events[: args.limit]

        print(f"\nrefuted producers : {len(mids)}")
        print(f"DELETE            : {len(plan_ids)} rows / {len(set(plan_events))} events")
        print(f"REFUSE            : {refused_rows} rows / {len(dark)} events "
              f"(the delete would leave no chart at all)")

        if small.message:
            print(f"\n⚠️  {small.message}")

        if not writes:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return 0
        if not plan_ids:
            print("\nnothing to do.")
            return 0

        if args.backup:
            refreshed = await backup(s, plan_ids)
            print(f"\nbacked up {len(plan_ids)} rows into {BAK_TABLE}"
                  + (f" (refreshed {refreshed} drifted)" if refreshed else ""))

        recon = await reconcile_backup(s, plan_ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned row.")
            return 1
        if not args.apply:
            print("\nbackup staged — re-run with --backup --apply to write.")
            return 0
        if small.blocks_apply:
            print("REFUSING --apply: plan is below the sanity floor (see above).")
            return 1

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = 0
        for chunk in _chunks(plan_ids, 2000):
            gone = (
                await s.execute(text(SQL["delete"]), {"ids": chunk, "mids": mids})
            ).fetchall()
            if gone:
                await s.execute(
                    text(SQL["man_record"]),
                    {
                        "ids": [int(_as_dict(g)["id"]) for g in gone],
                        "events": [int(_as_dict(g)["event_id"]) for g in gone],
                        "now": now,
                    },
                )
            applied += len(gone)
        await s.commit()
        print(f"\napplied {applied}, declined {len(plan_ids) - applied} "
              f"(a decline means the row moved under us — the good case)")
        print(f"verify: SELECT count(*) FROM win_prob_snapshots s JOIN "
              f"{MANIFEST_TABLE} m ON m.snapshot_id = s.id;  -- expect 0")
        print("undo:   python3 scripts/"
              "repair_9348_refuted_venue_label_win_prob_snapshots.py --restore")
        return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true",
                   help="copy every planned row into the backup table first")
    p.add_argument("--apply", action="store_true",
                   help="delete the rows (requires an exact backup)")
    p.add_argument("--restore", action="store_true",
                   help="re-insert every row this repair deleted")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    return asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
