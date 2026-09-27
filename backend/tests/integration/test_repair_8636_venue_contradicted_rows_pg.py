"""#8636 — the venue-contradicted-rows repair's apply, re-run and undo, against a real PostgreSQL.

The unit file drives the manifest and the refusal rule with dicts. What the
repair DOES is SQL:

* the population read — the pinned rows, their linked Polymarket markets'
  ``group_id`` and stamped slug;
* the banked pre-image and the guarded writes: ``status`` for a volleyball row,
  ``sport_id`` + ``llm_league`` for a soccer row;
* a re-run that finds nothing left to write;
* an undo that puts back ONLY rows still where the repair put them;
* and the ship, read the way a card reads it: the row's ``sports.key`` through
  its ``sport_id``, and its ``status``.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI.
"""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8636 "
            "venue-contradicted-rows apply/restore gate (CI job: search-recall)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    sys.path.insert(0, str(_SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "repair_8636_pg", _SCRIPTS / "repair_8636_venue_contradicted_rows.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


m = _load()

_GATE_SCHEMA = "venue_contradicted_gate_8636"
UNL_KEY = "soccer_uefa_nations_league"
UCL_KEY = "soccer_uefa_champs_league"
UWCL_KEY = "soccer_uefa_champs_league_women"

OTHER, UNL, UCL, UWCL, BASE = 86360001, 86360002, 86360003, 86360004, 86360005

# Pinned and qualifying.
EV_VB_UNL = 86360201  # Italy v Slovenia volleyball, in the Nations League
EV_VB_BASE = 86360202  # Italy v USA volleyball, on baseball_other, closed
EV_ROMA = 86360203  # women's UCL, filed as the men's
EV_FIF = 86360204  # FIFA friendly, filed as the Nations League
# Pinned, but must be skipped.
EV_MOVED = 86360205  # somebody already moved it to the catch-all
EV_UNLINKED = 86360206  # its measured venue event is no longer linked
EV_VOIDED = 86360207  # already retired
EV_RESTAMPED = 86360208  # a linked market's slug now names another competition
# Not pinned: a real Nations League game; must not be touched.
EV_REAL_UNL = 86360301

PINS = (
    (EV_VB_UNL, UNL_KEY, "1037992", "vbeuro-ita2-slo4-2026-09-17", "Volleyball"),
    (EV_VB_BASE, "baseball_other", "739849", "vbvnl-ita-usa-2026-07-30", "Volleyball"),
    (EV_ROMA, UCL_KEY, "1034901", "uwcl-asr-fcb-2026-09-30", "Soccer"),
    (EV_FIF, UNL_KEY, "1038099", "fif-lit-and-2026-09-30", "Soccer"),
    (EV_MOVED, UNL_KEY, "1063975", "clf-vfb-fch-2026-09-25", "Soccer"),
    (EV_UNLINKED, UNL_KEY, "1037990", "vbeuro-ser2-bel2-2026-09-17", "Volleyball"),
    (EV_VOIDED, "soccer_other", "885437", "vbeuro-ger-slo-2026-08-22", "Volleyball"),
    (EV_RESTAMPED, UNL_KEY, "1049364", "u20wwc-ita-esp-2026-09-23", "Soccer"),
)


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _event(id_, sport, home, away, status, league):
    league_sql = "NULL" if league is None else f"'{league}'"
    return f"({id_}, {sport}, '{home}', '{away}', '{status}', {league_sql})"


def _market(id_, event_id, group, slug=None):
    meta = {"polymarket_event_id": group}
    if slug:
        meta["polymarket_event_slug"] = slug
    return (
        f"({id_}, 'polymarket', 'poly-{id_}', 'polymarket:{group}', {event_id}, "
        f"'{json.dumps(meta)}')"
    )


