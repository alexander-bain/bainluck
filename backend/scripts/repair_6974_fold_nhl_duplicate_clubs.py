"""#6974 (NHL residual) — searching "rangers" or "islanders" leads with the real club.

THE SHIP: ``/search?q=rangers`` stops leading its TEAMS block with "New York R
28-33-8" above the real New York Rangers, and ``/search?q=islanders`` stops
leading with "New Jersey 42-27-5" and "New York I 39-26-5" above the real New
York Islanders. The NHL season opens 2026-10-07.

WHAT A READER SEES (production, 2026-09-26 ~13:20Z)
---------------------------------------------------

``GET /api/events/search?q=rangers`` → ``teams``::

    8293  New York R          icehockey_nhl  28-33-8   <- a duplicate, first
      57  New York Rangers    icehockey_nhl  1-2-0

``GET /api/events/search?q=islanders`` → ``teams``::

    12716 New Jersey          icehockey_nhl  42-27-5   <- wears the Islanders' identity
     6181 New York I          icehockey_nhl  39-26-5   <- a duplicate
       54 New York Islanders  icehockey_nhl  1-1-0

WHAT EACH ROW IS, measured the same morning
-------------------------------------------

* ``8293 New York R`` shares the Rangers' ``espn_id`` 13, crest and full name.
  Every one of its 36 futures legs is a Rangers leg (the club, or a Rangers
  player: Fox, Shesterkin, Zibanejad, Trocheck, Lafrenière, Perreault, Miller,
  Quick). Its three events are closed March rows, each a second row for a game
  the Rangers' own row already carries at the same minute. It FOLDS into 57.
* ``6181 New York I`` shares the Islanders' ``espn_id`` 12. One closed March
  event, same shape. It FOLDS into 54 — with two corrections first:
  - its one ``team_identity_mapping`` row says Kalshi's NHL "Columbus" is this
    row. A plain fold would hand that mapping to the Islanders. The row is
    repointed to the Columbus Blue Jackets (572) before the fold;
  - its aliases include the bare city "New York", which ``_apply_merge`` would
    union onto the Islanders — a name the Rangers own just as much. It is dropped.
* ``12716 New Jersey`` is NOT folded. Every identity column says Islanders
  (``espn_id`` 12, ``NYI``, crest, "New York Islanders" alias) while its events
  and legs split across the Islanders, the Devils and a Blues player (#6974
  comment 2026-09-19). Folding it into either club binds the other club's rows
  wrongly. It is STRIPPED like the MLS repair's borrowed-identity rows: the
  identity columns go NULL, the name stays, and nothing is repointed. That is
  also what stops a writer resolving "New York Islanders" onto it (it holds two
  open Islanders player legs written this month).

NOT DONE HERE, said rather than implied: ``12716``'s own 20 legs and 3 events
stay where they are; ``12649 Los Angeles C`` (NBA) is a catch-all for Lakers,
LAFC, Galaxy and Kings legs and needs a leg-by-leg repair, not a fold. The
repointed March events stay second rows for their games, as they already are;
no team-page rail reaches March (the recent rail looks back 30 days).

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_6974_fold_nhl_duplicate_clubs.py            # dry run
    python3 scripts/repair_6974_fold_nhl_duplicate_clubs.py --apply    # bank, strip, fold
    python3 scripts/repair_6974_fold_nhl_duplicate_clubs.py --restore  # undo
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
SPORT_KEY = "icehockey_nhl"

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

#: The MLS repair's strip set: ``espn_sync``'s ``ESPN_SOURCED_IDENTITY_FIELDS``
#: (#6215) plus the id and the full-size logo.
STRIP_FIELDS: tuple[str, ...] = (
    "espn_id",
    "logo_url",
    "logo_url_small",
    "logo_url_large",
    "primary_color",
    "secondary_color",
    "alternate_names",
    "abbreviation",
    "current_record",
    "location",
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
    #: Aliases NOT carried onto the club (a name another club owns too).
    drop_aliases: tuple[str, ...] = ()


class Strip(NamedTuple):
    team_id: int
    name: str
    espn_id: str | None
    logo_url_small: str
    aliases: tuple[str, ...]


class MappingEdit(NamedTuple):
    mapping_id: int
    source: str
    source_name: str
    from_team: int
    to_team: int
    to_name: str


def _crest(abbr: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/nhl/500/scoreboard/{abbr}.png"


#: Read from production 2026-09-26 ~13:20Z. Counts are (home, away, futures,
#: entities, mappings, tournament_odds, favourites).
FOLDS: tuple[Fold, ...] = (
    Fold(
        8293, "New York R", 57, "New York Rangers", "13", (1, 2, 36, 1, 0, 0, 0),
        ("Rangers", "New York Rangers"),
    ),
    Fold(
        6181, "New York I", 54, "New York Islanders", "12", (1, 0, 0, 1, 1, 0, 0),
        ("New York Islanders", "Islanders", "New York"),
        drop_aliases=("New York",),
    ),
)

STRIPS: tuple[Strip, ...] = (
    Strip(12716, "New Jersey", "12", _crest("nyi"), ("New York Islanders", "Islanders")),
)

#: Applied BEFORE the folds, so the fold finds nothing left to move for them.
MAPPING_EDITS: tuple[MappingEdit, ...] = (
    MappingEdit(156487, "kalshi", "Columbus", 6181, 572, "Columbus Blue Jackets"),
)

BACKUP_TEAMS = "backup_6974nhl_teams"
BACKUP_REFS = "backup_6974nhl_refs"


def all_team_ids() -> list[int]:
    ids = {f.dup_id for f in FOLDS} | {f.canon_id for f in FOLDS}
    ids |= {s.team_id for s in STRIPS} | {e.to_team for e in MAPPING_EDITS}
    return sorted(ids)


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
    for s in STRIPS:
        row = rows.get(s.team_id)
        if row is None:
            return f"strip row {s.team_id} ({s.name!r}) is gone"
        if row["name"] != s.name or row["sport_key"] != SPORT_KEY:
            return f"strip row {s.team_id} is now {row['name']!r} / {row['sport_key']!r}"
        if row["espn_id"] != s.espn_id:
            return f"strip row {s.team_id} carries espn_id {row['espn_id']!r}, expected {s.espn_id!r}"
        if row["logo_url_small"] != s.logo_url_small:
            return f"strip row {s.team_id} crest is {row['logo_url_small']!r}, expected {s.logo_url_small!r}"
        if _aliases(row["alternate_names"]) != s.aliases:
            return f"strip row {s.team_id} aliases are {row['alternate_names']!r}, expected {list(s.aliases)!r}"
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
            "SELECT t.id, t.name, t.espn_id, t.slug, t.logo_url_small, "
            "t.alternate_names, s.key AS sport_key "
            "FROM teams t LEFT JOIN sports s ON s.id = t.sport_id "
            "WHERE t.id = ANY(:ids)"
        ),
        {"ids": all_team_ids()},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _read_mappings(session) -> dict[int, dict]:
    res = await session.execute(
        text(
            "SELECT id, source, source_name, sport_key, team_id "
            "FROM team_identity_mapping WHERE id = ANY(:ids)"
        ),
        {"ids": [e.mapping_id for e in MAPPING_EDITS]},
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
            await session.execute(
                text(_BANK_REF.format(bk=BACKUP_REFS, table=table, col=col, extra="")),
                {"tbl": table, "col": col, "dup": f.dup_id, "canon": f.canon_id},
            )


async def _apply(session, rows: dict[int, dict]) -> list[str]:
    from app.utils.team_merge import _apply_merge

    out = []
    await _bank(session)

    nulls = ", ".join(f"{c} = NULL" for c in STRIP_FIELDS)
    for s in STRIPS:
        res = await session.execute(
            text(f"UPDATE teams SET {nulls} WHERE id = :id AND name = :name"),
            {"id": s.team_id, "name": s.name},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"strip {s.team_id} touched {res.rowcount} rows")
        out.append(f"  stripped borrowed identity from {s.team_id} {s.name!r}")

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
        return {"teams": 0, "refs": 0, "slugs": 0}
    dups = [f.dup_id for f in FOLDS]
    res = await session.execute(
        text(
            f"INSERT INTO teams SELECT * FROM {BACKUP_TEAMS} WHERE id = ANY(:dups) "
            "AND id NOT IN (SELECT id FROM teams)"
        ),
        {"dups": dups},
    )
    teams_restored = res.rowcount

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

    # A club only ever gained aliases; a stripped row gets its whole identity back.
    canons = sorted({f.canon_id for f in FOLDS})
    await session.execute(
        text(
            f"UPDATE teams t SET alternate_names = b.alternate_names FROM {BACKUP_TEAMS} b "
            "WHERE t.id = b.id AND t.id = ANY(:ids)"
        ),
        {"ids": canons},
    )
    sets = ", ".join(f"{c} = b.{c}" for c in STRIP_FIELDS)
    await session.execute(
        text(f"UPDATE teams t SET {sets} FROM {BACKUP_TEAMS} b WHERE t.id = b.id AND t.id = ANY(:ids)"),
        {"ids": [s.team_id for s in STRIPS]},
    )
    return {"teams": teams_restored, "refs": refs, "slugs": slugs}


async def repair(session, mode: str) -> tuple[int, list[str]]:
    """``mode`` is ``dry``, ``apply`` or ``restore``. Returns (exit code, lines).

    Commits only on a clean apply or restore; every refusal writes nothing.
    """
    out: list[str] = []
    if mode == "restore":
        restored = await _restore(session)
        await session.commit()
        out.append(
            f"  restored teams: {restored['teams']}  refs: {restored['refs']}  "
            f"legacy slugs removed: {restored['slugs']}"
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
        out.append(f"  {f.dup_id:>6} {f.dup_name!r:<14} -> {f.canon_id:>5}  refs {counts[f.dup_id]}")
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
            f"\ndry run — nothing written. Would strip {len(STRIPS)}, repoint "
            f"{len(MAPPING_EDITS)} mapping, fold {len(FOLDS)}."
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
        f"\n  applied: {len(STRIPS)} stripped, {len(MAPPING_EDITS)} mapping repointed, "
        f"{len(FOLDS)} folded (banked in {BACKUP_TEAMS} / {BACKUP_REFS})"
    )
    out.append("undo: python3 scripts/repair_6974_fold_nhl_duplicate_clubs.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#6974 NHL duplicate clubs — {mode.upper()}")
    async with get_task_session() as session:
        code, lines = await repair(session, mode)
    for line in lines:
        print(line)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--apply", action="store_true", help="bank, strip, fold (default: dry run)")
    group.add_argument("--restore", action="store_true", help="undo from the banked rows")
    args = parser.parse_args()
    mode = "restore" if args.restore else ("apply" if args.apply else "dry")
    return asyncio.run(run(mode))


if __name__ == "__main__":
    raise SystemExit(main())
