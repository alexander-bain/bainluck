"""#6126 — the historical cleanup: retire the 99% openings Kalshi's empty book minted.

THE SHIP: a settled ladder stops telling you an eliminated player opened at 99%.
`https://bainluck.com/futures/34277822` (US Open Men's Singles), production
2026-09-14 — three players who went out early each print **OPEN 99%**:

    Alexander Bublik   OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Cameron Norrie     OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Dino Prizmic       OPEN 99%    opening_captured_at 2026-06-08 18:00:00+00
    Jannik Sinner      OPEN 48%    opening_captured_at 2026-06-09 08:47:04.007243+00

Sinner is the control and he is the whole tell: an honest row carries a real
`opening_source` (`bid_ask_midpoint`) and a poller timestamp with microseconds,
while all three 99% rows share one instant exactly on the hour and carry no
source at all. Bublik's very next stored point is **0.13** — the series refutes
its own first point one hour later.

CAUSE, READ AT THE VENUE (notice 26), NOT INFERRED FROM OUR MIRROR: Kalshi opens
an untraded market at **bid 0.0000 / ask 0.9900**. Both candle reducers read
rule 3 as "trust a lone quote unless it is exactly 1.00", so that default book
was published as a probability.

    PREVENTION SHIPPED FIRST — `aadbe27ab` (PR #6131, CERT-2853 GREEN) makes
    `candle_yes_price` and `normalize_candle` refuse a lone ask above
    `app.utils.kalshi_empty_book.ASK_ONLY_TRUSTED_MAX`. This script is the owed
    DATA REPAIR for the rows written before that landed.

    THE TAP MUST BE OFF BEFORE THIS RUNS — repair_2871's lesson, and this script
    does not take it on trust. `tap_is_off()` pushes the venue's OWN opening
    candle through the deployed reducer and requires `None` back. It is not a
    version string or a map lookup: it is the defect itself, re-enacted in the
    interpreter that is about to write.

    THE TAP IS ON THE MAIN APP, NOT `bainluck-heavy` — re-derived, not assumed.
    `HEAVY_TASKS` has 33 members and the only Kalshi one is
    `app.tasks.poll_kalshi_markets`, which never reads a candle (zero
    candlestick references in `_poll_kalshi_markets`). Every caller of the two
    reducers — `kalshi_cliff`, `_backfill_kalshi_price_history`,
    `_backfill_kalshi_chart_history`, `event_chart_backfill` — is absent from
    `HEAVY_TASKS`, so the code that could re-mint these rows is what is deployed
    to `bainluck`. That is why `PRODUCER_APP` is the main app here and
    `bainluck-heavy` in repair_5621; the answer differs per population and is
    measured each time rather than copied.

------------------------------------------------------------------------------
THE POPULATION, AND WHY A SHARED VALUE IS NOT A FINGERPRINT
------------------------------------------------------------------------------

Measured on production 2026-09-14 11:0xZ, whole population, no sampling.

The obvious predicate — `opening_probability = 0.99 AND opening_source IS NULL`
— is WRONG and is not used here. `opening_source IS NULL` is the majority state
of the table for ordinary historical reasons, and 0.99 is a value honest rows
also carry. The discriminator is the TIMESTAMP'S PRECISION: a candle's
`end_period_ts` lands exactly on the hour, where the poller's `now` carries
microseconds. Splitting the 0.99 Kalshi legs four ways:

    exact hour + no source   4,402 legs / 610 markets   <- this rail
    off-hour   + no source  17,273 legs
    off-hour   + a source    5,135 legs
    exact hour + a source       45 legs

Only the first band is this writer's. But "written by this rail" still is not
"wrong" — a market really can be at 99c on the hour. So NOTHING here is repaired
on the fingerprint alone. Every leg must additionally REFUTE ITSELF, by one of
two independent tests:

  SUM    the leg shares its exact opening instant with another leg of the same
         market, also at exactly 0.99. Two legs at 0.99 is 1.98. Up to 140 legs
         share one instant (138.6). This is the venue default applied field-wide.

  SERIES the leg's own next stored point is either exactly 0.99 (the default
         book persisting, because nobody has traded yet) or below 0.90 (the
         series refuting its first point, as Bublik's 0.99 -> 0.13 does).

How the band splits on the two tests:

    sum + series      2,901      |  sum only (no later point)    754
    sum only           534       |  series only                  126
    ------------------------------------------------------------------
    REPAIRED                                                   4,315
    NEITHER TEST FIRES — REFUSED AND COUNTED, NEVER WRITTEN        87

The 87 are legs with no sibling at that instant whose next point sits in
[0.90, 0.99). Nothing in our own data distinguishes those from a genuine heavy
favourite, so this script withholds a correction and counts it rather than
writing a value it cannot prove. That is the same choice the shipped reducer
makes: an absent number is a gap, a fabricated one is a lie a curve then grades.

SUM IS THE WEAKER TEST AND IS TREATED AS SUCH. Futures outcomes are not always
mutually exclusive (gotcha #23: independent binaries can sum well over 100%), so
`--apply` does not take SUM on faith either — `_EXCLUSIVITY_SQL` checks that the
market's own outcomes sum to roughly one before a SUM-only leg is eligible, and
a leg that fails it falls back to needing SERIES. Legs that satisfy SERIES need
no exclusivity assumption at all.

SCOPED TO 0.99 ON PURPOSE. The reducer refuses any lone ask above 0.50, so in
principle other values were mintable. They are NOT repaired here: the candle
rail stores no book (NULL bid/ask), so for any other value there is no stored
fingerprint separating it from an honest price, and a repair that cannot name
its population does not get to run. 0.99 is the venue's measured default and is
the only value this script claims.

------------------------------------------------------------------------------
WHAT IS WRITTEN
------------------------------------------------------------------------------

Per repaired leg, in this order:

  1. futures_odds_snapshots   DELETE the LEADING RUN of bad-shape rows
  2. futures_outcomes         opening_probability  -> first surviving point
                              opening_captured_at  -> its timestamp
                                                   (both NULL if none survives)

THE LEADING RUN, NOT JUST THE FIRST ROW — this is the correction the measurement
forced. For 1,768 of these legs the next point is ALSO exactly 0.99, because an
untraded market keeps serving the same default book hour after hour. Deleting
only the opening point would leave the curve starting at 99% anyway, one hour
later, and the repair would read as done while the reader saw no change. So the
run is deleted up to the first row that is not this shape, and never past it: a
0.99 appearing LATER in a series is a genuine move to near-certainty and is left
alone.

`opening_source` is deliberately NOT written. It is NULL on these rows because
the rail never set one, and the surviving candle row it is re-derived from has
no source either; inventing one would fabricate provenance. Its value is still
copied into the backup so the undo is exact.

------------------------------------------------------------------------------
REVERSIBILITY (D51(b))
------------------------------------------------------------------------------

`--backup` copies the FULL deleted snapshot rows and the three opening columns
into `backup_6126_snapshots` / `backup_6126_openings`. The undo re-INSERTs the
snapshots and restores the openings:

    heroku run:detached -a bainluck -- \
        python3 scripts/restore_6126_candle_lone_ask_openings.py --apply

Runtime DDL, attended invocation only — `CREATE TABLE IF NOT EXISTS backup_*`
behind `--backup`, run by a person against a named app. Not migration-class
(notice 47(c)): nothing here executes as a consequence of merge or release.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PRODUCER_APP = "bainluck"

#: The venue's own opening book, read 2026-09-14 from
#: `KXWTACHALLENGERMATCH-26SEP14ZELNAJ-NAJ` candlesticks. This is the defect's
#: input, kept verbatim so `tap_is_off` re-enacts it rather than describing it.
#:
#: Kalshi publishes candle prices ONLY in the `*_dollars` spellings and ONLY as
#: strings — the cents keys are absent on this payload. Getting that wrong is
#: not a harmless typo here: a misspelled candle carries no readable price, both
#: reducers correctly answer `None` for want of data, and the tap check passes
#: VACUOUSLY against an unfixed deploy. Hence `TRADED_CONTROL_CANDLE`.
VENUE_DEFAULT_CANDLE = {
    "yes_bid": {"close_dollars": "0.0000"},
    "yes_ask": {"close_dollars": "0.9900"},
}

#: A real 0.99 trade — the population the refusal must NOT take. It also makes
#: `tap_is_off` falsifiable: a reducer stubbed to return `None` for everything
#: would satisfy the refusal while pricing nothing, and this control catches it.
TRADED_CONTROL_CANDLE = {"price": {"close_dollars": "0.9900"}}

#: One row per leg in the fingerprint band, with both refutation tests and the
#: exclusivity check evaluated in SQL so the dry run prints exactly what
#: `--apply` would act on.
_POPULATION_SQL = """
WITH band AS (
    SELECT o.id, o.market_id, o.name,
           o.opening_probability, o.opening_captured_at AS ts, o.opening_source
      FROM futures_outcomes o
      JOIN futures_markets m ON m.id = o.market_id
     WHERE m.source = 'kalshi'
       AND o.opening_probability = 0.99
       AND o.opening_source IS NULL
       AND o.opening_captured_at IS NOT NULL
       AND date_part('minute', o.opening_captured_at) = 0
       AND date_part('second', o.opening_captured_at) = 0
),
grp AS (
    SELECT market_id, ts, count(*) AS n FROM band GROUP BY 1, 2
),
excl AS (
    -- Gotcha #23: a futures market's outcomes are not always mutually
    -- exclusive. A market whose own outcomes sum to roughly one is; that is
    -- what makes "two legs at 0.99" arithmetically impossible rather than
    -- merely surprising.
    SELECT x.market_id, sum(x.current_probability) AS cur_sum
      FROM futures_outcomes x
      JOIN (SELECT DISTINCT market_id FROM band) b ON b.market_id = x.market_id
     GROUP BY 1
)
SELECT b.id,
       b.market_id,
       b.name,
       b.ts,
       b.opening_source,
       (g.n > 1)                                         AS sum_refutes,
       (e.cur_sum BETWEEN 0.85 AND 1.25)                 AS market_exclusive,
       nxt.p                                             AS next_p,
       (nxt.p = 0.99 OR nxt.p < 0.90)                    AS series_refutes
  FROM band b
  JOIN grp  g ON g.market_id = b.market_id AND g.ts = b.ts
  LEFT JOIN excl e ON e.market_id = b.market_id
  LEFT JOIN LATERAL (
        SELECT s.probability AS p
          FROM futures_odds_snapshots s
         WHERE s.outcome_id = b.id
           AND s.captured_at > b.ts
         ORDER BY s.captured_at
         LIMIT 1
  ) nxt ON true
 ORDER BY b.market_id, b.id
