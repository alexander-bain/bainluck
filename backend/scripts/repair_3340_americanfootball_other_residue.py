"""#3340 — the American Football page stops serving 4,656 games that are not American football.

THE SHIP: `https://bainluck.com/sports/americanfootball_other`, screenshotted at
phone width on 2026-09-05, is headed *"American football · Win probabilities for
live and upcoming games"* and contains **35 cards, not one of which is an
American football game**. Czech and Polish lower-league soccer (`Gliwice vs
Katowice`, `Jihlava vs Ceska Lipa`), a table-tennis match (`Seeman Jan vs Sabuka
David`), NCAAF *spread questions* parsed into two teams (`Kansas State` vs
`Kansas by 10 or more points`), props (`49ers` vs `Rams - Highest Scoring
Quarter`), and ten fabricated NBA/NFL hybrids (`Nuggets vs Chiefs`, `Packers vs
Timberwolves`). Every one of them reads **"No result reported"**, forever,
because none is a fixture anybody will ever settle.

PREVENTION ALREADY SHIPPED. #2321 / PR #3339 (`271041c2`, merged `84277932`)
mapped the seven bare NFL period/race tickers and stopped the ambiguous
`football` fallback from auto-creating events, so no NEW row lands here. This
script is the owed DATA REPAIR for the rows written before it landed. #3339
shuts the valve; it does not sweep the residue, and merging it did not change
this page by a single card.

------------------------------------------------------------------------------
WHY THE WHOLE BUCKET, AND NOT A SAMPLE — measured on production 2026-09-05
------------------------------------------------------------------------------

`americanfootball_other` has **no legitimate producer**, and that is a
structural fact rather than a judgement about any one row:

    KALSHI_TICKER_TO_SPORT_KEY          0 tickers map here
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY  0 tickers map here
    SPORT_LEAGUE_MAP                    the key does not appear

Contrast its siblings, which is the whole reason this is a bucket sweep and the
Basketball page is NOT (see "WHAT THIS REPAIR REFUSES TO TOUCH" below):

    basketball_other   6 ticker producers (CBA, J-League, Argentine LNB, …)
    soccer_other       6 game + 3 futures producers, and 7,504 real external ids

CFL and UFL carry their own sport keys and NFL/NCAAF are ticker-mapped, so
nothing that IS American football has any reason to be here. The bucket is fed
exclusively by the per-market `llm_sport_category` fallback that #3339 closed.

The population census agrees without appeal — 4,656 servable rows:

    0 of 4,656 carries a score, and never has
    0 of 4,656 carries a home_team_id or an away_team_id
    0 of 4,656 carries a real external id

The one row in the bucket with an `external_id` at all is
`pm_kalshi_KXNCAAMBGAME-26FEB18JVSTLT` — a synthetic prediction-market id, and
`KXNCAAMBGAME` is NCAA men's *basketball* ("Jacksonville St. vs Louisiana
Tech"). Even the single apparent exception is a misfiled row from the same
fallback. Not one row here came from a schedule source.

CAUTION, recorded because it nearly became this docstring's argument: **"0 rows
have ever carried a score" is NOT on its own evidence of fakeness.** All fourteen
`*_other` buckets measure 0 scores, including `soccer_other`, which is
legitimately populated with 7,504 externally-sourced rows. The scoreless
property is a coverage gap in `*_other` generally. The load-bearing evidence is
the producer count and the absent external ids, which are specific to this key.

------------------------------------------------------------------------------
VOID, NOT DELETE — and why that clears a lower bar
------------------------------------------------------------------------------

#2871's standing rule is *never delete the only record of a real fixture*, and
#3026 had to adjudicate 274 rows one at a time to honour it. This repair does
not, because it does not delete: `status → 'voided'` is the **reversible soft
void** already used by `repair_season_series_mislinks.py` (#1220).

Since lane1/132's `fad6197a` (CERT-1888) the marker is honoured by every reader:
`RETIRED_STATUSES = {"merged", "voided"}` 410s the by-id read, and the list
surfaces exclude it by omission from their allowlists (`_SEARCH_STATUSES`,
`EVENT_LIST_DEFAULT_STATUSES`, and the three league-page rails in
`app/utils/event_rails.py`). So a void takes the card off the page, out of the
feed, out of search — and puts it all back with one command.

`voided`, not `merged`: `merged` means "duplicate of a row we can name", and the
by-id read resolves it to that canonical row. These phantoms have no canonical
counterpart to name. `voided` — "a game that will not be played" — is what they
are.

The markets are NOT unlinked. A voided event is never surfaced, so the link is
inert, and `futures_markets` keeps naming the fixture in full — the trace
survives exactly as #3026's "delete — the trace survives in the market" class
intended.

------------------------------------------------------------------------------
WHAT THIS REPAIR REFUSES TO TOUCH
------------------------------------------------------------------------------

`basketball_other` carries the sibling residue #3340 flags — `kxnflrace` put 80
NFL markets on basketball events. It is **out of scope and must stay that way**:
it has six legitimate ticker producers and 4,137 real external ids, so it is a
real bucket with residue in it, and sweeping it would void live CBA and J-League
games. That is a per-row repair on a different evidence base.

`baseball_other` and `tennis_other` are producerless by the same ticker test and
may hold the same class of residue, but neither has been censused row by row and
`baseball_other` holds 243 external ids. They are reported, not swept. A bucket
is only sweepable once its own evidence says so.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

    bak_3340_af_other_status   (event_id, old_status, banked_at)

Undo:  python3 scripts/restore_3340_americanfootball_other_residue.py --apply

One column moves, so the backup is one column wide. The restore reads the banked
`old_status` back onto the exact ids it banked and touches nothing else.

USAGE
    python3 scripts/repair_3340_americanfootball_other_residue.py            # dry run
    python3 scripts/repair_3340_americanfootball_other_residue.py --backup   # bank only
    python3 scripts/repair_3340_americanfootball_other_residue.py --backup --apply

Heroku one-off (gotcha #48 — a non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`, and the script
must be on the DEPLOYED SLUG before it can run at all):

    heroku run:detached "python3 scripts/repair_3340_americanfootball_other_residue.py --backup --apply" -a bainluck
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The producer maps are IMPORTED, never restated. If somebody legitimises this
# sport key by mapping a ticker to it, `producerless_refusal_reason` starts
# returning a reason and this script refuses to run rather than voiding a real
# league's games. That bind is the point: the repair cannot outlive its premise.
from app.utils.event_completion import RETIRED_STATUSES  # noqa: E402
from app.utils.sport_keys import (  # noqa: E402
    KALSHI_FUTURES_TICKER_TO_SPORT_KEY,
    KALSHI_TICKER_TO_SPORT_KEY,
    SPORT_LEAGUE_MAP,
)

TARGET_SPORT_KEY = "americanfootball_other"
BAK_TABLE = "bak_3340_af_other_status"

#: The soft-void marker, asserted to be part of the shipped retirement
#: vocabulary at import time. If somebody narrows ``RETIRED_STATUSES``, this
#: script stops importing rather than writing a status no reader excludes — the
#: exact failure this repair exists to avoid.
VOID_STATUS = "voided"
assert VOID_STATUS in RETIRED_STATUSES, (
    f"{VOID_STATUS!r} is not in RETIRED_STATUSES {sorted(RETIRED_STATUSES)} — "
    "voiding a row under a marker no reader honours would hide nothing and "
    "silently report success"
)

#: Rows already retired are skipped, so the script is idempotent.
ALREADY_RETIRED = tuple(sorted(RETIRED_STATUSES))

#: Rendered as a SQL literal list rather than a bind parameter, on purpose.
#: A list-valued bind (`IN :retired`, `= ANY(:ids)`) needs `expanding=True` to
#: work at all, and — measured on the 2026-09-04 one-off rail — the `ANY()` shape
#: rolls back SILENTLY on a detached dyno whose stdout cannot be read. The values
#: come from the imported constant, so this is derived, not restated.
_RETIRED_SQL = ", ".join(f"'{status}'" for status in ALREADY_RETIRED)

#: Sanity band, measured on production 2026-09-05. A repair that finds nothing
#: and reports success is the worst outcome there is (gotcha #53 — an empty
#: result is a response shape, not an absence), and one that suddenly finds ten
#: times the population has had its premise change underneath it.
MIN_EXPECTED_POPULATION = 3_000
MAX_EXPECTED_POPULATION = 8_000

#: Pre-registered census. `--apply` refuses unless the live measurement still
#: shows zeros, so this docstring's claims and the dyno's result cannot drift
#: apart unnoticed.
EXPECTED_ZEROS = ("with_score", "with_team_id", "with_real_external_id")


def producerless_refusal_reason(sport_key: str) -> str | None:
    """Why this sport key must NOT be swept, or ``None`` if it is safe to sweep.

    Pure. The sweep's whole licence is that no legitimate producer can put a row
    under this key, so the licence is re-derived from the shipped maps on every
    run rather than trusted from a docstring.
    """
    game = sorted(k for k, v in KALSHI_TICKER_TO_SPORT_KEY.items() if v == sport_key)
    if game:
        return (
            f"{len(game)} Kalshi game ticker(s) map to {sport_key} "
            f"({', '.join(game[:5])}) — it has a legitimate producer and its rows "
            f"cannot be swept as a bucket"
        )
    futures = sorted(
        k for k, v in KALSHI_FUTURES_TICKER_TO_SPORT_KEY.items() if v == sport_key
    )
    if futures:
        return (
            f"{len(futures)} Kalshi futures ticker(s) map to {sport_key} "
            f"({', '.join(futures[:5])}) — legitimate producer"
        )
    if sport_key in SPORT_LEAGUE_MAP or sport_key in set(SPORT_LEAGUE_MAP.values()):
        return f"{sport_key} appears in SPORT_LEAGUE_MAP — it is a covered league"
    return None


def population_refusal_reason(measured: dict) -> str | None:
    """Why the measured population must NOT be voided, or ``None`` if it is safe.

    Pure, so the gate is unit-testable without a database. Every clause is a
    reason to find a REAL fixture in the bucket; any one of them firing means the
    premise ("nothing here came from a schedule source") has stopped holding.
    """
    population = measured.get("population", 0)
    if population < MIN_EXPECTED_POPULATION:
        return (
            f"population {population} is below the floor {MIN_EXPECTED_POPULATION} "
            f"— either the repair already ran, or the census the plan was built on "
            f"no longer describes production"
        )
    if population > MAX_EXPECTED_POPULATION:
        return (
            f"population {population} exceeds the ceiling {MAX_EXPECTED_POPULATION} "
            f"— the bucket grew far beyond the measured residue; re-measure before "
            f"voiding it"
        )
    for field in EXPECTED_ZEROS:
        count = measured.get(field, 0)
        if count:
            return (
                f"{count} row(s) have {field} — a row with a score, a resolved team "
                f"or a real external id came from a schedule source and may be a "
                f"REAL fixture. #2871: never hide the only record of a real game. "
                f"Adjudicate those rows individually before sweeping the bucket."
            )
    return None


_CENSUS_SQL = f"""
SELECT count(*) AS population,
       count(*) FILTER (WHERE e.home_score IS NOT NULL
                           OR e.away_score IS NOT NULL)      AS with_score,
       count(*) FILTER (WHERE e.home_team_id IS NOT NULL
                           OR e.away_team_id IS NOT NULL)    AS with_team_id,
       count(*) FILTER (WHERE e.external_id IS NOT NULL
                         AND e.external_id NOT LIKE 'pm\\_%') AS with_real_external_id
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.status NOT IN ({_RETIRED_SQL})
"""

_IDS_SQL = f"""
SELECT e.id, e.status
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.status NOT IN ({_RETIRED_SQL})
 ORDER BY e.id
