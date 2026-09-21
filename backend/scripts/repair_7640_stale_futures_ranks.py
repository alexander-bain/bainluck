"""#7640 — drain the stale `futures_outcomes.rank` backlog #6598 could not reach.

SCOPE IN ONE LINE: every OPEN market whose stored `rank` disagrees with the
ordering of its own `current_probability` — 76,513 rows across 13,130 markets,
measured on production 2026-09-21 01:05Z. Settled boards are excluded and stay
excluded (#6325).


WHAT A READER SEES TODAY. `https://bainluck.com/sport/football/nfl/team/buffalo-bills`,
SEASON FUTURES, at phone width. Three consecutive cards, screenshot
`artifacts-lane1b-430/AFTER-crop-the-defect.png`:

    Tyler Bass     25%   #8 of 50    Fantasy Football: 2026-27 K Points Leader
    Dawson Knox    24%   #43 of 50   Fantasy Football: 2026-27 TE Points Leader
    DJ Moore       24%   #42 of 50   Fantasy Football: 2026-27 WR Points Leader

One percentage point of price, thirty-five places of rank. On board 58602257
Knox's 0.240 is the 14th-best price of 50 (`rank()` ties: 0.280 -> 1, ten legs at
0.250 -> 2, two at 0.245 -> 12, five at 0.240 -> 14). The badge says 43.

🔴 WHY A REPAIR AND NOT THE POLL CADENCE. #6598 wired every writer of the price
to re-derive its market's field before committing, and that works — among open
markets a writer touched after its release, 0 of 733 disagree, against a control
of 3,974 of 7,264 in the hour before. But it re-ranks a board only when a writer
NEXT TOUCHES IT, and it repaired nothing already wrong. `futures_rank`'s own
docstring used to say the fossils would drain on the ordinary cadence; that
sentence was measured wrong and is now corrected there. The sweep that would
drain them, `refresh_stale_futures_prices`, admits a market on `market_tier = 1`
OR `volume >= HIGH_VALUE_VOLUME_FLOOR` (10,000), and **10,145 of the affected
markets fail both arms** — board 58602257 is tier 5, volume 3,242, last written
by a socket flush. Nothing schedules them. The team page does not care about
tier or volume; it renders whatever the team matches.

🔴 THE FORWARD WRITE IS #6598'S OWN STATEMENT, IMPORTED, NOT COPIED. A repair
that re-derives `rank` from a window function of its own authorship is a second
opinion about the ordering, and a second opinion is the exact defect #6598 exists
to end: it would "fix" 13,130 boards to a rule the live writers do not follow and
the next poll would undo every one of them. So `rerank_market_fields_stmt` is
imported from `app.utils.futures_rank` and used verbatim, and the plan's SELECT
asks its question with `field_rank_expr()` — the same partition, the same
`rank()` tie rule, the same `DESC NULLS LAST`. There is no ordering rule in this
file. `tests/test_repair_7640_stale_futures_ranks.py` asserts that by AST, so a
later reader who "inlines it for clarity" fails a test.

🔴 THE BACKUP'S UNIT IS THE MARKET, BECAUSE THE WRITE'S UNIT IS THE MARKET.
Staging only the legs the plan found mismatched would be a backup with holes:
the statement re-derives the WHOLE field, so if a price moves between the plan
and the write it can legitimately renumber a leg the plan considered fine, and
that leg would then have a manifest row with nothing behind it. Every leg of
every planned market is staged. Backup granularity below write granularity is
how an undo silently stops being one.

🔴 THE RESTORE IS A COMPARE-AND-SWAP IN REVERSE, ON TWO COLUMNS. This is
`SQL["restore"]` below, verbatim — a named artifact rather than prose so the
guard test executes the thing a person pastes:

    UPDATE futures_outcomes o
       SET rank = b.rank
      FROM bak_7640_stale_ranks b
      JOIN bak_7640_repair_manifest m ON m.outcome_id = b.outcome_id
     WHERE b.outcome_id = o.id
       AND o.rank         IS NOT DISTINCT FROM m.wrote_rank
       AND o.last_updated IS NOT DISTINCT FROM m.seen_last_updated;

  THE LAST TWO LINES ARE LOAD-BEARING. An undo binds to what was WRITTEN, not to
  what was planned. Without them the restore is a second bug: this pass writes a
  correct rank, a poller then reprices the board and re-derives it (correctly),
  and a restore run afterwards puts the broken fossil back over live, correct
  numbers — re-creating on purpose the defect the repair just removed.

  `rank` alone cannot carry that test, and the reason is worth stating: when a
  poller re-derives a board it arrives at the SAME number this pass wrote, so
  "the row still holds what we wrote" is true both when nobody touched it and
  when somebody did. `last_updated` is the witness that separates them —
  #6598's statement names `rank` and nothing else and the column has no
  `onupdate`, so a re-rank provably cannot move it, while any real price write
  does. The manifest banks both, read from the forward write's own RETURNING.

🔴 SETTLED BOARDS ARE EXEMPT AND THE EXEMPTION IS RE-CHECKED AT WRITE TIME.
#6325 refused to renumber a finished field — its rank is the record of how it
finished, not a live ordering — and `backfill_winners` / `repair_winner_field`
are named exempt in `futures_rank`'s docstring for the same reason. The plan
scopes to `status = 'open'`, and because a market can settle between the plan and
the write, `still_open()` re-reads the status of every chunk immediately before
writing it and drops what has closed. A drop is reported, and a drop is the good
case.

NOT IN SCOPE, deliberately:

  * `rank_change_24h`. A different column with a different defect (#2408's
    class). Recomputing it here would mint a "moved N places" arrow spanning
    however long it has been since the row was last written — a louder lie than
    the stale value it replaces. #6598 left it alone for this reason and so does
    this.
  * `last_updated`. `routes/playoffs.py` reads it as a liveness gate and this is
    not a poll. Touching it would make a six-week-old row look seen today, and
    it would also destroy the restore's own witness (above).
  * Markets with no mismatch. `IS DISTINCT FROM` inside the shipped statement
    makes a healthy board one indexed scan and zero row writes, so a re-run after
    a partial pass is free and the script is resumable by simply being run again.

RUNTIME DDL, ATTENDED INVOCATION ONLY (standing notice 47(c)). The two
`CREATE TABLE IF NOT EXISTS bak_7640_*` statements run only when a person invokes
`--backup`; nothing here runs on merge or on release, and this is not
migration-class. `--backup`/`--apply` refuse unless `HEROKU_APP_NAME` is
`bainluck-heavy` — the app the dominant producer runs on, since
`refresh_stale_futures_prices` is in `HEAVY_TASKS` — so an 80k-row write cannot
be fired from a laptop pointed at production with whatever happens to be checked
out, and it does not occupy a web dyno. A dry run only reads, and runs anywhere.

USAGE. The dyno's root `/app` IS this repo's `backend/`, so the path on Heroku is
`scripts/...`, NOT `backend/scripts/...` — the latter fails with a bare
`Errno 2: No such file or directory`, which `heroku run:detached` reports as an
empty stdout (gotcha #48). Run from the repo root locally; run without the
`backend/` prefix on the dyno.

    python3 backend/scripts/repair_7640_stale_futures_ranks.py --dry-run
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_7640_stale_futures_ranks.py
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_7640_stale_futures_ranks.py --backup --apply --limit 50
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_7640_stale_futures_ranks.py --backup --apply
    heroku run:detached -a bainluck-heavy -- python3 scripts/repair_7640_stale_futures_ranks.py --restore
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

WRITER_APP = "bainluck-heavy"
BAK_TABLE = "bak_7640_stale_ranks"
MANIFEST_TABLE = "bak_7640_repair_manifest"

#: Markets written per transaction. Small enough that a pass interrupted
#: mid-flight leaves a consistent database and a smaller plan next time, and
#: that no single statement holds row locks across a whole poll cycle
#: (gotcha #13's lesson, applied to a 13k-market sweep).
CHUNK_MARKETS = 200

#: The plan measured 13,130 open markets on 2026-09-21 01:05Z, out of 26,968 open
#: markets in total. A plan approaching the whole open population means a clause
#: stopped discriminating — most likely `status = 'open'` or the
#: `IS DISTINCT FROM` comparison — and the right response is a person reading it,
#: not a write.
SANITY_CEILING_MARKETS = 20000

#: Below this, `--apply` refuses. A plan of zero is the steady state AFTER a
#: successful pass, and reporting it as a successful write is gotcha #53:
#: "it returned" is not "it worked".
SANITY_FLOOR_MARKETS = 1


def _sql():
    """The raw statements, built lazily so importing this module needs no app.

    Only the backup/manifest/restore plumbing lives here. The ordering rule does
    not: it is `field_rank_expr()` and `rerank_market_fields_stmt()`, imported.
    """
    return {
        "bak_create": f"""
            CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
                outcome_id integer PRIMARY KEY,
                rank       integer,
                staged_at  timestamptz NOT NULL DEFAULT NOW())
        """,
        # Every leg of every planned market, not just the mismatched ones — the
        # write re-derives the whole field, so the backup covers the whole field.
        "bak_copy": f"""
            INSERT INTO {BAK_TABLE} (outcome_id, rank)
            SELECT o.id, o.rank
              FROM futures_outcomes o
             WHERE o.market_id = ANY(CAST(:mids AS int[]))
               AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = o.id)
        """,
        "bak_missing": f"""
            SELECT count(*) FROM futures_outcomes o
             WHERE o.market_id = ANY(CAST(:mids AS int[]))
               AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = o.id)
        """,
        # #5595 — PRESENCE BY ID IS NOT COVERAGE. `bak_copy` skips any leg
        # already staged, so a leg banked in an earlier session and CHANGED since
        # reconciles clean by id while the stored value is a false record of what
        # is about to be replaced. The comparison is therefore on the VALUE.
        "bak_stale": f"""
            SELECT count(*) FROM futures_outcomes o
              JOIN {BAK_TABLE} b ON b.outcome_id = o.id
             WHERE o.market_id = ANY(CAST(:mids AS int[]))
               AND b.rank IS DISTINCT FROM o.rank
        """,
        "bak_evict_stale": f"""
            DELETE FROM {BAK_TABLE} b
             USING futures_outcomes o
             WHERE b.outcome_id = o.id
               AND o.market_id = ANY(CAST(:mids AS int[]))
               AND b.rank IS DISTINCT FROM o.rank
        """,
        # Asked BEFORE `bak_missing`, never instead: that statement names the
        # backup table in a subquery and raises UndefinedTable on a database that
        # has never been backed up — which is every database on the documented
        # plan-only first run.
        "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
        "man_create": f"""
            CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} (
                outcome_id        integer PRIMARY KEY,
                wrote_rank        integer,
                seen_last_updated timestamptz,
                applied_at        timestamptz NOT NULL)
        """,
        "man_record": f"""
            INSERT INTO {MANIFEST_TABLE}
                   (outcome_id, wrote_rank, seen_last_updated, applied_at)
            VALUES (:outcome_id, :wrote_rank, :seen_last_updated, :applied_at)
            ON CONFLICT (outcome_id) DO UPDATE
               SET wrote_rank        = EXCLUDED.wrote_rank,
                   seen_last_updated = EXCLUDED.seen_last_updated,
                   applied_at        = EXCLUDED.applied_at
        """,
        # THE ROLLBACK (D51(b)), kept here rather than only in the docstring so
        # the guard test executes the statement a person will actually paste.
        # The two IS NOT DISTINCT FROM clauses are the undo binding itself to
        # what was written; see the module docstring for what happens without
        # them.
        "restore": f"""
            UPDATE futures_outcomes o
               SET rank = b.rank
              FROM {BAK_TABLE} b
              JOIN {MANIFEST_TABLE} m ON m.outcome_id = b.outcome_id
             WHERE b.outcome_id = o.id
               AND o.rank         IS NOT DISTINCT FROM m.wrote_rank
               AND o.last_updated IS NOT DISTINCT FROM m.seen_last_updated
            RETURNING o.id
        """,
        # The write-time re-read of #6325's exemption. A market that settled
        # between the plan and this chunk is dropped, not renumbered.
        "still_open": """
            SELECT id FROM futures_markets
             WHERE id = ANY(CAST(:mids AS int[])) AND status = 'open'
        """,
    }


SQL = _sql()


def wrong_app_refusal(args) -> Optional[str]:
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere — locally, on either app. A write
    must be the attended invocation standing notice 47(c) describes, and the only
    thing that distinguishes an attended `heroku run:detached` from a laptop
    holding production credentials is which dyno it is on.

    `HEROKU_APP_NAME` is populated by the `runtime-dyno-metadata` lab, enabled on
    both `bainluck` and `bainluck-heavy`. Unset means not a dyno at all, which is
    precisely the case this gate exists to stop, so it refuses too rather than
    falling through.
    """
    if not (args.apply or args.backup or args.restore):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == WRITER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{WRITER_APP}'. This script "
        f"creates its backup tables at runtime and rewrites a served column on "
        f"~13,000 markets, so the invocation IS the attended step (standing "
        f"notice 47(c)) and it happens on one named app — the one "
        f"`refresh_stale_futures_prices` runs on. Re-run with `heroku "
        f"run:detached -a {WRITER_APP} -- python3 scripts/"
        f"{os.path.basename(__file__)} ...` (no `backend/` prefix — the dyno's "
        f"root IS this repo's `backend/`)."
    )


