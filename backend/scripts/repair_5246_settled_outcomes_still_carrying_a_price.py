"""#5246 — zero the price on outcomes the venue has already settled.

WHAT A READER SEES TODAY. `https://bainluck.com/events/15309206` on US Open
men's **semifinal day**, three hours before first serve. The `MORE TENNIS` rail:

    US Open Men's Singles Winner
      Alexander Zverev   34%      <- Kalshi says 49.5%
      Ben Shelton        25%
      Frances Tiafoe      6%
      +45 more
    US Open Women's Singles Winner
      Aryna Sabalenka    45%      <- Kalshi says 57.5%
      Elena Rybakina     33%
      Iga Swiatek         2%      <- out of the tournament

Four men are alive and the card offers 48 names. Iga Swiatek renders as the
third most likely winner of a tournament she is not in. Every live number is
**out by up to 15 points**, on a marquee page, while the site's own hero one
screen above says Zverev is 80% to win this match.

THE NUMBERS ARE WRONG, NOT JUST THE ROSTER, AND THAT IS THE WHOLE POINT. The
survivors' stored probabilities are EXACTLY right. Measured on production
2026-09-11 ~17:2xZ, market 34277822:

    the four semifinalists   0.495 + 0.375 + 0.085 + 0.055 = 1.0100
    all 48 outcomes                                        = 1.4800
    Zverev as rendered            0.495 / 1.4800           =   33.4%
    Zverev after this repair      0.495 / 1.0100           =   49.0%   (venue 49.5%)

The rail renormalises over the column (gotcha #23 — independent binaries can sum
well past 100%), which is SOUND on a live field and unsound the moment most of
the field is dead: the 44 stale rows silently tax every live one. The women's
market is the same shape, 1.2900 -> 1.0300.

WHERE THE RESIDUE COMES FROM, AND WHY NOTHING WILL EVER CLEAR IT. The grade
landed and the price did not. All 44 eliminated men already carry
`is_winner = false, resolution_source = 'api_settlement'` — Kalshi's own
settlement feed graded them correctly, days ago. What the settling statement in
`backfill_winners` never wrote was the PRICE, so each row kept the last number
anyone paid for it. It cannot recover on its own:

  * Measured against the venue 2026-09-11 17:2xZ,
    `GET /events/KXATP-26USO?with_nested_markets=true` returns all 48 markets and
    every `finalized` one carries `yes_bid: null, yes_ask: null, last_price:
    null`. `_kalshi_yes_probability(None, None, None)` is None and every
    price-writing site skips a None.
  * `futures_price_refresh` additionally refuses anything outside `0 < prob < 1`
    — which a settled 0.0 or 1.0 is, by construction.

So a settled leg's price is not stale, it is **unreachable**: no poll will quote
it again, and no poll may write either of the two values it can now legally
hold. That is also why THIS SCRIPT DOES NOT HAVE TO WAIT FOR ITS PRODUCER FIX TO
DEPLOY, which is the opposite of #5221's rule and is worth saying out loud. The
beat cannot re-write what this clears, because the venue hands it nothing to
write; and the producer fix's own `WHERE` only ever touches rows whose
`resolution_source` is NULL or overwritable, which an `api_settlement` row is
not. The two halves are independent, and the data half is what a reader sees.

THE COHORT, re-measured on production 2026-09-11 ~17:2xZ by this script's own
filter. Only markets still `status='open'` are in scope — the 963,492 `resolved`
markets are not rendered as live winner cards, and a repair's blast radius
should stop where the defect stops:

    partition                                    rows    markets
    CLEAR   (a live field survives)              7,127     1,188
    REFUSE  (zeroing would blank the card)       4,613     1,139
    -------------------------------------------------------------
    candidates                                  11,740     2,327

    top of the CLEAR side, by category/source (candidate counts):
      entertainment kalshi 3,164 | politics kalshi 2,299 | football kalshi 1,372
      economics kalshi 1,044 | basketball kalshi 825 | soccer polymarket 818
      baseball kalshi 496 | soccer kalshi 268 | tennis kalshi 217

2,722 probability points of residue sit on open markets. That is the tax, and it
is levied on every live outcome on every one of those cards.

THE REFUSAL, WHICH IS THE SAFETY ARGUMENT. A candidate is cleared only if its
MARKET still has at least one priced outcome that is not itself a settled loser
— the same shape as `futures_price_refresh._KALSHI_FROZEN_CERTAIN_SQL`'s
crowned-sibling clause, and for the same reason: the decisive question is about
the row's SIBLINGS, not the row. Where every priced leg has been graded a loser,
zeroing them all replaces a wrong card with an all-zero card, and an open market
whose entire field is eliminated is a different defect (its market status is
wrong) that this repair must not paper over. It refuses **4,613 of 11,740
candidates across 1,139 markets — 39%** — so the clause is not decoration.

WHAT IS NOT TOUCHED, and each omission is a column with another owner:

  * `is_winner` / `resolution_source` — the grade is already right. This repair
    changes no verdict; it only stops contradicting one.
  * `opening_probability` / `calibration_probability` — the calibration curve's
    inputs (gotcha #144: the curve price is `COALESCE(calibration_probability,
    opening_probability)`). Zeroing a terminal price moves no published point.
  * `futures_odds_snapshots` — the full price history, untouched, so nothing
    that was ever true stops being recoverable.
  * `last_updated` — the PRICE TOUCH clock three surfaces read as "when did
    somebody last look at this number" (LIVE-077 / CERT-1936, and
    `app/routes/playoffs.py` reads it as a liveness gate). This script reads no
    venue price. `price_changed_at` IS stamped, because the stored price really
    does move, which is exactly what that column was added to record (#2024).

RESTORE, one command (D51(b)):

    UPDATE futures_outcomes fo
       SET current_probability   = b.current_probability,
           current_american_odds = b.current_american_odds,
           price_changed_at      = b.price_changed_at
      FROM bak_5246_futures_outcomes b
     WHERE b.id = fo.id
       AND fo.id IN (SELECT outcome_id FROM bak_5246_repair_manifest);

USAGE:

    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py            # plan only
    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py --backup
    python3 scripts/repair_5246_settled_outcomes_still_carrying_a_price.py --backup --apply
"""

