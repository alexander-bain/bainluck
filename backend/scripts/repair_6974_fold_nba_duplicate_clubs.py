"""#6974 (NBA residual) — the Pistons, Magic, Blazers and Clippers get their own rows back.

THE SHIP: the Pistons, Magic, Trail Blazers and Clippers pages carry the futures
legs a duplicate row holds today; Kalshi's 2027 title, East and West odds for the
Pistons, Magic and Blazers bind to them (today they bind to nothing); and search
stops showing a second card ("Los Angeles C 39-36", "Detroit 60-22") beside the club.

WHY THE KALSHI LEGS ARE STUCK (measured 2026-09-30 ~03:15Z)
-----------------------------------------------------------

Kalshi names NBA teams by city. The #9617 league step (``team_linking.
match_outcome_to_league_team``) binds a city inside the ticker's league only on
ONE hit. Each of these cities has TWO NBA rows, so it refuses and does not guess:

* "Detroit" is ``41 Detroit Pistons``'s alias AND ``12719 Detroit``'s name;
* "Orlando" is ``47 Orlando Magic``'s alias AND ``13554 Orlando``'s name;
* "Portland" is ``104 Portland Trail Blazers``'s alias AND ``11362 Portland``'s name.

Open and unbound: KXNBA-27 Detroit / Orlando / Portland, KXNBAEAST-27 Detroit /
Orlando, KXNBAWEST-27 Portland. After the fold each city is one row, and the next
linker pass binds them.

WHAT EACH ROW IS
----------------

Each duplicate shares ``basketball_nba`` and the real club's ``espn_id`` (8, 19,
22, 12), crest and abbreviation. Its events are closed February–April Kalshi
rows, each a second row for a game the club's own row already carries. Each
FOLDS into the club, after these corrections:

* **Legs that are another club's** move to that club first. A plain fold would
  put them on the wrong team page:
  - ``12649`` is Kalshi's "Los Angeles C" AND "Los Angeles L": 17 Lakers legs go
    to ``49``, one LAFC leg ("Los Angeles F vs Miami") to ``13537`` and one Kings
    leg to ``64``. Its 12 "Los Angeles C" legs are the Clippers';
  - ``12719``'s "Tobias Harris" leg is in "San Antonio Opening Game Starters",
    whose other ten named starters are all on the Spurs (``38``);
  - ``11362``'s "Nuggets" leg is the Nuggets' side of "Nuggets vs. Trail Blazers",
    whose Nuggets players are all on ``154``. Its MLS "Portland vs Columbus" leg
    goes to the Timbers (``21``).
* **College legs are unlinked** (``team_id`` NULL), not guessed onto one of the
  per-sport college rows: University of Portland ("WCC Regular Season Champion",
  "Portland at Oregon St."), Portland St. (three February games) and Detroit
  Mercy lacrosse ("Bellarmine vs Detroit"). All six are resolved.
* **Mappings:** ``11362``'s Kalshi "Brooklyn" is repointed to the Nets (``48``).
  ``12719``'s "Game 1: Orlando" and ``13554``'s "Detroit Professional Basketball
  Game" are market-title fragments, banked whole and deleted.

NOT DONE HERE, said rather than implied: Kalshi's "Los Angeles C" and "Los
Angeles L" (the Clippers' and Lakers' 2027 legs) stay unbound. ``normalize_name``
drops the trailing letter, so both read as "los angeles", which the Lakers also
answer to, and the league step refuses. That is the normalizer, not a duplicate
row, and no fold changes it. The game-line outcomes on
Polymarket's Blazers games ("O/U 238.5", "1H Moneyline") ride to ``104``, the
same row the other lines in those markets already name.

Runs only on ``bainluck-heavy`` (notice 47(c): runtime DDL, attended invocation):

    python3 scripts/repair_6974_fold_nba_duplicate_clubs.py            # dry run
    python3 scripts/repair_6974_fold_nba_duplicate_clubs.py --apply    # bank, correct, fold
    python3 scripts/repair_6974_fold_nba_duplicate_clubs.py --restore  # undo
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
SPORT_KEY = "basketball_nba"

#: Every foreign key onto ``teams.id`` in production (``pg_constraint``,
#: 2026-09-30), in the order ``Fold.refs`` pins them.
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


class Target(NamedTuple):
    """A club that receives a corrected leg or mapping, pinned by name and league."""

    team_id: int
    name: str
    sport_key: str


class MappingEdit(NamedTuple):
    mapping_id: int
    source: str
    source_name: str
    from_team: int
    to_team: int


class MappingRow(NamedTuple):
    """A mapping on a duplicate, pinned whole, then banked and deleted."""

    mapping_id: int
    source: str
    source_name: str
    team_id: int


class LegEdit(NamedTuple):
    """A futures leg on a duplicate that is not the duplicate's club."""

    outcome_id: int
    name: str
    from_team: int
    #: The leg's club, or None to unlink it.
    to_team: int | None
    #: The market's title, for the log (not pinned).
    market: str