def plan_select():
    """Open markets carrying at least one leg whose stored rank is not the field's.

    Built from `field_rank_expr()` so the question this asks is the same question
    the forward write answers. Grouped to the market because the market is the
    unit of both the write and the backup.
    """
    from sqlalchemy import case, func, select

    from app.models.models import FuturesMarket, FuturesOutcome
    from app.utils.futures_rank import field_rank_expr

    field = (
        select(
            FuturesOutcome.market_id.label("market_id"),
            FuturesOutcome.rank.label("stored"),
            field_rank_expr().label("derived"),
        )
        .join(FuturesMarket, FuturesMarket.id == FuturesOutcome.market_id)
        .where(FuturesMarket.status == "open")
        .subquery("field")
    )

    # Left unlabelled on purpose and spelled out at each use: PostgreSQL accepts
    # an output column name in ORDER BY but NOT in HAVING, and a label reused
    # there renders a statement that only fails on a real server.
    bad = func.sum(
        case((field.c.stored.is_distinct_from(field.c.derived), 1), else_=0)
    )

    return (
        select(
            field.c.market_id,
            func.count().label("legs"),
            bad.label("bad_legs"),
            FuturesMarket.name.label("market_name"),
            FuturesMarket.source.label("source"),
            FuturesMarket.market_tier.label("market_tier"),
            FuturesMarket.volume.label("volume"),
        )
        .join(FuturesMarket, FuturesMarket.id == field.c.market_id)
        .group_by(
            field.c.market_id,
            FuturesMarket.name,
            FuturesMarket.source,
            FuturesMarket.market_tier,
            FuturesMarket.volume,
        )
        .having(bad > 0)
        .order_by(bad.desc(), field.c.market_id)
    )