import argparse
import asyncio
import collections
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BAK_TABLE = "bak_5246_futures_outcomes"
#: What the repair DID, as opposed to what the rows WERE (the CERT-2439 lesson,
#: inherited via #5221). A full-row backup records where a row CAME FROM and
#: cannot record that this script is what moved it; without the manifest a
#: restore can only ask "does the live row differ from its backup?", which is
#: also true of a row a poll has legitimately re-priced since.
MANIFEST_TABLE = "bak_5246_repair_manifest"

#: The grade that means THE VENUE SAID SO, and the only one in scope.
#:
#: Every other value in `resolution_source` is either an inference the system is
#: allowed to revise (`pass2_guess`, `multi_max_prob`, `binary_higher_wins` and
#: the rest of `OVERWRITABLE_WINNER_SOURCES_SQL`) or a derivation from data that
#: can itself be wrong (`box_score`, `game_score` — see #5221, which existed
#: because one of those was computed off the wrong period). Zeroing a price on
#: the strength of a guess would spend a reader-visible number on a verdict we
#: are not sure of. `api_settlement` is written only from Kalshi's own settled
#: events feed, off a `status: finalized` market carrying an explicit
#: `result` — it is the venue closing the contract, and there is nothing better
#: to wait for.
SETTLED_SOURCE = "api_settlement"

#: The price floor that separates "carries residue" from "already zero".
#:
#: `current_probability` is `Numeric(7, 6)`, and a genuine zero stores as
#: exactly 0.000000, so `> 0` alone would be correct. The floor is half a basis
#: point instead, so that a row already repaired — or one a future producer
#: rounds to 0.000000 by a different route — is not re-planned on every run, and
#: so the count this script reports is the count of rows a reader could actually
#: see a number on.
RESIDUE_FLOOR = 0.0005

#: The sanity floor. 7,127 clearable rows were measured at ~17:2xZ on 2026-09-11.
#: Unlike #5221's population this one does NOT grow while a fix waits to deploy —
#: it grows whenever a round completes anywhere in sport, and it shrinks whenever
#: a market flips `open` -> `resolved` and leaves scope. So the floor is set at
#: ~80% of the measurement and a plan below it needs a DISCRIMINATOR rather than
#: an `--allow-small` override, because "the filter broke" and "the job is done"
#: are two different causes that both present as a small plan.
SANITY_FLOOR = 5700