#: Read from production 2026-09-30 ~03:15Z. Counts are (home, away, futures,
#: entities, mappings, tournament_odds, favourites).
FOLDS: tuple[Fold, ...] = (
    Fold(12719, "Detroit", 41, "Detroit Pistons", "8", (1, 1, 39, 1, 1, 0, 0),
         ("Detroit Pistons", "Pistons")),
    Fold(13554, "Orlando", 47, "Orlando Magic", "19", (0, 1, 43, 1, 1, 0, 0),
         ("Orlando Magic", "Magic")),
    Fold(11362, "Portland", 104, "Portland Trail Blazers", "22", (1, 1, 76, 1, 1, 0, 0),
         ("Trail Blazers", "Portland Trail Blazers")),
    Fold(12649, "Los Angeles C", 537, "Los Angeles Clippers", "12", (0, 1, 31, 1, 0, 0, 0),
         ("Clippers", "LA Clippers")),
)

LAKERS, KINGS, LAFC, SPURS, NUGGETS, TIMBERS, NETS = 49, 64, 13537, 38, 154, 21, 48

TARGETS: tuple[Target, ...] = (
    Target(LAKERS, "Los Angeles Lakers", SPORT_KEY),
    Target(KINGS, "Los Angeles Kings", "icehockey_nhl"),
    Target(LAFC, "LAFC", "soccer_usa_mls"),
    Target(SPURS, "San Antonio Spurs", SPORT_KEY),
    Target(NUGGETS, "Denver Nuggets", SPORT_KEY),
    Target(TIMBERS, "Portland Timbers", "soccer_usa_mls"),
    Target(NETS, "Brooklyn Nets", SPORT_KEY),
)

#: Applied BEFORE the folds, so the folds find nothing left to move for them.
MAPPING_EDITS: tuple[MappingEdit, ...] = (
    MappingEdit(156455, "kalshi", "Brooklyn", 11362, NETS),
)

#: Banked whole, then deleted, BEFORE the folds.
MAPPING_DELETES: tuple[MappingRow, ...] = (
    MappingRow(6864296, "kalshi", "Game 1: Orlando", 12719),
    MappingRow(7011777, "kalshi", "Detroit Professional Basketball Game", 13554),
)

_L = "Los Angeles L"
_LAKERS = "Los Angeles Lakers"

