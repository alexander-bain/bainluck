"""#1204 — CLI wrapper for the systemic team-identity merge (Queue #247 Item 1).

Folds bare-location duplicate team rows ("Boston" → "Boston Bruins", "Philadelphia"
→ "Philadelphia Union") into their canonical franchise. All logic + the safety gate
live in ``app/utils/team_merge.py`` (shared with POST /api/admin/repairs/
team-identity-merge). Dry-run by default (prints the plan + every skipped cluster
with its reason); --apply to commit.

    python3 scripts/merge_team_identities.py            # dry-run plan
    python3 scripts/merge_team_identities.py --apply    # commit the merges

Prefer the admin endpoint on production — a merge re-points the hot ``events``
table and running it in the web dyno (per-cluster) sidesteps the one-off-dyno lock
contention + gotcha-#48 exec failures. Heroku one-off (if you must):
    heroku run:detached "python scripts/merge_team_identities.py --apply" -a bainluck
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def run(apply: bool) -> None:
    from app.tasks.base import get_task_session
    from app.utils.team_merge import run_team_identity_merge

    async with get_task_session() as s:
        result = await run_team_identity_merge(s, apply)

    print("=== #1204 team-identity merge ===")
    print(f"  clusters examined: {result['clusters_examined']}")
    print(f"  clusters planned:  {result['clusters_planned']} "
          f"({result['pairs_planned']} stub pair(s))")
    print(f"  clusters skipped:  {result['clusters_skipped']} (see reasons below)")
    detail_key = "planned_detail" if not apply else "planned_detail"
    for e in result.get(detail_key, []):
        canon = e.get("canonical", {})
        folds = ", ".join(f"{f['name']}({f['slug']})" for f in e.get("folds", []))
        print(f"  PLAN [{e['sport_key']}] canonical={canon.get('name')} "
              f"(id={canon.get('id')}) ← {folds}")
    for e in result.get("skipped_detail", []):
        names = "/".join(m["name"] for m in e["members"])
        print(f"  SKIP [{e['sport_key']}] ({e['status']}): {names} — {e['reason']}")
    if apply:
        print(f"\nCOMMITTED: merged {result['pairs_merged']} stub pair(s).")
    else:
        print(f"\nDRY-RUN — pass --apply to merge {result['pairs_planned']} stub pair(s). "
              f"No writes made.")


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