"""

#: The bad shape, as stored. The candle rail writes no book at all, which is why
#: `app.utils.kalshi_empty_book.lone_ask_on_empty_book_sql` (which tests
#: `yes_bid`) cannot see these rows — noted in that module too.
_BAD_SHAPE = (
    "bookmaker = 'kalshi' AND probability = 0.99 "
    "AND yes_bid IS NULL AND yes_ask IS NULL "
    "AND date_part('minute', captured_at) = 0 "
    "AND date_part('second', captured_at) = 0"
)

#: The leading run for one leg: every bad-shape row from the opening instant up
#: to (not including) the first row that is not this shape. `cutoff` NULL means
#: the whole series is the default book and the run is all of it.
_LEADING_RUN_SQL = f"""
WITH cutoff AS (
    SELECT min(s.captured_at) AS ts
      FROM futures_odds_snapshots s
     WHERE s.outcome_id = :oid
       AND s.captured_at >= :ts
       AND NOT ({_BAD_SHAPE})
)
SELECT s.id, s.captured_at
  FROM futures_odds_snapshots s, cutoff c
 WHERE s.outcome_id = :oid
   AND s.captured_at >= :ts
   AND ({_BAD_SHAPE})
   AND (c.ts IS NULL OR s.captured_at < c.ts)
 ORDER BY s.captured_at
