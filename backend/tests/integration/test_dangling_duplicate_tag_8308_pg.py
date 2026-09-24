"""#8308 — the merge rail's tag move and the repair, against a real PostgreSQL.

Everything that decides the answer is JSONB arithmetic — ``-`` removing an element,
``||`` appending one, ``@>`` scoping the rows — and a recording session cannot run any
of it. The ``duplicate-of:2`` / ``duplicate-of:20`` pair is here because a substring
test would confuse them and ``@>`` must not.

A narrow ``events`` table in a private schema, so this runs on the lane VM's
Postgres 14 as well as in CI.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #8308 "
            "duplicate-tag gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "dangling_dup_tag_gate_8308"


def _load():
    path = Path(__file__).resolve().parents[2] / "scripts" / "repair_8308_dangling_duplicate_tags.py"
    spec = importlib.util.spec_from_file_location("repair_8308_pg", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_8308_pg"] = mod
    spec.loader.exec_module(mod)
    return mod


m = _load()


def T(n):
    return f"provenance:duplicate-of:{n}"


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # search_path is pinned on EVERY pooled connection, not SET once: `run()` commits,
    # and a commit may hand the session a different connection, which would then read
    # whatever `events` the database's default path finds.
    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
        await s.execute(
            text(
                f"CREATE TABLE {_SCHEMA}.events (id bigint PRIMARY KEY, sport_id int NOT NULL, "
                "home_team_name varchar(200) NOT NULL, away_team_name varchar(200) NOT NULL, "
                "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
                "event_tags jsonb)"
            )
        )
        await s.execute(
            text(f"CREATE INDEX ON {_SCHEMA}.events USING gin (event_tags jsonb_path_ops)")
        )
        await s.commit()
        yield s
        await s.rollback()
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.commit()
    await engine.dispose()


async def _seed(s, rows: dict):
    for rid, tags in rows.items():
        await s.execute(
            text(
                "INSERT INTO events (id, sport_id, home_team_name, away_team_name, "
                "commence_time, status, event_tags) VALUES (:id, 1, 'Baltimore Orioles', "
                "'Toronto Blue Jays', now(), 'live', CAST(:t AS jsonb))"
            ),
            {"id": rid, "t": None if tags is None else json.dumps(tags)},
        )


async def _tags(s) -> dict:
    got = await s.execute(text("SELECT id, event_tags FROM events ORDER BY id"))
    return {int(r.id): r.event_tags for r in got}


class TestTheMergeRailTagMove:
    async def test_survivor_is_cleared_others_retargeted_lookalikes_untouched(self, pg):
        from app.utils.event_child_repoint import (
            TAG_CLEARED_ON_KEEP,
            TAG_RETARGETED,
            _repoint_duplicate_tags,
        )

        await _seed(pg, {
            1: ["a", T(2)],             # keep: the specimen's shape
            2: ["x", T(9)],             # orphan: about to be deleted, left alone
            3: [T(2), "b"],             # third row pointing at the orphan
            4: [T(2), T(1)],            # already names keep: loses only the stale one
            5: [T(20)],                 # lookalike id: must not move
            6: None,                    # SQL NULL
            7: [],
        })
        out = await _repoint_duplicate_tags(pg, keep_id=1, orphan_id=2)
        after = await _tags(pg)

        assert after[1] == ["a"]
        assert after[2] == ["x", T(9)]
        assert after[3] == ["b", T(1)]
        assert after[4] == [T(1)]
        assert after[5] == [T(20)]
        assert after[6] is None
        assert after[7] == []
        assert out == {TAG_CLEARED_ON_KEEP: 1, TAG_RETARGETED: 2}

    async def test_no_tag_anywhere_moves_nothing(self, pg):
        from app.utils.event_child_repoint import _repoint_duplicate_tags

        await _seed(pg, {1: ["a"], 2: None, 3: [T(20)]})
        assert await _repoint_duplicate_tags(pg, keep_id=1, orphan_id=2) == {}
        assert await _tags(pg) == {1: ["a"], 2: None, 3: [T(20)]}


GAME2, NYY2 = 15317724, 15316870
DEAD_G2, DEAD_NYY2 = 15317957, 15317440
SEED = {
    GAME2: ["provenance:source:odds_api", T(DEAD_G2), "stakes:playoff_race"],
    NYY2: [T(DEAD_NYY2), "narrative:rivalry"],
    14788069: [T(15316824)],  # wrong-score row, deliberately unpinned
}


class TestTheRepair:
    async def test_dry_run_writes_nothing(self, pg):
        await _seed(pg, SEED)
        out = await m.run(pg, apply=False, restore=False)
        assert out["written"] == 0 and len(out["write"]) == 2
        assert await _tags(pg) == SEED

    async def test_apply_rerun_restore_round_trip(self, pg):
        await _seed(pg, SEED)
        out = await m.run(pg, apply=True, restore=False)
        assert out["written"] == 2
        healed = await _tags(pg)
        assert healed[GAME2] == ["provenance:source:odds_api", "stakes:playoff_race"]
        assert healed[NYY2] == ["narrative:rivalry"]
        assert healed[14788069] == [T(15316824)]

        again = await m.run(pg, apply=True, restore=False)
        assert again["written"] == 0
        assert sorted(r for r, _ in again["skip"]) == [NYY2, GAME2]

        back = await m.run(pg, apply=False, restore=True)
        assert back["written"] == 2
        restored = await _tags(pg)
        for rid in (GAME2, NYY2):
            assert sorted(restored[rid]) == sorted(SEED[rid])

    async def test_a_target_that_exists_refuses_and_writes_nothing(self, pg):
        seeded = {**SEED, DEAD_G2: ["provenance:source:statpal"]}
        await _seed(pg, seeded)
        await pg.commit()
        with pytest.raises(m.Refused, match=str(DEAD_G2)):
            await m.run(pg, apply=True, restore=False)
        await pg.rollback()
        assert await _tags(pg) == seeded
