"""#5869 — retire the futures legs that print `0%` for "we have no price".

SCOPE IN ONE LINE: 436 legs carry the producer's fingerprint; 373 of them sit on
markets the venue is still actively pricing, and those are the ones this writes.
The other 63 are one abandoned market and are explained — and excluded — below.


WHAT A READER SEES TODAY. `https://bainluck.com/futures/1`, MLB World Series
Winner, behind "Show more". Read from the served payload 2026-09-15 ~12:4xZ:

    {"name": "Athletics", "probability": 0.0, "american_odds": 331909,
     "is_winner": false, "resolution_source": null}

`0%`. The site asserting that the Athletics cannot win the World Series, beside a
price that implies 0.03%. On "The Open Winner" (market 6) it is **122 of the 205
outcomes served**; across 8 open markets, 436 legs.

The producer is `_poll_futures_odds`'s stale block (`app/tasks/futures.py`, "zero
out stale outcomes absent from API response"). It observes ONE fact — the outcome
was absent from the venue's response for over a day — and wrote `0`, which says
IMPOSSIBLE. `0` and NULL are different sentences, and only one of them is
something that block knows. The producer now writes NULL (same PR; guarded by
`tests/integration/test_stale_futures_leg_retires_to_null_5869.py`), which stops
the population growing — 5 legs joined it in the 30 days to 2026-09-15 — but
leaves every stored leg frozen exactly as it is, because the block's own guard
(`existing.current_probability and float(...) > 0`) skips a zeroed row forever.
This script is the half a reader can see.

WHY THE RENDER TURNS ON IT. Every serializer `#6081` converted in
`routes/futures.py` is `is not None`-guarded, so the stored value reaches the
client intact, and `probabilityParts`
(`frontend/lib/probabilityDisplay.ts:136`) reaches for the truthful `<1%` marker
only when `prob > 0`. So:

    stored NULL -> `probability: null` -> "-"     (we have no price: true)
    stored 0    -> `probability: 0.0`  -> "0%"    (impossible: unevidenced)

The falsy readers (`if o.current_probability`, `or 0`) — which is most of the
column's 772 read sites — already fold 0 and NULL together and see no change at
all. `routes/teams.py:675` drops both. The serializers that CAN tell them apart
are the point of the repair.

🔴 THE PREDICATE KEYS ON THE PRODUCER'S FINGERPRINT, NEVER ON THE ZERO. There are
919,923 rows storing `current_probability = 0` and most of them are honest —
a settled loser's price really is zero. Convicting on the zero would rewrite a
million graded outcomes. The fingerprint is what THIS block leaves behind, and it
is five columns wide (measured on production 2026-09-15 ~12:5xZ, 436/436):

    current_probability    = 0           the claim being withdrawn
    current_american_odds IS NOT NULL    the block never touches it, and
                                         `probability_to_american()` returns None
                                         for `prob <= 0` (`utils/odds_math.py:352`),
                                         so NO path that writes both columns in one
                                         call can produce this pair. That single
                                         fact excludes every co-writing candidate:
                                         `futures_price_refresh.py`,
                                         `tournament_price_refresh.py`, and this
                                         task's own insert branch.
    resolution_source     IS NULL        a settlement writer stamps it
                                         (`backfill_winners.py` always does)
    price_changed_at      IS NULL        the block does not stamp it;
                                         `repair_5246_*` writes a zero and DOES
                                         stamp it, so this column is what tells
                                         the two repairs apart
    markets.source        = 'odds_api'   the only poll this block runs in

🔴 PLUS ONE CLAUSE THE FINGERPRINT ALONE CANNOT SUPPLY: the venue must still be
pricing the market. The producer never needs this — it only runs inside a
per-sport loop that just received a response, so "absent from THIS answer" is
established by construction. A repair reconstructs that context afterwards and
must earn it, because on a market the venue has ABANDONED, a zeroed leg is
genuinely ambiguous: "we have no price" and "this outcome was eliminated" look
identical, and "-" would be the worse of the two readings.

The discriminator is whether any sibling in the same market carries a live price:

    EXISTS (sibling with current_probability > 0 and last_updated < 7 days old)

Measured on production 2026-09-15 ~13:0xZ it splits the 436 cleanly and with no
borderline case — seven markets whose priced siblings refreshed TODAY keep 373
legs, and exactly one market fails it:

    market 10, FIFA World Cup Winner, whose last priced sibling moved 2026-07-19

and that market deserves the exclusion on its own facts. It is the final —
Spain 58.7% vs Argentina 41.3%, frozen on the day it was played — with 63
eliminated teams at 0%, `status: open`, `settled_at` NULL and NO winner
recorded. Spain won and the page does not say so. Those 63 zeros are true by
accident, the real defect there is that nothing crowned Spain, and replacing
truthful-by-accident zeros with dashes on an ungraded final would delete an
alarm and leave the lie. Routed to settlement, untouched here.

🔴 AND IT DOES NOT DERIVE A PROBABILITY FROM THE SURVIVING ODDS, which is the
tempting repair and the wrong one. On 430 of the 436, the zeroed legs last moved
in May–August while their priced siblings in the same market refreshed today, so
`current_american_odds` there is a months-old relic: turning it into a live price
would store a stale number as a current one on almost the whole population —
plausible, wrong, and indistinguishable from a real repair afterwards. Two legs
that looked like flatly-wrong numbers rather than rendering niceties both
dissolved on inspection (Tiger Woods: `current` and `opening` odds disagree 185×,
an incoherent relic; England: market 10 is the FIFA World Cup, concluded 07-19,
and England's truthful render is "Lost", so 31% would be a NEW lie). Written up
on #1541. "-" is what we actually know, and it is the only thing this writes.

NOT IN SCOPE, deliberately:

  * `is_winner`. All 436 carry `is_winner = false` with `resolution_source
    IS NULL` — an affirmative graded loss nobody called (#4788's class). It is a
    real defect on the same rows and it is a SETTLEMENT question; a price repair
    that also grades outcomes is two repairs wearing one backup. Filed, not fixed
    here.
  * The 8 parent markets, every one of which is `status: open` with zero winners
    recorded — including two concluded golf majors and a concluded World Cup.
    Also settlement, also not this.
  * The `current_american_odds` value itself. It is the last honest thing the
    book said; retiring a price is not erasing the record of it.

RESTORE, one command (D51(b)):

    UPDATE futures_outcomes o
       SET current_probability = b.current_probability
      FROM bak_5869_stale_legs b
     WHERE b.outcome_id = o.id
       AND b.outcome_id IN (SELECT outcome_id FROM bak_5869_repair_manifest);

  The restore is only as honest as the backup, so the backup is reconciled by
  CONTENT, not by id (#5595): `--backup` evicts and re-stages any row that drifted
  since an earlier pass, and the forward UPDATE is a compare-and-swap that
  re-checks the whole fingerprint at write time, so a row that moved after the
  plan was computed is DECLINED rather than written. Every leg this script
  changed has an exact backup, or it was not changed.

RUNTIME DDL, ATTENDED INVOCATION ONLY (standing notice 47(c)). The two
`CREATE TABLE IF NOT EXISTS bak_5869_*` statements run only when a person invokes
`--backup`; nothing here runs on merge or on release, and this is not
migration-class. `--backup`/`--apply` refuse unless `HEROKU_APP_NAME` is
`bainluck` — the app the producing task runs on, since `poll_futures_odds` is not
in `HEAVY_TASKS` — so the write cannot be fired from a laptop pointed at
production with whatever happens to be checked out. A dry run only reads, and
runs anywhere.

USAGE:

    python3 scripts/repair_5869_stale_futures_legs_claiming_impossible.py
    heroku run:detached -a bainluck -- python3 backend/scripts/repair_5869_stale_futures_legs_claiming_impossible.py --backup
    heroku run:detached -a bainluck -- python3 backend/scripts/repair_5869_stale_futures_legs_claiming_impossible.py --backup --apply
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PRODUCER_APP = "bainluck"
BAK_TABLE = "bak_5869_stale_legs"
MANIFEST_TABLE = "bak_5869_repair_manifest"

#: The plan measured 373 on 2026-09-15 (436 carry the fingerprint; 63 sit on a
#: market the venue abandoned) and grows by roughly five a month until the
#: producer fix releases. A plan an order of magnitude bigger means the predicate
#: widened — a new writer, a renamed column, a dropped clause — and the right
#: response to that is a person reading it, not a write.
SANITY_CEILING = 2000

#: Below this, `--apply` still runs: a plan of one is the normal steady state
#: after the first pass. The floor exists only to catch a plan of ZERO being
#: treated as success (gotcha #53 — "it returned" is not "it worked").
SANITY_FLOOR = 1

#: The producer's fingerprint, written once and reused by the plan, the
#: reconciliation and the compare-and-swap, so the three can never disagree about
#: which rows this repair is about.
FINGERPRINT = """
        o.current_probability = 0
    AND o.current_american_odds IS NOT NULL
    AND o.resolution_source IS NULL
    AND o.price_changed_at IS NULL
    AND o.is_winner IS NOT TRUE
    AND m.source = 'odds_api'
    AND EXISTS (SELECT 1
                  FROM futures_outcomes sib
                 WHERE sib.market_id = o.market_id
                   AND sib.current_probability > 0
                   AND sib.last_updated > NOW() - INTERVAL '7 days')