"""


def tap_is_off():
    """The prevention is deployed *in this interpreter*.

    Not a version string and not a map lookup: the venue's actual opening book
    is pushed through both deployed reducers and both must answer `None`. If
    either still returns 0.99 the fix is not on this dyno, and applying would
    repair rows the next backfill immediately re-mints.

    BOTH HALVES ARE REQUIRED, and the second is the one that makes the first
    mean something. A refusal alone is satisfied by any reducer that prices
    nothing at all — including one broken by an unrelated change, and including
    the vacuous pass a misspelled fixture would produce. So a real 0.99 trade
    must still come back as 0.99 through both.

    Deliberately narrow: this can only answer for the process it runs in.
    `wrong_app_refusal` is what makes that process the right one.
    """
    from app.tasks.event_chart_backfill import normalize_candle
    from app.utils.kalshi_candle_price import candle_yes_price

    refuses_default = (
        candle_yes_price(VENUE_DEFAULT_CANDLE) is None
        and normalize_candle(VENUE_DEFAULT_CANDLE) is None
    )
    still_prices_a_trade = (
        candle_yes_price(TRADED_CONTROL_CANDLE) == 0.99
        and normalize_candle(TRADED_CONTROL_CANDLE) == 0.99
    )
    return refuses_default and still_prices_a_trade


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere. A write must happen on the
    producer's app, because that is the only place where `tap_is_off()` is
    inspecting the code that could re-mint these rows.

    Unset means we are not on a dyno at all — a laptop pointed at the production
    database with whatever happens to be checked out, which is precisely the
    case this gate exists to stop, so it refuses too rather than falling
    through.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. The two "
        "candle reducers are reached only by tasks that are NOT in HEAVY_TASKS "
        f"({', '.join(_REDUCER_CALLERS)}), so the code that can re-mint these "
        f"rows is what is deployed to '{PRODUCER_APP}'. Run from anywhere else "
        "and the tap check above passes against the wrong interpreter while the "
        "real producer keeps writing. Re-run with "
        f"`heroku run:detached -a {PRODUCER_APP}`."
    )


_REDUCER_CALLERS = (
    "kalshi_cliff",
    "_backfill_kalshi_price_history",
    "_backfill_kalshi_chart_history",
    "event_chart_backfill",
)


def classify(row):
    """REPAIR or the reason this leg is refused.

    SERIES needs no assumption about the market. SUM needs the market's
    outcomes to be mutually exclusive, so a SUM-only leg in a market that does
    not sum to roughly one is refused rather than repaired.
    """
    if row.series_refutes:
        return None
    if row.sum_refutes and row.market_exclusive:
        return None
    if row.sum_refutes:
        return "sum-only leg in a market that does not sum to ~1 (gotcha #23)"
    if row.next_p is None:
        return "singleton with no later point — nothing refutes it"
    return f"singleton whose next point is {row.next_p} — consistent with a real favourite"


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    if (args.apply or args.backup) and not tap_is_off():
        print(
            "REFUSING: the deployed reducers still price Kalshi's untraded "
            "bid-0.00/ask-0.99 book at 0.99. aadbe27ab (PR #6131) is not on "
            "this dyno, so any repair would be re-minted by the next backfill. "
            "Deploy it, then re-run."
        )
        return 2

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
        return 2

    async with get_task_session() as s:
        rows = (await s.execute(text(_POPULATION_SQL))).fetchall()

        repair, refused = [], []
        for r in rows:
            why = classify(r)
            (refused if why else repair).append((r, why))

        print(f"\n=== population === (band {len(rows)} legs)")
        print(f"  repair : {len(repair)}")
        print(f"  refused: {len(refused)}")
        by_reason = {}
        for _, why in refused:
            by_reason[why] = by_reason.get(why, 0) + 1
        for why, n in sorted(by_reason.items(), key=lambda kv: -kv[1]):
            print(f"      {n:5d}  {why}")

        # The leading run per repaired leg, and the point that will become the
        # new opening. Read for every mode, including the dry run, so the
        # attended operator sees the real write plan before authorising it.
        plan = []
        for r, _ in repair:
            run_rows = (
                await s.execute(text(_LEADING_RUN_SQL), {"oid": r.id, "ts": r.ts})
            ).fetchall()
            plan.append((r, [x.id for x in run_rows]))

        deleted_total = sum(len(ids) for _, ids in plan)
        print(f"\n=== snapshot rows in the leading runs === {deleted_total}")
        multi = sum(1 for _, ids in plan if len(ids) > 1)
        print(f"  legs whose default book persisted past the opening: {multi}")

        if args.limit:
            plan = plan[: args.limit]
            print(f"  (--limit {args.limit}: acting on {len(plan)} legs)")

        print("\n=== sample ===")
        for r, ids in plan[:8]:
            print(
                f"  {r.id:>10}  {r.name[:34]:<34} {str(r.ts)[:19]}  "
                f"run={len(ids):<3} next={r.next_p}"
            )

        if not (args.backup or args.apply):
            print("\ndry run — nothing written")
            return 0

        outcome_ids = [r.id for r, _ in plan]
        snap_ids = [i for _, ids in plan for i in ids]

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_6126_snapshots "
                    "(id bigint PRIMARY KEY, outcome_id bigint, bookmaker text, "
                    "probability numeric, american_odds integer, yes_bid numeric, "
                    "yes_ask numeric, last_price numeric, captured_at timestamptz, "
                    "reading_count integer, valid_until timestamptz)"
                )
            )
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_6126_openings "
                    "(id bigint PRIMARY KEY, opening_probability numeric, "
                    "opening_captured_at timestamptz, opening_source text)"
                )
            )
            await s.execute(
                text(
                    # DO UPDATE, not DO NOTHING: a second --backup after an
                    # unrelated writer moved a row must REFRESH it, or the undo
                    # restores a value that was never the one we overwrote.
                    "INSERT INTO backup_6126_snapshots SELECT id, outcome_id, "
                    "bookmaker, probability, american_odds, yes_bid, yes_ask, "
                    "last_price, captured_at, reading_count, valid_until "
                    "FROM futures_odds_snapshots WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "probability = EXCLUDED.probability, "
                    "captured_at = EXCLUDED.captured_at"
                ),
                {"ids": snap_ids},
            )
            await s.execute(
                text(
                    "INSERT INTO backup_6126_openings "
                    "SELECT id, opening_probability, opening_captured_at, "
                    "opening_source FROM futures_outcomes WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "opening_probability = EXCLUDED.opening_probability, "
                    "opening_captured_at = EXCLUDED.opening_captured_at, "
                    "opening_source = EXCLUDED.opening_source"
                ),
                {"ids": outcome_ids},
            )
            await s.commit()
            print(
                f"  copied {len(snap_ids)} snapshot rows + "
                f"{len(outcome_ids)} openings"
            )

        if args.apply:
            covered = (
                await s.execute(
                    text(
                        "SELECT count(*) FROM backup_6126_openings "
                        "WHERE id = ANY(:ids)"
                    ),
                    {"ids": outcome_ids},
                )
            ).scalar()
            if covered != len(outcome_ids):
                print(
                    f"REFUSING to apply: backup covers {covered} of "
                    f"{len(outcome_ids)} openings. Run --backup first."
                )
                return 2

            print("\n=== apply ===")
            await s.execute(
                text("DELETE FROM futures_odds_snapshots WHERE id = ANY(:ids)"),
                {"ids": snap_ids},
            )
            # Re-derive AFTER the delete, so "earliest surviving" means what it
            # says. NULL when nothing survives: the leg's whole stored series
            # was the venue's default book, and an absent opening is the honest
            # answer — the same one the shipped reducer now gives.
            await s.execute(
                text(
                    "UPDATE futures_outcomes o SET "
                    "opening_probability = nxt.p, opening_captured_at = nxt.ts "
                    "FROM (SELECT o2.id, f.probability AS p, f.captured_at AS ts "
                    "        FROM futures_outcomes o2 "
                    "        LEFT JOIN LATERAL ("
                    "             SELECT s.probability, s.captured_at "
                    "               FROM futures_odds_snapshots s "
                    "              WHERE s.outcome_id = o2.id "
                    "              ORDER BY s.captured_at LIMIT 1) f ON true "
                    "       WHERE o2.id = ANY(:ids)) nxt "
                    "WHERE o.id = nxt.id"
                ),
                {"ids": outcome_ids},
            )
            await s.commit()
            print(
                f"  deleted {len(snap_ids)} snapshot rows; "
                f"re-derived {len(outcome_ids)} openings"
            )

    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="read only (default)")
    p.add_argument("--backup", action="store_true", help="copy in-scope rows")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    p.add_argument("--limit", type=int, default=0, help="act on the first N legs")
    args = p.parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
