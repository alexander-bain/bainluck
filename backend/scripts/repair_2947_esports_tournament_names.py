"""#2947 — put the two team names back on the 366 esports events that lost them.

THE SHIP: an esports card stops printing a tournament as a team. Today an event
page and every search hit for these fixtures reads

    Counter-Strike: Fluxo W7M   vs   Back to Back  (BO3) - PGL Masters Bucharest

and the two actual teams are "Fluxo W7M" and "Back to Back". The prevention
(`_clean_esports_matchup`) stops the next one being written; this is the owed
repair for the ones already written. 23 of the 366 were non-terminal when this
was measured, eight of them live that day.

THE NET IS THE FIX'S NET, NOT A SECOND OPINION.
Names are not re-derived by a regex written here. For each event this script
re-runs `extract_matchup()` — the same function the matcher calls, carrying the
same guards — over the event's own Polymarket market names, and writes what it
returns. A repair whose net differs from the fix's either leaves rows behind or
eats rows the fix would have allowed. It follows that this script cannot repair
a row the fix would not have prevented, which is the property worth having.

WHAT IT WILL NOT TOUCH, and why each one is a deliberate refusal:

  * A row whose market names no longer parse, or parse to something that does
    not RECONSTRUCT the stored name. The check is exact: stored home must be
    "<anything>: <clean_a>" and stored away must be "<clean_b>(BOn)<anything>".
    A market that merely happens to hang off this event is not evidence of what
    the event was named from, and guessing would rename a row from an unrelated
    fixture's market.

  * A row whose clean name would COLLIDE — with a clean event that already
    exists, or with another row in this same plan. Five pairs collide with each
    other (all `closed`, identical `commence_time` to the second): they are
    pre-existing twins, lane1's under #2693, and renaming both would turn two
    obviously-broken rows into two convincing identical ones. That is the exact
    failure CERT-880 ruled against, and the reason this check runs over the full
    population rather than a sample. Measured 2026-09-04: 0 clean counterparts
    exist, so the only collisions are the five internal pairs.

  * Anything outside `events.home_team_name` / `.away_team_name`. Those are the
    only two columns holding the pollution — `teams` has 0 polluted rows
    (measured), no market moves, no blend is touched, nothing is deleted.

D51 UNDO. `--backup` writes every pre-repair (id, home, away) to
`bak_2947_event_names` before a single row changes, and
`restore_2947_esports_tournament_names.py --apply` is the one command that puts
them back. Run BOTH FLAGS IN ONE INVOCATION —

    heroku run:detached -a bainluck \
      "python3 scripts/repair_2947_esports_tournament_names.py --backup --apply"

— because a population can grow between two invocations (lane1b/029 paid for
that: rows keyed on a mutable status migrated INTO scope between the backup and
the apply, and the apply correctly refused). The backup is an idempotent
`NOT EXISTS` top-up, so a refusal is fixed by re-running that same one command.

The `bak_2947_*` table is NOT Alembic-managed. `alembic revision --autogenerate`
will propose DROPping it; that proposal must be deleted from the generated
migration, not accepted. Drop it deliberately with the restore script's
`--drop-backups` once the repair is trusted.

Without `--apply` this prints the full plan and writes nothing.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The fix itself. Imported, never restated — see the module docstring.
from app.utils.prediction_market_matching import (  # noqa: E402
    _ESPORTS_BEST_OF_RE,
    extract_matchup,
)

# Passed to Postgres as a BIND VALUE, never interpolated into the SQL text:
# inside SQLAlchemy `text()` a `(?:` group is read as a bind parameter named
# `:Exact` and the query dies as a bare `query_failed` (gotcha #45). This
# pattern has no `(?:` group, but the rule is the rule — as a value the pattern
# Postgres matches is byte-identical to the one Python matches.
BO_RE = _ESPORTS_BEST_OF_RE.pattern

BAK_TABLE = "bak_2947_event_names"

# Sanity floor. A repair that finds nothing and reports success is the worst
# outcome there is (gotcha #53 — an empty result is a response shape, not an
# absence). Measured population 2026-09-04 was 366; under this means the
# predicate broke, not that the work is done.
MIN_EXPECTED_POPULATION = 300

CHUNK = 200


def _fingerprint(stored_home: str, stored_away: str, team_a: str, team_b: str) -> bool:
    """True when (team_a, team_b) actually RECONSTRUCTS the stored pair.

    stored_home is "<game title>: <team_a>" (or bare team_a) and stored_away is
    "<team_b> (BOn) - <tournament>". Anything else means this market is not the
    one the event was named from, and the rename would be a guess.
    """
    if not team_a or not team_b:
        return False
    head = _ESPORTS_BEST_OF_RE.split(stored_away, maxsplit=1)[0].strip()
    if head.casefold() != team_b.strip().casefold():
        return False
    home, clean_a = stored_home.strip().casefold(), team_a.strip().casefold()
    return home == clean_a or home.endswith(f": {clean_a}")


async def build_plan(session, limit=0):
    """Re-derive clean names for the population. Returns (plan, skipped)."""
    from sqlalchemy import text

    rows = (
        await session.execute(
            text(
                "SELECT e.id, e.home_team_name, e.away_team_name, e.commence_time "
                "FROM events e WHERE e.away_team_name ~* :bo_re "
                "ORDER BY e.id" + (" LIMIT :lim" if limit else "")
            ),
            {"bo_re": BO_RE, **({"lim": limit} if limit else {})},
        )
    ).all()

    plan, skipped = [], []
    for event_id, home, away, commence in rows:
        names = (
            await session.execute(
                text(
                    "SELECT name FROM futures_markets "
                    "WHERE event_id = :eid AND source = 'polymarket' ORDER BY id"
                ),
                {"eid": event_id},
            )
        ).scalars().all()

        for name in names:
            matchup = extract_matchup(name)
            if matchup and _fingerprint(home, away, matchup.team_a, matchup.team_b):
                plan.append(
                    {
                        "id": event_id,
                        "old_home": home,
                        "old_away": away,
                        "new_home": matchup.team_a.strip(),
                        "new_away": matchup.team_b.strip(),
                        "commence": commence,
                        "from_market": name,
                    }
                )
                break
        else:
            skipped.append((event_id, home, away, "NO_MARKET_RECONSTRUCTS_THE_NAME"))

    return plan, skipped


async def drop_collisions(session, plan):
    """Remove rows whose clean name would land on top of another fixture."""
    from sqlalchemy import text

    def key(home, away, commence):
        return (home.casefold(), away.casefold(), commence.date())

    seen = {}
    for row in plan:
        seen.setdefault(key(row["new_home"], row["new_away"], row["commence"]), []).append(row)

    kept, dropped = [], []
    for group in seen.values():
        if len(group) > 1:
            # Pre-existing twins (#2693, lane1's). Renaming both would turn two
            # obviously-broken rows into two identical convincing ones.
            dropped.extend((r, "TWIN_WITHIN_PLAN") for r in group)
            continue
        row = group[0]
        clash = (
            await session.execute(
                text(
                    "SELECT id FROM events WHERE id <> :eid "
                    "AND lower(home_team_name) = lower(:h) "
                    "AND lower(away_team_name) = lower(:a) "
                    # +/-2 days, the window the counterpart rate was measured
                    # over (0 of 366) — not the calendar day, which would be a
                    # looser test than the evidence this repair rests on.
                    "AND commence_time BETWEEN :c - interval '2 days' "
                    "                      AND :c + interval '2 days' LIMIT 1"
                ),
                {
                    "eid": row["id"],
                    "h": row["new_home"],
                    "a": row["new_away"],
                    "c": row["commence"],
                },
            )
        ).first()
        if clash:
            dropped.append((row, f"CLEAN_COUNTERPART_EXISTS:{clash[0]}"))
        else:
            kept.append(row)
    return kept, dropped


async def ensure_backup(session, plan):
    """Idempotent `NOT EXISTS` top-up of the pre-repair names."""
    from sqlalchemy import text

    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BAK_TABLE} ("
            "  event_id bigint PRIMARY KEY,"
            "  home_team_name text NOT NULL,"
            "  away_team_name text NOT NULL,"
            # What the repair intends to write, so the undo can guard on the
            # exact value rather than infer it. Without this a restore has to
            # guess whether a differing current name is the repair's or someone
            # else's, and guessing is how an undo stomps a later decision.
            "  new_home_team_name text NOT NULL,"
            "  new_away_team_name text NOT NULL,"
            "  backed_up_at timestamptz NOT NULL DEFAULT now())"
        )
    )
    for chunk in [plan[i : i + CHUNK] for i in range(0, len(plan), CHUNK)]:
        for row in chunk:
            await session.execute(
                text(
                    f"INSERT INTO {BAK_TABLE} (event_id, home_team_name, away_team_name,"
                    "                          new_home_team_name, new_away_team_name) "
                    "SELECT :eid, :h, :a, :nh, :na WHERE NOT EXISTS "
                    f"(SELECT 1 FROM {BAK_TABLE} WHERE event_id = :eid)"
                ),
                {
                    "eid": row["id"],
                    "h": row["old_home"],
                    "a": row["old_away"],
                    "nh": row["new_home"],
                    "na": row["new_away"],
                },
            )
    await session.commit()

    covered = (
        await session.execute(
            text(f"SELECT count(*) FROM {BAK_TABLE} WHERE event_id = ANY(:ids)"),
            {"ids": [r["id"] for r in plan]},
        )
    ).scalar_one()
    return covered


async def apply_plan(session, plan):
    from sqlalchemy import text

    written = 0
    for chunk in [plan[i : i + CHUNK] for i in range(0, len(plan), CHUNK)]:
        for row in chunk:
            # Guarded on the OLD values: a row something else has since renamed
            # is left alone rather than stomped.
            result = await session.execute(
                text(
                    "UPDATE events SET home_team_name = :nh, away_team_name = :na "
                    "WHERE id = :eid AND home_team_name = :oh AND away_team_name = :oa"
                ),
                {
                    "eid": row["id"],
                    "nh": row["new_home"],
                    "na": row["new_away"],
                    "oh": row["old_home"],
                    "oa": row["old_away"],
                },
            )
            written += result.rowcount or 0
        await session.commit()
    return written


async def run(args):
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        plan, skipped = await build_plan(session, limit=args.limit)
        population = len(plan) + len(skipped)
        print(f"population (events with a (BOn) marker): {population}")
        print(f"  reconstructed from their own market : {len(plan)}")
        print(f"  skipped, no market reconstructs them: {len(skipped)}")

        if population < MIN_EXPECTED_POPULATION and not args.allow_small and not args.limit:
            print(
                f"REFUSING: population {population} < floor {MIN_EXPECTED_POPULATION}. "
                "The predicate probably broke. Re-run with --allow-small if the "
                "repair really has already run."
            )
            return 2

        plan, dropped = await drop_collisions(session, plan)
        print(f"  dropped as collisions               : {len(dropped)}")
        print(f"  TO RENAME                           : {len(plan)}")

        for row, why in dropped:
            print(f"    SKIP {row['id']}  {why}  -> {row['new_home']} vs {row['new_away']}")
        for event_id, home, away, why in skipped[:20]:
            print(f"    SKIP {event_id}  {why}  {home} vs {away}")

        for row in plan[:15]:
            print(
                f"    {row['id']}  {row['old_home']} vs {row['old_away']}"
                f"\n         -> {row['new_home']} vs {row['new_away']}"
            )
        if len(plan) > 15:
            print(f"    ... and {len(plan) - 15} more")

        if not plan:
            print("nothing to do")
            return 0

        if args.backup:
            covered = await ensure_backup(session, plan)
            print(f"backup: {covered}/{len(plan)} of the plan is in {BAK_TABLE}")
            if covered < len(plan):
                print("REFUSING: backup does not cover the plan.")
                return 3
        elif args.apply:
            print("REFUSING: --apply without --backup. Run both in one invocation.")
            return 4

        if not args.apply:
            print("DRY RUN — nothing written. Re-run with --backup --apply.")
            return 0

        written = await apply_plan(session, plan)
        print(f"APPLIED: {written} events renamed (planned {len(plan)})")
        print(
            "undo: heroku run:detached -a bainluck "
            '"python3 scripts/restore_2947_esports_tournament_names.py --apply"'
        )
        return 0 if written == len(plan) else 5


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--backup", action="store_true", help="top up the D51 backup table")
    p.add_argument("--apply", action="store_true", help="write the renames (needs --backup)")
    p.add_argument("--limit", type=int, default=0, help="plan at most N events (testing)")
    p.add_argument("--allow-small", action="store_true", help="bypass the population floor")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