"""

SQL = {
    "plan": f"""
        SELECT o.id                     AS outcome_id,
               o.current_probability    AS prob,
               o.current_american_odds  AS american,
               o.last_updated           AS last_updated,
               o.name                   AS outcome_name,
               m.id                     AS market_id,
               m.name                   AS market_name
          FROM futures_outcomes o
          JOIN futures_markets m ON m.id = o.market_id
         WHERE {FINGERPRINT}
         ORDER BY o.id
    """,
    "bak_create": f"""
        CREATE TABLE IF NOT EXISTS {BAK_TABLE} (
            outcome_id          integer PRIMARY KEY,
            current_probability numeric,
            staged_at           timestamptz NOT NULL DEFAULT NOW())
    """,
    "bak_copy": f"""
        INSERT INTO {BAK_TABLE} (outcome_id, current_probability)
        SELECT o.id, o.current_probability
          FROM futures_outcomes o
         WHERE o.id = ANY(CAST(:ids AS int[]))
           AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = o.id)
    """,
    "bak_missing": f"""
        SELECT count(*) FROM futures_outcomes o
         WHERE o.id = ANY(CAST(:ids AS int[]))
           AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.outcome_id = o.id)
    """,
    # #5595 — PRESENCE BY ID IS NOT COVERAGE. `bak_copy` skips any leg already
    # staged, so a leg banked in an earlier session and CHANGED since reconciles
    # clean by id while the stored value is a false record of what is about to be
    # replaced. The comparison is therefore on the VALUE.
    "bak_stale": f"""
        SELECT count(*) FROM futures_outcomes o
          JOIN {BAK_TABLE} b ON b.outcome_id = o.id
         WHERE o.id = ANY(CAST(:ids AS int[]))
           AND b.current_probability IS DISTINCT FROM o.current_probability
    """,
    "bak_evict_stale": f"""
        DELETE FROM {BAK_TABLE} b
         USING futures_outcomes o
         WHERE b.outcome_id = o.id
           AND o.id = ANY(CAST(:ids AS int[]))
           AND b.current_probability IS DISTINCT FROM o.current_probability
    """,
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run. A missing table yields an empty reconciliation and `--apply` refuses.
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_create": f"""
        CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} (
            outcome_id integer PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT NOW())
    """,
    "man_record": f"""
        INSERT INTO {MANIFEST_TABLE} (outcome_id, applied_at)
        VALUES (:outcome_id, :now)
        ON CONFLICT (outcome_id) DO UPDATE SET applied_at = EXCLUDED.applied_at
    """,
    # THE FORWARD WRITE, and it is a compare-and-swap on the whole fingerprint.
    # Everything the plan asserted is re-checked here, because each clause names
    # something that could have changed in between: a settlement writer could
    # have stamped `resolution_source`, a price refresh could have restored a
    # real probability and odds, the leg could have been crowned. A row that
    # moved is DECLINED, and a decline is the good case.
    "update": f"""
        UPDATE futures_outcomes o
           SET current_probability = NULL
          FROM futures_markets m
         WHERE m.id = o.market_id
           AND o.id = :outcome_id
           AND {FINGERPRINT}
        RETURNING o.id
    """,
}


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
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. This script "
        f"creates its backup tables at runtime and rewrites a served column, so "
        f"the invocation IS the attended step (standing notice 47(c)) and it "
        f"happens on one named app. Re-run with `heroku run:detached -a "
        f"{PRODUCER_APP} -- python3 backend/scripts/{os.path.basename(__file__)} ...`."
    )


async def plan(session, limit: int):
    from sqlalchemy import text

    rows = (await session.execute(text(SQL["plan"]))).mappings().all()
    return list(rows[:limit]) if limit else list(rows)


async def backup(session, ids) -> int:
    """Stage every planned leg's current value; return how many were RE-staged."""
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    refreshed = int(
        (await session.execute(text(SQL["bak_stale"]), {"ids": ids})).scalar_one()
    )
    if refreshed:
        await session.execute(text(SQL["bak_evict_stale"]), {"ids": ids})
    await session.execute(text(SQL["bak_copy"]), {"ids": ids})
    await session.commit()
    return refreshed