"""

#: What a user can actually see today, by the three league-page rails in
#: `app/utils/event_rails.py`. The bucket total is the repair's scope; THIS is
#: the ship, and it is the number the before/after is reported on.
_VISIBLE_SQL = f"""
SELECT count(*) FILTER (WHERE e.status = 'live'
                           OR (e.status = 'scheduled'
                               AND e.commence_time >= now() - interval '2 hours'))
           AS upcoming_rail,
       count(*) FILTER (WHERE e.status = 'scheduled'
                          AND e.commence_time <  now() - interval '2 hours'
                          AND e.commence_time >= now() - interval '14 days')
           AS unreported_rail,
       count(*) FILTER (WHERE e.status IN ('completed', 'closed', 'suspended')
                          AND e.commence_time >= now() - interval '14 days')
           AS recent_rail
  FROM events e
  JOIN sports s ON s.id = e.sport_id
 WHERE s.key = :sport_key
   AND e.status NOT IN ({_RETIRED_SQL})
"""


async def measure(session, sport_key: str = TARGET_SPORT_KEY) -> dict:
    """Census + user-visible rail counts for the bucket. Read-only."""
    from sqlalchemy import text

    params = {"sport_key": sport_key}
    census = (await session.execute(text(_CENSUS_SQL), params)).one()
    visible = (await session.execute(text(_VISIBLE_SQL), params)).one()
    return {
        "population": census.population,
        "with_score": census.with_score,
        "with_team_id": census.with_team_id,
        "with_real_external_id": census.with_real_external_id,
        "visible_upcoming": visible.upcoming_rail,
        "visible_unreported": visible.unreported_rail,
        "visible_recent": visible.recent_rail,
        "visible_total": (
            visible.upcoming_rail + visible.unreported_rail + visible.recent_rail
        ),
    }


async def ensure_backup(session, sport_key: str = TARGET_SPORT_KEY) -> int:
    """Create the D51 backup table and bank every row's CURRENT status.

    Returns rows banked on this call. `ON CONFLICT DO NOTHING` keeps the FIRST
    banked status, which is the pre-repair one — a re-run after a partial apply
    must not overwrite a banked `scheduled` with the `voided` it just wrote.
    """
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  old_status text NOT NULL,"
            "  sport_key text NOT NULL,"
            "  banked_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    await session.commit()

    banked = (
        await session.execute(
            text(
                f"INSERT INTO {BAK_TABLE} (event_id, old_status, sport_key) "
                "SELECT e.id, e.status, :sport_key FROM events e "
                "JOIN sports s ON s.id = e.sport_id "
                f"WHERE s.key = :sport_key AND e.status NOT IN ({_RETIRED_SQL}) "
                "ON CONFLICT (event_id) DO NOTHING"
            ),
            {"sport_key": sport_key},
        )
    ).rowcount or 0
    await session.commit()
    return banked


async def void_rows(session, event_ids: list[int], *, progress_every: int = 250) -> int:
    """Flip each row to ``voided``, ONE ROW PER TRANSACTION.

    Deliberately not a batch UPDATE and deliberately without a short
    `lock_timeout`: `events` is write-hot (constant poller and backfill locks), and
    a batched or lock-impatient one-off rolls back on every row. A single-row
    UPDATE that is willing to WAIT for the lock succeeds. Slow is the point.
    """
    from sqlalchemy import text

    written = 0
    for index, event_id in enumerate(event_ids, start=1):
        for attempt in (1, 2, 3):
            try:
                result = await session.execute(
                    text(
                        "UPDATE events SET status = :void "
                        f"WHERE id = :eid AND status NOT IN ({_RETIRED_SQL})"
                    ),
                    {"void": VOID_STATUS, "eid": event_id},
                )
                await session.commit()
                written += result.rowcount or 0
                break
            except Exception as exc:  # noqa: BLE001 — retry, then surface
                await session.rollback()
                if attempt == 3:
                    print(f"  FAILED event {event_id} after 3 attempts: {exc}")
                else:
                    await asyncio.sleep(attempt)
        if progress_every and index % progress_every == 0:
            print(f"  … {index}/{len(event_ids)} processed, {written} voided")
    return written


async def run(*, backup: bool, apply: bool, sport_key: str = TARGET_SPORT_KEY) -> None:
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    refusal = producerless_refusal_reason(sport_key)
    if refusal:
        print(f"REFUSING: {refusal}")
        sys.exit(1)
    print(f"Producer check: no ticker and no league entry maps to {sport_key}. OK.")

    async with get_task_session() as session:
        before = await measure(session, sport_key)
        print(f"\n=== #3340 census for {sport_key} ===")
        print(json.dumps(before, indent=2))
        print(
            f"\nOn the page right now: {before['visible_total']} cards "
            f"({before['visible_upcoming']} upcoming, "
            f"{before['visible_unreported']} no-result-reported, "
            f"{before['visible_recent']} recent results)"
        )

        if before["population"] == 0:
            print("\nNothing to repair — census already 0 (idempotent no-op).")
            return

        blocked = population_refusal_reason(before)
        if blocked and apply:
            print(f"\nREFUSING TO APPLY: {blocked}")
            sys.exit(1)
        if blocked:
            print(f"\nWOULD REFUSE: {blocked}")

        if backup:
            banked = await ensure_backup(session, sport_key)
            total = (
                await session.execute(text(f"SELECT count(*) FROM {BAK_TABLE}"))
            ).scalar() or 0
            print(f"\nBACKUP: banked {banked} new row(s); {total} total in {BAK_TABLE}")

        if not apply:
            print(
                f"\nDRY RUN — nothing written. {before['population']} rows would be "
                f"set status→'{VOID_STATUS}'. Re-run with --backup --apply."
            )
            return

        if not backup:
            print("\nREFUSING: --apply requires --backup in the same run (D51)")
            sys.exit(1)

        rows = (
            await session.execute(
                text(_IDS_SQL),
                {"sport_key": sport_key},
            )
        ).all()
        event_ids = [r.id for r in rows]
        print(f"\nVOIDING {len(event_ids)} rows, one transaction each …")
        written = await void_rows(session, event_ids)

        after = await measure(session, sport_key)
        print(f"\nCOMMITTED: {written} rows set status→'{VOID_STATUS}'.")
        print(json.dumps({"before": before, "after": after}, indent=2))
        if after["visible_total"] == 0:
            print(
                f"\n✅ #3340: the {sport_key} page serves 0 cards "
                f"(was {before['visible_total']})."
            )
        else:
            print(
                f"\n⚠️  {after['visible_total']} cards still visible — investigate "
                f"before closing #3340."
            )
        print(
            "\nUndo: python3 scripts/restore_3340_americanfootball_other_residue.py "
            "--apply"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--backup", action="store_true", help="top up the D51 backup table"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write the repair (requires --backup)"
    )
    parser.add_argument(
        "--sport-key",
        default=TARGET_SPORT_KEY,
        help="sport key to sweep (refused unless it is producerless)",
    )
    args = parser.parse_args()
    asyncio.run(run(backup=args.backup, apply=args.apply, sport_key=args.sport_key))


if __name__ == "__main__":
    main()
