"""#208 Item 1c — Backfill national-team crests (flags) onto ``teams.logo_url``.

National sides ship with ``logo_url = NULL`` (verified live 2026-07-15: every
``soccer_fifa_world_cup`` nation had no crest), so team pages + any surface that
reads the teams row render a blank shield. A national team's canonical crest IS
its flag, so this fills ``logo_url`` / ``logo_url_small`` from the curated
``app.utils.nation_flags`` ISO map against flagcdn.

Two guardrails keep CLUBS untouched (the ruling):
  1. Only names in the CURATED nation map resolve (clubs aren't named after
     countries); everything else is skipped.
  2. Only rows under NATIONAL-TEAM competitions are considered (a positive
     sport-key filter: world_cup / international / six_nations / nations_league /
     qualifiers / copa / euro / odi / test_match), never club leagues.

Idempotent — only fills rows whose ``logo_url`` is currently NULL, so re-running
is a no-op and it never clobbers a real ESPN crest that later lands. Dry-run by
default; pass --apply to commit.

    python3 scripts/backfill_nation_flags.py            # dry-run (ledger only)
    python3 scripts/backfill_nation_flags.py --apply    # commit the backfill
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# National-team competitions only — never a club league.
_NATIONAL_SPORT_RE = (
    r"world_cup|international|six_nations|nations_league|qualifiers"
    r"|copa|euro|_odi|test_match"
)


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from app.utils.nation_flags import flag_url
    from sqlalchemy import text

    async with get_task_session() as s:
        rows = (await s.execute(text(f"""
            SELECT t.id, t.name, s.key AS sport_key
            FROM teams t
            JOIN sports s ON t.sport_id = s.id
            WHERE t.logo_url IS NULL
              AND s.key ~ :re
            ORDER BY s.key, t.name
        """), {"re": _NATIONAL_SPORT_RE})).all()

        updates = []  # (id, name, sport_key, large, small)
        for r in rows:
            large = flag_url(r.name, "w320")
            small = flag_url(r.name, "w80")
            if large is None:
                continue  # not a known nation → clubs & unknowns untouched
            updates.append((r.id, r.name, r.sport_key, large, small))

        print(f"Candidate NULL-logo national-team rows: {len(rows)}")
        print(f"Resolvable to a flag (curated nation map): {len(updates)}")
        for tid, name, sk, large, _small in updates[:60]:
            print(f"  {tid:>7}  {name:<24} [{sk:<32}] -> {large}")
        if len(updates) > 60:
            print(f"  ... and {len(updates) - 60} more")

        if not updates:
            print("\nNothing to backfill.")
            return
        if not apply:
            print(f"\nDRY-RUN — pass --apply to backfill {len(updates)} rows. No writes made.")
            return

        n = 0
        for tid, _name, _sk, large, small in updates:
            await s.execute(text("""
                UPDATE teams
                SET logo_url = :large,
                    logo_url_small = COALESCE(logo_url_small, :small)
                WHERE id = :id AND logo_url IS NULL
            """), {"large": large, "small": small, "id": tid})
            n += 1
        await s.commit()
        print(f"\nAPPLIED: backfilled flags on {n} national-team rows.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
