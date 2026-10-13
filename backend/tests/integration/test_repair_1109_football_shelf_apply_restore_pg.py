"""#1109 — the Football-shelf repair's apply, rollback, re-run and undo, against a real PostgreSQL.

The unit file (`tests/test_repair_1109_football_shelf_residual.py`) drives the
artifact gates and the plan with dicts and a FakeSession. What the attended run
DOES is SQL, and three of its promises only a server can keep:

* **the compare-and-set is real** — a writer that lands between the run's read
  and its UPDATE changes zero rows in the CAS, for every value the plan decided
  on (`name`, `updated_at` to the microsecond, `source`, `external_id`,
  `llm_sport_category`), and the run refuses;
* **a refusal leaves nothing behind** — the first row's UPDATE is never committed
  on its own: a second connection never sees it, and the rollback takes it back,
  while the other writer's value survives;
* **only `llm_sport_category` moves** — every other column of a moved row, and
  the genuine football sibling, are untouched; the re-run writes nothing; the
  undo puts back only the ids it is given, still lands after a poll moved
  `updated_at`, and leaves a row another writer re-decided alone.

`name` is NOT NULL on `futures_markets`, so the CAS's null-safe `name` arm is not
exercised here: the private table mirrors the real column constraints.

Built narrow, in a private schema, so it runs on the lane VM's Postgres 14 as
well as in CI. CERT-4096 named this follow-up (1109-REPAIR-REAL-PG-ROLLBACK-GUARD).
"""

import importlib.util
import os
from pathlib import Path

import pytest
from sqlalchemy import text

from tests.test_repair_1109_football_shelf_residual import ARTIFACT, LIVE, NOW

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #1109 "
            "Football-shelf apply/restore gate (CI job: database-integration)"
        ),
    ),
]

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load():
    spec = importlib.util.spec_from_file_location(
        "repair_1109_pg", _SCRIPTS / "repair_1109_football_shelf_residual.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_GATE_SCHEMA = "football_shelf_gate_1109"
ITF, OTD, NFL = 901, 902, 903  # the artifact's two rows + a genuine football row


@pytest.fixture
async def engine():
    from sqlalchemy.ext.asyncio import create_async_engine

    # Every pooled connection — the run's and the concurrent writer's — resolves
    # the bare `futures_markets` the script names to the private table.
    eng = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _GATE_SCHEMA}}
    )
    yield eng
    await eng.dispose()


@pytest.fixture
async def gate(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))
        await conn.execute(text(f"CREATE SCHEMA {_GATE_SCHEMA}"))
        await conn.execute(
            text(
                "CREATE TABLE futures_markets (id int PRIMARY KEY, "
                "source varchar(50) NOT NULL, external_id varchar(200) NOT NULL, "
                "name varchar(300) NOT NULL, category varchar(50) NOT NULL, "
                "mutually_exclusive boolean NOT NULL, status varchar(20) NOT NULL, "
                "llm_sport_category varchar(50), llm_league varchar(50), "
                "canonical_market_key varchar(200), category_tags jsonb, "
                "updated_at timestamptz NOT NULL)"
            )
        )
        nfl_at = LIVE[ITF][4]
        for market_id, (source, external_id, sport, name, updated_at) in (
            *LIVE.items(),
            (NFL, ("kalshi", "KXNFLGAME-26SEP13KCBUF", "football", "Chiefs vs Bills", nfl_at)),
        ):
            await conn.execute(
                text(
                    "INSERT INTO futures_markets (id, source, external_id, name, "
                    "category, mutually_exclusive, status, llm_sport_category, "
                    "llm_league, canonical_market_key, category_tags, updated_at) "
                    "VALUES (:id, :source, :external_id, :name, 'futures', false, "
                    "'open', :sport, 'keep-league', :key, '[\"keep-tag\"]', :at)"
                ),
                {
                    "id": market_id,
                    "source": source,
                    "external_id": external_id,
                    "name": name,
                    "sport": sport,
                    "key": f"keep-key-{market_id}",
                    "at": updated_at,
                },
            )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    async with engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA IF EXISTS {_GATE_SCHEMA} CASCADE"))


async def _rows(engine):
    """Every column of every row, read on a connection of its own (committed state)."""
    async with engine.connect() as conn:
        got = await conn.execute(text("SELECT * FROM futures_markets ORDER BY id"))
        return [tuple(r._mapping.items()) for r in got]


async def _sports(engine):
    async with engine.connect() as conn:
        got = await conn.execute(
            text("SELECT id, llm_sport_category FROM futures_markets ORDER BY id")
        )
        return dict(got.all())


async def _concurrently(engine, sql, **params):
    """Another writer, committed on its own connection."""
    async with engine.begin() as conn:
        await conn.execute(text(sql), params)


def _without_sport(rows):
    return [tuple(kv for kv in row if kv[0] != "llm_sport_category") for row in rows]


