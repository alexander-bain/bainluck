"""#6974 — an MLS card shows its own club's record and crest, not a duplicate's.

THE SHIP: tonight's Seattle–Real Salt Lake hero stops reading "SEA 1-0-1 /
RSL 3-1-1" (the real records are 7-8-9 and 8-5-12), a search for "Salt Lake"
stops offering two RSL team cards, and Atlanta United's card stops wearing
Inter Miami's crest.

WHAT A READER SEES (production, 2026-09-24 ~00:30Z)
---------------------------------------------------

``/api/events?sport=soccer_usa_mls`` served 16 upcoming fixtures. **15 of their
32 team sides were painted from the wrong ``teams`` row**:

* twelve from a city-only duplicate of the club — ``Seattle`` (3644) 1-0-1,
  ``Salt Lake`` (3643) 3-1-1, ``Philadelphia`` (5221) 0-0-5, ``Orlando`` (6688)
  0-0-3, ``Colorado``, ``Dallas``, ``Kansas City``, ``Austin``, ``Charlotte``,
  ``Cincinnati``, ``Los Angeles G`` — each a March snapshot of a record;
* three from a RESERVE club wearing the first team's ESPN identity — "New York
  City FC" painted as ``New York Red Bulls II``, "Portland Timbers" as
  ``Portland Timbers 2``, "San Jose Earthquakes" as ``San Jose Earthquakes II``;
* "Atlanta United FC" painted as ``Inter Miami CF`` (crest and record), because
  Inter Miami's row carries ``Atlanta United FC`` as an alternate name.

The event rows themselves are right — 15313874 is home 2327 / away 24, the real
clubs. The card's team is chosen at serve time by NAME
(``routes/events.py::_team_for_event``), and every duplicate carries the real
club's full name in ``alternate_names``, so the name has two same-league
answers and #7132's preference picks the duplicate (it has a record; neither has
a standings board). A local run of the real ``_dedupe_team_name_lookup`` over
all 1,640 enriched production rows reproduces all 15, plus 5 more spellings the
Odds API also uses ("Columbus Crew", "Red Bull New York", "Houston Dynamo FC",
"CF Montréal", "LAFC"): **20 of 35 names wrong before, 0 after this repair,
and no key outside ``soccer_usa_mls`` changes.**

WHY A SCRIPT, AND WHY NOT THE EXISTING MERGE
--------------------------------------------

The writer is already fixed. ``espn_helpers.upsert_team`` stopped borrowing a
payload whose names do not correspond in #6215 / #7419, and every duplicate here
is older than that (the last event bound to one is 2026-09-10). These are the
rows it already wrote.

``app.utils.team_merge`` (#1204) folds exactly this class — its docstring names
"Philadelphia (MLS)" — and its fold (``_apply_merge``) is what this script
calls. Its PLANNER reaches only six of these pairs: "Salt Lake" is not a token
prefix of "Real Salt Lake", "Dallas" is not of "FC Dallas", and a duplicate with
one ``team_identity_mapping`` row is "not a clean stub". Worse, one of the six
it does plan is wrong — it would fold ``San Jose Earthquakes II`` (a different
club) into San Jose Earthquakes, because "X II" passes the prefix test. The
commit carrying this script closes that hole in the planner. This script does
not generalise the planner; it applies a pinned, reviewed list.

WHAT THIS DOES, in one transaction, after banking every row it touches
----------------------------------------------------------------------

1. ``STRIPS``: clears the borrowed ESPN identity (the #6215 field set, plus
   ``espn_id`` and ``logo_url``) from six rows that are NOT the club whose crest
   they wear — the four reserve sides, ``La Calamine`` (a Belgian club filed as
   MLS) and ``Los Angeles FC`` (2326), which wears the LA GALAXY crest
   (``names_match('Los Angeles FC', 'LA Galaxy')`` is True — see
   ``espn_helpers._sole_named_candidate``). Their names stay.
2. ``ALIAS_EDITS``: Inter Miami loses ``Atlanta United FC`` / ``Atlanta``; LAFC
   (13537, the row holding LAFC's real ESPN identity) gains ``Los Angeles FC``, so
   a card for "Los Angeles FC" paints LAFC's crest instead of the Galaxy's.
3. ``FOLDS``: 21 same-club duplicates (same ``espn_id`` as the real club) fold
   into the real club through ``team_merge._apply_merge`` — every foreign key
   repointed, the duplicate's names added to the club's ``alternate_names``, its
   slug registered as a ``legacy_slug`` so the old URL still opens the club, the
   row deleted. Each duplicate's reference count is pinned per foreign key.

NOT DONE HERE, said rather than implied: the two LAFC rows (2326 and 13537) are
still two rows. Both are bound to live fixtures from different writers, so a
pinned count would move before an attended apply; after this repair 2326 no
longer wears the Galaxy crest and every "Los Angeles FC" card paints LAFC. The
registry ``entities`` row of a duplicate whose club already has one is left
with ``source_team_id`` NULL — ``_apply_merge``'s own rule (one entity per team);
it is banked, and the undo re-links it.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_6974_fold_mls_duplicate_clubs.py            # dry run
    python3 scripts/repair_6974_fold_mls_duplicate_clubs.py --apply    # bank, strip, fold
    python3 scripts/repair_6974_fold_mls_duplicate_clubs.py --restore  # undo
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
#: 2026-09-24), in the order ``Fold.refs`` pins them.
FK_COLUMNS: tuple[tuple[str, str], ...] = (
    ("events", "home_team_id"),
    ("events", "away_team_id"),
    ("futures_outcomes", "team_id"),
    ("entities", "source_team_id"),
    ("team_identity_mapping", "team_id"),
    ("tournament_odds", "team_id"),
    ("user_favorites", "team_id"),
)

#: The identity columns a borrowed ESPN match writes. ``espn_sync``'s
#: ``ESPN_SOURCED_IDENTITY_FIELDS`` (#6215) plus the id and the full-size logo,
#: which a row that was never this club's must not keep either.
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


class Strip(NamedTuple):
    team_id: int
    name: str
    espn_id: str | None
    logo_url_small: str
    aliases: tuple[str, ...]


class AliasEdit(NamedTuple):
    team_id: int
    name: str
    before: tuple[str, ...] | None
    after: tuple[str, ...]


def _crest(espn_team_id: str) -> str:
    return f"https://a.espncdn.com/i/teamlogos/soccer/500/{espn_team_id}.png"


#: Read from production 2026-09-24 ~00:40Z. Every duplicate shares the club's
#: ``espn_id``; the counts are (home, away, futures, entities, mappings,
#: tournament_odds, favourites).
FOLDS: tuple[Fold, ...] = (
    Fold(5221, "Philadelphia", 32, "Philadelphia Union", "10739", (3, 0, 0, 1, 0, 0, 0)),
    Fold(6688, "Orlando", 33, "Orlando City SC", "12011", (0, 1, 0, 1, 0, 0, 0)),
    Fold(5222, "New York City", 2323, "New York City FC", "17606", (2, 1, 0, 0, 0, 0, 0)),
    Fold(8031, "Cincinnati", 29, "FC Cincinnati", "18267", (2, 1, 0, 1, 0, 0, 0)),
    Fold(6698, "Columbus", 22, "Columbus Crew SC", "183", (2, 1, 0, 1, 0, 0, 0)),
    Fold(3645, "Colorado", 2328, "Colorado Rapids", "184", (1, 1, 0, 1, 1, 0, 0)),
    Fold(8787, "Dallas", 17, "FC Dallas", "185", (1, 0, 0, 1, 0, 0, 0)),
    Fold(6692, "Kansas City", 26, "Sporting Kansas City", "186", (1, 0, 0, 1, 0, 0, 0)),
    Fold(12617, "Los Angeles G", 2325, "LA Galaxy", "187", (0, 1, 1, 1, 1, 0, 0)),
    Fold(10706, "New York", 34, "New York Red Bulls", "190", (0, 1, 3, 1, 0, 0, 0)),
    Fold(14179, "Red Bull New York", 34, "New York Red Bulls", "190", (2, 2, 0, 1, 0, 0, 0)),
    Fold(6695, "San Jose", 25, "San Jose Earthquakes", "191", (0, 2, 7, 1, 0, 0, 0)),
    Fold(6697, "Austin", 13, "Austin FC", "20906", (0, 1, 0, 1, 0, 0, 0)),
    Fold(6696, "Charlotte", 28, "Charlotte FC", "21300", (2, 0, 0, 1, 0, 0, 0)),
    Fold(3643, "Salt Lake", 24, "Real Salt Lake", "4771", (1, 1, 0, 1, 2, 0, 0)),
    Fold(6690, "Houston", 15, "Houston Dynamo", "6077", (0, 1, 0, 1, 0, 0, 0)),
    Fold(13902, "Houston Dynamo FC", 15, "Houston Dynamo", "6077", (1, 4, 0, 1, 0, 0, 0)),
    Fold(11692, "Montreal", 186, "CF Montreal", "9720", (0, 1, 0, 1, 0, 0, 0)),
    Fold(13900, "CF Montréal", 186, "CF Montreal", "9720", (3, 1, 0, 1, 0, 0, 0)),
    Fold(3646, "Portland", 21, "Portland Timbers", "9723", (2, 1, 0, 1, 1, 0, 0)),
    Fold(3644, "Seattle", 2327, "Seattle Sounders FC", "9726", (0, 1, 0, 1, 1, 0, 0)),
)

STRIPS: tuple[Strip, ...] = (
    Strip(14534, "New York Red Bulls II", "17606", _crest("17606"), ("New York City FC", "NYCFC")),
    Strip(14535, "Columbus Crew 2", "183", _crest("183"), ("Columbus", "Columbus Crew")),
    Strip(15119, "Portland Timbers 2", "9723", _crest("9723"), ("Portland", "Portland Timbers")),
    Strip(
        15120, "San Jose Earthquakes II", "191", _crest("191"), ("San Jose", "San Jose Earthquakes")
    ),
    Strip(4712, "La Calamine", None, _crest("187"), ("Galaxy", "LA Galaxy")),
    Strip(2326, "Los Angeles FC", None, _crest("187"), ("Galaxy", "LA Galaxy")),
)

ALIAS_EDITS: tuple[AliasEdit, ...] = (
    AliasEdit(2324, "Inter Miami CF", ("Atlanta United FC", "Atlanta", "Miami"), ("Miami",)),
    AliasEdit(13537, "LAFC", None, ("Los Angeles FC",)),
)

BACKUP_TEAMS = "backup_6974_teams"
BACKUP_REFS = "backup_6974_refs"


def all_team_ids() -> list[int]:
    ids = {f.dup_id for f in FOLDS} | {f.canon_id for f in FOLDS}
    ids |= {s.team_id for s in STRIPS} | {a.team_id for a in ALIAS_EDITS}
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


def rows_refusal(rows: dict[int, dict]) -> str | None:
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
    for a in ALIAS_EDITS:
        row = rows.get(a.team_id)
        if row is None:
            return f"alias row {a.team_id} ({a.name!r}) is gone"
        if row["name"] != a.name or row["sport_key"] != SPORT_KEY:
            return f"alias row {a.team_id} is now {row['name']!r} / {row['sport_key']!r}"
        if _aliases(row["alternate_names"]) != a.before:
            return (
                f"alias row {a.team_id} aliases are {row['alternate_names']!r}, "
                f"expected {None if a.before is None else list(a.before)!r}"
            )
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
    for f in FOLDS:
        for table, col in FK_COLUMNS:
            # CASTs because :dup binds twice — once in the SELECT list, once
            # against an int column — and asyncpg refuses to deduce two types for
            # one parameter (the real-PG gate caught it; #7021's did the same).
            await session.execute(
                text(
                    f"INSERT INTO {BACKUP_REFS} (tbl, col, row_id, from_team, to_team) "
                    f"SELECT CAST(:tbl AS text), CAST(:col AS text), id, "
                    f"CAST(:dup AS bigint), CAST(:canon AS bigint) FROM {table} "
                    f"WHERE {col} = CAST(:dup AS bigint) "
                    f"AND NOT EXISTS (SELECT 1 FROM {BACKUP_REFS} b "
                    f"WHERE b.tbl = CAST(:tbl AS text) AND b.col = CAST(:col AS text) "
                    f"AND b.row_id = {table}.id)"
                ),
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

    for a in ALIAS_EDITS:
        res = await session.execute(
            text("UPDATE teams SET alternate_names = CAST(:v AS jsonb) WHERE id = :id AND name = :name"),
            {"v": json.dumps(list(a.after)), "id": a.team_id, "name": a.name},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"alias edit {a.team_id} touched {res.rowcount} rows")
        out.append(f"  {a.team_id} {a.name!r} aliases -> {list(a.after)!r}")

    # One in-memory canonical per club, so two duplicates folding into the same
    # club (Red Bulls, Houston, Montreal) union into one alias list.
    canon: dict[int, SimpleNamespace] = {}
    for f in FOLDS:
        if f.canon_id not in canon:
            canon[f.canon_id] = SimpleNamespace(
                id=f.canon_id,
                name=f.canon_name,
                alternate_names=list(_aliases(rows[f.canon_id]["alternate_names"]) or []),
            )
        dup = rows[f.dup_id]
        stub = SimpleNamespace(
            id=f.dup_id,
            name=f.dup_name,
            slug=dup["slug"],
            alternate_names=list(_aliases(dup["alternate_names"]) or []),
        )
        evidence = await _apply_merge(session, canon[f.canon_id], stub, SPORT_KEY)
        out.append(f"  folded {f.dup_id} {f.dup_name!r} -> {f.canon_id}: {evidence['fk_repointed']}")
    return out


async def _refs_landed(session) -> str | None:
    """Every banked reference now names its club — except an entity whose club
    already had one, which ``_apply_merge`` leaves to go NULL on the delete."""
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
        # Only rows still on the club (or, for an entity, still unlinked): a row
        # somebody has since moved elsewhere is theirs, and the undo leaves it.
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

    # A club only ever gained aliases; a stripped or alias-edited row gets its
    # whole pre-image identity back.
    canons = sorted({f.canon_id for f in FOLDS})
    await session.execute(
        text(
            f"UPDATE teams t SET alternate_names = b.alternate_names FROM {BACKUP_TEAMS} b "
            "WHERE t.id = b.id AND t.id = ANY(:ids)"
        ),
        {"ids": canons + [a.team_id for a in ALIAS_EDITS]},
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
    refusal = rows_refusal(rows)
    if refusal:
        out.append(f"REFUSED: {refusal}")
        return 2, out
    counts = await _counts(session)
    for f in FOLDS:
        out.append(f"  {f.dup_id:>6} {f.dup_name!r:<22} -> {f.canon_id:>5}  refs {counts[f.dup_id]}")
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
            f"\ndry run — nothing written. Would strip {len(STRIPS)}, edit aliases on "
            f"{len(ALIAS_EDITS)}, fold {len(FOLDS)}."
        )
        return 0, out

    try:
        out.extend(await _apply(session, rows))
    except Exception as exc:  # the fold is one transaction: any failure undoes all of it
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
        f"\n  applied: {len(STRIPS)} stripped, {len(ALIAS_EDITS)} alias edits, "
        f"{len(FOLDS)} folded (banked in {BACKUP_TEAMS} / {BACKUP_REFS})"
    )
    out.append("undo: python3 scripts/repair_6974_fold_mls_duplicate_clubs.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#6974 MLS duplicate clubs — {mode.upper()}")
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