@pytest.fixture
async def gate(pg_session, monkeypatch):
    monkeypatch.setattr(m, "PINS", PINS)
    s = pg_session
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    for ddl in (
        "CREATE TABLE sports (id int PRIMARY KEY, key varchar(50) NOT NULL UNIQUE, "
        "name varchar(100) NOT NULL, active boolean NOT NULL)",
        "CREATE TABLE events (id int PRIMARY KEY, sport_id int NOT NULL REFERENCES sports(id), "
        "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
        "status varchar(20) NOT NULL, llm_league varchar(100))",
        "CREATE TABLE futures_markets (id int PRIMARY KEY, source varchar(20) NOT NULL, "
        "external_id varchar(200) NOT NULL, group_id varchar(100), "
        "event_id int REFERENCES events(id), market_metadata jsonb)",
    ):
        await s.execute(text(ddl))
    await s.execute(
        text(
            "INSERT INTO sports (id, key, name, active) VALUES "
            f"({OTHER}, 'soccer_other', 'soccer_other', true), "
            f"({UNL}, '{UNL_KEY}', 'UEFA Nations League', true), "
            f"({UCL}, '{UCL_KEY}', 'UEFA Champions League', true), "
            f"({UWCL}, '{UWCL_KEY}', 'UEFA Champions League Women', true), "
            f"({BASE}, 'baseball_other', 'baseball_other', true)"
        )
    )
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_name, away_team_name, status, "
            "llm_league) VALUES "
            + ", ".join(
                [
                    _event(EV_VB_UNL, UNL, "Italy", "Slovenia", "suspended",
                           "Uefa Nations League"),
                    _event(EV_VB_BASE, BASE, "Italy", "USA", "closed", "International"),
                    _event(EV_ROMA, UCL, "AS Roma", "FC Barcelona", "scheduled",
                           "Champions_League"),
                    _event(EV_FIF, UNL, "Lithuania", "Andorra", "scheduled",
                           "Uefa Nations League"),
                    _event(EV_MOVED, OTHER, "VfB Stuttgart", "1. FC Heidenheim",
                           "suspended", "Other"),
                    _event(EV_UNLINKED, UNL, "Serbia", "Belgium", "suspended",
                           "Uefa Nations League"),
                    _event(EV_VOIDED, OTHER, "Germany", "Slovenia", "voided", None),
                    _event(EV_RESTAMPED, UNL, "Italy", "Spain", "suspended",
                           "Uefa Nations League"),
                    _event(EV_REAL_UNL, UNL, "Italy", "Türkiye", "scheduled",
                           "Uefa Nations League"),
                ]
            )
        )
    )
    await s.execute(
        text(
            "INSERT INTO futures_markets (id, source, external_id, group_id, event_id, "
            "market_metadata) VALUES "
            + ", ".join(
                [
                    _market(86360501, EV_VB_UNL, "1037992"),
                    _market(86360502, EV_VB_BASE, "739849"),
                    _market(86360503, EV_ROMA, "1034901", "uwcl-asr-fcb-2026-09-30"),
                    _market(86360504, EV_ROMA, "1034916",
                            "uwcl-asr-fcb-2026-09-30-exact-score"),
                    _market(86360505, EV_FIF, "1038099", "fif-lit-and-2026-09-30"),
                    _market(86360506, EV_MOVED, "1063975"),
                    _market(86360507, EV_UNLINKED, "9999999"),
                    _market(86360508, EV_VOIDED, "885437"),
                    _market(86360509, EV_RESTAMPED, "1049364", "unl-ita-esp-2026-09-23"),
                    _market(86360510, EV_REAL_UNL, "1057000", "unl-ita-tur-2026-10-05"),
                ]
            )
        )
    )
    await s.commit()
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    yield s
    await s.rollback()
    await s.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
    await s.commit()


async def _row(s, event_id):
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    res = await s.execute(
        text(
            "SELECT s.key, e.status, e.llm_league FROM events e "
            "JOIN sports s ON s.id = e.sport_id WHERE e.id = :id"
        ),
        {"id": event_id},
    )
    return tuple(res.one())


async def _backup_ids(s):
    await s.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    res = await s.execute(text(f"SELECT event_id FROM {m.BACKUP} ORDER BY 1"))
    return [r[0] for r in res]


BEFORE = {
    EV_VB_UNL: (UNL_KEY, "suspended", "Uefa Nations League"),
    EV_VB_BASE: ("baseball_other", "closed", "International"),
    EV_ROMA: (UCL_KEY, "scheduled", "Champions_League"),
    EV_FIF: (UNL_KEY, "scheduled", "Uefa Nations League"),
    EV_MOVED: ("soccer_other", "suspended", "Other"),
    EV_UNLINKED: (UNL_KEY, "suspended", "Uefa Nations League"),
    EV_VOIDED: ("soccer_other", "voided", None),
    EV_RESTAMPED: (UNL_KEY, "suspended", "Uefa Nations League"),
    EV_REAL_UNL: (UNL_KEY, "scheduled", "Uefa Nations League"),
}
SKIPPED = (EV_MOVED, EV_UNLINKED, EV_VOIDED, EV_RESTAMPED, EV_REAL_UNL)