async def plan(session, limit: int):
    rows = (await session.execute(plan_select())).mappings().all()
    return list(rows[:limit]) if limit else list(rows)


async def backup(session, market_ids) -> int:
    """Stage every leg of every planned market; return how many were RE-staged."""
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    refreshed = int(
        (
            await session.execute(text(SQL["bak_stale"]), {"mids": market_ids})
        ).scalar_one()
    )
    if refreshed:
        await session.execute(text(SQL["bak_evict_stale"]), {"mids": market_ids})
    await session.execute(text(SQL["bak_copy"]), {"mids": market_ids})
    await session.commit()
    return refreshed


async def reconcile_backup(session, market_ids) -> dict:
    from sqlalchemy import text

    if not bool((await session.execute(text(SQL["bak_exists"]))).scalar_one()):
        return {"table": "absent"}
    return {
        "missing": int(
            (
                await session.execute(text(SQL["bak_missing"]), {"mids": market_ids})
            ).scalar_one()
        ),
        "stale": int(
            (
                await session.execute(text(SQL["bak_stale"]), {"mids": market_ids})
            ).scalar_one()
        ),
    }


def backup_is_exact(recon: dict) -> bool:
    """An empty or absent reconciliation is NOT exact (gotcha #53)."""
    return recon.get("missing") == 0 and recon.get("stale") == 0