#: Applied BEFORE the folds.
LEG_EDITS: tuple[LegEdit, ...] = (
    # 12649 "Los Angeles C": Kalshi's Lakers ("Los Angeles L") and Polymarket's.
    LegEdit(2362, "Stays with Los Angeles L or Retires", 12649, LAKERS, "LeBron James Next Team"),
    LegEdit(3635, _L, 12649, LAKERS, "Game 7: San Antonio vs Oklahoma City"),
    LegEdit(3676, _L, 12649, LAKERS, "2026 Pro Basketball Champion"),
    LegEdit(5417, _L, 12649, LAKERS, "Pro Basketball Playoff Qualifiers"),
    LegEdit(5609, _L, 12649, LAKERS, "Pro Basketball Best Regular Season Record"),
    LegEdit(5632, _L, 12649, LAKERS, "Pro Basketball Western Conference #1 Seed"),
    LegEdit(5650, _L, 12649, LAKERS, "Pro Basketball Pacific Division Winner"),
    LegEdit(1607018, _L, 12649, LAKERS, "Team to Win the Draft Lottery"),
    LegEdit(1607813, _L, 12649, LAKERS, "Teams to Make the Western Conference Play-In Tournament"),
    LegEdit(1616060, _L, 12649, LAKERS, "Los Angeles C at Los Angeles L"),
    LegEdit(1625796, _LAKERS, 12649, LAKERS, "2026 NBA Champion"),
    LegEdit(1626061, _LAKERS, 12649, LAKERS, "NBA Playoffs:  Western Conference Champion "),
    LegEdit(1627483, _LAKERS, 12649, LAKERS, "Which teams will make the NBA Playoffs?"),
    LegEdit(1627514, _LAKERS, 12649, LAKERS, "NBA Pacific Division Winner"),
    LegEdit(1627557, _LAKERS, 12649, LAKERS, "NBA Best Record"),
    LegEdit(1627586, "Will the Los Angeles Lakers have the worst record in the NBA", 12649,
            LAKERS, "NBA Worst Record"),
    LegEdit(1628000, _LAKERS, 12649, LAKERS, "NBA Western Conference #1 Seed"),
    LegEdit(1614739, "Los Angeles F", 12649, LAFC, "Los Angeles F vs Miami"),
    LegEdit(3366, "Los Angeles Kings", 12649, KINGS,
            "Series Winner: Vegas Golden Knights vs Colorado Avalanche"),
    # 12719 "Detroit".
    LegEdit(218007493, "Tobias Harris", 12719, SPURS, "San Antonio Opening Game Starters"),
    LegEdit(1615657, "Detroit", 12719, None, "Bellarmine vs Detroit"),
    # 11362 "Portland".
    LegEdit(1714079, "Nuggets", 11362, NUGGETS, "Nuggets vs. Trail Blazers"),
    LegEdit(1614671, "Portland", 11362, TIMBERS, "Portland vs Columbus"),
    LegEdit(1610270, "Portland", 11362, None, "WCC Regular Season Champion"),
    LegEdit(1618071, "Portland", 11362, None, "Portland at Oregon St."),
    LegEdit(1618069, "Portland St.", 11362, None, "Portland St. at Idaho"),
    LegEdit(1618201, "Portland St.", 11362, None, "Idaho at Portland St."),
    LegEdit(1618218, "Portland St.", 11362, None, "Idaho vs Portland St.: First Half Winner"),
)

BACKUP_TEAMS = "backup_6974nba_teams"
BACKUP_REFS = "backup_6974nba_refs"
BACKUP_MAPPINGS = "backup_6974nba_mappings"


def all_team_ids() -> list[int]:
    ids = {f.dup_id for f in FOLDS} | {f.canon_id for f in FOLDS}
    ids |= {t.team_id for t in TARGETS}
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


def rows_refusal(
    rows: dict[int, dict], mappings: dict[int, dict], legs: dict[int, dict]
) -> str | None:
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
    for t in TARGETS:
        row = rows.get(t.team_id)
        if row is None or row["name"] != t.name or row["sport_key"] != t.sport_key:
            return f"target {t.team_id} ({t.name!r}) is not the {t.sport_key} row it was"
    for e in MAPPING_EDITS:
        m = mappings.get(e.mapping_id)
        if m is None:
            return f"mapping {e.mapping_id} ({e.source} {e.source_name!r}) is gone"
        got = (m["source"], m["source_name"], m["sport_key"], m["team_id"])
        want = (e.source, e.source_name, SPORT_KEY, e.from_team)
        if got != want:
            return f"mapping {e.mapping_id} is now {got!r}, expected {want!r}"
    for p in MAPPING_DELETES:
        m = mappings.get(p.mapping_id)
        if m is None:
            return f"deleted mapping {p.mapping_id} ({p.source} {p.source_name!r}) is gone"
        got = (m["source"], m["source_name"], m["sport_key"], m["team_id"])
        want = (p.source, p.source_name, SPORT_KEY, p.team_id)
        if got != want:
            return f"deleted mapping {p.mapping_id} is now {got!r}, expected {want!r}"
    for g in LEG_EDITS:
        leg = legs.get(g.outcome_id)
        if leg is None:
            return f"leg {g.outcome_id} ({g.name!r}) is gone"
        got = (leg["name"], leg["team_id"])
        if got != (g.name, g.from_team):
            return f"leg {g.outcome_id} is now {got!r}, expected {(g.name, g.from_team)!r}"
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
    ids = [e.mapping_id for e in MAPPING_EDITS] + deleted_ids()
    res = await session.execute(
        text(
            "SELECT id, source, source_name, sport_key, team_id "
            "FROM team_identity_mapping WHERE id = ANY(:ids)"
        ),
        {"ids": ids},
    )
    return {r.id: dict(r._mapping) for r in res}


