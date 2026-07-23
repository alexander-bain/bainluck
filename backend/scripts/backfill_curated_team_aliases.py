"""#246 Item 1a — apply CURATED_TEAM_ALIASES into teams.alternate_names.

UNION-merges the curated colloquial nicknames (app/config/team_aliases.py) into
each franchise's `alternate_names` JSONB list, matched by (sport_key, name). This
makes "pats"/"revs"/… findable in the /search Teams surface (which builds a
query-time FTS vector over alternate_names). Union-safe: existing entries are
preserved, and the ESPN syncs also union (never overwrite), so curated aliases
persist across routine syncs.

Uses SQLAlchemy Core `update()` for the JSONB write (gotcha #4 — in-place ORM
mutation of a JSONB list can silently fail to flush). Dry-run by default; --apply
to commit. Idempotent: a second run adds nothing (the union is stable).

    python3 scripts/backfill_curated_team_aliases.py            # dry-run
    python3 scripts/backfill_curated_team_aliases.py --apply    # commit

Heroku one-off (gotcha #48 — non-detached run does not execute in the sandbox;
PROJECT_PATH=backend puts scripts at /app, so NO `cd backend`):
    heroku run:detached "python scripts/backfill_curated_team_aliases.py --apply" -a bainluck
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def merge_aliases(existing: list | None, curated: list[str]) -> list[str]:
    """Union existing alt-names with curated aliases, case-insensitively deduped,
    preserving the existing order then appending genuinely-new curated aliases."""
    existing = list(existing or [])
    seen = {str(e).strip().lower() for e in existing}
    out = list(existing)
    for a in curated:
        if a.strip().lower() not in seen:
            out.append(a)
            seen.add(a.strip().lower())
    return out


async def run(apply: bool) -> None:
    from app.config.team_aliases import CURATED_TEAM_ALIASES
    from app.tasks.base import get_task_session
    from sqlalchemy import text

    async with get_task_session() as s:
        changed = 0
        unmatched = []
        for (sport_key, name), aliases in CURATED_TEAM_ALIASES.items():
            row = (await s.execute(
                text("SELECT t.id, t.alternate_names FROM teams t "
                     "JOIN sports sp ON sp.id = t.sport_id "
                     "WHERE sp.key = :k AND t.name = :n"),
                {"k": sport_key, "n": name},
            )).first()
            if not row:
                unmatched.append((sport_key, name))
                print(f"  SKIP (no team): ({sport_key!r}, {name!r})")
                continue
            merged = merge_aliases(row.alternate_names, aliases)
            if merged == list(row.alternate_names or []):
                print(f"  ok (already present): {name} -> {row.alternate_names}")
                continue
            print(f"  {'APPLY' if apply else 'WOULD'}: {name} "
                  f"{row.alternate_names} -> {merged}")
            if apply:
                # Core update with explicit jsonb cast (asyncpg-safe; gotcha #4).
                await s.execute(
                    text("UPDATE teams SET alternate_names = CAST(:v AS jsonb) "
                         "WHERE id = :i"),
                    {"v": __import__("json").dumps(merged), "i": row.id},
                )
                changed += 1
        if apply:
            await s.commit()
        print(f"\n{'COMMITTED' if apply else 'DRY-RUN'}: "
              f"{changed} team(s) {'updated' if apply else 'would update'}, "
              f"{len(unmatched)} unmatched.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