async def still_open(session, market_ids):
    """#6325's exemption, re-read at write time rather than trusted from the plan."""
    from sqlalchemy import text

    rows = (
        await session.execute(text(SQL["still_open"]), {"mids": list(market_ids)})
    ).scalars()
    open_ids = set(int(i) for i in rows)
    return [m for m in market_ids if m in open_ids]


async def apply_chunk(session, market_ids, applied_at):
    """Re-derive one chunk with #6598's statement; bank what it actually wrote."""
    from sqlalchemy import text

    from app.models.models import FuturesOutcome
    from app.utils.futures_rank import rerank_market_fields_stmt

    stmt = rerank_market_fields_stmt(market_ids).returning(
        FuturesOutcome.id, FuturesOutcome.rank, FuturesOutcome.last_updated
    )
    written = (await session.execute(stmt)).all()

    # The manifest is banked AFTER the compare-and-swap, from the rows the write
    # actually returned — never from the plan. An undo binds to what was written.
    for outcome_id, wrote_rank, seen_last_updated in written:
        await session.execute(
            text(SQL["man_record"]),
            {
                "outcome_id": int(outcome_id),
                "wrote_rank": None if wrote_rank is None else int(wrote_rank),
                "seen_last_updated": seen_last_updated,
                "applied_at": applied_at,
            },
        )
    return len(written)