async def _read_legs(session) -> dict[int, dict]:
    res = await session.execute(
        text("SELECT id, name, team_id FROM futures_outcomes WHERE id = ANY(:ids)"),
        {"ids": [g.outcome_id for g in LEG_EDITS]},
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
    # ``to_team`` is NULL for an unlinked leg.
    await session.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_REFS} (tbl text NOT NULL, col text NOT NULL, "
            "row_id bigint NOT NULL, from_team bigint NOT NULL, to_team bigint)"
        )
    )
    # The mapping and leg edits bank first, naming THEIR destination, so the
    # folds' own banking below skips those rows (NOT EXISTS) instead of naming the club.
    for e in MAPPING_EDITS:
        await session.execute(
            text(
                _BANK_REF.format(
                    bk=BACKUP_REFS, table="team_identity_mapping", col="team_id",
                    extra="AND id = CAST(:rid AS bigint) ",
                )
            ),
            {"tbl": "team_identity_mapping", "col": "team_id", "dup": e.from_team,
             "canon": e.to_team, "rid": e.mapping_id},
        )
    for g in LEG_EDITS:
        await session.execute(
            text(
                _BANK_REF.format(
                    bk=BACKUP_REFS, table="futures_outcomes", col="team_id",
                    extra="AND id = CAST(:rid AS bigint) ",
                )
            ),
            {"tbl": "futures_outcomes", "col": "team_id", "dup": g.from_team,
             "canon": g.to_team, "rid": g.outcome_id},
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

    for p in MAPPING_DELETES:
        res = await session.execute(
            text("DELETE FROM team_identity_mapping WHERE id = :id AND team_id = :dup"),
            {"id": p.mapping_id, "dup": p.team_id},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"mapping delete {p.mapping_id} touched {res.rowcount} rows")
    out.append(f"  deleted {len(MAPPING_DELETES)} mappings (banked in {BACKUP_MAPPINGS})")

    for g in LEG_EDITS:
        res = await session.execute(
            text("UPDATE futures_outcomes SET team_id = :to WHERE id = :id AND team_id = :frm"),
            {"to": g.to_team, "id": g.outcome_id, "frm": g.from_team},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"leg edit {g.outcome_id} touched {res.rowcount} rows")
    moved = sum(1 for g in LEG_EDITS if g.to_team is not None)
    out.append(f"  legs: {moved} moved to their own club, {len(LEG_EDITS) - moved} unlinked")

    for f in FOLDS:
        stub = SimpleNamespace(
            id=f.dup_id, name=f.dup_name, slug=rows[f.dup_id]["slug"],
            alternate_names=list(f.aliases),
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

    # After the teams, which they reference. A (source, name) a writer has since
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
        # unlinked): a row somebody has since moved elsewhere is theirs. An
        # unlinked leg the linker has since bound is theirs too.
        null_arm = f" OR t.{col} IS NULL" if table == "entities" else ""
        res = await session.execute(
            text(
                f"UPDATE {table} t SET {col} = b.from_team FROM {BACKUP_REFS} b "
                f"WHERE b.tbl = :tbl AND b.col = :col AND b.row_id = t.id "
                f"AND (t.{col} IS NOT DISTINCT FROM b.to_team{null_arm})"
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
    refusal = rows_refusal(rows, await _read_mappings(session), await _read_legs(session))
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
            f"delete {len(MAPPING_DELETES)}, correct {len(LEG_EDITS)} legs, fold {len(FOLDS)}."
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
        f"{len(LEG_EDITS)} legs corrected, {len(FOLDS)} folded "
        f"(banked in {BACKUP_TEAMS} / {BACKUP_REFS} / {BACKUP_MAPPINGS})"
    )
    out.append("undo: python3 scripts/repair_6974_fold_nba_duplicate_clubs.py --restore")
    return 0, out


async def run(mode: str) -> int:
    refusal = wrong_app_refusal()
    if refusal:
        print(f"REFUSED: {refusal}")
        return 2
    from app.tasks.base import get_task_session

    print(f"#6974 NBA duplicate clubs — {mode.upper()}")
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
