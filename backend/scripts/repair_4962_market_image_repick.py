"""#4962 — clear the pictures that are about something else, so they get re-picked.

THE SHIP: a market card stops illustrating a question it is not about.

Two rows were filed on #4962, and both still hold the photograph the old query
fetched. Measured on production 2026-09-18, with the stored `image_url` resolved
back to its Pexels photo id:

    16757297  "Presidents Cup Winner"            golf
              photo 38465895 -> "Spectacular aerial display by US Air Force
              Thunderbirds flying in formation over Washington, DC."

    109295    "Will Taylor Swift meet with Pope Leo XIV before 2027?"  entertainment
              photo 35156556 -> "A competitive swimmer performs a backstroke in
              a pool, creating splashes."

PREVENTION SHIPS FIRST and it does not reach these rows. `enrich_market_images`
selects `image_url IS NULL`, so the corrected query only ever runs on rows that
have no picture yet. A row that already holds a wrong one is never revisited —
that asymmetry is the whole reason this script exists. (Same shape as #5621's:
a forward-only writer fix is inert on exactly the rows where the defect landed.)

------------------------------------------------------------------------------
WHY THIS CLEARS RATHER THAN REPLACES
------------------------------------------------------------------------------

Alex's constraint on #6444, verbatim: *"Do not replace with another arbitrary
picture."* So this script writes NULL into the three image columns and stops.
The corrected enricher then re-picks on its own beat (`minute=50, hour=*/4`,
`limit=200`, ordered by `volume_24h desc`), using the query the fix built. In
between, the card is imageless, which is honest; a second unrelated photograph
is not.

That also makes the repair cheap to reason about: one nullable display column
and its two dimension columns, no FK, no child row, nothing settled, nothing
priced, and the undo is the backup.

------------------------------------------------------------------------------
THE INTERLOCK — the tap must be off, and "off" is checked, not assumed
------------------------------------------------------------------------------

Clearing a picture is only a repair if the NEXT pick asks a different question.
If the deployed code would rebuild the same query, this script deletes a
photograph and re-fetches the identical one — strictly worse than doing nothing.

So `--backup` / `--apply` import the deployed `_image_query_candidates` and, per
row, compare its first candidate with `_legacy_image_keywords` — the extractor
exactly as it shipped before #4962, reproduced below so the comparison is
auditable rather than remembered. A row whose query is UNCHANGED aborts the run.
That is the same idea as repair_5621's ticker-map check: the interlock reads the
producer's own code rather than trusting a deploy.

AND THE PRODUCER IS THE MAIN APP. `app.tasks.enrich_market_images` is not in
`HEAVY_TASKS` (standing notice 48 does not apply here), so the code that will do
the re-pick is what is deployed to `bainluck`. `--backup` / `--apply` refuse
unless `HEROKU_APP_NAME` is `bainluck`, so the interlock is a statement about the
process that will actually re-pick these rows. A dry run reads nothing and runs
anywhere.

------------------------------------------------------------------------------
D51 — BACKUP FIRST, ONE-COMMAND RESTORE
------------------------------------------------------------------------------

`--apply` REFUSES until `--backup` has copied every in-scope row into
`backup_4962_market_images` and the reconciliation is CONTENT-exact — every
backed-up column compared with `IS NOT DISTINCT FROM`, not merely a matching id
(#5621's `5621-BACKUP-RECONCILIATION-MUST-BE-CONTENT-EXACT`: a backup taken
before another writer moved the row stays stale, satisfies an existence check,
and the documented undo restores the OLD value). The insert refreshes on
conflict, so a second `--backup` after a change is a refresh and not a no-op.

The gate survives its own precondition: before `--backup` has ever run the table
does not exist, and `to_regclass` reads that as "every in-scope row is unbacked"
rather than crashing on the dry run, which is the first thing anybody runs.

The backup table is created by this script at invocation time. Under notice
47(c) that is runtime DDL behind an attended invocation on a named app — NOT
migration-class: nothing here runs on merge or on release.

    python3 scripts/restore_4962_market_images.py --apply

USAGE

    python3 scripts/repair_4962_market_image_repick.py                 # dry run
    python3 scripts/repair_4962_market_image_repick.py --backup
    python3 scripts/repair_4962_market_image_repick.py --apply
    python3 scripts/repair_4962_market_image_repick.py --ids 1,2 ...   # extend scope

ORDER, and it is the whole safety argument:

  1. the #4962 fix merges and `bainluck` releases — prove it, do not assume it:
         heroku releases -a bainluck      # the sha must contain the fix
  2. only then, ON THE PRODUCER'S APP:

    heroku run:detached -a bainluck \
        "python3 scripts/repair_4962_market_image_repick.py --backup"
    heroku run:detached -a bainluck \
        "python3 scripts/repair_4962_market_image_repick.py --apply"

  3. the next `enrich-market-images` fire (`:50` of every 4th hour) re-picks.
     `image_url` going from NULL back to a URL is the after-check.

Non-detached `heroku run` fails silently in the sandbox (gotcha #48): use
`run:detached` and verify the side effect ~60s later.
"""