async def restore(session) -> int:
    from sqlalchemy import text

    rows = (await session.execute(text(SQL["restore"]))).fetchall()
    await session.commit()
    return len(rows)


def describe(rows, top: int = 15) -> str:
    lines = []
    for r in rows[:top]:
        lines.append(
            f"  market {r['market_id']:<10} tier {str(r['market_tier'] or '-'):<3} "
            f"vol {str(r['volume'] or 0):>9}  {r['bad_legs']:>4}/{r['legs']:<4} legs  "
            f"{str(r['market_name'])[:44]}"
        )
    if len(rows) > top:
        lines.append(f"  ... and {len(rows) - top:,} more markets")
    return "\n".join(lines)


async def run(args):
    # `async_session_maker` is the name this module exports and the one every
    # other script in this directory imports; #5869's first production
    # invocation died on a guessed `AsyncSessionLocal`, which no unit test that
    # stubs the session could have caught.
    from app.services.database import async_session_maker

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with async_session_maker() as s:
        if args.restore:
            reverted = await restore(s)
            print(
                f"#7640 restore: reverted {reverted} legs to their pre-repair rank.\n"
                "Legs a poller has rewritten since the repair were SPARED — the "
                "undo binds to what was written, and a spared row is the good case."
            )
            return 0

        rows = await plan(s, args.limit)
        mids = [int(r["market_id"]) for r in rows]
        bad_legs = sum(int(r["bad_legs"]) for r in rows)

        print(
            f"#7640 plan: {len(rows):,} open markets carrying {bad_legs:,} legs "
            "whose stored rank is not the field's\n"
        )
        print(describe(rows))

        if len(rows) > SANITY_CEILING_MARKETS:
            print(
                f"\nREFUSING: {len(rows):,} markets is past the ceiling of "
                f"{SANITY_CEILING_MARKETS:,}. The plan measured 13,130 of 26,968 "
                "open markets on 2026-09-21; a plan this size means a clause "
                "stopped discriminating. Read it before writing anything."
            )
            return 2

        if not args.backup and not args.apply:
            print("\nplan only — re-run with --backup, then --backup --apply.")
            return 0

        if args.backup:
            refreshed = await backup(s, mids)
            print(f"\nbacked up every leg of {len(mids):,} markets into {BAK_TABLE}")
            if refreshed:
                print(
                    f"  re-staged {refreshed:,} backup rows that had drifted since "
                    "an earlier pass (#5595) — restoring them would have written "
                    "a stale value"
                )

        recon = await reconcile_backup(s, mids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned leg.")
            return 2

        if not args.apply:
            print("\nbackup staged — re-run with --backup --apply to write.")
            return 0

        if len(rows) < SANITY_FLOOR_MARKETS:
            print(
                "REFUSING --apply: the plan is empty. Nothing was written, and "
                "that is a result to read, not a success to report."
            )
            return 2

        from sqlalchemy import text

        await s.execute(text(SQL["man_create"]))
        await s.commit()

        applied_at = datetime.now(timezone.utc)
        written = 0
        settled_mid_flight = 0
        for start in range(0, len(mids), CHUNK_MARKETS):
            chunk = mids[start : start + CHUNK_MARKETS]
            writable = await still_open(s, chunk)
            settled_mid_flight += len(chunk) - len(writable)
            if writable:
                written += await apply_chunk(s, writable, applied_at)
            await s.commit()
            print(
                f"  chunk {start // CHUNK_MARKETS + 1}: "
                f"{start + len(chunk):,}/{len(mids):,} markets, {written:,} legs rewritten"
            )

        print(
            f"\nrewrote {written:,} legs across {len(mids) - settled_mid_flight:,} markets"
        )
        if settled_mid_flight:
            print(
                f"  dropped {settled_mid_flight:,} markets that settled between the "
                "plan and the write — #6325 says a finished field keeps its ranks, "
                "and a drop is the good case"
            )
        print(f"  undo: python3 scripts/{os.path.basename(__file__)} --restore")
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="bank every leg of every planned market's current rank")
    p.add_argument("--apply", action="store_true",
                   help="re-derive the field (requires an exact backup)")
    p.add_argument("--restore", action="store_true",
                   help="D51(b) undo: revert legs no writer has touched since")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan to N markets, for a staged first run")
    p.add_argument("--dry-run", action="store_true",
                   help="alias for the default plan-only mode; writes nothing")
    args = p.parse_args()
    if args.dry_run:
        args.backup = args.apply = args.restore = False
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