SQL = {
    # LIKE copies columns and types but NOT the foreign keys — a backup that
    # cascaded with its source would be no backup at all.
    "bak_create": f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} "
                  f"(LIKE futures_outcomes INCLUDING DEFAULTS)",
    "bak_index": f"CREATE UNIQUE INDEX IF NOT EXISTS {BAK_TABLE}_pk "
                 f"ON {BAK_TABLE} (id)",
    "bak_copy": f"INSERT INTO {BAK_TABLE} SELECT s.* FROM futures_outcomes s "
                f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    "bak_missing": f"SELECT count(*) FROM futures_outcomes s "
                   f"WHERE s.id = ANY(CAST(:ids AS int[])) "
                   f"AND NOT EXISTS (SELECT 1 FROM {BAK_TABLE} b WHERE b.id = s.id)",
    # Asked BEFORE `bak_missing`, never instead: that statement names the backup
    # table in a subquery and raises UndefinedTable on a database that has never
    # been backed up — which is every database on the documented plan-only first
    # run. A missing table still yields an empty reconciliation, and
    # `backup_is_exact({})` is False, so `--apply` still refuses (gotcha #53).
    "bak_exists": f"SELECT to_regclass('{BAK_TABLE}') IS NOT NULL",
    "man_exists": f"SELECT to_regclass('{MANIFEST_TABLE}') IS NOT NULL",
    "man_count": f"SELECT count(*) FROM {MANIFEST_TABLE}",
    # THE SCAN. One row per candidate, carrying the two facts the classifier
    # needs: which market it belongs to, and whether that market still has a
    # live priced field to normalise over.
    #
    # `market_id IN (SELECT id FROM futures_markets WHERE status = 'open')`
    # rather than a JOIN: measured on production, the JOIN form of this scan
    # times out at the 10s db-query budget and the IN form returns, because it
    # lets the planner drive from the 51,762 open markets instead of the
    # 3.9M-row outcome table.
    "scan": f"""
        SELECT fo.id            AS outcome_id,
               fo.market_id     AS market_id,
               fo.name          AS outcome_name,
               fo.current_probability AS residue,
               EXISTS (
                   SELECT 1 FROM futures_outcomes live
                    WHERE live.market_id = fo.market_id
                      AND live.current_probability > {RESIDUE_FLOOR}
                      AND NOT (live.is_winner = false
                               AND live.resolution_source = '{SETTLED_SOURCE}')
               )                AS live_field_survives
          FROM futures_outcomes fo
         WHERE fo.market_id IN (SELECT id FROM futures_markets WHERE status = 'open')
           AND fo.is_winner = false
           AND fo.resolution_source = '{SETTLED_SOURCE}'
           AND fo.current_probability > {RESIDUE_FLOOR}
         ORDER BY fo.market_id, fo.id
    """,
    # THE FORWARD WRITE, and it is a compare-and-swap on every column of the
    # premise. If anything re-graded or re-priced the row between the plan and
    # the write — a poll that found the venue quoting again, a grader that
    # changed its mind, the fixed producer arriving first — the statement
    # no-ops instead of overwriting a fresher, better number with a zero.
    #
    # `last_updated` is deliberately NOT stamped; `price_changed_at` is. See the
    # module docstring: one column answers "when did a poll last look at this",
    # which this script is not, and the other answers "when did the stored price
    # last move", which is exactly what is happening.
    "clear": "UPDATE futures_outcomes "
             "SET current_probability = 0, "
             "    current_american_odds = NULL, "
             "    price_changed_at = NOW() "
             "WHERE id = :oid "
             "  AND is_winner = false "
             f"  AND resolution_source = '{SETTLED_SOURCE}' "
             f"  AND current_probability > {RESIDUE_FLOOR}",
    "man_create": f"CREATE TABLE IF NOT EXISTS {MANIFEST_TABLE} ("
                  f"  outcome_id  integer PRIMARY KEY,"
                  f"  market_id   integer NOT NULL,"
                  f"  applied_at  timestamptz NOT NULL DEFAULT NOW())",
    # A row can legitimately be cleared, restored and cleared again, so the
    # later row REPLACES the earlier one; `DO NOTHING` would leave the restore
    # reasoning about a move that is two states stale.
    "man_record": f"INSERT INTO {MANIFEST_TABLE} (outcome_id, market_id, applied_at) "
                  f"VALUES (:oid, :mid, :now) "
                  f"ON CONFLICT (outcome_id) DO UPDATE SET "
                  f"  market_id = EXCLUDED.market_id,"
                  f"  applied_at = EXCLUDED.applied_at",
}


def classify(legs):
    """Split one market's settled-loser legs into (clear, refuse).

    The market is the unit of judgement, not the leg: every candidate on a
    market either clears or is refused together, because the question asked —
    *does a live priced field survive here?* — is a property of the market. A
    per-leg answer would clear the legs of a market one at a time and blank the
    card on the last one.
    """
    survives = bool(legs[0]["live_field_survives"])
    return (legs, []) if survives else ([], legs)


def backup_is_exact(recon) -> bool:
    """The D51 gate: every clearable row has a backup row, and something was checked.

    `all()` over an empty mapping is True, so the emptiness test is not
    decoration — without it a reconciliation that inspected nothing reads as a
    clean pass and `--apply` proceeds with no undo (gotcha #53).
    """
    return bool(recon) and all(n == 0 for n in recon.values())