async def reconcile_backup(session, ids) -> dict:
    from sqlalchemy import text

    if not bool((await session.execute(text(SQL["bak_exists"]))).scalar_one()):
        return {"table": "absent"}
    return {
        "missing": int(
            (await session.execute(text(SQL["bak_missing"]), {"ids": ids})).scalar_one()
        ),
        "stale": int(
            (await session.execute(text(SQL["bak_stale"]), {"ids": ids})).scalar_one()
        ),
    }


def backup_is_exact(recon: dict) -> bool:
    """An empty or absent reconciliation is NOT exact (gotcha #53)."""
    return recon.get("missing") == 0 and recon.get("stale") == 0


def describe(rows) -> str:
    by_market: dict = {}
    for r in rows:
        key = (r["market_id"], r["market_name"])
        by_market.setdefault(key, []).append(r)
    lines = []
    for (mid, name), legs in sorted(
        by_market.items(), key=lambda kv: -len(kv[1])
    ):
        sample = ", ".join(
            f"{leg['outcome_name']} ({leg['american']:+})" for leg in legs[:3]
        )
        lines.append(f"  market {mid:<8} {str(name)[:34]:<34} {len(legs):>4} legs  {sample}")
    return "\n".join(lines)


async def run(args):
    from app.services.database import AsyncSessionLocal
    from sqlalchemy import text

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with AsyncSessionLocal() as s:
        rows = await plan(s, args.limit)
        ids = [r["outcome_id"] for r in rows]

        print(f"#5869 plan: {len(rows)} legs storing `0%` beside a live quote\n")
        print(describe(rows))

        if len(rows) > SANITY_CEILING:
            print(
                f"\nREFUSING: {len(rows)} legs is past the ceiling of "
                f"{SANITY_CEILING}. The fingerprint measured 436 on 2026-09-15; "
                "a plan this size means a clause stopped discriminating. Read it "
                "before writing anything."
            )
            return 2

        if not args.backup and not args.apply:
            print("\nplan only — re-run with --backup, then --backup --apply.")
            return 0

        if args.backup:
            refreshed = await backup(s, ids)
            print(f"\nbacked up {len(ids)} legs into {BAK_TABLE}")
            if refreshed:
                print(
                    f"  re-staged {refreshed} backup rows that had drifted since "
                    "an earlier pass (#5595) — restoring them would have written "
                    "a stale value"
                )

        recon = await reconcile_backup(s, ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned leg.")
            return 2

        if not args.apply:
            print("\nbackup staged — re-run with --backup --apply to write.")
            return 0

        if len(rows) < SANITY_FLOOR:
            print(
                "REFUSING --apply: the plan is empty. Nothing was written, and "
                "that is a result to read, not a success to report."
            )
            return 2

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = 0
        for outcome_id in ids:
            done = (
                await s.execute(text(SQL["update"]), {"outcome_id": outcome_id})
            ).fetchall()
            if done:
                await s.execute(
                    text(SQL["man_record"]), {"outcome_id": outcome_id, "now": now}
                )
                applied += 1
        await s.commit()
        declined = len(ids) - applied
        print(
            f"\napplied {applied}, declined {declined} "
            "(a decline means the leg moved under us — the good case)"
        )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="bank every planned leg's current_probability")
    p.add_argument("--apply", action="store_true",
                   help="retire the legs to NULL (requires an exact backup)")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    p.add_argument("--dry-run", action="store_true",
                   help="alias for the default plan-only mode; writes nothing")
    args = p.parse_args()
    if args.dry_run:
        args.backup = args.apply = False
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