async def test_the_dry_run_names_every_row_and_writes_nothing(gate):
    code, lines = await m.repair(gate, "dry")
    out = "\n".join(lines)
    assert code == 0, out
    assert f"retire {EV_VB_UNL} -> voided" in out
    assert f"retire {EV_VB_BASE} -> voided" in out
    assert f"relabel {EV_ROMA} -> {UWCL_KEY}" in out
    assert f"relabel {EV_FIF} -> soccer_other" in out
    assert f"skip {EV_MOVED}: now on 'soccer_other'" in out
    assert f"skip {EV_UNLINKED}: no longer linked" in out
    assert f"skip {EV_VOIDED}: already 'voided'" in out
    assert f"skip {EV_RESTAMPED}: a linked market's slug now names ['unl']" in out
    assert "Would retire 2, relabel 2, skip 4" in out
    for event_id, before in BEFORE.items():
        assert await _row(gate, event_id) == before


async def test_apply_writes_the_qualifying_pins_the_venues_way_and_nothing_else(gate):
    code, lines = await m.repair(gate, "apply")
    assert code == 0, lines
    # The ship: the volleyball rows leave every surface…
    assert await _row(gate, EV_VB_UNL) == (UNL_KEY, "voided", "Uefa Nations League")
    assert await _row(gate, EV_VB_BASE) == ("baseball_other", "voided", "International")
    # …Roma v Barcelona is the women's Champions League, league word and all…
    assert await _row(gate, EV_ROMA) == (UWCL_KEY, "scheduled", "Uefa Champs League Women")
    # …and a friendly leaves the Nations League for the catch-all.
    assert await _row(gate, EV_FIF) == ("soccer_other", "scheduled", "Other")
    for event_id in SKIPPED:
        assert await _row(gate, event_id) == BEFORE[event_id]
    assert await _backup_ids(gate) == [EV_VB_UNL, EV_VB_BASE, EV_ROMA, EV_FIF]


async def test_a_re_run_writes_nothing_and_keeps_the_first_pre_image(gate):
    assert (await m.repair(gate, "apply"))[0] == 0
    code, lines = await m.repair(gate, "apply")
    assert code == 0
    assert "nothing to write" in "\n".join(lines)
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    res = await gate.execute(
        text(f"SELECT from_status, from_sport_id FROM {m.BACKUP} WHERE event_id = :id"),
        {"id": EV_ROMA},
    )
    assert tuple(res.one()) == ("scheduled", UCL)


async def test_restore_puts_back_only_rows_still_where_the_repair_put_them(gate):
    assert (await m.repair(gate, "apply"))[0] == 0
    # Somebody moves one relabelled row on after the repair; the undo leaves it.
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    await gate.execute(
        text("UPDATE events SET sport_id = :unl WHERE id = :id"),
        {"unl": UNL, "id": EV_FIF},
    )
    await gate.commit()
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    code, lines = await m.repair(gate, "restore")
    assert code == 0
    assert "restored 3 event(s)" in "\n".join(lines)
    assert await _row(gate, EV_VB_UNL) == BEFORE[EV_VB_UNL]
    assert await _row(gate, EV_VB_BASE) == BEFORE[EV_VB_BASE]
    assert await _row(gate, EV_ROMA) == BEFORE[EV_ROMA]
    assert await _row(gate, EV_FIF) == (UNL_KEY, "scheduled", "Other")
    assert await _row(gate, EV_REAL_UNL) == BEFORE[EV_REAL_UNL]


async def test_restore_before_any_apply_is_a_no_op(gate):
    code, lines = await m.repair(gate, "restore")
    assert code == 0
    assert "restored 0 event(s)" in "\n".join(lines)


async def test_a_missing_league_row_refuses_and_writes_nothing(gate):
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    await gate.execute(text("UPDATE sports SET key = 'renamed' WHERE id = :id"), {"id": UWCL})
    await gate.commit()
    await gate.execute(text(f"SET search_path TO {_GATE_SCHEMA}"))
    code, lines = await m.repair(gate, "apply")
    assert code == 2
    assert "no sports row" in "\n".join(lines)
    assert (await _row(gate, EV_VB_UNL))[1] == "suspended"
