"""#6974 (LAFC residual) — searching "lafc" shows one LAFC, and its page has every game.

THE SHIP: ``/search?q=lafc`` stops showing two LAFC cards (``13537 LAFC 11-8-9``
beside ``2326 Los Angeles FC 11-8-8``), and the one card it keeps leads to a
team page that carries the Oct 11 game at Vancouver. Today ``/api/teams/lafc``
(13537) shows 0 upcoming games, because that game (event 15316577) names only
2326.

WHAT EACH ROW IS, measured 2026-09-27 ~04:30Z
---------------------------------------------

* ``13537 LAFC`` is the club: ESPN 18966, the only ``espn`` mapping (6795166),
  the ESPN event rows since 8/16.
* ``2326 Los Angeles FC`` carries the same ESPN 18966, the same crest and the
  abbreviation LAFC. Every LAFC game since 8/16 is two event rows, one on each.
  The sportsbook/StatPal rows (and Oct 11's) name 2326. It FOLDS into 13537, with
  corrections first:

  - mapping 299 says the Odds API's MLS "FC Cincinnati" is this row. A plain fold
    would hand FC Cincinnati's sportsbook games to LAFC. It is repointed to
    FC Cincinnati's MLS row (29) before the fold;
  - 13 mappings name nothing LAFC is: three EPL-keyed rows (StatPal and
    Polymarket "Los Angeles FC", Kalshi EPL "Houston") and ten Polymarket
    market-title fragments ("Los Angeles FC - Exact Score", "... - FC Dallas
    Starting 11"). They are banked whole and deleted. Nothing mints a team on a
    mapping miss (``TeamIdentityService.resolve_team`` falls back to a fuzzy match
    and re-registers). So a title seen again lands on whichever club it
    fuzzy-matches, which after the fold is 13537;
  - its aliases include "Galaxy" and "LA Galaxy", which ``_apply_merge`` would
    union onto LAFC. Those are the other LA club's names. They are dropped.

  The three real mappings (Kalshi "Los Angeles F" / "Los Angeles FC", Polymarket
  MLS "Los Angeles FC") ride the fold to 13537.

NOT DONE HERE, said rather than implied: the paired event rows stay two rows for
one game. After the fold both rows name 13537 and the team rail's twin fold
shows each game once. ``2055 Inter Milan`` / ``13469 Internazionale`` is the same
shape and is not touched. 2326's entity (2018) goes NULL on the delete because
13537 already has one (``_apply_merge``'s one-entity-per-team rule).

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation).
Kalshi and Polymarket write to 2326 while an LAFC game is live, so run it outside
one (the next is 2026-10-11 02:30Z):

    python3 scripts/repair_6974_fold_lafc_duplicate_club.py            # dry run
    python3 scripts/repair_6974_fold_lafc_duplicate_club.py --apply    # bank, correct, fold
    python3 scripts/repair_6974_fold_lafc_duplicate_club.py --restore  # undo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from types import SimpleNamespace
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

PRODUCER_APP = "bainluck-heavy"
SPORT_KEY = "soccer_usa_mls"

#: Every foreign key onto ``teams.id`` in production (``pg_constraint``,
#: 2026-09-26), in the order ``Fold.refs`` pins them.
FK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("events", "home_team_id"),
    ("events", "away_team_id"),
    ("futures_outcomes", "team_id"),
    ("entities", "source_team_id"),
    ("team_identity_mapping", "team_id"),
    ("tournament_odds", "team_id"),
    ("user_favorites", "team_id"),
)


class Fold(NamedTuple):
    dup_id: int
    dup_name: str
    canon_id: int
    canon_name: str
    espn_id: str
    #: Rows naming the duplicate, in ``FK_COLUMNS`` order — zeros included.
    refs: tuple[int, int, int, int, int, int, int]
    #: The duplicate's aliases, exactly as read.
    aliases: tuple[str, ...]
    #: Aliases NOT carried onto the club (a name another club owns).
    drop_aliases: tuple[str, ...] = ()


class MappingEdit(NamedTuple):
    mapping_id: int
    source: str
    source_name: str
    from_team: int
    to_team: int
    to_name: str


class MappingRow(NamedTuple):
    """A mapping on the duplicate, pinned whole: deleted, or carried by the fold."""

    mapping_id: int
    source: str
    source_name: str
    sport_key: str


#: Read from production 2026-09-27 ~04:30Z. Counts are (home, away, futures,
#: entities, mappings, tournament_odds, favourites).
FOLDS: tuple[Fold, ...] = (
    Fold(
        2326, "Los Angeles FC", 13537, "LAFC", "18966", (21, 23, 0, 1, 17, 0, 0),
        ("Galaxy", "LA Galaxy", "LAFC"),
        drop_aliases=("Galaxy", "LA Galaxy"),
    ),
)

#: Applied BEFORE the fold, so the fold finds nothing left to move for them.
MAPPING_EDITS: tuple[MappingEdit, ...] = (
    MappingEdit(299, "odds_api", "FC Cincinnati", 2326, 29, "FC Cincinnati"),
)

#: Banked whole, then deleted, BEFORE the fold.
MAPPING_DELETES: tuple[MappingRow, ...] = (
    MappingRow(155748, "statpal", "Los Angeles FC", "soccer_epl"),
    MappingRow(158956, "polymarket", "Los Angeles FC - Halftime Result", "soccer_epl"),
    MappingRow(1021234, "kalshi", "Houston", "soccer_epl"),
    MappingRow(46904170, "polymarket", "Los Angeles FC - Exact Score", SPORT_KEY),
    MappingRow(46904200, "polymarket", "Los Angeles FC - First Team to Score", SPORT_KEY),
    MappingRow(46906008, "polymarket", "Los Angeles FC - Halftime Result", SPORT_KEY),
    MappingRow(46906010, "polymarket", "Los Angeles FC - Second Half Result", SPORT_KEY),
    MappingRow(46906120, "polymarket", "Los Angeles FC - Total Corners", SPORT_KEY),
    MappingRow(47159598, "polymarket", "Los Angeles FC - 1st Half Exact Score", SPORT_KEY),
    MappingRow(47159600, "polymarket", "Los Angeles FC - 2nd Half First Team to Score", SPORT_KEY),
    MappingRow(47159602, "polymarket", "Los Angeles FC - 1st Half First Team to Score", SPORT_KEY),
    MappingRow(50474306, "polymarket", "Los Angeles FC - Los Angeles FC Starting 11", SPORT_KEY),
    MappingRow(50474308, "polymarket", "Los Angeles FC - FC Dallas Starting 11", SPORT_KEY),
)

#: The duplicate's real mappings — the fold carries them onto the club.
MAPPING_KEEPS: tuple[MappingRow, ...] = (
    MappingRow(35107881, "kalshi", "Los Angeles F", SPORT_KEY),
    MappingRow(35307696, "kalshi", "Los Angeles FC", SPORT_KEY),
    MappingRow(38653470, "polymarket", "Los Angeles FC", SPORT_KEY),
)

BACKUP_TEAMS = "backup_6974lafc_teams"
BACKUP_REFS = "backup_6974lafc_refs"
BACKUP_MAPPINGS = "backup_6974lafc_mappings"


def all_team_ids() -> list[int]:
    ids = {f.dup_id for f in FOLDS} | {f.canon_id for f in FOLDS}
    ids |= {e.to_team for e in MAPPING_EDITS}
    return sorted(ids)


def deleted_ids() -> list[int]:
    return [d.mapping_id for d in MAPPING_DELETES]


def wrong_app_refusal() -> str | None:
    app = os.environ.get("HEROKU_APP_NAME")
    if app == PRODUCER_APP:
        return None
    return (
        f"refusing to run on HEROKU_APP_NAME={app!r}: this repair writes "
        f"production rows and runs only on {PRODUCER_APP!r}"
    )


def _aliases(value) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    return tuple(value)


def rows_refusal(rows: dict[int, dict], mappings: dict[int, dict]) -> str | None:
    """Every pinned row still says what it said when it was read."""
    for f in FOLDS:
        for label, tid, name in (("duplicate", f.dup_id, f.dup_name), ("club", f.canon_id, f.canon_name)):
            row = rows.get(tid)
            if row is None:
                return f"{label} row {tid} ({name!r}) is gone"
            if row["name"] != name:
                return f"{label} row {tid} is now named {row['name']!r}, expected {name!r}"
            if row["sport_key"] != SPORT_KEY:
                return f"{label} row {tid} is {row['sport_key']!r}, expected {SPORT_KEY!r}"
            if row["espn_id"] != f.espn_id:
                return f"{label} row {tid} carries espn_id {row['espn_id']!r}, expected {f.espn_id!r}"
        if _aliases(rows[f.dup_id]["alternate_names"]) != f.aliases:
            return (
                f"duplicate row {f.dup_id} aliases are {rows[f.dup_id]['alternate_names']!r}, "
                f"expected {list(f.aliases)!r}"
            )
    for e in MAPPING_EDITS:
        target = rows.get(e.to_team)
        if target is None or target["name"] != e.to_name or target["sport_key"] != SPORT_KEY:
            return f"mapping target {e.to_team} ({e.to_name!r}) is not the {SPORT_KEY} row it was"
        m = mappings.get(e.mapping_id)
        if m is None:
            return f"mapping {e.mapping_id} ({e.source} {e.source_name!r}) is gone"
        got = (m["source"], m["source_name"], m["sport_key"], m["team_id"])
        want = (e.source, e.source_name, SPORT_KEY, e.from_team)
        if got != want:
            return f"mapping {e.mapping_id} is now {got!r}, expected {want!r}"
    dup = FOLDS[0].dup_id
    for label, pins in (("deleted", MAPPING_DELETES), ("kept", MAPPING_KEEPS)):
        for p in pins:
            m = mappings.get(p.mapping_id)
            if m is None:
                return f"{label} mapping {p.mapping_id} ({p.source} {p.source_name!r}) is gone"
            got = (m["source"], m["source_name"], m["sport_key"], m["team_id"])
            want = (p.source, p.source_name, p.sport_key, dup)
            if got != want:
                return f"{label} mapping {p.mapping_id} is now {got!r}, expected {want!r}"
    return None


def counts_refusal(counts: dict[int, tuple[int, ...]]) -> str | None:
    """Exact pinned counts per duplicate, or refuse — a moved count means another writer."""
    drift = []
    for f in FOLDS:
        got = counts.get(f.dup_id)
        if got != f.refs:
            moved = [
                f"{t}.{c} {g} (pinned {p})"
                for (t, c), g, p in zip(FK_COLUMNS, got or (None,) * len(FK_COLUMNS), f.refs)
                if g != p
            ]
            drift.append(f"{f.dup_id} {f.dup_name!r}: " + ", ".join(moved))
    return "population moved — " + "; ".join(drift) if drift else None


async def _read_rows(session) -> dict[int, dict]:
    res = await session.execute(
        text(
            "SELECT t.id, t.name, t.espn_id, t.slug, t.alternate_names, s.key AS sport_key "
            "FROM teams t LEFT JOIN sports s ON s.id = t.sport_id "
            "WHERE t.id = ANY(:ids)"
        ),
        {"ids": all_team_ids()},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _read_mappings(session) -> dict[int, dict]:
    ids = [e.mapping_id for e in MAPPING_EDITS]
    ids += [p.mapping_id for p in MAPPING_DELETES + MAPPING_KEEPS]
    res = await session.execute(
        text(
            "SELECT id, source, source_name, sport_key, team_id "
            "FROM team_identity_mapping WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _counts(session) -> dict[int, tuple[int, ...]]:
    dups = [f.dup_id for f in FOLDS]
    per_col = []
    for table, col in FK_COLUMNS:
        res = await session.execute(
            text(
                f"SELECT {col} AS tid, count(*) AS n FROM {table} "
                f"WHERE {col} = ANY(:ids) GROUP BY {col}"
            ),
            {"ids": dups},
        )
        per_col.append({r.tid: int(r.n) for r in res})
    return {d: tuple(col.get(d, 0) for col in per_col) for d in dups}


async def _slug_collisions(session, rows: dict[int, dict]) -> list[str]:
    """``_apply_merge`` INSERTs a legacy_slug mapping per duplicate; the two partial
    unique indexes on ``team_identity_mapping`` would abort the whole fold."""
    out = []
    for f in FOLDS:
        slug = rows[f.dup_id]["slug"]
        res = await session.execute(
            text(
                "SELECT id FROM team_identity_mapping WHERE source = 'legacy_slug' "
                "AND sport_key = :sk AND (source_id = :slug OR source_name = :name)"
            ),
            {"sk": SPORT_KEY, "slug": slug, "name": f.dup_name},
        )
        hit = res.first()
        if hit is not None:
            out.append(f"{f.dup_id} slug {slug!r}/{f.dup_name!r} already mapped (row {hit.id})")
    return out


async def _backup_exists(session) -> bool:
    res = await session.execute(text("SELECT to_regclass(:t)"), {"t": BACKUP_TEAMS})
    return res.scalar_one() is not None


_BANK_REF = (
    # CASTs because :dup binds twice — once in the SELECT list, once against an
    # int column — and asyncpg refuses to deduce two types for one parameter.
    "INSERT INTO {bk} (tbl, col, row_id, from_team, to_team) "
    "SELECT CAST(:tbl AS text), CAST(:col AS text), id, "
    "CAST(:dup AS bigint), CAST(:canon AS bigint) FROM {table} "
    "WHERE {col} = CAST(:dup AS bigint) {extra}"
    "AND NOT EXISTS (SELECT 1 FROM {bk} b "
    "WHERE b.tbl = CAST(:tbl AS text) AND b.col = CAST(:col AS text) "
    "AND b.row_id = {table}.id)"
)


async def _bank(session) -> None:
    # First pre-image wins: a second run never overwrites what was banked.
    await session.execute(
        text(f"CREATE TABLE IF NOT EXISTS {BACKUP_TEAMS} AS SELECT * FROM teams WHERE FALSE")
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_TEAMS} SELECT * FROM teams WHERE id = ANY(:ids) "
            f"AND id NOT IN (SELECT id FROM {BACKUP_TEAMS})"
        ),
        {"ids": all_team_ids()},
    )
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_MAPPINGS} AS "
            "SELECT * FROM team_identity_mapping WHERE FALSE"
        )
    )
    await session.execute(
        text(
            f"INSERT INTO {BACKUP_MAPPINGS} SELECT * FROM team_identity_mapping "
            f"WHERE id = ANY(:ids) AND id NOT IN (SELECT id FROM {BACKUP_MAPPINGS})"
        ),
        {"ids": deleted_ids()},
    )
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_REFS} (tbl text NOT NULL, col text NOT NULL, "
            "row_id bigint NOT NULL, from_team bigint NOT NULL, to_team bigint NOT NULL)"
        )
    )
    # The mapping edits bank first, naming THEIR destination, so the fold's own
    # banking below skips those rows (NOT EXISTS) instead of naming the club.
    for e in MAPPING_EDITS:
        await session.execute(
            text(
                _BANK_REF.format(
                    bk=BACKUP_REFS, table="team_identity_mapping", col="team_id",
                    extra="AND id = CAST(:mid AS bigint) ",
                )
            ),
            {"tbl": "team_identity_mapping", "col": "team_id", "dup": e.from_team,
             "canon": e.to_team, "mid": e.mapping_id},
        )
    for f in FOLDS:
        for table, col in FK_COLUMNS:
            params = {"tbl": table, "col": col, "dup": f.dup_id, "canon": f.canon_id}
            extra = ""
            if table == "team_identity_mapping":
                # A deleted mapping lives in BACKUP_MAPPINGS whole; it moves nowhere.
                extra = "AND id <> ALL(CAST(:deleted AS bigint[])) "
                params["deleted"] = deleted_ids()
            await session.execute(
                text(_BANK_REF.format(bk=BACKUP_REFS, table=table, col=col, extra=extra)),
                params,
            )


async def _apply(session, rows: dict[int, dict]) -> list[str]:
    from app.utils.team_merge import _apply_merge

    out = []
    await _bank(session)

    for e in MAPPING_EDITS:
        res = await session.execute(
            text(
                "UPDATE team_identity_mapping SET team_id = :to, updated_at = now() "
                "WHERE id = :id AND team_id = :frm"
            ),
            {"to": e.to_team, "id": e.mapping_id, "frm": e.from_team},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"mapping edit {e.mapping_id} touched {res.rowcount} rows")
        out.append(
            f"  mapping {e.mapping_id} {e.source} {e.source_name!r}: {e.from_team} -> {e.to_team}"
        )

    res = await session.execute(
        text("DELETE FROM team_identity_mapping WHERE id = ANY(:ids) AND team_id = :dup"),
        {"ids": deleted_ids(), "dup": FOLDS[0].dup_id},
    )
    if res.rowcount != len(MAPPING_DELETES):
        raise RuntimeError(f"mapping delete touched {res.rowcount} rows, expected {len(MAPPING_DELETES)}")
    out.append(f"  deleted {res.rowcount} mappings (banked in {BACKUP_MAPPINGS})")

    for f in FOLDS:
        dup = rows[f.dup_id]
        drop = {a.strip().lower() for a in f.drop_aliases}
        stub = SimpleNamespace(
            id=f.dup_id,
            name=f.dup_name,
            slug=dup["slug"],
            alternate_names=[a for a in f.aliases if a.strip().lower() not in drop],
        )
        canon = SimpleNamespace(
            id=f.canon_id,
            name=f.canon_name,
            alternate_names=list(_aliases(rows[f.canon_id]["alternate_names"]) or []),
        )
        evidence = await _apply_merge(session, canon, stub, SPORT_KEY)
        out.append(f"  folded {f.dup_id} {f.dup_name!r} -> {f.canon_id}: {evidence['fk_repointed']}")
    return out


async def _refs_landed(session) -> str | None:
    """Every banked reference now names its destination — except an entity whose
    club already had one, which ``_apply_merge`` leaves to go NULL on the delete."""
    res = await session.execute(
        text(f"SELECT tbl, col, row_id, from_team, to_team FROM {BACKUP_REFS}")
    )
    for r in res.all():
        cur = await session.execute(
            text(f"SELECT {r.col} FROM {r.tbl} WHERE id = :id"), {"id": r.row_id}
        )
        now = cur.scalar_one_or_none()
        if now == r.to_team or (r.tbl == "entities" and now is None):
            continue
        return f"{r.tbl}.{r.col} row {r.row_id} names {now}, expected {r.to_team}"
    return None


async def _restore(session) -> dict[str, int]:
    if not await _backup_exists(session):
        return {"teams": 0, "mappings": 0, "refs": 0, "slugs": 0}
    dups = [f.dup_id for f in FOLDS]
    res = await session.execute(
        text(
            f"INSERT INTO teams SELECT * FROM {BACKUP_TEAMS} WHERE id = ANY(:dups) "
            "AND id NOT IN (SELECT id FROM teams)"
        ),
        {"dups": dups},
    )
    teams_restored = res.rowcount

    # After the team, which they reference. A (source, name) a writer has since
    # re-registered elsewhere keeps the writer's row: DO NOTHING on any unique hit.
    res = await session.execute(
        text(
            f"INSERT INTO team_identity_mapping SELECT * FROM {BACKUP_MAPPINGS} "
            "WHERE id NOT IN (SELECT id FROM team_identity_mapping) ON CONFLICT DO NOTHING"
        )
    )
    mappings_restored = res.rowcount

    refs = 0
    for table, col in FK_COLUMNS:
        # Only rows still where the repair put them (or, for an entity, still
        # unlinked): a row somebody has since moved elsewhere is theirs.
        null_arm = f" OR t.{col} IS NULL" if table == "entities" else ""
        res = await session.execute(
            text(
                f"UPDATE {table} t SET {col} = b.from_team FROM {BACKUP_REFS} b "
                f"WHERE b.tbl = :tbl AND b.col = :col AND b.row_id = t.id "
                f"AND (t.{col} = b.to_team{null_arm})"
            ),
            {"tbl": table, "col": col},
        )
        refs += res.rowcount

    res = await session.execute(
        text(
            f"DELETE FROM team_identity_mapping m USING {BACKUP_TEAMS} b "
            "WHERE m.source = 'legacy_slug' AND m.sport_key = :sk "
            "AND b.id = ANY(:dups) AND m.source_id = b.slug"
        ),
        {"sk": SPORT_KEY, "dups": dups},
    )
    slugs = res.rowcount

    # A club only ever gained aliases.
    canons = sorted({f.canon_id for f in FOLDS})
    await session.execute(
        text(
            f"UPDATE teams t SET alternate_names = b.alternate_names FROM {BACKUP_TEAMS} b "
            "WHERE t.id = b.id AND t.id = ANY(:ids)"
        ),
        {"ids": canons},
    )
    return {"teams": teams_restored, "mappings": mappings_restored, "refs": refs, "slugs": slugs}


async def repair(session, mode: str) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        restored = await _restore(session)
        await session.commit()
        out.append(
            f"  restored teams: {restored['teams']}  mappings: {restored['mappings']}  "
            f"refs: {restored['refs']}  legacy slugs removed: {restored['slugs']}"
        )
        return 0, out

    rows = await _read_rows(session)
    if all(f.dup_id not in rows for f in FOLDS) and await _backup_exists(session):
        out.append(f"already applied: every duplicate is gone and {BACKUP_TEAMS} holds them.")
        return 0, out
    refusal = rows_refusal(rows, await _read_mappings(session))
    if refusal:
        out.append(f"REFUSED: {refusal}")
        return 2, out
    counts = await _counts(session)
    for f in FOLDS:
        out.append(f"  {f.dup_id:>6} {f.dup_name!r:<16} -> {f.canon_id:>5}  refs {counts[f.dup_id]}")
    refusal = counts_refusal(counts)
    if refusal:
        out.append(f"REFUSED: {refusal}")
        return 2, out
    collisions = await _slug_collisions(session, rows)
    if collisions:
        out.append("REFUSED: legacy slug already mapped — " + "; ".join(collisions))
        return 2, out
    if mode != "apply":
        out.append(
            f"\ndry run — nothing written. Would repoint {len(MAPPING_EDITS)} mapping, "
            f"delete {len(MAPPING_DELETES)}, fold {len(FOLDS)} (carrying {len(MAPPING_KEEPS)})."
        )
        return 0, out

    try:
        out.extend(await _apply(session, rows))
    except Exception as exc:  # one transaction: any failure undoes all of it
        await session.rollback()
        out.append(f"ROLLED BACK: {exc}")
        return 1, out
    left = await _counts(session)
    if any(any(v) for v in left.values()):
        await session.rollback()
        out.append(f"ROLLED BACK: rows still name a duplicate after the fold — {left}")
        return 1, out
    stray = await _refs_landed(session)
    if stray:
        await session.rollback()
        out.append(f"ROLLED BACK: {stray}")
        return 1, out
    await session.commit()
    out.append(
        f"\n  applied: {len(MAPPING_EDITS)} mapping repointed, {len(MAPPING_DELETES)} deleted, "
        f"{len(FOLDS)} folded (banked in {BACKUP_TEAMS} / {BACKUP_REFS} / {BACKUP_MAPPINGS})"
    )
    out.append("undo: python3 scripts/repair_6974_fold_lafc_duplicate_club.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#6974 LAFC duplicate club — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode)
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, correct, fold (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo from the banked rows")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
