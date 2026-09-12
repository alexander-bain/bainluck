"""#5621 — the historical cleanup: retire the games an NFL prop minted as basketball.

THE SHIP: searching your club stops returning the game twice, the second time
as basketball. `https://bainluck.com/search?q=Jacksonville`, production Sat
2026-09-12 13:55Z, the day before NFL Week 1 Sunday — two ADJACENT cards:

    NFL               Tomorrow 10:00 AM   Jaguars 79% / Browns 21%  Proj 24-16
    OTHER BASKETBALL  Tomorrow  1:00 PM   Cleveland / Jacksonville  No price yet

The second is a row this series minted: teams reversed, kickoff three hours
out, no price, initial avatars where the badges belong. Same for "Houston" and
"Cincinnati". (`/api/leagues/basketball_other` carries them too, but
`/sport/basketball/other` renders "League 'other' not found" — the basketball
hierarchy lists only nba/wnba/ncaab/wncaab, so that endpoint has no reader
route and is NOT the reach.)

PREVENTION SHIPS FIRST — PR #5624 maps `kxnflffpts` into
`KALSHI_TICKER_TO_SPORT_KEY`, so step 1 of `_categorize_kalshi_market` answers
"football" and `LLM_CATEGORIES_THAT_MAY_NOT_CREATE_EVENTS` then refuses the
fixture outright. This script is the owed DATA REPAIR for the sixteen rows
written before that landed.

    THE TAP MUST BE OFF BEFORE THIS RUNS — repair_2871's lesson, and this
    script does not take it on trust. `--apply` imports the ticker map and
    REFUSES if `kxnflffpts` is missing from it, so the repair cannot physically
    run against a deploy that would just mint the rows back.

------------------------------------------------------------------------------
WHY THIS IS NOT `DELETE FROM events WHERE id IN (...)`
------------------------------------------------------------------------------

`events` has 11 FK children and two of them are NO ACTION (repair_2871
measured it). Nothing here needs a delete: a retired row is already invisible
everywhere. `app/utils/event_rails.py` says so in its own header — ``merged``
and ``voided`` mean "stop showing this row", and every rail is an ALLOWLIST, so
a retired row is excluded BY CONSTRUCTION rather than by a rule somebody has to
remember. One column, fully reversible, no child touched.

------------------------------------------------------------------------------
WHY RETIRING LOSES NO GAME — the safety proof, measured, 16 of 16
------------------------------------------------------------------------------

This is the question repair_2871 got the opposite answer to (68% of ITS rows
were the only record of their fixture, which is why it merges instead of
deleting). Measured here on 2026-09-12 over the FULL population, no sampling:

    phantoms: 16   with a real anchored counterpart: 16   without: 0

Every phantom pairs with an `americanfootball_nfl` row carrying an `espn_id`,
matched on both team names in EITHER orientation within ±36h — e.g.

    15305032  "Houston @ Buffalo"      -> 14780141  Buffalo Bills @ Houston Texans
              2026-09-13 00:00Z  (Kalshi close)     2026-09-13 17:00Z  espn=401872660

The orientation is reversed on all 16 and the time is the Kalshi close, not
kickoff (gotcha #14) — which is exactly why `fold_twin_events` could never have
folded them: its key is `(sport, away, home, commence MINUTE)` and three of
those four differ. A serve-time fold was never available for this population.

`--apply` re-runs that pairing as a GATE, not as documentation: any phantom
without a counterpart aborts the run rather than being retired.

------------------------------------------------------------------------------
WHAT IS WRITTEN
------------------------------------------------------------------------------

Per phantom event (1 column):
    events.status                        -> 'voided'

Per attached market (3 columns):
    futures_markets.llm_sport_category   -> 'football'
    futures_markets.sport_id             -> the americanfootball_nfl sport row
    futures_markets.event_id             -> NULL

The `event_id` clear is the half that turns hiding into fixing. Gotcha #15 says
a matcher must never re-time-window an already-linked market — trust the
`event_id`. So while the wrong link exists the prop can never reach the real
game, no matter how good the matcher gets. Cleared, and with the ticker now
mapped game-level, Pass 1 links it to the real Week 1 fixture on the next run,
and the football refusal means it cannot invent a replacement if it fails.

The category is set explicitly rather than left to the poller because
`tasks/kalshi.py` writes it as
`coalesce(nullif(llm_sport_category,'other'), new)` — a REAL tag is never
overwritten (#1888 honest-empty), and 'basketball' is a real tag. Without this
line the map fix corrects future rows only and these sixteen stay basketball
forever. That asymmetry is the whole reason this script exists.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES until `--backup` has copied every in-scope row into
`backup_5621_events` / `backup_5621_markets` and the reconciliation is exact.

    python3 scripts/restore_5621_phantom_ffpts_events.py --apply

USAGE

    python3 scripts/repair_5621_phantom_ffpts_events.py              # dry run
    python3 scripts/repair_5621_phantom_ffpts_events.py --backup
    python3 scripts/repair_5621_phantom_ffpts_events.py --apply

    heroku run:detached -a bainluck \
        "python3 scripts/repair_5621_phantom_ffpts_events.py --backup"

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The tap's own vocabulary, imported rather than restated. If this prefix is
# absent the prevention is not deployed and the repair must not run.
from app.utils.sport_keys import KALSHI_TICKER_TO_SPORT_KEY  # noqa: E402

TICKER_PREFIX = "kxnflffpts"
TARGET_SPORT_KEY = "americanfootball_nfl"
TARGET_CATEGORY = "football"

#: Sanity ceiling, not a floor. gotcha #53 — an empty result is a response
#: shape, not an absence — but the inverse matters more for a WRITER: this
#: predicate should never match a large population, and if it suddenly does,
#: something upstream changed and a human should look before 200 rows are
#: retired. Measured population 2026-09-12 was exactly 16.
MAX_EXPECTED_POPULATION = 60

#: Every phantom, with its best real counterpart in either orientation. The
#: LATERAL is the safety gate: a NULL `real_id` aborts the apply.
_POPULATION_SQL = """
WITH ph AS (
    SELECT e.id,
           e.status,
           e.commence_time,
           e.home_team_name AS h,
           e.away_team_name AS a,
           s.key            AS sport_key,
           f.id             AS market_id,
           f.external_id    AS ticker,
           f.llm_sport_category
      FROM events e
      JOIN sports s          ON s.id = e.sport_id
      JOIN futures_markets f ON f.event_id = e.id
     WHERE f.source = 'kalshi'
       AND lower(f.external_id) LIKE :prefix || '%'
)
SELECT ph.*, r.id AS real_id, r.espn_id, r.commence_time AS real_ct
  FROM ph
  LEFT JOIN LATERAL (
        SELECT e2.id, e2.espn_id, e2.commence_time
          FROM events e2
          JOIN sports s2 ON s2.id = e2.sport_id
         WHERE s2.key = :target_sport
           AND e2.espn_id IS NOT NULL
           AND (
                 (lower(e2.home_team_name) LIKE lower(ph.a) || '%'
                  AND lower(e2.away_team_name) LIKE lower(ph.h) || '%')
              OR (lower(e2.home_team_name) LIKE lower(ph.h) || '%'
                  AND lower(e2.away_team_name) LIKE lower(ph.a) || '%')
               )
           AND e2.commence_time BETWEEN ph.commence_time - interval '36 hours'
                                    AND ph.commence_time + interval '36 hours'
         ORDER BY abs(extract(epoch FROM (e2.commence_time - ph.commence_time)))
         LIMIT 1
  ) r ON true
 ORDER BY ph.commence_time