import argparse
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.tasks.base import get_task_session  # noqa: E402

# The prevention's own vocabulary, imported rather than restated. An ImportError
# here means the fix is not deployed and the repair must not run.
from app.tasks.enrich_markets import _image_query_candidates  # noqa: E402

#: The rows filed on #4962. Both `status='open'`, both holding a photograph of
#: something else. `--ids` extends this; nothing widens it implicitly.
FILED_MARKET_IDS = (16757297, 109295)

#: The app whose deploy carries `enrich_market_images`. Not a heavy task.
PRODUCER_APP = "bainluck"

BACKUP_TABLE = "backup_4962_market_images"


def _legacy_image_keywords(name: str, category: str | None) -> str:
    """`_extract_image_keywords` EXACTLY as it shipped before #4962.

    Reproduced so the "did the query actually change" interlock compares against
    something a reviewer can read, rather than against a memory of what the old
    code did. It is dead weight the day #4962's rows are repaired, and it is
    deliberately not imported from anywhere — there is nowhere to import it from.
    """
    name = re.sub(
        r"\b(Winner|Over/Under|O/U|Spread|Total|Moneyline)\b",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\b(on|at|in|the|a|an|of|for|to|vs\.?|by)\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\d{4}[-/]\d{2,4}", "", name)
    name = re.sub(r"[:\-–—|()#]", " ", name)
    words = [w for w in name.split() if len(w) > 2][:4]
    if not words and category:
        words = [category]
    return " ".join(words)


def query_changed(name: str, category: str | None) -> tuple[str, str, bool]:
    """(old query, the new first candidate, did it change).

    Pure, so the interlock is unit-testable without a database.
    """
    old = _legacy_image_keywords(name, category)
    candidates = _image_query_candidates(name, category)
    new = candidates[0] if candidates else ""
    return old, new, new != old


def _parse_ids(raw: str | None) -> tuple[int, ...]:
    if not raw:
        return FILED_MARKET_IDS
    return tuple(int(part) for part in raw.replace(",", " ").split())


async def run(args) -> int:
    ids = _parse_ids(args.ids)
    id_list = ", ".join(str(i) for i in ids)

    async with get_task_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT id, name, llm_sport_category, status, image_url, "
                    "image_width, image_height FROM futures_markets "
                    f"WHERE id IN ({id_list}) ORDER BY id"
                )
            )
        ).all()

        print(f"=== scope === {len(rows)} of {len(ids)} requested id(s) found")
        in_scope = []
        unchanged = []
        for row in rows:
            old, new, changed = query_changed(row.name, row.llm_sport_category)
            mark = "" if row.image_url else "   (already imageless — nothing to clear)"
            print(f"\n  {row.id}  {row.name!r}  [{row.llm_sport_category}] {row.status}{mark}")
            print(f"      stored : {row.image_url}")
            print(f"      old query : {old!r}")
            print(f"      new query : {new!r}   changed={changed}")
            if not changed:
                unchanged.append(row.id)
            elif row.image_url is not None:
                in_scope.append(row)

        if unchanged:
            print(
                "\nREFUSING: the deployed extractor builds the SAME query for "
                f"{unchanged} — clearing those rows would re-fetch the identical "
                "photograph. The #4962 fix is not deployed on this app, or these "
                "ids are not what this repair is for."
            )
            return 2

        if not (args.apply or args.backup):
            print(f"\n=== dry run === {len(in_scope)} row(s) would be cleared. Nothing written.")
            return 0

        app = os.environ.get("HEROKU_APP_NAME")
        if app != PRODUCER_APP:
            where = f"'{app}'" if app else "not a Heroku dyno (HEROKU_APP_NAME is unset)"
            print(
                f"\nREFUSING --backup/--apply: this is {where}, and the app that "
                f"will re-pick these rows is '{PRODUCER_APP}'. The interlock above "
                "read THIS interpreter's code, so it only speaks for the producer "
                "when it runs on the producer."
            )
            return 2

        if not in_scope:
            print("\nnothing in scope to back up or clear.")
            return 0

        scope_ids = ", ".join(str(r.id) for r in in_scope)

        if args.backup:
            print("\n=== backup ===")
            await session.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} ("
                    "id BIGINT PRIMARY KEY, image_url TEXT, image_width INTEGER, "
                    "image_height INTEGER, backed_up_at TIMESTAMPTZ NOT NULL DEFAULT now())"
                )
            )
            # DO UPDATE, not DO NOTHING: a second --backup after another writer
            # moved a row must REFRESH it, or the undo restores a stale value.
            result = await session.execute(
                text(
                    f"INSERT INTO {BACKUP_TABLE} (id, image_url, image_width, image_height) "
                    "SELECT id, image_url, image_width, image_height FROM futures_markets "
                    f"WHERE id IN ({scope_ids}) "
                    "ON CONFLICT (id) DO UPDATE SET image_url = EXCLUDED.image_url, "
                    "image_width = EXCLUDED.image_width, "
                    "image_height = EXCLUDED.image_height, backed_up_at = now()"
                )
            )
            await session.commit()
            print(f"  backed up {result.rowcount} row(s) into {BACKUP_TABLE}")

        # The gate has to survive its own precondition: on the first dry run the
        # table does not exist, and "the backup is missing" is a verdict, not a
        # crash.
        backed = bool(
            (
                await session.execute(
                    text(f"SELECT to_regclass('public.{BACKUP_TABLE}') IS NOT NULL")
                )
            ).scalar()
        )
        if not backed:
            print(
                f"\n=== backup reconciliation (content-exact) === {BACKUP_TABLE} does "
                "not exist; every in-scope row is unbacked. Run --backup before --apply."
            )
            unbacked = len(in_scope)
        else:
            unbacked = (
                await session.execute(
                    text(
                        "SELECT count(*) FROM futures_markets f WHERE f.id IN "
                        f"({scope_ids}) AND NOT EXISTS (SELECT 1 FROM {BACKUP_TABLE} b "
                        "WHERE b.id = f.id "
                        "AND b.image_url IS NOT DISTINCT FROM f.image_url "
                        "AND b.image_width IS NOT DISTINCT FROM f.image_width "
                        "AND b.image_height IS NOT DISTINCT FROM f.image_height)"
                    )
                )
            ).scalar()
            print(
                "\n=== backup reconciliation (content-exact) === "
                f"in scope {len(in_scope)}, unbacked-or-stale {unbacked}"
            )

        if args.apply:
            if unbacked:
                print(
                    "\nREFUSING --apply: the backup does not match the rows about to "
                    "be cleared. Run --backup again."
                )
                return 2
            result = await session.execute(
                text(
                    "UPDATE futures_markets SET image_url = NULL, image_width = NULL, "
                    f"image_height = NULL WHERE id IN ({scope_ids})"
                )
            )
            await session.commit()
            print(f"\n=== apply === cleared {result.rowcount} row(s).")
            print(
                "  the next enrich-market-images fire (:50, every 4th hour) re-picks "
                "them with the corrected query. Undo:\n"
                "    python3 scripts/restore_4962_market_images.py --apply"
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backup", action="store_true", help="copy in-scope rows into the backup table")
    parser.add_argument("--apply", action="store_true", help="clear the image columns (needs a fresh backup)")
    parser.add_argument("--ids", help="comma/space separated market ids (default: the #4962 filed rows)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
