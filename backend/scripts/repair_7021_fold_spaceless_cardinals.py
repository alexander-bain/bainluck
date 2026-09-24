"""#7021 — fold the spaceless "St.Louis Cardinals" team row into the real club.

THE SHIP: searching "Cardinals" shows the St. Louis Cardinals once, spelled
right, and the club's page carries its division standing. On 2026-09-23 the
search's TOP team result was ``St.Louis Cardinals`` (13437, slug
``stlouis-cardinals``) and the real club (10740, ``St. Louis Cardinals``) sat
third; the two team pages split the club between them — the misspelled one had
"National League · #4 in Central" and one futures market, the real one had
every futures market and no standing.

WHAT THE ROWS SAY (production, 2026-09-23 ~23:10Z)
--------------------------------------------------

Both rows are ``baseball_mlb`` and carry ESPN team id 24 — one club, two rows.

    13437  'St.Louis Cardinals'   slug stlouis-cardinals      standings board (StatPal, 08:00Z)
    10740  'St. Louis Cardinals'  slug st-louis-cardinals-mlb standings NULL

No Cardinals game has bound to 13437 since 2026-09-06; every current fixture
is on 10740. What keeps 13437 alive is StatPal's standings writer
(``statpal_sync`` — ``db_by_name.get(team_name.lower())``): StatPal spells the
club ``St.Louis Cardinals``, only 13437 answers to that exact string, so the
board lands there every morning. The team lookup then prefers the row with the
fresher board (#7132), so a correct name resolves onto the duplicate.

WHAT THIS DOES
--------------

In one transaction, after banking both team rows whole and every foreign-key
row it moves:

1. repoints every ``teams.id`` reference from 13437 to 10740 — the population
   is pinned by exact count per (table, column), zero-count ones included, and
   a moved count refuses;
2. gives 10740 the duplicate's standings board if it is fresher than 10740's;
3. adds ``St.Louis Cardinals`` to 10740's ``alternate_names`` — THIS is what
   stops the split coming back: StatPal's writer reads alternate names into the
   same map, so tomorrow's board lands on 10740;
4. registers ``stlouis-cardinals`` as a legacy slug for 10740 (#1204), so the
   old URL opens the real club instead of 404-ing;
5. deletes 13437.

It does NOT touch registry entity 5422's name or slug (it is repointed, not
edited), nor the ``statpal`` identity mapping that points at the preseason row
2692 — neither is read by the writer or the surfaces above.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_7021_fold_spaceless_cardinals.py            # dry run
    python3 scripts/repair_7021_fold_spaceless_cardinals.py --apply    # bank, fold, delete
    python3 scripts/repair_7021_fold_spaceless_cardinals.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCER_APP = "bainluck-heavy"

DUP_ID = 13437
DUP_NAME = "St.Louis Cardinals"
CANON_ID = 10740
CANON_NAME = "St. Louis Cardinals"
ESPN_ID = "24"
SPORT_KEY = "baseball_mlb"
LEGACY_SLUG = "stlouis-cardinals"

#: Every foreign key onto ``teams.id`` in production (read from
#: ``pg_constraint`` 2026-09-23) with the number of rows naming the duplicate.
#: A zero is pinned too: a favourite appearing on 13437 could collide with the
#: same user's favourite of 10740, so it refuses rather than guesses.
REPOINTS: dict[tuple[str, str], int] = {
    ("events", "home_team_id"): 13,
    ("events", "away_team_id"): 21,
    ("futures_outcomes", "team_id"): 1,
    ("entities", "source_team_id"): 1,
    ("user_favorites", "team_id"): 0,
    ("tournament_odds", "team_id"): 0,
    ("team_identity_mapping", "team_id"): 0,
}

BACKUP_TEAMS = "backup_7021_teams"
BACKUP_REPOINTS = "backup_7021_repoints"


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def rows_refusal(dup: dict | None, canon: dict | None) -> str | None:
    """Both rows must still be the one club, measured."""
    if canon is None:
        return f"canonical row {CANON_ID} is gone"
    if dup is None:
        return f"duplicate row {DUP_ID} is gone"
    for label, row, name in (
        ("duplicate", dup, DUP_NAME),
        ("canonical", canon, CANON_NAME),
    ):
        if row["name"] != name:
            return f"{label} row {row['id']} is now named {row['name']!r}, expected {name!r}"
        if row["sport_key"] != SPORT_KEY:
            return f"{label} row {row['id']} is {row['sport_key']!r}, expected {SPORT_KEY!r}"
        if row["espn_id"] != ESPN_ID:
            return f"{label} row {row['id']} carries espn_id {row['espn_id']!r}, expected {ESPN_ID!r}"
    return None


def counts_refusal(counts: dict[tuple[str, str], int]) -> str | None:
    """Exact pinned counts, or refuse — a moved count means another writer."""
    drift = [
        f"{t}.{c}: {counts.get((t, c))} (pinned {n})"
        for (t, c), n in REPOINTS.items()
        if counts.get((t, c)) != n
    ]
    return "population moved — " + "; ".join(drift) if drift else None


async def _read_rows(session) -> tuple[dict | None, dict | None]:
    res = await session.execute(
        text(
            "SELECT t.id, t.name, t.espn_id, s.key AS sport_key "
            "FROM teams t LEFT JOIN sports s ON s.id = t.sport_id "
            "WHERE t.id IN (:dup, :canon)"
        ),
        {"dup": DUP_ID, "canon": CANON_ID},
    )
    rows = {r.id: dict(r._mapping) for r in res}
    return rows.get(DUP_ID), rows.get(CANON_ID)


async def _counts(session) -> dict[tuple[str, str], int]:
    out = {}
    for table, col in REPOINTS:
        res = await session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {col} = :dup"), {"dup": DUP_ID}
        )
        out[(table, col)] = int(res.scalar_one())
    return out


async def _backup_exists(session) -> bool:
    res = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TEAMS})
    return res.scalar_one() is not None


async def _apply(session) -> dict[tuple[str, str], int]:
    # First pre-image wins: a second run never overwrites what was banked.
    await session.execute(
        text(f"CREATE TABLE IF NOT EXISTS {BACKUP_TEAMS} AS SELECT * FROM teams WHERE FALSE")
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TEAMS} SELECT * FROM teams WHERE id IN (:dup, :canon) "
            f"AND id NOT IN (SELECT id FROM {BACKUP_TEAMS})"
        ),
        {"dup": DUP_ID, "canon": CANON_ID},
    )
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_REPOINTS} "
            "(tbl text NOT NULL, col text NOT NULL, row_id bigint NOT NULL)"
        )
    )

    moved = {}
    for table, col in REPOINTS:
        await session.execute(
            text(
                f"INSERT INTO {BACKUP_REPOINTS} (tbl, col, row_id) "
                f"SELECT :tbl, :col, id FROM {table} WHERE {col} = :dup "
                f"AND NOT EXISTS (SELECT 1 FROM {BACKUP_REPOINTS} b "
                f"WHERE b.tbl = :tbl AND b.col = :col AND b.row_id = {table}.id)"
            ),
            {"tbl": table, "col": col, "dup": DUP_ID},
        )
        res = await session.execute(
            text(f"UPDATE {table} SET {col} = :canon WHERE {col} = :dup"),
            {"canon": CANON_ID, "dup": DUP_ID},
        )
        moved[(table, col)] = res.rowcount

    # The board is carried only if it is the fresher one; a board 10740 already
    # holds that is newer is today's truth and is kept.
    await session.execute(
        text(
            "UPDATE teams c SET standings_data = d.standings_data, "
            "standings_updated_at = d.standings_updated_at "
            "FROM teams d WHERE c.id = :canon AND d.id = :dup "
            "AND d.standings_data IS NOT NULL "
            "AND (c.standings_updated_at IS NULL "
            "OR d.standings_updated_at > c.standings_updated_at)"
        ),
        {"canon": CANON_ID, "dup": DUP_ID},
    )
    await session.execute(
        text(
            "UPDATE teams SET alternate_names = "
            "COALESCE(alternate_names, '[]'::jsonb) || jsonb_build_array(CAST(:alias AS text)) "
            "WHERE id = :canon AND NOT (COALESCE(alternate_names, '[]'::jsonb) "
            "@> jsonb_build_array(CAST(:alias AS text)))"
        ),
        {"canon": CANON_ID, "alias": DUP_NAME},
    )
    await session.execute(
        text(
            "INSERT INTO team_identity_mapping (team_id, source, source_id, source_name, sport_key) "
            # CASTs because :slug and :sport each bind twice, once against a
            # SELECT-list slot (text) and once against a varchar column; asyncpg
            # refuses to deduce two types for one parameter.
            "SELECT :canon, 'legacy_slug', CAST(:slug AS varchar), CAST(:name AS varchar), "
            "CAST(:sport AS varchar) WHERE NOT EXISTS ("
            "SELECT 1 FROM team_identity_mapping WHERE source = 'legacy_slug' "
            "AND source_id = CAST(:slug AS varchar) AND sport_key = CAST(:sport AS varchar))"
        ),
        {"canon": CANON_ID, "slug": LEGACY_SLUG, "name": DUP_NAME, "sport": SPORT_KEY},
    )
    await session.execute(text("DELETE FROM teams WHERE id = :dup"), {"dup": DUP_ID})
    return moved


async def _restore(session) -> dict[str, int]:
    if not await _backup_exists(session):
        return {"teams": 0, "repoints": 0}
    res = await session.execute(
        text(
            f"INSERT INTO teams SELECT * FROM {BACKUP_TEAMS} WHERE id = :dup "
            "AND id NOT IN (SELECT id FROM teams)"
        ),
        {"dup": DUP_ID},
    )
    teams_restored = res.rowcount

    repointed = 0
    for table, col in REPOINTS:
        # Only rows still on 10740: a row somebody has since moved elsewhere is
        # theirs, and the undo leaves it alone.
        res = await session.execute(
            text(
                f"UPDATE {table} SET {col} = :dup WHERE {col} = :canon AND id IN ("
                f"SELECT row_id FROM {BACKUP_REPOINTS} WHERE tbl = :tbl AND col = :col)"
            ),
            {"dup": DUP_ID, "canon": CANON_ID, "tbl": table, "col": col},
        )
        repointed += res.rowcount

    await session.execute(
        text(
            f"UPDATE teams c SET standings_data = b.standings_data, "
            "standings_updated_at = b.standings_updated_at, "
            "alternate_names = b.alternate_names "
            f"FROM {BACKUP_TEAMS} b WHERE c.id = :canon AND b.id = :canon"
        ),
        {"canon": CANON_ID},
    )
    await session.execute(
        text(
            "DELETE FROM team_identity_mapping WHERE source = 'legacy_slug' "
            "AND source_id = :slug AND sport_key = :sport AND team_id = :canon"
        ),
        {"slug": LEGACY_SLUG, "sport": SPORT_KEY, "canon": CANON_ID},
    )
    return {"teams": teams_restored, "repoints": repointed}


async def repair(session, mode: str) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        restored = await _restore(session)
        await session.commit()
        out.append(f"  restored teams: {restored['teams']}  repoints: {restored['repoints']}")
        return 0, out

    dup, canon = await _read_rows(session)
    if dup is None and canon is not None and await _backup_exists(session):
        out.append(f"already applied: {DUP_ID} is gone and {BACKUP_TEAMS} holds it.")
        return 0, out
    refusal = rows_refusal(dup, canon)
    if refusal:
        out.append(f"REFUSED: {refusal}")
        return 2, out
    counts = await _counts(session)
    for (t, c), n in counts.items():
        out.append(f"  {t}.{c:<16}: {n} (pinned {REPOINTS[(t, c)]})")
    refusal = counts_refusal(counts)
    if refusal:
        out.append(f"REFUSED: {refusal}")
        return 2, out
    if mode != "apply":
        out.append("\ndry run — nothing written.")
        return 0, out

    moved = await _apply(session)
    refusal = counts_refusal(moved)
    if refusal:
        await session.rollback()
        out.append(f"ROLLED BACK: repoint counts did not match — {refusal}")
        return 1, out
    left = await _counts(session)
    if any(left.values()):
        await session.rollback()
        out.append(f"ROLLED BACK: rows still name {DUP_ID} after the fold — {left}")
        return 1, out
    await session.commit()
    out.append(
        f"  folded {DUP_ID} into {CANON_ID}: {sum(moved.values())} references moved, "
        f"alias {DUP_NAME!r} added, legacy slug {LEGACY_SLUG!r} registered, {DUP_ID} deleted "
        f"(banked in {BACKUP_TEAMS} / {BACKUP_REPOINTS})"
    )
    out.append("\nundo: python3 scripts/repair_7021_fold_spaceless_cardinals.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#7021 fold {DUP_NAME!r} ({DUP_ID}) into {CANON_NAME!r} ({CANON_ID}) — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode)
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, fold, delete (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo from the banked rows")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