def explain_small_plan(plan_count: int, manifest_rows: int) -> str:
    """Why is the plan below the floor — a broken filter, or a done job?

    A sanity floor that names two causes needs a DISCRIMINATOR, not an override
    flag: `--allow-small` would let the broken-filter case through wearing the
    completed-run case's clothes. The manifest is the discriminator, because
    only a successful forward write puts a row in it.
    """
    if plan_count >= SANITY_FLOOR:
        return ""
    if manifest_rows + plan_count >= SANITY_FLOOR:
        return (
            f"ALREADY APPLIED — {manifest_rows} rows are in {MANIFEST_TABLE} and "
            f"{plan_count} remain clearable; together they clear the floor of "
            f"{SANITY_FLOOR}. This is a drained backlog, not a broken filter."
        )
    return (
        f"FILTER BROKE — only {plan_count} rows are clearable and "
        f"{manifest_rows} were ever applied, so {plan_count + manifest_rows} of "
        f"an expected {SANITY_FLOOR}+ are accounted for. Either the cohort SQL "
        f"stopped matching or markets left `open` faster than expected. Do NOT "
        f"lower the floor; find the rows."
    )


async def backup(session, outcome_ids):
    from sqlalchemy import text

    await session.execute(text(SQL["bak_create"]))
    await session.execute(text(SQL["bak_index"]))
    await session.execute(text(SQL["bak_copy"]), {"ids": outcome_ids})
    await session.commit()


async def _table_exists(session, key) -> bool:
    from sqlalchemy import text

    return bool((await session.execute(text(SQL[key]))).scalar_one())


async def manifest_count(session) -> int:
    from sqlalchemy import text

    if not await _table_exists(session, "man_exists"):
        return 0
    return int((await session.execute(text(SQL["man_count"]))).scalar_one())


async def reconcile_backup(session, outcome_ids) -> dict:
    from sqlalchemy import text

    if not await _table_exists(session, "bak_exists"):
        return {}
    missing = (
        await session.execute(text(SQL["bak_missing"]), {"ids": outcome_ids})
    ).scalar_one()
    return {"futures_outcomes": int(missing)}


def plan(rows):
    """Group the candidate scan by market and classify each one."""
    by_market = collections.OrderedDict()
    for row in rows:
        leg = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        by_market.setdefault(leg["market_id"], []).append(leg)

    clear, refuse = [], []
    for legs in by_market.values():
        c, r = classify(legs)
        clear.extend(c)
        refuse.extend(r)
    return clear, refuse


async def run(args) -> None:
    from datetime import datetime, timezone

    from sqlalchemy import text

    from app.tasks.base import get_task_session

    async with get_task_session() as s:
        rows = (await s.execute(text(SQL["scan"]))).fetchall()
        clear, refuse = plan(rows)
        if args.limit:
            clear = clear[: args.limit]

        markets_clear = len({leg["market_id"] for leg in clear})
        markets_refuse = len({leg["market_id"] for leg in refuse})
        residue = sum(float(leg["residue"] or 0) for leg in clear)

        print(f"candidates : {len(rows)}")
        print(f"CLEAR      : {len(clear)} rows / {markets_clear} markets "
              f"({residue:.1f} probability points of residue)")
        print(f"REFUSE     : {len(refuse)} rows / {markets_refuse} markets "
              f"(no live priced field would survive)")

        manifest_rows = await manifest_count(s)
        small = explain_small_plan(len(clear), manifest_rows)
        if small:
            print(f"\n⚠️  plan is below the sanity floor of {SANITY_FLOOR}.")
            print(f"   {small}")

        if not args.backup and not args.apply:
            print("\nplan only — pass --backup to stage an undo, then --apply.")
            return

        outcome_ids = [leg["outcome_id"] for leg in clear]
        if not outcome_ids:
            print("\nnothing to do.")
            return

        if args.backup:
            await backup(s, outcome_ids)
            print(f"\nbacked up {len(outcome_ids)} rows into {BAK_TABLE}")

        recon = await reconcile_backup(s, outcome_ids)
        print(f"reconciliation: {recon}")
        if not backup_is_exact(recon):
            print("REFUSING --apply: the backup does not cover every planned row.")
            return

        if not args.apply:
            print("\nbackup staged — re-run with --apply to write.")
            return

        if small:
            print("REFUSING --apply: plan is below the sanity floor (see above).")
            return

        await s.execute(text(SQL["man_create"]))
        now = datetime.now(timezone.utc)
        applied = declined = 0
        for leg in clear:
            r = await s.execute(text(SQL["clear"]), {"oid": leg["outcome_id"]})
            if r.rowcount:
                applied += 1
                await s.execute(
                    text(SQL["man_record"]),
                    {"oid": leg["outcome_id"], "mid": leg["market_id"], "now": now},
                )
            else:
                declined += 1
        await s.commit()
        print(f"\napplied {applied}, declined {declined} "
              f"(a decline means the row moved under us — the good case)")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true",
                   help="copy every planned row into the backup table first")
    p.add_argument("--apply", action="store_true",
                   help="write the zeros (requires an exact backup)")
    p.add_argument("--limit", type=int, default=0,
                   help="cap the plan, for a staged first run")
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