async def test_apply_moves_only_the_category_and_the_rerun_and_undo_are_exact(gate, engine):
    r = _load()
    before = await _rows(engine)

    dry = await r.run(gate, ARTIFACT, mode="dry-run", now=NOW)
    assert dry["written"] == 0
    assert await _rows(engine) == before

    out = await r.run(
        gate, ARTIFACT, mode="apply", now=NOW, expect_plan_hash=dry["plan_hash"]
    )
    assert out["written"] == 2
    assert out["movement"] == {"football->tennis": 1, "football->basketball": 1}
    after = await _rows(engine)
    assert await _sports(engine) == {ITF: "tennis", OTD: "basketball", NFL: "football"}
    # Name, updated_at, league, canonical key, tags, status: byte-for-byte unchanged.
    assert _without_sport(after) == _without_sport(before)

    read = await r.run(gate, ARTIFACT, mode="readback", now=NOW)
    assert read["ids"]["after"] == [ITF, OTD]

    # The re-run reads both rows as already repaired: an empty plan writes nothing.
    rerun_dry = await r.run(gate, ARTIFACT, mode="dry-run", now=NOW)
    assert rerun_dry["write"] == []
    rerun = await r.run(
        gate, ARTIFACT, mode="apply", now=NOW, expect_plan_hash=rerun_dry["plan_hash"]
    )
    assert rerun["written"] == 0
    assert await _rows(engine) == after

    # A poll touches the repaired row; the undo gates on identity and category only.
    await _concurrently(
        engine,
        "UPDATE futures_markets SET updated_at = updated_at + interval '1 minute' "
        "WHERE id = :id",
        id=ITF,
    )
    undo = await r.run(gate, ARTIFACT, mode="restore", now=NOW, restore_ids=frozenset({ITF}))
    assert undo["written"] == 1
    assert await _sports(engine) == {ITF: "football", OTD: "basketball", NFL: "football"}
    assert (await r.run(gate, ARTIFACT, mode="readback", now=NOW))["ids"]["before"] == [ITF]


async def test_undo_leaves_a_row_another_writer_re_decided(gate, engine):
    r = _load()
    dry = await r.run(gate, ARTIFACT, mode="dry-run", now=NOW)
    await r.run(gate, ARTIFACT, mode="apply", now=NOW, expect_plan_hash=dry["plan_hash"])
    await _concurrently(
        engine, "UPDATE futures_markets SET llm_sport_category = 'hockey' WHERE id = :id", id=OTD
    )

    undo = await r.run(
        gate, ARTIFACT, mode="restore", now=NOW, restore_ids=frozenset({ITF, OTD})
    )
    assert undo["written"] == 1
    assert [market_id for market_id, _ in undo["skip"]] == [OTD]
    assert await _sports(engine) == {ITF: "football", OTD: "hockey", NFL: "football"}


_DRIFT = {
    "name": "name = 'Renamed by a poll'",
    "updated_at": "updated_at = updated_at + interval '1 microsecond'",
    "source": "source = 'polymarket'",
    "external_id": "external_id = 'KXOTHER-26JUL01'",
    "llm_sport_category": "llm_sport_category = 'hockey'",
}


@pytest.mark.parametrize("field", sorted(_DRIFT))
async def test_a_writer_between_the_read_and_the_update_refuses_and_rolls_back(
    gate, engine, monkeypatch, field
):
    """The plan is made on the read; the second row moves before its UPDATE.

    The first row's write has already executed when the second CAS matches zero
    rows. It must never have been committed on its own, and the rollback must take
    it back without touching the other writer's value.
    """
    r = _load()
    dry = await r.run(gate, ARTIFACT, mode="dry-run", now=NOW)
    before = await _rows(engine)
    real_read = r._read

    async def read_then_another_writer(session, ids):
        live = await real_read(session, ids)
        await _concurrently(
            engine, f"UPDATE futures_markets SET {_DRIFT[field]} WHERE id = :id", id=OTD
        )
        return live

    monkeypatch.setattr(r, "_read", read_then_another_writer)
    with pytest.raises(r.Refused, match=f"market {OTD}: expected to change 1 row, changed 0"):
        await r.run(gate, ARTIFACT, mode="apply", now=NOW, expect_plan_hash=dry["plan_hash"])

    # The run's own transaction holds the first write; nobody else can see it.
    mine = await gate.execute(
        text("SELECT llm_sport_category FROM futures_markets WHERE id = :id"), {"id": ITF}
    )
    assert mine.scalar_one() == "tennis"
    assert (await _sports(engine))[ITF] == "football"

    await gate.rollback()
    after = await _rows(engine)
    # The ITF row and the football sibling are exactly as they were; the OTD row
    # carries the other writer's change and nothing of the repair's.
    assert after[0] == before[0] and after[2] == before[2]
    otd_before, otd_after = dict(before[1]), dict(after[1])
    changed = {k for k in otd_before if otd_before[k] != otd_after[k]}
    assert changed == {field}
    if field != "llm_sport_category":
        assert otd_after["llm_sport_category"] == "football"
