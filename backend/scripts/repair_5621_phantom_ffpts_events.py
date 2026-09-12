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

    AND THE TAP IS ON THE OTHER APP (CERT-2726, standing notice 48).
    `poll_kalshi_markets` and `match_prediction_markets` are both in
    `HEAVY_TASKS`, so the code that can re-mint these rows is what is deployed
    to `bainluck-heavy` — not the web app. Since the heavy split (2026-09-11)
    that app is released separately and drifts: at 14:24Z on 2026-09-12 it was
    v10 `87a095b4`, which does not carry `kxnflffpts`, while main already
    could. `tap_is_off()` can only inspect the map of the interpreter it runs
    in, so run from `-a bainluck` it reads the web app's fresh map, PASSES, and
    leaves the old heavy poller free to write every phantom straight back. The
    interlock is only an interlock on the producer's own app, so the app is
    checked (`HEROKU_APP_NAME`) rather than assumed.

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

Exact means CONTENT, not merely a matching id. The first cut of this script
inserted `ON CONFLICT (id) DO NOTHING` and then reconciled on existence, so a
backup taken before an unrelated writer moved a row stayed stale, still
satisfied the gate, and the documented undo would have restored the OLD value.
That is `5621-BACKUP-RECONCILIATION-MUST-BE-CONTENT-EXACT` (and the defect
CERT-2724 blocked on lane1b's #5595 the same morning). The insert now refreshes
on conflict and the gate compares every backed-up column with
`IS NOT DISTINCT FROM`, so a stale backup FAILS instead of passing.

    python3 scripts/restore_5621_phantom_ffpts_events.py --apply

USAGE

    python3 scripts/repair_5621_phantom_ffpts_events.py              # dry run
    python3 scripts/repair_5621_phantom_ffpts_events.py --backup
    python3 scripts/repair_5621_phantom_ffpts_events.py --apply

ORDER, and it is the whole safety argument (standing notice 48):

  1. #5624 merges — the web app releases and `bainluck.com` is correct.
  2. ALEX redeploys `bainluck-heavy` (attended) so the PRODUCER carries the
     prevention. Prove it, do not assume it:
         heroku releases -a bainluck-heavy      # the sha must contain #5624
  3. only then, ON THE PRODUCER'S APP:

    heroku run:detached -a bainluck-heavy \
        "python3 scripts/repair_5621_phantom_ffpts_events.py --backup"
    heroku run:detached -a bainluck-heavy \
        "python3 scripts/repair_5621_phantom_ffpts_events.py --apply"

Steps 2 and 3 are not advice. `--backup`/`--apply` refuse unless
`HEROKU_APP_NAME` is `bainluck-heavy`, and the map check then reads the
producer's own code, so "the tap is off" becomes a statement about the process
that could actually re-mint the rows. A dry run reads nothing and runs anywhere.

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

#: The app the PRODUCER runs on — see the header. `poll_kalshi_markets` and
#: `match_prediction_markets` live in `HEAVY_TASKS`, and since the heavy split
#: that means `bainluck-heavy`, released separately from the web app. Writing
#: from anywhere else makes `tap_is_off()` a statement about the wrong
#: interpreter.
PRODUCER_APP = "bainluck-heavy"

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
    """The prevention is deployed *in this interpreter*.

    Deliberately narrow: this can only ever answer for the process it runs in.
    `wrong_app_refusal` is what makes that process the right one.
    """
    return KALSHI_TICKER_TO_SPORT_KEY.get(TICKER_PREFIX, "").startswith(
        "americanfootball"
    )


def wrong_app_refusal(args):
    """Why this invocation may not WRITE, or None if it may.

    A dry run only reads, so it runs anywhere — locally, on either app. A write
    must happen on the producer's app, because that is the only place where
    `tap_is_off()` is inspecting the code that could re-mint the rows.

    `HEROKU_APP_NAME` is populated by the `runtime-dyno-metadata` lab, enabled
    on both `bainluck` and `bainluck-heavy` (checked 2026-09-12). Unset means we
    are not on a dyno at all — a laptop pointed at the production database with
    whatever happens to be checked out, which is precisely the case this gate
    exists to stop, so it refuses too rather than falling through.
    """
    if not (args.apply or args.backup):
        return None

    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None

    where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
    return (
        f"REFUSING to write: this is {where}, not '{PRODUCER_APP}'. The Kalshi "
        "poller and the matcher are HEAVY_TASKS, so the code that re-mints these "
        f"rows is what is deployed to '{PRODUCER_APP}' — an app released "
        "separately from the web app and routinely behind it (standing notice "
        "48). Run from anywhere else and the map check above passes against the "
        "wrong interpreter while the real producer keeps writing. Redeploy "
        f"'{PRODUCER_APP}' onto a sha containing PR #5624 (`heroku releases -a "
        f"{PRODUCER_APP}`), then re-run this with `heroku run:detached -a "
        f"{PRODUCER_APP}`."
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

    refusal = wrong_app_refusal(args)
    if refusal:
        print(refusal)
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
                    # DO UPDATE, not DO NOTHING: a second --backup after an
                    # unrelated writer moved a row must REFRESH it, or the undo
                    # restores a value that was never the one we overwrote.
                    "INSERT INTO backup_5621_events (id, status) "
                    "SELECT id, status FROM events WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status"
                ),
                {"ids": event_ids},
            )
            await s.execute(
                text(
                    "INSERT INTO backup_5621_markets "
                    "(id, llm_sport_category, sport_id, event_id) "
                    "SELECT id, llm_sport_category, sport_id, event_id "
                    "FROM futures_markets WHERE id = ANY(:ids) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "llm_sport_category = EXCLUDED.llm_sport_category, "
                    "sport_id = EXCLUDED.sport_id, "
                    "event_id = EXCLUDED.event_id"
                ),
                {"ids": market_ids},
            )
            await s.commit()
            print(f"  copied {len(event_ids)} events + {len(market_ids)} markets")

        # The D51 gate: every in-scope row has a backup holding the values that
        # are about to be overwritten. A clean pass over an EMPTY backup is not
        # a clean pass — and neither is one over a STALE backup, which is why
        # these compare CONTENT and not just the id. `IS NOT DISTINCT FROM`
        # rather than `=` so a NULL on both sides reconciles instead of
        # silently counting as a mismatch forever (`event_id` is nullable).
        stale_e = (
            await s.execute(
                text(
                    "SELECT count(*) FROM events e WHERE e.id = ANY(:ids) AND NOT "
                    "EXISTS (SELECT 1 FROM backup_5621_events b WHERE b.id = e.id "
                    "AND b.status IS NOT DISTINCT FROM e.status)"
                ),
                {"ids": event_ids},
            )
        ).scalar()
        stale_m = (
            await s.execute(
                text(
                    "SELECT count(*) FROM futures_markets f WHERE f.id = ANY(:ids) "
                    "AND NOT EXISTS (SELECT 1 FROM backup_5621_markets b "
                    "WHERE b.id = f.id "
                    "AND b.llm_sport_category IS NOT DISTINCT FROM "
                    "f.llm_sport_category "
                    "AND b.sport_id IS NOT DISTINCT FROM f.sport_id "
                    "AND b.event_id IS NOT DISTINCT FROM f.event_id)"
                ),
                {"ids": market_ids},
            )
        ).scalar()
        missing_e, missing_m = stale_e, stale_m
        print(
            f"\n=== backup reconciliation (content-exact) === events "
            f"unbacked-or-stale={stale_e} markets unbacked-or-stale={stale_m}"
        )

        if not args.apply:
            print(
                "\nDRY RUN — nothing written. Would retire "
                f"{len(event_ids)} events and re-file {len(market_ids)} markets "
                f"to {TARGET_SPORT_KEY}/{TARGET_CATEGORY} with event_id cleared."
            )
            return 0

        if missing_e or missing_m:
            print(
                "\nREFUSING --apply: the backup does not match the rows about to "
                "be written — either a row is unbacked, or it MOVED since the "
                "backup was taken and the undo would restore a value that was "
                "never overwritten. Re-run --backup."
            )
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