"""


def tap_is_off():
    """The prevention is deployed: the prefix resolves to American football."""
    return KALSHI_TICKER_TO_SPORT_KEY.get(TICKER_PREFIX, "").startswith(
        "americanfootball"
    )


async def run(args):
    from sqlalchemy import text

    from app.tasks.base import get_task_session

    if not tap_is_off():
        print(
            f"REFUSING: '{TICKER_PREFIX}' is not in KALSHI_TICKER_TO_SPORT_KEY on "
            "this deploy, so the prevention (PR #5624) is not live and every row "
            "retired here would be minted again on the next Kalshi poll. Land the "
            "map fix first."
        )
        return 2

    async with get_task_session() as s:
        rows = (
            await s.execute(
                text(_POPULATION_SQL),
                {"prefix": TICKER_PREFIX, "target_sport": TARGET_SPORT_KEY},
            )
        ).all()

        print(f"=== #5621 phantom {TICKER_PREFIX} events — population ===")
        if not rows:
            print("Nothing to repair — population is 0 (idempotent no-op).")
            return 0

        orphans = [r for r in rows if r.real_id is None]
        for r in rows:
            pair = (
                f"-> {r.real_id} espn={r.espn_id} {str(r.real_ct)[:16]}"
                if r.real_id
                else "-> *** NO COUNTERPART ***"
            )
            print(
                f"  {r.id:>9} {str(r.status)[:9]:<9} {str(r.sport_key):<18} "
                f"{str(r.a)[:13]:<13}@{str(r.h)[:13]:<13} {pair}"
            )
        print(f"  events={len(rows)}  orphans={len(orphans)}")

        if len(rows) > MAX_EXPECTED_POPULATION:
            print(
                f"\nREFUSING: {len(rows)} rows exceeds MAX_EXPECTED_POPULATION="
                f"{MAX_EXPECTED_POPULATION}. The predicate matched far more than "
                "the measured population; look before writing."
            )
            return 2

        if orphans:
            print(
                f"\nREFUSING: {len(orphans)} phantom(s) have no anchored NFL "
                "counterpart. Retiring those would remove the only record of a "
                "fixture — the repair_2871 failure mode. Investigate them first."
            )
            return 2

        event_ids = [r.id for r in rows]
        market_ids = [r.market_id for r in rows]

        if args.backup:
            print("\n=== backup ===")
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_5621_events "
                    "(id bigint PRIMARY KEY, status text)"
                )
            )
            await s.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS backup_5621_markets "
                    "(id bigint PRIMARY KEY, llm_sport_category text, "
                    "sport_id bigint, event_id bigint)"
                )
            )
            await s.execute(
                text(
                    "INSERT INTO backup_5621_events (id, status) "
                    "SELECT id, status FROM events WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"ids": event_ids},
            )
            await s.execute(
                text(
                    "INSERT INTO backup_5621_markets "
                    "(id, llm_sport_category, sport_id, event_id) "
                    "SELECT id, llm_sport_category, sport_id, event_id "
                    "FROM futures_markets WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"ids": market_ids},
            )
            await s.commit()
            print(f"  copied {len(event_ids)} events + {len(market_ids)} markets")

        # The D51 gate: every in-scope row has a backup row, and something was
        # checked. A clean pass over an EMPTY backup is not a clean pass.
        missing_e = (
            await s.execute(
                text(
                    "SELECT count(*) FROM events e WHERE e.id = ANY(:ids) AND NOT "
                    "EXISTS (SELECT 1 FROM backup_5621_events b WHERE b.id = e.id)"
                ),
                {"ids": event_ids},
            )
        ).scalar()
        missing_m = (
            await s.execute(
                text(
                    "SELECT count(*) FROM futures_markets f WHERE f.id = ANY(:ids) "
                    "AND NOT EXISTS (SELECT 1 FROM backup_5621_markets b "
                    "WHERE b.id = f.id)"
                ),
                {"ids": market_ids},
            )
        ).scalar()
        print(
            f"\n=== backup reconciliation === events missing={missing_e} "
            f"markets missing={missing_m}"
        )

        if not args.apply:
            print(
                "\nDRY RUN — nothing written. Would retire "
                f"{len(event_ids)} events and re-file {len(market_ids)} markets "
                f"to {TARGET_SPORT_KEY}/{TARGET_CATEGORY} with event_id cleared."
            )
            return 0

        if missing_e or missing_m:
            print("\nREFUSING --apply: backup is not exact. Run --backup first.")
            return 2

        sport_id = (
            await s.execute(
                text("SELECT id FROM sports WHERE key = :k"),
                {"k": TARGET_SPORT_KEY},
            )
        ).scalar()
        if not sport_id:
            print(f"\nREFUSING: no sports row for {TARGET_SPORT_KEY}.")
            return 2

        await s.execute(
            text("UPDATE events SET status = 'voided' WHERE id = ANY(:ids)"),
            {"ids": event_ids},
        )
        await s.execute(
            text(
                "UPDATE futures_markets SET llm_sport_category = :cat, "
                "sport_id = :sid, event_id = NULL WHERE id = ANY(:ids)"
            ),
            {"cat": TARGET_CATEGORY, "sid": sport_id, "ids": market_ids},
        )
        await s.commit()
        print(
            f"\nAPPLIED: retired {len(event_ids)} events; re-filed "
            f"{len(market_ids)} markets to {TARGET_SPORT_KEY} and unlinked them."
        )
        print(
            "UNDO: python3 scripts/restore_5621_phantom_ffpts_events.py --apply"
        )
        return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backup", action="store_true", help="copy in-scope rows")
    p.add_argument("--apply", action="store_true", help="write (needs a backup)")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)) or 0)


if __name__ == "__main__":
    main()
